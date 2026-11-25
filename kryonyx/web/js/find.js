/* find.js — «добавить треки» в плейлист, как в Spotify.

   Экран один: поисковая строка и список находок. У каждой строки две
   кнопки:
     ▶ — короткая проба. Играет не начало, а самый интересный кусок:
         середину трека. Пробу слышно поверх плеера, основной трек на это
         время ставится на паузу и возвращается сам.
     + — трек уходит в плейлист; строка сразу помечается галочкой, так что
         видно, что уже добавлено.

   Проба — отдельный <audio>: очередь, позиция и состояние основного плеера
   её не замечают. */
'use strict';

const Finder = {
  target: null,        // { id, name }
  tracks: [],
  added: new Set(),
  token: 0,
  audio: null,
  previewId: null,
  resumeAfter: false,
  stopTimer: null,

  PREVIEW_SECONDS: 30,     // сколько длится проба
  PREVIEW_AT: 0.38,        // с какого места трека начинать (доля длительности)

  /* -------------------------------------------------------------- показ */
  open(playlist) {
    if (!playlist || playlist.id == null) { toast(t('Open a playlist first')); return; }
    this.target = { id: playlist.id, name: playlist.name || '' };
    this.added = new Set(playlist.ids || []);
    this.tracks = [];
    const sub = $('findSub');
    if (sub) sub.textContent = this.target.name;
    const list = $('findList');
    if (list) {
      list.innerHTML = `<div class="empty">${icon('search')}<div>` +
        `${t('Find a track and press + to add it')}</div></div>`;
    }
    const input = $('findQ');
    if (input) { input.value = ''; }
    openModal('mFind');
    setTimeout(() => input && input.focus(), 160);
  },

  close() {
    this.stopPreview();
    this.token++;
  },

  /* ------------------------------------------------------------- поиск */
  async search(query) {
    query = (query || '').trim();
    const list = $('findList');
    if (!list) return;
    this.stopPreview();
    if (!query) {
      this.tracks = [];
      list.innerHTML = `<div class="empty">${icon('search')}<div>` +
        `${t('Find a track and press + to add it')}</div></div>`;
      return;
    }
    const token = ++this.token;
    Views.skeletons(list, 6, 'row');
    let tracks = [];
    try {
      const chunks = await Promise.all(activeSources().map(source =>
        App.fetchSearch(query, 0, source).catch(() => ({ tracks: [] }))));
      const seen = new Set();
      chunks.forEach(chunk => (chunk.tracks || []).forEach(track => {
        if (!track || !track.id || seen.has(track.id)) return;
        seen.add(track.id);
        tracks.push(track);
      }));
    } catch (err) {
      if (token !== this.token) return;
      list.innerHTML = `<div class="empty">${icon('search')}<div>${esc(err.message)}</div></div>`;
      return;
    }
    if (token !== this.token) return;
    this.tracks = tracks;
    this.render();
  },

  render() {
    const list = $('findList');
    if (!list) return;
    list.innerHTML = '';
    if (!this.tracks.length) {
      list.innerHTML = `<div class="empty">${icon('search')}<div>${t('Nothing found')}</div></div>`;
      return;
    }
    this.tracks.forEach(track => list.appendChild(this.row(track)));
  },

  row(track) {
    const done = this.added.has(track.id);
    const row = el('div', 'tr find-row' + (done ? ' is-added' : ''));
    row.dataset.id = track.id;
    row.innerHTML = `
      <button class="ib find-prev" data-act="preview"
              title="${esc(t('Hear the best part'))}">${icon('play', 'ic s f')}</button>
      <img alt="">
      <span class="meta">
        <span class="t clip">${esc(track.title)}</span>
        <span class="a clip">${esc(track.artist || '')} · ${sourceName(track.source)}</span>
      </span>
      <span class="d">${fmt(track.duration)}</span>
      <button class="ib find-add" data-act="add"
              title="${esc(t('Add to the playlist'))}">${icon(done ? 'check' : 'plus', 'ic s')}</button>`;
    setImg(row.querySelector('img'), track.thumbnail, 56);
    row.querySelector('[data-act=preview]').onclick = () => this.togglePreview(track, row);
    row.querySelector('[data-act=add]').onclick = () => this.add(track, row);
    return row;
  },

  /* ----------------------------------------------------------- проба */
  ensureAudio() {
    if (this.audio) return this.audio;
    const a = new Audio();
    a.preload = 'none';
    a.volume = Math.min(1, (S.volume ?? 100) / 100);
    a.addEventListener('ended', () => this.stopPreview());
    a.addEventListener('error', () => {
      if (!this.previewId) return;
      toast(t('Could not play the preview'));
      this.stopPreview();
    });
    this.audio = a;
    return a;
  },

  togglePreview(track, row) {
    if (this.previewId === track.id) { this.stopPreview(); return; }
    const resumeAfter = this.resumeAfter, resumeContext = this.resumeContext;
    this.stopPreview(false);
    const a = this.ensureAudio();
    this.previewId = track.id;
    row.classList.add('is-playing');
    this.paintPreview();

    // Основной плеер уступает место пробе и сам возвращается, когда она
    // закончится: двух песен разом слышно быть не должно.
    this.resumeAfter = resumeAfter || !!(Player.audio && !Player.audio.paused);
    this.resumeContext = resumeAfter ? resumeContext : {audio:Player.audio,track:Player.current,token:Player.loadToken};
    if (this.resumeAfter) { Player.wantPlay = false; Player.audio.pause(); }

    a.volume = Math.min(1, (S.volume ?? 100) / 100);
    a.src = '/api/stream?id=' + encodeURIComponent(track.id);
    const jump = () => {
      a.removeEventListener('loadedmetadata', jump);
      if(this.previewId!==track.id)return;
      const total = (isFinite(a.duration) && a.duration > 0) ? a.duration : (+track.duration || 0);
      if (!total) return;
      // Середина — почти всегда припев; с самого конца начинать нельзя.
      const at = Math.max(0, Math.min(total - 12, total * this.PREVIEW_AT));
      try { a.currentTime = at; } catch {}
    };
    this.previewJump=jump;a.addEventListener('loadedmetadata', jump);
    const request=this.previewRequest=(this.previewRequest||0)+1;
    a.play().catch(() => {if(this.previewRequest===request&&this.previewId===track.id){toast(t('Could not play the preview'));this.stopPreview();}});
    clearTimeout(this.stopTimer);
    this.stopTimer = setTimeout(() => this.stopPreview(), this.PREVIEW_SECONDS * 1000);
  },

  stopPreview(resume = true) {
    this.previewRequest=(this.previewRequest||0)+1;
    if(this.previewJump&&this.audio)this.audio.removeEventListener('loadedmetadata',this.previewJump);
    this.previewJump=null;
    clearTimeout(this.stopTimer);
    this.stopTimer = null;
    if (!this.previewId) return;
    this.previewId = null;
    if (this.audio) {
      try { this.audio.pause(); } catch {}
      this.audio.removeAttribute('src');
      try { this.audio.load(); } catch {}
    }
    const context=this.resumeContext, shouldResume=resume&&this.resumeAfter&&context&&Player.audio===context.audio&&Player.current===context.track&&Player.loadToken===context.token;
    this.resumeAfter=false;this.resumeContext=null;
    if (shouldResume) {
      Player.wantPlay = true;
      Player.audio.play().catch(() => {});
    }
    this.paintPreview();
  },

  paintPreview() {
    document.querySelectorAll('#findList .find-row').forEach(row => {
      const on = row.dataset.id === this.previewId;
      row.classList.toggle('is-playing', on);
      const use = row.querySelector('.find-prev use');
      if (use) use.setAttribute('href', on ? '#i-pause' : '#i-play');
    });
  },

  /* ---------------------------------------------------------- добавить */
  async add(track, row) {
    if (!this.target) return;
    if (this.added.has(track.id)) { toast(t('Already in the playlist')); return; }
    const button = row.querySelector('.find-add');
    button.disabled = true;
    try {
      await api(`/api/playlists/${this.target.id}/tracks`, { method: 'POST', body: { track } });
      this.added.add(track.id);
      row.classList.add('is-added');
      const use = button.querySelector('use');
      if (use) use.setAttribute('href', '#i-check');
      toast(t('Added to') + ' «' + this.target.name + '»');
      refreshPlaylists();
      // Открытый плейлист обновляем на месте — без перезагрузки экрана.
      if (K.view === 'list' && Views.listState
          && Views.listState.type === 'playlist'
          && String(Views.listState.id) === String(this.target.id)) {
        App.refreshOpenPlaylist();
      }
    } catch (err) {
      toast(err.message || t('Error'));
    } finally {
      button.disabled = false;
    }
  },

  bind() {
    const input = $('findQ');
    if (input) {
      input.addEventListener('input', debounce(() => this.search(input.value), 320));
      input.addEventListener('keydown', event => {
        if (event.key === 'Enter') { event.preventDefault(); this.search(input.value); }
      });
    }
    const go = $('findGo');
    if (go) go.onclick = () => this.search(($('findQ') || {}).value || '');
  },
};
