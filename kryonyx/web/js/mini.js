/* mini.js — мини-плеер поверх всех окон (Настройки → Мини-плеер).

   ПК-версия: отдельное маленькое окно pywebview с on_top (main.DesktopApi.
   mini_open). Браузер: окно Document Picture-in-Picture — оно тоже лежит
   поверх всех приложений. Вид у обоих общий — web/js/mini-view.js. */
'use strict';

window.MiniPlayer = {
  pip: null,          // окно Picture-in-Picture (браузер)
  view: null,
  openState: false,
  _timer: 0,
  _last: '',

  desk() {
    const a = window.pywebview && window.pywebview.api;
    return a && a.mini_open ? a : null;
  },

  supported() {
    return !!(this.desk() || 'documentPictureInPicture' in window);
  },

  labels() {
    return {
      prev: t('Previous'), play: t('Play'), pause: t('Pause'), next: t('Next'),
      volume:t('Volume'), loading:t('Loading…'), drag:t('Drag to move'),
      close: t('Close'), seek: t('Seek'), idle: t('Nothing is playing'), show: t('Show window'),
    };
  },

  state() {
    const track = typeof Player !== 'undefined' ? Player.current : null;
    const a = typeof Player !== 'undefined' ? Player.audio : null;
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()
      || getComputedStyle(document.body).getPropertyValue('--accent').trim();
    return {
      title: track ? (track.title || '') : '',
      artist: track ? (track.artist || '') : '',
      cover: track ? (track.thumbnail || '') : '',
      playing: !!(track && a && !a.paused && !a.ended),
      loading: !!(track && Player.busy),
      position: a ? (a.currentTime || 0) : 0,
      duration: (a && isFinite(a.duration) && a.duration) || (track && track.duration) || 0,
      accent: accent || '#7c5cff',
      palette:window.CoverPalette23?CoverPalette23.forCover(track?.thumbnail):[],
      volume:typeof S!=='undefined'?S.volume:100,
      labels: this.labels(),
      reducedMotion: !!S.noAnim || matchMedia('(prefers-reduced-motion: reduce)').matches,
      at: Date.now(),
    };
  },

  /* Настройка изменилась (или приложение запустилось). */
  apply() {
    if (typeof S === 'undefined') return;
    if (S.miniPlayer) this.open(); else this.close(true);
  },

  async open() {
    if (this.openState) { this.push(true); return; }
    const desk = this.desk();
    if (desk) {
      this.openState = true;
      const run = () => desk.mini_open().then(ok => { if (ok) this.push(true); else this.closed(); }).catch(() => this.closed());
      if (window.Frame && Frame.call) Frame.call(run); else run();
      return;
    }
    if (!('documentPictureInPicture' in window)) {
      toast(t('The mini player is not supported here'));
      this.closed();
      return;
    }
    try {
      // Окно PiP открывается только по действию пользователя (щелчку).
      const pip = await documentPictureInPicture.requestWindow({ width: 420, height: 180 });
      this.pip = pip;
      this.openState = true;
      this.view = MiniView.mount(pip.document, {
        prev: () => Player.prev(),
        toggle: () => Player.toggle(),
        next: () => Player.next(false),
        seek: f => this.seek(f),
        close: () => { pip.close(); },
        show: () => this.returnToPlayer(),
        volume:v=>this.volume(v),
      }, { base: location.origin });
      pip.addEventListener('pagehide', () => {
        if (this.pip === pip) { this.pip = null; this.view = null; this.closed(); }
      });
      this.push(true);
    } catch (err) {
      toast(t('Turn the mini player on with a click in the settings'));
      this.closed();
    }
  },

  returnToPlayer() {
    window.focus();
    this.close(false);
  },

  close(fromSetting) {
    if (!this.openState) return;
    this.openState = false;
    const desk = this.desk();
    if (desk && desk.mini_close) {
      const run = () => desk.mini_close();
      if (window.Frame && Frame.call) Frame.call(run); else run();
    }
    if (this.pip) { const pip = this.pip; this.pip = null; this.view = null; try { pip.close(); } catch {} }
    if (!fromSetting) this.closed();
  },

  /* Окошко закрыли его собственным крестиком — гасим переключатель. */
  closed() {
    this.openState = false;
    if (typeof S === 'undefined' || !S.miniPlayer) return;
    S.miniPlayer = false;
    saveSettings();
    document.querySelectorAll('[data-sw="miniPlayer"]').forEach(n => n.classList.remove('on'));
  },

  seek(fraction) {
    const a = typeof Player !== 'undefined' ? Player.audio : null;
    if (!a || !isFinite(a.duration) || !a.duration) return;
    a.currentTime = Math.max(0, Math.min(1, +fraction || 0)) * a.duration;
    this.push(true);
  },

  action(name){if(name==='lyrics'){window.focus();App.openNow();}else if(name==='queue'){window.focus();$('pQueue')?.click();}},
  volume(raw){const n=Number(raw);if(!Number.isFinite(n))return;const value=Math.min(100,Math.max(0,n));Player.setVolume(value);['vol','sVolume'].forEach(id=>{if($(id))$(id).value=value;});this.push(true);},

  /* Что играет — в окошко. Пачку событий сводим в один вызов. */
  push(force) {
    if (!this.openState) return;
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this.send(force), force ? 0 : 200);
  },

  send(force) {
    if (!this.openState) return;
    const st = this.state();
    const key = JSON.stringify([st.title, st.artist, st.cover, st.playing, st.loading, st.accent,
                                Math.round(st.duration), st.labels, st.reducedMotion,st.palette,st.volume]);
    if (key === this._last && !force) return;
    this._last = key;
    if (this.view) { this.view.update(st); return; }
    const desk = this.desk();
    if (desk && desk.mini_update) {
      const run = () => desk.mini_update(st);
      if (window.Frame && Frame.call) Frame.call(run); else run();
    }
  },

  /* Раз в несколько секунд — сверка позиции (между сверками окошко само
     двигает полосу времени). */
  tick() {
    if (!this.openState || Date.now() - (this._tickAt || 0) < 5000) return;
    this._tickAt = Date.now();
    this.send(true);
  },

  init() {
    // Плеер дергает KTray на каждое событие — вешаемся рядом.
    if (window.KTray && !KTray._miniHooked) {
      KTray._miniHooked = true;
      const push = KTray.push.bind(KTray);
      const tick = KTray.tick.bind(KTray);
      KTray.push = () => { push(); this.push(); };
      KTray.tick = () => { tick(); this.tick(); };
    }
    // ПК-окно открываем сразу при запуске, если настройка включена (мостик
    // pywebview может подняться позже — тогда откроет обработчик ниже).
    // В браузере окно PiP открывается только щелчком по переключателю.
    if (S.miniPlayer && this.desk()) this.open();
  },
};

window.addEventListener('pywebviewready', () => {
  if (typeof S !== 'undefined' && S.miniPlayer && MiniPlayer.desk()) MiniPlayer.open();
});
