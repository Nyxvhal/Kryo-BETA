/* v73 interface: search layout, button motion, player sweep helpers.
   Search: on «All» the songs come right after the top result (the first eight,
   «Show all tracks» opens the Tracks tab); artists, albums and playlists
   follow. Before, four shelves stood between the top result and the songs,
   so at 1280×720 the first song was ~1100 px below the fold. The source chips
   and «Filters and sorting» share one row; the TikTok entry joins the action
   row; the duplicate «N tracks loaded» counter is gone. */
'use strict';
const UI73 = {
 t(en) { return typeof t === 'function' ? t(en) : en; },
 el(tag, cls, text) { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; },
 reduced() { return (typeof S !== 'undefined' && S.noAnim) || matchMedia('(prefers-reduced-motion: reduce)').matches; },
};

const Search73 = {
 ready: false, PREVIEW: 8,
 init() {
  if (this.ready || typeof App === 'undefined' || !$('vSearch') || !$('sTracks') || !$('sAuthors')) return;
  this.ready = true;
  document.body.classList.add('search-v73');
  const all = UI73.el('button', 'btn g s73-alltracks'); all.id = 'sAllTracks73'; all.type = 'button'; all.hidden = true;
  all.onclick = () => { App.setSearchTab('tracks'); requestAnimationFrame(() => $('sTracks')?.querySelector('[data-id]')?.scrollIntoView({ block: 'nearest' })); };
  $('sAuthors').before($('sTracksH'), $('sTracks'), all, $('sMore'));
  this.tidy();
  const render = App.renderSearchState.bind(App);
  App.renderSearchState = (...args) => { const out = render(...args); this.paint(); return out; };
  this.paint();
 },
 // The TikTok entry and the filter row are built by other modules, sometimes
 // after this one: put them in place whenever the results repaint.
 tidy() {
  const acts = $('searchActions26'), tiktok = $('searchTikTok39');
  if (acts && tiktok && tiktok.parentElement !== acts) acts.appendChild(tiktok);
  const chips = $('searchSources26'), toggle = $('studioFilterToggle');
  if (chips && toggle && !chips.closest('.s73-filterbar')) {
   const bar = UI73.el('div', 's73-filterbar'); chips.before(bar); bar.append(chips, toggle);
  }
 },
 paint() {
  this.tidy();
  const tab = App.searchTab || 'all', view = $('vSearch');
  const total = typeof Studio !== 'undefined' && K.search ? Studio.filterTracks(K.search.tracks || []).length : 0;
  const compact = tab === 'all' && total > this.PREVIEW;
  view.classList.toggle('s73-all', tab === 'all');
  view.classList.toggle('s73-compact', compact);
  const all = $('sAllTracks73');
  if (all) {
   all.hidden = !compact;
   all.textContent = '';
   all.append(UI73.el('span', '', UI73.t('Show all tracks')), UI73.el('b', 's73-n', String(total)));
   all.setAttribute('aria-label', UI73.t('Show all tracks') + ': ' + total);
  }
 },
};

/* ---------- Wave lock: shuffle/repeat explain themselves instead of going dead.
   While Wave picks the order these buttons were natively disabled, so a click
   did nothing at all and the tooltip was often overwritten. Now they stay
   focusable and clickable, look dimmed (aria-disabled) and a click explains
   the reason with a one-tap way out: turning Wave off. */
const WaveLock73 = {
 IDS: ['pShuffle', 'pShuffleM', 'nShuffle', 'pRepeat', 'nRepeat'],
 ready: false, busy: false,
 init() {
  if (this.ready || typeof Wave61 === 'undefined') return;
  this.ready = true;
  const mo = new MutationObserver(() => this.sync());
  for (const id of this.IDS) { const b = $(id); if (b) mo.observe(b, { attributes: true, attributeFilter: ['disabled'] }); }
  document.addEventListener('click', event => {
   const b = event.target.closest && event.target.closest('.wave-locked73');
   if (!b || !Wave61.active) return;
   event.preventDefault(); event.stopImmediatePropagation();
   try { if (Motion73.on()) Motion73.gesture(b, true); } catch {}
   const repeat = /Repeat/.test(b.id);
   toastAction(UI73.t(repeat ? 'Wave chooses what plays next. Click here to turn Wave off and use repeat.'
                             : 'Wave chooses what plays next. Click here to turn Wave off and use shuffle.'), () => Wave61.stop(true), 6000);
  }, true);
  this.sync();
 },
 sync() {
  if (this.busy) return;
  this.busy = true;
  try {
   for (const id of this.IDS) {
    const b = $(id); if (!b) continue;
    const locked = !!Wave61.active;
    if (locked && b.disabled) b.disabled = false;
    b.classList.toggle('wave-locked73', locked);
    if (locked) b.setAttribute('aria-disabled', 'true'); else if (b.getAttribute('aria-disabled') === 'true') b.removeAttribute('aria-disabled');
   }
  } finally { this.busy = false; }
 },
};

