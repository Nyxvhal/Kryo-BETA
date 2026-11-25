/* core.js — состояние, настройки, темы, API, мелкие утилиты. */
'use strict';

const K = {
  view: 'home',
  stack: [],
  search: { query: '', page: 0, tracks: [], loading: false, more: false },
  playlists: [],
  likes: new Set(),
  health: null,
  desktop: !!(window.pywebview && window.pywebview.api),
};

/* ------------------------------------------------------------- настройки */
const DEFAULTS = {
  repair33:false,
  upgrade30:false, auroraContrast30:1.15, auroraFps30:30, idleDelay30:3, lyricScale30:1, sidebarWidth30:232, panelRadius30:14, interfaceSpace30:14,
  search26Hidden: [],             // explicit local recommendation dismissals, bounded to 200 keys
  ui7: { favorites: [] },
  studio: { searchLayout: 'list', searchSort: 'relevance', density: 'comfortable', cards: 180, stats: true, localStats: true, hero: true, quick: true, hidden: [], order: [], saved: [] },
  workspace: { libraryLayout: 'grid', librarySort: 'recent', listSort: 'original', sidebarCollapsed: false, compactPlayer: true, pinned: [] },
  appearance52: {palette:'theme',accent:'#ffffff',fontSize:15,cards:184,radius:12,art:'soft',motion:'smooth',showSource:true,showReasons:true,showClip:true,showLike:true,showAdd:true},
  vizBudget51: 'auto',
  recommend50: {discovery:50,importInfluence:65},
  transfer49: {connections:[],history:[]},
  layout48: {sidebar:'left',sidebarWidth:232,dock:'bottom',transport:'center',density:'comfortable',radius:12,motion:'smooth',quality:'balanced'},
  lang: 'en',
  lyricTranslationTarget: '',
  lyricTranslationVisible: true,
  themeArtwork: typeof KRYONYX_BUILD !== 'undefined' ? KRYONYX_BUILD.themeArtwork : 'characters',
  /* v70: новые пользователи начинают с чёрно-белой OLED-темы. Профили, где
     тема уже сохранена, её не меняют: настройки хранятся целиком. */
  theme: 'oled',
  /* Аватарка приложения: id из kryonyx/avatars.json. Она же иконка окна,
     панели задач и ярлыков — см. js/avatars.js и kryonyx/avatars.py. */
  avatar: 'kryonyx-core',
  /* YouTube нужен в наборе по умолчанию: у Spotify нет своего потока, и
     звук для его треков подбирается в других библиотеках. */
  sources: ['youtube', 'soundcloud', 'spotify'],
  accent: '#FFFFFF',
  accent2: '#9AA0A6',
  bg: '#000000',
  light: false,
  sketch: false,                   // нарисованная тема: включает css/sketch.css
  /* Рисованная тема настраивается целиком: скин задаёт палитру и характер
     бумаги, а поправки ниже перебивают любое его поле. Пустая строка
     означает «брать из скина». См. js/sketch.js. */
  sketchFavorites: [],
  sketchRenderRev: 0,              // migrated once by Sketch.apply; persisted with settings
  sketchSkin: 'saba',             // id скина: saba, noir, blueprint, kraft…
  sketchInk: '',                  // свои чернила
  sketchPaper: '',                // своя бумага
  sketchSky: '',                  // свой акцент
  sketchGold: '',                 // своё золото
  sketchDoodles: 'skin',          // skin | fish | stars | music | hearts | geo | mix | none
  sketchDoodleOp: 0,             // заметность каракулей, %
  sketchTex: 'skin',              // skin | ruled | grid | dots | plain
  sketchStroke: 85,              // нажим карандаша, %
  sketchMark: 'dot',              // маркер и бегунок: dot | star | fish
  sketchWobble: false,             // неровные скругления
  sketchHand: false,               // рукописные заголовки (Caveat)
  sketchShadow: false,             // карандашная тень со смещением
  sketchGrain: false,              // зерно бумаги
  /* Обои под интерфейсом. 'local' — картинка из localStorage, 'cover' —
     обложка текущего трека, 'p:*' — встроенный узор, иначе прямая ссылка. */
  wallSrc: '',
  wallMode: 'cover',              // cover | contain | tile | center
  wallOpacity: 40,                // непрозрачность обоев, %
  wallBlur: 0,                    // размытие обоев, px
  wallDim: 30,                    // шторка поверх обоев, %
  wallScope: 'both',              // app | player | both
  /* Внешний вид интерфейса поверх любой темы. */
  uiFont: 'system',               // system | rounded | serif | mono | hand | condensed
  uiScale: 100,                   // масштаб интерфейса, %
  coverShape: 'rounded',          // rounded | square | circle
  barStyle: 'slim',               // slim | round | thick | step
  panelOpacity33: 75,
  audioQuality: 'best',
  glass: 22,                      // размытие под панелями, px
  customCss: '',                  // своё правило CSS
  /* Коррекция цвета темы: работает поверх любой палитры, см. js/tune.js. */
  tuneHue: 0,                     // сдвиг оттенка акцентов, °
  tuneSat: 100,                   // насыщенность акцентов, %
  tuneLight: 100,                 // яркость акцентов, %
  tuneWarm: 0,                    // теплота: + к тёплому, − к холодному
  tuneBgSat: 100,                 // насыщенность фона, %
  tuneBgLight: 100,               // яркость фона, %
  tuneSurface: 100,               // заметность панелей, %
  tuneLine: 100,                  // заметность границ, %
  tuneText: 100,                  // контраст основного текста, %
  tuneMuted: 100,                 // контраст второстепенного текста, %
  tuneGlow: 100,                  // сила свечения акцента, %
  tuneShadow: 100,                // глубина теней, %
  radius: 18,
  karaokeBg: true,
  karaokeStyle: 'albumflow',
  karaokeSize: 'm',               // размер текста: s / m / l
  karaokeDim: true,               // приглушать и размывать соседние строки
  karaokeDots: true,              // точки отсчёта в проигрышах
  karaokeBare: false,             // «только караоке»: кнопки прячутся
  vbgOn: false, vbgFit: 'cover', vbgBlur: 0, vbgDim: 35,
  /* «Визуализатор»: цвет сцены. white — белый монохром (по умолчанию),
     custom — две свои краски из настроек, остальное как раньше. */
  vizColor: 'cover',              // white | cycle | cover | accent | custom
  vizColor1: '#FFFFFF',           // своя первая краска сцены
  vizColor2: '#FFFFFF',           // своя вторая краска сцены
  vizParticles: true,
  vizMirror: true,                // спектр от центра в обе стороны
  vizWave: false,                 // живая волна только по выбору пользователя
  vizRings: true,                 // кольца расходятся от обложки на удар
  vizReflect: false,              // отражение обложки под ней
  /* Фон сцены: auto (сцена выбирает под трек) | beams | grid | hex |
     tunnel | stars | aurora | rain | ridge | city | orbit | ripple |
     plasma | spiral | cover | off */
  vizScene: 'beams',
  vizSpec: 'mirror',              // шкала: top | mirror | bars | wave | dots | led | spike | line
  vizAdapt: true,                 // сцена подстраивается под характер трека
  vizLayout: 'side',              // side | center | poster — где обложка и подписи
  vizShape: 'round',              // round | circle | square — форма обложки
  vizArt: 100,                    // размер обложки, %
  vizText: 100,                   // размер подписей, %
  vizGlow: 100,                   // сила свечения, %
  vizBgLevel: 100,                // яркость фона, %
  vizSparkRate: 100,              // плотность искр, %
  vizMotion: 100,                 // скорость движения сцены, %
  vizPeaks: true,                 // шапки пиков на шкале
  vizVignette: true,              // затемнение по краям сцены
  vizFlash: true,                 // вспышка сцены на удар
  vizTilt: true,                  // обложка поворачивается за курсором
  vizTip: true,                   // подсказка времени на шкале
  vizProgress: true,              // полоса прогресса в рамке над спектром
  vizSource: true,                // ярлык-рамка рядом со временем
  vizSrcText: '',                 // свой текст в этом ярлыке
  vizMark: false,                 // крупная подпись исполнителя под плеером
  vizDecor: true,                 // уголки рамки и неоновые штрихи у обложки
  vizScan: true,                  // строки развёртки и редкий глитч
  vizBolts: true,                 // молнии на удар
  kCoverOn: false,                // своя обложка на экране караоке
  kCoverMode: 'always',           // always | missing
  kCoverUrl: '',
  kArt: 100,                      // размер обложки, %
  kBgKind: 'auto',                // auto | image | color | gradient
  kBgUrl: '', kBgColor: '#101018', kBgColor2: '#3a1c71', kBgAngle: 135,
  kBgFit: 'cover', kBgBlur: 0, kBgDim: 30, kbScene: false,
  karaokeTiming: 'line',          // line | word | syllable (independent of layout)
  playbackSpeed: 1,
  karaokeMode: 'split',           // split | focus | cinema
  karaokeAlign: 'left',           // left | center
  karaokeLit: 'text',             // text | accent — цвет подсветки строки
  karaokeLook: 'glow',            // glow | apple — вид строк караоке
  playerControls: true,           // кнопки на экране плеера (полоса остаётся)
  karaokeWords: false,            // устаревший ключ: караоке подсвечивает строку целиком
  coverQuality: 'high',           // normal | high | max — разрешение обложек
  videoQuality: 720,              // качество встроенных музыкальных клипов
  clipPreload: false,             // legacy key; v4 prefetch is explicitly opt-in
  videoVolume: 100,               // отдельная сохраняемая громкость клипов
  clipStartPercent: 10,
  clipMinBuffer: 3,
  clipSpeed: 1,
  clipLoop: false,
  clipAutoNext: true,
  clipPrefetch: false,
  clipKeepDownloading: false,
  clipResume: true,
  /* Режим «Диск» */
  discSync: 'line',               // word | line — слово за словом или строкой
  discLayout: 'side',             // side | under | over — где текст
  discCaseSkin: 'jewel',          // jewel | bare | vinyl — вид коробки
  discSize: 100,                  // размер диска, %
  discTextSize: 100,              // размер текста, %
  discSpinSpeed: 8,               // секунд на оборот
  discLines: 4,                   // сколько строк текста помещается
  discGrain: true,                // зерно на буквах
  discGlow: true,                 // свечение за диском (старый ключ, совместимость)
  discGlowStyle: 'cover',         // свечение: cover | white (bloom как в клипе) | off
  discPulse: true,                // свет и яркость дышат в такт басу
  reactSense: 100,                // чувствительность всех эффектов к музыке, %
  discBloom: true,                // белое свечение вокруг слов
  settingsRev: 8,                 // ревизия настроек: см. migrate() ниже
  discReflect: false,             // отражение диска под коробкой
  discItalic: true,               // первое слово страницы курсивом
  discVignette: true,             // затемнение по краям сцены
  discMeta: true,                 // название трека внизу
  discFade: true,                 // слова проявляются, а не возникают
  discLead: 0,                    // поправка слов, с (минус — раньше)
  discHold: 0.25,                 // выдержка слова, с (метки в базах спешат)
  discLinger: 1.6,                // сколько строка висит после конца, с
  discBigButtons: false,          // крупные кнопки на сцене
  spin: true,
  compact: false,
  rail: false,
  flat: true,
  vizExperience32: 'aurora',
  vizEffect46: 'rings', vizEffectIntensity46: 70,
  noAnim: false,
  atmo: true,                     // «атмосфера караоке»: живой свет из обложки
  fade: 0,
  normalize: false,
  /* Эквалайзер: включён ли, шесть полос в дБ и имя пресета. Всё это уходит
     в базу на устройстве вместе с остальными настройками, поэтому кривая
     держится до следующего изменения. */
  eqOn: false,
  eqGains: [0, 0, 0, 0, 0, 0],
  eqPreset: 'flat',
  balance: 0,                     // −1 левее, 0 центр, +1 правее
  endlessRadio: true,
  // окно настольной сборки
  winOnTop: false,
  miniPlayer: false,              // мини-плеер поверх всех окон
  winRemember: true,
  winGrab: false,
  winGrip: true,

  autoLyrics: true,
  lyricsOffset: 0,
  lyricsFit: false,               // тянуть шкалу текста под длину файла
  lyricsAutoSync: true,          // ловить сдвиг текста на слух
  volume: 100,
  limit: 20,
  prefetch: true,
  logFollow: true,
  streamExpiryMs: 3600000,        // сколько живёт готовая ссылка на поток
  streamResolutionRetries: 3,     // как playback.streamResolutionRetries
  autoFallback: true,
  shuffle: false,
  repeat: 'off',
  lastVolume: 100,             // громкость до нажатия «без звука»
};

