/* v73 performance: clip room scrubbing, ambient light budget and an automatic
   "video is stuttering" fallback. Media engine, downloads and the player audio
   graph are untouched; every change here is a wrapper that can be switched off
   with Settings → Animations / visual budget, and none of it runs outside the
   clip room.

   What was measured (Chromium, 1920×1080, fixture clip, ambient on):
   * dragging the seek bar issued a seek on every input event; each seek fired
     waiting → stall() → pause → busy overlay → play again, so the Play button
     and the "Buffering" overlay flickered on every pixel of the drag;
   * the ambient canvas was redrawn on every decoded video frame (up to 60/s on
     60 fps clips) plus once more on every seek;
   * two time tooltips (the global one and the clip one) followed the pointer
     over the clip seek bar, each forcing a layout per move (fixed in
     interface-v45.js). */
'use strict';
const Perf73 = {
 ready: false,
 level: 0,           // 0 normal · 1 lighter ambient · 2 ambient off + flat glass (this session only)
 auto: true,         // the stutter fallback can be undone for the session
 budget() { return typeof S !== 'undefined' && ['economy', 'quality'].includes(S.vizBudget51) ? S.vizBudget51 : 'auto'; },
 init() {
  if (this.ready) return;
  this.ready = true;
  const steps = [['settings', () => this.settings()]];
  if (typeof Clips !== 'undefined' && Clips.video) steps.push(['seek', () => this.seek()], ['stall', () => this.stall()], ['play label', () => this.playLabel()], ['ambient', () => this.ambient()], ['watchdog', () => this.watchdog()]);
  for (const [name, fn] of steps) {
   try { fn(); } catch (err) { console.warn('[perf73] ' + name, err); }
  }
 },

 /* ---------- 0. Settings: tab switches without forced layouts or gallery rebuilds.
    Two openPane wrappers (ui-v7, redesign-v52) scrolled the selected tab into
    view synchronously, each forcing a full style + layout pass in the middle
    of the click; and the ~3 500-node theme gallery was rebuilt from scratch
    every time its tab was opened, even when nothing had changed. */
 settings() {
  if (typeof App === 'undefined' || !App.openPane || App.openPane.perf73) return;
  const open = App.openPane.bind(App), proto = Element.prototype, native = proto.scrollIntoView;
  let want = null, frame = 0;
  const flush = () => { frame = 0; const w = want; want = null; if (w && w[0].isConnected) native.call(w[0], w[1]); };
  const wrapped = function (name, ...rest) {
   // Only the scroll of the settings tab list is postponed (and merged): it
   // runs in the next frame, after every wrapper has finished its DOM work.
   proto.scrollIntoView = function (arg) {
    if (this instanceof Element && this.closest('#setTabs')) { want = [this, arg]; return; }
    return native.apply(this, arguments);
   };
   Perf73.pane = name;
   try { return open(name, ...rest); }
   finally {
    proto.scrollIntoView = native; Perf73.pane = null;
    if (want && !frame) frame = requestAnimationFrame(flush);
   }
  };
  wrapped.perf73 = true;
  App.openPane = wrapped;
  if (typeof Themes !== 'undefined' && Themes.build && !Themes.build.perf73) {
   const build = Themes.build.bind(Themes);
   const sig = () => [Themes.group, Themes.query, typeof S !== 'undefined' ? S.theme : '', typeof LANG !== 'undefined' ? LANG : '',
    typeof THEME_LIBRARY !== 'undefined' ? Object.keys(THEME_LIBRARY).length : 0].join('|');
   const cached = function (...a) {
    const list = $('themeList');
    // Re-opening the tab with the same group, search, language and selected
    // theme shows the gallery that is already there.
    if (Perf73.pane === 'themes' && list && list.childElementCount && !Themes.dirty70 && Perf73.themeSig === sig()) return;
    const r = build(...a);
    Perf73.themeSig = Themes.dirty70 ? null : sig();
    return r;
   };
   cached.perf73 = true;
   Themes.build = cached;
   const openPaneWithThemes = App.openPane;
   App.openPane = function (name, ...rest) {
    const r = openPaneWithThemes.call(this, name, ...rest);
    if (name === 'themes' && Themes._deferredBuild) Themes.build();
    return r;
   };
  }
 },

 /* ---------- 1. Seeking: one seek in flight, the newest target wins */
 seek() {
  const v = Clips.video, input = $('clipSeek');
  if (!v || !input) return;
  const orig = Clips.seek.bind(Clips);
  this.pending = null;
  Clips.seek = at => {
   if (v.seeking && Number.isFinite(at)) { this.pending = at; Clips.paintTime(); return; }
   this.pending = null;
   return orig(at);
  };
  v.addEventListener('seeked', () => {
   if (this.pending == null) return;
   const at = this.pending; this.pending = null;
   if (Math.abs(v.currentTime - at) > .04) orig(at);
  });
 },

 /* ---------- 2. A seek is not a stall: no pause/overlay flicker while dragging */
 stall() {
  const orig = Clips.stall.bind(Clips), v = Clips.video;
  let later = 0;
  const dragging = () => typeof Clips69 !== 'undefined' && !!Clips69.drag;
  Clips.stall = media => {
   if (media && (media.seeking || dragging() || this.pending != null)) {
    clearTimeout(later);
    // Still starving once the seek settled → the normal buffering path.
    later = setTimeout(() => {
     if (Clips.active && Clips.wantPlay && !media.seeking && !dragging() && media.readyState < 3) orig(media);
    }, 450);
    return;
   }
   return orig(media);
  };
  v.addEventListener('seeked', () => {
   if (!Clips.active || !Clips.wantPlay || dragging()) return;
   clearTimeout(later);
   later = setTimeout(() => { if (Clips.active && Clips.wantPlay && !v.seeking && v.readyState < 3 && !v.paused) orig(v); }, 450);
  });
 },

  /* ---------- 2b. The Play/Pause label is rebuilt only when it changes
    ('playing' fires after every seek; each rebuild replaced two icons). */
 playLabel() {
  if (typeof Clips.paintPlay !== 'function') return;
  const orig = Clips.paintPlay.bind(Clips);
  let last = '';
  Clips.paintPlay = (...a) => {
   const key = [Clips.wantPlay ? 1 : 0, S.lang || '', Clips.track?.id || '', Clips.job?.video_url ? 1 : 0].join('|');
   if (key === last && $('clipPlay')?.childNodes.length) { if (typeof Watch58 !== 'undefined' && Watch58.ready) Watch58.show(); return; }
   last = key;
   return orig(...a);
  };
  this.relabel = () => { last = ''; };
  if (typeof App !== 'undefined' && App.afterLangChange) {
   const lang = App.afterLangChange.bind(App);
   App.afterLangChange = (...a) => { last = ''; return lang(...a); };
  }
 },

 /* ---------- 3. Ambient light: at most 30 redraws a second (12 on economy),
    none while a seek is in flight, one trailing draw so the light settles. */
 ambient() {
  const E = typeof Experience66 !== 'undefined' ? Experience66 : null;
  if (!E || typeof E.draw !== 'function') return;
  const draw = E.draw.bind(E);
  let at = 0, trail = 0;
  this.gap = () => this.level >= 1 || this.budget() === 'economy' ? 1000 / 12 : this.budget() === 'quality' ? 1000 / 60 : 1000 / 30;
  E.draw = function (...args) {
   const v = this.video;
   if (v && v.seeking) return;                         // the frame isn't new yet; 'seeked' draws it
   const now = performance.now(), gap = Perf73.gap();
   if (now - at < gap - 1) {
    // Playing video calls again on its next frame; a paused one needs one trailing draw.
    if (v && (v.paused || v.ended) && !trail) trail = setTimeout(() => { trail = 0; at = performance.now(); try { draw(); } catch {} }, gap - (now - at));
    return;
   }
   at = now;
   return draw(...args);
  };
  if (typeof E.on === 'function') {
   const on = E.on.bind(E);
   E.on = function () { return Perf73.level < 2 && on(); };
  }
  if (typeof E.fit === 'function') {
   const fit = E.fit.bind(E);
   E.fit = function () {
    if (Perf73.level < 1) return fit();
    if (this.canvas.width !== 192 || this.canvas.height !== 108) { this.canvas.width = 192; this.canvas.height = 108; }
   };
  }
 },

 /* ---------- 4. Watchdog: if the clip itself drops frames, lighten the room.
    Only while a clip plays in the watch view; checks every 2 s; two bad
    windows in a row are needed; at most two steps; one toast with Undo. */
 watchdog() {
  const v = Clips.video;
  if (!v || typeof v.getVideoPlaybackQuality !== 'function') return;
  let last = null, bad = 0;
  setInterval(() => {
   const watching = Clips.active && !document.hidden && !v.paused && !v.seeking && $('clips')?.dataset.videoMode57 === 'watch';
   if (!watching || !this.auto || S.noAnim) { last = null; bad = 0; return; }
   const q = v.getVideoPlaybackQuality(), now = { total: q.totalVideoFrames, dropped: q.droppedVideoFrames };
   if (last && now.total >= last.total) {
    const frames = now.total - last.total, dropped = now.dropped - last.dropped;
    if (frames >= 20 && dropped / frames > .12) bad++; else bad = Math.max(0, bad - 1);
    if (bad >= 2 && this.level < 2) { bad = 0; this.lighten(); }
   }
   last = now;
  }, 2000);
 },
 lighten() {
  this.level++;
  document.body.classList.toggle('clip-lite73', this.level >= 2);
  try { Experience66.fit?.(); Experience66.syncAmbient?.(); if (this.level >= 2) { Experience66.stop?.(); Experience66.clear?.(); } } catch {}
  if (this.level === 1 || this.level === 2 && !this.told) {
   this.told = true;
   const msg = UI73.t('The video was stuttering, so the background effects were made lighter.');
   toastAction(msg + ' ' + UI73.t('Click to undo.'), () => this.restore(), 7000);
  }
 },
 restore() {
  this.level = 0; this.auto = false;
  document.body.classList.remove('clip-lite73');
  try { Experience66.fit?.(); Experience66.syncAmbient?.(); Experience66.draw?.(); Experience66.schedule?.(); } catch {}
 },
};
if (typeof App !== 'undefined' && App.boot) {
 const boot73 = App.boot.bind(App);
 App.boot = async function (...a) { await boot73(...a); try { Perf73.init(); } catch (err) { console.warn('[perf73]', err); } };
}
