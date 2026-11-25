/* tune.js — тонкая настройка цвета темы и обмен темами файлом.

   Раньше «своя тема» — это три поля цвета: акцент, второй акцент и фон.
   Всё остальное (насыщенность, яркость, теплота, заметность панелей,
   границ, контраст текста, сила свечения) было намертво вшито в
   css/app.css, и подогнать готовую палитру под себя было нельзя — только
   выбрать другую.

   Здесь эти значения считаются из палитры и поправок пользователя и
   выставляются теми же переменными, которыми живёт весь интерфейс. То
   есть коррекция работает поверх ЛЮБОЙ темы из каталога, включая
   рисованные и светлые, и ничего в самих темах менять не требуется.

   Второе, что лежит тут же, — экспорт и импорт. Тема целиком (палитра,
   поправки, настройки рисованного слоя и обоев) выгружается в один
   .json-файл, который можно отдать другу; импорт принимает такой файл
   обратно. Поэтому списки ключей живут рядом с кодом, который их считает. */
'use strict';

/* ------------------------------------------------------------ цвет: HSL */
function tnHex(hex) {
  const v = String(hex || '').replace('#', '').trim();
  const s = v.length === 3 ? v.split('').map(c => c + c).join('') : v;
  if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
  const n = parseInt(s, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function tnStr(rgb) {
  return '#' + rgb.map(v => Math.max(0, Math.min(255, Math.round(v)))
                           .toString(16).padStart(2, '0')).join('');
}
function tnToHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0, s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0));
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
  }
  return [h, s, l];
}
function tnFromHsl([h, s, l]) {
  h = ((h % 360) + 360) % 360;
  s = Math.max(0, Math.min(1, s));
  l = Math.max(0, Math.min(1, l));
  if (!s) { const v = l * 255; return [v, v, v]; }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const hue = k => {
    let x = (h / 360) + k;
    if (x < 0) x += 1; if (x > 1) x -= 1;
    if (x < 1 / 6) return p + (q - p) * 6 * x;
    if (x < 1 / 2) return q;
    if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
    return p;
  };
  return [hue(1 / 3) * 255, hue(0) * 255, hue(-1 / 3) * 255];
}

/* Поправка одного цвета. Теплота тянет оттенок к оранжевому (+) или к
   синему (−), но только там, где цвет вообще окрашен: серый остаётся
   серым, иначе «чёрно-белые» темы переставали быть чёрно-белыми. */
function tnShift(hex, { hue = 0, sat = 1, light = 1, warm = 0 }) {
  const rgb = tnHex(hex);
  if (!rgb) return hex;
  const hsl = tnToHsl(rgb);
  let [h, s, l] = hsl;
  if (s > 0.02) {
    h += hue;
    if (warm) {
      const target = warm > 0 ? 32 : 215;              // тёплый / холодный полюс
      let delta = ((target - h + 540) % 360) - 180;
      h += delta * Math.min(0.6, Math.abs(warm) / 100);
    }
  }
  s *= sat;
  // Яркость тянем к белому или к чёрному, а не умножаем: иначе светлые
  // палитры при «ярче» упирались в потолок и просто выцветали.
  l = light >= 1 ? l + (1 - l) * (light - 1) : l * light;
  return tnStr(tnFromHsl([h, Math.min(1, s), Math.max(0, Math.min(1, l))]));
}

function tnMixHex(a, b, k) {
  const x = tnHex(a) || [0, 0, 0], y = tnHex(b) || [255, 255, 255];
  return tnStr([0, 1, 2].map(i => x[i] + (y[i] - x[i]) * k));
}
function tnRgba(hex, alpha) {
  const rgb = tnHex(hex) || [0, 0, 0];
  return `rgba(${rgb.map(Math.round).join(', ')}, ${Math.max(0, Math.min(1, alpha)).toFixed(3)})`;
}

/* ------------------------------------------------------------- поправки */
/* Каждая поправка: ключ настройки, подпись, границы, единица. Список один
   и тот же для разметки, сброса и файла темы. */
const TUNE_FIELDS = [
  ['tuneHue', 'Hue shift', -180, 180, 5, '°'],
  ['tuneSat', 'Accent saturation', 0, 200, 5, '%'],
  ['tuneLight', 'Accent brightness', 50, 150, 5, '%'],
  ['tuneWarm', 'Warmth', -100, 100, 5, ''],
  ['tuneBgSat', 'Background saturation', 0, 200, 5, '%'],
  ['tuneBgLight', 'Background brightness', 50, 160, 2, '%'],
  ['tuneSurface', 'Panel contrast', 0, 300, 10, '%'],
  ['tuneLine', 'Border visibility', 0, 300, 10, '%'],
  ['tuneText', 'Text contrast', 60, 140, 2, '%'],
  ['tuneMuted', 'Secondary text', 40, 160, 5, '%'],
  ['tuneGlow', 'Accent glow', 0, 250, 10, '%'],
  ['tuneShadow', 'Shadow depth', 0, 200, 10, '%'],
];