const SOURCE_META = {
  youtube:    { name: 'YouTube',          tag: 'yt' },
  soundcloud: { name: 'SoundCloud',       tag: 'sc' },
  spotify:    { name: 'Spotify',          tag: 'sp' },
  audius:     { name: 'Audius',           tag: 'au' },
  bandcamp:   { name: 'Bandcamp',         tag: 'bc' },
  archive:    { name: 'Internet Archive', tag: 'ia' },
  mixcloud:   { name: 'Mixcloud',         tag: 'mx' },
  jamendo:    { name: 'Jamendo',          tag: 'jm' },
  radio:      { name: 'Internet Radio',   tag: 'rb' },
  deezer:     { name: 'Deezer',           tag: 'dz' },
};

/* Каталог тем живёт в themes.js — там же группы и подписи. */
const THEMES = THEME_LIBRARY;

/* Настройки, которые нельзя округлять до целого: доли секунды здесь и есть
   весь смысл (поправки синхронизации текста). */
const FLOAT_SETTINGS = ['lyricsOffset', 'discLead', 'discHold', 'discLinger'];

let S = { ...DEFAULTS };

/* ------------------------------------------------- облегчённый режим
   Запуск с `?safe=1`. Так окно открывается после того, как прошлый запуск
   не доложил о загрузке: всё тяжёлое оформление выключено, настройки не
   сохраняются. Задача режима — чтобы плеером можно было пользоваться и
   разобраться, что именно не поднялось. */
