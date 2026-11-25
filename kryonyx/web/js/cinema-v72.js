/* v72 «Cinema+»: the playback menu becomes a tabbed panel (video · screen ·
   colour · ambient · AI · keys). Video size previews while the slider is dragged
   and is applied on release with an eased resize (the menu glides with its
   button instead of jumping under the pointer mid-drag). Pitch follows the speed by default, and audio/video drift is
   corrected on the video clock, so the sound never wobbles. */
'use strict';
DEFAULTS.clipPitch72 = true;
DEFAULTS.clipAvOffset72 = 0;
DEFAULTS.clipAutoFocus72 = false;
DEFAULTS.clipFit72 = 'contain';
DEFAULTS.clipPicture72 = { brightness: 100, contrast: 100, saturation: 100 };
DEFAULTS.clipHideDelay72 = 2600;
const Cinema72 = {
 ready: false, tab: 'video', nudge: 0, sizeRaf: 0,
 SPEEDS: [0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2],
 TABS: [['video', 'play', 'Video'], ['screen', 'focus71', 'Screen'], ['color', 'palette', 'Colour'], ['ambient', 'image', 'Ambient'], ['ai', 'spark', 'AI'], ['keys', 'keyboard', 'Keys']],
 HIDE: [[1500], [2600], [4000], [8000], [0]],
 t(en) { return typeof t === 'function' ? t(en) : en; },
 el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; },
 reduced() { return matchMedia('(prefers-reduced-motion: reduce)').matches || document.body.classList.contains('reduce-motion'); },
 clamp(v, a, b) { return Math.max(a, Math.min(b, v)); },

 init() {
  if (this.ready || typeof Cinema71 === 'undefined' || !Cinema71.ready || !$('watchMenu58')) return;
  this.ready = true;
  this.root = $('clips'); this.stage = $('clipStage'); this.menu = $('watchMenu58'); this.video = Clips.video;
  this.root.classList.add('cx72'); document.body.classList.add('cinema72');
  const steps = [['menu', () => this.buildMenu()], ['video', () => this.buildVideo()], ['screen', () => this.buildScreen()], ['color', () => this.buildColor()], ['keys', () => this.buildKeys()], ['audio', () => this.audioHooks()], ['sync', () => this.sync()], ['hooks', () => this.hooks()]];
  for (const [name, fn] of steps) { try { fn(); } catch (e) { Cinema71.fail('Cinema72.' + name, e); } }
  this.select(this.tab, false); this.labels(); this.applyFit(); this.applyPicture();
 },

 /* ---------- Tabs */
 buildMenu() {
  const menu = this.menu, tabs = this.el('div', 'cx-tabs72'), pages = this.el('div', 'cx-pages72');
  tabs.setAttribute('role', 'tablist'); tabs.dataset.noI18n = '';
  this.tabs = {}; this.pages = {};
  this.TABS.forEach(([id, icon], index) => {
   const b = this.el('button', 'cx-tab72'); b.type = 'button'; b.id = 'cxTab72-' + id; b.dataset.tab72 = id; b.dataset.index72 = index;
   b.setAttribute('role', 'tab'); b.setAttribute('aria-controls', 'cxPage72-' + id);
   b.append(Cinema71.icon(icon), this.el('span'));
   b.onclick = () => this.select(id, true);
   tabs.append(b); this.tabs[id] = b;
   const page = this.el('div', 'cx-page72'); page.id = 'cxPage72-' + id; page.dataset.page72 = id;
   page.setAttribute('role', 'tabpanel'); page.setAttribute('aria-labelledby', b.id); page.hidden = true;
   pages.append(page); this.pages[id] = page;
  });
  tabs.addEventListener('keydown', e => {
   const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
   if (!keys.includes(e.key)) return;
   e.preventDefault();
   const ids = this.TABS.map(x => x[0]), i = ids.indexOf(this.tab);
   const next = e.key === 'Home' ? 0 : e.key === 'End' ? ids.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + ids.length) % ids.length;
   this.select(ids[next], true); this.tabs[ids[next]].focus();
  });
  for (const node of [...menu.children]) {
   if (node.matches('section.ambient-settings66')) this.pages.ambient.append(node);
   else if (node.matches('section.cx-focus-settings71')) this.pages.screen.append(node);
   else this.pages.video.append(node);
  }
  this.pages.ai.append(this.el('p', 'cx-note72 cx-ai-wait72'));
  menu.replaceChildren(tabs, pages); menu.classList.add('cx-menu72');
  this.tabBar = tabs; this.pageBox = pages;
  const W = Watch58, open = W.menu.bind(W);
  W.menu = state => {
   const was = W.menuOpen, r = open(state);
   if (state && !was) this.onOpen();
   if (!state) this.hidePreview();
   return r;
  };
 },
 select(id, user) {
  if (!this.pages[id]) id = 'video';
  const prev = this.tab, menu = this.menu, animate = user && prev !== id && !menu.hidden && !this.reduced();
  const from = animate ? menu.getBoundingClientRect().height : 0;
  this.tab = id;
  for (const [key, b] of Object.entries(this.tabs)) {
   const on = key === id;
   b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; this.pages[key].hidden = !on;
  }
  this.tabBar.style.setProperty('--cx-tab-i72', this.tabs[id].dataset.index72);
  if (id === 'ai' && typeof AI72 !== 'undefined') try { AI72.clipPage(this.pages.ai); } catch (e) { Cinema71.fail('AI72.clipPage', e); }
  if (id === 'screen') this.paintScreen();
  if (!animate) return;
  const to = menu.getBoundingClientRect().height;
  try {
   if (Math.abs(to - from) > 1) { this.heightAnim?.cancel(); this.heightAnim = menu.animate([{ height: from + 'px' }, { height: to + 'px' }], { duration: 240, easing: 'cubic-bezier(.2,.8,.2,1)' }); }
   this.pages[id].animate([{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 220, easing: 'cubic-bezier(.2,.8,.2,1)' });
  } catch {}
 },
 onOpen() { this.select(this.tab, false); this.paintSpeed(); this.paintScreen(); },

 /* ---------- Rows */
 row(cls, input, extra, tag = 'label') {
  const row = this.el(tag, 'cx-row72' + (cls ? ' ' + cls : '')), text = this.el('span'); row.dataset.noI18n = '';
  row.append(text); if (extra) row.append(extra); row.append(input);
  return { row, text };
 },
 switch(id) { const box = this.el('input', 'cx-switch72'); box.type = 'checkbox'; box.id = id; box.setAttribute('role', 'switch'); return box; },
 range(id, min, max, step) { const r = this.el('input'); r.type = 'range'; r.id = id; r.min = min; r.max = max; r.step = step; return r; },

 /* ---------- Video page: quality, speed, pitch, loop, A/V offset */
 buildVideo() {
  const page = this.pages.video, sel = $('clipSpeed');
  const have = new Set([...sel.options].map(o => Number(o.value)));
  for (const v of this.SPEEDS) if (!have.has(v)) {
   const o = new Option(v + '×', String(v)), after = [...sel.options].find(x => Number(x.value) > v);
   sel.insertBefore(o, after || null);
  }
  const saved = Number(S.clipSpeed);
  if (Number.isFinite(saved) && saved >= .25 && saved <= 2) this.option(saved);
  sel.addEventListener('change', () => this.paintSpeed());
  const speedRow = sel.closest('label');
  const fine = this.range('cxSpeedFine72', .25, 2, .05), fineOut = this.el('output');
  const fineRow = this.row('cx-range72', fine, fineOut);
  fine.oninput = () => { fineOut.value = this.fmtSpeed(+fine.value); };
  fine.onchange = () => this.setSpeed(+fine.value);
  const pitch = this.switch('cxPitch72'), pitchRow = this.row('cx-switch-row72', pitch);
  pitch.checked = S.clipPitch72 !== false;
  pitch.onchange = () => { S.clipPitch72 = pitch.checked; saveSettings(true); Clips.applyAudio(); this.paintSpeed(); };
  const pitchNote = this.el('p', 'cx-note72');
  const loop = this.switch('cxLoop72'), loopRow = this.row('cx-switch-row72', loop), source = $('clipLoop');
  loop.checked = !!source?.checked;
  loop.onchange = () => { if (!source) return; source.checked = loop.checked; source.dispatchEvent(new Event('change')); };
  source?.addEventListener('change', () => { loop.checked = source.checked; });
  const av = this.range('cxAvOffset72', -300, 300, 10), avOut = this.el('output'), avRow = this.row('cx-range72', av, avOut, 'div');
  av.value = this.offsetMs();
  av.oninput = () => { avOut.value = this.fmtOffset(+av.value); };
  av.onchange = () => { S.clipAvOffset72 = this.clamp(Math.round(+av.value / 10) * 10, -300, 300); saveSettings(true); this.paintSpeed(); Clips.syncAudio?.(true); };
  const avReset = this.el('button', 'cx-mini72'); avReset.type = 'button'; avReset.id = 'cxAvReset72';
  avReset.onclick = () => { S.clipAvOffset72 = 0; av.value = 0; saveSettings(true); this.paintSpeed(); Clips.syncAudio?.(true); };
  avRow.row.insertBefore(avReset, avOut);
  const anchor = $('watchHint58');
  if (speedRow) speedRow.after(fineRow.row, pitchRow.row, pitchNote, loopRow.row, avRow.row);
  else page.append(fineRow.row, pitchRow.row, pitchNote, loopRow.row, avRow.row);
  const quality = $('clipQuality')?.closest('label');
  if (quality && anchor) quality.after(anchor);
  this.ui = { fine, fineOut, fineRow, pitch, pitchRow, pitchNote, loop, loopRow, av, avOut, avRow, avReset };
  this.paintSpeed();
 },
 fmtSpeed(v) { return (Math.round(v * 100) / 100) + '×'; },
 fmtOffset(ms) { ms = Math.round(ms); return ms === 0 ? '0 ms' : (ms > 0 ? '+' : '−') + Math.abs(ms) + ' ms'; },
 offsetMs() { const v = Number(S.clipAvOffset72); return Number.isFinite(v) ? this.clamp(v, -300, 300) : 0; },
 rate() { return Number($('clipSpeed').value) || 1; },
 option(v) {
  const sel = $('clipSpeed'), value = String(v);
  for (const o of [...sel.options]) if (o.dataset.custom72 && o.value !== value) o.remove();
  if (![...sel.options].some(o => Number(o.value) === v)) {
   const o = new Option(this.fmtSpeed(v), value); o.dataset.custom72 = '';
   sel.insertBefore(o, [...sel.options].find(x => Number(x.value) > v) || null);
  }
  const match = [...sel.options].find(o => Number(o.value) === v);
  if (match) sel.value = match.value;
 },
 setSpeed(v, badge) {
  v = Math.round(this.clamp(Number(v) || 1, .25, 2) * 100) / 100;
  this.option(v);
  $('clipSpeed').dispatchEvent(new Event('change'));
  this.paintSpeed();
  if (badge) this.badge(this.fmtSpeed(v));
 },
 stepSpeed(dir) {
  const cur = this.rate(), grid = .25;
  const next = dir > 0 ? Math.floor((cur + 1e-6) / grid) * grid + grid : Math.ceil((cur - 1e-6) / grid) * grid - grid;
  this.setSpeed(next, true); Watch58.show();
 },
 paintSpeed() {
  if (!this.ui) return;
  const v = this.rate(), u = this.ui, busy = n => document.activeElement === n && n.matches(':active, :focus-visible');
  if (!busy(u.fine)) { u.fine.value = v; u.fineOut.value = this.fmtSpeed(v); }
  u.pitch.checked = S.clipPitch72 !== false;
  u.pitchNote.textContent = u.pitch.checked ? this.t('The voice gets higher when faster and lower when slower, like a record.') : this.t('The voice keeps its natural pitch at any speed.');
  const ms = this.offsetMs(); if (!busy(u.av)) { u.av.value = ms; u.avOut.value = this.fmtOffset(ms); } u.avReset.hidden = ms === 0;
  const split = !!Clips.job?.audio_url || !Clips.job;
  u.av.disabled = !split; u.avRow.row.classList.toggle('cx-disabled72', !split);
 },
 badge(text) {
  let b = $('cxBadge72');
  if (!b) { b = this.el('div'); b.id = 'cxBadge72'; b.setAttribute('aria-live', 'polite'); b.dataset.noI18n = ''; this.stage.append(b); }
  b.textContent = text; b.classList.remove('on'); void b.offsetWidth; b.classList.add('on');
  clearTimeout(this.badgeTimer); this.badgeTimer = setTimeout(() => b.classList.remove('on'), 900);
 },

 /* ---------- Screen page: size (preview + apply on release), auto mode, fit, hide delay */
 buildScreen() {
  const C = Cinema71, ui = C.sizeUi, page = this.pages.screen, section = page.querySelector('.cx-focus-settings71');
  const chips = this.el('div', 'cx-chips72 cx-size-chips72'); chips.setAttribute('role', 'group');
  for (const v of [70, 80, 90, 100]) { const b = this.el('button', 'cx-chip72', v + '%'); b.type = 'button'; b.dataset.size72 = v; b.onclick = () => this.setSize(v); chips.append(b); }
  const note = this.el('p', 'cx-note72 cx-size-note72');
  const enter = this.el('button', 'cx-mini72 cx-enter72'); enter.type = 'button'; enter.id = 'cxEnterFocus72';
  enter.onclick = () => { Watch58.menu(false); C.setFocus(true); };
  section.append(chips, note, enter);
  const input = ui.input;
  input.oninput = () => this.preview(+input.value);
  input.onchange = () => this.setSize(+input.value);
  input.addEventListener('blur', () => this.hidePreview());
  input.addEventListener('pointercancel', () => this.hidePreview());
  const frame = this.el('div'); frame.id = 'cx72SizePreview'; frame.setAttribute('aria-hidden', 'true'); frame.append(this.el('span'));
  this.stage.append(frame); this.frame = frame;

  const auto = this.switch('cxAutoFocus72'), autoRow = this.row('cx-switch-row72', auto);
  auto.checked = S.clipAutoFocus72 === true;
  auto.onchange = () => { S.clipAutoFocus72 = auto.checked; saveSettings(true); };
  const fitHead = this.el('span', 'cx-menu-title71 cx-fit-head72');
  const fit = this.el('div', 'cx-chips72 cx-fit72'); fit.setAttribute('role', 'radiogroup');
  for (const id of ['contain', 'cover']) { const b = this.el('button', 'cx-chip72'); b.type = 'button'; b.dataset.fit72 = id; b.setAttribute('role', 'radio'); b.onclick = () => { S.clipFit72 = id; saveSettings(true); this.applyFit(); }; fit.append(b); }
  const fitNote = this.el('p', 'cx-note72');
  const hide = this.el('select'); hide.id = 'cxHideDelay72';
  for (const [ms] of this.HIDE) hide.append(new Option('', String(ms)));
  const hideRow = this.row('', hide);
  hide.value = String(this.hideDelay());
  if (hide.value === '') hide.value = '2600';
  hide.onchange = () => { S.clipHideDelay72 = Number(hide.value); saveSettings(true); Watch58.show(); };
  const extra = this.el('section', 'cx-screen-more72');
  extra.append(autoRow.row, fitHead, fit, fitNote, hideRow.row);
  page.append(extra);
  this.screen = { chips, note, enter, auto, autoRow, fitHead, fit, fitNote, hide, hideRow };
  this.applied = C.size;
 },
 hideDelay() { const v = Number(S.clipHideDelay72); return Number.isFinite(v) && v >= 0 ? v : 2600; },
 sizeVisible() { return Cinema71.focus; },
 preview(v) {
  const C = Cinema71; v = this.clamp(Math.round(v), 60, 100);
  C.sizeUi.out.value = v + '%';
  this.paintChips(v);
  if (!this.sizeVisible()) return;
  this.root.style.setProperty('--cx-preview-size', String(v / 100));
  this.frame.firstChild.textContent = v + '%';
  this.root.classList.add('cx-previewing72');
 },
 hidePreview() { this.root?.classList.remove('cx-previewing72'); },
 setSize(v) {
  const C = Cinema71; v = this.clamp(Math.round(Number(v) || 90), 60, 100);
  const from = this.applied ?? C.size;
  C.size = v; this.applied = v; S.clipFocusSize71 = v; saveSettings(true);
  C.sizeUi.input.value = v; C.sizeUi.out.value = v + '%';
  this.hidePreview(); this.paintChips(v);
  this.tween(from, v);
 },
 tween(from, to) {
  const C = Cinema71, root = this.root;
  cancelAnimationFrame(this.sizeRaf); this.sizeRaf = 0;
  if (from === to || this.reduced() || !C.focus) { C.applySize(); return; }
  root.classList.add('cx-resizing72');
  const start = performance.now(), dur = 420;
  const step = now => {
   const k = Math.min(1, (now - start) / dur), e = 1 - Math.pow(1 - k, 3);
   root.style.setProperty('--cx-focus-size', ((from + (to - from) * e) / 100).toFixed(4));
   if (k < 1) this.sizeRaf = requestAnimationFrame(step);
   else { this.sizeRaf = 0; root.classList.remove('cx-resizing72'); C.applySize(); }
  };
  this.sizeRaf = requestAnimationFrame(step);
 },
 paintChips(v) { for (const b of this.screen?.chips.children || []) b.setAttribute('aria-pressed', String(Number(b.dataset.size72) === v)); },
 paintScreen() {
  if (!this.screen) return;
  const C = Cinema71, s = this.screen;
  this.paintChips(C.size);
  s.note.textContent = C.focus ? this.t('Drag to preview the frame; the size is applied when you release the slider.') : this.t('The size applies in viewing mode (T).');
  s.enter.hidden = C.focus; s.auto.checked = S.clipAutoFocus72 === true;
  const fit = S.clipFit72 === 'cover' ? 'cover' : 'contain';
  for (const b of s.fit.children) b.setAttribute('aria-checked', String(b.dataset.fit72 === fit));
  s.hide.value = String(this.hideDelay()); if (s.hide.value === '') s.hide.value = '2600';
 },
 applyFit() {
  const fit = S.clipFit72 === 'cover' ? 'cover' : 'contain';
  this.root.dataset.cxFit72 = fit; this.paintScreen();
 },

 /* ---------- Colour page */
 PICTURE: [['brightness', 'Brightness'], ['contrast', 'Contrast'], ['saturation', 'Saturation']],
 picture() {
  const p = S.clipPicture72 && typeof S.clipPicture72 === 'object' ? S.clipPicture72 : {};
  const num = v => Number.isFinite(Number(v)) ? this.clamp(Math.round(Number(v)), 50, 150) : 100;
  return { brightness: num(p.brightness), contrast: num(p.contrast), saturation: num(p.saturation) };
 },
 buildColor() {
  const page = this.pages.color, rows = {};
  for (const [key] of this.PICTURE) {
   const input = this.range('cxPic72-' + key, 50, 150, 1), out = this.el('output'), r = this.row('cx-range72', input, out);
   input.oninput = () => { const p = this.picture(); p[key] = +input.value; S.clipPicture72 = p; this.applyPicture(); };
   input.onchange = () => saveSettings(true);
   rows[key] = { input, out, ...r }; page.append(r.row);
  }
  const reset = this.el('button', 'cx-mini72 cx-reset72'); reset.type = 'button'; reset.id = 'cxPicReset72';
  reset.onclick = () => { S.clipPicture72 = { brightness: 100, contrast: 100, saturation: 100 }; saveSettings(true); this.applyPicture(); };
  const note = this.el('p', 'cx-note72');
  page.append(reset, note);
  this.color = { rows, reset, note };
 },
 applyPicture() {
  const p = this.picture(), plain = p.brightness === 100 && p.contrast === 100 && p.saturation === 100;
  this.root.classList.toggle('cx-picture72', !plain);
  if (plain) this.root.style.removeProperty('--cx-filter72');
  else this.root.style.setProperty('--cx-filter72', `brightness(${p.brightness / 100}) contrast(${p.contrast / 100}) saturate(${p.saturation / 100})`);
  if (!this.color) return;
  for (const [key, row] of Object.entries(this.color.rows)) { row.input.value = p[key]; row.out.value = p[key] + '%'; }
  this.color.reset.disabled = plain;
 },

 /* ---------- Keys page */
 KEYS: [['Space · K', 'Play / pause'], ['← / →', 'Back / forward 5 s'], ['J / L', 'Back / forward 10 s'], ['0 – 9', 'Jump to 0–90 %'], ['[ / ]', 'Slower / faster'], ['T', 'Viewing mode'], ['F', 'Fullscreen'], ['M', 'Mute'], ['N', 'Next video'], ['Esc', 'Exit viewing mode / close']],
 buildKeys() {
  const list = this.el('dl', 'cx-keys72');
  this.keyRows = this.KEYS.map(([keys]) => { const dt = this.el('dt'), dd = this.el('dd'); for (const part of keys.split(' ')) dt.append(/^[·/–]$/.test(part) ? this.el('i', '', part) : this.el('kbd', '', part)); list.append(dt, dd); return dd; });
  this.pages.keys.append(list);
 },

 /* ---------- Audio: pitch follows speed; drift corrected on the video clock */
 audioHooks() {
  const apply = Clips.applyAudio.bind(Clips);
  Clips.applyAudio = (...a) => {
   const r = apply(...a), keep = S.clipPitch72 === false;
   for (const m of [Clips.video, Clips.audio]) if (m && m.preservesPitch !== keep) m.preservesPitch = keep;
   return r;
  };
  Clips.applyAudio();
 },
 sync() {
  const C = this;
  Clips.syncAudio = function (force = false) {
   if (!this.job?.audio_url) return;
   const v = this.video, a = this.audio, base = Number($('clipSpeed').value) || 1, off = C.offsetMs() / 1000;
   if (a.readyState >= 1) {
    const target = Math.max(0, v.currentTime - off), drift = a.currentTime - target, size = Math.abs(drift);
    if (force || v.paused || size > .3) {
     if (size > (force ? .03 : .3)) try { a.currentTime = target; } catch {}
     if (v.playbackRate !== base) v.playbackRate = base;
     C.nudge = 0;
    } else if (size > .025) {
     // Audio is the clock: the muted video runs up to 5 % faster/slower until
     // it meets the sound again. Pitch and audio rate never move.
     const k = Math.max(-.05, Math.min(.05, drift * .3)), rate = base * (1 + k);
     if (Math.abs(v.playbackRate - rate) > .001) v.playbackRate = rate;
     C.nudge = k;
    } else { if (v.playbackRate !== base) v.playbackRate = base; C.nudge = 0; }
    if (a.playbackRate !== base) a.playbackRate = base;
   }
   if (!this.wantPlay || (v.paused && !this.playPending)) a.pause();
   else if (!v.paused && a.paused && !this.audioPending) {
    this.audioPending = true; const token = this.token;
    a.play().catch(e => { if (token === this.token && e.name !== 'AbortError') { this.wantPlay = false; this.stopMedia(); this.showError(e.message); } }).finally(() => { this.audioPending = false; });
   }
  };
 },

 /* ---------- Hooks */
 hooks() {
  const C = this, W = Watch58;
  W.show = function () {
   clearTimeout(this.hideTimer); this.stage.classList.add('controls-visible58');
   const delay = C.hideDelay();
   if (Clips.wantPlay && !this.menuOpen && delay > 0) this.hideTimer = setTimeout(() => {
    const a = document.activeElement, keyboard = this.stage.contains(a) && a !== Clips.video && a.matches(':focus-visible');
    if (!keyboard && !this.menuOpen) this.stage.classList.remove('controls-visible58');
   }, delay);
  };
  const onKey = Clips.onKey.bind(Clips);
  Clips.onKey = e => {
   const tag = e.target?.tagName || '';
   if (Clips.active && !e.ctrlKey && !e.altKey && !e.metaKey && !/INPUT|TEXTAREA|SELECT/.test(tag) && C.root.dataset.videoMode57 === 'watch' && !document.querySelector('.modal.on')) {
    const code = e.code;
    const dir = code === 'BracketLeft' || (e.shiftKey && code === 'Comma') ? -1 : code === 'BracketRight' || (e.shiftKey && code === 'Period') ? 1 : 0;
    if (dir) { e.preventDefault(); e.stopImmediatePropagation(); C.stepSpeed(dir); return; }
    if (code === 'KeyK' && !e.shiftKey && tag !== 'BUTTON' && !e.repeat) { e.preventDefault(); e.stopImmediatePropagation(); Clips.toggle(); W.show(); return; }
   }
   return onKey(e);
  };
  // Optional: open every clip straight in viewing mode (once per clip).
  Clips.video.addEventListener('playing', () => {
   const id = Clips.track?.id;
   if (!S.clipAutoFocus72 || !id || C.autoFor === id || Cinema71.focus || !Clips.active || C.root.dataset.videoMode57 !== 'watch') return;
   C.autoFor = id; Cinema71.setFocus(true, true);
  });
  const setFocus = Cinema71.setFocus.bind(Cinema71);
  Cinema71.setFocus = (...a) => { const r = setFocus(...a); C.hidePreview(); if (!Cinema71.focus) { cancelAnimationFrame(C.sizeRaf); C.sizeRaf = 0; C.root.classList.remove('cx-resizing72'); Cinema71.applySize(); } C.paintScreen(); return r; };
  const receive = Clips.receive.bind(Clips);
  Clips.receive = job => { const r = receive(job); C.paintSpeed(); return r; };
  const labels = Cinema71.labels.bind(Cinema71);
  Cinema71.labels = (...a) => { const r = labels(...a); C.labels(); return r; };
  document.addEventListener('fullscreenchange', () => C.hidePreview());
 },

 /* ---------- Text */
 labels() {
  if (!this.ready || !this.tabs) return;
  const T = x => this.t(x);
  for (const [id, , label] of this.TABS) { const b = this.tabs[id]; b.lastChild.textContent = T(label); b.title = T(label); }
  this.menu.setAttribute('aria-label', T('Playback settings'));
  for (const [id, label] of [['clipQuality', 'Quality'], ['clipSpeed', 'Playback speed']]) { const span = $(id)?.closest('label')?.querySelector('span'); if (span) span.textContent = T(label); }
  for (const n of this.menu.querySelectorAll('.cx-note72, .cx-chips72, .cx-keys72, .cx-mini72, .cx-menu-title71')) n.dataset.noI18n = '';
  if (this.ui) {
   const u = this.ui;
   u.fineRow.text.textContent = T('Exact speed');
   u.pitchRow.text.textContent = T('Pitch follows speed');
   u.loopRow.text.textContent = T('Loop video');
   u.avRow.text.textContent = T('Audio delay');
   u.avReset.textContent = T('Reset');
   u.av.setAttribute('aria-label', T('Audio delay'));
   this.paintSpeed();
  }
  if (this.screen) {
   const s = this.screen;
   s.autoRow.text.textContent = T('Open clips in viewing mode');
   s.fitHead.textContent = T('Picture in viewing mode');
   const fit = { contain: T('Fit'), cover: T('Fill screen') };
   for (const b of s.fit.children) b.textContent = fit[b.dataset.fit72];
   s.fitNote.textContent = T('Fill screen crops the edges instead of showing black bars.');
   s.hideRow.text.textContent = T('Hide controls after');
   const lang = typeof LANG === 'string' ? LANG : undefined;
   [...s.hide.options].forEach((o, i) => { const ms = this.HIDE[i][0]; o.textContent = ms ? (ms / 1000).toLocaleString(lang) + ' ' + T('s') : T('Never'); });
   s.enter.textContent = T('Open viewing mode (T)');
   for (const b of s.chips.children) b.setAttribute('aria-label', T('Video size') + ' ' + b.textContent);
   this.paintScreen();
  }
  if (this.color) {
   for (const [key, label] of this.PICTURE) this.color.rows[key].text.textContent = T(label);
   this.color.reset.textContent = T('Reset picture');
   this.color.note.textContent = T('Applies only to the clip, not to the blurred background.');
  }
  if (this.keyRows) this.KEYS.forEach(([, label], i) => { this.keyRows[i].textContent = T(label); });
  const wait = this.pages.ai.querySelector('.cx-ai-wait72'); if (wait) wait.textContent = T('AI tools are loading…');
 }
};
const boot72c = App.boot.bind(App);
App.boot = async function (...a) { await boot72c(...a); try { Cinema72.init(); } catch (e) { console.error('Cinema72.init', e); } };
