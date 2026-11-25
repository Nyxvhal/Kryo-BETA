/* viz.js — режим караоке «Визуализатор»: без текста песни.
   Слева обложка в светящейся рамке, справа название, исполнитель, шкала-
   спектр (она же перемотка) и кнопки; на фоне неоновые полосы и искры,
   которые живут в такт музыке. Кадры ведёт Player.tick через Karaoke.onTime,
   отдельного цикла нет. */
'use strict';

const Viz = {
  on: false,
  root: null, bg: null, ctx: null, spec: null, sctx: null, art: null,
  parts: [], hue: 200, w: 0, h: 0, sw: 0, sh: 0, beatPrev: 0, last: 0,
  /* t — собственные часы сцены в секундах. Они только растут и никогда
     не сбрасываются: раньше фазы брались из hue, а он замыкался на 360 —
     именно там полосы и сетка дёргались и «обрывали» цикл. */
  t: 0, dt: 1 / 60, k: 1,
  mood: null, bpm: 0, beatAt: 0, pulse: 0,

  build() {
    if (this.root) return;
    const now = $('now');
    if (!now) return;
    const root = el('div', 'viz-stage');
    root.id = 'vizStage';
    root.innerHTML =
      '<i class="viz-cover" id="vizCover"></i>' +
      '<canvas class="viz-bg" id="vizBg"></canvas>' +
      '<div class="viz-card">' +
        '<div class="viz-artwrap"><div class="viz-art"><img id="vizArt" alt="" draggable="false"></div></div>' +
        '<div class="viz-info">' +
          '<div class="viz-title" id="vizTitle"><span id="vizTitleIn"></span></div>' +
          '<div class="viz-artist" id="vizArtist"></div>' +
          '<div class="viz-row">' +
            '<div class="viz-time"><span class="tm" id="vCur">0:00</span>' +
              '<span class="viz-left" id="vLeft"></span>' +
              '<span class="tm" id="vDur">0:00</span></div>' +
            '<div class="viz-src" id="vSrc"></div>' +
          '</div>' +
          '<div class="viz-prog track" id="vProg" tabindex="0" role="slider" aria-label="' + esc(t('Seek')) + '" aria-valuemin="0" aria-valuemax="100"><div class="rail"></div><div class="buf" id="vBuf"></div><div class="fill" id="vFill"></div><div class="knob"></div><span class="viz-tip" id="vTip"></span></div>' +
          '<div class="viz-bar" id="vTrack" role="img" aria-label="' + esc(t('Audio spectrum')) + '">' +
            '<canvas id="vizSpectrumCanvas25"></canvas>' +

          '</div>' +
          '<div class="viz-frequency" aria-hidden="true"><span>30 Hz</span><span>250 Hz</span><span>2 kHz</span><span>18 kHz</span></div>' +
          '<div class="viz-ctl">' +
            '<button class="disc-b" data-a="like" title="' + esc(t('Like')) + '">' +
              '<svg class="ic"><use href="#i-heart"/></svg></button>' +
            '<button class="disc-b" data-a="prev" title="' + esc(t('Previous')) + '">' +
              '<svg class="ic f"><use href="#i-prev"/></svg></button>' +
            '<button class="disc-b disc-play" data-a="play" title="' + esc(t('Play')) + '">' +
              '<svg class="ic f"><use href="#i-play"/></svg></button>' +
            '<button class="disc-b" data-a="next" title="' + esc(t('Next')) + '">' +
              '<svg class="ic f"><use href="#i-next"/></svg></button>' +
            '<button class="disc-b" data-a="mix" title="' + esc(t('Mixer')) + ' (M)">' +
              '<svg class="ic"><use href="#i-mixer"/></svg></button>' +
            '<button class="disc-b" data-a="close" title="' + esc(t('Close')) + '">' +
              '<svg class="ic"><use href="#i-down"/></svg></button>' +
          '</div>' +
          '<div class="viz-mark" id="vizMark"></div>' +
        '</div>' +
        '<i class="viz-frame"></i>' +
        '<i class="viz-scan"></i>' +
      '</div>';
    const top = $('nowTop');
    if (top) top.after(root); else now.appendChild(root);
    this.root = root;
    this.bg = $('vizBg'); this.ctx = this.bg.getContext('2d');
    this.spec = $('vizSpectrumCanvas25'); this.sctx = this.spec.getContext('2d');
    this.art = $('vizArt');
    Player.bindSeek($('vProg'));
    $('vProg').addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();event.stopPropagation();Player.nudge(event.key==='ArrowRight'?5:-5);}});
    root.querySelector('.viz-ctl').onclick = event => {
      const btn = event.target.closest('button');
      if (!btn) return;
      const a = btn.dataset.a;
      if (a === 'play') Player.toggle();
      else if (a === 'prev') Player.prev();
      else if (a === 'next') Player.next(false);
      else if (a === 'mix') Mixer.open();
      // toggleLike асинхронный: перерисовка сразу после вызова показывала
      // прежнее состояние сердца — ждём ответ сервера.
      else if (a === 'like') {
        if (Player.current) {
          btn.disabled = true;
          Promise.resolve(toggleLike(Player.current))
            .catch(() => {})
            .then(() => { btn.disabled = false; this.paintButtons(); });
        }
        return;
      }
      else if (a === 'close') $('nClose').click();
      this.paintButtons();
    };
    // Подсказка перемотки: под курсором видно, на какую секунду он встанет.
    const bar = $('vProg'), tip = $('vTip');
    if (bar && tip) {
      bar.addEventListener('pointermove', event => {
        const rect = bar.getBoundingClientRect();
        if (!rect.width) return;
        if (S.vizTip === false) { bar.classList.remove('tip'); return; }
        const k = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
        const dur = Player.audio && Player.audio.duration;
        tip.textContent = dur ? fmt(dur * k) : '';
        bar.style.setProperty('--tip-x',(k*100).toFixed(2)+'%');
        bar.classList.add('tip');
      }, { passive: true });
      bar.addEventListener('pointerleave', () => bar.classList.remove('tip'), { passive: true });
    }
    // Обложка слегка поворачивается за курсором: сцена перестаёт быть
    // плоской картинкой, но ничего не «плавает» само по себе.
    root.addEventListener('pointermove', event => {
      if (S.noAnim || S.vizTilt === false) return;
      const rect = root.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      root.style.setProperty('--vx', ((event.clientX - rect.left) / rect.width - 0.5).toFixed(3));
      root.style.setProperty('--vy', ((event.clientY - rect.top) / rect.height - 0.5).toFixed(3));
    }, { passive: true });

    let idle = null;
    const wake = () => {
      root.classList.add('awake');
      clearTimeout(idle);
      idle = setTimeout(() => root.classList.remove('awake'), 2500);
    };
    root.addEventListener('pointermove', wake, { passive: true });
    root.addEventListener('pointerdown', wake, { passive: true });
    addEventListener('resize', debounce(() => { this.w = 0; }, 150));
    this.apply();
    this.recolor();
    this.paint();
  },

  setMode(on) {
    const entering = !!on && !this.on;
    this.on = !!on;
    if (entering) { this.last = 0; this.w = 0; if (typeof Visualizer32 !== "undefined") Visualizer32.lastSize = 0; }
    if (this.on) {
      this.build();
      this.apply();
      this.recolor();
      this.paint();
      Player.paintTime();
      this.setPlaying(Player.audio && !Player.audio.paused);
      this.frame(performance.now(), true);
    }
  },

  setPlaying(playing) {
    if (!this.root) return;
    const use = this.root.querySelector('.disc-play use');
    if (use) use.setAttribute('href', playing ? '#i-pause' : '#i-play');
    this.root.classList.toggle('playing', !!playing);
    this.root.classList.toggle('render-idle51', !playing);
  },

  paint() {
    if (!this.root) return;
    const track = Player.current;
    const title = $('vizTitle'), inner = $('vizTitleIn'), artist = $('vizArtist');
    const want = track ? track.title : '';
    const key = track?.id || "";
    const fresh = this.trackKey46 !== key;
    this.trackKey46 = key;
    inner.textContent = want;
    if (fresh) this.reset();                   // новый трек — новое настроение сцены
    artist.textContent = track ? track.artist : '';
    // Новый трек — название и исполнитель выезжают, как в лирик-клипах.
    if (fresh && !S.noAnim) {
      this.root.classList.remove('fresh');
      void this.root.offsetWidth;
      this.root.classList.add('fresh');
    }
    title.classList.remove('run');
    if(window.KMarquee){KMarquee.set(inner,want,S.noAnim);KMarquee.set(artist,track?track.artist:'',S.noAnim);}
    if (this.art) {
      const src = track ? KCustom.cover(track.thumbnail) : '';
      if (this.artKey46 !== src) { this.artKey46 = src; setImg(this.art, src, 600); }
    }
    const src = $('vSrc'), mark = $('vizMark');
    // В ярлыке стоит только то, что вписано в настройках: название
    // источника там раньше появлялось само и никому не было нужно.
    if (src) src.textContent = String(S.vizSrcText || '');
    if (mark) mark.textContent = track ? (track.artist || track.title || '') : '';
    this.paintCover();
    this.paintButtons();
    if (typeof VMedia !== 'undefined' && this.on) VMedia.paintTrack();
  },

  paintButtons() {
    if (!this.root) return;
    const like = this.root.querySelector('[data-a=like]');
    if (like) {
      const on = !!(Player.current && K.likes.has(Player.current.id));
      like.classList.toggle('on', on);
      const ic = like.querySelector('.ic');
      if (ic) ic.classList.toggle('f', on);
    }
    const mix = this.root.querySelector('[data-a=mix]');
    if (mix) mix.classList.toggle('on', !!S.eqOn || !!S.normalize || !!(+S.balance));
  },

  /* Цвета сцены. По умолчанию — белый монохром: так экран выглядит
     спокойно на любой обложке. Остальные режимы: две свои краски из
     настроек, перебор оттенков, цвета обложки или акцент темы. */
  colors(hue) {
    const mode = S.vizColor || 'white';
    if (mode === 'white') return ['#FFFFFF', '#FFFFFF'];
    if (mode === 'custom') {
      const a = S.vizColor1 || '#FFFFFF';
      return [a, S.vizColor2 || a];
    }
    if (mode === 'accent') return [S.accent, S.accent2];
    if (mode === 'cover') {
      const palette = CoverPalette23.forCover(Player.current?.thumbnail);
      return [palette[0], palette[1] || palette[0]];
    }
    return [`hsl(${hue}, 100%, 60%)`, `hsl(${(hue + 70) % 360}, 100%, 62%)`];
  },

  /* ----------------------------------------------------- вид сцены
     Всё, что крутится в настройках «Визуализатора», применяется здесь:
     пара классов и несколько CSS-переменных. Кадры от этого не сбиваются. */
  apply() {
    const root = this.root;
    if (!root) return;
    const num = (value, fallback) => {
      const got = +value;
      return isFinite(got) && got > 0 ? got : fallback;
    };
    root.style.setProperty('--vart', (num(S.vizArt, 100) / 100).toFixed(3));
    root.style.setProperty('--vtext', (num(S.vizText, 100) / 100).toFixed(3));
    root.style.setProperty('--vglow', (num(S.vizGlow, 100) / 100).toFixed(3));
    root.style.setProperty('--vbgl', (Math.max(0, +S.vizBgLevel || 0) / 100).toFixed(3));
    root.classList.remove('art-round', 'art-circle', 'art-square');
    root.classList.add('art-' + (S.vizShape || 'round'));
    const lay = S.vizLayout || 'side';
    root.classList.toggle('lay-center', lay === 'center');
    root.classList.toggle('lay-poster', lay === 'poster');
    root.classList.toggle('reflect', S.vizReflect !== false);
    root.classList.toggle('flash', S.vizFlash !== false);
    root.classList.toggle('tilt', S.vizTilt !== false);
    root.classList.toggle('scene-cover', (S.vizScene || 'beams') === 'cover');
    root.classList.toggle('decor', S.vizDecor !== false);
    root.classList.toggle('scan', S.vizScan !== false && !S.noAnim);
    root.classList.toggle('with-prog', S.vizProgress !== false);
    root.classList.toggle('with-src', S.vizSource !== false);
    root.classList.toggle('with-mark', S.vizMark !== false);
    root.classList.remove('spec-top', 'spec-mirror', 'spec-bars', 'spec-wave', 'spec-dots',
                          'spec-led', 'spec-line', 'spec-spike');
    root.classList.add('spec-' + (S.vizSpec || 'mirror'));
    this.sw = this.sh = 0;                 // высота шкалы меняется вместе с видом
    this.paintCover();
    this._c = null;                 // размеры обложки поменялись
    this._cTag = '';
  },

  /* Фон из обложки: та же картинка, сильно размытая и приглушённая. */
  paintCover() {
    const node = $('vizCover');
    if (!node) return;
    const track = Player.current;
    const src = track ? this.coverUrl(track.thumbnail) : '';
    node.style.backgroundImage = src ? `url("${src}")` : 'none';
  },

  coverUrl(url) {
    if (!url) return '';
    const list = typeof coverVariants === 'function'
      ? coverVariants(KCustom.cover(url), 1200) : [KCustom.cover(url)];
    return list[0] || '';
  },

  /* Множители из настроек: скорость движения и яркость фона. */
  motion() { const v = +S.vizMotion; return isFinite(v) && v > 0 ? v / 100 : 1; },
  bgLevel() { const v = +S.vizBgLevel; return isFinite(v) && v >= 0 ? v / 100 : 1; },

  /* Набор режимов цвета. Один и тот же и в настройках, и в микшере,
     рядом с эквалайзером. */
  MODES: [['white', 'White'], ['custom', 'Your colours'], ['cycle', 'Cycle'],
          ['cover', 'From the cover'], ['accent', 'Accent']],

  /* Рисует ленту режимов и привязывает две свои краски. Вызывается из
     настроек караоке и из микшера, поэтому ничего не знает о разметке
     вокруг — только идентификаторы узлов. */
  mountColors(tabsId, c1Id, c2Id) {
    const box = $(tabsId);
    const again = () => this.mountColors(tabsId, c1Id, c2Id);
    if (box) {
      box.innerHTML = '';
      this.MODES.forEach(([value, label]) => {
        const chip = el('button', 'chip' + ((S.vizColor || 'white') === value ? ' on' : ''), t(label));
        chip.onclick = () => {
          S.vizColor = value;
          saveSettings();
          this.recolor();
          again();
        };
        box.appendChild(chip);
      });
    }
    [[c1Id, 'vizColor1'], [c2Id, 'vizColor2']].forEach(([id, key]) => {
      const node = $(id);
      if (!node) return;
      node.value = S[key] || '#FFFFFF';
      // Тронул краску — сцена сразу переходит на свои цвета: иначе выбор
      // цвета выглядел бы как кнопка, которая ничего не делает.
      node.oninput = () => {
        S[key] = node.value;
        S.vizColor = 'custom';
        saveSettings();
        this.recolor();
        again();
      };
    });
  },

  /* Тот же цвет, но прозрачный. Краска приходит из четырёх разных мест,
     поэтому здесь понимаем и #rrggbb, и hsl(), и rgb(). */
  fade(color, a) {
    const c = String(color || '#FFFFFF');
    if (c[0] === '#') return rgba(c, a);
    if (c.startsWith('hsl(')) return c.replace('hsl(', 'hsla(').replace(')', `, ${a})`);
    if (c.startsWith('rgb(')) return c.replace('rgb(', 'rgba(').replace(')', `, ${a})`);
    return c;
  },

  /* Краски уезжают в CSS: рамка обложки, название, кнопки и шкала берут
     их оттуда, поэтому смена цвета в настройках видна сразу — даже на
     паузе, когда кадры сцены не идут. */
  setVars(c1, c2, beat) {
    if (!this.root) return;
    const style=this.root.style,set=(key,value)=>{value=String(value);if(style.getPropertyValue(key)!==value)style.setProperty(key,value);};
    // Colour work is event-like. Spectrum moves on canvas, not inherited text/layout styles.
    set('--vb',(+beat||0).toFixed(2));
    if(this.color1_51!==c1||this.color2_51!==c2){this.color1_51=c1;this.color2_51=c2;set('--vc1',c1);set('--vc2',c2);set('--vc1-90',this.fade(c1,.9));set('--vc1-55',this.fade(c1,.55));set('--vc1-28',this.fade(c1,.28));set('--vc2-55',this.fade(c2,.55));}
  },

  /* Зовётся из настроек: цвет поменяли — пересобираем сцену на месте. */
  recolor() {
    if (!this.root) return;
    this.apply();
    const [c1, c2] = this.colors(this.hue);
    this.setVars(c1, c2, 0);
    if (this.on) this.frame(performance.now(), true);
  },

  size() {
    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const bw = this.bg.clientWidth, bh = this.bg.clientHeight;
    if (!bw || !bh) return false;
    if (this.w !== bw || this.h !== bh || this.pixelRatio !== dpr) {
      this.w = bw; this.h = bh;
      this.bg.width = Math.round(bw * dpr); this.bg.height = Math.round(bh * dpr);
    }
    const sw = this.spec.clientWidth, sh = this.spec.clientHeight;
    if (this.sw !== sw || this.sh !== sh || this.pixelRatio !== dpr) {
      this.sw = sw; this.sh = sh;
      this.spec.width = Math.max(1, Math.round(sw*dpr)); this.spec.height = Math.max(1, Math.round(sh*dpr));
      this.sctx.setTransform(dpr,0,0,dpr,0,0);
    }
    this.pixelRatio=dpr;
    return true;
  },

  /* Зовётся из Karaoke.onTime каждый кадр. */
  onTime() { this.frame(performance.now()); },

  /* Кадр сцены. Движение считается по времени, а не по числу кадров:
     сцена идёт с одной и той же скоростью и на 60 Гц, и на 144 Гц, и
     после возврата из фона — ничего не «проматывается» рывком. */
  frame(now, force) {
    if (!this.on || !this.root || document.hidden || document.querySelector('.modal.on') || !$('now')?.classList.contains('on')) return;
    let dt = this.last ? (now - this.last) / 1000 : 1 / 60;
    const fps=typeof Visualizer32!=='undefined'?Visualizer32.budget().spectrum:60;
    if (!force && this.last && dt < 1/fps-.001) return;                  // потолок — 60 кадров в секунду
    this.last = now;
    if (!(dt > 0.0005) || dt > 0.08) dt = 1 / 60;       // вкладку сворачивали — идём дальше ровно
    this.dt = dt;
    this.k = dt * 60;                                   // «сколько шагов 60 fps прошло»
    if (!this.size()) return;
    const active=!!Player.current && !!Player.audio && !Player.audio.paused && !Player.audio.ended;
    const raw=Karaoke.level();
    const lv=active?raw:{energy:0,bins:null};
    const energy = Math.min(1, lv.energy * 2.2);
    const beat = active?Math.min(1,Karaoke.beat||0):0;
    const calm = !!S.noAnim || (typeof Visualizer32!=='undefined'?!!Visualizer32.reduce51?.matches:!!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
    const mood = this.sense(lv, beat, dt);
    // Скорость сцены ведёт сама музыка: тихий куплет течёт медленно,
    // припев разгоняет и полосы, и звёзды, и искры.
    const drive = this.adapt() ? mood.drive : 0.35;
    this.t += dt * this.motion() * (0.75 + drive * 0.9);
    this.hue = (this.hue + dt * 60 * (0.35 + energy * 0.9) * this.motion()) % 360;
    const [c1, c2] = this.colors(this.hue);

    // Рамка обложки и заголовок дышат цветом.
    this.setVars(c1, c2, beat);

    this.paintLeft();
    this.paintProg();
    this.drawBg(c1, c2, energy, beat, calm, lv.bins);
    this.drawSpec(lv.bins, c1, c2, energy);
  },

  /* ------------------------------------------------- характер трека
     Сцена слушает не только громкость: отдельно низ, середина и «воздух»,
     общий напор и примерный темп. Из этого собирается настроение, по
     которому сцена сама выбирает размах движения, плотность искр и —
     в режиме «Сама» — вид фона. */
  adapt() { return S.vizAdapt !== false; },

  sense(lv, beat, dt) {
    const m = this.mood || (this.mood = { bass: 0, mid: 0, air: 0, drive: 0, punch: 0, bpm: 0 });
    const bins = lv.bins;
    const band = (from, to) => {
      if (!bins || !bins.length) return 0;
      const a = Math.floor(bins.length * from);
      const b = Math.max(a + 1, Math.floor(bins.length * to));
      let sum = 0;
      for (let i = a; i < b; i++) sum += bins[i];
      return sum / (b - a) / 255;
    };
    // Плавность по времени: быстрый подъём, мягкий спад — так сцена
    // успевает за ударом, но не мигает на каждом шорохе.
    const ease = (cur, target, up, down) =>
      cur + (target - cur) * (1 - Math.exp(-dt / (target > cur ? up : down)));
    m.bass = ease(m.bass, band(0, 0.08), 0.03, 0.16);
    m.mid = ease(m.mid, band(0.08, 0.3), 0.05, 0.22);
    m.air = ease(m.air, band(0.3, 0.8), 0.06, 0.3);
    m.drive = ease(m.drive, Math.min(1, lv.energy * 2.6), 0.22, 1.1);
    m.punch = Math.max(beat, m.punch - dt * 2.2);
    // Темп: считаем промежутки между ударами и держим среднее.
    if (beat > 0.85 && this.beatPrev <= 0.85) {
      const at = this.t;
      const gap = at - (this.beatAt || 0);
      this.beatAt = at;
      if (gap > 0.25 && gap < 1.6) {
        const bpm = 60 / gap;
        m.bpm = m.bpm ? m.bpm * 0.82 + bpm * 0.18 : bpm;
      }
    }
    return m;
  },

  /* Новый трек — характер считаем заново, иначе тихая баллада достаётся
     сцене с разгоном предыдущего припева. */
  reset() {
    this.mood = null; this.bpm = 0; this.beatAt = 0;
    this.peaks=null; this.vals=null;
    this.parts = []; this.rings = []; this.bolts = []; this.drops = null;
    this.orbs = null; this.ripples = null; this.stars = null;
    this._autoKey = null; this._autoScene = null;
  },

  /* Сколько осталось до конца трека. Пишем только при смене секунды:
     иначе узел трогался бы каждый кадр без всякой пользы. */
  paintLeft() {
    const node = $('vLeft');
    const audio = Player.audio;
    if (!node || !audio || !Number.isFinite(audio.duration) || audio.duration <= 0) { if (node) node.textContent = ''; this._left=null; return; }
    const left = Math.max(0, Math.floor(audio.duration) - Math.floor(audio.currentTime));
    if (left === this._left) return;
    this._left = left;
    node.textContent = '−' + fmt(left);
  },

  /* Полоса прогресса над спектром — как в клипе: белая заливка в рамке. */
  paintProg() {
    if (Player.seeking || Player.holdUntilSeeked) { Player.paintProgress(); return; }
    const fill = $('vFill');
    const audio = Player.audio;
    if (!fill) return;
    const k = audio && Number.isFinite(audio.duration) && audio.duration > 0 ? Math.max(0,Math.min(1,audio.currentTime / audio.duration)) : 0;
    const pct = Math.round(k * 1000) / 10;
    if (pct === this._prog) return;
    this._prog = pct;
    paintStyle40(fill, 'width', pct + '%');
    const slider = $('vProg');
    if (slider) { slider.setAttribute('aria-valuenow', String(pct)); slider.setAttribute('aria-valuetext', fmt(audio?.currentTime || 0) + ' / ' + fmt(Number.isFinite(audio?.duration) ? audio.duration : 0)); }
  },

  /* Середина обложки в координатах сцены: от неё расходятся кольца. */
  center() {
    const tag = this.w + 'x' + this.h;
    if (!this._c || this._cTag !== tag) {
      const art = this.art ? this.art.getBoundingClientRect() : null;
      const box = this.root.getBoundingClientRect();
      if (!art || !art.width) return null;
      this._cTag = tag;
      this._c = { x: art.left - box.left + art.width / 2,
                  y: art.top - box.top + art.height / 2,
                  r: art.width / 2 };
    }
    return this._c;
  },

  drawBg(c1, c2, energy, beat, calm, bins) {
    const ctx = this.ctx, w = this.bg.width, h = this.bg.height;
    const scene = this.sceneName();
    const mood = this.mood || { bass: 0, mid: 0, air: 0, drive: 0, punch: 0, bpm: 0 };
    // Яркость фона тоже дышит: в тихом месте сцена отступает, на припеве
    // выходит вперёд. Ползунок из настроек остаётся общим потолком.
    const lvl = this.bgLevel() * (this.adapt() ? 0.78 + mood.drive * 0.45 : 1);
    ctx.globalCompositeOperation = 'source-over';
    // Свой видеофон или фон-обложка: холст остаётся прозрачным, на нём
    // живут только свет, сцена и искры.
    if (document.body.classList.contains('k-vbg') || document.body.classList.contains('k-custom') || scene === 'cover') ctx.clearRect(0, 0, w, h);
    else { ctx.fillStyle = '#04050a'; ctx.fillRect(0, 0, w, h); }
    ctx.globalCompositeOperation = 'lighter';

    // Углы светятся цветом сцены — общая подсветка для всех видов фона.
    const glow = (x, y, r, col, a) => {
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, col); g.addColorStop(1, 'transparent');
      ctx.globalAlpha = Math.max(0, a * lvl); ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    };
    const R = Math.max(w, h) * (0.5 + beat * 0.06);
    glow(0, 0, R, c1, 0.16 + energy * 0.2);
    glow(w, h, R, c2, 0.15 + energy * 0.2);

    if (scene === 'beams') this.sceneBeams(ctx, w, h, c1, c2, energy, beat, lvl);
    else if (scene === 'grid') this.sceneGrid(ctx, w, h, c1, c2, energy, beat, lvl);
    else if (scene === 'tunnel') this.sceneTunnel(ctx, w, h, c1, c2, energy, beat, lvl);
    else if (scene === 'stars') this.sceneStars(ctx, w, h, c1, c2, energy, beat, lvl, calm);
    else if (scene === 'aurora') this.sceneAurora(ctx, w, h, c1, c2, energy, beat, lvl);
    else if (scene === 'hex') this.sceneHex(ctx, w, h, c1, c2, energy, beat, lvl);
    else if (scene === 'rain') this.sceneRain(ctx, w, h, c1, c2, energy, beat, lvl, calm);
    else if (scene === 'ridge') this.sceneRidge(ctx, w, h, c1, c2, energy, beat, lvl, bins);
    else if (scene === 'city') this.sceneCity(ctx, w, h, c1, c2, energy, beat, lvl, bins);
    else if (scene === 'orbit') this.sceneOrbit(ctx, w, h, c1, c2, energy, beat, lvl, calm);
    else if (scene === 'ripple') this.sceneRipple(ctx, w, h, c1, c2, energy, beat, lvl);
    else if (scene === 'plasma') this.scenePlasma(ctx, w, h, c1, c2, energy, beat, lvl);
    else if (scene === 'spiral') this.sceneSpiral(ctx, w, h, c1, c2, energy, beat, lvl);

    // Кольца на удар расходятся от обложки — ударный «импульс» сцены.
    if (S.vizRings !== false && !calm) {
      const c = this.center();
      if (c) {
        if (!this.rings) this.rings = [];
        if (beat > 0.85 && this.beatPrev <= 0.85 && this.rings.length < 6) this.rings.push(1);
        this.rings = this.rings.filter(life => life > 0.02);
        for (let i = 0; i < this.rings.length; i++) {
          const life = this.rings[i] -= 0.022 * this.motion() * this.k;
          const r = c.r * (1 + (1 - life) * 1.9);
          ctx.globalAlpha = life * life * 0.32;
          ctx.strokeStyle = i % 2 ? c2 : c1;
          ctx.lineWidth = 1 + life * 1.4;
          ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, 6.283); ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
    }

    // Молнии на удар: короткие ломаные вспышки у краёв сцены.
    if (S.vizBolts !== false && !calm) this.drawBolts(ctx, w, h, c1, c2, beat);
    // Живая волна по низу сцены — как в клипах: она идёт по басу и
    // мягко подсвечивает нижний край экрана.
    if (S.vizWave === true) this.drawWave(ctx, w, h, c1, c2, energy, beat, bins);

    // Искры: на каждый удар вылетает горсть, дальше они плывут и гаснут.
    const rate = Math.max(0, (+S.vizSparkRate >= 0 ? +S.vizSparkRate : 100) / 100);
    if (S.vizParticles !== false && !calm && rate > 0) {
      const push = this.adapt() ? 0.6 + mood.drive * 0.9 : 1;
      const cap = Math.round(110 * rate * push);
      if (beat > 0.85 && this.beatPrev <= 0.85 && this.parts.length < cap) {
        for (let i = 0; i < Math.max(1, Math.round(9 * rate * push)); i++) {
          const a = Math.random() * Math.PI * 2, v = 0.0015 + Math.random() * 0.004;
          const kick = 1 + mood.bass * 1.2;
          this.parts.push({ x: 0.3 + Math.random() * 0.4, y: 0.3 + Math.random() * 0.4,
                            vx: Math.cos(a) * v * kick, vy: Math.sin(a) * v * kick - 0.0008,
                            life: 1, s: 1.5 + Math.random() * 3.5, k: Math.random() < 0.5 });
        }
      }
      // Между ударами сцена не пустеет: редкие искры идут по громкости.
      if (this.parts.length < cap && Math.random() < energy * 0.18 * rate * this.k) {
        const a = Math.random() * Math.PI * 2, v = 0.0008 + Math.random() * 0.002;
        this.parts.push({ x: 0.2 + Math.random() * 0.6, y: 0.35 + Math.random() * 0.5,
                          vx: Math.cos(a) * v, vy: -0.001 - Math.random() * 0.0015,
                          life: 1, s: 1 + Math.random() * 2.2, k: Math.random() < 0.5 });
      }
      this.parts = this.parts.filter(p => (p.life -= 0.012 * this.k) > 0);
      for (const p of this.parts) {
        p.x += p.vx * this.motion() * this.k; p.y += p.vy * this.motion() * this.k;
        ctx.globalAlpha = Math.min(1, p.life * 1.2);
        ctx.fillStyle = p.k ? c1 : c2;
        ctx.beginPath(); ctx.arc(p.x * w, p.y * h, p.s * (w / 1400 + 0.5), 0, 6.283); ctx.fill();
      }
    } else if (this.parts.length) this.parts = [];
    this.beatPrev = beat;
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';

    // Виньетка: края сцены темнее, и взгляд сам идёт к плееру.
    if (S.vizVignette !== false) {
      const vg = ctx.createRadialGradient(w * 0.5, h * 0.5, Math.min(w, h) * 0.25,
                                          w * 0.5, h * 0.5, Math.max(w, h) * 0.72);
      vg.addColorStop(0, 'rgba(0,0,0,0)');
      vg.addColorStop(1, 'rgba(0,0,0,.58)');
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, w, h);
    }
  },

  /* ------------------------------------------------------------- сцены
     Каждая сцена — отдельная картинка фона. Все они рисуются в режиме
     lighter поверх общей подсветки углов и ничего друг о друге не знают,
     поэтому новую можно добавить одной функцией. */

  /* Какой фон рисовать. «Сама» — сцена смотрит на характер трека и
     выбирает вид один раз на песню: менять картинку посреди куплета
     неприятно, а на новом треке смена выглядит как часть клипа. */
  sceneName() {
    const want = S.vizScene || 'beams';
    if (want !== 'auto') return want;
    const key = (Player.current && Player.current.id) || '';
    if (this._autoKey !== key) { this._autoKey = key; this._autoScene = null; this._autoAt = this.t; }
    if (this._autoScene) return this._autoScene;
    const m = this.mood || { bass: 0, air: 0, drive: 0, bpm: 0 };
    if (this.t - (this._autoAt || 0) < 3 && m.drive < 0.5) return 'aurora';
    const fast = m.bpm > 132 || m.drive > 0.62;
    const low = m.bass > m.air * 1.5;
    const calmTrack = m.drive < 0.3;
    const pool = calmTrack ? ['aurora', 'plasma', 'stars']
      : fast && low ? ['tunnel', 'city', 'rain']
      : fast ? ['stars', 'spiral', 'beams']
      : low ? ['ridge', 'hex', 'ripple']
      : ['beams', 'orbit', 'grid'];
    this._autoScene = pool[Math.floor(Math.random() * pool.length)];
    return this._autoScene;
  },

  /* «Полосы»: наклонные неоновые ленты идут через экран. */
  sceneBeams(ctx, w, h, c1, c2, energy, beat, lvl) {
    const t = this.t * 0.5;
    const slant = h * 0.55;
    for (let i = 0; i < 9; i++) {
      const phase = ((i / 9) + t * (0.2 + (i % 3) * 0.08)) % 1;
      const x = (phase * 1.5 - 0.25) * w;
      const bw = w * (0.015 + (i % 4) * 0.012) * (1 + beat * 0.8);
      ctx.fillStyle = i % 2 ? c1 : c2;
      ctx.globalAlpha = (0.03 + energy * 0.12) * (0.5 + (i % 3) * 0.3) * lvl;
      ctx.beginPath();
      ctx.moveTo(x, h); ctx.lineTo(x + bw, h);
      ctx.lineTo(x + bw + slant, 0); ctx.lineTo(x + slant, 0);
      ctx.closePath(); ctx.fill();
    }
    ctx.globalAlpha = 1;
  },

  /* «Сетка»: уходящий к горизонту пол в духе ретровейва. */
  sceneGrid(ctx, w, h, c1, c2, energy, beat, lvl) {
    const hz = h * 0.58;                 // линия горизонта
    const cx = w * 0.5;
    ctx.lineWidth = 1;
    ctx.globalAlpha = (0.1 + energy * 0.22) * lvl;
    ctx.strokeStyle = c1;
    ctx.beginPath();
    for (let i = -14; i <= 14; i++) {    // лучи к горизонту
      const x = cx + i * (w * 0.085);
      ctx.moveTo(cx + i * (w * 0.012), hz);
      ctx.lineTo(x, h);
    }
    ctx.stroke();
    const run = (this.t * 0.16) % 1;
    ctx.strokeStyle = c2;
    ctx.beginPath();
    for (let i = 0; i < 12; i++) {       // поперечины бегут на зрителя
      const k = ((i + run) / 12) ** 2.4;
      const y = hz + k * (h - hz) * 1.02;
      if (y > h) continue;
      ctx.moveTo(0, y); ctx.lineTo(w, y);
    }
    ctx.stroke();
    // Горизонт светится, а на удар вспыхивает ярче.
    const g = ctx.createLinearGradient(0, hz - h * 0.12, 0, hz + h * 0.04);
    g.addColorStop(0, 'transparent');
    g.addColorStop(1, this.fade(c1, (0.26 + beat * 0.3) * lvl));
    ctx.globalAlpha = 1; ctx.fillStyle = g;
    ctx.fillRect(0, hz - h * 0.12, w, h * 0.16);
  },

  /* «Тоннель»: круги уходят в глубину, спицы медленно поворачиваются. */
  sceneTunnel(ctx, w, h, c1, c2, energy, beat, lvl) {
    const cx = w * 0.5, cy = h * 0.5;
    const max = Math.hypot(w, h) * 0.6;
    const run = (this.t * 0.18) % 1;
    ctx.lineWidth = 1.4;
    for (let i = 0; i < 14; i++) {
      const k = ((i + run) / 14) ** 2.2;
      const r = k * max;
      ctx.globalAlpha = (0.05 + energy * 0.2) * (1 - k * 0.7) * lvl;
      ctx.strokeStyle = i % 2 ? c1 : c2;
      ctx.beginPath(); ctx.arc(cx, cy, r + beat * 10, 0, 6.283); ctx.stroke();
    }
    const spin = this.t * 0.14;
    ctx.globalAlpha = (0.05 + energy * 0.12) * lvl;
    ctx.strokeStyle = c2;
    ctx.beginPath();
    for (let i = 0; i < 16; i++) {
      const a = spin + (i / 16) * 6.283;
      ctx.moveTo(cx + Math.cos(a) * max * 0.12, cy + Math.sin(a) * max * 0.12);
      ctx.lineTo(cx + Math.cos(a) * max, cy + Math.sin(a) * max);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
  },

  /* «Звёзды»: поле звёзд летит сквозь экран, на удар — рывок вперёд. */
  sceneStars(ctx, w, h, c1, c2, energy, beat, lvl, calm) {
    if (!this.stars || !this.stars.length) {
      this.stars = Array.from({ length: 150 }, () => ({
        a: Math.random() * 6.283, z: Math.random(), s: 0.5 + Math.random() * 1.6,
        k: Math.random() < 0.5,
      }));
    }
    const cx = w * 0.5, cy = h * 0.5;
    const max = Math.hypot(w, h) * 0.55;
    const speed = (calm ? 0.002 : 0.004 + energy * 0.012 + beat * 0.02) * this.motion() * this.k;
    for (const star of this.stars) {
      star.z += speed;
      if (star.z > 1) { star.z = 0.02; star.a = Math.random() * 6.283; }
      const r = star.z ** 1.8 * max;
      const x = cx + Math.cos(star.a) * r, y = cy + Math.sin(star.a) * r;
      const tail = r * 0.06 * (1 + beat * 2);
      ctx.globalAlpha = Math.min(1, star.z * 1.3) * (0.35 + energy * 0.5) * lvl;
      ctx.strokeStyle = star.k ? c1 : c2;
      ctx.lineWidth = star.s * (0.4 + star.z * 1.4);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(cx + Math.cos(star.a) * (r - tail), cy + Math.sin(star.a) * (r - tail));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },

  /* «Сияние»: мягкие пятна света плывут и дышат вместе с музыкой. */
  sceneAurora(ctx, w, h, c1, c2, energy, beat, lvl) {
    const t = this.t * 0.4;
    for (let i = 0; i < 3; i++) {
      const x = w * (0.5 + Math.cos(t * (0.5 + i * 0.3) + i * 2.1) * 0.32);
      const y = h * (0.5 + Math.sin(t * (0.4 + i * 0.25) + i * 1.3) * 0.28);
      const r = Math.min(w, h) * (0.42 + i * 0.1) * (1 + energy * 0.25 + beat * 0.08);
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, this.fade(i % 2 ? c2 : c1, (0.2 + energy * 0.22) * lvl));
      g.addColorStop(0.5, this.fade(i % 2 ? c2 : c1, (0.07 + energy * 0.08) * lvl));
      g.addColorStop(1, 'transparent');
      ctx.globalAlpha = 1; ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
  },

  /* Молнии: на сильный удар у случайного края вспыхивает ломаная линия
     и почти сразу гаснет. Её хватает, чтобы сцена «щёлкала» вместе с
     битом, и она не отвлекает от плеера. */
  drawBolts(ctx, w, h, c1, c2, beat) {
    if (!this.bolts) this.bolts = [];
    if (beat > 0.9 && this.beatPrev <= 0.9 && this.bolts.length < 3) {
      const left = Math.random() < 0.5;
      const x0 = left ? w * (0.02 + Math.random() * 0.1) : w * (0.88 + Math.random() * 0.1);
      const y0 = h * Math.random() * 0.5;
      const pts = [[x0, y0]];
      const dx = (left ? 1 : -1) * w * 0.035;
      for (let i = 0; i < 6; i++) {
        const prev = pts[pts.length - 1];
        pts.push([prev[0] + dx * (0.6 + Math.random()), prev[1] + h * (0.05 + Math.random() * 0.07)]);
      }
      this.bolts.push({ pts, life: 1, k: Math.random() < 0.5 });
    }
    this.bolts = this.bolts.filter(bolt => (bolt.life -= 0.09 * this.k) > 0);
    for (const bolt of this.bolts) {
      ctx.globalAlpha = bolt.life * 0.8;
      ctx.strokeStyle = bolt.k ? c1 : c2;
      ctx.lineWidth = 1.2 + bolt.life * 1.6;
      ctx.shadowColor = this.fade(bolt.k ? c1 : c2, 0.9);
      ctx.shadowBlur = 12;
      ctx.beginPath();
      bolt.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.stroke();
      ctx.shadowBlur = 0;
    }
    ctx.globalAlpha = 1;
  },

  /* «Соты»: техно-сетка из шестиугольников, она дышит вместе с музыкой
     и медленно плывёт — тот самый фон из клипов. */
  sceneHex(ctx, w, h, c1, c2, energy, beat, lvl) {
    const r = Math.max(26, Math.min(w, h) * 0.06);
    const stepX = r * 1.5, stepY = r * Math.sqrt(3);
    const shift = (this.t * 9) % stepY;
    ctx.lineWidth = 1;
    ctx.globalAlpha = (0.07 + energy * 0.16 + beat * 0.06) * lvl;
    ctx.strokeStyle = c1;
    ctx.beginPath();
    for (let col = -1, x = -stepX; x < w + stepX; col++, x += stepX) {
      const offset = col % 2 ? stepY / 2 : 0;
      for (let y = -stepY + offset - shift; y < h + stepY; y += stepY) {
        for (let i = 0; i < 6; i++) {
          const a = Math.PI / 180 * (60 * i);
          const px = x + Math.cos(a) * r, py = y + Math.sin(a) * r;
          if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
        }
        ctx.closePath();
      }
    }
    ctx.stroke();
    ctx.globalAlpha = 1;
  },

  /* «Дождь»: светящиеся капли падают сверху, скорость ведёт напор трека,
     на удар по экрану проходит короткая волна ярких капель. */
  sceneRain(ctx, w, h, c1, c2, energy, beat, lvl, calm) {
    if (!this.drops || !this.drops.length) {
      this.drops = Array.from({ length: 90 }, () => ({
        x: Math.random(), y: Math.random(), v: 0.4 + Math.random() * 1.1,
        len: 0.04 + Math.random() * 0.1, k: Math.random() < 0.5,
      }));
    }
    const m = this.mood || { drive: 0.4 };
    const speed = (calm ? 0.12 : 0.35 + m.drive * 0.9 + beat * 0.5) * this.motion();
    ctx.lineWidth = 1.2;
    for (const d of this.drops) {
      d.y += d.v * speed * this.dt;
      if (d.y > 1.1) { d.y = -0.1; d.x = Math.random(); }
      const x = d.x * w, y = d.y * h;
      ctx.globalAlpha = (0.12 + energy * 0.5) * lvl;
      ctx.strokeStyle = d.k ? c1 : c2;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x, y - d.len * h * (1 + beat));
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },

  /* «Горы»: слои силуэтов по спектру — ровная линия гор, которая
     поднимается на басах и медленно плывёт вбок. */
  sceneRidge(ctx, w, h, c1, c2, energy, beat, lvl, bins) {
    const layers = 3;
    for (let layer = 0; layer < layers; layer++) {
      const depth = (layer + 1) / layers;
      const base = h * (0.72 + layer * 0.1);
      const amp = h * (0.1 + energy * 0.16 + beat * 0.05) * (1.2 - depth * 0.5);
      const run = this.t * (0.12 + layer * 0.06);
      ctx.globalAlpha = (0.1 + energy * 0.16) * (1.1 - depth * 0.4) * lvl;
      ctx.fillStyle = layer % 2 ? c2 : c1;
      ctx.beginPath();
      ctx.moveTo(0, h);
      const step = Math.max(8, w / 70);
      for (let x = 0; x <= w; x += step) {
        const u = x / w;
        let s = Math.sin((u * 6 + run) * 1.7) * 0.6 + Math.sin((u * 13 - run * 1.4)) * 0.4;
        if (bins && bins.length) {
          const i = Math.floor(u * bins.length * 0.35);
          s += (bins[i] / 255) * 0.9;
        }
        ctx.lineTo(x, base - amp * s);
      }
      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  },

  /* «Город»: неоновые башни по полосам спектра, с окнами и отражением
     света на «асфальте». */
  sceneCity(ctx, w, h, c1, c2, energy, beat, lvl, bins) {
    const n = 26;
    const bw = w / n;
    const floor = h * 0.86;
    const drift = (this.t * 12) % bw;
    for (let i = 0; i < n + 1; i++) {
      let v = 0.2;
      if (bins && bins.length) {
        const from = Math.floor((i / n) ** 1.6 * bins.length * 0.5);
        const to = Math.max(from + 1, Math.floor(((i + 1) / n) ** 1.6 * bins.length * 0.5));
        for (let k = from; k < to; k++) v = Math.max(v, bins[k] / 255);
      }
      const bh = h * (0.1 + v * 0.45) * (1 + beat * 0.12);
      const x = i * bw - drift;
      ctx.globalAlpha = (0.12 + energy * 0.2) * lvl;
      ctx.fillStyle = i % 2 ? c1 : c2;
      ctx.fillRect(x + bw * 0.12, floor - bh, bw * 0.76, bh);
      ctx.globalAlpha = (0.05 + energy * 0.1) * lvl;
      ctx.fillRect(x + bw * 0.12, floor, bw * 0.76, bh * 0.35);   // отражение
    }
    ctx.globalAlpha = 1;
  },

  /* «Орбиты»: точки кружат вокруг обложки, на сильный удар между
     ближними точками вспыхивают нити. */
  sceneOrbit(ctx, w, h, c1, c2, energy, beat, lvl, calm) {
    if (!this.orbs || !this.orbs.length) {
      this.orbs = Array.from({ length: 34 }, (_, i) => ({
        r: 0.16 + Math.random() * 0.4, a: Math.random() * 6.283,
        v: (0.15 + Math.random() * 0.5) * (i % 2 ? 1 : -1),
        s: 1 + Math.random() * 2.2, k: Math.random() < 0.5,
      }));
    }
    const cx = w * 0.5, cy = h * 0.5;
    const scale = Math.min(w, h);
    const speed = calm ? 0.2 : 1 + energy * 1.6;
    const pts = [];
    for (const o of this.orbs) {
      o.a += o.v * speed * this.dt * this.motion();
      const r = o.r * scale * (1 + beat * 0.08);
      const x = cx + Math.cos(o.a) * r * 1.35, y = cy + Math.sin(o.a) * r;
      pts.push([x, y, o.k]);
      ctx.globalAlpha = (0.3 + energy * 0.5) * lvl;
      ctx.fillStyle = o.k ? c1 : c2;
      ctx.beginPath(); ctx.arc(x, y, o.s * (1 + beat * 0.6), 0, 6.283); ctx.fill();
    }
    if (beat > 0.5) {
      ctx.globalAlpha = (beat - 0.5) * 0.4 * lvl;
      ctx.strokeStyle = c2; ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i < pts.length; i++) {
        const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length];
        if (Math.hypot(x2 - x1, y2 - y1) < scale * 0.28) { ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); }
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },

  /* «Круги на воде»: каждый удар роняет каплю, от неё расходится круг. */
  sceneRipple(ctx, w, h, c1, c2, energy, beat, lvl) {
    if (!this.ripples) this.ripples = [];
    if (beat > 0.8 && this.beatPrev <= 0.8 && this.ripples.length < 10) {
      this.ripples.push({ x: Math.random(), y: 0.2 + Math.random() * 0.6, life: 1, k: Math.random() < 0.5 });
    }
    this.ripples = this.ripples.filter(r => (r.life -= this.dt * 0.55) > 0);
    const max = Math.hypot(w, h) * 0.45;
    for (const r of this.ripples) {
      const grow = 1 - r.life;
      ctx.globalAlpha = r.life * r.life * (0.35 + energy * 0.3) * lvl;
      ctx.strokeStyle = r.k ? c1 : c2;
      ctx.lineWidth = 1 + r.life * 2.4;
      ctx.beginPath();
      ctx.arc(r.x * w, r.y * h, grow * max, 0, 6.283);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },

  /* «Плазма»: мягкие светящиеся ленты текут поперёк экрана — спокойный
     фон для медленных треков. */
  scenePlasma(ctx, w, h, c1, c2, energy, beat, lvl) {
    const t = this.t * 0.45;
    ctx.lineWidth = Math.max(6, h * 0.035);
    for (let i = 0; i < 5; i++) {
      const phase = t * (0.5 + i * 0.17) + i * 1.7;
      ctx.globalAlpha = (0.05 + energy * 0.12) * lvl;
      ctx.strokeStyle = i % 2 ? c1 : c2;
      ctx.beginPath();
      for (let x = 0; x <= w; x += Math.max(8, w / 60)) {
        const u = x / w;
        const y = h * (0.5 + Math.sin(u * 3.1 + phase) * 0.22 * (1 + energy)
                              + Math.sin(u * 7.3 - phase * 1.3) * 0.08)
                  + (i - 2) * h * 0.08 * (1 + beat * 0.3);
        if (x) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },

  /* «Спираль»: точки раскручиваются из центра, на удар спираль
     подкручивается быстрее. */
  sceneSpiral(ctx, w, h, c1, c2, energy, beat, lvl) {
    const cx = w * 0.5, cy = h * 0.5;
    const max = Math.hypot(w, h) * 0.5;
    const spin = this.t * (0.3 + energy * 0.7);
    const dots = 170;
    for (let i = 0; i < dots; i++) {
      const k = i / dots;
      const a = k * 18 + spin;
      const r = k * max * (1 + beat * 0.05);
      ctx.globalAlpha = (0.1 + energy * 0.45) * (1 - k * 0.5) * lvl;
      ctx.fillStyle = i % 2 ? c1 : c2;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(a) * r * 1.2, cy + Math.sin(a) * r, 1 + k * 2.2 + beat, 0, 6.283);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  },

  /* Волна по низу сцены. Форма — две синусоиды разной длины, высота
     ведётся громкостью, цвет — тот же, что у всей сцены. Рисуем в режиме
     lighter, поэтому волна светится, а не закрывает фон. */
  drawWave(ctx, w, h, c1, c2, energy, beat, bins) {
    let bass = 0;
    if (bins && bins.length) {
      const to = Math.max(1, Math.floor(bins.length * 0.08));
      for (let i = 0; i < to; i++) bass += bins[i];
      bass = bass / to / 255;
    }
    const amp = h * (0.016 + energy * 0.05 + bass * 0.05);
    const base = h * 0.97;
    const t = this.t * 0.7;
    const grad = ctx.createLinearGradient(0, base - amp * 3, 0, h);
    grad.addColorStop(0, this.fade(c2, (0.14 + energy * 0.16) * this.bgLevel()));
    grad.addColorStop(1, this.fade(c1, 0.04));
    for (let layer = 0; layer < 2; layer++) {
      const k = layer ? 0.62 : 1;
      ctx.globalAlpha = layer ? 0.4 : 0.85;
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(0, h);
      for (let x = 0; x <= w; x += Math.max(6, w / 90)) {
        const u = x / w;
        const y = base - amp * k * (
          Math.sin(u * 7.5 + t * (layer ? -1.3 : 1.7)) * 0.7 +
          Math.sin(u * 17 + t * (layer ? 2.1 : -2.6)) * 0.3) - amp * k;
        ctx.lineTo(x, y);
      }
      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  },

  /* Шкала-спектр: она же перемотка. Вид выбирается в настройках:
     полоски от центра, полоски от низа, залитая волна или точки. Над
     полосками держатся «шапки» пиков, поверх идёт плавная огибающая, а
     текущее место отмечает светящийся бегунок. Пройденная часть яркая. */
  drawSpec(bins, c1, c2, energy) {
    const ctx = this.sctx, w = this.sw || this.spec.width, h = this.sh || this.spec.height;
    ctx.clearRect(0, 0, w, h);
    const audio = Player.audio;
    const progress = 1; // Spectrum is a frequency display, not a second timeline.
    const kind = S.vizSpec || (S.vizMirror === false ? 'bars' : 'mirror');
    const mirror = kind === 'mirror' || kind === 'dots' || kind === 'wave'
                || kind === 'spike' || kind === 'line';
    const top = kind === 'top';
    const budget=typeof Visualizer32!=='undefined'?Visualizer32.budget():{bars:128,shadow:true};
    const n = Math.min(budget.bars, kind === 'led' ? Math.max(16, Math.floor(w / 14)) : Math.max(24, Math.floor(w / 7)));
    const mid = mirror ? h / 2 : (top ? 0 : h);
    const span = mirror ? h / 2 : h;
    const bw = Math.max(2, w / n - 2);
    const gradientKey=[w,this.pixelRatio,c1,c2].join('|');
    if(!this.gradient51||this.gradient51.key!==gradientKey||this.gradient51.ctx!==ctx){const g=ctx.createLinearGradient(0,0,w,0);g.addColorStop(0,c1);g.addColorStop(1,c2);this.gradient51={key:gradientKey,ctx,value:g};}
    const g=this.gradient51.value;
    if (!this.peaks || this.peaks.length !== n) this.peaks = new Float32Array(n);
    const peaks = this.peaks;
    const vals = this.vals && this.vals.length === n ? this.vals : (this.vals = new Float32Array(n));

    const length=bins?.length||0,nyquist=(Player.ctx?.sampleRate||48000)/2,key=[length,nyquist,n].join('|');
    if(this.spectrumRangeKey51!==key){this.spectrumRangeKey51=key;this.spectrumRanges51=new Uint32Array(n*2);const high=Math.min(18000,nyquist);for(let i=0;i<n;i++){const from=Math.min(Math.max(0,length-1),Math.floor(30*Math.pow(high/30,i/n)/nyquist*length));this.spectrumRanges51[i*2]=from;this.spectrumRanges51[i*2+1]=Math.min(length,Math.max(from+1,Math.ceil(30*Math.pow(high/30,(i+1)/n)/nyquist*length)));}}
    const dt=Math.max(1/240,Math.min(.08,this.dt||1/60)),up=1-Math.exp(-22*dt),down=1-Math.exp(-7*dt),playing=bins&&audio&&!audio.paused&&!audio.ended;
    for(let i=0;i<n;i++){
      let v=0;
      if(playing){const from=this.spectrumRanges51[i*2],to=this.spectrumRanges51[i*2+1];let sum=0,peak=0;for(let k=from;k<to;k++){const value=bins[k];sum+=value*value;if(value>peak)peak=value;}v=(Math.sqrt(sum/Math.max(1,to-from))*.7+peak*.3)/255;}
      vals[i]+=(v-vals[i])*(v>vals[i]?up:down);peaks[i]=Math.max(vals[i],peaks[i]-.65*dt);
    }
    const at = i => (0.015 + vals[i] * 0.985) * span;

    ctx.shadowColor = this.fade(c1, 0.55);
    ctx.shadowBlur = budget.shadow&&audio&&!audio.paused?2+energy*4:0;
    if (kind === 'wave') {
      // Залитая волна: мягкая лента вокруг середины полосы.
      const paint = (from, to, alpha) => {
        if (to <= from) return;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.moveTo(from, mid);
        for (let i = 0; i < n; i++) {
          const x = (i / n) * w + bw / 2;
          if (x < from - 2 || x > to + 2) continue;
          ctx.lineTo(Math.max(from, Math.min(to, x)), mid - at(i));
        }
        for (let i = n - 1; i >= 0; i--) {
          const x = (i / n) * w + bw / 2;
          if (x < from - 2 || x > to + 2) continue;
          ctx.lineTo(Math.max(from, Math.min(to, x)), mid + at(i));
        }
        ctx.closePath(); ctx.fill();
      };
      paint(0, progress * w, 1);
      paint(progress * w, w, 0.3);
    } else if (kind === 'dots') {
      // Две заливки вместо двух сотен: со свечением каждая стоит дорого,
      // и именно на этом шкала раньше подлагивала.
      const r = Math.max(1.4, bw * 0.4);
      for (const played of [true, false]) {
        ctx.globalAlpha = played ? 1 : 0.3;
        ctx.fillStyle = g;
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          if ((i / n <= progress) !== played) continue;
          const x = (i / n) * w + bw / 2, d = at(i);
          ctx.moveTo(x + r, mid - d); ctx.arc(x, mid - d, r, 0, 6.283);
          ctx.moveTo(x + r, mid + d); ctx.arc(x, mid + d, r, 0, 6.283);
        }
        ctx.fill();
      }
    } else if (kind === 'led') {
      // Сегменты, как на старых индикаторах: столбик из коротких блоков.
      const seg = 5, gap = 2;
      const cells = Math.max(4, Math.floor(h / (seg + gap)));
      ctx.fillStyle=g;
      for(const litPass of [false,true]){ctx.globalAlpha=litPass?1:.055;ctx.beginPath();for(let i=0;i<n;i++){const x=i/n*w,lit=Math.round(vals[i]*cells);for(let c=0;c<cells;c++){if((c<lit)!==litPass)continue;ctx.rect(x,h-(c+1)*(seg+gap)+gap,bw,seg);}}ctx.fill();}
    } else if (kind === 'spike') {
      // Иглы: тонкие штрихи от середины в обе стороны.
      ctx.lineCap='round';ctx.globalAlpha=1;ctx.strokeStyle=g;ctx.lineWidth=Math.max(1,bw*.35);ctx.beginPath();for(let i=0;i<n;i++){const x=i/n*w+bw/2,d=at(i);ctx.moveTo(x,mid-d);ctx.lineTo(x,mid+d);}ctx.stroke();ctx.lineCap='butt';
    } else if (kind === 'line') {
      // Осциллограф: только тонкая зеркальная линия без полосок.
      for (const dir of [-1, 1]) {
        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = g;
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          const prev = vals[Math.max(0, i - 1)], next = vals[Math.min(n - 1, i + 1)];
          const sm = (prev + vals[i] * 2 + next) / 4;
          const x = (i / n) * w + bw / 2;
          const y = mid + dir * (0.07 + sm * 0.93) * span;
          if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        }
        ctx.stroke();
      }
    } else {
      // Пройденная и оставшаяся части — два пути и две заливки: свечение
      // считается дважды за кадр, а не на каждую полоску.
      const round = Math.min(bw / 2, 2.5);
      for (const played of [true, false]) {
        ctx.globalAlpha = played ? 1 : 0.3;
        ctx.fillStyle = g;
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          if ((i / n <= progress) !== played) continue;
          const bh = Math.max(2, at(i));
          const x = (i / n) * w;
          // Скруглённые верхушки: полоски перестают выглядеть «пиксельными».
          const y = mirror ? mid - bh : (top ? 0 : h - bh);
          const hh = mirror ? bh * 2 : bh;
          if (ctx.roundRect) ctx.roundRect(x, y, bw, hh, round);
          else ctx.rect(x, y, bw, hh);
        }
        ctx.fill();
      }
    }
    ctx.shadowBlur = 0;

    // Шапки пиков: тонкая черта над полоской, она задерживается на месте.
    if (S.vizPeaks !== false && kind !== 'wave' && kind !== 'line') {
      for (let i = 0; i < n; i++) {
        const ph = Math.max(2, (0.07 + peaks[i] * 0.93) * span);
        const x = (i / n) * w;
        ctx.globalAlpha = (i / n <= progress ? 0.85 : 0.22);
        ctx.fillStyle = c2;
        if (top) ctx.fillRect(x, Math.min(h - 1.5, ph + 0.5), bw, 1.5);
        else {
          ctx.fillRect(x, Math.max(0, mid - ph - 2), bw, 1.5);
          if (mirror) ctx.fillRect(x, Math.min(h - 1.5, mid + ph + 0.5), bw, 1.5);
        }
      }
    }

    // Огибающая: сглаженная линия по верхушкам полосок.
    if (kind !== 'wave' && kind !== 'line') {
      ctx.globalAlpha = 0.9;
      ctx.strokeStyle = top ? g : c2;
      ctx.lineWidth = top ? 3.4 : 1.6;
      ctx.lineJoin = 'round';
      ctx.shadowColor = this.fade(c2, 0.6);
      ctx.shadowBlur = budget.shadow?6:0;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const prev = vals[Math.max(0, i - 1)], next = vals[Math.min(n - 1, i + 1)];
        const sm = (prev + vals[i] * 2 + next) / 4;
        const y = top ? (0.07 + sm * 0.93) * span : mid - (0.07 + sm * 0.93) * span;
        const x = (i / n) * w + bw / 2;
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.stroke();
    }

    // Бегунок: светящаяся черта с точкой ровно на текущем месте трека.
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  },
};
if(typeof module!=='undefined'&&module.exports)module.exports=Viz;