const SAFE = /[?&]safe=1/.test(location.search);

const SAFE_OFF = {
  atmo: false, sketch: false, noAnim: true, spin: false,
  wallSrc: '', customCss: '', glass: 0, karaokeBg: false, discGrain: false,
  discGlow: false, discPulse: false, discBloom: false,
};

function applySafeMode() {
  if (!SAFE) return;
  Object.assign(S, SAFE_OFF);
  document.body.classList.add('safe-mode');
}

function loadLocal() {
  try {
    const saved = JSON.parse(localStorage.getItem('kryonyx') || '{}');
    const own = {};
    for (const key of Object.keys(DEFAULTS)) {
      if (saved[key] !== undefined && saved[key] !== null) own[key] = saved[key];
    }
    S = { ...DEFAULTS, ...own };
  } catch { S = { ...DEFAULTS }; }
  dropLegacy();
  // Do not write a stale local snapshot before the device database is read.
  migrate(false);
}

/* Перенос настроек со старых версий.

   Ловушка, из-за которой новые возможности «не появлялись»: настройки
   хранятся целиком, поэтому значение, записанное прошлой сборкой,
   перебивает новое значение по умолчанию. Капли на коробке и новая
   выдержка слова так и оставались выключенными. Ревизия решает это раз и
   навсегда: каждый шаг применяется один раз. */
function migrate(persist = true) {
  const rev = +S.settingsRev || 0;
  if (rev >= 8) return;
  if (rev < 2) {
    // выдержка слова на диске поднята с 0.08 с — старое значение
    // держалось в базе, и текст по-прежнему спешил.
    if (!(+S.discHold > 0.1)) S.discHold = DEFAULTS.discHold;
    if (!S.discGlowStyle) S.discGlowStyle = DEFAULTS.discGlowStyle;
    S.discGlow = true;
  }
  // режима капель больше нет — ключ из базы просто выбрасываем.
  delete S.discDrops;
  if (rev < 4) {
    // Рыбка-маркер заменена на нарисованный кружок. Старым базам
    // переключаем только то, что стояло по умолчанию: если человек сам
    // выбрал звёздочку, выбор остаётся.
    if (!S.sketchMark || S.sketchMark === 'fish') S.sketchMark = 'dot';
  }
  // пословный режим убран. В старых профилях он мог остаться
  // включённым и перебить новое поведение после обновления.
  S.karaokeWords = false;
  if (rev < 6) {
    // 2.27: цвета «Визуализатора» стали белыми. Старые профили держали
    // в базе прежний перебор оттенков и нового вида не видели.
    if (!S.vizColor || S.vizColor === 'cycle') S.vizColor = DEFAULTS.vizColor;
    if (!S.vizColor1) S.vizColor1 = DEFAULTS.vizColor1;
    if (!S.vizColor2) S.vizColor2 = DEFAULTS.vizColor2;
  }
  if (rev < 7) {
    // отражение обложки в «Визуализаторе» убрано из вида по
    // умолчанию — его просили выключить. Настройка осталась на месте.
    S.vizReflect = false;
    if (!S.vizSpec) S.vizSpec = DEFAULTS.vizSpec;
  }
  if (rev < 8) {
    // 1.0.0: крупная подпись исполнителя под плеером убрана из вида по
    // умолчанию. Тумблер остался в настройках «Визуализатора».
    S.vizMark = false;
  }
  S.settingsRev = 8;
  if (persist) saveSettings(true);
}

/* микшер скорости убран — старые ключи из базы больше не нужны. */
function dropLegacy() {
  ['speed', 'pitch', 'pitchWithSpeed', 'discDrops']
    .forEach(key => { delete S[key]; });
}

/* Полный снимок настроек для базы.

   Тут была неприятная ловушка: `JSON.stringify` молча выбрасывает ключи со
   значением `undefined`. Тёмные темы не задают поле `light`, поэтому
   `useTheme()` писал в S `light: undefined`, ключ не попадал в запрос, а
   `storage.save_settings()` пишет только присланные ключи — в базе
   оставалось `light: true` от прошлой светлой темы. После перезапуска тема
   приезжала «наполовину»: цвета новые, а режим светлый.

   Поэтому в базу всегда уходят ВСЕ ключи из DEFAULTS, и ни один из них не
   может быть undefined. */
