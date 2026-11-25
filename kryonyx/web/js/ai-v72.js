/* v72 «AI»: optional Real-ESRGAN upscaling (wallpapers and clips) and RIFE
   frame interpolation (smoother clips). The player never loads the networks
   itself: a separate worker in its own Python environment (.ai-venv) does the
   work, one task at a time, and the UI always says up front that a powerful
   computer is needed.
   · Wallpapers: after a new image is set, a dialog offers «Enhance with AI»
     or «Keep as is» (plus «don't ask again»); the original can be restored.
   · Clips: the AI tab of the playback menu builds a sharper version (above
     the source's own quality limit, up to 4K) and/or a smoother one (×2
     frames). It plays in place of the original at the same position, speed
     and audio, and is cached, so it is made only once. */
'use strict';
DEFAULTS.aiWallAsk72 = true;
DEFAULTS.aiWallModel72 = '';
DEFAULTS.aiClip72 = { target: null, style: 'general', smooth: false };
const AI72 = {
 ready: false, info: null, infoAt: 0, loading: null, jobs: {}, timer: 0,
 sid: '', versions: [], versionsFor: '', activeKey: null, swap: null, pending: null, offline: false,
 page: null, ui: null, wall: null, dlg: null, wallRow: null, wallStyle: '',
 RESULT: /^\/api\/ai\/result\/[a-f0-9]{32}\.mp4$/,
 WALL_FILE: /^\/api\/wallpaper\/file\/([a-f0-9]{64}\.jpg)$/,
 STORE_WALL: 'kryonyx.aiwall72', STORE_CLIP: 'kryonyx.aiclip72',
 WALL_STYLES: [['photo', 'Photo', 'Most detail · slower'], ['fast', 'Fast', 'Lighter model · quicker'], ['art', 'Art & anime', 'Drawings and flat colours']],
 CLIP_STYLES: [['general', 'Live action'], ['anime', 'Animation']],
 MODEL: { photo: 'RealESRGAN_x4plus', fast: 'realesr-general-x4v3', art: 'realesr-animevideov3', general: 'realesr-general-x4v3', anime: 'realesr-animevideov3', smooth: 'rife' },
 STAGES: { queued: 'Waiting for the previous AI task', starting: 'Starting AI…', loading: 'Loading the AI model…', processing: 'Enhancing frames', encoding: 'Saving the video…', saving: 'Saving the picture…' },

 T(en) { return typeof t === 'function' ? t(en) : en; },
 F(en, args) { return String(this.T(en)).replace(/\{(\w+)\}/g, (m, k) => (args && args[k] != null ? String(args[k]) : m)); },
 P(text) { return typeof tParts === 'function' ? tParts(text) : text; },
 el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; },
 icon(name) { try { return KryoIcons60.create(name); } catch { return this.el('i'); } },
 button(cls, text, onclick, icon) {
  const b = this.el('button', cls); b.type = 'button';
  if (icon) b.append(this.icon(icon));
  b.append(this.el('span', '', text));
  if (onclick) b.onclick = onclick;
  return b;
 },
 text(b, value) { const s = b.querySelector(':scope > span'); if (s) s.textContent = value; else b.textContent = value; },
 read(key) { try { return JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch { return {}; } },
 write(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
 mb(bytes) { bytes = +bytes || 0; return bytes >= 1e9 ? (bytes / 1e9).toFixed(1) + ' ' + this.T('GB') : Math.max(1, Math.round(bytes / 1e6)) + ' ' + this.T('MB'); },
 eta(s) {
  s = Math.max(0, Math.round(+s || 0));
  if (s < 60) return s + ' ' + this.T('s');
  if (s < 3600) return Math.round(s / 60) + ' ' + this.T('min');
  return Math.floor(s / 3600) + ' ' + this.T('h') + ' ' + Math.round(s % 3600 / 60) + ' ' + this.T('min');
 },
 sleep(ms) { return new Promise(done => setTimeout(done, ms)); },
 reduced() { return matchMedia('(prefers-reduced-motion: reduce)').matches || document.body.classList.contains('reduce-motion'); },

 init() {
  if (this.ready) return;
  this.ready = true;
  document.body.classList.add('ai72');
  for (const [name, fn] of [['wall', () => this.hookWall()], ['clips', () => this.hookClips()], ['lang', () => this.hookLang()]]) {
   try { fn(); } catch (e) { console.error('AI72.' + name, e); }
  }
  // Jobs live on the server: after a reload their progress is picked up again.
  setTimeout(() => api('/api/ai/jobs', { timeout: 10000 }).then(d => { for (const j of d.items || []) if (!j.finished) this.follow(j); }).catch(() => {}), 2500);
 },

 /* ---------- Engine status (probing starts the worker, so it is cached) */
 async status(mode) {
  if (!mode && this.info && Date.now() - this.infoAt < 20000) return this.info;
  if (this.loading && mode !== 'probe') return this.loading;
  const task = api('/api/ai/status' + (mode === 'probe' ? '?refresh=1' : ''), { timeout: 120000 })
   .then(info => { this.info = info; this.infoAt = Date.now(); return info; })
   .finally(() => { if (this.loading === task) this.loading = null; });
  this.loading = task;
  return task;
 },
 engine() { return (this.info && this.info.engine) || {}; },
 advice() { return this.engine().advice || 'missing'; },
 level() { return !this.info ? 'off' : ({ gpu: 'ok', 'gpu-low': 'warn', cpu: 'warn' }[this.advice()] || 'off'); },
 deviceText() {
  const e = this.engine();
  if (!this.info) return this.T('Checking this computer…');
  if (!e.installed) return this.T('AI module is not installed');
  if (e.cuda) return [e.device_name || 'NVIDIA GPU', e.vram_gb ? e.vram_gb + ' ' + this.T('GB') : '', 'CUDA'].filter(Boolean).join(' · ');
  return this.T('Processor') + ' · ' + this.F('{n} threads', { n: e.cpu_threads || '?' });
 },
 warnText(kind) {
  if (!this.info) return this.T('Needs a powerful computer: an NVIDIA graphics card with 6 GB of video memory or more is recommended.');
  if (kind === 'image') switch (this.advice()) {
   case 'gpu': return this.T('The graphics card handles this: a wallpaper takes a few seconds.');
   case 'gpu-low': return this.T('Less than 6 GB of video memory: AI works, but slower.');
   case 'cpu': return this.T('No NVIDIA graphics card found: AI runs on the processor, so a wallpaper takes longer (up to a few minutes). A powerful PC with an NVIDIA GPU is recommended.');
  }
  switch (this.advice()) {
   case 'gpu': return this.T('AI is demanding: the graphics card works at full load while a version is being made. Long clips take a while; you can keep watching.');
   case 'gpu-low': return this.T('Less than 6 GB of video memory: AI works, but slowly. 1080p is the sensible limit on this card.');
   case 'cpu': return this.T('No NVIDIA graphics card found: AI runs on the processor and is very slow; a clip can take hours. A powerful PC with an NVIDIA GPU (6 GB or more) is recommended.');
   default: return this.T('Needs a powerful computer: an NVIDIA graphics card with 6 GB of video memory or more is recommended. On a weak PC processing takes a very long time.');
  }
 },
 installBox(after) {
  const box = this.el('div', 'ai72-install'), row = this.el('div', 'ai72-actions'), msg = this.el('p', 'ai72-note ai72-msg');
  box.append(this.el('p', 'ai72-note', this.T('The AI module (PyTorch, about 3 GB with CUDA) is installed into the program folder; nothing is installed system-wide. Python 3.10–3.12 is required.')));
  const install = this.button('ai72-primary', this.T('Install AI module'), async () => {
   install.disabled = true;
   try {
    const r = await api('/api/ai/install', { method: 'POST', body: {} });
    msg.textContent = r.launched
     ? this.T('Setup is running in a separate window. When it says it is done, press «Check again».')
     : this.T('Run this command in the program folder, then press «Check again»:') + ' ' + (r.command || 'sh setup-ai.sh');
   } catch (e) { msg.textContent = e.message; }
   finally { install.disabled = false; }
  }, 'down');
  install.classList.add('ai72-install-btn');
  const again = this.button('ai72-ghost', this.T('Check again'), async () => {
   again.disabled = true; msg.textContent = this.T('Checking this computer…');
   try { await this.status('probe'); msg.textContent = ''; if (after) after(); }
   catch (e) { msg.textContent = e.message; }
   finally { again.disabled = false; }
  }, 'refresh');
  again.classList.add('ai72-check-btn');
  if (this.info && this.info.setup && this.info.setup.available === false) {
   install.disabled = true;
   msg.textContent = this.T('setup-ai.bat was not found next to the program. Reinstall Kryo.');
  }
  row.append(install, again); box.append(row, msg);
  return box;
 },
 /* Downloads the missing weights (verified on the server) and reports progress. */
 async ensureModels(ids, progress, cancelled) {
  ids = [...new Set(ids.filter(Boolean))];
  let info = await this.status('fresh');
  const missing = ids.filter(id => !(info.models && info.models[id] && info.models[id].present));
  if (!missing.length) return;
  await api('/api/ai/models', { method: 'POST', body: { ids: missing } });
  const size = id => (info.models && info.models[id] && info.models[id].size) || 0;
  const total = missing.reduce((n, id) => n + size(id), 0);
  let last = -1, still = Date.now();
  for (;;) {
   await this.sleep(800);
   if (cancelled && cancelled()) throw Object.assign(new Error('cancelled'), { cancelled: true });
   info = await this.status('fresh');
   const bad = missing.map(id => (info.downloads || {})[id] || {}).find(s => s.stage === 'error');
   if (bad) throw new Error(this.T('Model download failed') + (bad.error ? ': ' + this.P(bad.error) : ''));
   const ready = id => info.models && info.models[id] && info.models[id].present;
   const done = missing.reduce((n, id) => n + (ready(id) ? size(id) : (((info.downloads || {})[id] || {}).done || 0)), 0);
   if (progress) progress(done, total);
   if (missing.every(ready)) return;
   if (done !== last) { last = done; still = Date.now(); }
   else if (Date.now() - still > 180000) throw new Error(this.T('Model download stalled. Check the connection and try again.'));
  }
 },

 /* ---------- Clip page (the AI tab of the playback menu) */
 clipPage(page) {
  this.page = page; page.dataset.noI18n = '';
  this.renderPage();
  const stale = !this.info || Date.now() - this.infoAt > 20000;
  if (stale) this.status().then(() => this.renderPage()).catch(e => { this.pageError = e.message; this.renderPage(); });
  this.loadVersions().then(changed => { if (changed) this.renderPage(); });
 },
 targets(height) {
  if (!height) return [];
  const out = [], seen = new Set(), limit = Math.min(2160, height * 4);
  const add = (value, label) => { if (value > height && value <= limit && !seen.has(value)) { seen.add(value); out.push([value, label]); } };
  for (const v of [1080, 1440, 2160]) add(v, v === 2160 ? '4K · 2160p' : v + 'p');
  const x2 = Math.min(2160, height * 2);
  add(x2, '×2 · ' + x2 + 'p');
  return out.sort((a, b) => a[0] - b[0]);
 },
 pref() { return S.aiClip72 && typeof S.aiClip72 === 'object' ? S.aiClip72 : {}; },
 setPref(patch) { S.aiClip72 = { ...this.pref(), ...patch }; saveSettings(true); },
 target(height) {
  const list = this.targets(height), want = this.pref().target;
  if (want === 0 || !list.length) return 0;
  if (!want) return list[0][0];
  return (list.find(([v]) => v >= want) || list[list.length - 1])[0];
 },
 request(job) {
  const height = +(job && job.height) || 0, target = this.target(height), smooth = !!this.pref().smooth;
  if (!target && !smooth) return null;
  const upscale = !target ? 'off' : [1080, 1440, 2160].includes(target) ? String(target) : 'x2';
  return { upscale, style: this.pref().style === 'anime' ? 'anime' : 'general', smooth, height: target || null };
 },
 same(options, req) {
  if (!options || !req) return false;
  return (options.height || 0) === (req.height || 0) && !!options.smooth === !!req.smooth && (!req.height || options.style === req.style);
 },
 runningFor(sid) { return Object.values(this.jobs).find(j => j.kind === 'clip' && j.session === sid && !j.finished) || null; },
 row(text, control, cls) {
  const row = this.el('label', 'cx-row72' + (cls ? ' ' + cls : '')); row.dataset.noI18n = '';
  row.append(this.el('span', '', text), control);
  return row;
 },
 renderPage() {
  const page = this.page; if (!page) return;
  const focus = document.activeElement && page.contains(document.activeElement) ? document.activeElement.id : '';
  const T = x => this.T(x), job = typeof Clips !== 'undefined' ? Clips.job : null, height = +(job && job.height) || 0;
  const head = this.el('section', 'ai72-head');
  const title = this.el('div', 'ai72-title');
  title.append(this.icon('spark'), this.el('b', '', T('AI enhancement')), this.el('span', 'ai72-badge', T('Needs a powerful PC')));
  const device = this.el('div', 'ai72-device ai72-' + this.level());
  device.append(this.el('i', 'ai72-dot'), this.el('span', '', this.deviceText()));
  head.append(title, device, this.el('p', 'ai72-warn ai72-' + this.level(), this.warnText()));
  const parts = [head];
  // Saved versions first (the usual next step), then options, the start button and the explanation last.
  if (this.versions.length) parts.push(this.versionsSection(job));
  if (!this.info) parts.push(this.el('p', 'cx-note72', this.pageError || T('Checking this computer…')));
  else if (!this.engine().installed) { const s = this.el('section', 'ai72-setup'); s.append(this.installBox(() => this.renderPage())); parts.push(s); }
  else parts.push(this.optionsSection(height), this.runSection(job));
  if (this.info) parts.push(this.el('p', 'cx-note72 ai72-about', T('Sharper picture goes past the original quality limit: Real-ESRGAN redraws every frame at a higher resolution. Smoother motion adds in-between frames with RIFE. The original file is kept.')));
  page.replaceChildren(...parts);
  if (focus && $(focus)) $(focus).focus({ preventScroll: true });
  this.paintProgress();
 },
 optionsSection(height) {
  const T = x => this.T(x), pref = this.pref(), s = this.el('section', 'ai72-opts');
  const list = this.targets(height), target = this.target(height);
  const sel = this.el('select'); sel.id = 'aiRes72';
  sel.append(new Option(T('Off'), '0'));
  for (const [v, label] of list) sel.append(new Option(label, String(v)));
  sel.value = String(target); sel.disabled = !list.length;
  sel.onchange = () => { this.setPref({ target: +sel.value }); this.renderPage(); };
  s.append(this.row(T('Sharper picture'), sel));
  if (!height) s.append(this.el('p', 'cx-note72', T('The resolution of this clip is not known yet.')));
  else if (!list.length) s.append(this.el('p', 'cx-note72', T('This clip is already 4K: only smoother motion is available.')));
  if (target) {
   const chips = this.el('div', 'cx-chips72 ai72-style'); chips.setAttribute('role', 'radiogroup'); chips.setAttribute('aria-label', T('Picture type')); chips.dataset.noI18n = '';
   for (const [id, label] of this.CLIP_STYLES) {
    const c = this.el('button', 'cx-chip72', T(label)); c.type = 'button'; c.id = 'aiStyle72-' + id; c.setAttribute('role', 'radio');
    c.setAttribute('aria-checked', String((pref.style === 'anime' ? 'anime' : 'general') === id));
    c.onclick = () => { this.setPref({ style: id }); this.renderPage(); };
    chips.append(c);
   }
   s.append(chips);
  }
  const smooth = this.el('input', 'cx-switch72'); smooth.type = 'checkbox'; smooth.id = 'aiSmooth72'; smooth.setAttribute('role', 'switch');
  smooth.checked = !!pref.smooth;
  smooth.onchange = () => { this.setPref({ smooth: smooth.checked }); this.renderPage(); };
  s.append(this.row(T('Smoother motion · ×2 frames'), smooth, 'cx-switch-row72'));
  return s;
 },
 summary(job, req) {
  const parts = [], height = +(job && job.height) || 0;
  if (req.height) parts.push(height + 'p → ' + (req.height >= 2160 ? '4K' : req.height + 'p'));
  if (req.smooth) parts.push(this.T('×2 frames'));
  return parts.join(' · ');
 },
 runSection(job) {
  const T = x => this.T(x), s = this.el('section', 'ai72-run');
  const req = this.request(job), existing = req && this.versions.find(v => this.same(v.options, req));
  const start = this.button('ai72-primary', T('Enhance clip'), () => this.start(), 'spark'); start.id = 'aiStart72';
  const note = this.el('p', 'cx-note72 ai72-run-note');
  if (!job || !job.id) { start.disabled = true; note.textContent = T('Open a clip first.'); }
  else if (!job.offline_ready) { start.disabled = true; note.textContent = T('Available after the clip has fully downloaded.'); }
  else if (!req) { start.disabled = true; note.textContent = T('Choose a higher resolution, smoother motion or both.'); }
  else if (existing) {
   const on = existing.key === this.activeKey;
   this.text(start, on ? T('This version is playing') : T('Play this version'));
   start.disabled = on; start.onclick = () => this.use(existing.key);
   note.textContent = T('This version is already made and saved on this device.');
  } else note.textContent = this.summary(job, req);
  if (this.pageError && this.info) { note.textContent = this.pageError; note.classList.add('ai72-error'); }
  const prog = this.el('div', 'ai72-progress'); prog.id = 'aiProg72'; prog.hidden = true;
  const top = this.el('div', 'ai72-prog-top'), stage = this.el('b'), pct = this.el('span', 'ai72-pct');
  const bar = this.el('div', 'ai72-bar'), fill = this.el('i');
  bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100'); bar.append(fill);
  const bottom = this.el('div', 'ai72-prog-bottom'), detail = this.el('span', 'ai72-detail');
  const cancel = this.el('button', 'cx-mini72', T('Cancel')); cancel.type = 'button'; cancel.id = 'aiCancel72'; cancel.onclick = () => this.cancel();
  top.append(stage, pct); bottom.append(detail, cancel); prog.append(top, bar, bottom);
  s.append(start, note, prog);
  this.ui = { start, note, prog, stage, pct, bar, fill, detail, cancel };
  return s;
 },
 paintProgress() {
  const u = this.ui; if (!u || !u.prog.isConnected) return;
  const T = x => this.T(x), sid = Clips.job && Clips.job.id;
  const job = this.runningFor(sid), p = this.pending && this.pending.sid === sid ? this.pending : null;
  const live = job || p;
  u.prog.hidden = !live; u.start.hidden = !!live;
  if (u.note) u.note.hidden = !!live;
  if (!live) return;
  let stage = T('Preparing…'), ratio = null, detail = '';
  if (!job) {
   if (p.stage === 'models') { stage = T('Downloading AI models'); ratio = p.total ? p.done / p.total : null; detail = p.total ? this.mb(p.done) + ' / ' + this.mb(p.total) : ''; }
  } else {
   stage = T(this.STAGES[job.stage] || 'Working…');
   if (job.stage === 'processing' && job.total) {
    ratio = job.done / job.total;
    detail = this.F('{done} / {total} frames', { done: job.done || 0, total: job.total })
     + (job.fps ? ' · ' + (+job.fps).toFixed(1) + ' ' + T('frames/s') : '')
     + (job.eta != null ? ' · ' + this.F('{time} left', { time: this.eta(job.eta) }) : '');
   } else if (job.stage === 'encoding') ratio = 1;
   if (job.stage === 'processing' && job.out_height) stage += ' · ' + (job.out_height >= 2160 ? '4K' : job.out_height + 'p') + (job.out_fps ? ' ' + Math.round(job.out_fps) + ' ' + T('fps') : '');
  }
  u.stage.textContent = stage;
  u.pct.textContent = ratio == null ? '' : Math.floor(ratio * 100) + '%';
  u.fill.style.transform = 'scaleX(' + (ratio == null ? 1 : Math.max(.02, Math.min(1, ratio))) + ')';
  u.bar.classList.toggle('ai72-indet', ratio == null);
  if (ratio == null) u.bar.removeAttribute('aria-valuenow'); else u.bar.setAttribute('aria-valuenow', String(Math.floor(ratio * 100)));
  u.bar.setAttribute('aria-label', stage);
  u.detail.textContent = detail;
 },
 async start() {
  const job = Clips.job, req = this.request(job);
  if (!job || !job.id || !req || this.pending || this.runningFor(job.id)) return;
  const sid = job.id;
  this.pageError = '';
  this.pending = { sid, stage: 'prepare', done: 0, total: 0 };
  this.renderPage();
  try {
   const info = await this.status('fresh');
   if (!info.engine || !info.engine.installed) { this.pending = null; this.renderPage(); return; }
   const ids = [];
   if (req.height) ids.push(this.MODEL[req.style]);
   if (req.smooth) ids.push(this.MODEL.smooth);
   await this.ensureModels(ids, (done, total) => {
    if (this.pending && this.pending.sid === sid) { Object.assign(this.pending, { stage: 'models', done, total }); this.paintProgress(); }
   }, () => !this.pending || this.pending.sid !== sid);
   if (!this.pending || this.pending.sid !== sid) return;
   const r = await api('/api/ai/clip', { method: 'POST', body: { session: sid, upscale: req.upscale, style: req.style, smooth: req.smooth } });
   this.pending = null;
   if (r.stage === 'done') {
    await this.loadVersions(true);
    if (Clips.job && Clips.job.id === sid) this.use(r.key);
   } else this.follow(r);
  } catch (e) {
   this.pending = null;
   if (!e.cancelled) {
    if (e.data && e.data.code === 'engine') await this.status('probe').catch(() => {});
    this.pageError = e.message;
   }
  }
  this.renderPage();
 },
 async cancel() {
  const sid = Clips.job && Clips.job.id;
  if (this.pending && this.pending.sid === sid) { this.pending = null; this.renderPage(); return; }
  const job = this.runningFor(sid); if (!job) return;
  if (this.ui) this.ui.cancel.disabled = true;
  try { this.jobs[job.id] = await api('/api/ai/jobs/' + job.id, { method: 'DELETE' }); }
  catch (e) { toast(e.message); }
  this.renderPage();
 },

 /* ---------- Versions */
 async loadVersions(force) {
  const sid = Clips.job && Clips.job.id;
  if (!sid) { const had = this.versions.length; this.versions = []; this.versionsFor = ''; return had > 0; }
  if (!force && this.versionsFor === sid) return false;
  let data;
  try { data = await api('/api/ai/clip?session=' + encodeURIComponent(sid), { timeout: 10000 }); }
  catch { return false; }
  if (!Clips.job || Clips.job.id !== sid) return false;
  this.versionsFor = sid; this.versions = data.items || [];
  if (this.activeKey && !this.versions.some(v => v.key === this.activeKey)) this.activeKey = null;
  return true;
 },
 label(v) {
  const o = v.options || {}, parts = [];
  parts.push(o.height ? (o.height >= 2160 ? '4K' : o.height + 'p') : this.T('Original resolution'));
  if (o.height) parts.push(this.T(o.style === 'anime' ? 'Animation' : 'Live action'));
  if (o.smooth) parts.push(v.fps ? Math.round(v.fps) + ' ' + this.T('fps') : this.T('Smoother motion'));
  return parts.join(' · ');
 },
 versionsSection(job) {
  const s = this.el('section', 'ai72-versions'), list = this.el('div', 'ai72-list');
  s.append(this.el('div', 'ai72-sub', this.T('Versions')));
  list.setAttribute('role', 'radiogroup'); list.setAttribute('aria-label', this.T('Versions'));
  list.append(this.version(null, this.T('Original') + (job && job.height ? ' · ' + job.height + 'p' : ''), ''));
  for (const v of this.versions) list.append(this.version(v, this.label(v), this.mb(v.size)));
  s.append(list);
  return s;
 },
 version(item, text, meta) {
  const row = this.el('div', 'ai72-ver'), key = item ? item.key : null, on = key === this.activeKey;
  const b = this.el('button', 'ai72-ver-btn'); b.type = 'button'; b.id = 'aiVer72-' + (key || 'original');
  b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', String(on));
  b.append(this.el('i', 'ai72-radio'), this.el('span', 'ai72-ver-name', text));
  if (meta) b.append(this.el('small', '', meta));
  b.onclick = () => this.use(key);
  row.append(b);
  if (item) {
   const del = this.el('button', 'cx-mini72 ai72-del'); del.type = 'button'; del.id = 'aiDel72-' + key;
   del.append(this.icon('trash')); del.title = this.T('Delete this version'); del.setAttribute('aria-label', del.title);
   del.onclick = () => this.remove(key, del);
   row.append(del);
  }
  return row;
 },
 remember(sid, key) {
  if (!sid) return;
  const map = this.read(this.STORE_CLIP);
  if (key) map[sid] = key; else delete map[sid];
  const keys = Object.keys(map); for (const k of keys.slice(0, Math.max(0, keys.length - 60))) delete map[k];
  this.write(this.STORE_CLIP, map);
 },
 use(key) {
  const C = Clips, v = C.video, job = C.job;
  if (!job || !job.video_url || !v) return;
  const item = key ? this.versions.find(x => x.key === key) : null;
  if (key && !item) return;
  const url = item ? item.url : job.video_url;
  this.activeKey = item ? key : null; this.remember(job.id, this.activeKey);
  if ((v.getAttribute('src') || '') !== url) this.load(url, v.currentTime || 0);
  this.renderPage();
 },
 load(url, at) {
  const C = Clips, v = C.video, play = !!C.wantPlay, swap = this.swap = { url, at, play };
  v.src = url;
  v.addEventListener('loadedmetadata', () => {
   if (this.swap !== swap) return;
   this.swap = null;
   C.applyAudio();
   if (at > 0 && Number.isFinite(v.duration) && at < v.duration - .3) C.seek(at);
   C.syncAudio(true);
   if (C.paintTime) C.paintTime();
   if (play) { C.wantPlay = true; C.maybeStart(); }
  }, { once: true });
 },
 async remove(key, btn) {
  if (!btn.classList.contains('ai72-confirm')) {
   btn.classList.add('ai72-confirm'); btn.replaceChildren(this.el('span', '', this.T('Delete?')));
   clearTimeout(this.confirmTimer); this.confirmTimer = setTimeout(() => this.renderPage(), 4000);
   return;
  }
  clearTimeout(this.confirmTimer);
  if (this.activeKey === key) { this.use(null); await this.sleep(500); }
  try { await api('/api/ai/result/' + key + '.mp4', { method: 'DELETE' }); }
  catch (e) { toast(e.message); }
  await this.loadVersions(true);
  this.renderPage();
 },
 hookClips() {
  if (typeof Clips === 'undefined' || !Clips.video) return;
  const v = Clips.video;
  // An AI file that cannot be played falls back to the original instead of an error screen.
  v.addEventListener('error', e => {
   const src = v.getAttribute('src') || '';
   if (!this.RESULT.test(src) || !Clips.job || !Clips.job.video_url) return;
   e.stopImmediatePropagation();
   const at = this.swap ? this.swap.at : (v.currentTime || 0);
   this.activeKey = null; this.remember(Clips.job.id, null);
   toast(this.T('The AI version could not be played. Back to the original.'));
   this.load(Clips.job.video_url, at);
   this.renderPage();
  }, true);
  const receive = Clips.receive.bind(Clips);
  Clips.receive = job => { const r = receive(job); try { this.onJob(job); } catch (e) { console.error('AI72.onJob', e); } return r; };
  const detach = Clips.detach.bind(Clips);
  Clips.detach = (...a) => { this.swap = null; this.activeKey = null; return detach(...a); };
 },
 onJob(job) {
  if (!job) return;
  if (job.id !== this.sid) {
   this.sid = job.id; this.activeKey = null; this.versions = []; this.versionsFor = ''; this.offline = !!job.offline_ready; this.pageError = '';
   this.loadVersions().then(() => { this.autoUse(); if (this.page) this.renderPage(); });
   if (this.page) this.renderPage();
   return;
  }
  if (!!job.offline_ready !== this.offline) { this.offline = !!job.offline_ready; if (this.page) this.renderPage(); }
 },
 /* The version picked last time for this clip comes back automatically. */
 autoUse() {
  const job = Clips.job; if (!job || !Clips.attached) return;
  const key = this.read(this.STORE_CLIP)[job.id];
  if (key && this.versions.some(v => v.key === key) && (Clips.video.getAttribute('src') || '') === job.video_url) this.use(key);
 },

 /* ---------- Background polling */
 follow(job) {
  if (!job || !job.id) return;
  this.jobs[job.id] = job;
  if (!this.timer) this.timer = setTimeout(() => this.tick(), 600);
  if (job.kind === 'clip' && this.page) this.renderPage();
 },
 async tick() {
  this.timer = 0;
  for (const j of Object.values(this.jobs).filter(x => !x.finished)) {
   try {
    const s = await api('/api/ai/jobs/' + j.id, { timeout: 10000 });
    this.jobs[j.id] = s;
    if (s.finished) this.finished(s);
   } catch (e) {
    if (e.status === 404) { const lost = { ...j, finished: true, stage: 'error', error: 'The AI task was lost (the player restarted)' }; this.jobs[j.id] = lost; this.finished(lost); }
   }
  }
  this.paintProgress();
  if (this.wall) this.paintWall();
  if (Object.values(this.jobs).some(x => !x.finished)) this.timer = setTimeout(() => this.tick(), document.hidden ? 4000 : 1000);
 },
 async finished(job) {
  if (job.kind === 'wallpaper') { this.wallFinished(job); return; }
  const here = Clips.active && Clips.job && Clips.job.id === job.session;
  if (job.stage === 'done') {
   if (here) {
    await this.loadVersions(true);
    toastAction(this.T('The AI version of the clip is ready · Play'), () => this.use(job.key), 9000);
   } else toast(this.T('The AI version of the clip is ready'), 5000);
  } else if (job.stage === 'error') toast(this.T('AI processing failed') + (job.error ? ': ' + this.P(job.error) : ''), 7000);
  if (this.page) this.renderPage();
 },

 /* ---------- Wallpapers */
 hookWall() {
  if (typeof Wall === 'undefined') return;
  const pick = Wall.pickFile.bind(Wall);
  Wall.pickFile = async file => {
   const before = this.wallSig(), r = await pick(file), after = this.wallSig();
   if (S.wallSrc === 'local' && after && after !== before) this.offer({ kind: 'local', sig: after });
   return r;
  };
  const bind = Wall.bind.bind(Wall);
  Wall.bind = (...a) => { const r = bind(...a); this.hookUrl(); return r; };
  const build = Wall.build.bind(Wall);
  Wall.build = (...a) => { const r = build(...a); this.paintWallRow(); return r; };
  this.hookUrl();
  this.buildWallRow();
 },
 hookUrl() {
  const url = $('wallUrl');
  if (!url || !url.onchange || url.onchange === this.urlHandler) return;
  const original = url.onchange;
  this.urlHandler = url.onchange = async event => {
   const before = S.wallSrc, r = await original.call(url, event), m = this.WALL_FILE.exec(S.wallSrc || '');
   if (m && S.wallSrc !== before) this.offer({ kind: 'file', file: m[1] });
   return r;
  };
 },
 wallSig() { let d = ''; try { d = localStorage.getItem(WALL_KEY) || ''; } catch {} return d ? d.length + ':' + d.slice(-40) : ''; },
 current() {
  const src = S.wallSrc || '';
  if (src === 'local') { const sig = this.wallSig(); return sig ? { kind: 'local', sig } : null; }
  const m = this.WALL_FILE.exec(src);
  return m ? { kind: 'file', file: m[1] } : null;
 },
 results() { return this.read(this.STORE_WALL); },
 resultFor(source) { return source && source.kind === 'file' ? this.results()[source.file] || null : null; },
 sameSource(a, b) { return !!a && !!b && a.kind === b.kind && (a.kind === 'local' ? a.sig === b.sig : a.file === b.file); },
 offer(source) {
  if (S.aiWallAsk72 === false || this.resultFor(source)) return;
  this.openWall(source, false);
 },
 buildWallRow() {
  // After «Image link» when it sits right below «Your picture», otherwise after the file row.
  const pick = $('wallPick'), file = pick && pick.closest('.set'), link = $('wallUrl') && $('wallUrl').closest('.set');
  const anchor = link && file && link.parentNode === file.parentNode ? link : file;
  if (!anchor || $('wallAiRow72')) return;
  const make = (id, control) => {
   const set = this.el('div', 'set ai72-set'); set.id = id; set.dataset.noI18n = '';
   const left = this.el('div'), l = this.el('div', 'l'), h = this.el('div', 'h'), c = this.el('div', 'c');
   left.append(l, h); c.append(control); set.append(left, c);
   return { set, l, h };
  };
  const btn = this.button('btn ai72-wall-btn', '', () => this.wallButton(), 'spark'); btn.id = 'wallAi72';
  const sw = this.el('div', 'sw'); sw.id = 'wallAiAsk72'; sw.dataset.sw = 'aiWallAsk72'; sw.tabIndex = 0; sw.setAttribute('role', 'switch');
  const flip = e => { e.preventDefault(); e.stopPropagation(); S.aiWallAsk72 = S.aiWallAsk72 === false; saveSettings(); this.paintWallRow(); };
  sw.onclick = flip; sw.onkeydown = e => { if (e.key === ' ' || e.key === 'Enter') flip(e); };
  const one = make('wallAiRow72', btn), two = make('wallAiAskRow72', sw);
  anchor.after(one.set, two.set);
  this.wallRow = { one, two, btn, sw };
  this.paintWallRow();
 },
 paintWallRow() {
  const u = this.wallRow; if (!u) return;
  const T = x => this.T(x), cur = this.current(), res = this.resultFor(cur);
  u.one.l.textContent = T('Enhance with AI');
  u.one.h.textContent = !cur ? T('Choose your own image or a link first') : res
   ? this.F('Enhanced with AI · {size}', { size: (res.w || '?') + ' × ' + (res.h || '?') })
   : T('Real-ESRGAN redraws the picture at your screen resolution · needs a powerful PC');
  this.text(u.btn, res ? T('Restore original') : T('Enhance'));
  u.btn.disabled = !cur; u.btn.dataset.mode72 = res ? 'restore' : 'enhance';
  u.two.l.textContent = T('Offer AI for new wallpapers');
  u.two.h.textContent = T('Ask after you choose a file or a link');
  const on = S.aiWallAsk72 !== false;
  u.sw.classList.toggle('on', on); u.sw.setAttribute('aria-checked', String(on)); u.sw.setAttribute('aria-label', T('Offer AI for new wallpapers'));
 },
 wallButton() {
  const cur = this.current(); if (!cur) return;
  const res = this.resultFor(cur);
  if (res) this.restore(res.from); else this.openWall(cur, true);
 },
 restore(from) {
  if (from && from.kind === 'local' && this.wallSig() === from.sig) Wall.select('local');
  else if (from && from.kind === 'file') Wall.select('/api/wallpaper/file/' + from.file);
  else { toast(this.T('The original image is no longer available')); return; }
  toast(this.T('Original wallpaper restored'));
 },
 measure(url) { return new Promise((done, fail) => { const im = new Image(); im.onload = () => done([im.naturalWidth, im.naturalHeight]); im.onerror = fail; im.src = url; }); },
 /* Mirrors the server: aimed at this screen, at most ×4 and never above 3840 px. */
 outSize(w, h) {
  const longest = Math.max(w, h); if (!longest) return null;
  const screenLong = Math.round(Math.max(screen.width || 1920, screen.height || 1080) * (window.devicePixelRatio || 1));
  const target = Math.max(1920, Math.min(3840, screenLong));
  let f = longest < target ? Math.min(4, target / longest) : 1;
  if (longest * f > 3840) f = 3840 / longest;
  return { w: Math.max(1, Math.round(w * f)), h: Math.max(1, Math.round(h * f)), f, target };
 },
 dialog() {
  if (this.dlg) return this.dlg;
  const scrim = this.el('div', 'ai72-scrim'); scrim.id = 'aiWall72'; scrim.hidden = true; scrim.dataset.noI18n = '';
  const box = this.el('div', 'ai72-dialog'); box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-labelledby', 'aiWallTitle72'); box.tabIndex = -1;
  const art = this.el('div', 'ai72-art'), img = this.el('img'); img.alt = ''; img.decoding = 'async'; img.draggable = false;
  const badge = this.el('span', 'ai72-art-badge'); art.append(img, this.el('span', 'ai72-art-scan'), badge);
  const body = this.el('div', 'ai72-body'), kicker = this.el('div', 'ai72-kicker');
  kicker.append(this.icon('spark'), this.el('span'));
  const title = this.el('h3'); title.id = 'aiWallTitle72';
  const text = this.el('p', 'ai72-text'), dims = this.el('div', 'ai72-dims');
  const chips = this.el('div', 'ai72-chips'); chips.setAttribute('role', 'radiogroup');
  const styles = {};
  for (const [id] of this.WALL_STYLES) {
   const c = this.el('button', 'ai72-chip'); c.type = 'button'; c.id = 'aiWallStyle72-' + id; c.setAttribute('role', 'radio');
   c.append(this.el('b'), this.el('small'));
   c.onclick = () => { this.wallStyle = id; this.paintWall(); };
   chips.append(c); styles[id] = c;
  }
  const warn = this.el('p', 'ai72-warn'), setup = this.el('div', 'ai72-setup-slot');
  const prog = this.el('div', 'ai72-progress'), top = this.el('div', 'ai72-prog-top'), stage = this.el('b'), pct = this.el('span', 'ai72-pct');
  const bar = this.el('div', 'ai72-bar'), fill = this.el('i'), detail = this.el('span', 'ai72-detail');
  bar.setAttribute('role', 'progressbar'); bar.setAttribute('aria-valuemin', '0'); bar.setAttribute('aria-valuemax', '100');
  bar.append(fill); top.append(stage, pct); prog.append(top, bar, detail);
  const ask = this.el('label', 'ai72-ask'), askBox = this.el('input'); askBox.type = 'checkbox'; askBox.id = 'aiWallNever72';
  ask.append(askBox, this.el('span'));
  askBox.onchange = () => { S.aiWallAsk72 = !askBox.checked; saveSettings(); this.paintWallRow(); };
  const actions = this.el('div', 'ai72-actions');
  const keep = this.button('btn g ai72-keep', '', () => this.wallSecondary()); keep.id = 'aiWallKeep72';
  const go = this.button('btn ai72-go', '', () => this.wallPrimary(), 'spark'); go.id = 'aiWallGo72';
  actions.append(keep, go);
  body.append(kicker, title, text, dims, chips, warn, setup, prog, ask, actions);
  box.append(art, body); scrim.append(box);
  scrim.addEventListener('mousedown', e => { if (e.target === scrim) this.wallSecondary(true); });
  box.addEventListener('keydown', e => {
   if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); this.closeWall(); return; }
   if (e.key !== 'Tab') return;
   const items = [...box.querySelectorAll('button, input, select, [tabindex="0"]')].filter(n => !n.disabled && n.offsetParent !== null);
   if (!items.length) return;
   const first = items[0], last = items[items.length - 1];
   if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
   else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  document.body.append(scrim);
  this.dlg = { scrim, box, art, img, badge, kicker, title, text, dims, chips, styles, warn, setup, prog, stage, pct, bar, fill, detail, ask, askBox, keep, go };
  return this.dlg;
 },
 async openWall(source, manual) {
  const d = this.dialog(), busy = this.wall && ['prepare', 'models', 'run'].includes(this.wall.phase);
  if (busy) { this.showWall(); this.paintWall(); return; }
  let url = '';
  if (source.kind === 'local') { try { url = localStorage.getItem(WALL_KEY) || ''; } catch {} }
  else url = '/api/wallpaper/file/' + source.file;
  if (!url) return;
  const w = this.wall = { source, url, w: 0, h: 0, phase: 'ask', manual: !!manual, error: '' };
  if (!this.wallStyle) this.wallStyle = ['photo', 'fast', 'art'].includes(S.aiWallModel72) ? S.aiWallModel72 : '';
  d.img.src = url;
  this.showWall(); this.paintWall();
  const size = await this.measure(url).catch(() => null);
  if (this.wall === w && size) { w.w = size[0]; w.h = size[1]; this.paintWall(); }
  this.status().then(() => { if (this.wall === w) this.paintWall(); }).catch(e => { if (this.wall === w) { w.error = e.message; this.paintWall(); } });
 },
 showWall() {
  const d = this.dialog();
  if (!d.scrim.hidden && d.scrim.classList.contains('on')) return;
  this.returnFocus = document.activeElement;
  clearTimeout(this.hideTimer);
  d.scrim.hidden = false;
  requestAnimationFrame(() => requestAnimationFrame(() => d.scrim.classList.add('on')));
  setTimeout(() => { if (!d.go.disabled) d.go.focus({ preventScroll: true }); else d.box.focus({ preventScroll: true }); }, 30);
 },
 closeWall() {
  const d = this.dlg, w = this.wall; if (!d || d.scrim.hidden) return;
  if (w && ['prepare', 'models', 'run'].includes(w.phase)) toast(this.T('AI keeps working in the background. The wallpaper changes when it is ready.'), 4200);
  d.scrim.classList.remove('on');
  this.hideTimer = setTimeout(() => { d.scrim.hidden = true; }, this.reduced() ? 0 : 220);
  const back = this.returnFocus; this.returnFocus = null;
  if (back && back.isConnected) try { back.focus({ preventScroll: true }); } catch {}
  if (w && ['ask', 'done', 'error'].includes(w.phase)) this.wall = null;
 },
 wallSecondary(outside) {
  const w = this.wall; if (!w) { this.closeWall(); return; }
  if (w.phase === 'prepare' || w.phase === 'models') { if (outside) { this.closeWall(); return; } w.cancelled = true; w.phase = 'ask'; this.paintWall(); return; }
  if (w.phase === 'run') {
   if (outside) { this.closeWall(); return; }
   const id = w.job && w.job.id; this.dlg.keep.disabled = true;
   api('/api/ai/jobs/' + id, { method: 'DELETE' }).catch(() => {}).finally(() => { if (this.wall === w) { w.phase = 'ask'; w.job = null; this.paintWall(); } });
   return;
  }
  if (w.phase === 'done' && !outside) this.restore(w.source);
  this.closeWall();
 },
 wallPrimary() {
  const w = this.wall; if (!w) return;
  if (['prepare', 'models', 'run'].includes(w.phase) || w.phase === 'done') { this.closeWall(); return; }
  this.wallGo();
 },
 async wallGo() {
  const w = this.wall; if (!w || !this.info || !this.engine().installed) return;
  const style = this.wallStyle || (this.engine().cuda ? 'photo' : 'fast');
  this.wallStyle = style; S.aiWallModel72 = style; saveSettings(true);
  Object.assign(w, { phase: 'prepare', error: '', cancelled: false, done: 0, total: 0 });
  this.paintWall();
  try {
   await this.ensureModels([this.MODEL[style]], (done, total) => { if (this.wall === w && !w.cancelled) { Object.assign(w, { phase: 'models', done, total }); this.paintWall(); } }, () => this.wall !== w || w.cancelled);
   if (this.wall !== w || w.cancelled) return;
   const target = (this.outSize(w.w || 1, w.h || 1) || {}).target || 2560;
   let job;
   if (w.source.kind === 'local') {
    if (this.wallSig() !== w.source.sig) throw new Error(this.T('The wallpaper changed. Choose it again.'));
    const blob = await (await fetch(localStorage.getItem(WALL_KEY) || '')).blob();
    job = await this.postImage('/api/ai/wallpaper?model=' + style + '&target=' + target, blob);
   } else job = await api('/api/ai/wallpaper', { method: 'POST', body: { file: w.source.file, model: style, target } });
   if (this.wall !== w || w.cancelled) { if (job && job.id) api('/api/ai/jobs/' + job.id, { method: 'DELETE' }).catch(() => {}); return; }
   Object.assign(w, { phase: 'run', job });
   this.follow(job);
  } catch (e) {
   if (this.wall !== w || e.cancelled) return;
   if (e.data && e.data.code === 'engine') { await this.status('probe').catch(() => {}); w.phase = 'ask'; }
   else w.phase = 'error';
   w.error = e.message;
  }
  this.paintWall();
 },
 async postImage(url, blob) {
  const type = blob.type && blob.type.startsWith('image/') ? blob.type : 'image/jpeg';
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': type }, body: blob });
  let data = {}; try { data = await res.json(); } catch {}
  if (!res.ok) { const e = new Error(this.P(data.error || 'HTTP ' + res.status)); e.status = res.status; e.data = data; throw e; }
  return data;
 },
 wallFinished(job) {
  const w = this.wall && this.wall.job && this.wall.job.id === job.id ? this.wall : null;
  if (job.stage === 'done' && job.file) {
   const from = w ? w.source : job.original === 'local' ? { kind: 'local', sig: this.wallSig() } : { kind: 'file', file: job.original };
   const results = this.results(), o = job.options || {};
   results[job.file] = { from, model: o.model, w: o.out_width, h: o.out_height, at: Date.now() };
   const keys = Object.keys(results).sort((a, b) => (results[a].at || 0) - (results[b].at || 0));
   for (const k of keys.slice(0, Math.max(0, keys.length - 24))) delete results[k];
   this.write(this.STORE_WALL, results);
   const apply = () => Wall.select('/api/wallpaper/file/' + job.file);
   if (this.sameSource(this.current(), from)) {
    apply();
    toastAction(this.T('Wallpaper enhanced with AI · Undo'), () => this.restore(from), 8000);
   } else toastAction(this.T('The enhanced wallpaper is ready · Apply'), apply, 9000);
   if (w) { w.phase = 'done'; this.paintWall(); setTimeout(() => { if (this.wall === w) this.closeWall(); }, 1400); }
   this.paintWallRow();
  } else if (w) {
   w.phase = job.stage === 'cancelled' ? 'ask' : 'error'; w.error = job.error ? this.P(job.error) : ''; w.job = null;
   if (job.stage !== 'cancelled' && this.dlg && this.dlg.scrim.hidden) toast(this.T('Could not enhance the wallpaper') + (w.error ? ': ' + w.error : ''), 7000);
   this.paintWall();
  } else if (job.stage === 'error') toast(this.T('Could not enhance the wallpaper') + (job.error ? ': ' + this.P(job.error) : ''), 7000);
 },
 paintWall() {
  const d = this.dlg, w = this.wall; if (!d || !w) return;
  const T = x => this.T(x), installed = !!this.engine().installed, phase = w.phase;
  const busy = ['prepare', 'models', 'run'].includes(phase), needInstall = !!this.info && !installed;
  d.box.dataset.phase72 = phase;
  d.kicker.lastChild.textContent = T('AI enhancement') + ' · ' + T('Needs a powerful PC');
  d.title.textContent = phase === 'done' ? T('Wallpaper enhanced') : busy ? T('Enhancing the wallpaper…') : T('Enhance the wallpaper with AI?');
  d.text.textContent = T('Real-ESRGAN redraws the picture at a higher resolution: sharper details, less blur and fewer compression artefacts. Or keep the image exactly as it is.');
  const out = w.w ? this.outSize(w.w, w.h) : null;
  d.dims.textContent = out ? w.w + ' × ' + w.h + '  →  ' + out.w + ' × ' + out.h + (out.f <= 1.01 ? ' · ' + T('same size, cleaner details') : ' · ×' + out.f.toFixed(1)) : '';
  d.badge.textContent = out ? (out.f <= 1.01 ? 'AI' : '×' + out.f.toFixed(1)) : 'AI';
  const style = this.wallStyle || (this.engine().cuda ? 'photo' : 'fast');
  for (const [id, name, hint] of this.WALL_STYLES) {
   const c = d.styles[id]; c.firstChild.textContent = T(name); c.lastChild.textContent = T(hint);
   c.setAttribute('aria-checked', String(style === id)); c.disabled = busy;
  }
  d.chips.setAttribute('aria-label', T('AI model'));
  d.chips.hidden = needInstall;
  d.warn.textContent = this.warnText('image'); d.warn.className = 'ai72-warn ai72-' + this.level();
  if (needInstall && !d.setup.firstChild) d.setup.append(this.installBox(() => this.paintWall()));
  if (!needInstall && d.setup.firstChild) d.setup.replaceChildren();
  // Progress
  let stage = '', ratio = null, detail = '';
  if (phase === 'prepare') stage = T('Preparing…');
  else if (phase === 'models') { stage = T('Downloading AI models'); ratio = w.total ? w.done / w.total : null; detail = w.total ? this.mb(w.done) + ' / ' + this.mb(w.total) : ''; }
  else if (phase === 'run') {
   const job = (w.job && this.jobs[w.job.id]) || w.job || {};
   stage = T(this.STAGES[job.stage] || 'Working…');
   if (job.stage === 'processing' && job.total) { ratio = job.done / job.total; detail = this.F('{done} / {total} parts', { done: job.done || 0, total: job.total }) + (job.eta != null ? ' · ' + this.F('{time} left', { time: this.eta(job.eta) }) : ''); }
   if (job.stage === 'saving') ratio = 1;
  } else if (phase === 'done') { stage = T('Done'); ratio = 1; }
  else if (phase === 'error') stage = T('Could not enhance the wallpaper');
  d.prog.hidden = !(busy || phase === 'done' || phase === 'error');
  d.prog.classList.toggle('ai72-failed', phase === 'error');
  d.stage.textContent = stage;
  d.pct.textContent = ratio == null || phase === 'error' ? '' : Math.floor(ratio * 100) + '%';
  d.fill.style.transform = 'scaleX(' + (ratio == null ? 1 : Math.max(.02, Math.min(1, ratio))) + ')';
  d.bar.classList.toggle('ai72-indet', ratio == null && busy);
  d.bar.hidden = phase === 'error';
  d.detail.textContent = phase === 'error' ? w.error : detail;
  d.art.classList.toggle('ai72-working', busy);
  d.art.classList.toggle('ai72-done', phase === 'done');
  d.ask.hidden = busy || phase === 'done';
  d.askBox.checked = S.aiWallAsk72 === false;
  d.ask.lastChild.textContent = T('Don’t ask when I set a wallpaper');
  this.text(d.keep, busy ? T('Cancel') : phase === 'done' ? T('Restore original') : T('Keep as is'));
  d.keep.disabled = false;
  this.text(d.go, busy ? T('Hide') : phase === 'done' ? T('Done') : phase === 'error' ? T('Try again') : T('Enhance with AI'));
  d.go.classList.toggle('ai72-go-hide', busy);
  d.go.disabled = !busy && phase !== 'done' && (!this.info || needInstall || !w.w);
  if (phase === 'ask' && w.error) { d.prog.hidden = false; d.bar.hidden = true; d.stage.textContent = ''; d.detail.textContent = w.error; }
 },

 /* ---------- Language */
 hookLang() {
  if (typeof App === 'undefined' || !App.afterLangChange) return;
  const lang = App.afterLangChange.bind(App);
  App.afterLangChange = (...a) => { const r = lang(...a); try { this.labels(); } catch (e) { console.error('AI72.labels', e); } return r; };
 },
 labels() {
  this.paintWallRow();
  if (this.page) this.renderPage();
  if (this.dlg && this.wall) this.paintWall();
 }
};
const boot72ai = App.boot.bind(App);
App.boot = async function (...a) { await boot72ai(...a); try { AI72.init(); } catch (e) { console.error('AI72.init', e); } };