/* ---------- Motion: ink ripple and small per-control gestures.
   CSS (polish-v73.css) does press/hover with the individual scale/translate
   properties; this part adds what CSS can't: a ripple from the pointer, the
   heart pop, next/prev nudges, the play/pause swap and a "locked" shake.
   Same switches as the rest of the motion: Settings → Animations, Motion: Off,
   prefers-reduced-motion, and nothing runs while the window is hidden. */
const Motion73 = {
 RIPPLE: '.btn, .chip, .ib, .nav, #pBtns button, #ctxMenu button, .set-nav-i, .ar-btn, .home-new-playlist, #nBtns button, #sceneTools30 .ib, #albumActions78 button, #albumTransport24 button, #albumTools24 button',
 GESTURE: '#pLike, #nLike, #pLikeM, #pNext, #nNext, #pNextM, #pPrev, #nPrev, #pPrevM, #pShuffle, #nShuffle, #pShuffleM, #pRepeat, #nRepeat, #sceneShuffle87, #sceneRepeat87, #sceneTranslate87, #karaokeMenuButton45, #albumQueue78, #albumPrev24, #albumNext24, #albumLyrics24, #s33Prev, #s33Next',
 EASE: 'cubic-bezier(.2, .8, .2, 1)',
 SPRING: 'cubic-bezier(.34, 1.56, .64, 1)',
 on() {
  if (typeof Motion47 !== 'undefined' && Motion47.allowed) return !!Motion47.allowed();
  return !S.noAnim && !matchMedia('(prefers-reduced-motion: reduce)').matches && !document.hidden;
 },
 k() { return document.body.dataset.motion48 === 'expressive' ? 1.45 : 1; },
 handles(b) { return !!(b && b.matches && document.body.classList.contains('motion-v73') && b.matches(this.RIPPLE)); },
 init() {
  document.body.classList.add('motion-v73');
  document.addEventListener('click', e => this.click(e), true);
  // Play/pause icons update immediately, without an opacity animation.
 },
 usable(b) { return b && !b.disabled && b.getAttribute('aria-disabled') !== 'true' && !b.closest('#clips'); },
 down(e) {
  if (e.button !== 0 || e.isPrimary === false || !e.target.closest) return;
  const b = e.target.closest(this.RIPPLE);
  if (!this.usable(b) || !this.on()) return;
  // Keep native immediate feedback without allocating a ripple on every click.
 },
 // A ripple needs a positioned box. A static button becomes relative only for
 // the ripple's lifetime, and only if none of its own children are absolutely
 // positioned (those keep the anchor they were laid out against).
 host(b) {
  if (b.classList.contains('rip73-host')) return true;
  if (getComputedStyle(b).position !== 'static') return true;
  for (const n of b.querySelectorAll('*')) {
   if (n.localName === 'rip-73' || n.closest('rip-73')) continue;
   const p = getComputedStyle(n).position;
   if (p === 'absolute' || p === 'fixed') return false;
  }
  b.classList.add('rip73-host');
  return true;
 },
 release(b, box) {
  box.remove();
  if (!b.querySelector(':scope > rip-73')) b.classList.remove('rip73-host');
 },
 ripple(b, e) {
  const r = b.getBoundingClientRect();
  if (!r.width || !r.height || !this.host(b)) return;
  const z = b.offsetWidth ? r.width / b.offsetWidth : 1;   // UI scale (CSS zoom)
  const w = r.width / z, h = r.height / z;
  const round = w <= 64 && Math.abs(w - h) < 6;              // icon buttons: from the centre
  const x = round ? w / 2 : Math.max(0, Math.min(w, (e.clientX - r.left) / z));
  const y = round ? h / 2 : Math.max(0, Math.min(h, (e.clientY - r.top) / z));
  const d = 2 * Math.hypot(Math.max(x, w - x), Math.max(y, h - y));
  const old = b.querySelectorAll(':scope > rip-73');
  if (old.length > 2) this.release(b, old[0]);
  const box = document.createElement('rip-73');
  box.setAttribute('aria-hidden', 'true');
  const dot = document.createElement('i');
  dot.style.cssText = `left:${x.toFixed(1)}px;top:${y.toFixed(1)}px;width:${d.toFixed(1)}px;height:${d.toFixed(1)}px`;
  box.append(dot);
  b.append(box);
  let gone = false;
  const done = () => { if (!gone) { gone = true; this.release(b, box); } };
  dot.addEventListener('animationend', done, { once: true });
  setTimeout(done, 900);
 },
 click(e) {
  if (!e.target.closest) return;
  const b = e.target.closest(this.GESTURE);
  if (!b || b.disabled || !this.on()) return;
  const locked = b.classList.contains('wave-locked73');
  if (/Like/.test(b.id) && !locked) return this.likeAfter(b, b.classList.contains('on'));
  setTimeout(() => { try { this.gesture(b, locked); } catch {} }, 0);   // after the app updated the state
 },
 // Liking can wait for storage, so the heart animates when its state flips.
 likeAfter(b, was) {
  const go = () => { try { this.gesture(b, false); } catch {} };
  if (b.classList.contains('on') !== was) return go();
  const mo = new MutationObserver(() => { if (b.classList.contains('on') !== was) { mo.disconnect(); clearTimeout(t); go(); } });
  const t = setTimeout(() => mo.disconnect(), 1500);
  mo.observe(b, { attributes: true, attributeFilter: ['class'] });
 },
 play(node, frames, ms, easing) {
  if (!node || !node.animate || !node.getClientRects().length) return null;
  return node.animate(frames, { duration: ms, easing: easing || this.EASE });
 },
 gesture(b, locked) {
  const ic = b.querySelector('.ic');
  const k = this.k(), id = b.id;
  if (locked) return this.play(ic, [{ translate: '0 0' }, { translate: '-3px 0' }, { translate: '3px 0' }, { translate: '-2px 0' }, { translate: '0 0' }], 340, 'ease-out');
  if (/Like/.test(id)) {
   if (b.classList.contains('on')) {
    this.play(ic, [{ scale: 1 + .3 * k, offset: .35 }, { scale: .92, offset: .7 }], 480);
    this.burst(b);
   } else this.play(ic, [{ scale: .78, offset: .4 }], 260);
  } else if (/Next/.test(id)) this.play(ic, [{ translate: (4 * k).toFixed(1) + 'px 0', offset: .35 }], 300);
  else if (/Prev/.test(id)) this.play(ic, [{ translate: (-4 * k).toFixed(1) + 'px 0', offset: .35 }], 300);
  else if (/Repeat/.test(id)) this.play(ic, [{ rotate: '-200deg', offset: 0 }], 520, this.SPRING);
  else this.play(ic, [{ scale: 1 + .2 * k, offset: .4 }], 320);
 },
 burst(b) {
  if (!b.getClientRects().length || !this.host(b)) return;
  const box = document.createElement('rip-73');
  box.className = 'burst73';
  box.setAttribute('aria-hidden', 'true');
  box.append(document.createElement('i'));
  b.append(box);
  let gone = false;
  const done = () => { if (!gone) { gone = true; this.release(b, box); } };
  box.firstChild.addEventListener('animationend', done, { once: true });
  setTimeout(done, 800);
 },
 // Play ⇄ pause: the icon swaps with a small spring instead of snapping.
 watchPlay() {
  const mo = new MutationObserver(list => {
   if (!this.on()) return;
   for (const m of list) {
    const now = m.target.getAttribute('href');
    if (!m.oldValue || m.oldValue === now) continue;
    this.play(m.target.closest('svg'), [{ scale: .55, opacity: .3, offset: 0 }], 260, this.SPRING);
   }
  });
  for (const id of ['pPlay', 'nPlay', 'pMobPlay']) {
   const b = $(id);
   if (b) mo.observe(b, { subtree: true, attributes: true, attributeFilter: ['href'], attributeOldValue: true });
  }
 },
};

/* ---------- boot */
(() => {
 const boot = () => {
  for (const [name, part] of [['search', Search73], ['wave lock', WaveLock73], ['motion', Motion73]]) {
   try { part.init(); } catch (err) { console.warn('[v73] ' + name, err); }
  }
 };
 if (document.readyState === 'complete') setTimeout(boot, 0);
 else addEventListener('load', () => setTimeout(boot, 0), { once: true });
})();
