/* eq.js — эквалайзер и микшер.

   Шесть полос, как в Spotify: 60 Hz, 150 Hz, 400 Hz, 1 kHz, 2.4 kHz, 15 kHz,
   каждая от −12 до +12 дБ. Крайние полосы — полочные фильтры (lowshelf и
   highshelf), остальные — колокольные (peaking): так низ и верх поднимаются
   целиком, а середина правится точечно.

   Фильтры стоят в общей цепочке Web Audio прямо за источником:

       <audio> → [компрессор] → EQ (6 фильтров) → баланс → громкость → анализатор → выход

   Настройки живут в S.eqOn / S.eqGains / S.eqPreset и уходят в базу на
   устройстве вместе с остальными: выбранная кривая держится до тех пор,
   пока её не поменяют снова — перезапуск, обновление и чистка кэша
   WebView на неё не влияют.

   Виджет можно поставить в любое место (настройки, микшер): Equalizer.mount()
   создаёт отдельный вид, все виды перерисовываются вместе. */
'use strict';

const EQ_BANDS = [
  { f: 60,    type: 'lowshelf',  label: '60Hz' },
  { f: 150,   type: 'peaking',   label: '150Hz' },
  { f: 400,   type: 'peaking',   label: '400Hz' },
  { f: 1000,  type: 'peaking',   label: '1KHz' },
  { f: 2400,  type: 'peaking',   label: '2.4KHz' },
  { f: 15000, type: 'highshelf', label: '15KHz' },
];

const EQ_LIMIT = 12;        // ±12 дБ, как в Spotify

/* Пресеты. Порядок полос тот же: 60 / 150 / 400 / 1k / 2.4k / 15k. */
const EQ_PRESETS = [
  ['manual',    'Manual',          null],
  ['flat',      'Flat',            [0, 0, 0, 0, 0, 0]],
  ['acoustic',  'Acoustic',        [4, 3, 1, 2, 3, 3]],
  ['bass',      'Bass booster',    [7, 5.5, 2.5, 0, 0, 0]],
  ['bassless',  'Bass reducer',    [-7, -5.5, -2.5, 0, 0, 0]],
  ['classical', 'Classical',       [4.5, 3.5, -1.5, -1.5, 2.5, 3.5]],
  ['dance',     'Dance',           [6, 4.5, 0, 2, 3.5, 1]],
  ['deep',      'Deep',            [6, 4, 1.5, -1.5, -4, -6]],
  ['electronic','Electronic',      [5, 3.5, -1.5, 1.5, 2.5, 4.5]],
  ['hiphop',    'Hip-Hop',         [6.5, 4.5, -1, 1.5, 2, 2.5]],
  ['jazz',      'Jazz',            [4, 3, -1.5, 1.5, 3, 3.5]],
  ['latin',     'Latin',           [5, 2.5, -3, -3, 2.5, 5]],
  ['loudness',  'Loudness',        [7, 4.5, -1.5, -2.5, 3, 1]],
  ['lounge',    'Lounge',          [-2.5, 1.5, 3.5, 2, -1.5, 1.5]],
  ['piano',     'Piano',           [2.5, 1.5, 2.5, 3.5, 2.5, 3]],
  ['pop',       'Pop',             [-1.5, 1.5, 4.5, 3.5, 0, -1.5]],
  ['rnb',       'R&B',             [6.5, 5, -2, 1.5, 3.5, 4]],
  ['rock',      'Rock',            [5.5, 3.5, -1, 1, 3.5, 4.5]],
  ['small',     'Small speakers',  [6.5, 4.5, 1.5, 0, -2, -3.5]],
  ['spoken',    'Spoken word',     [-4, -1, 2, 4.5, 4, 1]],
  ['treble',    'Treble booster',  [0, 0, 0, 2.5, 5, 7]],
  ['trebleless','Treble reducer',  [0, 0, 0, -2.5, -5, -7]],
  ['vocal',     'Vocal booster',   [-2.5, -2.5, 2.5, 5, 4, -1.5]],
];

