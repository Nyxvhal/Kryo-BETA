/* frame.js — своя рамка окна на ПК.

   Системный заголовок выключен (frameless), поэтому название, кнопки
   свернуть/развернуть/закрыть и растягивание за края живут здесь. В браузере
   и в Android-сборке файл ничего не делает: там окном распоряжается система. */
window.Frame = {
  on: false,
  api: null,
  maximized: false,

  init() {
    const api = window.pywebview && window.pywebview.api;
    if (!api || !api.close || this.on) return;
    this.api = api;
    this.on = true;
    document.body.classList.add('framed');

    const min = document.getElementById('winMin');
    const max = document.getElementById('winMax');
    const close = document.getElementById('winClose');
    const drag = document.getElementById('titlebarDrag');

    if (min) min.onclick = () => api.minimize();
    if (max) max.onclick = () => this.toggleMax();
    if (close) close.onclick = () => api.close();
    // Двойной щелчок по полосе — как по системному заголовку.
    if (drag) drag.addEventListener('dblclick', () => this.toggleMax());

    this.bindResizers();
    this.bindSnap();

    if (api.info) {
      api.info().then((info) => {
        this.minW = (info && info.min_width) || 400;
        this.minH = (info && info.min_height) || 560;
        if (info && info.maximized) this.applyMax(true);
        // Что окно уже знает про себя. Без этого `_top` и `_remember`
        // оставались undefined, не совпадали ни с true, ни с false, и на
        // каждом запуске уходил лишний set_on_top — а он в pywebview
        // правит форму мимо потока интерфейса (см. main.DesktopApi).
        this._top = !!(info && info.on_top);
        this._remember = !!(info && info.remember);
        this.ready = true;
        this.applySettings();
      }).catch(() => {});
    }
  },

  /* Настройки окна из общей базы: широкие края, уголок, «поверх всех окон»,
     запоминать размер. Вызывается и при открытии, и при каждом изменении
     переключателя в настройках. */
  applySettings() {
    if (typeof S === 'undefined' || !S) return;     // core.js ещё не загрузился
    document.body.classList.toggle('rz-wide', !!S.winGrab);
    document.body.classList.toggle('no-grip', S.winGrip === false);
    if (!this.on || !this.ready) return;
    if (this.api.set_on_top && this._top !== !!S.winOnTop) {
      this._top = !!S.winOnTop;
      this.call(() => this.api.set_on_top(this._top));
    }
    if (this.api.set_remember && this._remember !== !!S.winRemember) {
      this._remember = !!S.winRemember;
      this.call(() => this.api.set_remember(this._remember));
    }
  },

  /* Очередь вызовов в окно.

     Мостик pywebview возвращает каждый ответ через evaluate_js, а у окна
     на все такие ответы один семафор: два запроса, ушедшие одновременно,
     умеют дождаться чужого ответа и зависнуть вместе с потоком интерфейса.
     Поэтому запросы к окну идут строго по одному, а первый ждёт, пока
     страница закончит собираться. */
  _chain: null,

  call(fn) {
    const start = this._chain || new Promise(resolve => setTimeout(resolve, 1200));
    this._chain = start.then(fn).catch(() => {});
    return this._chain;
  },

  /* ------------------------------------------------ привязка к краям экрана
     Своя рамка лишает окно системной привязки (перетащил к краю — половина
     экрана), поэтому делаем её сами: правый щелчок по полосе заголовка даёт
     меню, Ctrl+Alt+стрелки — то же с клавиатуры. */
  SNAP: {
    left:   [0,  0,  .5, 1],
    right:  [.5, 0,  .5, 1],
    top:    [0,  0,  1,  .5],
    bottom: [0,  .5, 1,  .5],
    tl:     [0,  0,  .5, .5],
    tr:     [.5, 0,  .5, .5],
    bl:     [0,  .5, .5, .5],
    br:     [.5, .5, .5, .5],
    full:   [0,  0,  1,  1],
    center: null,
  },

  snap(where) {
    if (!this.on || !this.api.screen || !this.api.set_bounds) return;
    this.api.screen().then((scr) => {
      if (!scr || !scr.width || !scr.real) return;
      if (this.maximized && this.api.toggle_maximize) {
        this.api.toggle_maximize().then((state) => this.applyMax(!!state)).catch(() => {});
      }
      const box = this.SNAP[where];
      const minW = this.minW || 400;
      const minH = this.minH || 560;
      if (!box) {                                   // по центру, 70 % экрана
        const w = Math.max(minW, Math.round(scr.width * .7));
        const h = Math.max(minH, Math.round(scr.height * .8));
        this.api.set_bounds(scr.x + Math.round((scr.width - w) / 2),
                            scr.y + Math.round((scr.height - h) / 2), w, h)
            .catch(() => {});
        return;
      }
      const w = Math.max(minW, Math.round(scr.width * box[2]));
      const h = Math.max(minH, Math.round(scr.height * box[3]));
      this.api.set_bounds(scr.x + Math.round(scr.width * box[0]),
                          scr.y + Math.round(scr.height * box[1]), w, h)
          .catch(() => {});
    }).catch(() => {});
  },

  bindSnap() {
    const bar = document.getElementById('titlebarDrag');
    if (bar) {
      bar.addEventListener('contextmenu', (event) => {
        event.preventDefault();
        this.snapMenu(event.clientX, event.clientY);
      });
    }
    window.addEventListener('keydown', (event) => {
      if (!event.ctrlKey || !event.altKey || event.shiftKey) return;
      const map = { ArrowLeft: 'left', ArrowRight: 'right',
                    ArrowUp: 'full', ArrowDown: 'center' };
      const where = map[event.key];
      if (!where) return;
      event.preventDefault();
      if (where === 'full') { this.toggleMax(); return; }
      this.snap(where);
    });
  },

  snapMenu(x, y) {
    const T = typeof t === 'function' ? t : ((text) => text);
    const items = [
      ['left', T('Left half')], ['right', T('Right half')],
      ['top', T('Top half')], ['bottom', T('Bottom half')],
      ['-', ''],
      ['tl', T('Top left quarter')], ['tr', T('Top right quarter')],
      ['bl', T('Bottom left quarter')], ['br', T('Bottom right quarter')],
      ['-', ''],
      ['center', T('Center the window')], ['full', T('Maximize')],
    ];
    const rows = items.map(([key, label]) => (key === '-'
      ? '-'
      : { label, action: () => (key === 'full' ? this.toggleMax() : this.snap(key)) }));
    if (typeof showMenu === 'function') showMenu(x, y, rows);
  },

  toggleMax() {
    if (!this.api.toggle_maximize) return;
    this.api.toggle_maximize()
      .then((state) => this.applyMax(!!state))
      .catch(() => {});
  },

  applyMax(state) {
    this.maximized = state;
    document.body.classList.toggle('max', state);
    const icon = document.querySelector('#winMax use');
    if (icon) icon.setAttribute('href', state ? '#i-win-restore' : '#i-win-max');
    const btn = document.getElementById('winMax');
    const T = typeof t === 'function' ? t : (text) => text;
    if (btn) btn.title = state ? T('Restore') : T('Maximize');
  },

  /* Полный экран: полоса заголовка там лишняя. */
  setFullscreen(state) {
    document.body.classList.toggle('fs', !!state);
  },

  /* Растягивание за края.

     Границы окна считаем в экранных координатах (screenX/screenY): клиентские
     во время растягивания уже неверны, ведь окно едет под курсором. Новые
     границы отправляем не чаще одного кадра — иначе окно дёргается. */
  bindResizers() {
    const handles = document.querySelectorAll('#resizers .rz');
    handles.forEach((handle) => {
      handle.addEventListener('mousedown', (event) => {
        if (event.button !== 0 || this.maximized) return;
        event.preventDefault();
        this.startResize(handle.dataset.edge, event);
      });
    });
  },

  startResize(edge, event) {
    if (!this.api.bounds || !this.api.set_bounds) return;
    const minW = this.minW || 400;
    const minH = this.minH || 560;

    this.api.bounds().then((box) => {
      if (!box || !box.width) return;
      const startX = event.screenX;
      const startY = event.screenY;
      const from = { x: box.x, y: box.y, w: box.width, h: box.height };
      const right = from.x + from.w;
      const bottom = from.y + from.h;

      let frame = 0;
      let target = null;
      document.body.classList.add('resizing');
      document.body.style.cursor = getComputedStyle(event.target).cursor;

      const compute = (ev) => {
        const dx = ev.screenX - startX;
        const dy = ev.screenY - startY;
        let { x, y, w, h } = from;

        if (edge.indexOf('left') !== -1) {
          w = Math.max(minW, from.w - dx);
          x = right - w;                      // правый край стоит на месте
        }
        if (edge.indexOf('right') !== -1) {
          w = Math.max(minW, from.w + dx);
        }
        if (edge.indexOf('top') !== -1) {
          h = Math.max(minH, from.h - dy);
          y = bottom - h;                     // нижний край стоит на месте
        }
        if (edge.indexOf('bottom') !== -1) {
          h = Math.max(minH, from.h + dy);
        }
        return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
      };

      const onMove = (ev) => {
        target = compute(ev);
        if (frame) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          const box2 = target;
          if (box2) this.api.set_bounds(box2.x, box2.y, box2.w, box2.h).catch(() => {});
        });
      };

      const onUp = () => {
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
        if (frame) cancelAnimationFrame(frame);
        frame = 0;
        if (target) this.api.set_bounds(target.x, target.y, target.w, target.h).catch(() => {});
        document.body.classList.remove('resizing');
        document.body.style.cursor = '';
      };

      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    }).catch(() => {});
  },
};

// pywebview появляется в окне не сразу: мостик готов к этому событию.
window.addEventListener('pywebviewready', () => window.Frame.init());
document.addEventListener('DOMContentLoaded', () => window.Frame.init());
