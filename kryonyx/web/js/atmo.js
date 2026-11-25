/* atmo.js — «атмосфера караоке»: тёмная сцена, цветной свет из обложки
   трека, который дышит в такт музыке.

   Оптимизация:
     * свет — три радиальных градиента без filter: blur (дешёвый композитинг);
     * за кадр меняются только две CSS-переменные на одном слое #atmo и на
       кнопке Play — остальной документ стили не пересчитывает;
     * 30 кадров в секунду, на паузе и в свёрнутом окне цикл стоит;
     * «Меньше анимаций» или системный prefers-reduced-motion — свет застывает. */
'use strict';

const Atmo = {
  root: null, raf: null, data: null,
  level: 0, beat: 0, avg: 0, last: 0,
  colors: null,

  init() {
    if (S.atmo === undefined) S.atmo = true;
    const root = el('div');
    root.id = 'atmo';
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = '<div class="atmo-pulse"><i class="atmo-l l1"></i><i class="atmo-l l2"></i>' +
      '<i class="atmo-l l3"></i></div><i class="atmo-beams"></i><i class="atmo-grain"></i><i class="atmo-vig"></i>';
    document.body.insertBefore(root, document.body.firstChild);
    this.root = root;
    this.play = $('pPlay');
    this.reduce = matchMedia('(prefers-reduced-motion: reduce)');
    this.apply();
    document.addEventListener('visibilitychange', () => this.kick());
    new MutationObserver(() => this.kick()).observe($('now'),{attributes:true,attributeFilter:['class']});
  },

  apply() {
    document.body.classList.toggle('atmo', !!S.atmo && !S.light);
    this.paint();
    this.kick();
  },

  /* Цвета берём из обложки (Karaoke уже вытаскивает палитру) или из темы. */
  setColors(list) {
    this.colors = list && list.length ? list : null;
    this.paint();
  },

  paint() {
    if (!this.root) return;
    const c = this.colors || [S.accent, S.accent2, S.accent];
    const st = this.root.style;
    st.setProperty('--c1', c[0]);
    st.setProperty('--c2', c[1] || c[0]);
    st.setProperty('--c3', c[2] || c[0]);
  },

  running() {
    if (!this.root) return false;                  // ещё не запущены
    return S.vizBudget51!=='economy'&&S.layout48?.quality!=='economy'&&!$('now')?.classList.contains('on') && !document.querySelector('.modal.on') && !!S.atmo && !S.light && !S.noAnim && !this.reduce.matches && !document.hidden &&
      Player.audio && !Player.audio.paused;
  },

  kick() {
    const running=this.running();
    this.root?.classList.toggle('atmo-sleep42',!running);
    if (running) { if (!this.raf) this.raf = requestAnimationFrame(t => this.loop(t)); return; }
    // Остановились — свет плавно гаснет до спокойного уровня.
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = null;
    this.set(0, 0);
  },

  loop(now) {
    if (!this.running()) { this.raf = null; this.set(0, 0); return; }
    this.raf = requestAnimationFrame(t => this.loop(t));
    if (now - this.last < (S.vizBudget51==='quality'?33:65)) return;              // ~30 кадров в секунду
    this.last = now;
    const an = Player.analyser;
    let bass = 0, energy = 0;
    if (an) {
      if (!this.data || this.data.length !== an.frequencyBinCount) this.data = new Uint8Array(an.frequencyBinCount);
      an.getByteFrequencyData(this.data);
      const n = this.data.length, bassN = Math.max(4, n >> 4);
      let sum = 0, low = 0;
      for (let i = 0; i < n; i += 2) { sum += this.data[i]; if (i < bassN) low += this.data[i]; }
      energy = sum / ((n >> 1) * 255);
      bass = low / ((bassN >> 1) * 255);
    }
    this.avg = this.avg * 0.93 + bass * 0.07;
    if (bass > this.avg * 1.3 && bass > 0.3) this.beat = 1;
    this.beat = Math.max(0, this.beat - 0.08);
    this.level += (energy - this.level) * 0.2;
    this.set(this.level, this.beat);
  },

  set(level, beat) {
    const l = Math.round(Math.min(1, level * 1.6) * 100) / 100;
    const b = Math.round(beat * 100) / 100;
    if (l === this._l && b === this._b) return;
    this._l = l; this._b = b;
    if (this.root) { this.root.style.setProperty('--lv', l); this.root.style.setProperty('--bt', b); }
    if (this.play) this.play.style.setProperty('--bt', b);
  },
};
