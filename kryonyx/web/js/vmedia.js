/* vmedia.js — видео в караоке: аватарка трека и фон.

   Аватарка: вместо обложки крутится зацикленное беззвучное видео. Окно
   настройки — как у фото профиля в соцсети: форма, перетаскивание, масштаб
   и отрезок, который будет повторяться. Работает там, где есть обложка
   («Обложка и текст», «Визуализатор»; «Диск» — это диск, там её нет).
   Фон: одно видео за плеером во всех режимах, с затемнением и размытием.

   Сами файлы лежат в IndexedDB браузера (видео слишком велики для
   localStorage), настройки кадра — в localStorage. Наружу ничего не уходит. */
'use strict';

const VM_CFG = 'kryonyx.vav';
const VM_BG = 'kryonyx.vbg';

const VMedia = {
  db: null, seq: 0, sig: '', urls: {}, vids: {}, ro: null, bgUrl: '', ed: null,

  /* ---------------------------------------------------------- хранилище */
  open() {
    if (!this.db) {
      this.db = new Promise((ok, fail) => {
        try {
          const r = indexedDB.open('kryonyx-media', 1);
          r.onupgradeneeded = () => r.result.createObjectStore('f');
          r.onsuccess = () => ok(r.result);
          r.onerror = () => fail(r.error);
        } catch (e) { fail(e); }
      });
    }
    return this.db;
  },
  async tx(mode, fn) {
    const db = await this.open();
    return new Promise((ok, fail) => {
      const req = fn(db.transaction('f', mode).objectStore('f'));
      req.onsuccess = () => ok(req.result);
      req.onerror = () => fail(req.error);
    });
  },
  get(key) { return this.tx('readonly', s => s.get(key)).catch(() => null); },
  put(key, blob) { return this.tx('readwrite', s => s.put(blob, key)); },
  del(key) { return this.tx('readwrite', s => s.delete(key)).catch(() => {}); },

  cfgAll() { try { return JSON.parse(localStorage.getItem(VM_CFG) || '{}') || {}; } catch { return {}; } },
  cfgSave(all) { try { localStorage.setItem(VM_CFG, JSON.stringify(all)); } catch {} },
  keyFor(track) {
    const all = this.cfgAll();
    if (track && all[track.id]) return track.id;
    return all['*'] ? '*' : null;
  },
  norm(c) {
    c = c || {};
    return {
      zoom: Math.min(4, Math.max(1, +c.zoom || 1)),
      x: Math.min(1, Math.max(-1, +c.x || 0)),
      y: Math.min(1, Math.max(-1, +c.y || 0)),
      shape: ['circle', 'round', 'square'].includes(c.shape) ? c.shape : 'round',
      start: Math.max(0, +c.start || 0), end: Math.max(0, +c.end || 0), v: c.v || 0,
    };
  },

  /* ------------------------------------------------- расстановка кадра */
  /* Видео занимает «обложку» целиком (как cover), затем масштаб и сдвиг;
     x и y — доля от запаса, который даёт масштаб (−1…1). */
  place(video, box, cfg) {
    const bw = box.clientWidth, bh = box.clientHeight;
    if (!bw || !bh || !video.videoWidth) return;
    const a = video.videoWidth / video.videoHeight;
    let w, h;
    if (a >= bw / bh) { h = bh; w = bh * a; } else { w = bw; h = bw / a; }
    w *= cfg.zoom; h *= cfg.zoom;
    const mx = Math.max(0, (w - bw) / 2), my = Math.max(0, (h - bh) / 2);
    video.style.width = w + 'px'; video.style.height = h + 'px';
    video.style.transform =
      `translate(calc(-50% + ${(cfg.x * mx).toFixed(1)}px), calc(-50% + ${(cfg.y * my).toFixed(1)}px))`;
    return { mx, my };
  },

  mkVideo(url, cfg, box) {
    const v = document.createElement('video');
    v.muted = true; v.loop = true; v.playsInline = true; v.preload = 'auto';
    v.disablePictureInPicture = true; v.setAttribute('muted', '');
    v.src = url;
    v._cfg = cfg;
    v.addEventListener('loadedmetadata', () => this.place(v, box, v._cfg));
    return v;
  },

  /* --------------------------------------------- аватарка на экране */
  targets() {
    const out = [];
    const left = $('nowLeft'), art = $('nArt');
    if (left && art) out.push({ name: 'split', host: left, before: art, img: art });
    const vz = document.querySelector('.viz-art');
    if (vz) out.push({ name: 'viz', host: vz, before: vz.firstChild, img: $('vizArt') });
    return out;
  },

  clearAvatar() {
    this.sig = '';
    Object.values(this.vids).forEach(v => {
      try { v.pause(); } catch {}
      if (v._box) v._box.remove();
    });
    this.vids = {};
    Object.values(this.urls).forEach(u => URL.revokeObjectURL(u));
    this.urls = {};
    document.querySelectorAll('.has-vav').forEach(n => n.classList.remove('has-vav', 'sh-circle', 'sh-round', 'sh-square'));
  },

  async paintTrack() {
    const track = (typeof Player !== 'undefined') ? Player.current : null;
    const my = ++this.seq;
    const key = this.keyFor(track);
    if (!key) { if (this.sig) this.clearAvatar(); return; }
    const cfg = this.norm(this.cfgAll()[key]);
    const sig = key + ':' + cfg.v;
    const tg = this.targets();
    const mounted = tg.every(x => this.vids[x.name] && this.vids[x.name]._box.isConnected);
    if (sig === this.sig && mounted) { this.apply(cfg); return; }
    const blob = await this.get('av:' + key);
    if (my !== this.seq) return;
    if (!blob) { this.clearAvatar(); return; }
    this.clearAvatar();
    this.sig = sig;
    const url = URL.createObjectURL(blob);
    this.urls.main = url;
    this.mount(cfg);
  },

  mount(cfg) {
    this.targets().forEach(x => {
      const box = el('div', 'vav-box vav-' + x.name);
      const v = this.mkVideo(this.urls.main, cfg, box);
      v._box = box;
      box.appendChild(v);
      if (x.name === 'split') x.host.insertBefore(box, x.before);
      else x.host.insertBefore(box, x.before);
      x.host.classList.add('has-vav');
      this.vids[x.name] = v;
      if (!this.ro) this.ro = new ResizeObserver(entries => entries.forEach(e => {
        const vv = Object.values(this.vids).find(q => q._box === e.target);
        if (vv) this.place(vv, vv._box, vv._cfg);
      }));
      this.ro.observe(box);
    });
    this.apply(cfg);
  },

  apply(cfg) {
    Object.values(this.vids).forEach(v => {
      v._cfg = cfg;
      v._box.parentElement.classList.remove('sh-circle', 'sh-round', 'sh-square');
      v._box.parentElement.classList.add('sh-' + cfg.shape);
      this.place(v, v._box, cfg);
    });
    this.tick();
  },

  /* Одна проверка в 100 мс: играет ли видео и не вышло ли за отрезок. */
  tick() {
    const now = $('now');
    const open = !!(now && now.classList.contains('on')) && !document.hidden;
    const playing = !!(typeof Player !== 'undefined' && Player.audio && !Player.audio.paused);
    const go = open && playing;
    Object.values(this.vids).forEach(v => {
      const c = v._cfg || {};
      const show = go && v._box.offsetParent !== null;     // скрытые режимы не крутим
      if (show && v.paused) v.play().catch(() => {});
      else if (!show && !v.paused) v.pause();
      if (v.duration && c.end > c.start && (v.currentTime >= c.end || v.currentTime < c.start - 0.3)) {
        v.currentTime = c.start;
      }
    });
    const bg = $('nowVid');
    if (bg && document.body.classList.contains('k-vbg')) {
      if (go && bg.paused) bg.play().catch(() => {});
      else if (!go && !bg.paused) bg.pause();
    }
  },

  /* ----------------------------------------------------------------- фон */
  async applyBg() {
    const revision = this.bgRevision46 = (this.bgRevision46 || 0) + 1;
    const bg = $('nowVid');
    if (!bg) return;
    const has = !!this.cfgBg();
    const on = !!S.vbgOn && has;
    const root = document.documentElement.style;
    root.setProperty('--vb-fit', (S.vbgFit || 'cover') === 'contain' ? 'contain' : 'cover');
    root.setProperty('--vb-blur', (+S.vbgBlur || 0) + 'px');
    root.setProperty('--vb-bright', (1 - Math.max(0, Math.min(90, S.vbgDim == null ? 35 : +S.vbgDim)) / 100).toFixed(2));
    root.setProperty('--vb-scale', (+S.vbgBlur || 0) > 0 ? '1.08' : '1');
    document.body.classList.toggle('k-vbg', on);
    if (!on) { bg.pause(); return; }
    const sig = this.cfgBg();
    if (this._bgSig !== sig) {
      const blob = await this.get('bg');
      if (revision !== this.bgRevision46 || !S.vbgOn || sig !== this.cfgBg()) return;
      if (!blob) { document.body.classList.remove('k-vbg'); return; }
      if (this.bgUrl) URL.revokeObjectURL(this.bgUrl);
      this.bgUrl = URL.createObjectURL(blob);
      this._bgSig = sig;
      bg.muted = true; bg.loop = true;
      bg.src = this.bgUrl;
    }
    this.tick();
  },
  cfgBg() { try { return localStorage.getItem(VM_BG) || ''; } catch { return ''; } },

  async pickBg(file) {
    if (!file) return;
    if (!/^video\//.test(file.type) && !/\.(mp4|webm|mov|m4v|mkv|ogv)$/i.test(file.name)) {
      toast(t('This is not a video')); return;
    }
    try {
      await this.put('bg', file);
      localStorage.setItem(VM_BG, String(Date.now()));
    } catch { toast(t('Could not save the video')); return; }
    S.vbgOn = true; saveSettings();
    this._bgSig = '';
    this.applyBg(); this.build();
    toast(t('Background video set'));
  },
  async clearBg() {
    await this.del('bg');
    try { localStorage.removeItem(VM_BG); } catch {}
    S.vbgOn = false; saveSettings();
    this._bgSig = '';
    this.applyBg(); this.build();
  },

  /* ---------------------------------------------- окно «Видео-аватар» */
  async openEditor() {
    const track = Player.current;
    const own = track && this.cfgAll()[track.id];
    const glob = this.cfgAll()['*'];
    this.ed = {
      track, file: null, url: '', all: !track || (!own && !!glob),
      cfg: this.norm(own || glob || {}), dur: 0,
    };
    const ed = this.ed;
    if (!track && !glob) { toast(t('Play a track first')); this.ed = null; return; }
    $('vavSub').textContent = ed.all ? t('For all tracks') : (track.title + ' — ' + track.artist);
    const key = own ? track.id : (glob ? '*' : null);
    if (key) {
      const blob = await this.get('av:' + key);
      if (blob) { ed.blob = blob; ed.url = URL.createObjectURL(blob); }
    }
    openModal('mVav');
    this.edDraw();
  },

  edLoad(file) {
    if (!file) return;
    if (!/^video\//.test(file.type) && !/\.(mp4|webm|mov|m4v|mkv|ogv)$/i.test(file.name)) {
      toast(t('This is not a video')); return;
    }
    const ed = this.ed;
    if (!ed) return;
    if (ed.url) URL.revokeObjectURL(ed.url);
    ed.blob = file; ed.url = URL.createObjectURL(file);
    ed.cfg = this.norm({ shape: ed.cfg.shape });
    this.edDraw();
  },

  edDraw() {
    const ed = this.ed;
    if (!ed) return;
    const box = $('vavBox'), mask = $('vavMask');
    box.innerHTML = '';
    mask.className = 'vav-mask sh-' + ed.cfg.shape;
    $('vavEmpty').style.display = ed.url ? 'none' : '';
    $('vavCrop').classList.toggle('empty', !ed.url);
    if (ed.url) {
      const v = this.mkVideo(ed.url, ed.cfg, box);
      v.addEventListener('loadedmetadata', () => {
        ed.dur = v.duration || 0;
        if (!ed.cfg.end || ed.cfg.end > ed.dur) ed.cfg.end = ed.dur;
        this.edSync();
      });
      box.appendChild(v);
      v.play().catch(() => {});
      ed.vid = v;
    }
    this.edSync();
  },

  edSync() {
    const ed = this.ed;
    if (!ed) return;
    const c = ed.cfg;
    if (ed.vid) { ed.vid._cfg = c; this.place(ed.vid, $('vavBox'), c); }
    $('vavMask').className = 'vav-mask sh-' + c.shape;
    document.querySelectorAll('#vavShape .chip').forEach(n => n.classList.toggle('on', n.dataset.v === c.shape));
    const set = (id, v) => { const n = $(id); if (n && n !== document.activeElement) n.value = v; };
    set('vavZoom', Math.round(c.zoom * 100));
    $('vavZoomV').textContent = Math.round(c.zoom * 100) + ' %';
    const d = ed.dur || 0;
    ['vavFrom', 'vavTo'].forEach(id => { $(id).max = d.toFixed(1); $(id).disabled = !d; });
    set('vavFrom', c.start); set('vavTo', c.end || d);
    const fmt = s => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');
    $('vavFromV').textContent = fmt(c.start);
    $('vavToV').textContent = fmt(c.end || d);
    $('vavAll').classList.toggle('on', ed.all);
    $('vavRemove').style.display = this.keyForEdit() ? '' : 'none';
  },
  keyForEdit() {
    const ed = this.ed, all = this.cfgAll();
    return ed && ((ed.track && all[ed.track.id]) || all['*']);
  },

  async edSave() {
    const ed = this.ed;
    if (!ed || !ed.blob) { toast(t('Choose a video first')); return; }
    const key = ed.all ? '*' : (ed.track && ed.track.id);
    if (!key) { toast(t('Play a track first')); return; }
    const c = ed.cfg;
    const full = !ed.dur || (c.start <= 0.05 && c.end >= ed.dur - 0.05);
    const cfg = { zoom: c.zoom, x: c.x, y: c.y, shape: c.shape,
                  start: full ? 0 : c.start, end: full ? 0 : c.end, v: Date.now() };
    try { await this.put('av:' + key, ed.blob); }
    catch { toast(t('Could not save the video')); return; }
    const all = this.cfgAll(); all[key] = cfg; this.cfgSave(all);
    this.edClose();
    this.sig = '';
    this.paintTrack();
    toast(t('Video avatar saved'));
    this.build();
  },

  async edRemove() {
    const ed = this.ed;
    if (!ed) return;
    const all = this.cfgAll();
    const key = (ed.track && all[ed.track.id]) ? ed.track.id : '*';
    delete all[key]; this.cfgSave(all);
    await this.del('av:' + key);
    this.edClose();
    this.clearAvatar();
    this.paintTrack();
    toast(t('Video avatar removed'));
    this.build();
  },

  edClose() {
    const ed = this.ed;
    if (ed && ed.url) URL.revokeObjectURL(ed.url);
    this.ed = null;
    $('vavBox').innerHTML = '';
    closeModals();
  },

  /* ------------------------------------------------------------- панель */
  build() {
    const chips = (id, key, options, after) => {
      const host = $(id);
      if (!host) return;
      host.innerHTML = '';
      options.forEach(([value, label]) => {
        const chip = el('button', 'chip' + ((S[key] || options[0][0]) === value ? ' on' : ''), t(label));
        chip.onclick = () => { S[key] = value; saveSettings(); this.build(); if (after) after(); };
        host.appendChild(chip);
      });
    };
    chips('vbgFit', 'vbgFit', [['cover', 'Fill'], ['contain', 'Fit']], () => this.applyBg());
    const has = !!this.cfgBg();
    const val = (id, v) => { const n = $(id); if (n && n !== document.activeElement) n.value = v; };
    const txt = (id, v) => { const n = $(id); if (n) n.textContent = v; };
    val('sVbgBlur', S.vbgBlur || 0); txt('vVbgBlur', S.vbgBlur || 0);
    val('sVbgDim', S.vbgDim == null ? 35 : S.vbgDim); txt('vVbgDim', S.vbgDim == null ? 35 : S.vbgDim);
    const clr = $('vbgClear'); if (clr) clr.style.display = has ? '' : 'none';
    const tr = Player.current, all = this.cfgAll();
    const state = $('vavState');
    if (state) state.textContent = (tr && all[tr.id]) ? t('This track has a video avatar')
      : (all['*'] ? t('Video avatar is set for all tracks') : t('No video avatar yet'));
  },

  bind() {
    const pick = (btn, input, fn) => {
      const b = $(btn), i = $(input);
      if (b && i) b.onclick = () => i.click();
      if (i) i.onchange = e => { const f = e.target.files && e.target.files[0]; e.target.value = ''; fn(f); };
    };
    pick('vbgPick', 'vbgFile', f => this.pickBg(f));
    $('vbgClear').onclick = () => this.clearBg();
    const range = (id, key) => {
      const n = $(id);
      n.oninput = () => { S[key] = +n.value; this.applyBg(); this.build(); };
      n.onchange = () => saveSettings();
    };
    range('sVbgBlur', 'vbgBlur'); range('sVbgDim', 'vbgDim');
    $('vavOpen').onclick = () => this.openEditor();

    // Окно редактора.
    pick('vavPick', 'vavFile', f => this.edLoad(f));
    $('vavEmpty').onclick = () => $('vavFile').click();
    const shape = $('vavShape');
    [['circle', 'Circle'], ['round', 'Rounded'], ['square', 'Square']].forEach(([v, label]) => {
      const c = el('button', 'chip', t(label)); c.dataset.v = v;
      c.onclick = () => { if (this.ed) { this.ed.cfg.shape = v; this.edSync(); } };
      shape.appendChild(c);
    });
    $('vavZoom').oninput = e => { if (this.ed) { this.ed.cfg.zoom = +e.target.value / 100; this.edSync(); } };
    const seg = which => e => {
      const ed = this.ed; if (!ed) return;
      const v = +e.target.value, c = ed.cfg, d = ed.dur;
      if (which === 'from') c.start = Math.min(v, (c.end || d) - 0.5);
      else c.end = Math.max(v, c.start + 0.5);
      if (ed.vid) { ed.vid.currentTime = c.start; }
      this.edSync();
    };
    $('vavFrom').oninput = seg('from'); $('vavTo').oninput = seg('to');
    $('vavAll').onclick = () => { if (this.ed) { this.ed.all = !this.ed.all; this.edSync();
      $('vavSub').textContent = this.ed.all ? t('For all tracks') : (this.ed.track ? this.ed.track.title + ' — ' + this.ed.track.artist : ''); } };
    $('vavSave').onclick = () => this.edSave();
    $('vavRemove').onclick = () => this.edRemove();
    $('vavCancel').onclick = () => this.edClose();

    // Перетаскивание и колесо мыши по кадру.
    const crop = $('vavCrop');
    let drag = null;
    crop.addEventListener('pointerdown', e => {
      if (!this.ed || !this.ed.vid) return;
      drag = { x: e.clientX, y: e.clientY };
      crop.setPointerCapture(e.pointerId);
      crop.classList.add('drag');
    });
    crop.addEventListener('pointermove', e => {
      if (!drag || !this.ed || !this.ed.vid) return;
      const c = this.ed.cfg, v = this.ed.vid;
      const lim = this.place(v, $('vavBox'), c) || { mx: 0, my: 0 };
      if (lim.mx) c.x = Math.max(-1, Math.min(1, c.x + (e.clientX - drag.x) / lim.mx));
      if (lim.my) c.y = Math.max(-1, Math.min(1, c.y + (e.clientY - drag.y) / lim.my));
      drag = { x: e.clientX, y: e.clientY };
      this.edSync();
    });
    const end = () => { drag = null; crop.classList.remove('drag'); };
    crop.addEventListener('pointerup', end); crop.addEventListener('pointercancel', end);
    crop.addEventListener('wheel', e => {
      if (!this.ed || !this.ed.vid) return;
      e.preventDefault();
      const c = this.ed.cfg;
      c.zoom = Math.max(1, Math.min(4, c.zoom * (e.deltaY < 0 ? 1.06 : 0.94)));
      this.edSync();
    }, { passive: false });
    // Предпросмотр зацикливается по выбранному отрезку.
    setInterval(() => {
      const ed = this.ed;
      if (ed && ed.vid && ed.dur && ed.cfg.end > ed.cfg.start &&
          (ed.vid.currentTime >= ed.cfg.end || ed.vid.currentTime < ed.cfg.start - 0.3)) {
        ed.vid.currentTime = ed.cfg.start;
      }
      this.tick();
    }, 100);
    document.addEventListener('visibilitychange', () => this.tick());
    new MutationObserver(() => this.tick())
      .observe($('now'), { attributes: true, attributeFilter: ['class'] });
  },
};
