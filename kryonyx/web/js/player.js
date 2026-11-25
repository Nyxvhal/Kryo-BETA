/* player.js — движок воспроизведения: очередь, Web Audio, громкость. */
'use strict';

const Player = {
  audio: null,
  deck: [],           // две звуковые дорожки: пока одна гаснет, вторая уже играет
  xfToken: 0,         // номер текущего перехода: старый кадр себя отменяет
  xfFrom: null,       // дорожка, которая сейчас гаснет
  handedOver: '',
  completedToken: -1,     // id трека, с которого переход уже запущен
  queue: [],
  queueRevision: 0,
  playlistContext: null,
  index: -1,
  current: null,
  ctx: null,
  srcNode: null,
  gain: null,
  comp: null,
  panner: null,
  analyser: null,
  played: 0,
  lastTick: 0,
  reported: false,
  seeking: false,
  seekRatio: null,
  holdUntilSeeked: false,
  radioBusy: false,
  intentRevision62: 0,
  attempt: 0,
  resumeAt: 0,
  wantPlay: false,
  lastResume: 0,
  failStreak: 0,
  recovering: false,
  loadToken: 0,
  busy: false,
  staged: false,      // очередь восстановлена из базы, звук ждёт кнопки
  stateTimer: null,
  stateAt: 0,
  emptyStateIntent: false,
  progressKnobs40: new Set(),

  init() {
    this.audio = $('audio');
    // Вторая дорожка — точная копия первой. Без неё «переход» мог быть
    // только последовательным: сначала тишина, потом новый трек.
    const twin = this.audio.cloneNode(false);
    twin.id = 'audio2';
    this.audio.parentNode.insertBefore(twin, this.audio.nextSibling);
    this.deck = [this.audio, twin];
    this.audio.volume = S.volume / 100;
    this.audio.preservesPitch = false;
    this.audio.playbackRate = +S.playbackSpeed || 1;

    this.deck.forEach(deck => { deck.preservesPitch = false; this.bindDeck(deck); });
    ['pTrack', 'pTrackM', 'nTrack'].forEach(id => this.bindSeek($(id)));
    this.paintState();
    this.paintIdle();
    document.addEventListener('visibilitychange', () => this.wake42());
    this.wake42();
  },

  /* Слушатели вешаются на обе дорожки, но срабатывают только у активной:
     гаснущая дорожка не должна рисовать интерфейс, двигать ползунок и
     тем более переключать трек своим `ended`. */
  bindDeck(a) {
    const live = () => a === this.audio;
    a.addEventListener('timeupdate', () => {
      if (!live()) return;
      this.onTime();
      if (window.KTray) KTray.tick();
    });
    a.addEventListener('progress', () => { if (live()) this.paintBuffer(); });
    a.addEventListener('durationchange', () => {
      if (!live()) return;
      this.paintTime(); this.pushPresence();
    });
    a.addEventListener('ended', () => {
      if (!live()) { this.rest(a); return; }
      if (a.ended) this.finish(a);
    });
    a.addEventListener('play', () => {
      if (!live()) return;
      this.paintState(); this.ensureCtx(); this.pushPresence(true);
      if (window.KTray) KTray.push();
    });
    a.addEventListener('pause', () => {
      if (!live()) return;
      if (!this.wantPlay || a.ended) this.setBusy(false);
      this.paintState(); this.watch(); this.pushPresence(true); this.saveState(true);
      if (window.KTray) KTray.push();
    });
    a.addEventListener('waiting', () => { if (live()) { this.paintState(); this.setBusy(true); } });
    a.addEventListener('loadstart', () => { if (live()) this.setBusy(true); });
    a.addEventListener('stalled', () => { if (live() && this.wantPlay && a.readyState < 3) this.setBusy(true); });
    a.addEventListener('canplay', () => { if (live()) { this.setBusy(false); this.pushPresence(); this.prefetchNext(); } });
    a.addEventListener('canplaythrough', () => { if (live()) this.prefetchNext(); });
    // Длительность приходит позже первых кадров: без этого события Discord
    // успевал получить duration=0 и рисовал счётчик вместо полосы времени.
    a.addEventListener('loadeddata', () => { if (live()) this.pushPresence(); });
    a.addEventListener('playing', () => { if (live()) { this.setBusy(false); this.failStreak = 0; this.prefetchNext(); } });
    a.addEventListener('error', () => { if (live()) this.onError(); });
    a.addEventListener('loadedmetadata', () => {
      if (!live()) return;
      this.paintTime(); // Metadata is not buffered audio: canplay/playing ends loading.
    });
    // Перемотка: караоке встаёт на новое место сразу, ещё до того как
    // браузер догрузит звук, и повторно — когда позиция окончательно принята.
    a.addEventListener('seeking', () => { if (live()) { if (this.wantPlay && a.readyState < 3) this.setBusy(true); Karaoke.seek(a.currentTime); } });
    a.addEventListener('seeked', () => {
      if (!live()) return;
      this.holdUntilSeeked = false;
      this.seekRatio = null;
      // Перемотали назад — переход с этого трека снова разрешён.
      this.handedOver = '';
      this.paintProgress();
      this.paintTime();
      Karaoke.seek(a.currentTime);
      this.pushPresence();
      this.saveState();
    });
    a.addEventListener('ratechange', () => {
      if (!live()) return;
      const rate=Math.max(.25,Math.min(2,a.playbackRate || 1));
      if(a.playbackRate!==rate)a.playbackRate=rate;
      Karaoke.seek(a.currentTime);
    });
  },

  // A source may emit ended twice, or WebView may miss that event entirely.
  finish(a = this.audio) {
    if (a !== this.audio || !a.ended || !this.current || this.completedToken === this.loadToken) return;
    this.completedToken = this.loadToken;
    this.paintState();
    this.next(true).catch(() => { this.wantPlay = false; this.setBusy(false); this.paintState(); });
  },

  /* v42: one cancellable frame owner. Paused UI sleeps; hidden playback
     retains a low-frequency watchdog/crossfade clock, never a second media clock. */
  wake42() {
    if (this.frame42) cancelAnimationFrame(this.frame42);
    if (this.timer42) clearTimeout(this.timer42);
    this.frame42 = 0; this.timer42 = 0; this.visualAt42 = 0;
    // Defer until source/deck mutations complete (setBusy runs before src changes).
    if (!document.hidden) this.frame42=requestAnimationFrame(t=>{this.frame42=0;this.tick(t);});
    else this.timer42=setTimeout(()=>{this.timer42=0;this.tick();},0);
  },

  tick(stamp = performance.now()) {
    const a = this.audio;
    if (!a) return;
    const visible = !document.hidden && !document.querySelector('.modal.on');
    const stage = visible && $('now')?.classList.contains('on');
    const playing = !a.paused && !a.ended;
    const visual = visible && (playing || !this.visualAt42);
    // Bound high-refresh displays to 60 UI updates; progress needs only 30.
    if (visual && (!this.visualAt42 || stamp - this.visualAt42 >= 1000/60 - .5)) {
      this.visualAt42 = this.visualAt42 ? this.visualAt42 + Math.max(1,Math.floor((stamp-this.visualAt42+.5)/(1000/60)))*(1000/60) : stamp;
      if (stage) Karaoke.onTime(a.currentTime);
      if (!this.seeking && !this.holdUntilSeeked &&
          (!playing || !this.progressAt42 || stamp - this.progressAt42 >= 1000/30 - .5)) {
        this.progressAt42 = this.progressAt42 ? this.progressAt42 + Math.max(1,Math.floor((stamp-this.progressAt42+.5)/(1000/30)))*(1000/30) : stamp;
        this.paintProgress(); this.paintTime();
      }
    }
    if (a.ended && this.wantPlay && !this.recovering) this.finish(a);
    this.handover();
    if (!this._houseAt40 || stamp - this._houseAt40 >= 250) {
      this._houseAt40 = stamp;
      this.watch(); this.presenceHeartbeat();
      if (!a.paused && Date.now() - this.stateAt > 5000) this.saveState(true);
    }
    if (this.frame42 || this.timer42) return;
    if (visible && !a.paused && !a.ended) {
      this.frame42 = requestAnimationFrame(t => { this.frame42 = 0; this.tick(t); });
    } else if ((!a.paused && !a.ended) || this.wantPlay || this.recovering) {
      // Keep transitions functional in minimized WebViews; ended events remain authoritative.
      this.timer42 = setTimeout(() => { this.timer42 = 0; this.tick(); }, 250);
    }
  },

  /* Переход начинается ДО конца трека, как в Spotify: за выбранные секунды
     до последней ноты следующая песня уже поднимается. Если ждать события
     `ended`, наложения не получится в принципе — старый трек к этому
     моменту уже молчит. */
  handover() {
    const secs = Math.max(0, +S.fade || 0);
    const a = this.audio;
    if (!secs || !a || a.paused || a.ended || this.busy) return;
    if (!this.current || S.repeat === 'one') return;
    const total = a.duration;
    if (!total || !isFinite(total)) return;
    if (total - a.currentTime > secs) return;
    // Переход с этого трека уже запущен — второй раз не начинаем.
    const mark = this.current.id + ':' + this.index;
    if (this.handedOver === mark) return;
    const last = this.index >= this.queue.length - 1;
    if (last && S.repeat !== 'all') return;     // дальше нечего накладывать
    this.handedOver = mark;
    this.next(true);
  },

  /* Сторож: WebView и медиаклавиши Windows иногда ставят трек на паузу сами.
     Если пользователь паузу не нажимал — просто продолжаем играть. */
  watch() {
    const a = this.audio;
    if (!this.wantPlay || !this.current || !a || (typeof Clips !== 'undefined' && Clips.active)) return;
    if (!a.paused || a.ended) return;
    if (a.duration && a.currentTime >= a.duration - 0.35) return;
    const now = performance.now();
    if (now - this.lastResume < 800) return;
    this.lastResume = now;
    const promise = a.play();
    if (promise && promise.catch) promise.catch(() => {});
  },

  /* ------------------------------------------------------------ Web Audio */
  ensureCtx() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return this.ctx; }
    try {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      // Обе дорожки заходят в один сумматор: эквалайзер, баланс, громкость
      // и анализатор одни на весь плеер, поэтому во время перехода ничего
      // не пропадает — ни кривая EQ, ни «живой» фон караоке.
      this.mix = this.ctx.createGain();
      this.srcNodes = this.deck.map(deck => {
        const node = this.ctx.createMediaElementSource(deck);
        node.connect(this.mix);
        return node;
      });
      this.srcNode = this.mix;
      this.gain = this.ctx.createGain();
      this.comp = this.ctx.createDynamicsCompressor();
      this.comp.threshold.value = -24;
      this.comp.knee.value = 24;
      this.comp.ratio.value = 3;
      this.comp.attack.value = 0.008;
      this.comp.release.value = 0.25;
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 2048;
      this.analyser.smoothingTimeConstant = 0.24;
      // Баланс между колонками. StereoPannerNode есть не везде — без него
      // просто нет регулятора, остальной звук работает как прежде.
      try {
        this.panner = this.ctx.createStereoPanner();
        this.panner.pan.value = Math.max(-1, Math.min(1, +S.balance || 0));
      } catch { this.panner = null; }
      this.rebuild();
    } catch (err) {
      console.warn(t('Web Audio unavailable'), err);
      this.ctx = null;
    }
    return this.ctx;
  },

  /* Цепочка звука:
       <audio> → [компрессор] → эквалайзер → баланс → громкость → анализатор → выход
     Выключенные узлы из графа выпадают совсем, а не стоят «прозрачными». */
  rebuild() {
    if (!this.ctx) return;
    [this.srcNode, this.gain, this.comp, this.analyser, this.panner]
      .forEach(node => { try { node && node.disconnect(); } catch {} });
    if (typeof Equalizer !== 'undefined') Equalizer.detach();
    let tail = this.srcNode;
    if (S.normalize) { tail.connect(this.comp); tail = this.comp; }
    if (typeof Equalizer !== 'undefined') tail = Equalizer.attach(this.ctx, tail);
    if (this.panner) { tail.connect(this.panner); tail = this.panner; }
    tail.connect(this.gain);
    this.gain.connect(this.analyser);
    this.analyser.connect(this.ctx.destination);
  },

  /* Баланс: −1 левее, 0 центр, +1 правее. */
  setBalance(value) {
    const pan = Math.max(-1, Math.min(1, Math.round((+value || 0) * 100) / 100));
    S.balance = pan;
    this.ensureCtx();
    if (this.panner) {
      try { this.panner.pan.setTargetAtTime(pan, this.ctx.currentTime, 0.02); }
      catch { this.panner.pan.value = pan; }
    }
    saveSettings();
  },

  /* ------------------------------------------------- состояние на диске */
  /* Очередь, текущий трек и позиция лежат в той же базе, что плейлисты, —
     после перезапуска приложение открывается ровно там, где его закрыли. */
  snapshot() {
    if (!this.current && !this.queue.length) {
      // Do not overwrite a state that is still being restored during startup.
      if (!this.emptyStateIntent) return null;
      return { queue: [], index: -1, position: 0, track: null, playlistContext: null, at: Date.now() };
    }
    // Keep the current item inside the bounded snapshot, including for long queues.
    const start = Math.max(0, Math.min(this.index - 100, this.queue.length - 500));
    return {
      queue: this.queue.slice(start, start + 500),
      index: this.index - start,
      position: Math.round((this.staged ? this.resumeAt : (this.audio ? this.audio.currentTime : 0)) * 10) / 10,
      track: this.current || null,
      playlistContext: this.playlistContext,
      at: Date.now(),
    };
  },

  saveState(now, beacon) {
    clearTimeout(this.stateTimer);
    const send = () => {
      const value = this.snapshot();
      if (!value) return;
      this.stateAt = Date.now();
      const body = { key: 'player', value };
      if (beacon && navigator.sendBeacon) {
        try {
          if (navigator.sendBeacon('/api/state/beacon',
            new Blob([JSON.stringify(body)], { type: 'application/json' }))) return;
        } catch { /* упало — уходим обычным запросом */ }
      }
      api('/api/state', { method: 'PUT', body }).catch(() => {});
    };
    if (now) send(); else this.stateTimer = setTimeout(send, 1200);
  },

  async restoreState() {
    let saved = null;
    try {
      saved = (await api('/api/state?key=player', { timeout: 6000 }) || {}).value;
    } catch { return; }
    if (!saved || !Array.isArray(saved.queue) || !saved.queue.length) return;
    if (this.current || this.emptyStateIntent) return; // пользователь уже изменил состояние
    this.queue = saved.queue.filter(item => item && item.id);
    if (!this.queue.length) return;
    // Исходного порядка с прошлого запуска нет — считаем им то, что лежит.
    this.order = this.queue.slice();
    this.index = Math.max(0, Math.min(this.queue.length - 1, parseInt(saved.index, 10) || 0));
    this.current = this.queue[this.index];
    const context = saved.playlistContext;
    this.playlistContext = context && typeof context.id === 'string' && Array.isArray(context.trackIds)
      && context.trackIds.includes(this.current.id)
      ? {id:context.id.slice(0,120),trackIds:context.trackIds.filter(id=>typeof id==='string').slice(0,500)} : null;
    this.resumeAt = Math.max(0, +saved.position || 0);
    this.staged = true;
    this.paintTrack();
    this.paintTime();
    this.paintState();
    Views.markPlaying();
    Views.renderQueue();
    if (typeof Karaoke !== 'undefined') Karaoke.onTrack(this.current);
  },

  /* ------------------------------------------------------------- очередь */
  /* Исходный порядок очереди: по нему перемешка выключается обратно. */
  order: [],

  /* Новая очередь с учётом перемешки.

     Раньше S.shuffle работал ровно один раз — в момент нажатия кнопки. Стоило
     открыть другой плейлист или подборку, как очередь снова строилась по
     порядку, хотя кнопка продолжала гореть. Теперь перемешка — это режим: он
     применяется к каждой новой очереди, а выбранный трек остаётся первым.
     Исходный порядок запоминается, поэтому выключение перемешки возвращает
     список как был. */
  queueFrom(list, startIndex) {
    const items = (list || []).slice();
    this.order = items.slice();
    const at = Math.max(0, Math.min(items.length - 1, startIndex || 0));
    if (!S.shuffle || items.length < 2) return { queue: items, index: at };
    const rest = items.slice();
    const [picked] = rest.splice(at, 1);
    return { queue: [picked, ...this.shuffled(rest)], index: 0 };
  },

  /* Перемешать то, что уже играет, оставив текущий трек на месте. */
  reshuffle() {
    if (typeof Wave61 !== 'undefined' && Wave61.active) return;
    if (this.queue.length < 2) return;
    if (!this.order.length) this.order = this.queue.slice();
    const current = this.queue[this.index];
    const rest = this.queue.filter((_, i) => i !== this.index);
    this.queue = [current, ...this.shuffled(rest)];
    this.index = 0;
    this.queueRevision++;
    this.prefetchNext();
  },

  /* Вернуть исходный порядок, не прерывая текущий трек. */
  unshuffle() {
    if (typeof Wave61 !== 'undefined' && Wave61.active) return;
    const current = this.queue[this.index];
    const ids = new Set(this.queue.map(item => item.id));
    const source = this.order.filter(item => ids.has(item.id));
    if (source.length !== this.queue.length) { this.order = this.queue.slice(); return; }
    this.queue = source;
    this.index = current ? Math.max(0, source.findIndex(item => item.id === current.id)) : 0;
    this.queueRevision++;
    this.prefetchNext();
  },

  play(track, list, startIndex) {
    this.queueRevision++;
    if (list) {
      this.playlistContext = this.contextForList(list);
      const built = this.queueFrom(
        list,
        startIndex != null ? startIndex
          : Math.max(0, list.findIndex(t => t && track && t.id === track.id)));
      this.queue = built.queue;
      this.index = built.index;
    } else {
      const at = this.queue.findIndex(t => t.id === track.id);
      if (at >= 0) this.index = at;
      else { this.queue.splice(this.index + 1, 0, track); this.index += 1; }
    }
    if (this.playlistContext && !this.playlistContext.trackIds.includes(track.id)) this.playlistContext = null;
    this.load();
  },

  contextForList(list) {
    if (typeof Workspace === 'undefined' || list !== Workspace.listVisible) return null;
    const state = Workspace.listState;
    const id = state?.type === 'liked' ? 'liked' : state?.type === 'playlist' ? String(state.id) : null;
    return id === null ? null : {id,trackIds:list.map(t=>t.id)};
  },

  playList(list, shuffle, context) {
    if (!list || !list.length) { toast(t('Nothing here yet')); return; }
    this.queueRevision++;
    this.playlistContext = context ? {id:String(context.id),trackIds:list.map(t=>t.id)} : this.contextForList(list);
    this.order = list.slice();
    // shuffle — это кнопка «Вперемешку» у плейлиста; S.shuffle — включённый
    // режим перемешки. Любого из двух достаточно.
    const items = (shuffle || S.shuffle) ? this.shuffled(list.slice()) : list.slice();
    this.queue = items;
    this.index = 0;
    this.load();
  },

  shuffled(list) {
    const copy = list.slice();
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  },

  addNext(track) {
    this.queue.splice(this.index + 1, 0, track);
    this.queueRevision++;
    Views.renderQueue();
    this.saveState();
    this.prefetchNext();
    toast(t('Playing next'));
  },
  addLast(track) {
    this.queue.push(track);
    this.queueRevision++;
    Views.renderQueue();
    this.saveState();
    this.prefetchNext();
    toast(t('Added to the queue'));
  },

  /* Убрать трек из очереди. Играющий трек не обрываем: он доигрывает,
     а из списка уходит только то, что ещё не прозвучало. */
  removeAt(at) {
    if (at < 0 || at >= this.queue.length) return;
    if (at === this.index) {
      // Текущий трек: снимаем его и сразу переходим к следующему.
      this.queue.splice(at, 1);
      if (!this.queue.length) {
        this.index = -1;
        this.emptyStateIntent = true;
        this.wantPlay = false;
        this.audio.pause();
        this.audio.removeAttribute('src');
        this.audio.load();
        this.current = null;
        this.paintIdle();
        this.paintState();
      } else {
        this.index = Math.min(at, this.queue.length - 1);
        this.load();
      }
    } else {
      this.queue.splice(at, 1);
      if (at < this.index) this.index -= 1;
    }
    Views.renderQueue();
    Views.markPlaying();
    this.queueRevision++;
    this.saveState();
    this.prefetchNext();
  },

  /* Перенос строки очереди. Указатель на играющий трек едет вместе с ним —
     звук при этом не прерывается. */
  move(from, to) {
    const n = this.queue.length;
    if (from === to || from < 0 || to < 0 || from >= n || to >= n) return;
    const [item] = this.queue.splice(from, 1);
    this.queue.splice(to, 0, item);
    if (this.index === from) this.index = to;
    else if (from < this.index && to >= this.index) this.index -= 1;
    else if (from > this.index && to <= this.index) this.index += 1;
    Views.renderQueue();
    Views.markPlaying();
    this.queueRevision++;
    this.saveState();
    this.prefetchNext();
  },

  /* Очистить очередь целиком, кроме играющего трека. */
  clearQueue() {
    if (this.current && this.index >= 0) {
      this.queue = [this.queue[this.index]];
      this.index = 0;
    } else {
      this.queue = [];
      this.index = -1;
      this.emptyStateIntent = true;
    }
    Views.renderQueue();
    Views.markPlaying();
    this.saveState();
  },

  load(at = 0) {
    const track = this.queue[this.index];
    if (!track) return;
    this.emptyStateIntent = false;
    if(typeof Finder!=='undefined'&&Finder.previewId)Finder.stopPreview(false);
    this.staged = false;
    this.handedOver = '';
    this.completedToken = -1;
    this.report(true);
    this.current = track;
    this.seekRatio = null;
    this.holdUntilSeeked = false;
    this.played = 0;
    this.listenSession = (globalThis.crypto?.randomUUID?.() || Date.now() + '-' + Math.random());
    this.reported = false;
    this.lastTick = 0;

    this.attempt = 0;
    this.resumeAt = Math.max(0, +at || 0);
    this.recovering = false;
    this.loadToken++;
    const url = this.streamUrl(track, false);
    this.start(url);

    this.paintTrack();
    // Длительность известна из карточки трека — показываем её сразу,
    // не дожидаясь первого тика воспроизведения.
    this.paintTime();
    Views.markPlaying();
    Views.renderQueue();
    Karaoke.onTrack(track);
    if (typeof Clips !== 'undefined') Clips.onTrack(track);
    // Prefetch begins on canplay, never while the current track is resolving.
    this.saveState();
  },

  streamUrl(track, fallback, fresh) {
    const params = new URLSearchParams({ id: track.id });
    // Metadata-only providers (Spotify) need these immediately so the server
    // can match the track to YouTube/SoundCloud without a failed first load.
    if (track.title) params.set('title', track.title);
    if (track.artist) params.set('artist', track.artist);
    if (fallback) {
      params.set('fb', '1');
    }
    // Повтор после обрыва обязан получить новую ссылку: старая лежит в кэше
    // сервера, и если источник её уже закрыл, она закрыта навсегда.
    if (fresh) params.set('fresh', '1');
    return '/api/stream?' + params.toString();
  },

  setBusy(on) {
    const was = this.busy;
    this.busy = !!on;
    document.body.classList.toggle('busy', this.busy);
    if (was !== this.busy) { this.paintState(); if (typeof MiniPlayer !== 'undefined') MiniPlayer.push(true); }
    // Пока трек грузится, статус в Discord не должен «играть»: раньше полоса
    // времени уезжала вперёд, хотя звука ещё не было.
    if (was !== this.busy && this.current && !this.recovering) this.pushPresence(true);
  },

  start(url) {
    this.setBusy(true);
    this.wantPlay = true;
    const at = this.resumeAt || 0;
    this.resumeAt = 0;

    /* Плавный переход вместо плавного затухания.

       Было: громкость уводилась в ноль, звук пропадал совсем, и только
       потом с нуля поднимался новый трек — между песнями оставалась
       заметная дыра тишины.

       Стало: новый трек уходит на свободную дорожку и поднимается ровно
       тогда, когда старая опускается. Кривые равной мощности (cos/sin)
       держат суммарную громкость постоянной, поэтому в середине перехода
       нет провала — так это сделано у Spotify. */
    const secs = Math.max(0, +S.fade || 0);
    const old = this.audio;
    const overlap = secs > 0 && old && !old.paused && !old.ended && old.currentTime > 0.2;
    if (overlap) {
      this.audio = this.deck[0] === old ? this.deck[1] : this.deck[0];
      this.audio.preservesPitch = false;
      this.audio.playbackRate = +S.playbackSpeed || 1;
      this.audio.volume = 0;
    } else {
      this.rest(this.deck[0] === this.audio ? this.deck[1] : this.deck[0]);
      this.audio.volume = S.volume / 100;
    }

    this.audio.src = url;
    try { this.audio.currentTime = at; } catch { /* позиция станет доступна позже */ }
    if (at > 0) {
      const seek = () => {
        this.audio.removeEventListener('loadedmetadata', seek);
        try { this.audio.currentTime = at; } catch {}
      };
      this.audio.addEventListener('loadedmetadata', seek);
    }
    this.audio.preservesPitch = false;
    this.audio.playbackRate = +S.playbackSpeed || 1;
    const promise = this.audio.play();
    if (promise && promise.catch) {
      const pendingAudio = this.audio, pendingToken = this.loadToken;
      promise.catch(error => {
        if (pendingAudio !== this.audio || pendingToken !== this.loadToken) return;
        if (error?.name === 'NotAllowedError') {
          this.wantPlay = false; this.setBusy(false); this.paintState();
        }
      });
    }
    if (overlap) this.crossfade(old, this.audio, secs);
  },

  /* Один переход: `from` гаснет, `to` поднимается, оба звучат одновременно. */
  crossfade(from, to, secs) {
    const ms = Math.max(250, Math.min(secs * 1000, 12000));
    const target = S.volume / 100;
    const from0 = from.volume;
    const token = ++this.xfToken;
    this.xfFrom = from;
    const t0 = performance.now();
    const step = () => {
      if (token !== this.xfToken) return;      // начался следующий переход
      const k = Math.min(1, (performance.now() - t0) / ms);
      const angle = k * Math.PI / 2;
      from.volume = Math.max(0, Math.min(1, from0 * Math.cos(angle)));
      if (this.audio === to) to.volume = Math.max(0, Math.min(1, target * Math.sin(angle)));
      if (k < 1) { requestAnimationFrame(step); return; }
      this.xfFrom = null;
      this.rest(from);
    };
    requestAnimationFrame(step);
  },

  /* Отпустить дорожку: остановить и отцепить поток, чтобы он не грузился
     в фоне. Громкость возвращаем — дорожка ещё пригодится. */
  rest(deck) {
    if (!deck || deck === this.audio) return;
    try {
      deck.pause();
      deck.removeAttribute('src');
      deck.load();
    } catch { /* дорожка и так пуста */ }
    deck.volume = S.volume / 100;
  },

  mediaPlay() {
    if (this.staged || this.audio.paused || this.audio.ended || this.audio.error) this.toggle();
    else this.wantPlay = true;
  },

  mediaPause() {
    this.intentRevision62++;
    this.wantPlay = false;
    this.setBusy(false);
    if (!this.audio.paused) this.audio.pause();
  },

  toggle() {
    if(typeof Finder!=='undefined'&&Finder.previewId)Finder.stopPreview(false);
    // Очередь после перезапуска: первое нажатие продолжает с той же секунды.
    if (this.staged) { this.load(this.resumeAt); return; }
    if (!this.current) {
      if (this.queue.length) this.load();
      return;
    }
    const a = this.audio;
    if(this.busy&&this.wantPlay){this.mediaPause();return;}
    if (a.ended || (Number.isFinite(a.duration) && a.duration > 0 && a.currentTime >= a.duration - .05)) { this.load(0); return; }
    if (a.error) { this.load(Math.max(0, a.currentTime || 0)); return; }
    if (this.audio.paused) {
      this.wantPlay = true;
      this.ensureCtx();
      this.audio.play().catch(() => {});
    } else {
      this.intentRevision62++;
      this.wantPlay = false;        // пауза от пользователя — сторож не мешает
      this.audio.pause();
    }
  },

  async next(auto) {
    this.report(!auto);
    if (S.repeat === 'one' && auto) { this.load(0); return; }
    if (this.index < this.queue.length - 1) { this.index += 1; this.load(); return; }
    if (S.repeat === 'all' && this.queue.length) { this.index = 0; this.load(); return; }
    if (S.endlessRadio && this.current && !this.radioBusy) {
      this.radioBusy = true;
      const radioTrack = this.current, radioRevision = this.queueRevision, radioToken = this.loadToken, radioIntent = this.intentRevision62;
      try {
        const data = await api('/api/radio', { method: 'POST', body: { track: this.current } });
        if (this.current !== radioTrack || this.queueRevision !== radioRevision || this.loadToken !== radioToken || this.intentRevision62 !== radioIntent) return;
        const items = (data.items || []).filter(t => t && t.id && t.id !== radioTrack.id);
        if (items.length) {
          this.queue = this.queue.concat(items);
          this.index += 1;
          this.load();
          toast(t('Radio keeps the queue going'));
          return;
        }
      } catch { /* нет сети — просто остановимся */ }
      finally { this.radioBusy = false; }
    }
    if (auto) { this.wantPlay = false; this.setBusy(false); this.paintState(); this.saveState(true); }
  },

  prev() {
    if (this.audio.currentTime > 4) { this.audio.currentTime = 0; return; }
    if (this.index > 0) { this.index -= 1; this.load(); }
    else this.audio.currentTime = 0;
  },

  setPrefetchState(state, trackId = '', extra = {}) {
    this.prefetchState = {
      state,
      trackId: trackId || '',
      cached: !!extra.cached,
      key: extra.key || '',
      error: extra.error || '',
      updatedAt: Date.now(),
    };
  },

  _stopWarmAudio() {
    if (typeof clearTimeout === 'function' && this._prefetchPollTimer) clearTimeout(this._prefetchPollTimer);
    this._prefetchPollTimer = null;
    if (this._warmAudio30) {
      try {
        this._warmAudio30.pause();
        this._warmAudio30.removeAttribute('src');
        this._warmAudio30.load();
      } catch {}
    }
  },

  _warmNextAudio(track) {
    if (typeof Audio === 'undefined' || !track?.id) return;
    if (!this._warmAudio30) {
      this._warmAudio30 = new Audio();
      this._warmAudio30.muted = true;
      this._warmAudio30.volume = 0;
    }
    const q = new URLSearchParams({ id: track.id, title: track.title || '', artist: track.artist || '' });
    if (typeof track.duration === 'number' && isFinite(track.duration) && track.duration > 0) q.set('dur', String(track.duration));
    const url = '/api/stream?' + q;
    if (this._warmAudio30.dataset?.warmUrl === url || this._warmAudio30.src?.endsWith(url)) return;
    if (this._warmAudio30.dataset) this._warmAudio30.dataset.warmUrl = url;
    this._warmAudio30.preload = 'auto';
    this._warmAudio30.src = url;
  },

  _pollPrefetchStatus(track, key, controller, attempt = 0) {
    if (typeof setTimeout !== 'function' || this._prefetchKey30 !== key || controller.signal.aborted || attempt >= 30) return;
    this._prefetchPollTimer = setTimeout(() => {
      if (this._prefetchKey30 !== key || controller.signal.aborted) return;
      const statusParams = new URLSearchParams({ id: track.id, status: '1' });
      fetch('/api/prefetch?' + statusParams, { signal: controller.signal }).then(async r => {
        if (!r || r.ok === false) return;
        const st = typeof r.json === 'function' ? await r.json().catch(() => null) : null;
        if (this._prefetchKey30 !== key || controller.signal.aborted) return;
        if (st?.state === 'downloaded' || st?.state === 'resolved' || st?.cached) {
          this.setPrefetchState('ready', track.id, { key, cached: !!st.cached });
          this._warmNextAudio(track);
        } else if (st?.state === 'error' || st?.state === 'cancelled') {
          this.setPrefetchState(st.state === 'cancelled' ? 'cancelled' : 'failed', track.id, { key });
        } else {
          this._pollPrefetchStatus(track, key, controller, attempt + 1);
        }
      }).catch(() => {});
    }, 1200);
  },

  /* One successor only. The queue is already in its effective shuffle order.
     Repeat-one has no different successor; radio is resolved only at queue end. */
  prefetchNext() {
    const wave = typeof Wave61 !== 'undefined' && Wave61.active;
    const enabled = (S.prefetch || wave) && (S.repeat !== 'one' || wave);
    const track = enabled ? this.queue[this.index + 1] || (!wave && S.repeat === 'all' ? this.queue[0] : null) : null;
    if (!track?.id || track.id === this.current?.id) {
      if (this._prefetchKey30) {
        this._prefetchKey30 = ''; this._prefetchController30?.abort();
        this._stopWarmAudio();
        this.setPrefetchState('cancelled', '');
        fetch('/api/prefetch?' + new URLSearchParams({cancel:'1',current:this.current?.id||''})).catch(()=>{});
      } else {
        this._stopWarmAudio();
        this.setPrefetchState('idle', '');
      }
      return;
    }
    if (this.audio.readyState < 3) {
      this.setPrefetchState('queued', track.id);
      return;
    }
    const key = `${this.loadToken}:${this.queueRevision}:${track.id}`;
    if (key === this._prefetchKey30) return;
    this._prefetchKey30 = key;
    this._prefetchController30?.abort();
    this._stopWarmAudio();
    const controller = this._prefetchController30 = new AbortController();
    this.setPrefetchState('resolving', track.id, { key });
    const params = new URLSearchParams({id:track.id,title:track.title||'',artist:track.artist||'',current:this.current?.id||''});
    fetch('/api/prefetch?' + params, {signal:controller.signal}).then(async r=>{
      if (!r || r.ok === false) throw new Error('prefetch unavailable');
      let data = null;
      if (typeof r.json === 'function') { try { data = await r.json(); } catch {} }
      if (this._prefetchKey30 !== key || controller.signal.aborted) {
        if (this.prefetchState?.key === key) this.setPrefetchState('stale', track.id, { key });
        return;
      }
      if (data?.ready || data?.cached) {
        this.setPrefetchState('ready', track.id, { key, cached: !!data.cached });
        this._warmNextAudio(track);
      } else if (data?.busy) {
        this.setPrefetchState('downloading', track.id, { key });
        this._pollPrefetchStatus(track, key, controller, 0);
      } else {
        this.setPrefetchState('ready', track.id, { key });
        this._warmNextAudio(track);
      }
      if(wave && Wave61.active && this.queue[this.index+1]?.id===track.id) Wave61.warmNext();
    }).catch(e=>{
      if(e?.name==='AbortError'||this._prefetchKey30!==key){
        if (this.prefetchState?.key === key) this.setPrefetchState('stale', track.id, { key });
        return;
      }
      this._prefetchKey30='';
      this.setPrefetchState('failed', track.id, { key, error: e?.message || 'error' });
      if(wave && Wave61.active && this.queue[this.index+1]?.id===track.id){Wave61.warm='error';Wave61.render()}
    });
  },

  seek(ratio) {
    const dur = this.audio.duration;
    if (dur && isFinite(dur)) this.audio.currentTime = dur * ratio;
  },

  bindSeek(trackEl) {
    const knob40=trackEl?.querySelector('.knob');
    if(knob40)this.progressKnobs40.add(knob40);
    if (!trackEl) return;
    const ratioAt = event => {
      const rect = trackEl.getBoundingClientRect();
      const x = (event.clientX != null ? event.clientX
        : (event.touches && event.touches[0] ? event.touches[0].clientX : 0)) - rect.left;
      return Math.max(0, Math.min(1, rect.width ? x / rect.width : 0));
    };

    const onMove = event => {
      if (!this.seeking) return;
      this.seekRatio = ratioAt(event);
      this.paintProgress(this.seekRatio);      // рисуем сразу, не ждём аудио
      this.paintTime(this.seekRatio);
    };

    const onUp = event => {
      if (!this.seeking) return;
      const ratio = ratioAt(event);
      this.seeking = false;
      document.querySelectorAll('.track.drag').forEach(n => n.classList.remove('drag'));
      removeEventListener('pointermove', onMove);
      removeEventListener('pointerup', onUp);
      removeEventListener('pointercancel', onUp);
      const duration = this.audio.duration;
      const changed = Number.isFinite(duration) && duration > 0 && Math.abs(this.audio.currentTime-duration*ratio) > .015;
      this.holdUntilSeeked = changed;
      this.seekRatio = changed ? ratio : null;
      this.seek(ratio);
      // ползунок остаётся на месте до события seeked — иначе он «отскакивает»
      this.holdUntilSeeked = changed && this.audio.seeking;
      this.seekRatio = this.holdUntilSeeked ? ratio : null;
      this.paintProgress(); this.paintTime();
    };

    trackEl.addEventListener('pointerdown', event => {
      if (event.button != null && event.button !== 0) return;
      event.preventDefault();
      this.seeking = true;
      trackEl.classList.add('drag');
      onMove(event);
      addEventListener('pointermove', onMove);
      addEventListener('pointerup', onUp);
      addEventListener('pointercancel', onUp);
    });

    // колесо над полосой — точная перемотка на ±5 с
    trackEl.addEventListener('wheel', event => {
      event.preventDefault();
      this.nudge(event.deltaY > 0 ? -5 : 5);
    }, { passive: false });
  },

  /* --------------------------------------------------------- телеметрия */
  /* timeupdate прилетает рвано (раз в ~0.25 с и с плавающим шагом), поэтому
     караоке отсюда больше НЕ обновляется: это была вторая, «дрожащая»
     шкала времени поверх кадровой, и от неё шёл рассинхрон. Здесь остаются
     только счётчики и подписи. */
  onTime() {
    const now = performance.now();
    if (this.lastTick) this.played += (now - this.lastTick) / 1000;
    this.lastTick = now;
    if (!document.hidden && !document.querySelector('.modal.on') && !this.seeking && !this.holdUntilSeeked && !this.frame42) { this.paintProgress(); this.paintTime(); }
    if (!this.reported && this.played > 25) { this.reported = true; this.report(false); }
  },

  report(skipped) {
    const track = this.current;
    if (!track || this.played < 4) return;
    const duration = this.audio.duration || track.duration || 0;
    const completed = duration ? this.audio.currentTime / duration > 0.9 : false;
    api('/api/play', {
      method: 'POST',
      body: { track, seconds: Math.round(this.played), completed, skipped: !!skipped && !completed, session_id: this.listenSession },
    }).then(() => Studio.refreshStats(track.id)).catch(() => {});
    this.played = 0;
    this.lastTick = 0;
  },

  onError() {
    const a = this.audio;
    const err = a.error;
    // Смена источника, пустой src и отмена загрузки — это не ошибки трека.
    if (!this.current || !a.src) return;
    if (err && err.code === 1) return;                       // MEDIA_ERR_ABORTED
    if (a.networkState === 0 /* NETWORK_EMPTY */) return;
    if (this.recovering) return;

    // Трек НИКОГДА не переключается сам: если поток оборвался, восстанавливаем
    // его с той же секунды. Переключить может только пользователь или конец трека.
    this.recovering = true;
    this.setBusy(true);
    const track = this.current;
    const token = this.loadToken;
    const at = a.currentTime || 0;
    const done = () => { this.recovering = false; };

    // failStreak переживает load(): без него плеер мог ходить по кругу
    // часами. В журнале это выглядело так: «link is stale (403) attempt 2,
    // attempt 3, interrupted» — и всё заново каждые полторы минуты, пока
    // YouTube не отдаст рабочую ссылку. Счётчик обнуляется только когда
    // звук действительно пошёл (событие playing).
    this.failStreak = (this.failStreak || 0) + 1;
    if (this.attempt < 4 && this.failStreak <= 6) {
      this.attempt++;
      const fallback = this.attempt >= 2 && S.autoFallback !== false;
      setTimeout(() => {
        if (token !== this.loadToken || this.current !== track) return done();
        done();
        this.resumeAt = at;
        this.start(this.streamUrl(track, fallback, true));
      }, 300 * this.attempt);
      return;
    }

    // Совсем не открылось — просто останавливаемся и говорим об этом один раз.
    done();
    this.setBusy(false);
    this.wantPlay = false;
    a.pause();
    // Самая частая причина — не сломанный трек, а пропавшая сеть: в логах
    // это getaddrinfo failed у всех источников сразу. Пишем об этом прямо,
    // иначе пользователь ищет проблему в плеере.
    toast(navigator.onLine === false
      ? t('No internet connection: the track cannot be loaded')
      : t('This track would not start. Try another source in the track menu'),
      6000);
    // Повторный «Play» по этому же треку — это уже осознанное решение
    // человека, поэтому даём ему полный запас попыток заново.
    this.failStreak = 0;
  },

  /* Статус «сейчас играет» для интеграций (Discord Rich Presence, Last.fm).
     Кадр уходит при смене трека, паузе и перемотке, плюс раз в полминуты —
     чтобы полоса времени в Discord не разъезжалась. */
  pushPresence(now) {
    clearTimeout(this._presenceTimer);
    const send = () => {
      this._presenceAt = Date.now();
      const a = this.audio;
      // «Играет» только когда звук реально идёт: буферизация и ожидание
      // данных считаются паузой, иначе карточка Discord показывает движение
      // там, где трек ещё не загрузился.
      const paused = !a || a.paused;
      // Загрузка — это не пауза пользователя: карточку не прячем, но и
      // полосу времени не запускаем, пока звука ещё нет.
      const loading = !paused && (this.busy || a.readyState < 3);
      api('/api/nowplaying', {
        method: 'POST',
        body: {
          track: this.current || null,
          position: a ? a.currentTime : 0,
          // Длительность берём у самого аудио: в карточке поиска её может не
          // быть, а без неё в Discord вместо полосы времени голый счётчик.
          duration: this.realDuration(),
          paused,
          loading,
          // Скорость нужна Discord: на 1.5x трек кончается в полтора раза
          // быстрее, и полоса времени обязана идти по реальным секундам.
          speed: 1,
        },
      }).catch(() => {});
    };
    if (now) { send(); return; }
    // Меньше задержка — карточка в Discord успевает за плеером.
    this._presenceTimer = setTimeout(send, 200);
  },

  /* Настоящая длительность трека: сначала декодированное аудио, потом
     метаданные карточки. Живые потоки длительности не имеют. */
  realDuration() {
    const value = this.audio ? this.audio.duration : 0;
    if (value && isFinite(value) && value > 0) return Math.round(value * 1000) / 1000;
    const meta = this.current && this.current.duration;
    return meta && isFinite(meta) ? +meta : 0;
  },

  /* Раз в 30 с подтверждаем состояние: Discord так держит корректный таймер. */
  presenceHeartbeat() {
    if (!this.current) return;
    // Пока длительность неизвестна, полосы времени в Discord нет — повторяем
    // кадр каждые две секунды, чтобы отправить её сразу, как только браузер
    // раскодирует заголовок файла.
    const wait = this.realDuration() ? 30000 : 2000;
    if (Date.now() - (this._presenceAt || 0) < wait) return;
    this.pushPresence(true);
  },

  /* Подписи «ничего не играет»: узлы с названием трека из автоперевода
     исключены (там данные пользователя), поэтому переводим их вручную. */
  paintIdle() {
    if (this.current) return;
    const title = t('Nothing is playing');
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.paintPlayer();
    const artist = t('Pick a track');
    [$('pTitle'), $('nTitle')].forEach(n => { if (n) n.textContent = title; });
    [$('pArtist'), $('nArtist')].forEach(n => {
      if (n) { n.textContent = artist; n.classList.remove('ar-btn'); }
    });
  },

  /* -------------------------------------------------------------- отрисовка */
  paintTrack() {
    const track = this.current;
    if (!track) return;
    // Обои «по обложке» едут за треком.
    if (typeof Wall !== 'undefined') Wall.onTrack();
    [$('pTitle'), $('nTitle')].forEach(node => node.textContent = track.title);
    [$('pArtist'), $('nArtist')].forEach(node => node.textContent = track.artist);
    // Имя исполнителя становится кнопкой только когда есть куда вести.
    [$('pArtist'), $('nArtist')].forEach(node => {
      if (node) node.classList.toggle('ar-btn', !!track.artist);
    });
    setImg($('pArt'), track.thumbnail, 64);
    const kArt = (typeof KCustom !== 'undefined') ? KCustom.cover(track.thumbnail) : track.thumbnail;
    setImg($('nArt'), kArt, 360);
    $('pArt').classList.toggle('ph', !track.thumbnail);
    const badge = $('pSource');
    if (badge) {
      badge.textContent = sourceName(track.source);
      badge.classList.add('on');
    }
    if(window.KMarquee)KMarquee.sync();
    this.paintLike();
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.paintPlayer();
    Karaoke.setArtwork(kArt);
    if (typeof Viz !== 'undefined') Viz.paint();
    if (typeof VMedia !== 'undefined') { VMedia.paintTrack(); VMedia.build(); }
    this.pushPresence();
    if (window.KTray) KTray.push();

    if ('mediaSession' in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title, artist: track.artist, album: sourceName(track.source),
        artwork: track.thumbnail
          ? [{ src: hiRes(track.thumbnail, 512), sizes: '512x512' }] : [],
      });
      const handlers = {
        // Раньше здесь был toggle: система иногда шлёт «play» на играющем треке,
        // и плеер сам вставал на паузу. Теперь действия строго однозначные.
        play: () => this.mediaPlay(),
        pause: () => this.mediaPause(),
        nexttrack: () => this.next(false), previoustrack: () => this.prev(),
        seekto: d => { if (d.seekTime != null) this.audio.currentTime = d.seekTime; },
      };
      for (const [name, fn] of Object.entries(handlers)) {
        try { navigator.mediaSession.setActionHandler(name, fn); } catch {}
      }
    }
  },

  paintLike() {
    const liked = this.current && K.likes.has(this.current.id);
    ['pLike', 'nLike', 'pLikeM'].forEach(id => {
      const node = $(id);
      if (node) {
        node.classList.toggle('on', !!liked);
        node.setAttribute('aria-pressed', String(!!liked));
        node.querySelector('.ic')?.classList.toggle('f', !!liked);
      }
    });
    // Сцены «Диск» и «Визуализатор» рисуют своё сердце — его тоже надо
    // обновить, иначе лайк с клавиши L или из мини-плеера туда не доходил.
    if (typeof Disc !== 'undefined' && Disc.paintButtons) Disc.paintButtons();
    if (typeof Viz !== 'undefined' && Viz.paintButtons) Viz.paintButtons();
  },

  paintLoading() {
    const loading = !!this.current && !!this.busy;
    document.querySelectorAll('#pPlay,#pMobPlay,#nPlay,#albumPlay24,#s33Play,#now [data-a="play"]').forEach(node => {
      if (loading && !node._loadingLabel37) node._loadingLabel37 = {label:node.getAttribute('aria-label'),title:node.getAttribute('title')};
      node.classList.toggle('loading37', loading);
      if(loading&&!node.querySelector(':scope > .loading-glyph38'))node.insertAdjacentHTML('beforeend',loadingIcon38());
      if(!loading)node.querySelector(':scope > .loading-glyph38')?.remove();
      paintAttr40(node, 'aria-busy', String(loading));
      if (loading) { node.setAttribute('aria-label', t('Loading…')); node.title=t('Loading…'); }
      else if (node._loadingLabel37) {
        for (const [key,value] of [['aria-label',node._loadingLabel37.label],['title',node._loadingLabel37.title]]) { if (value == null) node.removeAttribute(key); else node.setAttribute(key,value); }
        delete node._loadingLabel37;
      }
    });
    paintAttr40($('now'), 'aria-busy', String(loading));
  },

  paintState() {
    const playing = !this.audio.paused && !this.audio.ended;
    ['pPlay', 'nPlay', 'pMobPlay'].forEach(id => {
      const node = $(id);
      if (!node) return;
      node.querySelector('use')?.setAttribute('href', playing ? '#i-pause' : '#i-play');
      node.setAttribute('aria-pressed', String(playing));
      const label = t(playing ? 'Pause' : 'Play');
      node.setAttribute('aria-label', label);
      node.title = label;
    });
    ['pShuffle', 'nShuffle', 'pShuffleM', 'sceneShuffle87'].forEach(id => {
      const node = $(id);
      if (node) {
        node.classList.toggle('on', !!S.shuffle);
        node.setAttribute('aria-pressed', String(!!S.shuffle));
      }
    });
    ['pRepeat', 'nRepeat', 'sceneRepeat87'].forEach(id => {
      const node = $(id);
      if (!node) return;
      node.classList.toggle('on', S.repeat !== 'off');
      node.setAttribute('aria-pressed', String(S.repeat !== 'off'));
      node.querySelector('use')?.setAttribute('href',
        S.repeat === 'one' ? '#i-repeat1' : '#i-repeat');
    });
    Views.markPlaying();
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.paintState();
    Karaoke.setPlaying(playing && !this.busy);
    this.paintLoading();
    this.wake42();
  },

  paintProgress(forced) {
    const dur = this.realDuration();
    let ratio = forced != null ? forced
      : (this.seeking || this.holdUntilSeeked) && this.seekRatio != null ? this.seekRatio
      : dur && isFinite(dur) ? this.audio.currentTime / dur : 0;
    ratio = Math.max(0, Math.min(1, ratio));
    const pct = (ratio * 100).toFixed(3) + '%';
    ['pFill', 'pFillM', 'nFill', 'dFill', 'vFill', 's33Fill'].forEach(id => { const n = $(id); paintStyle40(n, 'width', pct); });
    this.progressKnobs40.forEach(knob => {if(!knob.isConnected){this.progressKnobs40.delete(knob);return;}paintStyle40(knob, 'left', pct);});
    if (typeof Workspace !== 'undefined' && Workspace.ready) Workspace.progress(ratio);
  },

  nudge(seconds) {
    if (!this.current) return;
    const dur = this.audio.duration;
    const next = Math.max(0, Math.min((dur || 1e9) - 0.3, this.audio.currentTime + seconds));
    this.audio.currentTime = next;
    if (Number.isFinite(dur) && dur > 0) { this.seekRatio = this.audio.seeking ? next / dur : null; this.holdUntilSeeked = this.audio.seeking; this.paintProgress(); this.paintTime(); }
  },

  paintBuffer() {
    const dur = this.audio.duration;
    if (!dur || !isFinite(dur) || !this.audio.buffered.length) return;
    const pct = (this.audio.buffered.end(this.audio.buffered.length - 1) / dur) * 100 + '%';
    ['pBuf', 'pBufM', 'nBuf', 'dBuf', 'vBuf'].forEach(id => { const n = $(id); paintStyle40(n, 'width', pct); });
  },

  paintTime(forcedRatio) {
    const dur0 = this.audio.duration;
    const shown = forcedRatio != null && dur0 && isFinite(dur0)
      ? forcedRatio * dur0 : this.audio.currentTime;
    const cur = fmt(shown);
    const total = this.realDuration();
    // Правое число можно переключить на «сколько осталось» — щелчком по нему.
    const dur = this.showLeft && total && isFinite(total)
      ? '-' + fmt(Math.max(0, Math.floor(total) - Math.floor(shown))) : fmt(total);
    const timeKey = cur + '|' + dur;
    if (this._lastTimeKey === timeKey) return;
    this._lastTimeKey = timeKey;
    ['pCur', 'pCurM', 'nCur', 'dCur', 'vCur', 's33Cur'].forEach(id => { const n = $(id); paintText40(n, cur); });
    ['pDur', 'pDurM', 'nDur', 'dDur', 'vDur', 's33Dur'].forEach(id => { const n = $(id); paintText40(n, dur); });
  },

  setVolume(value) {
    value=Number(value);if(!Number.isFinite(value))return;value=Math.max(0,Math.min(100,value));
    S.volume = value;
    // Громкость одна на обе дорожки, иначе после перехода ползунок
    // «не доезжает»: активной была бы уже вторая дорожка.
    this.deck.forEach(deck => { if (deck !== this.xfFrom) deck.volume = value / 100; });
    if(typeof Finder!=='undefined'&&Finder.previewId&&Finder.audio)Finder.audio.volume=value/100;
    const muted = value === 0;
    ['pMute'].forEach(id => {
      const node = $(id);
      if (node) {node.querySelector('use').setAttribute('href', muted ? '#i-mute' : '#i-vol');node.title=t(muted?'Unmute':'Mute');node.setAttribute('aria-label',node.title);node.setAttribute('aria-pressed',String(muted));}
    });
    saveSettings();
  },
};
