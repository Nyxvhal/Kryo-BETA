/* tray.js — значок в трее Windows (ПК-версия).

   Плеер сообщает сюда, что играет; окно передаёт это в main.py, а тот —
   значку в области уведомлений (подсказка, меню, уведомление при смене
   трека в свёрнутом окне). Команды из меню значка приходят в act(). */
window.KTray = {
  _timer: 0,
  _last: '',

  api() {
    const a = window.pywebview && window.pywebview.api;
    return a && a.now_playing ? a : null;
  },

  push() {
    clearTimeout(this._timer);
    // Пауза/играть и смена трека прилетают пачкой — шлём только итог.
    this._timer = setTimeout(() => this.send(), 250);
  },

  send(force) {
    const a = this.api();
    if (!a || typeof Player === 'undefined') return;
    const track = Player.current;
    const info = {
      title: track ? (track.title || '') : '',
      artist: track ? (track.artist || '') : '',
      playing: !!(track && Player.audio && !Player.audio.paused),
      labels: {
        prev: t('Previous'), play: t('Play'), pause: t('Pause'), next: t('Next'),
        show: t('Show window'), quit: t('Quit'), idle: t('Nothing is playing'),
      },
    };
    const key = JSON.stringify(info);
    const a2 = Player.audio;
    // Ход трека — для полоски прогресса на кнопке в панели задач.
    info.position = a2 ? (a2.currentTime || 0) : 0;
    info.duration = (a2 && isFinite(a2.duration) && a2.duration) || (track && track.duration) || 0;
    if (key === this._last && !force) return;
    this._last = key;
    this._sent = Date.now();
    const run = () => a.now_playing(info);
    // Вызовы в окно идут по одному через очередь рамки (см. frame.js).
    if (window.Frame && Frame.call) Frame.call(run); else run();
  },

  /* Раз в несколько секунд, пока играет: двигает полоску прогресса. */
  tick() {
    if (!this.api() || Date.now() - (this._sent || 0) < 4000) return;
    this._sent = Date.now();
    this.send(true);
  },

  act(name) {
    if (typeof Player === 'undefined') return false;
    if (name === 'next') Player.next(false);
    else if (name === 'prev') Player.prev();
    else if (name === 'toggle') Player.toggle();
    return true;
  },
};
window.addEventListener('pywebviewready', () => KTray.push());
