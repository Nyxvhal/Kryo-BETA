/* v70 «Polish»: calm OLED black-and-white defaults, legible accent buttons,
   a compact home header with onboarding, honest loading states, a lazy theme
   gallery and fault-tolerant module start-up. Loaded last; every hook wraps
   an existing function instead of replacing its behaviour. */
'use strict';
DEFAULTS.welcome70 = '';   // '' — onboarding may show for a new profile; 'done' — never again
DEFAULTS.region70 = '';    // '' — chart region follows the interface language (server side)
// "Reset appearance" returns to the v70 look: the palette follows the theme
// (OLED black by default) instead of the blue-grey graphite palette.
if (typeof UI52 !== 'undefined' && UI52.defaults) Object.assign(UI52.defaults, { palette: 'theme', accent: '#ffffff' });

const Polish70 = {
 ready: false,
 reported: new Set(),
 // Chart regions offered by YouTube Music. ZZ = worldwide.
 regions: ['AR','AT','AU','BE','BG','BO','BR','CA','CH','CL','CO','CR','CZ','DE','DK','DO','EC','EE','EG','ES','FI','FR','GB','GT','HN','HU','IE','IL','IN','IS','IT','JP','KE','KR','LU','MX','NG','NI','NL','NO','NZ','PA','PE','PL','PT','PY','RO','RS','RU','SA','SE','SV','TR','TZ','UA','UG','US','UY','ZA','ZW'],

 /* ------------------------------------------------------------ colour */
 rgb(value) {
  const v = String(value || '').trim();
  if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(v)) return hex2rgb(v);
  const m = v.match(/rgba?\(([^)]+)\)/i);
  if (m) { const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); if (p.length >= 3 && p.slice(0, 3).every(Number.isFinite)) return p.slice(0, 3); }
  return null;
 },
 lum(rgb) { const f = v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }; return .2126 * f(rgb[0]) + .7152 * f(rgb[1]) + .0722 * f(rgb[2]); },
 /* Text on accent-filled buttons follows the real accent. A white OLED accent
    used to get white text (design-v48 forced #f7f8fc inside Clips). */
 ink() {
  try {
   const root = document.documentElement, css = getComputedStyle(root);
   const a = this.rgb(css.getPropertyValue('--accent')) || this.rgb(S.accent) || [255, 255, 255];
   const b = this.rgb(css.getPropertyValue('--accent-2')) || a;
   const light = (this.lum(a) + this.lum(b)) / 2 > .179;   // WCAG crossover for black vs white text
   const ink = light ? '#0b0b0d' : '#ffffff';
   for (const name of ['--on-accent70', '--accent-ink', '--u52-ink']) root.style.setProperty(name, ink);
   root.style.setProperty('--clip-ink45', light ? '#000' : '#fff');
   document.body.classList.toggle('accent-light70', light);
   document.body.classList.toggle('oled70', S.theme === 'oled' || /^#0{3}(0{3})?$/i.test(String(S.bg || '')));
  } catch (e) { this.report(e, 'ink'); }
 },

 /* ------------------------------------------------ two-language helpers */
 // Older modules return English for every language except Russian. Fall back
 // to the shared dictionary so Ukrainian, German, Japanese… get translations
 // wherever the English key exists.
 locales() {
  const names = ['Design48', 'UI52', 'UI53', 'Video57', 'Wave61', 'Classic63'];
  for (const name of names) {
   const obj = this.lookup(name);
   if (obj && typeof obj.tr === 'function') obj.tr = function (en, ru) { return LANG === 'ru' && ru !== undefined ? ru : t(en); };
  }
  for (const name of ['Watch58', 'Experience66']) {
   const obj = this.lookup(name);
   if (obj && typeof obj.t === 'function') obj.t = function (en, ru) { return LANG === 'ru' && ru !== undefined ? ru : t(en); };
  }
 },
 lookup(name) { try { return Function('return typeof ' + name + "!=='undefined'?" + name + ':null')(); } catch { return null; } },

 /* -------------------------------------------- fault-tolerant start-up */
 // One broken module used to reject the whole boot chain: the splash stayed
 // with "Some parts did not load". Each module now starts in isolation.
 guard() {
  const names = ['Interface22', 'AlbumFlow23', 'ReferenceScene24', 'SearchDiscovery26', 'Upgrade30', 'Home31', 'Visualizer32', 'Repair33', 'UI38', 'TikTokFinder39', 'Repair34', 'Interface45', 'Scene46', 'Performance47', 'Design48', 'Transfer48', 'Search48', 'Connections49', 'Personal50', 'Video57', 'Watch58', 'Brand60', 'Wave61', 'ClipsMenu63', 'Classic63', 'Locale64', 'Customize64', 'Share64', 'Experience66', 'Clips69'];
  for (const name of names) {
   const obj = this.lookup(name);
   if (!obj || typeof obj.init !== 'function' || obj.init.guarded70) continue;
   const init = obj.init;
   const safe = function (...a) {
    try {
     const r = init.apply(this, a);
     return r && typeof r.then === 'function' ? r.catch(e => Polish70.fail(name, e)) : r;
    } catch (e) { Polish70.fail(name, e); }
   };
   safe.guarded70 = true;
   obj.init = safe;
  }
 },
 fail(name, error) {
  console.error('[boot] ' + name + ' failed', error);
  this.report(error, 'init:' + name);
 },
 report(error, where) {
  try {
   const message = String(error && (error.message || error.reason || error) || '').slice(0, 300);
   if (!message || /ResizeObserver loop|AbortError|The user aborted|NotAllowedError/i.test(message)) return;
   const key = where + '|' + message;
   if (this.reported.has(key) || this.reported.size > 30) return;
   this.reported.add(key);
   fetch('/api/client-error', { method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
    body: JSON.stringify({ message, source: String(where || '').slice(0, 160), stack: String(error && error.stack || '').slice(0, 700) }) }).catch(() => {});
  } catch { /* reporting must never throw */ }
 },
 listen() {
  addEventListener('error', e => { if (e && e.message) this.report(e.error || e.message, (e.filename || '').replace(location.origin, '') + ':' + (e.lineno || 0)); });
  addEventListener('unhandledrejection', e => this.report(e && e.reason, 'promise'));
 },

 /* ------------------------------------------------------- navigation */
 nav() {
  const go = App.go.bind(App);
  App.go = (view, ...a) => {
   const r = go(view, ...a);
   try {
    if (view !== 'search') {
     // Search history must not hang over the next screen when navigation
     // happens from the keyboard or from code while the field has focus.
     if (typeof Hints !== 'undefined' && Hints.open) Hints.hide();
     if (document.activeElement === $('q')) $('q').blur();
    }
    if (view === 'home') this.greet();
   } catch (e) { this.report(e, 'nav'); }
   return r;
  };
  if (typeof Workspace !== 'undefined' && typeof Workspace.onNavigate === 'function') {
   const nav = Workspace.onNavigate.bind(Workspace);
   Workspace.onNavigate = (view, ...a) => {
    const r = nav(view, ...a);
    if (view === 'home' && $('workspaceLocation')) $('workspaceLocation').textContent = t('Recommendations');
    return r;
   };
   if (K.view === 'home' && $('workspaceLocation')) $('workspaceLocation').textContent = t('Recommendations');
  }
 },

 /* ------------------------------------------------------------- home */
 greet() {
  const kicker = document.querySelector('#homeHead31 .home-kicker31');
  if (!kicker) return;
  const h = new Date().getHours();
  kicker.textContent = t(h < 5 ? 'Good night' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening');
 },
 home() {
  const filter = $('homeFilter31'), head = $('homeHead31');
  if (!filter || !head || $('homeBar70')) return;
  document.body.classList.add('ui-v70');
  const bar = el('div', 'home-bar70'); bar.id = 'homeBar70';
  const start = el('div', 'home-bar70-group'), end = el('div', 'home-bar70-group home-bar70-end');
  const source = el('div', 'home-source70'); source.id = 'homeSourceBox70';
  for (const id of ['homeKinds38', 'personal50Home']) if ($(id)) start.append($(id));
  if ($('recommendToggle66')) end.append($('recommendToggle66'));
  for (const id of ['homeSourceLabel31', 'homeSource31']) if ($(id)) source.append($(id));
  end.append(source);
  bar.append(start, end);
  filter.prepend(bar);
  if ($('homeStatus31') && $('homeCount31')) $('homeCount31').after($('homeStatus31'));
  // One clear import entry instead of two competing buttons.
  const actions = head.querySelector('.home-actions31');
  if (actions && !$('homeImport70')) {
   const b = el('button', 'btn g', icon('import', 'ic s') + '<span></span>');
   b.id = 'homeImport70'; b.type = 'button';
   b.onclick = () => (typeof Connections49 !== 'undefined' ? Connections49.open() : (Workspace.openSettings(), App.openPane('importPane')));
   actions.append(b);
  }
  this.welcomeBox();
  const cats = $('homeCategories33');
  if (cats) {
   const edge = () => cats.classList.toggle('end70', cats.scrollLeft + cats.clientWidth >= cats.scrollWidth - 4);
   cats.addEventListener('scroll', edge, { passive: true });
   new ResizeObserver(edge).observe(cats);
   cats.addEventListener('wheel', e => {
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && cats.scrollWidth > cats.clientWidth) { cats.scrollLeft += e.deltaY; e.preventDefault(); }
   }, { passive: false });
  }
  const receive = Home31.receive.bind(Home31);
  Home31.receive = data => { const r = receive(data); this.welcome(); return r; };
  const render = Home31.render.bind(Home31);
  Home31.render = (...a) => { const r = render(...a); this.afterRender(); return r; };
  const load = Home31.load.bind(Home31);
  Home31.load = (force, ...a) => {
   if (!Home31.busy) this.skeleton();
   const p = load(force, ...a);
   Promise.resolve(p).finally(() => { if ($('rows')?.querySelector('.skel70') && !Home31.busy && !Home31.data?.refreshing) Home31.render(); });
   return p;
  };
  if (typeof Personal50 !== 'undefined') {
   const ph = Personal50.home.bind(Personal50);
   Personal50.home = (...a) => { const r = ph(...a); this.welcome(); return r; };
   const pr = Personal50.render.bind(Personal50);
   Personal50.render = (...a) => { const r = pr(...a); this.region(); return r; };
  }
  this.labels(); this.greet(); this.welcome(); this.afterRender(); this.region();
 },
 welcomeBox() {
  if ($('homeWelcome70')) return;
  const box = el('section', 'home-welcome70'); box.id = 'homeWelcome70'; box.hidden = true; box.dataset.noI18n = '';
  box.setAttribute('aria-labelledby', 'homeWelcomeTitle70');
  box.innerHTML = '<div class="home-welcome70-mark" aria-hidden="true">' + icon('spark') + '</div><div class="home-welcome70-copy"><h2 id="homeWelcomeTitle70"></h2><p id="homeWelcomeText70"></p></div><div class="home-welcome70-actions"><button class="btn g" type="button" id="homeWelcomeImport70">' + icon('import', 'ic s') + '<span></span></button><button class="btn g" type="button" id="homeWelcomeTaste70">' + icon('user', 'ic s') + '<span></span></button><button class="ib" type="button" id="homeWelcomeClose70">' + icon('close') + '</button></div>';
  $('homeFilter31').prepend(box);
  $('homeWelcomeImport70').onclick = () => (typeof Connections49 !== 'undefined' ? Connections49.open() : (Workspace.openSettings(), App.openPane('importPane')));
  $('homeWelcomeTaste70').onclick = () => (typeof Personal50 !== 'undefined' ? Personal50.open() : (Workspace.openSettings(), App.openPane('profile50')));
  $('homeWelcomeClose70').onclick = () => { this.finish(); $('homeBar70')?.querySelector('button')?.focus(); };
 },
 finish() { if (S.welcome70 !== 'done') { S.welcome70 = 'done'; saveSettings(); } this.welcome(); },
 welcome() {
  const box = $('homeWelcome70');
  if (!box) return;
  const rows = Home31.data?.rows || [];
  const personal = (K.likes && K.likes.size > 0) || (typeof Personal50 !== 'undefined' && (Personal50.profiles || []).length > 0) || rows.some(r => r && ['continue', 'repeat70'].includes(r.id));
  if (personal && S.welcome70 !== 'done') { S.welcome70 = 'done'; saveSettings(); }
  box.hidden = S.welcome70 === 'done' || personal || !Home31.data;
 },
 labels() {
  const set = (id, text) => { const n = $(id); if (n) n.textContent = text; };
  const span = (id, text) => { const n = $(id)?.querySelector('span'); if (n) n.textContent = text; };
  span('homeImport70', t('Import'));
  $('homeImport70')?.setAttribute('title', t('Import playlists'));
  set('homeWelcomeTitle70', t('Welcome to Kryo'));
  set('homeWelcomeText70', t('Start with what the world is playing today. Every like, skip and replay tunes your next mix.'));
  span('homeWelcomeImport70', t('Import playlists'));
  span('homeWelcomeTaste70', t('Import listening history'));
  const close = $('homeWelcomeClose70');
  if (close) { close.title = t('Hide'); close.setAttribute('aria-label', t('Hide')); }
  if ($('workspaceLocation') && K.view === 'home') $('workspaceLocation').textContent = t('Recommendations');
  this.greet();
 },
 skeleton() {
  const box = $('rows');
  if (!box || box.querySelector('.track-shell30,.card,.skel70')) return;
  const frag = document.createDocumentFragment();
  for (let i = 0; i < 10; i++) { const s = el('div', 'skel70', '<i></i><b></b><b></b>'); s.setAttribute('aria-hidden', 'true'); frag.append(s); }
  box.replaceChildren(frag);
  box.setAttribute('aria-busy', 'true');
  box.setAttribute('aria-label', t('Loading recommendations…'));
 },
 afterRender() {
  try {
   const box = $('rows');
   if (!box) return;
   const items = Home31.filtered ? Home31.filtered() : [];
   // Keep the skeleton while the first selection is still being built:
   // "nothing to show" was misleading during the background refresh.
   if (!items.length && (Home31.busy || Home31.data?.refreshing) && !box.querySelector('.track-shell30,.card')) {
    box.replaceChildren(); this.skeleton();
   } else if (items.length || !Home31.busy) box.removeAttribute('aria-label');
   // A label repeated on every card ("A new discovery") carries no information.
   const informative = items.filter(x => x && x.recommend_reason && x.recommend_reason !== 'discovery').length;
   document.body.classList.toggle('quiet-reasons70', informative < Math.max(1, Math.round(items.length * .1)));
   $('homeCategories33')?.dispatchEvent(new Event('scroll'));
   // "Youtube" → "YouTube": service names keep their own spelling.
   const ops = [...($('homeSource31')?.options || [])];
   for (const op of ops) { const name = this.services[op.value]; if (name) op.textContent = name; }
   // One source for every card: its badge repeats the same word fifty times.
   document.body.classList.toggle('one-source70', ops.filter(o => o.value !== 'all').length <= 1);
  } catch (e) { this.report(e, 'home.render'); }
 },

 services: { youtube: 'YouTube', ytmusic: 'YouTube Music', soundcloud: 'SoundCloud', spotify: 'Spotify', deezer: 'Deezer', bandcamp: 'Bandcamp', audius: 'Audius', jamendo: 'Jamendo', mixcloud: 'Mixcloud', archive: 'Internet Archive', vk: 'VK', yandex: 'Yandex Music' },

 /* ----------------------------------------------------- chart region */
 region() {
  const pane = $('profilePane50');
  if (!pane) return;
  let box = $('region70');
  if (!box) {
   box = el('section', 'profile50-tune region70'); box.id = 'region70'; box.dataset.noI18n = '';
   const title = el('h3'); title.id = 'region70Title';
   const select = el('select'); select.id = 'region70Select'; select.setAttribute('aria-labelledby', 'region70Title');
   const note = el('p', 'profile50-note'); note.id = 'region70Note';
   select.onchange = async () => {
    const before = S.region70 || '';
    S.region70 = select.value;
    try {
     await saveSettings(true);
     dropCache('/api/recommend'); Home31.data = null;
     if (K.view === 'home') Home31.load(true);
    } catch { S.region70 = before; select.value = before; toast(t('Could not save')); }
   };
   box.append(title, select, note);
  }
  const select = $('region70Select') || box.querySelector('select');
  $('region70Title') && ($('region70Title').textContent = t('Chart region'));
  box.querySelector('#region70Note').textContent = t('Charts and fresh picks on Home follow this region.');
  let names = null;
  try { names = new Intl.DisplayNames([LANG, 'en'], { type: 'region' }); } catch { /* old engines */ }
  const name = code => { try { return names ? names.of(code) : code; } catch { return code; } };
  const options = [['', t('Automatic · by interface language')], ['ZZ', t('Worldwide')], ...this.regions.map(c => [c, name(c)]).sort((a, b) => a[1].localeCompare(b[1], LANG))];
  if (select.options.length !== options.length || select.dataset.lang70 !== LANG) {
   select.replaceChildren(...options.map(([v, label]) => new Option(label, v)));
   select.dataset.lang70 = LANG;
  }
  select.value = this.regions.includes(S.region70) || S.region70 === 'ZZ' ? S.region70 : '';
  const tune = pane.querySelector('.profile50-tune:not(.region70)');
  if (tune) tune.after(box); else pane.append(box);
 },

 /* Two settings tabs were added later without icons; the column looked broken. */
 navIcons() {
  for (const [pane, name] of [['layout48', 'expand'], ['profile50', 'heart']]) {
   const tab = document.querySelector('#setTabs [data-pane="' + pane + '"]');
   if (tab && !tab.querySelector('svg')) tab.insertAdjacentHTML('afterbegin', icon(name, 'ic s'));
  }
 },

 /* ---------------------------------------------------- theme gallery */
 // The gallery is ~3 500 nodes. It was rebuilt five times during start-up
 // although nobody was looking at it; now it is built when its pane is open.
 themes() {
  if (typeof Themes === 'undefined' || Themes.lazy70) return;
  const build = Themes.build.bind(Themes);
  Themes.lazy70 = true;
  Themes.build = function (...a) {
   const pane = document.querySelector('.pane[data-pane="themes"]');
   if (pane && !pane.classList.contains('on')) { this.dirty70 = true; return; }
   this.dirty70 = false;
   return build(...a);
  };
 },

 init() {
  if (this.ready) return;
  this.ready = true;
  document.body.classList.add('ui-v70');
  const steps = [['ink', () => this.ink()], ['nav', () => this.nav()], ['home', () => this.home()]];
  for (const [name, fn] of steps) { try { fn(); } catch (e) { this.fail('Polish70.' + name, e); } }
  const tokens = typeof Classic63 !== 'undefined' && Classic63.tokens ? Classic63.tokens.bind(Classic63) : null;
  if (tokens) Classic63.tokens = (...a) => { const r = tokens(...a); this.ink(); return r; };
  const lang = App.afterLangChange.bind(App);
  App.afterLangChange = (...a) => { const r = lang(...a); try { this.labels(); this.region(); this.navIcons(); } catch (e) { this.report(e, 'lang'); } return r; };
  const pane = App.openPane.bind(App);
  App.openPane = (...a) => { const r = pane(...a); try { this.navIcons(); } catch (e) { this.report(e, 'pane'); } return r; };
  try { this.navIcons(); } catch (e) { this.report(e, 'navIcons'); }
  addEventListener('kryonyx:coverpalette', () => this.ink());
 }
};

// Before boot: wrap helpers and module start-up.
Polish70.locales();
Polish70.guard();
Polish70.themes();
Polish70.listen();
{
 const theme70 = applyTheme;
 applyTheme = function (...a) { const r = theme70.apply(this, a); Polish70.ink(); return r; };
}
const boot70 = App.boot.bind(App);
App.boot = async function (...a) { await boot70(...a); try { Polish70.init(); } catch (e) { Polish70.fail('Polish70', e); } };