function settingsPayload() {
  const out = {};
  for (const key of Object.keys(DEFAULTS)) {
    const value = S[key];
    out[key] = value === undefined || value === null ? DEFAULTS[key] : value;
  }
  return out;
}

let saveTimer;
let settingsWrite45 = Promise.resolve();
// Monotonic revision prevents older save responses from overwriting current feedback.
saveSettings.revision = 0;
function saveSettings(now) {
  // В облегчённом режиме часть настроек подменена принудительно —
  // записывать подмену в базу нельзя, иначе обычный режим тоже останется
  // без оформления.
  if (SAFE) return;
  // localStorage — быстрый кэш, настоящее хранилище — база на устройстве:
  // WebView может очистить своё хранилище, база переживает и это.
  const payload = JSON.parse(JSON.stringify(settingsPayload()));
  try { localStorage.setItem('kryonyx', JSON.stringify(payload)); }
  catch { /* приватный режим */ }
  clearTimeout(saveTimer);
  dispatchEvent(new CustomEvent('kryonyx:settings-save', {detail:'pending'}));
  const revision = ++saveSettings.revision;
  const push = () => {
    settingsWrite45 = settingsWrite45.catch(() => {}).then(async () => {
      // Coalesce snapshots that have not started yet. An in-flight save finishes first.
      if (revision !== saveSettings.revision) return;
      try {
        await api('/api/settings', { method: 'PUT', body: payload });
        if(revision === saveSettings.revision) dispatchEvent(new CustomEvent('kryonyx:settings-save', {detail:'saved'}));
      } catch (error) {
        if(revision === saveSettings.revision) dispatchEvent(new CustomEvent('kryonyx:settings-save', {detail:'error'}));
        throw error;
      }
    });
    // The next save can retry; do not create an unhandled promise rejection.
    settingsWrite45.catch(() => {});
    return settingsWrite45;
  };
  if (now) return push(); else saveTimer = setTimeout(push, 500);
}

/* Настройки и тема при запуске берутся из базы: что пользователь выбрал в
   прошлый раз, то и увидит, даже после переустановки WebView или чистки кэша. */
async function pullSettings() {
  try {
    const remote = await api('/api/settings', { timeout: 6000 });
    if (remote && typeof remote === 'object' && Object.keys(remote).length) {
      // В той же таблице лежат каталог плагинов и поправки караоке —
      // в настройки интерфейса они попадать не должны.
      const own = {};
      for (const key of Object.keys(DEFAULTS)) {
        if (remote[key] !== undefined && remote[key] !== null) own[key] = remote[key];
      }
      S = { ...DEFAULTS, ...own };
      dropLegacy();
      // В базе лежит тот же старый набор, поэтому перенос нужно повторить
      // и здесь: иначе значения из базы снова перебивали новые.
      migrate();
      try { localStorage.setItem('kryonyx', JSON.stringify(S)); } catch {}
      return true;
    }
  } catch { /* Не затираем базу локальным снимком при ошибке чтения. */ return false; }
  // Базы ещё нет: кладём в неё то, что есть, чтобы дальше она была главной.
  saveSettings(true);
  return false;
}

// Закрытие окна не должно съедать последнее изменение настроек.
addEventListener('pagehide', () => {
  clearTimeout(saveTimer);
  // В облегчённом режиме настройки подменены принудительно: маяк при
  // закрытии окна утащил бы эту подмену в базу в обход saveSettings().
  if (SAFE) {
    if (typeof Player !== 'undefined' && Player.saveState) Player.saveState(true, true);
    return;
  }
  try {
    const body = new Blob([JSON.stringify(settingsPayload())],
                          { type: 'application/json' });
    navigator.sendBeacon && navigator.sendBeacon('/api/settings/beacon', body);
  } catch {}
  if (typeof Player !== 'undefined' && Player.saveState) Player.saveState(true, true);
});