/* Что уезжает в файл темы: палитра, поправки, рисованный слой и обои. */
const THEME_FILE_KEYS = [
  'theme', 'accent', 'accent2', 'bg', 'light', 'flat', 'sketch', 'radius',
  ...TUNE_FIELDS.map(f => f[0]),
  'sketchSkin', 'sketchInk', 'sketchPaper', 'sketchSky', 'sketchGold',
  'sketchDoodles', 'sketchDoodleOp', 'sketchTex', 'sketchStroke', 'sketchMark',
  'sketchWobble', 'sketchHand', 'sketchShadow', 'sketchGrain',
  'wallSrc', 'wallMode', 'wallOpacity', 'wallBlur', 'wallDim', 'wallScope',
  'uiFont', 'uiScale', 'coverShape', 'barStyle', 'glass', 'customCss',
];

const Tune = {
  /* Все поправки стоят по нулям — тогда и считать нечего. */
  idle() {
    return TUNE_FIELDS.every(([key]) => (+S[key] || 0) === (+DEFAULTS[key] || 0));
  },

  /* Считает итоговые переменные темы. Вызывается из applyTheme() последней,
     поэтому спокойно перекрывает базовые значения. */
  apply() {
    const r = document.documentElement.style;
    /* Панели, границы, текст и тень переопределяет правило `body.light` в
       css/app.css. Переменная, выставленная на <html>, этим правилом
       перекрывается — поэтому такие токены пишем прямо на <body>: инлайн
       на самом элементе сильнее любого правила для него. */
    const b = document.body.style;
    const light = !!S.light;
    const num = (key, fallback) => {
      const v = +S[key];
      return Number.isFinite(v) ? v : fallback;
    };
    const hue = num('tuneHue', 0);
    const warm = num('tuneWarm', 0);
    const opts = {
      hue, warm,
      sat: num('tuneSat', 100) / 100,
      light: num('tuneLight', 100) / 100,
    };
    const accent = tnShift(S.accent, opts);
    const accent2 = tnShift(S.accent2, opts);
    const bg = tnShift(S.bg, {
      hue, warm,
      sat: num('tuneBgSat', 100) / 100,
      light: num('tuneBgLight', 100) / 100,
    });
    r.setProperty('--accent', accent);
    r.setProperty('--accent-2', accent2);
    r.setProperty('--bg', bg);
    // Второй слой фона: на тёмных темах чуть светлее, на светлых — чуть темнее.
    r.setProperty('--bg-2', tnMixHex(bg, light ? '#000000' : '#FFFFFF', light ? 0.035 : 0.055));

    const glow = num('tuneGlow', 100) / 100;
    r.setProperty('--accent-soft', tnRgba(accent, (light ? 0.16 : 0.2) * glow));

    /* Рисованная тема собирает свою бумагу, чернила и панели сама
       (js/sketch.js). Навязывать ей обычные токены нельзя — лист перестанет
       быть листом, поэтому там эти поправки просто снимаются. */
    if (S.sketch) {
      ['--surface', '--surface-2', '--line', '--text', '--muted', '--shadow']
        .forEach(name => b.removeProperty(name));
      return;
    }

    // Панели и границы — полупрозрачный белый на тёмном и почти чёрный на
    // светлом: так они ложатся на любой фон, включая обои.
    const ink = light ? '12, 10, 30' : '255, 255, 255';
    const surf = num('tuneSurface', 100) / 100;
    const linek = num('tuneLine', 100) / 100;
    const base = light ? [0.04, 0.07, 0.1] : [0.045, 0.075, 0.09];
    b.setProperty('--surface', `rgba(${ink}, ${(base[0] * surf).toFixed(3)})`);
    b.setProperty('--surface-2', `rgba(${ink}, ${(base[1] * surf).toFixed(3)})`);
    b.setProperty('--line', `rgba(${ink}, ${(base[2] * linek).toFixed(3)})`);

    // Контраст текста считается от фона: «меньше» не делает текст серым
    // пятном, а подтягивает его к фону ровно на заданную долю.
    const text = light ? '#16142A' : '#F2F2F7';
    const tk = num('tuneText', 100) / 100;
    b.setProperty('--text', tk >= 1
      ? tnMixHex(text, light ? '#000000' : '#FFFFFF', Math.min(0.6, tk - 1))
      : tnMixHex(text, bg, Math.min(0.7, 1 - tk)));
    const muted = light ? '#625F7E' : '#9A9AB2';
    const mk = num('tuneMuted', 100) / 100;
    b.setProperty('--muted', mk >= 1
      ? tnMixHex(muted, text, Math.min(0.8, mk - 1))
      : tnMixHex(muted, bg, Math.min(0.8, 1 - mk)));

    const shadow = num('tuneShadow', 100) / 100;
    b.setProperty('--shadow', light
      ? `0 18px 44px rgba(30, 24, 70, ${(0.14 * shadow).toFixed(3)})`
      : `0 18px 50px rgba(0, 0, 0, ${(0.45 * shadow).toFixed(3)})`);

    const meta = document.querySelector('meta[name=theme-color]');
    if (meta) meta.content = bg;
  },

  reset() {
    TUNE_FIELDS.forEach(([key]) => { S[key] = DEFAULTS[key]; });
    applyTheme(); saveSettings(); this.build();
    toast(t('Colour correction reset'));
  },

  build() {
    const host = $('tuneList');
    if (!host) return;
    host.innerHTML = '';
    TUNE_FIELDS.forEach(([key, label, min, max, step, unit]) => {
      const row = el('div', 'set');
      const left = el('div');
      left.appendChild(el('div', 'l', t(label)));
      const value = el('div', 'h', (+S[key] || 0) + (unit ? ' ' + unit : ''));
      left.appendChild(value);
      row.appendChild(left);
      const cell = el('div', 'c');
      const slider = document.createElement('input');
      slider.type = 'range';
      slider.min = min; slider.max = max; slider.step = step;
      slider.value = +S[key] || 0;
      slider.oninput = () => {
        S[key] = Math.round(+slider.value);
        value.textContent = S[key] + (unit ? ' ' + unit : '');
        applyTheme(); saveSettings();
      };
      cell.appendChild(slider);
      row.appendChild(cell);
      host.appendChild(row);
    });
  },

  /* -------------------------------------------------- файл темы */
  /* Формат нарочно простой и читаемый: это обычный JSON, его можно
     открыть блокнотом и переслать как угодно. Версия нужна, чтобы
     будущие сборки понимали старые файлы. */
  export() {
    const data = { kryonyxTheme: 1, app: 'Kryo', name: this.title(), values: {} };
    THEME_FILE_KEYS.forEach(key => {
      if (S[key] !== undefined) data.values[key] = S[key];
    });
    const name = (data.name || 'theme').toLowerCase().replace(/[^a-z0-9._-]+/g, '-');
    return FileSave27.save({kind:'theme',name:`${name || 'theme'}.kryonyx-theme.json`,text:JSON.stringify(data,null,2)});
  },

  title() {
    const field = $('themeName');
    const typed = field && field.value.trim();
    if (typed) return typed;
    const theme = (typeof THEME_LIBRARY !== 'undefined' && THEME_LIBRARY[S.theme]) || null;
    return theme ? theme.name : 'Kryo';
  },

  async import(file) {
    if (!file) return;
    let data = null;
    try { data = JSON.parse(await file.text()); }
    catch { toast(t('This file is not a theme')); return; }
    const values = data && (data.values || (data.kryonyxTheme ? null : data));
    if (!values || typeof values !== 'object') { toast(t('This file is not a theme')); return; }
    let used = 0;
    THEME_FILE_KEYS.forEach(key => {
      if (!(key in values)) return;
      const value = values[key];
      const want = typeof DEFAULTS[key];
      // Чужой файл не должен ломать настройки: принимаем только значения
      // того же типа, что и у настройки по умолчанию.
      if (want !== 'undefined' && typeof value !== want) return;
      if (want === 'string' && value.length > 20000) return;
      S[key] = value;
      used++;
    });
    if (!used) { toast(t('This file is not a theme')); return; }
    applyTheme(); saveSettings(true);
    const field = $('themeName');
    if (field && data.name) field.value = data.name;
    if (typeof Themes !== 'undefined') Themes.build();
    if (typeof Sketch !== 'undefined') Sketch.build();
    if (typeof Wall !== 'undefined') Wall.build();
    if (typeof Look !== 'undefined') Look.build();
    this.build();
    if (typeof App !== 'undefined') App.syncSettingsUI();
    toast(t('Theme applied') + (data.name ? ': ' + data.name : ''));
  },

  bind() {
    const out = $('themeExport');
    if (out) out.onclick = () => this.export();
    const file = $('themeFile');
    const pick = $('themeImport');
    if (pick && file) pick.onclick = () => file.click();
    if (file) file.onchange = event => {
      const chosen = event.target.files && event.target.files[0];
      event.target.value = '';
      this.import(chosen);
    };
    const reset = $('tuneReset');
    if (reset) reset.onclick = () => this.reset();
  },
};