const Equalizer = {
  filters: [],
  ctx: null,
  views: [],
  uid: 0,

  /* ------------------------------------------------------------- данные */
  gains() {
    const saved = Array.isArray(S.eqGains) ? S.eqGains : [];
    return EQ_BANDS.map((_, i) => this.clamp(+saved[i] || 0));
  },

  clamp(value) {
    if (!isFinite(value)) return 0;
    return Math.max(-EQ_LIMIT, Math.min(EQ_LIMIT, Math.round(value * 10) / 10));
  },

  setGain(index, value, save = true) {
    const list = this.gains();
    list[index] = this.clamp(value);
    S.eqGains = list;
    S.eqPreset = this.matchPreset(list);
    this.apply();
    this.paintAll();
    if (save) saveSettings();
  },

  setAll(list, preset) {
    S.eqGains = EQ_BANDS.map((_, i) => this.clamp(+list[i] || 0));
    S.eqPreset = preset || this.matchPreset(S.eqGains);
    this.apply();
    this.paintAll();
    saveSettings();
  },

  /* Если кривая совпала с пресетом — показываем его имя, иначе «вручную». */
  matchPreset(list) {
    for (const [id, , values] of EQ_PRESETS) {
      if (!values) continue;
      if (values.every((v, i) => Math.abs(v - list[i]) < 0.05)) return id;
    }
    return 'manual';
  },

  toggle(on) {
    S.eqOn = on === undefined ? !S.eqOn : !!on;
    // Цепочку надо пересобрать: выключенный EQ полностью уходит из графа,
    // чтобы не тратить процессор впустую.
    if (Player.ctx) { Player.ensureCtx(); Player.rebuild(); }
    this.paintAll();
    saveSettings();
    toast(S.eqOn ? t('Equalizer on') : t('Equalizer off'));
  },

  /* ------------------------------------------------------- Web Audio */
  /* Встраиваем фильтры за узлом input и возвращаем конец цепочки. */
  attach(ctx, input) {
    if (!S.eqOn) return input;
    if (this.ctx !== ctx) { this.ctx = ctx; this.filters = []; }
    if (!this.filters.length) {
      this.filters = EQ_BANDS.map(band => {
        const node = ctx.createBiquadFilter();
        node.type = band.type;
        node.frequency.value = band.f;
        if (band.type === 'peaking') node.Q.value = 1.1;
        node.gain.value = 0;
        return node;
      });
    }
    this.apply();
    let tail = input;
    this.filters.forEach(node => { tail.connect(node); tail = node; });
    return tail;
  },

  detach() {
    this.filters.forEach(node => { try { node.disconnect(); } catch {} });
  },

  /* Значения уезжают плавно: резкий скачок усиления слышно как щелчок. */
  apply() {
    if (!this.filters.length || !this.ctx) return;
    const list = this.gains();
    const at = this.ctx.currentTime;
    this.filters.forEach((node, i) => {
      const value = S.eqOn ? list[i] : 0;
      try { node.gain.setTargetAtTime(value, at, 0.02); }
      catch { node.gain.value = value; }
    });
  },

  /* ------------------------------------------------------------ виджет */
  mount(host) {
    if (!host) return null;
    host.innerHTML = '';
    const id = 'eqg' + (++this.uid);
    const root = el('div', 'eqbox');
    root.innerHTML = `
      <div class="eq-head">
        <span class="eq-title">${t('Equalizer')}</span>
        <div class="sw eq-sw" role="switch" tabindex="0"></div>
      </div>
      <div class="eq-body">
        <div class="eq-top">
          <span class="muted eq-lbl">${t('Effects')}</span>
          <select class="eq-preset"></select>
          <button class="btn g sm eq-reset">${t('Reset')}</button>
        </div>
        <div class="eq-plot">
          <span class="eq-db eq-db-top">+${EQ_LIMIT}dB</span>
          <span class="eq-db eq-db-bot">−${EQ_LIMIT}dB</span>
          <svg class="eq-svg" viewBox="0 0 620 280" preserveAspectRatio="none">
            <defs>
              <linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="var(--accent)" stop-opacity=".55"/>
                <stop offset="1" stop-color="var(--accent)" stop-opacity=".02"/>
              </linearGradient>
            </defs>
            <g class="eq-grid"></g>
            <path class="eq-area" fill="url(#${id})"></path>
            <path class="eq-line"></path>
            <g class="eq-knobs"></g>
          </svg>
        </div>
        <div class="eq-axis">${EQ_BANDS.map(b => `<span>${b.label}</span>`).join('')}</div>
      </div>`;
    host.appendChild(root);

    const view = {
      root,
      sw: root.querySelector('.eq-sw'),
      select: root.querySelector('.eq-preset'),
      svg: root.querySelector('.eq-svg'),
      area: root.querySelector('.eq-area'),
      line: root.querySelector('.eq-line'),
      knobs: root.querySelector('.eq-knobs'),
      grid: root.querySelector('.eq-grid'),
    };

    EQ_PRESETS.forEach(([pid, name]) => {
      const option = document.createElement('option');
      option.value = pid;
      option.textContent = t(name);
      view.select.appendChild(option);
    });
    view.select.onchange = () => {
      const found = EQ_PRESETS.find(p => p[0] === view.select.value);
      if (!found || !found[2]) { this.paintAll(); return; }
      if (!S.eqOn) this.toggle(true);
      this.setAll(found[2], found[0]);
      toast(t(found[1]));
    };
    view.sw.onclick = () => this.toggle();
    view.sw.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.toggle(); }
    };
    root.querySelector('.eq-reset').onclick = () => {
      this.setAll([0, 0, 0, 0, 0, 0], 'flat');
      toast(t('Equalizer reset'));
    };

    // Сетка: нулевая линия и края диапазона.
    [this.y(EQ_LIMIT), this.y(0), this.y(-EQ_LIMIT)].forEach((y, i) => {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', 0); line.setAttribute('x2', 620);
      line.setAttribute('y1', y); line.setAttribute('y2', y);
      line.setAttribute('class', i === 1 ? 'eq-zero' : 'eq-edge');
      view.grid.appendChild(line);
    });
    EQ_BANDS.forEach((_, i) => {
      const x = this.x(i);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x); line.setAttribute('x2', x);
      line.setAttribute('y1', this.y(EQ_LIMIT)); line.setAttribute('y2', this.y(-EQ_LIMIT));
      line.setAttribute('class', 'eq-tick');
      view.grid.appendChild(line);
    });

    // Ручки полос.
    EQ_BANDS.forEach((band, i) => {
      const knob = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      knob.setAttribute('r', 9);
      knob.setAttribute('cx', this.x(i));
      knob.setAttribute('class', 'eq-knob');
      knob.dataset.band = i;
      knob.setAttribute('tabindex', '0');
      knob.setAttribute('role', 'slider');
      knob.setAttribute('aria-label', band.label);
      view.knobs.appendChild(knob);
    });

    this.bindDrag(view);
    this.views.push(view);
    this.paint(view);
    return view;
  },

  /* Вид удалили из DOM — убираем его из списка, иначе перерисовка упадёт. */
  sweep() {
    this.views = this.views.filter(view => view.root.isConnected);
  },

  /* ---------------------------------------------------- координаты */
  x(i) { return 50 + i * (520 / (EQ_BANDS.length - 1)); },
  y(db) { return 140 - (db / EQ_LIMIT) * 110; },
  db(y) { return this.clamp(((140 - y) / 110) * EQ_LIMIT); },

  /* Перетаскивание ручек и щелчок по полю. */
  bindDrag(view) {
    let band = -1;
    const dbAt = event => {
      const rect = view.svg.getBoundingClientRect();
      if (!rect.height) return 0;
      return this.db((event.clientY - rect.top) / rect.height * 280);
    };
    const bandAt = event => {
      const rect = view.svg.getBoundingClientRect();
      if (!rect.width) return 0;
      const vx = (event.clientX - rect.left) / rect.width * 620;
      let best = 0, dist = Infinity;
      EQ_BANDS.forEach((_, i) => {
        const d = Math.abs(this.x(i) - vx);
        if (d < dist) { dist = d; best = i; }
      });
      return best;
    };
    const move = event => {
      if (band < 0) return;
      event.preventDefault();
      // Пока тянут — настройки в базу не пишем, только звук и картинка.
      this.setGain(band, dbAt(event), false);
    };
    const up = event => {
      if (band < 0) return;
      band = -1;
      if (event && event.pointerId != null) {
        try { view.svg.releasePointerCapture(event.pointerId); } catch {}
      }
      removeEventListener('pointermove', move);
      removeEventListener('pointerup', up);
      removeEventListener('pointercancel', up);
      saveSettings(true);
    };
    // Браузер при нажатии сам наводит фокус на кружок (у него tabindex) и
    // прокручивает к нему прокручиваемого родителя — внутри панели настроек
    // график уезжал прямо из-под курсора, и полоса не поднималась.
    // Отменяем стандартный фокус и ставим его сами, без прокрутки.
    view.svg.addEventListener('mousedown', event => event.preventDefault());
    view.svg.addEventListener('pointerdown', event => {
      if (event.button != null && event.button !== 0) return;
      if (!S.eqOn) this.toggle(true);
      const knob = event.target.closest('.eq-knob');
      band = knob ? +knob.dataset.band : bandAt(event);
      event.preventDefault();
      const target = knob || view.knobs.children[band];
      if (target) { try { target.focus({ preventScroll: true }); } catch {} }
      // Захват указателя: курсор можно увести за край графика и даже за окно —
      // полоса продолжит тянуться.
      if (event.pointerId != null) {
        try { view.svg.setPointerCapture(event.pointerId); } catch {}
      }
      move(event);
      addEventListener('pointermove', move);
      addEventListener('pointerup', up);
      addEventListener('pointercancel', up);
    });
    // Клавиатура: стрелки двигают выбранную полосу на 0.5 дБ.
    view.knobs.addEventListener('keydown', event => {
      const knob = event.target.closest('.eq-knob');
      if (!knob) return;
      const i = +knob.dataset.band;
      const step = event.key === 'ArrowUp' ? 0.5 : event.key === 'ArrowDown' ? -0.5
                 : event.key === 'Home' ? null : undefined;
      if (step === undefined) return;
      event.preventDefault();
      this.setGain(i, step === null ? 0 : this.gains()[i] + step);
    });
    // Колесо над полем — та же полоса, шаг 0.5 дБ.
    view.svg.addEventListener('wheel', event => {
      event.preventDefault();
      const i = bandAt(event);
      this.setGain(i, this.gains()[i] + (event.deltaY > 0 ? -0.5 : 0.5));
    }, { passive: false });
  },

  /* ------------------------------------------------------- отрисовка */
  paintAll() {
    this.sweep();
    this.views.forEach(view => this.paint(view));
    const badge = $('eqBadge');
    if (badge) badge.textContent = this.summary();
  },

  summary() {
    if (!S.eqOn) return t('Off');
    const found = EQ_PRESETS.find(p => p[0] === (S.eqPreset || 'manual'));
    return t(found ? found[1] : 'Manual');
  },

  paint(view) {
    const list = this.gains();
    view.root.classList.toggle('is-off', !S.eqOn);
    view.sw.classList.toggle('on', !!S.eqOn);
    view.sw.setAttribute('aria-checked', S.eqOn ? 'true' : 'false');
    view.select.value = S.eqPreset || this.matchPreset(list);

    const pts = list.map((db, i) => [this.x(i), this.y(db)]);
    // Края: кривая уходит к рамке ровно, без «хвостов» вверх-вниз.
    const full = [[0, pts[0][1]], ...pts, [620, pts[pts.length - 1][1]]];
    const d = this.curve(full);
    view.line.setAttribute('d', d);
    view.area.setAttribute('d', `${d} L 620 ${this.y(-EQ_LIMIT)} L 0 ${this.y(-EQ_LIMIT)} Z`);
    [...view.knobs.children].forEach((knob, i) => {
      knob.setAttribute('cy', pts[i][1]);
      knob.setAttribute('aria-valuenow', list[i]);
      const title = knob.querySelector('title') ||
        knob.appendChild(document.createElementNS('http://www.w3.org/2000/svg', 'title'));
      title.textContent = `${EQ_BANDS[i].label}: ${list[i] > 0 ? '+' : ''}${list[i]} dB`;
    });
  },

  /* Гладкая кривая через точки (Catmull-Rom → кубические Безье). */
  curve(points) {
    if (points.length < 2) return '';
    let d = `M ${points[0][0]} ${points[0][1]}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i - 1] || points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)},` +
           ` ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
    return d;
  },
};

/* ------------------------------------------------------------- микшер */
/* Окно «Микшер»: громкость, баланс, нормализация, плавный переход и тот же
   эквалайзер. Открывается кнопкой на сцене «Диск» и клавишей M. */
const Mixer = {
  built: false,

  open() {
    this.build();
    if (typeof Viz !== 'undefined') Viz.mountColors('mxVizColor', 'mxVizC1', 'mxVizC2');
    this.sync();
    openModal('mMixer');
  },

  build() {
    if (this.built) return;
    this.built = true;
    Equalizer.mount($('mixEq'));
    if (typeof Viz !== 'undefined') Viz.mountColors('mxVizColor', 'mxVizC1', 'mxVizC2');

    const vol = $('mxVol');
    if (vol) {
      vol.oninput = () => {
        Player.setVolume(+vol.value);
        const slider = $('vol');
        if (slider) slider.value = vol.value;
        this.sync();
      };
    }
    const bal = $('mxBal');
    if (bal) {
      bal.oninput = () => { Player.setBalance(+bal.value); this.sync(); };
      bal.ondblclick = () => { Player.setBalance(0); this.sync(); };
    }
    const center = $('mxBalCenter');
    if (center) center.onclick = () => { Player.setBalance(0); this.sync(); };

    const norm = $('mxNorm');
    if (norm) {
      norm.onclick = () => {
        S.normalize = !S.normalize;
        saveSettings();
        Player.ensureCtx();
        Player.rebuild();
        document.querySelectorAll('[data-sw="normalize"]')
          .forEach(node => node.classList.toggle('on', !!S.normalize));
        this.sync();
      };
    }
    const fade = $('mxFade');
    if (fade) {
      fade.oninput = () => {
        S.fade = +fade.value;
        saveSettings();
        const other = $('sFade');
        if (other) other.value = fade.value;
        const text = $('vFade');
        if (text) text.textContent = S.fade;
        this.sync();
      };
    }
  },

  sync() {
    const set = (id, value) => { const n = $(id); if (n) n.value = value; };
    const text = (id, value) => { const n = $(id); if (n) n.textContent = value; };
    set('mxVol', S.volume); set('mxBal', S.balance || 0); set('mxFade', S.fade);
    text('mxVolV', S.volume + ' %');
    const b = Math.round((+S.balance || 0) * 100);
    text('mxBalV', b === 0 ? t('Centre') : (b < 0 ? `${t('Left')} ${-b} %` : `${t('Right')} ${b} %`));
    text('mxFadeV', S.fade + ' ' + t('s'));
    const norm = $('mxNorm');
    if (norm) norm.classList.toggle('on', !!S.normalize);
    Equalizer.paintAll();
  },
};