/* ------------------------------------------------------------------ темы */
function hex2rgb(hex) {
  const v = hex.replace('#', '');
  const n = parseInt(v.length === 3 ? v.split('').map(c => c + c).join('') : v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function mix(hex, amount) {
  const [r, g, b] = hex2rgb(hex);
  const f = v => Math.max(0, Math.min(255, Math.round(v + amount)));
  return `#${[f(r), f(g), f(b)].map(v => v.toString(16).padStart(2, '0')).join('')}`;
}
function rgba(hex, a) { const [r, g, b] = hex2rgb(hex); return `rgba(${r},${g},${b},${a})`; }

function applyTheme() {
  if(S.theme==='sketch:vt-ironmouse-season-0'){S.theme='studio6';S.sketch=false;S.sketchSkin='saba';}
  const r = document.documentElement.style;
  r.setProperty('--accent', S.accent);
  r.setProperty('--accent-2', S.accent2);
  r.setProperty('--accent-soft', rgba(S.accent, S.light ? 0.16 : 0.2));
  r.setProperty('--bg', S.bg);
  r.setProperty('--bg-2', S.light ? mix(S.bg, 12) : mix(S.bg, 8));
  // Поправки пользователя пересчитывают те же переменные поверх палитры:
  // насыщенность, яркость, теплота, панели, границы, текст, тени.
  if (typeof Tune !== 'undefined') Tune.apply();
  r.setProperty('--radius', S.radius + 'px');
  r.setProperty('--radius-sm', Math.max(4, S.radius - 6) + 'px');
  document.body.classList.toggle('light', !!S.light);
  document.body.classList.toggle('compact', !!S.compact);
  document.body.classList.toggle('nav-rail', !!S.rail);
  document.body.classList.toggle('flat', !!S.flat);
  document.body.classList.toggle('sketch', !!S.sketch);
  // Рисованная тема собирает свои контуры и бумагу сама: цвет чернил
  // живёт внутри SVG, из CSS его не поменять. См. js/sketch.js.
  if (S.sketch && typeof applyReferencePalette === 'function') applyReferencePalette();
  if (typeof Sketch !== 'undefined') { S.sketch ? Sketch.apply() : Sketch.clear(); }
  if (!S.sketch && typeof applyReferencePalette === 'function') applyReferencePalette();
  document.body.classList.toggle('no-anim', !!S.noAnim);
  document.body.classList.toggle('spin', !!S.spin);
  if(window.KMarquee)KMarquee.sync();
  if (typeof Look !== 'undefined') Look.apply();
  if (typeof Wall !== 'undefined') Wall.apply();
  if (typeof Atmo !== 'undefined' && Atmo.root) Atmo.apply();
  const meta = document.querySelector('meta[name=theme-color]');
  if (meta) meta.content = S.bg;
}

function useTheme(id) {
  const chosenAvatar=S.avatar;
  const theme = THEMES[id];
  if (!theme) return;
  // Рисованных тем теперь много: каждая — это скин из js/sketch.js. Выбор
  // такой темы сбрасывает ручные поправки, иначе новый скин приедет в
  // чернилах предыдущего.
  if (theme.skin) {
    S.sketchSkin = theme.skin;
    ['sketchInk', 'sketchPaper', 'sketchSky', 'sketchGold'].forEach(k => { S[k] = ''; });
    S.sketchDoodles = 'skin';
    S.sketchTex = 'skin';
    const skin = (typeof SKETCH_SKINS !== 'undefined' && SKETCH_SKINS[theme.skin]) || null;
    if (skin) S.sketchMark = skin.mark || 'dot';
  }
  // Каждое поле приводим к настоящему значению: у тёмных тем `light` и
  // `flat` в каталоге просто не заданы, а `undefined` в настройках означало
  // «оставить как было» — тема применялась наполовину.
  Object.assign(S, {
    theme: id,
    accent: theme.accent || DEFAULTS.accent,
    accent2: theme.accent2 || DEFAULTS.accent2,
    bg: theme.bg || DEFAULTS.bg,
    light: !!theme.light,
    flat: !!theme.flat,
    // Своё оформление есть только у «Sketch»: у остальных тем флаг гаснет,
    // иначе рисованный слой остался бы висеть после переключения.
    sketch: false,
  });
  applyTheme();
  S.avatar=chosenAvatar;
  if(typeof Avatars!=='undefined')Avatars.paint();
  // Тему сохраняем сразу: закрыть окно успевают быстрее, чем истекут 500 мс.
  saveSettings(true);
}

/* ------------------------------------------------------------------- API */
/* Любой запрос ограничен по времени: раньше зависший ответ сервера оставлял
   экран на скелетонах навсегда — теперь приходит внятная ошибка. */
async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {} };
  if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  // По умолчанию таймаута нет: импорт плейлиста и скачивание идут долго.
  // Ограничиваем только те запросы, где зависание видно как вечный скелетон.
  const limit = opts.timeout || 0;
  let timer = null, timedOut = false, detach = null;
  if ((limit || opts.signal) && typeof AbortController === 'function') {
    const ctrl = new AbortController();
    init.signal = ctrl.signal;
    if (opts.signal) {
      const cancel = () => ctrl.abort();
      if (opts.signal.aborted) cancel();
      else { opts.signal.addEventListener('abort', cancel, {once:true}); detach = () => opts.signal.removeEventListener('abort', cancel); }
    }
    if (limit) timer = setTimeout(() => { timedOut = true; ctrl.abort(); }, limit);
  }
  let res, text;
  try {
    res = await fetch(path, init);
    // Reading the body is part of the request too: headers alone are not completion.
    text = await res.text();
  } catch (err) {
    if (err && err.name === 'AbortError' && timedOut) throw new Error(t('Request timed out'));
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
    if (detach) detach();
  }
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: text }; }
  if (!res.ok) {
    // Ответ не всегда JSON: прокси и сам сервер умеют отдать страницу с
    // ошибкой. Её разметку в окно сообщения тащить незачем — оставляем
    // короткий текст, иначе на экране оказывается кусок HTML.
    let note = String(data.error || '').trim();
    if (/^\s*</.test(note) || note.length > 160) note = '';
    // Сервер отвечает по-английски; сообщение переводится здесь, чтобы
    // и склейки вида t('Failed: ') + err.message были на языке интерфейса.
    // Исходный английский текст остаётся в err.raw для проверок в коде.
    const raw = note;
    if (note && typeof tParts === 'function') note = tParts(note);
    const error = new Error(note || `HTTP ${res.status}`);
    error.raw = raw;
    error.status = res.status;
    error.data = data;   // v72: structured details (e.g. {code, missing}) for callers that need them
    throw error;
  }
  return data;
}

const memo = new Map();
const inflight = new Map();
const cacheWrites = new Map();
let memoRevision = 0;
/* Кэш + склейка параллельных запросов: два клика по одному автору больше не
   заставляют сервер делать двойную работу. */
async function cachedApi(path, ttl = 120000, opts = {}) {
  if (opts.signal?.aborted) throw new DOMException('Request aborted', 'AbortError');
  const hit = memo.get(path);
  if (hit && Date.now() - hit.at < ttl) return hit.value;
  // An independently cancellable request must not own another caller's in-flight work.
  if (opts.signal) {
    const revision = memoRevision, write = {};
    cacheWrites.set(path, write);
    try {
      const value = await api(path, opts);
      if (!opts.signal.aborted && revision === memoRevision && cacheWrites.get(path) === write && (!opts.cacheIf || opts.cacheIf(value)))
        memo.set(path, {at:Date.now(), value});
      return value;
    } finally { if (cacheWrites.get(path) === write) cacheWrites.delete(path); }
  }
  const running = inflight.get(path);
  if (running) return running;
  const write = {};
  cacheWrites.set(path, write);
  const task = api(path, opts).then(value => {
    // opts.cacheIf позволяет не запоминать неполный ответ: иначе страница
    // могла «залипнуть» пустой на весь срок кэша.
    if (inflight.get(path) === task && cacheWrites.get(path) === write && (!opts.cacheIf || opts.cacheIf(value)))
      memo.set(path, { at: Date.now(), value });
    return value;
  }).finally(() => { if (inflight.get(path) === task) inflight.delete(path); if (cacheWrites.get(path) === write) cacheWrites.delete(path); });
  inflight.set(path, task);
  return task;
}
function dropCache(prefix = '') {
  memoRevision++;
  for (const key of [...memo.keys()]) if (!prefix || key.startsWith(prefix)) memo.delete(key);
  // A request already in flight must not satisfy a forced retry or repopulate
  // the cache after the caller invalidates it.
  for (const key of [...inflight.keys()]) if (!prefix || key.startsWith(prefix)) inflight.delete(key);
  for (const key of [...cacheWrites.keys()]) if (!prefix || key.startsWith(prefix)) cacheWrites.delete(key);
}

