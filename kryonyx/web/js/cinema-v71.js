/* v71 «Cinema»: the clip room rebuilt — one header, a section/category toolbar,
   a calmer watch page, a distraction-free viewing mode (T), an ambient background
   drawn at the video's own frame rate, and gentler audio/video drift correction.
   The download engine, cookie gate and media pipeline are unchanged. */
'use strict';
DEFAULTS.clipFocusSize71 = 90;
DEFAULTS.clipFocusHints71 = 0;
DEFAULTS.clipFocusAmbient71 = true;
const Cinema71 = {
 ready: false, focus: false,
 t(en) { return typeof t === 'function' ? t(en) : en; },
 el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; },
 // The viewing-mode glyph stays local: the shared KryoIcons60 set is a fixed,
 // sprite-backed catalogue (each path has a static <symbol> in index.html).
 FOCUS_ICON: '<rect x="2.8" y="4.8" width="18.4" height="14.4" rx="2.6"/><path d="M6.8 10V8.4h2.4M17.2 10V8.4h-2.4M6.8 14v1.6h2.4M17.2 14v1.6h-2.4"/>',
 icon(name) {
  if (name !== 'focus71') return KryoIcons60.create(name);
  const svg = KryoIcons60.create('note'); svg.dataset.kryo60 = 'focus71';
  svg.querySelector('g').innerHTML = this.FOCUS_ICON; return svg;
 },

 init() {
  if (this.ready || typeof Clips === 'undefined' || !Clips.video || typeof Video57 === 'undefined' || !Video57.ready || typeof Watch58 === 'undefined' || !Watch58.ready) return;
  this.ready = true;
  const root = $('clips');
  this.root = root; this.stage = $('clipStage'); this.video = Clips.video;
  root.classList.add('cx71');
  document.body.classList.add('cinema71');
  const steps = [['header', () => this.buildHeader()], ['bar', () => this.buildBar()], ['watch', () => this.buildWatch()], ['focus', () => this.buildFocus()], ['ambient', () => this.ambient()], ['sync', () => this.sync()], ['hooks', () => this.hooks()]];
  for (const [name, fn] of steps) { try { fn(); } catch (e) { this.fail(name, e); } }
  this.labels(); this.paint();
 },
 fail(name, e) { try { if (typeof Polish70 !== 'undefined' && Polish70.fail) Polish70.fail('Cinema71.' + name, e); else console.error('Cinema71.' + name, e); } catch { console.error(e); } },

 /* ---------- Structure */
 buildHeader() {
  const head = this.root.querySelector('.cs-head');
  const start = this.el('div', 'cx-head-start71'), end = this.el('div', 'cx-head-end71');
  start.append($('videoBack57'), head.querySelector('.video-brand57'));
  end.append($('videoCookieButton57'), $('clipClose'));
  head.replaceChildren(start, $('clipSearchForm'), end);
  $('clipSearch').setAttribute('enterkeyhint', 'search');
 },
 buildBar() {
  const content = this.root.querySelector('.video-content57'), bar = this.el('div', 'cx-bar71');
  bar.append(this.root.querySelector('.video-nav57'), this.root.querySelector('.video-filters57'));
  content.insertBefore(bar, this.root.querySelector('.cs-layout'));
 },
 buildWatch() {
  const title = this.root.querySelector('.cs-title');
  const actions = this.el('div', 'cx-actions71'); actions.dataset.noI18n = '';
  const pill = (id, icon, fn, primary) => { const b = this.el('button', 'cx-pill71' + (primary ? ' cx-primary71' : '')); b.type = 'button'; b.id = id; b.append(this.icon(icon), this.el('span')); b.onclick = fn; return b; };
  this.focusPill = pill('cxFocusPill71', 'focus71', () => this.setFocus(!this.focus), true);
  this.focusPill.append(this.el('kbd', '', 'T'));
  this.savePill = pill('cxSave71', 'down', () => Clips.saveOriginal(Clips.job)); this.savePill.hidden = true;
  this.artistPill = pill('cxArtist71', 'user', () => $('clipArtistTab').click());
  actions.append(this.focusPill, this.savePill, this.artistPill, $('clipSource'));
  title.append(actions);
  new MutationObserver(() => this.paintActions()).observe($('clipDownload'), { attributes: true, attributeFilter: ['hidden'] });

  // Transport: viewing-mode toggle sits next to settings and fullscreen.
  this.focusBtn = Watch58.button('cxFocusBtn71', 'focus71', 'Viewing mode', () => { this.setFocus(!this.focus); Watch58.show(); });
  this.focusBtn.replaceChildren(this.icon('focus71'));
  $('watchSettings58').before(this.focusBtn);
  $('clipTime').dataset.noI18n = '';

  // "Up next" heading gets the autoplay switch (mirrors the tools checkbox).
  const heading = $('videoHeading57'), copy = this.el('div');
  copy.append(...heading.children); heading.append(copy);
  const auto = this.el('label', 'cx-auto71'), text = this.el('span'), box = this.el('input', 'cx-switch71');
  auto.dataset.noI18n = ''; box.type = 'checkbox'; box.id = 'cxAutoNext71'; box.setAttribute('role', 'switch');
  auto.append(text, box); heading.append(auto); this.autoText = text;
  const source = $('clipAutoNext'); box.checked = source.checked;
  box.onchange = () => { source.checked = box.checked; source.dispatchEvent(new Event('change')); };
  source.addEventListener('change', () => { box.checked = source.checked; });

  // Busy overlay shows real download progress instead of a bare spinner.
  const progress = this.el('div'); progress.id = 'cxBusyProgress71'; progress.dataset.noI18n = ''; $('clipBusy').append(progress);

  // Title strip used by viewing mode and fullscreen.
  const top = this.el('div'); top.id = 'cxTop71';
  const exit = this.el('button'); exit.id = 'cxExit71'; exit.type = 'button'; exit.dataset.noI18n = '';
  exit.append(this.icon('back'), this.el('span'));
  exit.onclick = () => { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); this.setFocus(false); };
  const meta = this.el('div', 'cx-top-meta71'); meta.dataset.entityName = '';
  meta.append(this.el('strong'), this.el('span'));
  top.append(exit, meta); this.stage.append(top); this.top = top;
  const mirror = () => { meta.firstChild.textContent = $('clipTitle').textContent; meta.lastChild.textContent = $('clipMeta').textContent; this.paintActions(); };
  for (const id of ['clipTitle', 'clipMeta']) new MutationObserver(mirror).observe($(id), { childList: true, characterData: true, subtree: true });
  mirror();
 },
 buildFocus() {
  const menu = $('watchMenu58'), section = this.el('section', 'cx-focus-settings71');
  section.dataset.noI18n = '';
  const head = this.el('span', 'cx-menu-title71'), row = this.el('label', 'cx-size71');
  const text = this.el('span'), out = this.el('output'), input = this.el('input');
  input.type = 'range'; input.id = 'cxFocusSize71'; input.min = 60; input.max = 100; input.step = 1;
  row.append(text, out, input); section.append(head, row); menu.append(section);
  this.sizeUi = { head, text, out, input };
  const saved = Number(S.clipFocusSize71);
  this.size = Number.isFinite(saved) ? Math.max(60, Math.min(100, saved)) : 90;
  input.value = this.size;
  input.oninput = () => { this.size = +input.value; this.applySize(); };
  input.onchange = () => { S.clipFocusSize71 = this.size; saveSettings(true); };
  this.applySize();
 },
 applySize() { this.root.style.setProperty('--cx-focus-size', String(this.size / 100)); if (this.sizeUi) this.sizeUi.out.value = this.size + '%'; },

 /* ---------- Viewing mode */
 setFocus(on, quiet = false) {
  on = !!on && Clips.active && this.root.dataset.videoMode57 === 'watch';
  if (on === this.focus) return;
  this.focus = on;
  this.root.classList.toggle('focus71', on);
  document.body.classList.toggle('focus71', on);
  if (!on) { document.body.classList.remove('cx-ui71'); $('cxHint71')?.remove(); }
  this.paintFocus();
  try { Experience66.applyAmbient(); } catch (e) { this.fail('ambient', e); }
  if (on) {
   this.root.scrollTop = 0;
   Watch58.show(); this.syncUi();
   if (!quiet) this.hint();
   if (!this.stage.contains(document.activeElement)) try { this.video.focus({ preventScroll: true }); } catch {}
  }
 },
 hint() {
  const seen = Number(S.clipFocusHints71) || 0;
  if (seen >= 3) return;
  S.clipFocusHints71 = seen + 1; saveSettings(true);
  $('cxHint71')?.remove();
  const hint = this.el('div', '', this.t('Viewing mode · T or Esc to exit')); hint.id = 'cxHint71'; hint.dataset.noI18n = '';
  this.stage.append(hint);
  setTimeout(() => hint.remove(), 3300);
 },
 syncUi() {
  const visible = this.stage.classList.contains('controls-visible58') || this.stage.classList.contains('paused58');
  document.body.classList.toggle('cx-ui71', this.focus && visible);
 },

 /* ---------- Ambient: per-frame, blurred inside a small canvas */
 ambient() {
  const E = Experience66, C = this;
  if (!E?.canvas || !E.ctx) return;
  E.stop();
  C.focusAmbient = S.clipFocusAmbient71 !== false;
  E.wanted = function () { return C.focus ? C.focusAmbient : !!this.prefs.enabled; };
  E.on = function () { return this.wanted() && Clips.active && $('clips').dataset.videoMode57 === 'watch'; };
  E.fit = function () {
   const w = this.prefs.blur < 8 ? 480 : 320, h = Math.round(w * 9 / 16);
   if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
  };
  E.filterFor = function () {
   const scale = this.canvas.width / Math.max(320, innerWidth || 1280), blur = this.prefs.blur * scale;
   this.pad = Math.ceil(blur * 2);
   return (blur > .25 ? 'blur(' + blur.toFixed(2) + 'px) ' : '') + 'brightness(' + (1 - this.prefs.dim / 100).toFixed(2) + ') saturate(1.25)';
  };
  E.draw = function () {
   if (!this.on() || this.video.readyState < 2 || !this.video.videoWidth) return;
   try {
    this.fit();
    const c = this.canvas, x = this.ctx, f = this.filterFor(), p = this.pad || 0;
    this.filterText = f;
    if (x.filter !== f) x.filter = f;
    x.imageSmoothingQuality = 'low';
    x.drawImage(this.video, -p, -p, c.width + p * 2, c.height + p * 2);
    this.drawCount = (this.drawCount || 0) + 1;
   } catch { this.stop(); }
  };
  E.schedule = function () {
   this.stop();
   const v = this.video;
   if (!this.on() || document.hidden || v.paused || v.ended) return;
   if (typeof v.requestVideoFrameCallback === 'function') {
    this.rvfc = true;
    const tick = () => { this.timer = 0; if (!this.on() || document.hidden || v.paused || v.ended) return; this.draw(); this.timer = v.requestVideoFrameCallback(tick) || -1; };
    this.timer = v.requestVideoFrameCallback(tick) || -1;
   } else {
    this.rvfc = false; let last = 0;
    const tick = now => { this.timer = 0; if (!this.on() || document.hidden || v.paused || v.ended) return; if (now - last >= 30) { last = now; this.draw(); } this.timer = requestAnimationFrame(tick); };
    this.timer = requestAnimationFrame(tick);
   }
  };
  E.stop = function () {
   if (this.timer) {
    if (this.rvfc) { try { this.video.cancelVideoFrameCallback(this.timer); } catch {} }
    else cancelAnimationFrame(this.timer);
   }
   this.timer = 0;
  };
  E.syncAmbient = function () {
   const root = $('clips'), active = this.on();
   root.classList.toggle('ambient-screen67', active);
   this.canvas.hidden = !active;
   const parent = document.fullscreenElement === this.stage ? this.stage : root;
   if (this.canvas.parentElement !== parent) { if (parent === this.stage) parent.insertBefore(this.canvas, this.video); else parent.prepend(this.canvas); }
  };
  const apply = E.applyAmbient.bind(E);
  E.applyAmbient = function () {
   apply();
   const wanted = this.wanted();
   this.ambientCheck.checked = wanted;
   for (const o of Object.values(this.sliders)) o.input.disabled = !wanted;
   if (this.on()) { this.draw(); this.schedule(); } else { this.stop(); this.clear(); }
  };
  E.ambientLabels = function () {
   this.ambientText.textContent = C.t('Moving blurred background');
   const labels = { blur: C.t('Blur'), dim: C.t('Dim') };
   for (const k of Object.keys(labels)) this.sliders[k].text.textContent = labels[k];
  };
  // In viewing mode the switch controls the viewing-mode background (on by default),
  // so the menu always shows what is on screen.
  const change = E.ambientCheck?.onchange;
  if (E.ambientCheck) E.ambientCheck.onchange = function (ev) {
   if (!C.focus) return change ? change.call(this, ev) : undefined;
   C.focusAmbient = E.ambientCheck.checked; S.clipFocusAmbient71 = C.focusAmbient; saveSettings(true); E.applyAmbient();
  };
  E.ambientLabels();
  addEventListener('resize', () => { if (E.on() && E.video.paused) E.draw(); }, { passive: true });
  E.syncAmbient();
  if (E.on()) { E.draw(); E.schedule(); }
 },

 /* ---------- A/V drift: nudge the audio rate instead of seeking (no clicks) */
 sync() {
  Clips.syncAudio = function (force = false) {
   if (!this.job?.audio_url) return;
   const v = this.video, a = this.audio, base = Number($('clipSpeed').value) || 1;
   if (a.readyState >= 1) {
    const drift = a.currentTime - v.currentTime, size = Math.abs(drift);
    if (force || size > .3 || v.paused) {
     if (size > (force ? .03 : .3)) try { a.currentTime = v.currentTime; } catch {}
     if (a.playbackRate !== base) a.playbackRate = base;
    } else if (size > .04) {
     const rate = base * (1 - Math.max(-.05, Math.min(.05, drift * .25)));
     if (Math.abs(a.playbackRate - rate) > .002) a.playbackRate = rate;
    } else if (a.playbackRate !== base) a.playbackRate = base;
   }
   if (!this.wantPlay || (v.paused && !this.playPending)) a.pause();
   else if (!v.paused && a.paused && !this.audioPending) {
    this.audioPending = true; const token = this.token;
    a.play().catch(e => { if (token === this.token && e.name !== 'AbortError') { this.wantPlay = false; this.stopMedia(); this.showError(e.message); } }).finally(() => { this.audioPending = false; });
   }
  };
 },

 /* ---------- Hooks into the existing modules */
 hooks() {
  const C = this, root = this.root, v = this.video;
  const mode = Video57.mode.bind(Video57);
  Video57.mode = name => { const r = mode(name); if (name !== 'watch') C.setFocus(false, true); C.paint(); return r; };
  const cards = Video57.cards.bind(Video57);
  Video57.cards = (...a) => { const r = cards(...a); C.paintCards(); return r; };
  const receive = Clips.receive.bind(Clips);
  Clips.receive = job => { const r = receive(job); C.paintBusy(job); return r; };
  const load = Clips.load.bind(Clips);
  Clips.load = (...a) => { $('cxBusyProgress71').textContent = ''; return load(...a); };
  const open = Clips.open.bind(Clips);
  Clips.open = (...a) => {
   const r = open(...a);
   clearTimeout(C.coverTimer);
   C.coverTimer = setTimeout(() => { if (Clips.active && root.classList.contains('on')) document.body.classList.add('cx-cover71'); }, 340);
   return r;
  };
  const close = Clips.close.bind(Clips);
  Clips.close = async (...a) => {
   if (Clips.active) { clearTimeout(C.coverTimer); C.setFocus(false, true); document.body.classList.remove('cx-cover71'); }
   return close(...a);
  };
  const onKey = Clips.onKey.bind(Clips);
  Clips.onKey = e => {
   const tag = e.target?.tagName || '';
   if (Clips.active && C.focus && e.key === 'Escape' && !document.fullscreenElement && !e.defaultPrevented && !Watch58.menuOpen) {
    e.preventDefault(); e.stopImmediatePropagation(); C.setFocus(false); return;
   }
   if (Clips.active && (e.code === 'KeyT' || /^[tе]$/i.test(e.key || '')) && !e.ctrlKey && !e.altKey && !e.metaKey && !e.repeat && !/INPUT|TEXTAREA|SELECT/.test(tag) && root.dataset.videoMode57 === 'watch' && !document.querySelector('.modal.on')) {
    e.preventDefault(); e.stopImmediatePropagation(); C.setFocus(!C.focus); return;
   }
   return onKey(e);
  };
  new MutationObserver(() => this.syncUi()).observe(this.stage, { attributes: true, attributeFilter: ['class'] });
  const bar = $('titlebar');
  if (bar) for (const evt of ['pointerenter', 'pointermove']) bar.addEventListener(evt, () => { if (C.focus) Watch58.show(); }, { passive: true });
  const ratio = () => { const w = v.videoWidth, h = v.videoHeight; if (w > 0 && h > 0) root.style.setProperty('--cx-ar', (w / h).toFixed(4)); else root.style.removeProperty('--cx-ar'); };
  for (const evt of ['loadedmetadata', 'resize', 'emptied']) v.addEventListener(evt, ratio);
  document.addEventListener('fullscreenchange', () => this.paintFocus());
  const labels = UI52.clipLabels.bind(UI52);
  UI52.clipLabels = (...a) => { const r = labels(...a); C.labels(); return r; };
  const lang = App.afterLangChange.bind(App);
  App.afterLangChange = (...a) => { const r = lang(...a); C.labels(); return r; };
 },

 /* ---------- Painting */
 paint() {
  if (!this.ready) return;
  const name = this.root.dataset.videoMode57;
  this.root.classList.toggle('cx-queue71', !!Video57.queueMode && name === 'catalog');
  this.paintActions(); this.paintFocus();
 },
 paintCards() {
  const list = $('clipList'), current = Clips.track?.id, label = this.t('Now playing');
  const cards = list.querySelectorAll('.video-card57');
  list.classList.toggle('cx-many71', cards.length >= 5);
  for (const card of cards) {
   const on = !!current && card.dataset.videoId57 === current && this.root.dataset.videoMode57 === 'watch';
   if (on) { if (card.dataset.cxNow71 !== label) card.dataset.cxNow71 = label; } else if ('cxNow71' in card.dataset) delete card.dataset.cxNow71;
  }
  this.paintFailure(list);
 },
 // A failed catalog request gets its own message and a retry button instead of
 // the generic "no videos" placeholder.
 paintFailure(list) {
  const V = Video57, text = $('clipListLabel')?.textContent || '';
  const errors = [V.tr('Could not load the catalog. Try again.', 'Не удалось загрузить каталог. Повтори попытку.'), V.tr('Catalog request timed out. Retry the search.', 'Каталог не ответил вовремя. Повтори поиск.')];
  const failed = !Clips.items.length && !V.queueMode && errors.includes(text);
  list.classList.toggle('cx-failed71', failed);
  this.root.classList.toggle('cx-failed71', failed);
  const empty = list.querySelector('.video-empty57');
  if (!failed || !empty || empty.querySelector('.cx-retry71')) return;
  const retry = this.el('button', 'btn cx-retry71', this.t('Retry'));
  retry.type = 'button'; retry.dataset.noI18n = '';
  retry.onclick = () => { retry.disabled = true; V.cache?.clear?.(); V.catalog(V.lastQuery); };
  empty.replaceChildren(this.el('b', '', text), retry);
 },
 paintActions() {
  if (!this.savePill) return;
  this.savePill.hidden = $('clipDownload').hidden;
  const artist = (Clips.track?.artist || '').trim();
  this.artistPill.hidden = !artist || artist === 'YouTube';
 },
 paintBusy(job) {
  const out = $('cxBusyProgress71');
  if (!out || !job) return;
  let text = '';
  if (['resolving', 'downloading', 'paused'].includes(job.state)) {
   const pct = job.progress == null ? this.t('Determining size') : Math.floor(job.progress * 100) + '%';
   text = pct + (job.state === 'downloading' && job.bytes_per_second ? ' · ' + ClipUtils.bytes(job.bytes_per_second) + this.t('/s') : '');
  }
  if (out.textContent !== text) out.textContent = text;
 },
 paintFocus() {
  if (!this.focusBtn) return;
  const label = this.focus ? this.t('Exit viewing mode (T)') : this.t('Viewing mode (T)');
  if (!this.focusBtn.querySelector('svg[data-kryo60="focus71"]')) this.focusBtn.replaceChildren(this.icon('focus71'));
  this.focusBtn.title = label; this.focusBtn.setAttribute('aria-label', label);
  this.focusBtn.setAttribute('aria-pressed', String(this.focus));
  this.focusPill.setAttribute('aria-pressed', String(this.focus));
  this.focusPill.title = label;
 },
 labels() {
  if (!this.ready) return;
  const close = $('clipClose');
  close.replaceChildren(this.icon('close'), this.el('span', 'cx-close-text71', this.t('Close')), this.el('kbd', 'cx-kbd71', 'Esc'));
  close.dataset.noI18n = ''; close.title = this.t('Close') + ' (Esc)'; close.setAttribute('aria-label', this.t('Close'));
  const back = $('videoBack57');
  back.replaceChildren(this.icon('back'), this.el('span', 'cx-back-text71', this.t('All videos')));
  back.dataset.noI18n = ''; back.setAttribute('aria-label', this.t('All videos'));
  this.focusPill.querySelector('span').textContent = this.t('Viewing mode');
  this.savePill.querySelector('span').textContent = this.t('Download');
  this.artistPill.querySelector('span').textContent = this.t('More from the artist');
  const source = $('clipSource');
  if (source) { source.textContent = this.t('Open on YouTube'); source.dataset.noI18n = ''; source.title = 'YouTube'; }
  this.autoText.textContent = this.t('Autoplay');
  $('cxExit71').querySelector('span').textContent = this.t('Exit viewing mode');
  this.sizeUi.head.textContent = this.t('Viewing mode');
  this.sizeUi.text.textContent = this.t('Video size');
  try { Experience66.ambientLabels(); } catch {}
  this.paintFocus(); this.paintCards();
 }
};
const boot71 = App.boot.bind(App);
App.boot = async function (...a) { await boot71(...a); try { Cinema71.init(); } catch (e) { Cinema71.fail('init', e); } };
