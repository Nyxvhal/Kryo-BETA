/* v72: quick sound settings in the player bar. The quality you really hear
   (codec · bitrate · cache) is always visible; switching quality is applied to
   the current track at the same position, without a gap. Speed (with an
   optional natural pitch), crossfade and loudness normalisation sit in the
   same popover. */
'use strict';
DEFAULTS.playbackPitch72 = true;
const Sound72 = {
 ready: false, info: null, open: false, reloadToken: 0,
 MODES: [['best', 'Best quality', 'Highest bitrate the source offers'], ['balanced', 'Balanced quality', 'Up to 160 kbps'], ['data', 'Data saver mode', 'Up to 80 kbps']],
 SPEEDS: [0.75, 1, 1.25, 1.5, 2],
 t(en) { return typeof t === 'function' ? t(en) : en; },
 el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; },
 icon(name) { return KryoIcons60.create(name); },
 mode() { return ['best', 'balanced', 'data'].includes(S.audioQuality) ? S.audioQuality : 'best'; },

 init() {
  if (this.ready || typeof Player === 'undefined' || !Player.deck || !$('pRight')) return;
  this.ready = true;
  document.body.classList.add('sound-v72'); // not 'sound72': that is the popover's own class
  this.buildPill(); this.buildPanel(); this.hooks(); this.applyPitch(); this.labels(); this.paint();
 },

 /* ---------- Pill in the player bar */
 buildPill() {
  const b = this.el('button', 'q72'); b.id = 'pQuality72'; b.type = 'button'; b.dataset.noI18n = '';
  b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-expanded', 'false'); b.setAttribute('aria-controls', 'sound72');
  const codec = this.el('span', 'q72-codec'), rate = this.el('span', 'q72-rate');
  b.append(this.icon('mixer'), codec, rate);
  b.onclick = e => { e.stopPropagation(); this.toggle(!this.open); };
  $('pRight').insertBefore(b, $('volWrap'));
  this.pill = { b, codec, rate };
 },

 /* ---------- Popover */
 buildPanel() {
  const p = this.el('div', 'sound72'); p.id = 'sound72'; p.hidden = true; p.dataset.noI18n = '';
  p.setAttribute('role', 'dialog'); p.tabIndex = -1;
  const head = this.el('div', 'sound72-head'), title = this.el('strong'), close = this.el('button', 'sound72-x');
  close.type = 'button'; close.append(this.icon('close')); close.onclick = () => this.toggle(false);
  head.append(title, close);

  const qTitle = this.el('span', 'sound72-label'), modes = this.el('div', 'sound72-modes');
  modes.setAttribute('role', 'radiogroup');
  this.modeButtons = {};
  for (const [id] of this.MODES) {
   const m = this.el('button', 'sound72-mode'); m.type = 'button'; m.dataset.mode72 = id; m.setAttribute('role', 'radio');
   m.append(this.el('b'), this.el('small'));
   m.onclick = () => this.setMode(id);
   modes.append(m); this.modeButtons[id] = m;
  }
  modes.addEventListener('keydown', e => {
   if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
   e.preventDefault();
   const ids = this.MODES.map(x => x[0]), i = ids.indexOf(this.mode()), d = e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 1;
   const next = ids[(i + d + ids.length) % ids.length]; this.setMode(next); this.modeButtons[next].focus();
  });
  const now = this.el('p', 'sound72-now'); now.id = 'sound72Now'; now.setAttribute('aria-live', 'polite');

  const sTitle = this.el('span', 'sound72-label'), chips = this.el('div', 'sound72-chips');
  for (const v of this.SPEEDS) { const c = this.el('button', 'sound72-chip', v + '×'); c.type = 'button'; c.dataset.speed72 = v; c.onclick = () => this.setSpeed(v); chips.append(c); }
  const speedRow = this.el('label', 'sound72-range'), speedText = this.el('span'), speedOut = this.el('output'), speed = this.el('input');
  speed.type = 'range'; speed.id = 'sound72Speed'; speed.min = .5; speed.max = 2; speed.step = .05;
  speed.oninput = () => { speedOut.value = this.fmtSpeed(+speed.value); };
  speed.onchange = () => this.setSpeed(+speed.value);
  speedRow.append(speedText, speedOut, speed);
  const pitchRow = this.el('label', 'sound72-switch'), pitchText = this.el('span'), pitch = this.el('input');
  pitch.type = 'checkbox'; pitch.id = 'sound72Pitch'; pitch.setAttribute('role', 'switch');
  pitch.onchange = () => { S.playbackPitch72 = pitch.checked; saveSettings(); this.applyPitch(); };
  pitchRow.append(pitchText, pitch);

  const fadeRow = this.el('label', 'sound72-range'), fadeText = this.el('span'), fadeOut = this.el('output'), fade = this.el('input');
  fade.type = 'range'; fade.id = 'sound72Fade'; fade.min = 0; fade.max = 12; fade.step = 1;
  fade.oninput = () => { fadeOut.value = this.fmtFade(+fade.value); };
  fade.onchange = () => this.setFade(+fade.value);
  fadeRow.append(fadeText, fadeOut, fade);
  const normRow = this.el('label', 'sound72-switch'), normText = this.el('span'), norm = this.el('input');
  norm.type = 'checkbox'; norm.id = 'sound72Normalize'; norm.setAttribute('role', 'switch');
  norm.onchange = () => this.setNormalize(norm.checked);
  normRow.append(normText, norm);

  const more = this.el('button', 'sound72-more'); more.type = 'button';
  more.onclick = () => { this.toggle(false); try { Workspace.openSettings(); App.openPane('sound'); } catch { $('bSettings')?.click(); } };

  const sec = (...n) => { const s = this.el('section'); s.append(...n); return s; };
  p.append(head, sec(qTitle, modes, now), sec(sTitle, chips, speedRow, pitchRow), sec(fadeRow, normRow), more);
  document.body.append(p);
  this.panel = p;
  this.ui = { title, close, qTitle, now, sTitle, chips, speedRow, speedText, speedOut, speed, pitchRow, pitchText, pitch, fadeText, fadeOut, fade, normText, norm, more };
  document.addEventListener('pointerdown', e => { if (this.open && !p.contains(e.target) && !this.pill.b.contains(e.target)) this.toggle(false); }, true);
  p.addEventListener('keydown', e => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); this.toggle(false, true); } });
  addEventListener('resize', () => { if (this.open) this.place(); }, { passive: true });
 },
 toggle(on, focusBack) {
  on = !!on;
  if (on === this.open) return;
  this.open = on;
  this.pill.b.setAttribute('aria-expanded', String(on));
  this.pill.b.classList.toggle('on', on);
  if (on) {
   this.paint(); this.panel.hidden = false; this.place();
   this.panel.classList.remove('in'); void this.panel.offsetWidth; this.panel.classList.add('in');
   (this.modeButtons[this.mode()] || this.panel).focus({ preventScroll: true });
   this.refresh();
  } else {
   this.panel.classList.remove('in'); this.panel.hidden = true;
   if (focusBack) this.pill.b.focus({ preventScroll: true });
  }
 },
 place() {
  const p = this.panel, r = this.pill.b.getBoundingClientRect(), narrow = innerWidth <= 640 || !r.width;
  p.classList.toggle('sheet', narrow);
  if (narrow) { const bar = $('player')?.getBoundingClientRect(); p.style.right = '8px'; p.style.left = '8px'; p.style.bottom = Math.max(8, innerHeight - (bar?.top ?? innerHeight) + 8) + 'px'; return; }
  p.style.left = 'auto';
  p.style.right = Math.max(8, Math.round(innerWidth - r.right - 40)) + 'px';
  p.style.bottom = Math.max(8, Math.round(innerHeight - r.top + 10)) + 'px';
 },

 /* ---------- Quality */
 async setMode(mode) {
  if (!this.MODES.some(m => m[0] === mode)) return;
  if (mode === this.mode()) { this.paint(); return; }
  S.audioQuality = mode;
  if ($('audioQuality33')) $('audioQuality33').value = mode;
  try { Player._prefetchController30?.abort(); Player._prefetchKey30 = null; } catch {}
  this.paint(); this.status(this.t('Switching quality…'));
  try { await saveSettings(true); } catch {}
  const track = Player.current;
  if (!track) { this.refresh(); return; }
  try {
   const r = await api('/api/stream/requality', { method: 'POST', body: { id: track.id }, timeout: 10000 });
   if (r && r.reload && Player.current === track) await this.reloadCurrent(track);
   else this.status(this.t('This track is already saved at this quality or better — no data needed.'));
  } catch (e) { this.status(this.t('Could not switch quality') + ': ' + (e?.message || e)); }
  setTimeout(() => this.refresh(), 400);
 },
 once(node, events, ms) {
  return new Promise((done, fail) => {
   const list = events.split(' '), off = () => { clearTimeout(timer); for (const e of list) node.removeEventListener(e, on); node.removeEventListener('error', bad); };
   const on = () => { off(); done(); }, bad = () => { off(); fail(new Error(this.t('The stream could not be opened'))); };
   const timer = setTimeout(() => { off(); fail(new Error(this.t('Timed out'))); }, ms);
   for (const e of list) node.addEventListener(e, on); node.addEventListener('error', bad);
  });
 },
 // The new stream is prepared on the idle deck while the old one keeps
 // playing, aligned to the same moment, then a short crossfade swaps them.
 async reloadCurrent(track) {
  const P = Player, old = P.audio, token = ++this.reloadToken;
  if (!old || !track || P.current !== track) return;
  const next = P.deck[0] === old ? P.deck[1] : P.deck[0], playing = !old.paused && P.wantPlay;
  const stale = () => token !== this.reloadToken || P.current !== track || P.audio !== old;
  P.rest(next);
  next.preservesPitch = old.preservesPitch; next.playbackRate = old.playbackRate; next.volume = 0;
  this.status(this.t('Applying to the current track…'));
  try {
   next.src = P.streamUrl(track, false, true);
   await this.once(next, 'loadedmetadata', 20000);
   if (stale()) throw 0;
   try { next.currentTime = Math.max(0, old.currentTime + (playing ? .35 : 0)); } catch {}
   if (playing) {
    await Promise.all([next.play(), this.once(next, 'playing', 20000)]);
    if (stale()) throw 0;
    const drift = old.currentTime - next.currentTime;
    if (Math.abs(drift) > .12) { try { next.currentTime = old.currentTime + .03; } catch {} }
    P.audio = next; P.crossfade(old, next, .45);
   } else {
    await this.once(next, 'canplay', 20000);
    if (stale()) throw 0;
    try { next.currentTime = old.currentTime; } catch {}
    next.volume = S.volume / 100; P.audio = next; P.rest(old);
   }
   P.paintState(); P.paintTime(); P.paintBuffer?.();
   this.status(this.t('Quality applied to the current track.'));
  } catch (e) {
   if (P.audio !== next) P.rest(next);
   if (e) this.status(this.t('Could not switch quality') + ': ' + (e.message || e));
  }
 },
 async refresh() {
  const track = Player.current;
  if (!track) { this.info = null; this.paint(); return; }
  const id = track.id, dur = Player.realDuration?.() || track.duration || 0, ticket = this.infoTicket = (this.infoTicket || 0) + 1;
  try {
   const r = await api('/api/stream/info?' + new URLSearchParams({ id, dur: String(Math.round(dur || 0)) }), { timeout: 8000 });
   if (ticket !== this.infoTicket || Player.current?.id !== id) return;
   this.info = r; this.paint();
  } catch { if (ticket === this.infoTicket) { this.info = null; this.paint(); } }
 },
 status(text) { this.statusText = text; this.statusAt = Date.now(); this.paintNow(); },
 describe(info) {
  if (!info) return '';
  const parts = [];
  if (info.codec) parts.push(info.codec);
  if (info.kbps) parts.push((info.estimated ? '≈' : '') + info.kbps + ' ' + this.t('kbps'));
  if (info.cached) parts.push(this.t('cached on this device'));
  else if (info.live) parts.push(this.t('streaming now'));
  return parts.join(' · ');
 },

 /* ---------- Speed, pitch, crossfade, normalisation */
 fmtSpeed(v) { return (Math.round(v * 100) / 100) + '×'; },
 fmtFade(v) { return v > 0 ? v + ' ' + this.t('s') : this.t('Off'); },
 setSpeed(v) {
  v = Math.round(Math.max(.5, Math.min(2, Number(v) || 1)) * 100) / 100;
  S.playbackSpeed = v;
  for (const a of Player.deck) a.playbackRate = v;
  saveSettings();
  try { Karaoke.resync?.(); } catch {}
  this.paint();
 },
 applyPitch() {
  const keep = S.playbackPitch72 === false;
  for (const a of Player.deck || []) if (a.preservesPitch !== keep) a.preservesPitch = keep;
 },
 setFade(v) {
  S.fade = Math.max(0, Math.min(12, Math.round(Number(v) || 0)));
  if ($('sFade')) $('sFade').value = S.fade;
  if ($('vFade')) $('vFade').textContent = S.fade;
  saveSettings(); this.paint();
 },
 setNormalize(on) {
  S.normalize = !!on;
  document.querySelectorAll('[data-sw="normalize"]').forEach(n => n.classList.toggle('on', S.normalize));
  try { Player.ensureCtx(); Player.rebuild(); } catch {}
  saveSettings(); this.paint();
 },

 /* ---------- Hooks */
 hooks() {
  const P = Player, start = P.start.bind(P);
  P.start = (...a) => { const r = start(...a); this.applyPitch(); return r; };
  const load = P.load.bind(P);
  P.load = (...a) => { this.reloadToken++; this.info = null; this.statusText = ''; const r = load(...a); this.paint(); return r; };
  for (const deck of P.deck) {
   deck.addEventListener('playing', () => { if (deck !== P.audio) return; clearTimeout(this.infoTimer); this.infoTimer = setTimeout(() => this.refresh(), 700); });
   deck.addEventListener('ratechange', () => { if (deck === P.audio && this.open) this.paint(); });
  }
  // Settings → Sound changes keep the pill honest.
  addEventListener('kryonyx:settings-save', e => { if (e.detail === 'saved' && this.lastMode !== this.mode()) { this.lastMode = this.mode(); this.paint(); this.refresh(); } });
  const sync = App.syncSettingsUI?.bind(App);
  if (sync) App.syncSettingsUI = (...a) => { const r = sync(...a); this.paint(); return r; };
  const lang = App.afterLangChange.bind(App);
  App.afterLangChange = (...a) => { const r = lang(...a); this.labels(); return r; };
  if (typeof Workspace !== 'undefined' && Workspace.playerMenu) {
   const menu = Workspace.playerMenu.bind(Workspace);
   Workspace.playerMenu = event => {
    const original = window.showMenu;
    if (typeof original !== 'function') return menu(event);
    window.showMenu = (x, y, items) => original(x, y, [{ label: this.t('Sound & quality'), icon: 'mixer', action: () => setTimeout(() => this.toggle(true), 0) }, '-', ...items]);
    try { return menu(event); } finally { window.showMenu = original; }
   };
  }
  this.lastMode = this.mode();
 },

 /* ---------- Painting */
 labels() {
  if (!this.ui) return;
  const T = x => this.t(x), u = this.ui;
  u.title.textContent = T('Sound & quality');
  this.panel.setAttribute('aria-label', T('Sound & quality'));
  u.close.title = T('Close'); u.close.setAttribute('aria-label', T('Close'));
  u.qTitle.textContent = T('Audio quality');
  for (const [id, name, hint] of this.MODES) { const b = this.modeButtons[id]; b.firstChild.textContent = T(name); b.lastChild.textContent = T(hint); }
  u.sTitle.textContent = T('Playback speed');
  u.speedText.textContent = T('Exact speed');
  u.pitchText.textContent = T('Pitch follows speed');
  u.fadeText.textContent = T('Crossfade');
  u.normText.textContent = T('Normalize loudness');
  u.more.textContent = T('All sound settings');
  this.paint();
 },
 paint() {
  if (!this.ui) return;
  const u = this.ui, mode = this.mode(), info = this.info;
  for (const [id, b] of Object.entries(this.modeButtons)) { const on = id === mode; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; }
  const speed = +S.playbackSpeed || 1;
  for (const c of u.chips.children) c.setAttribute('aria-pressed', String(Math.abs(Number(c.dataset.speed72) - speed) < .001));
  if (document.activeElement !== u.speed) u.speed.value = speed;
  u.speedOut.value = this.fmtSpeed(speed);
  u.pitch.checked = S.playbackPitch72 !== false;
  const fade = Math.max(0, Math.min(12, Math.round(+S.fade || 0)));
  if (document.activeElement !== u.fade) u.fade.value = fade;
  u.fadeOut.value = this.fmtFade(fade);
  u.norm.checked = !!S.normalize;
  // Pill: what is really playing, or the selected mode before anything is known.
  const short = { best: 'HQ', balanced: '≤160', data: '≤80' }[mode];
  const codec = info?.codec || '';
  this.pill.codec.textContent = codec || (info?.kbps ? '' : short);
  this.pill.rate.textContent = info?.kbps ? String(info.kbps) : '';
  this.pill.b.classList.toggle('q72-known', !!(info?.codec || info?.kbps));
  this.pill.b.dataset.mode72 = mode;
  const label = this.t('Sound & quality') + ' · ' + this.t({ best: 'Best quality', balanced: 'Balanced quality', data: 'Data saver mode' }[mode]) + (info ? ' · ' + this.describe(info) : '');
  this.pill.b.title = label; this.pill.b.setAttribute('aria-label', label);
  this.paintNow();
 },
 paintNow() {
  if (!this.ui) return;
  const info = this.info, recent = this.statusText && Date.now() - (this.statusAt || 0) < 8000;
  let text = '';
  if (recent) text = this.statusText;
  else if (!Player.current) text = this.t('Nothing is playing');
  else if (info) {
   const d = this.describe(info);
   text = d ? this.t('Now') + ': ' + d : this.t('The source does not report its bitrate.');
   if (info.cached && info.satisfies && info.tier && info.tier !== this.mode()) text += ' — ' + this.t('saved at a higher quality, no data used');
  } else text = this.t('Checking the stream…');
  if (this.ui.now.textContent !== text) this.ui.now.textContent = text;
 }
};
const boot72s = App.boot.bind(App);
App.boot = async function (...a) { await boot72s(...a); try { Sound72.init(); } catch (e) { console.error('Sound72.init', e); } };