/* ------------------------------------------------------------- утилиты UI */
const $ = id => document.getElementById(id);
const el = (tag, cls, html) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html != null) node.innerHTML = html;
  return node;
};
const icon = (name, cls = 'ic') =>
  `<svg class="${cls}"><use href="#i-${name}"/></svg>`;

/* Заглушка обложки прозрачная: цвет подложки даёт сама карточка, поэтому
   на светлой теме больше не появляется тёмно-синий квадрат. */
/* Заглушка обложки — прозрачный квадрат: сам значок рисует CSS по классу
   `ph` (см. app.css и css/sketch.css). Раньше серый цвет значка был зашит
   в картинку, и на бумажной теме он оставался пыльно-серым. */
const PLACEHOLDER =
  'data:image/svg+xml;utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"></svg>');

/* Обложки из выдачи приходят маленькими: YouTube отдаёт кадр 320×180, а
   SoundCloud — квадрат 100×100. В списке это незаметно, но на большой
   карточке и на диске картинка расплывается. Здесь ссылка переписывается на
   версию нужного размера, а если такой версии у источника нет, браузер
   спокойно откатывается на следующую по списку. */
function coverVariants(url, size = 600) {
  const src = String(url || '');
  if (!src || src.startsWith('data:')) return src ? [src] : [];
  const out = [];
  const push = value => { if (value && !out.includes(value)) out.push(value); };

  // YouTube: maxres есть не у всех видео, hq720 и sd — почти у всех.
  const yt = src.match(/i\.ytimg\.com\/vi(?:_webp)?\/([\w-]{6,})\//);
  if (yt) {
    const ext = /\.webp/.test(src) ? 'webp' : 'jpg';
    const base = src.slice(0, src.lastIndexOf('/') + 1);
    const names = size >= 900 ? ['maxresdefault', 'hq720', 'sddefault', 'hqdefault']
                : size >= 480 ? ['hq720', 'sddefault', 'maxresdefault', 'hqdefault']
                : ['hqdefault', 'mqdefault'];
    names.forEach(name => push(base + name + '.' + ext));
    push(src);
    return out;
  }
  // YouTube Music / Google: размер прямо в ссылке.
  if (/googleusercontent\.com|ggpht\.com|lh3\./.test(src) && /=w\d+-h\d+/.test(src)) {
    push(src.replace(/=w\d+-h\d+[^/]*$/, `=w${size}-h${size}-l95-rj`));
    push(src);
    return out;
  }
  // SoundCloud: -large (100px) → -t500x500 / -original.
  if (/sndcdn\.com/.test(src)) {
    push(src.replace(/-(?:large|t\d+x\d+|crop|badge|small|tiny|mini|t67x67)\.(jpg|png)/,
                     size >= 900 ? '-t1080x1080.$1' : '-t500x500.$1'));
    push(src.replace(/-(?:large|t\d+x\d+|crop)\.(jpg|png)/, '-t500x500.$1'));
    push(src);
    return out;
  }
  // iTunes / Apple: 100x100bb → нужный размер.
  if (/mzstatic\.com/.test(src)) {
    push(src.replace(/\/\d+x\d+(bb)?\.(jpg|png)$/, `/${size}x${size}$1.$2`));
    push(src);
    return out;
  }
  // Deezer: /56x56-000000-80-0-0.jpg и подобное.
  if (/dzcdn\.net|deezer/.test(src)) {
    push(src.replace(/\/\d+x\d+(-[\w-]*)?\.(jpg|png)/, `/${size}x${size}$1.$2`));
    push(src);
    return out;
  }
  // Cover Art Archive: -250 / -500 / -1200.
  if (/coverartarchive\.org/.test(src)) {
    push(src.replace(/-(?:250|500|1200)\.(jpg|png)/, size >= 900 ? '-1200.$1' : '-500.$1'));
    push(src);
    return out;
  }
  push(src);
  return out;
}

/* Насколько крупную версию просить: зависит от настройки и от экрана. */
function coverSize(base = 300) {
  const mode = S.coverQuality || 'high';
  const dpr = Math.min(devicePixelRatio || 1, 2);
  const k = mode === 'max' ? 2.2 : mode === 'normal' ? 1 : 1.6;
  const want = Math.round(base * k * dpr);
  return want >= 1000 ? 1200 : want >= 700 ? 800 : want >= 450 ? 600 : 320;
}

function hiRes(url, base = 300) {
  return coverVariants(url, coverSize(base))[0] || '';
}

/* Крупные обложки грузим сразу: плеер на весь экран, «Диск» и мини-плеер
   скрыты до открытия, а ленивой картинке в скрытом блоке браузер просто не
   даёт загрузиться — поэтому в караоке оставался пустой квадрат. */
const EAGER_ART = new Set(['nArt', 'pArt', 'discArt', 'nowArtBg', 'miniArt']);

function setImg(node, src, base = 160) {
  node.loading = EAGER_ART.has(node.id) || base >= 300 ? 'eager' : 'lazy';
  node.decoding = 'async';
  const direct = coverVariants(src, coverSize(base));
  const list = [...direct];
  // pywebview/Windows can sporadically reject direct CDN loads (especially
  // yt3.ggpht author avatars). Retry through the local allow-listed endpoint.
  direct.forEach(url => {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (/(^|\.)((ytimg|ggpht|googleusercontent)\.com)$/.test(host)) {
        list.push('/api/image/youtube?url=' + encodeURIComponent(url));
      }
    } catch (_) { /* data/local/invalid URLs use the normal fallback path */ }
  });
  // Класс `ph` помечает заглушку: темам нужно знать, что обложки нет, —
  // рисованная тема перекрашивает её под свои чернила.
  if (!list.length) {
    node.onerror = null; node.classList.add('ph'); node.src = PLACEHOLDER; return;
  }
  let at = 0;
  node.classList.remove('ph');
  node.onerror = () => {
    at += 1;
    if (at < list.length) { node.src = list[at]; return; }
    node.onerror = null;
    node.classList.add('ph');
    node.src = PLACEHOLDER;
  };
  node.src = list[0];
}

