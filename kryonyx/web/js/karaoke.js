/* karaoke.js — синхронный текст и живой анимированный фон плеера. */
'use strict';

const Karaoke = {
  lines: [],
  synced: false,
  active: -1,
  canvas: null,
  ctx2d: null,
  raf: null,
  playing: false,
  palette: ['#7C5CFF', '#FF5CA8'],
  artToken: 0,
  bgToken: 0,
  data: null,
  blobs: [],
  particles: [],
  stars: [],
  rings: [],
  stageBlobs: [],
  phase: 0,

  init() {
    this.canvas = $('nowCanvas');
    this.ctx2d = this.canvas.getContext('2d', { alpha: true });
    this.resize();
    addEventListener('resize', debounce(() => this.resize(), 150));
    for (let i = 0; i < 6; i++) {
      this.blobs.push({
        x: Math.random(), y: Math.random(),
        r: 0.25 + Math.random() * 0.35,
        dx: (Math.random() - 0.5) * 0.00035,
        dy: (Math.random() - 0.5) * 0.00035,
        hue: i,
      });
    }
    for (let i = 0; i < 5; i++) {
      // Пятна сцены: огромные, мягкие и почти неподвижные — свет, а не фигуры.
      this.stageBlobs.push({
        t: Math.random() * Math.PI * 2,
        v: 0.0006 + Math.random() * 0.0009,
        ratio: 0.6 + Math.random() * 0.8,
        ph: Math.random() * Math.PI * 2,
        ax: 0.18 + Math.random() * 0.22,
        ay: 0.16 + Math.random() * 0.2,
        r: 0.42 + Math.random() * 0.3,
      });
    }
    for (let i = 0; i < 90; i++) {
      // Звёзды летят на зрителя: z — глубина, чем меньше, тем ближе.
      this.stars.push({ x: Math.random() * 2 - 1, y: Math.random() * 2 - 1,
                        z: Math.random() });
    }
    for (let i = 0; i < 70; i++) {
      this.particles.push({
        x: Math.random(), y: Math.random(),
        v: 0.0002 + Math.random() * 0.0009,
        s: 0.6 + Math.random() * 2.2,
      });
    }
  },

  resize() {
    if (!this.canvas) return;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    this.canvas.width = Math.floor(this.canvas.clientWidth * dpr) || 1;
    this.canvas.height = Math.floor(this.canvas.clientHeight * dpr) || 1;
    this.dpr = dpr;
  },

  /* Чувствительность эффектов к музыке: 0.2…2.0 (в настройках — проценты). */
  sense() {
    const value = +S.reactSense;
    return isFinite(value) ? Math.max(0.2, Math.min(2, value / 100)) : 1;
  },

  /* Палитра доезжает до цветов обложки даже тогда, когда главный цикл
     караоке не крутится. Раньше blend() жил только внутри draw-цикла, а он
     выключен в режимах «Диск» и «Визуализатор» (start() выходит на
     Disc.on || Viz.on) — поэтому там свечение и акценты навсегда
     оставались в цветах темы и под обложку не подстраивались. */
  pushPalette() {
    if (this._pr) return;
    const close = () => {
      if (!this.target || !this.palette) return true;
      const parse = c => {
        if (typeof c !== 'string') return [0, 0, 0];
        if (c.startsWith('#')) return hex2rgb(c);
        const m = c.match(/-?\d+/g) || [0, 0, 0];
        return [+m[0], +m[1], +m[2]];
      };
      return this.palette.every((c, i) => {
        const a = parse(c), b = parse(this.target[i] || this.target[0]);
        return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]) < 6;
      });
    };
    const step = () => {
      // Главный цикл сам всё сделает — второй таймер только мешал бы.
      if (this.raf) { this._pr = null; return; }
      this.blend(0.12);
      Disc.paintGlow();
      if (typeof Viz !== 'undefined' && Viz.on && Viz.repaintColors) Viz.repaintColors();
      if (close()) { this._pr = null; return; }
      this._pr = requestAnimationFrame(step);
    };
    this._pr = requestAnimationFrame(step);
  },

  /* Ссылки на обложку от крупной к мелкой. Для каждой добавляем и путь
     через локальный прокси: в WebView прямые запросы к CDN YouTube иногда
     отваливаются, а для чтения пикселей свой домен нужен обязательно —
     иначе холст «запятнан» и цвет посчитать нельзя. */
  artChain(url, base = 480, proxyFirst = false) {
    const out = [];
    const add = value => { if (value && !out.includes(value)) out.push(value); };
    coverVariants(url, coverSize(base)).forEach(variant => {
      let host = '';
      try { host = new URL(variant, location.href).hostname.toLowerCase(); } catch (_) {}
      const via = /(^|\.)((ytimg|ggpht|googleusercontent)\.com)$/.test(host)
        ? '/api/image/youtube?url=' + encodeURIComponent(variant) : '';
      if (via && proxyFirst) { add(via); add(variant); }
      else { add(variant); if (via) add(via); }
    });
    return out;
  },

  /* Первая ссылка из списка, которая действительно загрузилась. */
  firstLoadable(chain, done) {
    const step = index => {
      if (index >= chain.length) { done(''); return; }
      const img = new Image();
      img.decoding = 'async';
      img.onload = () => done(chain[index]);
      img.onerror = () => step(index + 1);
      img.src = chain[index];
    };
    step(0);
  },

  /* Палитра темы: сюда возвращаемся, когда обложки нет или её не удалось
     прочитать ни по одной ссылке. Раньше в этом случае фон и свечение
     молча оставались в цветах предыдущего трека. */
  themeColors() {
    this.target = [S.accent, S.accent2, S.accent2];
    if (!this.palette || this.palette.length !== 3) this.palette = this.target.slice();
    Atmo.setColors(null);
    Disc.paintGlow();
    this.pushPalette();
  },

  setArtwork(url) {
    if(window.CoverPalette23)CoverPalette23.begin(url);
    // Размытая обложка как подложка — фон сразу выглядит «дорого».
    Disc.setArt(url);
    const bg = $('nowArtBg');
    if (bg) {
      bg.classList.toggle('on', !!url && !!S.karaokeBg);
      // Фон — это background-image, у него нет onerror: если крупной версии
      // обложки не существует (у YouTube нет maxresdefault почти у половины
      // видео), подложка просто не появлялась. Проверяем ссылку картинкой и
      // спускаемся по запасным вариантам, как делает setImg().
      const bgToken = ++this.bgToken;
      if (!url) bg.style.backgroundImage = '';
      else this.firstLoadable(this.artChain(url, 720), src => {
        if (bgToken !== this.bgToken) return;
        bg.style.backgroundImage = src ? `url("${src}")` : '';
      });
    }
    // Целевая палитра: цвета фона подстраиваются под трек.
    // Палитра всегда из трёх цветов: при разной длине blend() подменял её
    // мгновенно, и фон дёргался вместо плавного перехода.
    const token = ++this.artToken;
    if (!this.palette || this.palette.length !== 3) {
      this.palette = [S.accent, S.accent2, S.accent2];
    }
    if (!url) { this.themeColors(); return; }

    // Сэмплить можно только незапятнанный холст. Картинки YouTube отдаются
    // без CORS-заголовков (а в WebView иногда и вовсе не грузятся напрямую),
    // поэтому для замера цвета сначала пробуем локальный прокси — он свой
    // домен, и getImageData с него работает всегда.
    const chain = this.artChain(url, 480, true);

    const sample = img => {
      const size = 64;
      const c = document.createElement('canvas');
      c.width = c.height = size;
      const cx = c.getContext('2d', { willReadFrequently: true });
      cx.drawImage(img, 0, 0, size, size);
      const { data } = cx.getImageData(0, 0, size, size);
      if(window.CoverPalette23)CoverPalette23.publish(url,data);
      const buckets = {};
      const grey = { n: 0, r: 0, g: 0, b: 0 };
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] < 24) continue;                  // прозрачные пиксели
        const r = data[i], g = data[i + 1], b = data[i + 2];
        const max = Math.max(r, g, b), min = Math.min(r, g, b);
        if (max >= 40) { grey.n++; grey.r += r; grey.g += g; grey.b += b; }
        if (max < 40 || max - min < 24) continue;        // серое и тёмное пропускаем
        const key = `${r >> 5}:${g >> 5}:${b >> 5}`;
        (buckets[key] = buckets[key] || { n: 0, r: 0, g: 0, b: 0 });
        buckets[key].n++; buckets[key].r += r; buckets[key].g += g; buckets[key].b += b;
      }
      let top = Object.values(buckets).sort((a, b) => b.n - a.n).slice(0, 3);
      // Чёрно-белая обложка: цветных пикселей нет вообще. Раньше палитра в
      // этом случае оставалась от прошлого трека — берём её средний тон.
      if (!top.length && grey.n) top = [grey];
      if (!top.length) top = [{ n: 1, r: 24, g: 24, b: 24 }];
      const list = top.map(bucket => `rgb(${Math.round(bucket.r / bucket.n)},`
        + `${Math.round(bucket.g / bucket.n)},${Math.round(bucket.b / bucket.n)})`);
      while (list.length < 3) list.push(list[list.length - 1]);
      this.target = list;
      Atmo.setColors(this.target);
      // Свечение сцены «Диска» берёт те же цвета, что и фон караоке.
      Disc.paintGlow();
      this.pushPalette();
      return true;
    };

    const tryAt = index => {
      if (token !== this.artToken) return;              // трек успели сменить
      if (index >= chain.length) { if(window.CoverPalette23)CoverPalette23.fail(url); this.themeColors(); return; }
      const src = chain[index];
      const img = new Image();
      const proxied = src.startsWith('/');
      // Своему домену crossOrigin не нужен, а чужому он нужен обязательно —
      // иначе холст «запятнан» и getImageData бросает исключение.
      if (!proxied) img.crossOrigin = 'anonymous';
      img.decoding = 'async';
      img.onload = () => {
        if (token !== this.artToken) return;
        let done = false;
        try { done = sample(img); } catch (_) { done = false; }
        if (!done) tryAt(index + 1);
      };
      img.onerror = () => tryAt(index + 1);             // раньше не было вовсе
      img.src = src;
    };
    tryAt(0);
  },

  setPlaying(playing) {
    this.playing = playing;
    Atmo.kick();
    Disc.setPlaying(playing);
    if (typeof Viz !== 'undefined') Viz.setPlaying(playing);
    const now = $('now');
    if (playing) this.start();
    else if (!now || !now.classList.contains('on')) this.stop();
  },

  start() {
    if(['aurora','albumflow'].includes(S.karaokeStyle)){this.stop();return;}
    if (this.raf || !S.karaokeBg || S.noAnim || Disc.on || Viz.on) return;
    let last = 0;
    const loop = now => {
      this.raf = requestAnimationFrame(loop);
      if (document.hidden || !$('now')?.classList.contains('on') || document.querySelector('.modal.on')) { this.stop(); return; }
      // 40 кадров в секунду достаточно и экономит батарею/процессор
      if (now - last < 24) return;
      last = now;
      this.blend();
      this.draw();
    };
    this.raf = requestAnimationFrame(loop);
  },

  stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = null;
  },

  /* Палитра переезжает к целевой плавно, без резкой смены картинки. */
  blend(speed) {
    if (!this.target) return;
    if (!this.palette || this.palette.length !== this.target.length) {
      this.palette = this.target.slice();
      return;
    }
    const parse = c => {
      if (c.startsWith('#')) return hex2rgb(c);
      const m = c.match(/-?\d+/g) || [0, 0, 0];
      return [+m[0], +m[1], +m[2]];
    };
    this.palette = this.palette.map((current, i) => {
      const a = parse(current), b = parse(this.target[i] || this.target[0]);
      const k = speed || 0.04;
      return `rgb(${Math.round(a[0] + (b[0] - a[0]) * k)},${Math.round(a[1] + (b[1] - a[1]) * k)},${Math.round(a[2] + (b[2] - a[2]) * k)})`;
    });
  },

  level() {
    const analyser = Player.analyser;
    if (!analyser) return { energy: 0, bins: null };
    // Один замер на кадр: уровень просят и сцена, и фон, и «Диск» —
    // второй раз читать анализатор незачем, а затухание удара от этого
    // раньше ускорялось вдвое.
    const now = performance.now();
    if (this._lvAt && now - this._lvAt < 8 && this._lv) return this._lv;
    const dt = Math.min(0.1, Math.max(0.004, (now - (this._lvAt || now - 16)) / 1000));
    this._lvAt = now;
    if (!this.data || this.data.length !== analyser.frequencyBinCount) {
      this.data = new Uint8Array(analyser.frequencyBinCount);
    }
    try { analyser.getByteFrequencyData(this.data); }
    catch { return { energy: 0, bins: null }; }
    let sum = 0;
    let bass = 0;
    const bassBins = Math.max(4, Math.floor(this.data.length * 0.08));
    for (let i = 0; i < this.data.length; i++) {
      sum += this.data[i];
      if (i < bassBins) bass += this.data[i];
    }
    // Чувствительность: один множитель на всю реакцию интерфейса — фон
    // караоке, пульс «Диска» и визуализатор читают уровень отсюда.
    const sense = this.sense();
    const energy = Math.min(1, sum / (this.data.length * 255) * sense);
    const bassLevel = Math.min(1, bass / (bassBins * 255) * sense);
    // Детекция удара по всплеску низов относительно их собственного фона.
    // Раньше удар требовал, чтобы бас был на 35 % выше среднего; на плотно
    // сведённых треках (фонк, EDM, рэп) низ всё время у потолка, и удар не
    // находился вовсе — искры, кольца, вспышки и молнии молчали. Теперь
    // считаем отклонение от среднего в единицах разброса и рост за кадр,
    // без насыщения, с коротким «замком» между ударами.
    const rawBass = bass / (bassBins * 255);
    const slow = 1 - Math.exp(-dt / 0.45);
    if (this.bassAvg == null) { this.bassAvg = rawBass; this.bassVar = 0.002; this.bassPrev = rawBass; }
    const dev = rawBass - this.bassAvg;
    this.bassAvg += dev * slow;
    this.bassVar += (dev * dev - this.bassVar) * slow;
    const rise = rawBass - (this.bassPrev || 0);
    this.bassPrev = rawBass;
    const spread = Math.sqrt(Math.max(1e-5, this.bassVar));
    const k = 1.15 / Math.max(0.5, sense);          // выше чувствительность — ниже порог
    const since = now - (this._beatAt || 0);
    if (since > 170 && rawBass > 0.12 && rise > 0.012
        && (dev > spread * k || rise > 0.09 / Math.max(0.5, sense))) {
      this.beat = 1;
      this._beatAt = now;
    }
    this.beat = Math.max(0, (this.beat || 0) - dt * 2.7);
    this._lv = { energy, bins: this.data, bass: bassLevel };
    return this._lv;
  },

  draw() {
    const ctx = this.ctx2d;
    if (!ctx) return;
    const w = this.canvas.width, h = this.canvas.height;
    const { energy, bins } = this.level();
    this.phase += 0.004 + energy * 0.02;
    ctx.clearRect(0, 0, w, h);

    if ((S.karaokeStyle || 'aurora') === 'stage') {
      this.drawStage(ctx, w, h, energy);
      return;
    }

    // базовый градиент — фон выглядит богато даже до анализа звука
    const base = ctx.createLinearGradient(0, 0, w, h);
    base.addColorStop(0, this.alpha(this.palette[0], 0.30));
    base.addColorStop(0.5, this.alpha(this.palette[1] || this.palette[0], 0.16));
    base.addColorStop(1, this.alpha(this.palette[2] || this.palette[0], 0.26));
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, w, h);

    const style = S.karaokeStyle || 'aurora';
    if (style === 'none') return;                 // только обложка и вуаль
    if (style === 'bars') this.drawBars(ctx, w, h, bins, energy);
    else if (style === 'waves') this.drawWaves(ctx, w, h, energy);
    else if (style === 'particles') this.drawParticles(ctx, w, h, energy);
    else if (style === 'rings') this.drawRings(ctx, w, h, energy);
    else if (style === 'grid') this.drawGrid(ctx, w, h, energy);
    else if (style === 'stars') this.drawStars(ctx, w, h, energy);
    else if (style === 'mirror') this.drawMirror(ctx, w, h, bins, energy);
    else if (style === 'glow') this.drawGlow(ctx, w, h, energy);
    else this.drawAurora(ctx, w, h, energy);
  },

  /* «Сцена» в духе Apple Music: почти чёрный зал и несколько огромных
     размытых пятен цвета обложки, которые еле плывут. Звук добавляет только
     дыхание — пятна не дёргаются в такт, иначе текст читать невозможно. */
  drawStage(ctx, w, h, energy) {
    const span = Math.hypot(w, h);
    const breathe = 1 + energy * 0.1 + (this.beat || 0) * 0.04;
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = '#05050A';
    ctx.fillRect(0, 0, w, h);

    ctx.globalCompositeOperation = 'lighter';
    this.stageBlobs.forEach((blob, i) => {
      blob.t += blob.v * (1 + energy);
      const x = (0.5 + Math.cos(blob.t) * blob.ax) * w;
      const y = (0.5 + Math.sin(blob.t * blob.ratio + blob.ph) * blob.ay) * h;
      const r = span * blob.r * breathe;
      const color = this.palette[i % this.palette.length] || this.palette[0];
      const grad = ctx.createRadialGradient(x, y, 0, x, y, r);
      grad.addColorStop(0, this.alpha(color, 0.24 + energy * 0.07));
      grad.addColorStop(0.45, this.alpha(color, 0.085));
      grad.addColorStop(1, this.alpha(color, 0));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    });

    // Виньетка прижимает свет к середине: края зала остаются чёрными.
    ctx.globalCompositeOperation = 'source-over';
    const vig = ctx.createRadialGradient(w / 2, h * 0.5, 0, w / 2, h * 0.5, span * 0.62);
    vig.addColorStop(0, 'rgba(0,0,0,0)');
    vig.addColorStop(0.6, 'rgba(0,0,0,.28)');
    vig.addColorStop(1, 'rgba(0,0,0,.74)');
    ctx.fillStyle = vig;
    ctx.fillRect(0, 0, w, h);
  },

  drawAurora(ctx, w, h, energy) {
    const beat = this.beat || 0;
    ctx.globalCompositeOperation = 'lighter';
    this.blobs.forEach((blob, i) => {
      blob.x += blob.dx * (1 + energy * 4);
      blob.y += blob.dy * (1 + energy * 4);
      if (blob.x < -0.15 || blob.x > 1.15) blob.dx *= -1;
      if (blob.y < -0.15 || blob.y > 1.15) blob.dy *= -1;

      const radius = blob.r * Math.min(w, h) * (0.85 + energy * 0.8 + beat * 0.25);
      const x = blob.x * w + Math.sin(this.phase * 0.9 + i * 1.7) * w * 0.05;
      const y = blob.y * h + Math.cos(this.phase * 1.2 + i * 2.1) * h * 0.05;
      const color = this.palette[i % this.palette.length];

      // три стопа вместо двух дают мягкий «мешевый» градиент без резкого края
      const grad = ctx.createRadialGradient(x, y, radius * 0.05, x, y, radius);
      grad.addColorStop(0, this.alpha(color, 0.5 + energy * 0.3 + beat * 0.16));
      grad.addColorStop(0.45, this.alpha(color, 0.24 + energy * 0.14));
      grad.addColorStop(1, this.alpha(color, 0));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();
    });

    // тонкие световые линии поверх — «шёлковый» блик
    ctx.globalCompositeOperation = 'screen';
    ctx.lineWidth = Math.max(1, this.dpr);
    for (let layer = 0; layer < 3; layer++) {
      const color = this.palette[layer % this.palette.length];
      ctx.strokeStyle = this.alpha(color, 0.07 + energy * 0.09);
      ctx.beginPath();
      for (let x = 0; x <= w; x += Math.max(8, w / 120)) {
        const t = x / w;
        const y = h * (0.35 + layer * 0.14)
          + Math.sin(t * 7 + this.phase * (1.1 + layer * 0.3)) * h * (0.05 + energy * 0.09)
          + Math.sin(t * 2.3 - this.phase) * h * 0.03;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    ctx.globalCompositeOperation = 'source-over';
  },

  drawWaves(ctx, w, h, energy) {
    for (let layer = 0; layer < 4; layer++) {
      const color = this.palette[layer % this.palette.length];
      ctx.beginPath();
      ctx.moveTo(0, h);
      const amp = h * (0.05 + energy * 0.16) * (1 + layer * 0.35);
      const base = h * (0.55 + layer * 0.1);
      for (let x = 0; x <= w; x += Math.max(6, w / 140)) {
        const t = x / w * Math.PI * 2;
        const y = base + Math.sin(t * (1.4 + layer * 0.5) + this.phase * (1 + layer * 0.4)) * amp;
        ctx.lineTo(x, y);
      }
      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fillStyle = this.alpha(color, 0.16 + layer * 0.05);
      ctx.fill();
    }
  },

  drawBars(ctx, w, h, bins, energy) {
    const count = 96;
    const gap = w / count;
    const grad = ctx.createLinearGradient(0, h, 0, 0);
    grad.addColorStop(0, this.alpha(this.palette[0], 0.85));
    grad.addColorStop(1, this.alpha(this.palette[1] || this.palette[0], 0.25));
    ctx.fillStyle = grad;
    for (let i = 0; i < count; i++) {
      const raw = bins ? bins[Math.floor((i / count) * bins.length * 0.7)] / 255
                       : 0.2 + Math.abs(Math.sin(this.phase * 2 + i)) * 0.3;
      const barHeight = Math.max(h * 0.012,
        raw * h * 0.6 * (0.6 + energy) * (1 + (this.beat || 0) * 0.18));
      const x = i * gap + gap * 0.18;
      const width = gap * 0.64;
      const y = h - barHeight;
      const r = Math.min(width / 2, 8);
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, y, width, barHeight, r)
                    : ctx.rect(x, y, width, barHeight);
      ctx.fill();
    }
  },

  drawParticles(ctx, w, h, energy) {
    ctx.fillStyle = this.alpha(this.palette[0], 0.55);
    this.particles.forEach((p, i) => {
      p.y -= p.v * (1 + energy * 8);
      if (p.y < -0.05) { p.y = 1.05; p.x = Math.random(); }
      const x = (p.x + Math.sin(this.phase + i) * 0.01) * w;
      const size = p.s * this.dpr * (1 + energy * 2);
      ctx.fillStyle = this.alpha(this.palette[i % this.palette.length], 0.28 + energy * 0.4);
      ctx.beginPath();
      ctx.arc(x, p.y * h, size, 0, Math.PI * 2);
      ctx.fill();
    });
  },

  /* Кольца: на каждый удар от центра расходится волна. */
  drawRings(ctx, w, h, energy) {
    const beat = this.beat || 0;
    if (beat > 0.85 || (!this.rings.length && energy > 0.05)) {
      if (!this.rings.length || this.rings[this.rings.length - 1].r > 0.12) {
        this.rings.push({ r: 0.02, c: this.palette[this.rings.length % this.palette.length] });
      }
    }
    if (this.rings.length > 9) this.rings.shift();
    const cx = w / 2, cy = h / 2, max = Math.hypot(w, h) / 2;
    ctx.globalCompositeOperation = 'lighter';
    ctx.lineWidth = Math.max(1.5, this.dpr * 2);
    this.rings = this.rings.filter(ring => {
      ring.r += 0.0045 + energy * 0.012;
      if (ring.r >= 1) return false;
      ctx.strokeStyle = this.alpha(ring.c, (1 - ring.r) * (0.35 + energy * 0.35));
      ctx.beginPath();
      ctx.arc(cx, cy, ring.r * max, 0, Math.PI * 2);
      ctx.stroke();
      return true;
    });
    // Пульс в центре — по низам.
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, max * (0.25 + beat * 0.3));
    grad.addColorStop(0, this.alpha(this.palette[0], 0.22 + beat * 0.3));
    grad.addColorStop(1, this.alpha(this.palette[0], 0));
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
    ctx.globalCompositeOperation = 'source-over';
  },

  /* Перспективная сетка: линии уезжают к горизонту, как в синтвейве. */
  drawGrid(ctx, w, h, energy) {
    const horizon = h * 0.52;
    const speed = 0.35 + energy * 1.6;
    this.gridPhase = ((this.gridPhase || 0) + speed * 0.006) % 1;
    ctx.globalCompositeOperation = 'lighter';
    ctx.lineWidth = Math.max(1, this.dpr);

    // Свечение горизонта.
    const glow = ctx.createLinearGradient(0, horizon - h * 0.2, 0, horizon + h * 0.05);
    glow.addColorStop(0, this.alpha(this.palette[0], 0));
    glow.addColorStop(1, this.alpha(this.palette[1] || this.palette[0], 0.3 + energy * 0.25));
    ctx.fillStyle = glow;
    ctx.fillRect(0, horizon - h * 0.2, w, h * 0.25);

    ctx.strokeStyle = this.alpha(this.palette[0], 0.3 + energy * 0.3);
    for (let i = 0; i < 16; i++) {
      const t = (i + this.gridPhase) / 16;
      const y = horizon + (h - horizon) * t * t;   // квадрат даёт перспективу
      ctx.globalAlpha = Math.min(1, t * 1.6);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.strokeStyle = this.alpha(this.palette[1] || this.palette[0], 0.22 + energy * 0.25);
    for (let i = -10; i <= 10; i++) {
      ctx.beginPath();
      ctx.moveTo(w / 2 + i * w * 0.02, horizon);
      ctx.lineTo(w / 2 + i * w * 0.34, h);
      ctx.stroke();
    }
    ctx.globalCompositeOperation = 'source-over';
  },

  /* Звёздное поле: полёт сквозь звёзды, скорость зависит от громкости. */
  drawStars(ctx, w, h, energy) {
    const cx = w / 2, cy = h / 2;
    ctx.globalCompositeOperation = 'lighter';
    this.stars.forEach((star, i) => {
      star.z -= 0.0022 + energy * 0.012;
      if (star.z <= 0.02) {
        star.z = 1; star.x = Math.random() * 2 - 1; star.y = Math.random() * 2 - 1;
      }
      const k = 0.5 / star.z;
      const x = cx + star.x * k * w * 0.5;
      const y = cy + star.y * k * h * 0.5;
      if (x < 0 || x > w || y < 0 || y > h) return;
      const size = Math.max(0.6, (1 - star.z) * 2.6 * this.dpr);
      ctx.fillStyle = this.alpha(this.palette[i % this.palette.length],
                                 0.25 + (1 - star.z) * 0.6);
      ctx.beginPath();
      ctx.arc(x, y, size, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalCompositeOperation = 'source-over';
  },

  /* Зеркальный спектр: столбцы растут от середины вверх и вниз. */
  drawMirror(ctx, w, h, bins, energy) {
    const count = 72;
    const gap = w / count;
    const mid = h / 2;
    for (let i = 0; i < count; i++) {
      const raw = bins ? bins[Math.floor((i / count) * bins.length * 0.7)] / 255
                       : 0.2 + Math.abs(Math.sin(this.phase * 2 + i * 0.4)) * 0.3;
      const half = Math.max(h * 0.008, raw * h * 0.3 * (0.6 + energy));
      const x = i * gap + gap * 0.2;
      const width = gap * 0.6;
      const color = this.palette[i % this.palette.length];
      const grad = ctx.createLinearGradient(0, mid - half, 0, mid + half);
      grad.addColorStop(0, this.alpha(color, 0.1));
      grad.addColorStop(0.5, this.alpha(color, 0.75));
      grad.addColorStop(1, this.alpha(color, 0.1));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, mid - half, width, half * 2, width / 2)
                    : ctx.rect(x, mid - half, width, half * 2);
      ctx.fill();
    }
  },

  /* Спокойное свечение: мягко дышит в такт низам, ничего не мельтешит. */
  drawGlow(ctx, w, h, energy) {
    const beat = this.beat || 0;
    const cx = w / 2, cy = h * 0.55;
    const r = Math.hypot(w, h) * (0.35 + energy * 0.18 + beat * 0.08);
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, this.alpha(this.palette[0], 0.3 + energy * 0.2));
    grad.addColorStop(0.6, this.alpha(this.palette[1] || this.palette[0], 0.12));
    grad.addColorStop(1, this.alpha(this.palette[0], 0));
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);
  },

  alpha(color, value) {
    if (color.startsWith('#')) return rgba(color, value);
    return color.replace('rgb(', 'rgba(').replace(')', `,${value})`);
  },

  /* --------------------------------------------------------------- текст */
  /* Караоке сделано по образцу Apple Music:
       * текущая строка загорается целиком в момент начала вокала;
       * активная строка крупнее, соседние приглушены и слегка размыты;
       * перед вступлением и в проигрышах идут точки отсчёта;
       * прокрутка не «прыгает», а плавно догоняет строку;
       * пролистал руками — автопрокрутка вежливо ждёт и предлагает вернуться.

     Правила синхронизации (их легко сломать, поэтому они здесь явно):
       1. Единственный источник времени — audio.currentTime, прочитанный
          внутри requestAnimationFrame (Player.tick). Никаких setInterval,
          setTimeout и timeupdate: они дают рваный шаг и накопленный дрейф.
       2. Вся арифметика идёт по одной шкале: time = currentTime + offset − HOLD.
          Поэтому строки, слова и точки отсчёта не могут разъехаться между собой.
       3. За кадр меняются только CSS-переменные и классы изменившихся узлов.
          Ни innerHTML, ни перебора всего текста в цикле отрисовки нет. */

  lineNodes: [],
  lineRows: [],           // { span, state } — узел текста каждой строки
  dotNodes: [],
  follow: true,
  scrollTo: null,
  glideRaf: null,
  userAt: 0,
  offsets: {},            // подгонка времени по трекам: id → секунды
  trackId: null,

  lastTime: null,         // время прошлого кадра — пустые кадры пропускаем
  hint: -1,               // подсказка для поиска строки: почти всегда та же
  painted: null,          // какая строка была активной при прошлой отрисовке
  dotsOn: -1,             // у какой строки сейчас горят точки отсчёта
  restingOn: -1,          // какая строка «догорает» в проигрыше

  FOLLOW_BACK: 5200,      // столько ждём после ручной прокрутки
  // Метки в текстах почти всегда стоят на волосок раньше голоса. Лучше
  // зажечь строку чуть позже, чем раньше: опережение сразу видно, а
  // небольшая выдержка читается как попадание в такт.
  HOLD: 0,
  ANCHOR: 0.42,           // активная строка держится чуть выше середины

  /* --------------------------------------------------- подгонка времени */
  /* Метки в открытых базах текстов сняты с другого издания трека: у клипа
     бывает вступление, у ремастера — другая длина. Поэтому у каждого трека
     своя поправка, она живёт в базе на устройстве и применяется молча. */
  /* Задержка вывода звука: между currentTime и тем, что реально слышно,
     стоит буфер аудиосистемы (на Bluetooth-наушниках — 150–300 мс). Браузер
     сообщает её сам; вычитаем, чтобы текст шёл под то, что слышно ушами. */
  latency() {
    const ctx = Player.ctx;
    if (!ctx || ctx.state !== 'running') return 0;
    const now = performance.now();
    if (this._latAt && now - this._latAt < 1000) return this._lat;   // раз в секунду хватает
    this._latAt = now;
    const value = (+ctx.outputLatency || 0) + (+ctx.baseLatency || 0);
    this._lat = value > 0 && value < 0.6 ? value : 0;
    return this._lat;
  },

  /* Коэффициент растяжения шкалы. Метки часто сняты с другого издания
     трека: при той же первой строке к концу песни текст уезжает на секунды.
     Если сервер сообщил длину записи, с которой сняты метки, и она близка к
     длине нашего файла (±5 %), шкалу масштабируем — расхождение копится
     линейно, поэтому одного множителя достаточно. */
  rate() {
    if (S.lyricsFit === false) return 1;
    const src = +this.srcDuration || 0;
    const own = +(Player.audio && Player.audio.duration) || 0;
    if (!(src > 30) || !(own > 30)) return 1;
    const k = src / own;
    // Раньше тянули при расхождении до 5 % — на пятиминутном треке это
    // пятнадцать секунд натяжки. Если запись длиннее или короче настолько,
    // дело почти всегда не в другом издании, а в чужой заливке со
    // вступлением: там нужен сдвиг (его находит autoFit), а не растяжение.
    if (k < 0.98 || k > 1.02) return 1;
    if (Math.abs(src - own) < 1) return 1;         // в пределах погрешности
    return k;
  },

  /* Шкала времени текста без выдержки: «сырое» время трека с поправками.
     Режимам, у которых своя выдержка (например «Диск»), нужна именно она —
     иначе выдержка применяется дважды и текст опаздывает. */
  base(raw) {
    if (this.precise) return raw + this.offset();
    return raw * this.rate() + this.offset() - this.latency() * (Player.audio?.playbackRate || 1);
  },

  /* Единая шкала времени текста для всех режимов. */
  clock(raw) {
    return this.base(raw) - (this.precise ? 0 : this.HOLD);
  },

  /* Подстройка «в такт»: нажми T (или кнопку), когда слышишь начало строки.
     Ближайшая строка в пределах 2 с встаёт ровно на этот момент; несколько
     нажатий усредняются, поэтому случайный промах почти не портит поправку. */
  tap() {
    if (!this.synced || !this.lines.length || !Player.audio || !this.trackId) {
      toast(t('Tap sync needs synced lyrics')); return;
    }
    const now = this.clock(Player.audio.currentTime);
    let best = -1, dist = 2;
    this.lines.forEach((line, i) => {
      const d = Math.abs(line.time - now);
      if (d < dist) { dist = d; best = i; }
    });
    if (best < 0) { toast(t('No line nearby — tap right when a line starts')); return; }
    const delta = this.lines[best].time - now;          // на сколько сдвинуть текст
    this.taps = (this.taps || []).filter(tp => tp.track === this.trackId).slice(-3);
    this.taps.push({ track: this.trackId, delta });
    const avg = this.taps.reduce((sum, tp) => sum + tp.delta, 0) / this.taps.length;
    const base = +this.offsets[this.trackId] || 0;
    // Сдвигаем на среднее из последних нажатий, но плавно — на половину.
    const value = Math.round((base + avg * (this.taps.length > 1 ? 0.5 : 1)) * 100) / 100;
    if (Math.abs(value) < 0.03) delete this.offsets[this.trackId];
    else this.offsets[this.trackId] = value;
    if (this.auto) this.auto.done = true;          // дальше ведёт человек
    this.saveOffsets();
    this.paintSync();
    this.resync();
    toast(t('Lyrics timing') + ': ' + (value > 0 ? '+' : '') + value.toFixed(2) + 's');
  },

  /* ------------------------------------------------ автоматическая подгонка

     Беда, ради которой всё это написано: текст подходит песне, а едет на
     секунды. Причина почти всегда одна — у нашей заливки на YouTube другое
     начало: вступление, тишина, склейка из альбома. Метки при этом верные,
     просто вся дорожка стоит не там, и человек видит караоке, которое
     «очень спешит» или «очень отстаёт».

     Чинится это слухом, а не длительностью: раз в восьмую долю секунды
     запоминаем громкость голосовой полосы (200–3500 Гц) и сравниваем её с
     разметкой — там, где в тексте строка, голос должен звучать, а в
     проигрышах полоса пустая. Перебираем сдвиги в пределах ±20 с и берём
     тот, при котором совпадение заметно лучше нынешнего. Поправка ложится
     в ту же копилку, что и ручная (offsets), поэтому её видно в плеере,
     её можно поправить клавишами и сбросить одной кнопкой. */
  auto: null,

  AUTO_RANGE: 20,         // насколько далеко ищем сдвиг, секунды
  AUTO_STEP: 0.1,
  AUTO_MIN: 45,           // столько секунд звука нужно для первой оценки
  AUTO_MAX: 150,          // после этого сдаёмся и больше не считаем
  AUTO_GAIN: 0.12,        // насколько совпадение должно стать лучше

  /* Громкость голосовой полосы прямо сейчас, 0..1. */
  voiceLevel() {
    const analyser = Player.analyser;
    const ctx = Player.ctx;
    if (!analyser || !ctx) return -1;
    if (!this.voiceBuf || this.voiceBuf.length !== analyser.frequencyBinCount) {
      this.voiceBuf = new Uint8Array(analyser.frequencyBinCount);
    }
    analyser.getByteFrequencyData(this.voiceBuf);
    const perBin = (ctx.sampleRate / 2) / this.voiceBuf.length;
    const from = Math.max(1, Math.floor(200 / perBin));
    const to = Math.min(this.voiceBuf.length - 1, Math.ceil(3500 / perBin));
    if (to <= from) return -1;
    let sum = 0;
    for (let i = from; i <= to; i++) sum += this.voiceBuf[i];
    return sum / ((to - from + 1) * 255);
  },

  /* Один замер за кадр, не чаще восьми раз в секунду. */
  autoSample(raw) {
    if (this.precise || S.lyricsAutoSync === false || !this.synced || !this.trackId) return;
    if (!this.lines.length || !Player.audio || Player.audio.paused) return;
    let box = this.auto;
    if (!box || box.track !== this.trackId) {
      // Человек уже подвинул текст руками — не спорим с ним.
      const manual = Math.abs(+this.offsets[this.trackId] || 0) > 0.05;
      box = this.auto = { track: this.trackId, t: [], v: [], last: -9, done: manual || this.autoResults?.[this.trackId]?.signature === this.lyricSignature };
    }
    if (box.done || raw - box.last < 0.12 || raw < box.last) {
      if (raw < box.last) box.last = raw;          // перемотка назад
      return;
    }
    const level = this.voiceLevel();
    if (level < 0) { box.done = true; return; }    // нет анализатора — нечем слушать
    box.last = raw;
    box.t.push(raw);
    box.v.push(level);
    // Полный перебор — дело не бесплатное: считаем раз в восемь секунд.
    if (box.t.length % 64 === 0) this.autoFit(box);
  },

  /* Отрезки, на которых по разметке должен звучать голос. */
  voiceSpans() {
    if (this._spansFor === this.trackId && this._spans) return this._spans;
    const spans = [];
    this.lines.forEach((line, i) => {
      const start = +line.time || 0;
      const next = this.lines[i + 1];
      let stop = +line.end || 0;
      if (!(stop > start)) {
        stop = next ? Math.min(+next.time || start + 3, start + 9) : start + 3;
      }
      const last = spans[spans.length - 1];
      if (last && start - last[1] < 0.35) last[1] = Math.max(last[1], stop);
      else spans.push([start, stop]);
    });
    this._spans = spans;
    this._spansFor = this.trackId;
    return spans;
  },

  /* Поиск сдвига: считаем совпадение громкости с разметкой. */
  async autoFit(box) {
    if (box.fitPending42 || box.done || box.t.length < 2) return;
    const span=box.t[box.t.length-1]-box.t[0];
    if (span<this.AUTO_MIN) return;
    const key=()=>[this.trackId,this.lyricSignature,this.offset(),this.rate(),this.precise].join('|');
    const identity=key();
    box.fitPending42=true;
    try {
      const result=await KFit42.run({times:box.t.map(t=>this.clock(t)),values:box.v.slice(),
        spans:this.voiceSpans().map(s=>s.slice()),span,range:this.approx?30:this.AUTO_RANGE,
        step:this.AUTO_STEP,min:this.AUTO_MIN,max:this.AUTO_MAX,gain:this.AUTO_GAIN});
      // Track, manual offset, speed or document may have changed while searching.
      if (!result || S.lyricsAutoSync === false || this.auto!==box || key()!==identity || box.done) return;
      if (!result.accepted) { if(result.done)box.done=true; if(result.wrong)this.wrongRecord(); return; }
      const shift=result.shift,sharp=result.confidence;
      box.done = true;
      const value = Math.round(((+this.offsets[this.trackId] || 0) + shift) * 20) / 20;
      if (Math.abs(value) < 0.005) delete this.offsets[this.trackId];
      else this.offsets[this.trackId] = value;
      this.autoResults = this.autoResults || {}; this.autoResults[this.trackId] = { offset:value, confidence:sharp, signature:this.lyricSignature };
      api('/api/state',{method:'PUT',body:{key:'lyricsAutoResults',value:this.autoResults}}).catch(()=>{});
      this.saveOffsets();
      this.paintSync();
      this.resync();
      toast(t('Karaoke timing matched to the track') + ': ' +
            (value > 0 ? '+' : '') + value.toFixed(2) + 's');
    } finally { box.fitPending42=false; }
  },

  /* Текст подходит по названию, но под звук не ложится совсем. */
  wrongRecord() {
    if (this._warned === this.trackId) return;
    this._warned = this.trackId;
    toast(t('These lyrics seem to be from another recording — try “Find lyrics by hand”'), 6000);
  },

  offset() {
    const own = this.trackId ? (+this.offsets[this.trackId] || 0) : 0;
    return (+S.lyricsOffset || 0) + own;
  },

  /* Ручной выбор записи текста: trackId -> id записи LRCLIB. */
  picks: {},

  async loadPicks() {
    try {
      const data = await api('/api/state?key=lyricsPicks', { timeout: 6000 });
      if (data && data.value && typeof data.value === 'object') this.picks = data.value;
    } catch { /* сервер ещё поднимается */ }
  },

  savePicks() {
    api('/api/state', { method: 'PUT', body: { key: 'lyricsPicks', value: this.picks } })
      .catch(() => {});
  },

  async loadOffsets() {
    try {
      const data = await api('/api/state?key=lyricsOffsets', { timeout: 6000 });
      if (data && data.value && typeof data.value === 'object') this.offsets = data.value;
    } catch { /* сервер ещё поднимается */ }
    try { this.autoResults = (await api('/api/state?key=lyricsAutoResults', { timeout: 6000 })).value || {}; } catch {}
  },

  saveOffsets() {
    clearTimeout(this._offTimer);
    this._offTimer = setTimeout(() => {
      api('/api/state', { method: 'PUT', body: { key: 'lyricsOffsets', value: this.offsets } })
        .catch(() => {});
    }, 500);
  },

  /* Минус — текст спешит, плюс — отстаёт. */
  nudge(delta) {
    if (!this.trackId) { toast(t('Pick a track first')); return; }
    const value = Math.round(((+this.offsets[this.trackId] || 0) + delta) * 100) / 100;
    if (Math.abs(value) < 0.005) delete this.offsets[this.trackId];
    else this.offsets[this.trackId] = value;
    if (this.auto) this.auto.done = true;          // дальше ведёт человек
    this.saveOffsets();
    this.paintSync();
    this.resync();
    toast(t('Lyrics timing') + ': ' + (value > 0 ? '+' : '') + value.toFixed(2) + 's');
  },

  resetOffset() {
    if (!this.trackId || !this.offsets[this.trackId]) return;
    delete this.offsets[this.trackId];
    if(this.autoResults) delete this.autoResults[this.trackId];
    api('/api/state',{method:'PUT',body:{key:'lyricsAutoResults',value:this.autoResults||{}}}).catch(()=>{});
    this.auto = null;                               // можно подобрать заново
    this.saveOffsets();
    this.paintSync();
    this.resync();
    toast(t('Lyrics timing reset'));
  },

  /* Полный пересчёт подсветки на месте — без перезагрузки текста.
     Зовётся после смены поправки и после перемотки. */
  resync(instant = true) {
    if (!Player.audio) return;
    this.hint = -1;
    this.painted = null;
    this.active = -1;
    this.lastTime = null;
    this.dotsOn = -1;
    this.restingOn = -1;
    this.onTime(Player.audio.currentTime, instant);
  },

  /* Перемотка: подсветка и прокрутка встают на новое место без анимации. */
  seek(time) {
    if (Disc.on) Disc.reset();
    if (!this.synced || !this.lines.length) return;
    this.scrollTo = null;
    this.follow = true;
    this.chip(false);
    this.hint = -1;
    this.painted = null;
    this.active = -1;
    this.lastTime = null;
    this.dotsOn = -1;
    this.restingOn = -1;
    const at = time != null ? time : (Player.audio ? Player.audio.currentTime : 0);
    this.onTime(at, !(performance.now() < (this.smoothSeekUntil33 || 0)));
  },

  paintSync() {
    const quickValue = $('karaokeTimingValue45');
    const validTrack = !!this.trackId && Player.current?.id === this.trackId;
    if (quickValue) { const v = validTrack ? (+this.offsets[this.trackId] || 0) : 0; quickValue.textContent = (v > 0 ? '+' : '') + v.toFixed(2) + 's'; }
    for (const id of ['karaokeTimingMinus45','karaokeTimingFineMinus78','karaokeTimingFinePlus78','karaokeTimingPlus45','karaokeTimingReset45']) if ($(id)) $(id).disabled = !validTrack;
    const exact = $('karaokeExactOffset');
    if (exact) exact.value = this.trackId ? (+this.offsets[this.trackId] || 0) : 0;
    const node = $('nSyncVal');
    if (!node) return;
    const value = this.trackId ? (+this.offsets[this.trackId] || 0) : 0;
    node.textContent = (value > 0 ? '+' : '') + value.toFixed(2) + 's';
    node.classList.toggle('on', Math.abs(value) > 0.05);
    const row = $('nSyncRow');
    if (row) row.style.display = this.synced ? '' : 'none';
  },

  async onTrack(track, options = {}) {
    if (typeof KFit42 !== 'undefined') KFit42.cancel();
    const nextId = track && track.id ? track.id : null;
    if (this.findFor && nextId !== this.findFor) {
      this.findToken = (this.findToken || 0) + 1;
      this.findFor = null;
      if ($('mLyrics')?.classList.contains('on')) closeModals();
    }
    if(nextId!==this.trackId)this.variant="";
    this.trackId = nextId;
    this.lines = [];
    this.precise = false; this.document = null;
    this.fetchToken = (this.fetchToken || 0) + 1;
    this.synced = false;
    this.paintSync();
    this.srcDuration = 0;
    this.auto = null;
    this._spans = null;
    this.approx = false;
    this.active = -1;
    this.lineNodes = [];
    this.lineRows = [];
    this.dotNodes = [];       // раньше оставались узлы прошлого трека
    this.hint = -1;
    this.painted = null;
    this.lastTime = null;
    this.dotsOn = -1;
    this.restingOn = -1;
    this.follow = true;
    this.scrollTo = null;
    this.empty(t('Loading lyrics…'), 'load');
    if (typeof KaraokeTools !== 'undefined') KaraokeTools.resetTrack();
    Disc.reset();
    if (!S.autoLyrics && !options.force) {
      this.empty(t('Karaoke is turned off in settings'));
      return;
    }
    await this.fetchLyrics(track);
  },

  /* Пустой экран текста. Без надписи (empty('')) он остаётся совсем
     чистым: у трека просто нет караоке-текста, и сообщать об этом
     каждый раз не нужно — экран не должен об этом кричать. */
  empty(text, kind = '') {
    const box = $('lyrics');
    if (!box) return;
    box.classList.remove('synced');
    this.lineNodes = [];
    this.lineRows = [];
    this.dotNodes = [];
    if (!text) {
      box.innerHTML = '';
      this.chip(false);
      return;
    }
    box.innerHTML = `<div class="empty${kind ? ' ' + kind : ''}">${icon('lyrics')}` +
      `<div>${esc(text)}</div></div>`;
    this.chip(false);
    // Текста нет или он чужой — отсюда можно сразу найти его руками.
    if (kind !== 'load' && Player.current) {
      const find = el('button', 'btn g sm', t('Find lyrics'));
      find.style.marginTop = '12px';
      find.onclick = () => this.openFind();
      const holder = box.querySelector('.empty');
      if (holder) holder.appendChild(find);
    }
  },

  /* ------------------------------------------- ручной поиск текста */
  /* Автоподбор ищет по названию трека, и у заголовков с YouTube он иногда
     промахивается. Здесь задаются ник исполнителя и название песни, сервер
     отдаёт список записей LRCLIB, а выбор запоминается для этого трека. */
  openFind() {
    const track = Player.current;
    if (!track) { toast(t('Pick a track first')); return; }
    this.findFor = track.id;
    const artist = $('lyrArtist');
    const title = $('lyrTitle');
    if (artist) artist.value = track.artist || '';
    if (title) title.value = track.title || '';
    openModal('mLyrics');
    this.findRun();
  },

  async findRun() {
    const box = $('lyrList');
    if (!box) return;
    const artist = ($('lyrArtist').value || '').trim();
    const title = ($('lyrTitle').value || '').trim();
    const token = this.findToken = (this.findToken || 0) + 1;
    const trackId = this.findFor;
    if (!artist && !title) {
      box.innerHTML = `<div class="plug-empty">${t('Type an artist or a title')}</div>`;
      return;
    }
    box.innerHTML = `<div class="plug-empty">${t('Searching…')}</div>`;
    try {
      const params = new URLSearchParams({ artist, title });
      const data = await api('/api/lyrics/search?' + params, { timeout: 20000 });
      if (token !== this.findToken || trackId !== this.findFor || Player.current?.id !== trackId) return;
      const items = data.items || [];
      box.innerHTML = '';
      if (!items.length) {
        box.innerHTML = `<div class="plug-empty">${t('No lyrics found for this name')}</div>`;
      }
      items.forEach(item => {
        const row = el('button', 'lyr-pick');
        const meta = [
          item.album || '',
          item.duration ? fmt(item.duration) : '',
          item.synced ? t('synced') : t('plain text'),
          item.lines ? item.lines + ' ' + t('lines') : '',
        ].filter(Boolean).join(' · ');
        row.innerHTML = `<span class="lp-text"><b>${esc(item.title)}</b>` +
          `<span>${esc(item.artist)}</span><small>${esc(meta)}</small></span>`;
        row.onclick = () => this.usePick(item.id);
        box.appendChild(row);
      });
      // The fallback does not expose identity/duration metadata. Never select it
      // automatically: keep it available only as a clearly labelled manual choice.
      if (artist && title && artist.length <= 300 && title.length <= 300) {
        const fallback = el('button', 'lyr-pick');
        const label = LANG === 'ru' ? 'lyrics.ovh — непроверенное совпадение, обычный текст' : 'lyrics.ovh — unverified match, plain text';
        fallback.textContent = label;
        fallback.onclick = () => this.usePick('ovh:' + JSON.stringify([artist, title]));
        box.appendChild(fallback);
      }
    } catch (err) {
      if (token !== this.findToken || trackId !== this.findFor || Player.current?.id !== trackId) return;
      box.innerHTML = `<div class="plug-empty">${esc(err.message || t('Search failed'))}</div>`;
    }
  },

  usePick(id) {
    const track = Player.current;
    if (!track || !id || track.id !== this.findFor) return;
    this.picks[track.id] = id;
    this.savePicks();
    dropCache('/api/lyrics');
    closeModals();
    toast(t('Lyrics replaced'));
    this.onTrack(track, { force: true });
  },

  clearPick() {
    const track = Player.current;
    if (!track) return;
    if (this.picks[track.id]) {
      delete this.picks[track.id];
      this.savePicks();
    }
    dropCache('/api/lyrics');
    closeModals();
    toast(t('Lyrics are matched automatically again'));
    this.onTrack(track, { force: true });
  },

  bindFind() {
    const go = $('lyrGo');
    if (go) go.onclick = () => this.findRun();
    const auto = $('lyrAuto');
    if (auto) auto.onclick = () => this.clearPick();
    ['lyrArtist', 'lyrTitle'].forEach(id => {
      const node = $(id);
      if (node) node.onkeydown = event => {
        if (event.key === 'Enter') { event.preventDefault(); this.findRun(); }
      };
    });
    const button = $('kFind');
    if (button) button.onclick = () => this.openFind();
  },

  /* Подписи источника («--- www.LRCgenerator.com ---», «Synced by …») не
     часть песни: сервер их уже вырезает (kryonyx/lyrics.py), здесь — вторая
     сетка для текста из старого кэша и из плагинов. */
  dropPromo(lines) {
    const link = /(?:https?:\/\/|www\.)|\b[\w-]+\.(?:com|net|org|ru|io|co|me|info|tv|xyz)\b/i;
    const names = /lrcgenerator|lrclib|lrcget|megalobiz|rentanadviser|lyricsify|azlyrics|musixmatch|karafun|amalgama|zaycev/i;
    const credit = /^(?:lrc|lyrics?|text|sync(?:ed|hronized)?|timing|timed|tagged|transcribed|translated|subtitles?|edited|uploaded|submitted|created|made)\b[^.!?]{0,40}?\b(?:by|from)\b.{0,40}$/i;
    const core = row => String((row && row.text) || '')
      .replace(/^[\s\-–—=*_~·•.<>[\](){}"'«»|/\\#]+|[\s\-–—=*_~·•.<>[\](){}"'«»|/\\#]+$/g, '')
      .trim();
    const out = lines.filter(row => {
      const text = core(row);
      if (!text) return true;
      return !(link.test(text) || names.test(text));
    });
    // Мягкое правило — только по краям: «made by» бывает и в песне.
    for (let pass = 0; pass < 2; pass++) {
      if (out.length && credit.test(core(out[0]))) out.shift();
      if (out.length && credit.test(core(out[out.length - 1]))) out.pop();
    }
    return out;
  },

  async fetchLyrics(track) {
    if (!track) return;
    const id = track.id;
    const token = this.fetchToken = (this.fetchToken || 0) + 1;
    try {
      const params = new URLSearchParams({ title: track.title || "", artist: track.artist || "", track_id:id });
      if(this.variant) params.set("variant",this.variant);
      // Запись, выбранная вручную в «Найти текст», важнее автоподбора.
      const pick = this.picks[track.id];
      if (pick) params.set('lrc', String(pick));
      // Длительность берём у самого аудио: в карточке поиска она часто
      // округлена или взята у другой версии, а по ней сервер отбирает
      // запись текста — ошибка здесь и даёт «караоке спешит».
      const secs = Math.round((Player.realDuration && Player.realDuration())
                              || track.duration || 0);
      if (secs) params.set('duration', secs);
      const data = await cachedApi('/api/lyrics?' + params, 3600000, { timeout: 30000, cacheIf: data => (Array.isArray(data.lines) && data.lines.length > 0) || data.instrumental === true });
      // Пока текст ехал, пользователь мог переключить трек — чужой не рисуем.
      if (id !== this.trackId || token !== this.fetchToken) return;
      this.document = data.document || null; this.precise = !!data.precise;
      this.lines = this.precise ? (data.lines || []) : this.dropPromo(data.lines || []);
      this.lyricSignature = String(data.source||'') + ':' + this.lines.reduce((hash,line)=>{for(const c of String(line.time)+':'+line.text)hash=Math.imul(hash^c.charCodeAt(0),16777619);return hash;},2166136261);
      this.synced = !!data.synced && this.lines.length > 0;
      // Длина записи, с которой сняты метки: по ней шкала растягивается
      // под наш файл (см. rate()).
      this.srcDuration = +data.duration || 0;
      // Сервер предупредил: запись от другой заливки. Сдвиг у таких может
      // быть и в полминуты — ищем его шире.
      this.approx = !!data.approx;
      this.instrumental = !!data.instrumental;
      if (this.lines.length) this.render();
      else this.empty(t('Lyrics not found'));
      this.paintSync();
      if(typeof KaraokeTools!=="undefined") KaraokeTools.loaded(data);
      Disc.reset();
      // Текст мог приехать, когда трек уже играет: сразу встаём на место.
      if (this.synced && Player.audio) this.resync();
    } catch {
      if (id === this.trackId && token === this.fetchToken) {
        this.lines = []; this.synced = false; this.document = null; this.precise = false;
        this.empty(t('Search failed')); this.paintSync(); Disc.reset();
        if (typeof KaraokeTools !== 'undefined') KaraokeTools.resetTrack();
      }
    }
  },

  render() {
    const box = $('lyrics');
    if (!box) return;
    if (!this.lines.length) {
      this.empty('');
      return;
    }
    box.innerHTML = '';
    box.classList.toggle('synced', this.synced);
    this.applyStyle();

    this.lineNodes = [];
    this.lineRows = [];
    this.dotNodes = [];
    this.painted = null;
    this.hint = -1;
    this.dotsOn = -1;
    this.restingOn = -1;
    const frag = document.createDocumentFragment();

    this.lines.forEach((line, i) => {
      const node = el('div', 'lyr-l' + (this.synced ? ' tap' : ''));
      node.dataset.i = i;

      // Точки отсчёта перед вступлением и в проигрышах.
      if (this.synced && line.gap >= 3 && S.karaokeDots !== false) {
        const dots = el('div', 'lyr-dots');
        for (let d = 0; d < 3; d++) dots.appendChild(el('i'));
        node.appendChild(dots);
        this.dotNodes[i] = dots;
      }

      const text = el('div', 'lyr-t');
      const units = []; // Performance view always highlights complete lines.
      const span = el('span', 'lyr-w');
      span.textContent = line.text || '';
      const row = {span,state:-1,units:[],timings:[],paintedWord:-1};
      if(units.length) {
        units.forEach(item=>{
          if(item.before) text.appendChild(document.createTextNode(item.before));
          const part=el('span','lyr-k karaoke-unit',item.text);
          text.appendChild(part);row.units.push({node:part,unit:item.unit});row.timings.push(item.unit);
          if(item.after)text.appendChild(document.createTextNode(item.after));
        });
      } else text.appendChild(span);
      node.appendChild(text);
      this.lineRows[i] = row;
      if(line.translation && typeof LyricsTranslate==='undefined')node.appendChild(el('div','karaoke-translation',String(line.translation)));
      if(line.romanization)node.appendChild(el('div','karaoke-translation',String(line.romanization)));

      if (this.synced) {
        node.setAttribute('role','button'); node.tabIndex=0; node.setAttribute('aria-label',t('Seek')+' '+fmt(line.time)); node.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();this.jump(i);}};
        node.onclick = () => this.jump(i);
      }
      frag.appendChild(node);
      this.lineNodes[i] = node;
    });

    box.appendChild(frag);
    this.bindScroll(box);
    box.scrollTop = 0;
    this.active = -1;
    this.paintLines(-1);
  },

  /* Размер текста и приглушение соседних строк — из настроек. */
  applyStyle() {
    const box = $('lyrics');
    if (!box) return;
    box.classList.remove('size-s', 'size-m', 'size-l');
    box.classList.add('size-' + (S.karaokeSize || 'm'));
    box.classList.toggle('no-dim', S.karaokeDim === false);
    box.classList.toggle('align-c', S.karaokeAlign === 'center');
    box.classList.toggle('lit-accent', S.karaokeLit === 'accent');
    box.classList.toggle('look-apple', S.karaokeLook === 'apple');
    box.classList.toggle('plain', !this.synced);
    box.classList.remove('words');
  },

  jump(index) {
    const line = this.lines[index];
    if (!line || line.time == null || !Player.audio) return;
    // Перемотка идёт по времени звука, а метка строки — по времени текста:
    // поправку вычитаем, иначе клик по строке промахивается.
    const rate = this.precise ? 1 : this.rate();
    const latency = this.precise ? 0 : this.latency() * (Player.audio.playbackRate || 1);
    const at = Math.max(0, (line.time - this.offset() + latency + (this.precise ? 0 : this.HOLD)) / rate);
    this.smoothSeekUntil33 = performance.now() + 1200;
    Player.audio.currentTime = at;
    this.seek(at);
  },

  /* ------------------------------------------------- ручная прокрутка */
  bindScroll(box) {
    if (box.dataset.bound) return;
    box.dataset.bound = '1';
    const detach = () => {
      this.userAt = Date.now();
      if (this.follow) { this.follow = false; this.chip(true); }
    };
    box.addEventListener('wheel', detach, { passive: true });
    box.addEventListener('touchmove', detach, { passive: true });
    box.addEventListener('pointerdown', event => {
      if (event.pointerType !== 'mouse' || event.buttons === 1) detach();
    });
  },

  chip(show) {
    let node = $('lyrFollow');
    if (!node) {
      node = el('button', 'lyr-follow', t('Back to the line'));
      node.id = 'lyrFollow';
      node.onclick = () => {
        this.follow = true;
        this.chip(false);
        this.center(true);
      };
      const host = $('nowBody') || $('lyrics');
      if (host) host.appendChild(node);
    }
    node.textContent = t('Back to the line');
    node.classList.toggle('on', !!show && this.synced);
  },

  /* ------------------------------------------------------ прокрутка */
  center(now = false) {
    const box = $('lyrics');
    const node = this.lineNodes[this.active];
    if (!box || !node) return;
    // offsetTop can be relative to nowBody rather than the scrolling lyrics box.
    // Measure in the scroll container's coordinate system (also after responsive reflow).
    const rect = box.getBoundingClientRect();
    const zoom = box.offsetHeight ? rect.height / box.offsetHeight : 1;
    const relativeTop = (node.getBoundingClientRect().top - rect.top) / (zoom || 1) + box.scrollTop;
    this.scrollTo = Math.max(0, relativeTop
      - box.clientHeight * this.ANCHOR + node.clientHeight / 2);
    if (now || S.noAnim) {
      box.scrollTop = this.scrollTo;
      this.scrollTo = null;
      return;
    }
    this.glide();
  },

  /* Плавное «догоняющее» движение вместо scrollTo({behavior:'smooth'}):
     тот дёргается, если цель меняется несколько раз подряд. */
  glide() {
    if (this.glideRaf) return;
    let previous = 0, lastPosition = null, lastTarget = null;
    const step = stamp => {
      const box = $('lyrics');
      if (!box || this.scrollTo == null || !this.follow || document.hidden || !$('now')?.classList.contains('on')) {
        this.glideRaf = null; return;
      }
      const target = Math.max(0, Math.min(this.scrollTo, box.scrollHeight - box.clientHeight));
      const position = box.scrollTop, diff = target - position;
      if (Math.abs(diff) < 1.5 || (position === lastPosition && target === lastTarget) || S.noAnim || matchMedia('(prefers-reduced-motion: reduce)').matches) {
        box.scrollTop = target; this.scrollTo = null; this.glideRaf = null; return;
      }
      const dt = previous ? Math.min(64, stamp - previous) : 1000 / 60;
      previous = stamp; lastPosition = position; lastTarget = target;
      box.scrollTop = position + diff * (1 - Math.exp(-dt / 95));
      this.glideRaf = requestAnimationFrame(step);
    };
    this.glideRaf = requestAnimationFrame(step);
  },

  /* ------------------------------------------------------- подсветка */
  /* Строка по времени. Обычный кадр сдвигает индекс максимум на единицу,
     поэтому сначала проверяем подсказку и только потом идём двоичным
     поиском — это важно после перемотки и на длинных текстах. */
  indexAt(time) {
    const lines = this.lines;
    const n = lines.length;
    if (!n) return -1;
    const at = i => +lines[i].time || 0;
    const fits = i => (i < 0 || at(i) <= time) && (i + 1 >= n || at(i + 1) > time);

    const hint = this.hint;
    if (hint >= -1 && hint < n) {
      if (fits(hint)) return hint;
      if (hint + 1 < n && fits(hint + 1)) { this.hint = hint + 1; return hint + 1; }
      if (hint - 1 >= -1 && fits(hint - 1)) { this.hint = hint - 1; return hint - 1; }
    }
    let lo = 0, hi = n - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (at(mid) <= time) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    this.hint = found;
    return found;
  },

  /* Перерисовываем только те строки, у которых состояние действительно
     изменилось: соседей старой и новой активной плюс всё, что между ними.
     Раньше цикл шёл по всему тексту на каждой строке — на длинных песнях
     это давало заметные подтормаживания. */
  paintLines(active) {
    const n = this.lineNodes.length;
    if (!n) { this.painted = active; return; }
    const prev = this.painted;
    let from = 0, to = n - 1;
    if (prev != null) {
      // За пределами ±7 строк меняются только классы done/next, а их
      // перекрывает диапазон между старой и новой позицией.
      from = Math.max(0, Math.min(prev, active) - 7);
      to = Math.min(n - 1, Math.max(prev, active) + 7);
    }
    for (let i = from; i <= to; i++) this.paintLine(i, active);
    this.painted = active;
  },

  paintLine(i, active) {
    const node = this.lineNodes[i];
    if (!node) return;
    const distance = Math.min(6, Math.abs(i - active));
    const state = i === active ? 1 : i < active ? 2 : i === active + 1 ? 3 : 0;
    const sig = distance + ':' + state;
    if (node.__sig === sig && this.painted != null) return;
    node.__sig = sig;
    node.style.setProperty('--d', String(distance));
    node.classList.toggle('on', state === 1);
    node.classList.toggle('done', state === 2);
    node.classList.toggle('next', state === 3);
    node.classList.remove('rest'); // seek/resync may reactivate a resting line
    // Активная и уже спетые строки подсвечиваются целиком.
    this.fillRow(i, state);
  },

  /* Состояние строки: 1 — поётся, 2 — спета, остальное — ещё впереди.
     Строка зажигается целиком: ни заливки по словам, ни по буквам. */
  fillRow(i, state) {
    const row = this.lineRows[i];
    if (!row || row.state === state) return;
    row.state = state;
    if(row.units.length) {
      if(state!==1)row.units.forEach(u=>KaraokeTiming.paint(u.node,state===2?1:0));
      row.paintedWord=-1;
    } else row.span.classList.toggle('lit', state === 1 || state === 2);
  },

  paintWords(index,time,instant=false) {
    const row=this.lineRows[index];
    if(!row || !row.units.length)return;
    const units=row.units;
    const current=KaraokeTiming.index(row.timings,time);
    // Update only the traversed units and the current unit. Seeking can reset
    // the active row; normal frames mutate one CSS property, no full render.
    const from=instant?0:Math.max(0,Math.min(row.paintedWord,current));
    const to=instant?units.length-1:Math.min(units.length-1,Math.max(row.paintedWord,current));
    for(let i=from;i<=to;i++)KaraokeTiming.paint(units[i].node,KaraokeTiming.progress(time,units[i].unit));
    row.paintedWord=current;
  },

  /* Точки отсчёта: заполняются по ходу паузы перед строкой.
     Трогаем только одну группу точек, а не весь список. */
  paintDots(next, time) {
    if (this.dotsOn >= 0 && this.dotsOn !== next) {
      const old = this.dotNodes[this.dotsOn];
      if (old) old.classList.remove('on');
      this.dotsOn = -1;
    }
    const dots = this.dotNodes[next];
    const line = this.lines[next];
    if (!dots || !line || !line.gap) return;
    const start = line.time - line.gap;
    const on = time >= start - 0.1 && time < line.time;
    if (on !== (this.dotsOn === next)) {
      dots.classList.toggle('on', on);
      this.dotsOn = on ? next : -1;
    }
    if (!on) return;
    const span = Math.max(0.5, line.gap);
    let done = (time - start) / span;
    if (done < 0) done = 0; else if (done > 1) done = 1;
    for (let d = 0; d < dots.children.length; d++) {
      let value = done * 3 - d;
      if (value < 0) value = 0; else if (value > 1) value = 1;
      value = Math.round(value * 50) / 50;
      const dot = dots.children[d];
      if (dot.__p === value) continue;
      dot.__p = value;
      dot.style.setProperty('--p', value.toFixed(2));
    }
  },

  /* Единственная точка входа. Player.tick() зовёт её каждый кадр и передаёт
     сырое audio.currentTime; instant = true после перемотки и смены поправки. */
  onTime(raw, instant = false) {
    // Слушаем звук в любом режиме: подгонка нужна и «Диску», и караоке.
    if (!instant) this.autoSample(raw);
    if (Disc.on) { Disc.onTime(raw, instant); return; }   // режим «Диск» ведёт сам
    if (Viz.on) { Viz.onTime(); return; }                  // «Визуализатор» тоже
    if (!this.synced || !this.lines.length) return;
    if (!(raw >= 0)) return;
    // Одна шкала на всё: строки, слова и точки не могут разойтись.
    const time = this.clock(raw);
    // Кадр без движения (пауза, тот же currentTime) не трогает DOM вовсе.
    if (!instant && this.lastTime === time) return;
    this.lastTime = time;

    const index = this.indexAt(time);
    if (index !== this.active || this.painted === null) {
      this.active = index;
      this.paintLines(index);
      if (this.follow && index >= 0) this.center(instant);
    } else if (instant && this.follow && index >= 0) {
      this.center(true);
    }
    // Line timestamps share the media clock; playback speed is already reflected in currentTime.
    if (this.dotNodes.length) this.paintDots(index + 1, time);

    // Строка допета, а следующая ещё не началась: приглушаем её, чтобы в
    // проигрыше на экране не «горел» уже спетый куплет.
    const line = this.lines[index];
    const resting = !!(line && line.end && time > line.end + 0.35);
    const restingOn = resting ? index : -1;
    if (restingOn !== this.restingOn) {
      const old = this.lineNodes[this.restingOn];
      if (old) old.classList.remove('rest');
      const node = this.lineNodes[restingOn];
      if (node) node.classList.add('rest');
      this.restingOn = restingOn;
    }

    // Подсветку вернули пользователю — через паузу снова ведём сами.
    if (!this.follow && Date.now() - this.userAt > this.FOLLOW_BACK) {
      this.follow = true;
      this.chip(false);
      this.center();
    }
  },
};