function fmt(sec) {
  if (!sec && sec !== 0) return '--:--';
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
           : `${m}:${String(s).padStart(2, '0')}`;
}

let toastTimer;
/* Имя плейлиста по умолчанию создаётся сервером при первом запуске и
   хранится в базе как данные. Показываем его на языке интерфейса, пока
   пользователь его не переименовал. */
const DEFAULT_PLAYLIST_NAMES = ['Мне нравится', 'Liked songs'];
function plName(name) {
  return DEFAULT_PLAYLIST_NAMES.includes(name) ? t('Liked songs') : name;
}

function toast(message, ms) {
  const node = $('toast');
  node.textContent = message;
  node.onclick = null;
  node.classList.remove('act');
  node.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('on'), ms || 2600);
}

/* Тост, по которому можно щёлкнуть (например, «открыть папку»). */
function toastAction(message, fn, ms) {
  toast(message, ms || 5000);
  const node = $('toast');
  node.classList.add('act');
  node.onclick = () => { node.classList.remove('on'); node.onclick = null; fn(); };
}

/* Artwork is exported losslessly as PNG, only after a Save As choice. */
async function saveCover(url, name, label='Cover artwork') {
  const src=String(url||'');
  if(!src){toast(t('There is no cover here'));return null;}
  let urls=coverVariants(src,1200);
  const proxied=src.match(/\/api\/image\/youtube\?url=([^&]+)/);
  if(proxied){try{urls=coverVariants(decodeURIComponent(proxied[1]),1200).concat(urls);}catch{}}
  if(!urls.includes(src))urls.push(src);
  return FileSave27.save({kind:'cover',name:FileSave27.name([name,t(label)].filter(Boolean).join(' — '),'.png'),urls:[...new Set(urls)].slice(0,12)});
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

/* ----------------------------------------------------- модалки и панели */
function openModal(id) {
  document.querySelectorAll('.modal.on').forEach(m => m.classList.remove('on'));
  $(id).classList.add('on');
  $('veil').classList.add('on');
  syncMotion40();
}
function closeModals() {
  document.querySelectorAll('.modal.on').forEach(m => m.classList.remove('on'));
  $('queue').classList.remove('on');
  $('veil').classList.remove('on');
  // Проба трека не должна играть из закрытого окна.
  if (typeof Finder !== 'undefined' && Finder.close) Finder.close();
  hideMenu();
  syncMotion40();
}

/* -------------------------------------------------- контекстное меню */
// v73: a menu opened from a button is anchored to that button and never covers
// it (opens above or below, scrolls inside when the window is short). A
// right-click menu opens at the pointer and flips instead of sliding over it.
// Keyboard: arrows / Home / End move, Esc closes and returns focus.
const Menu73 = { anchor: null, point: null, back: null, press: { x: -1, y: -1, t: 0, el: null, ctx: false }, mo: null };
addEventListener('pointerdown', e => { Menu73.press = { x: e.clientX, y: e.clientY, t: performance.now(), el: e.target, ctx: e.button === 2 }; }, true);
addEventListener('contextmenu', e => { Menu73.press = { x: e.clientX, y: e.clientY, t: performance.now(), el: e.target, ctx: true }; }, true);
function menuAnchor73(x, y) {
  const p = Menu73.press, near = performance.now() - p.t < 2000 && Math.abs(p.x - x) < 4 && Math.abs(p.y - y) < 4;
  let node = null;
  if (near) { if (p.ctx) return null; node = p.el; }
  else if (!x && !y) node = document.activeElement;   // keyboard activation reports 0,0
  const anchor = node && node.closest ? node.closest('button,[role="button"],a,.ib') : null;
  return anchor && !anchor.closest('#ctxMenu') ? anchor : null;
}
function placeMenu73() {
  const menu = $('ctxMenu');
  if (!menu || !menu.classList.contains('on')) return;
  const pad = 10, gap = 6, vw = innerWidth, vh = innerHeight;
  menu.style.maxHeight = '';
  // Layout sizes, not getBoundingClientRect(): the open animation scales the menu.
  let z = 1;
  for (let node = menu; node && node.nodeType === 1; node = node.parentElement) z *= parseFloat(getComputedStyle(node).zoom) || 1;
  const w = menu.offsetWidth * z, natural = (menu.scrollHeight + menu.offsetHeight - menu.clientHeight) * z;
  const anchor = Menu73.anchor && Menu73.anchor.isConnected ? Menu73.anchor : null;
  const a = anchor ? anchor.getBoundingClientRect() : null;
  let left, top, room, up, end;
  if (a && (a.width || a.height)) {
    const above = a.top - gap - pad, below = vh - a.bottom - gap - pad;
    up = a.top + a.height / 2 > vh / 2 ? (natural <= above || above >= below) : !(natural <= below || below >= above);
    room = Math.max(96, up ? above : below);
    top = up ? a.top - gap - Math.min(natural, room) : a.bottom + gap;
    end = a.left + a.width / 2 > vw / 2;
    left = end ? a.right - w : a.left;
  } else {
    const p = Menu73.point || { x: 0, y: 0 }, below = vh - p.y - pad, above = p.y - pad;
    up = natural > below && above > below;
    room = Math.max(96, up ? above : below);
    top = up ? p.y - Math.min(natural, room) : p.y;
    end = p.x + w > vw - pad && p.x - w >= pad;
    left = end ? p.x - w : p.x;
  }
  const h = Math.min(natural, room);
  left = Math.max(pad, Math.min(left, vw - w - pad));
  top = Math.max(pad, Math.min(top, vh - pad - h));
  menu.style.maxHeight = Math.floor(room / z) + 'px';
  menu.style.left = left / z + 'px';
  menu.style.top = top / z + 'px';
  menu.style.transformOrigin = (up ? 'bottom ' : 'top ') + (end ? 'right' : 'left');
  menu.dataset.side73 = up ? 'up' : 'down';
}
function showMenu(x, y, items) {
  guardMenu();
  if(typeof S!=='undefined' && S.lang && LANG!==S.lang)setLang(S.lang,false);
  const menu = $('ctxMenu');
  const anchor = menuAnchor73(x, y);
  Menu73.anchor = anchor; Menu73.point = { x, y };
  Menu73.back = anchor || (document.activeElement !== document.body ? document.activeElement : null);
  menu.innerHTML = '';
  menu.setAttribute('role', 'menu');
  items.forEach(item => {
    if (item === '-') { menu.appendChild(el('hr')); return; }
    const btn = el('button', item.danger ? 'danger' : '',
      `${item.icon ? icon(item.icon, 'ic s') : ''}<span>${item.label}</span>`);
    btn.setAttribute('role', 'menuitem');
    btn.onclick = () => { hideMenu(); item.action(); };
    menu.appendChild(btn);
  });
  translateDom(menu);
  if (anchor) anchor.setAttribute('aria-expanded', 'true');
  menu.classList.add('on');
  placeMenu73();
  // Extensions append actions synchronously after showMenu returns.
  requestAnimationFrame(placeMenu73);
  if (!Menu73.mo) {
    Menu73.mo = new MutationObserver(() => {
      menu.querySelectorAll('button:not([role])').forEach(b => b.setAttribute('role', 'menuitem'));
      requestAnimationFrame(placeMenu73);
    });
    Menu73.mo.observe(menu, { childList: true });
    menu.addEventListener('keydown', menuKeys73);
    addEventListener('resize', () => requestAnimationFrame(placeMenu73));
  }
  if (!x && !y || (anchor && anchor.matches(':focus-visible'))) requestAnimationFrame(() => menu.querySelector('button')?.focus({ preventScroll: true }));
}
function menuKeys73(e) {
  const menu = $('ctxMenu'), items = [...menu.querySelectorAll('button:not([disabled])')];
  if (!items.length) return;
  const i = items.indexOf(document.activeElement), n = items.length;
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const j = i < 0 ? (e.key === 'ArrowDown' ? 0 : n - 1) : (i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n;
    items[j].focus({ preventScroll: false });
  } else if (e.key === 'Home' || e.key === 'End') {
    e.preventDefault(); items[e.key === 'Home' ? 0 : n - 1].focus();
  } else if (e.key === 'Escape') {
    e.preventDefault(); e.stopPropagation(); hideMenu(true);
  } else if (e.key === 'Tab') hideMenu();
}
function hideMenu(restore) {
  const menu = $('ctxMenu');
  const wasOn = menu.classList.contains('on');
  menu.classList.remove('on');
  if (Menu73.anchor) Menu73.anchor.removeAttribute('aria-expanded');
  const back = Menu73.back; Menu73.anchor = null;
  if (wasOn && back && back.isConnected && (restore === true || menu.contains(document.activeElement))) back.focus({ preventScroll: true });
}

/* ------------------------------------------------------ лайки/плейлисты */
async function refreshLikes() {
  try {
    const data = await api('/api/likes');
    K.likes = new Set(data.ids || []);
    K.likedTracks = data.items || [];
    if (K.view === 'lib') Views.renderLibrary();
  } catch { /* локальный сервер ещё поднимается */ }
}

async function toggleLike(track) {
  const liked = (await api('/api/likes', { method: 'POST', body: { track } })).liked;
  if (liked) K.likes.add(track.id); else K.likes.delete(track.id);
  toast(liked ? t('Added to Liked') : t('Removed from Liked'));
  document.querySelectorAll(`[data-like="${CSS.escape(track.id)}"]`)
    .forEach(node => node.classList.toggle('on', liked));
  if (Player.current && Player.current.id === track.id) Player.paintLike();
  dropCache('/api/likes');
  return liked;
}

async function refreshPlaylists() {
  try {
    const data = await api('/api/playlists');
    K.playlists = data.items || [];
    Views.renderSidePlaylists();
    if (K.view === 'lib') Views.renderLibrary();
  } catch { /* сервер ещё не готов */ }
}

/* Активные библиотеки выбираются в настройках. */
const ALL_SOURCES = Object.keys(SOURCE_META);
function activeSources() {
  const list = (S.sources || []).filter(s => ALL_SOURCES.includes(s));
  return list.length ? list : ['youtube'];
}
const sourceName = src => (SOURCE_META[src] || {}).name || src || t('Source');
const sourceTag = src => (SOURCE_META[src] || {}).tag || '?';

/* Закрытие меню/панелей по клику вне них — с защитой от «клик открыл и сразу закрыл». */
let menuGuard = 0;
function guardMenu() { menuGuard = performance.now(); }
function menuJustOpened() { return performance.now() - menuGuard < 220; }

// Same vector geometry in every loading surface; no border-size centring drift.
function loadingIcon38(){return '<svg class="loading-glyph38" viewBox="0 0 24 24" aria-hidden="true" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" opacity=".22"/><g class="loading-arc38"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-dasharray="38 57"/></g></svg>';}

/* v40: hot-path DOM writes are idempotent; no observer churn for equal values. */
function paintText40(node, value) { if (node && node.textContent !== value) node.textContent = value; }
function paintAttr40(node, name, value) { if (node && node.getAttribute(name) !== value) node.setAttribute(name, value); }
function paintStyle40(node, name, value) { if (node && node.style[name] !== value) node.style[name] = value; }

// Modals pause decoration, not media playback. Coalesce close+open in one turn.
let motionFrame40 = 0;
function syncMotion40() {
  if (motionFrame40) return;
  motionFrame40 = requestAnimationFrame(() => {
    motionFrame40 = 0;
    const blocked = document.hidden || !!document.querySelector('.modal.on');
    if (typeof Karaoke !== 'undefined') {
      if (blocked) Karaoke.stop();
      else if ($('now')?.classList.contains('on')) Karaoke.start();
    }
    if (typeof Player !== 'undefined' && Player.audio) Player.wake42();
    if (typeof Atmo !== 'undefined') Atmo.kick();
    if (window.KMarquee?.visibility51) KMarquee.visibility51();
    if (typeof FluidCover24 !== 'undefined') FluidCover24.sync();
  });
}
