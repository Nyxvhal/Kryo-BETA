/* disc.js — режим караоке «Диск».
   Чёрная сцена, обложка крутится как CD в прозрачной коробке, а слова
   появляются по одному слева от неё — как в вертикальных лирик-видео.

   Время берётся из той же шкалы, что и обычное караоке
   (currentTime + поправка − HOLD), поэтому поправки синхронизации общие.
   За кадр меняется максимум одно слово: никаких innerHTML в цикле. */
'use strict';

const Disc = {
  on: false,
  root: null, words: null, disc: null, art: null, meta: null,
  line: -2,          // какая строка сейчас на экране (−2 — ничего не строили)
  shown: 0,          // сколько слов этой строки уже показано
  pageFrom: 0,       // с какого слова начата текущая «страница»
  lastTime: null,
  MAX_ROWS: 4,       // больше строк в блоке не помещаем — листаем страницу
  LINGER: 1.6,
  // Слово «выскакивает», а не заливается: такому стилю нужна меньшая
  // выдержка, чем строке. Проверено на трёх треках: голос встаёт на метку
  // строки в среднем ±0.1 с, 0.08 с запаса не даёт словам обгонять голос.
  HOLD: 0.25,       // выдержка слова: метки в базах стоят раньше голоса

  build() {
    if (this.root) return;
    const now = $('now');
    if (!now) return;
    const root = el('div', 'disc-stage');
    root.id = 'discStage';
    root.innerHTML =
      '<i class="disc-vignette"></i>' +
      '<div class="disc-text"><div class="disc-words" id="discWords"></div></div>' +
      '<div class="disc-case">' +
        '<i class="disc-glow" id="discGlow"></i>' +
        '<div class="disc-tray"></div>' +
        '<div class="disc-slot" id="discSlot"><div class="disc-cd blank" id="discCd">' +
          '<img id="discArt" alt="" draggable="false"><span class="disc-label" id="discLabel"></span>' +
          '<i class="disc-ring"></i><i class="disc-hub"></i><i class="disc-hole"></i></div></div>' +
        '<div class="disc-lid"></div><i class="disc-hinge"></i>' +
        '<i class="disc-reflect"></i>' +
      '</div>' +
      '<div class="disc-meta" id="discMeta"></div>' +
      // Перемотка прямо на сцене: раньше в режиме «Диск» трек можно было
      // только слушать с начала — шкалы здесь не было вообще.
      '<div class="bar disc-bar">' +
        '<span class="tm" id="dCur">0:00</span>' +
        '<div class="track" id="dTrack">' +
          '<div class="rail"></div><div class="buf" id="dBuf"></div>' +
          '<div class="fill" id="dFill"></div><div class="knob"></div>' +
        '</div>' +
        '<span class="tm" id="dDur">0:00</span>' +
      '</div>' +
      // Зерно: шум выбивает отдельные пиксели букв — края становятся «живыми».
      '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><filter id="discGrain" x="0" y="0" width="100%" height="100%">' +
        '<feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="1" seed="7" result="n"/>' +
        '<feColorMatrix in="n" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 -1.6 1.9" result="m"/>' +
        '<feComposite in="SourceGraphic" in2="m" operator="in"/></filter></svg>' +
      // Кнопки сцены: одинаковые круглые площадки, иконки по центру и
      // ровно одного размера. Раньше это были обычные .ib из общего
      // интерфейса — на чёрной сцене они выглядели разнокалиберными, а
      // «Tap» вообще был буквой T в кружке.
      '<div class="disc-ctl">' +
        '<button class="disc-b" data-a="like" title="' + esc(t('Like')) + '">' +
          '<svg class="ic"><use href="#i-heart"/></svg></button>' +
        '<button class="disc-b" data-a="prev" title="' + esc(t('Previous')) + '">' +
          '<svg class="ic f"><use href="#i-prev"/></svg></button>' +
        '<button class="disc-b disc-play" data-a="play" title="' + esc(t('Play')) + '">' +
          '<svg class="ic f"><use href="#i-play"/></svg></button>' +
        '<button class="disc-b" data-a="next" title="' + esc(t('Next')) + '">' +
          '<svg class="ic f"><use href="#i-next"/></svg></button>' +
        // Вместо «подгонки текста» здесь теперь микшер: громкость, баланс,
        // плавный переход и эквалайзер. Подстройка текста осталась на
        // клавише T и в настройках караоке.
        '<button class="disc-b" data-a="mix" title="' + esc(t('Mixer')) + ' (M)">' +
          '<svg class="ic"><use href="#i-mixer"/></svg></button>' +
        '<button class="disc-b" data-a="close" title="' + esc(t('Close')) + '">' +
          '<svg class="ic"><use href="#i-down"/></svg></button>' +
      '</div>';
    const top = $('nowTop');
    if (top) top.after(root); else now.appendChild(root);
    this.root = root;
    // Шрифт грузим заранее: иначе первые слова мерились бы по запасному.
    if (document.fonts) {
      document.fonts.load("300 40px 'Kry Disc'").then(() => { this.lh = 0; });
      document.fonts.load("italic 300 40px 'Kry Disc'");
    }
    this.words = $('discWords');
    this.disc = $('discCd');
    this.slot = $('discSlot');
    this.art = $('discArt');
    this.meta = $('discMeta');
    Player.bindSeek($('dTrack'));
    Player.paintTime();
    root.querySelector('.disc-ctl').onclick = event => {
      const btn = event.target.closest('button');
      if (!btn) return;
      const a = btn.dataset.a;
      if (a === 'play') Player.toggle();
      else if (a === 'prev') Player.prev();
      else if (a === 'next') Player.next(false);
      else if (a === 'mix') Mixer.open();
      // toggleLike асинхронный: paintButtons() сразу после вызова рисовал
      // ещё старое состояние, и сердце «залипало» до следующего клика.
      else if (a === 'like') {
        if (Player.current) {
          btn.disabled = true;
          Promise.resolve(toggleLike(Player.current))
            .catch(() => {})
            .then(() => { btn.disabled = false; this.paintButtons(); });
        }
        return;
      }
      else if (a === 'close') $('now').classList.remove('on');
      this.paintButtons();
    };
    // Курсор неподвижен 2.5 с — кнопки и курсор прячутся, остаётся сцена.
    let idle = null;
    const wake = () => {
      root.classList.add('awake');
      clearTimeout(idle);
      idle = setTimeout(() => root.classList.remove('awake'), 2500);
    };
    root.addEventListener('pointermove', wake, { passive: true });
    root.addEventListener('pointerdown', wake, { passive: true });
    if (Player.current) this.setArt(KCustom.cover(Player.current.thumbnail));
    this.paintMeta();
    this.apply();
    this.paintButtons();
  },

  setMode(on) {
    this.on = !!on;
    if (this.on) { this.build(); this.apply(); }
    this.reset();
    this.setPlaying(Player.audio && !Player.audio.paused);
  },


  /* ------------------------------------------------------ настройки сцены
     Всё, что крутится в настройках режима «Диск», применяется здесь и
     только здесь: несколько классов на сцене и пара CSS-переменных. Текст
     при этом не перестраивается, поэтому смена вида не сбивает тайминг. */
  apply() {
    const root = this.root;
    if (!root) return;
    const num = (value, fallback) => {
      const got = +value;
      return isFinite(got) && got > 0 ? got : fallback;
    };
    root.style.setProperty('--disc-zoom', (num(S.discSize, 100) / 100).toFixed(3));
    root.style.setProperty('--disc-text-zoom', (num(S.discTextSize, 100) / 100).toFixed(3));
    root.style.setProperty('--disc-spin', num(S.discSpinSpeed, 8).toFixed(1) + 's');
    root.classList.remove('lay-side', 'lay-under', 'lay-over');
    root.classList.add('lay-' + (S.discLayout || 'side'));
    root.classList.remove('skin-jewel', 'skin-bare', 'skin-vinyl');
    root.classList.add('skin-' + (S.discCaseSkin || 'jewel'));
    root.classList.toggle('grain', S.discGrain !== false);
    // Свечение: цветное из обложки, белое «как в клипе» или выключено.
    // Старый переключатель discGlow оставлен для совместимости настроек:
    // выключенный он по-прежнему означает «без свечения».
    const glow = S.discGlow === false ? 'off' : (S.discGlowStyle || 'cover');
    root.classList.remove('glow', 'glow-cover', 'glow-white');
    if (glow !== 'off') root.classList.add('glow', 'glow-' + glow);
    root.classList.toggle('pulse', S.discPulse !== false);
    root.classList.toggle('bloom', S.discBloom !== false);
    root.classList.toggle('reflect', !!S.discReflect);
    root.classList.toggle('italic', S.discItalic !== false);
    root.classList.toggle('vignette', S.discVignette !== false);
    root.classList.toggle('no-meta', S.discMeta === false);
    root.classList.toggle('soft', S.discFade !== false);
    root.classList.toggle('big-ctl', !!S.discBigButtons);
    this.MAX_ROWS = Math.max(1, Math.min(8, +S.discLines || 4));
    this.lh = 0;                       // высота строки изменилась — пересчитать
    this.paintGlow();
    this.reset();
  },

  /* Свечение за коробкой красится в цвета обложки: сцена перестаёт быть
     плоским чёрным прямоугольником, но остаётся спокойной. */
  paintGlow() {
    const node = $('discGlow');
    if (!node) return;
    // «Выключено» — значит выключено: раньше фон элемента всё равно
    // перекрашивался, и на некоторых темах сквозь него пробивался ореол.
    if (!this.root || !this.root.classList.contains('glow')) {
      node.style.background = 'none';
      return;
    }
    // «Белое» свечение — тот самый bloom из клипа: контур коробки светится
    // ровным белым светом, а цвет обложки в него не вмешивается.
    if (this.root && this.root.classList.contains('glow-white')) {
      node.style.background =
        'radial-gradient(circle at 50% 50%, rgba(255,255,255,.62) 0%, '
        + 'rgba(255,255,255,.26) 38%, transparent 68%)';
      return;
    }
    const colors = (Karaoke.palette && Karaoke.palette.length)
      ? Karaoke.palette : [S.accent, S.accent2];
    node.style.background =
      'radial-gradient(circle at 50% 50%, ' +
      Karaoke.alpha(colors[0], 0.55) + ' 0%, ' +
      Karaoke.alpha(colors[1] || colors[0], 0.24) + ' 46%, transparent 72%)';
  },

  /* Состояние кнопок сцены: «нравится» горит, как в остальном интерфейсе. */
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

  /* ------------------------------------------------ обложка на диске
     Каждый трек «печатается» на диск: старый диск выезжает из коробки,
     новый с обложкой трека въезжает на его место и продолжает крутиться. */
  artUrl: null,
  artOk: false,
  artToken: 0,

  /* Самая крупная версия обложки: на диске она занимает пол-экрана, и
     каждая лишняя сотня пикселей там видна. Варианты считает core.js —
     он же знает, чем заменить ссылку, если крупной версии нет. */
  bigArt(url) {
    if (!url) return '';
    return this.artChain(url)[0] || String(url);
  },

  artChain(url) {
    const list = coverVariants(url, S.coverQuality === 'normal' ? 600 : 1200);
    // Запас на случай, когда ссылки на обложку нет совсем или все её
    // варианты отдают 404: у треков YouTube картинку всегда можно собрать
    // из идентификатора. Раньше в этом месте оставался белый диск с одним
    // названием.
    const id = String((Player.current && Player.current.id) || '');
    if (id.startsWith('yt:') && id.length > 3) {
      const code = id.slice(3);
      ['hqdefault', 'mqdefault'].forEach(name => {
        const guess = `https://i.ytimg.com/vi/${code}/${name}.jpg`;
        if (!list.includes(guess)) list.push(guess);
      });
    }
    // pywebview на Windows иногда отказывается тянуть картинки с CDN
    // YouTube напрямую — тогда вся цепочка падала и на сцене оставался
    // белый квадрат. Подстраховываемся локальным прокси, как setImg().
    const out = [];
    list.forEach(url => {
      if (!out.includes(url)) out.push(url);
      let host = '';
      try { host = new URL(url, location.href).hostname.toLowerCase(); } catch (_) { return; }
      if (/(^|\.)((ytimg|ggpht|googleusercontent)\.com)$/.test(host)) {
        const via = '/api/image/youtube?url=' + encodeURIComponent(url);
        if (!out.includes(via)) out.push(via);
      }
    });
    return out;
  },

  setArt(url) {
    if (!this.art) return;
    this.paintMeta();
    const big = this.bigArt(url);
    // Повтор пропускаем только если обложка тогда действительно загрузилась:
    // после неудачной попытки тот же трек должен получить второй шанс,
    // иначе белый квадрат оставался до смены трека.
    if (big === this.artUrl && this.artOk) return;
    this.artUrl = big;
    this.artOk = false;
    const token = ++this.artToken;
    const load = src => new Promise(done => {
      if (!src) { done(null); return; }
      const img = new Image();
      img.decoding = 'async';
      img.onload = () => done(img);
      img.onerror = () => done(null);
      img.src = src;
    });
    // Крупной версии может не быть — спокойно спускаемся по списку запасных.
    const chain = this.artChain(url);
    const tryAt = index => index >= chain.length
      ? Promise.resolve(null)
      : load(chain[index]).then(img => img || tryAt(index + 1));
    tryAt(0).then(img => {
      if (token !== this.artToken) return;          // трек успели сменить ещё раз
      this.artOk = !!img;
      this.swap(img);
      this.paintGlow();
    });
  },

  /* Подгоняем картинку под круг. У YouTube превью 4:3 с чёрными полосами
     сверху и снизу — увеличиваем, чтобы полосы не попали на диск. */
  fit(node, img) {
    const ratio = img ? img.naturalWidth / img.naturalHeight : 1;
    let zoom = 1;
    if (img && /ytimg\.com/.test(img.src) && Math.abs(ratio - 4 / 3) < 0.05) zoom = 4 / 3 * 1.02;
    node.style.transform = zoom > 1 ? `scale(${zoom.toFixed(3)})` : '';
  },

  swap(img) {
    const cd = this.disc;
    const apply = () => {
      if (img) {
        this.art.src = img.src;
        this.fit(this.art, img);
        cd.classList.remove('blank');
      } else {
        this.art.removeAttribute('src');
        cd.classList.add('blank');                  // без обложки — чистый белый диск
      }
      const label = $('discLabel');
      if (label) label.textContent = img ? '' : (Player.current ? Player.current.title || '' : '');
    };
    const slot = this.slot;
    // Первый показ или «меньше анимаций» — просто меняем картинку.
    if (!slot || !this.on || S.noAnim || !this.hadArt) {
      apply();
      this.hadArt = true;
      return;
    }
    slot.classList.remove('in');
    slot.classList.add('out');
    clearTimeout(this.swapTimer);
    this.swapTimer = setTimeout(() => {
      apply();
      slot.classList.remove('out');
      void slot.offsetWidth;                       // перезапуск анимации въезда
      slot.classList.add('in');
    }, 380);
  },

  paintMeta() {
    this.paintButtons();
    if (!this.meta) return;
    const track = Player.current;
    this.meta.innerHTML = track
      ? `<b>${esc(track.title || '')}</b><span>${esc(track.artist || '')}</span>` : '';
  },

  setPlaying(playing) {
    if (!this.root) return;
    this.root.classList.toggle('spin', !!playing && !S.noAnim);
    const use = this.root.querySelector('.disc-play use');
    if (use) use.setAttribute('href', playing ? '#i-pause' : '#i-play');
  },

  /* Новый текст или перемотка: всё строим заново с текущего места. */
  reset() {
    this.line = -2;
    this.shown = 0;
    this.pageFrom = 0;
    this.lastTime = null;
    if (this.words) {
      this.words.textContent = '';
      this.words.classList.remove('gone');
    }
    this.paintMeta();
    if (this.on && Player.audio) this.onTime(Player.audio.currentTime, true);
  },

  wordsOf(line) {
    return [{ time: line.time, end: line.end, text: line.text }];
  },

  /* Выдержка слова. Метки в базах текстов стоят на волосок раньше голоса,
     но слову нужна меньшая выдержка, чем целой строке: оно «выскакивает»,
     и опоздание заметнее опережения. */
  hold() {
    const own = +S.discHold;
    return isFinite(own) ? Math.max(0, Math.min(1.2, own)) : this.HOLD;
  },

  /* Пульс сцены по звуку.

     В клипе свет и яркость коробки «дышат» в такт басу, поэтому значения
     берём из того же анализатора, что рисует фон караоке, и отдаём в CSS
     двумя переменными: --energy (общая громкость) и --beat (удар).
     Переменные пишем только при заметном изменении: style.setProperty на
     каждый кадр заставлял браузер пересчитывать всю сцену без нужды. */
  pulse() {
    const root = this.root;
    if (!root || !root.classList.contains('pulse')) {
      if (root && this._energy) { this._energy = this._beat = 0;
        root.style.setProperty('--energy', '0');
        root.style.setProperty('--beat', '0'); }
      return;
    }
    const got = Karaoke.level();
    const level = Math.min(1, (got.bass != null ? got.bass : got.energy) * 1.25);
    // Сглаживание: без него яркость дёргается на каждом кадре и рябит.
    this._energy = this._energy == null ? level : this._energy * 0.76 + level * 0.24;
    const beat = Math.max(0, Math.min(1, Karaoke.beat || 0));
    this._beat = this._beat == null ? beat : Math.max(beat, this._beat * 0.82);
    if (Math.abs((this._energyCss || 0) - this._energy) > 0.012) {
      this._energyCss = this._energy;
      root.style.setProperty('--energy', this._energy.toFixed(3));
    }
    if (Math.abs((this._beatCss || 0) - this._beat) > 0.012) {
      this._beatCss = this._beat;
      root.style.setProperty('--beat', this._beat.toFixed(3));
    }
  },

  /* Зовётся из Karaoke.onTime каждый кадр. */
  onTime(raw, force = false) {
    if (!this.on || !this.words || !(raw >= 0)) return;
    this.pulse();
    const K = Karaoke;
    if (!K.synced || !K.lines.length) {
      // Меток времени нет — сцена просто остаётся пустой. Раньше здесь
      // появлялась надпись «текста нет» или название трека, и она висела
      // весь трек, хотя сообщать об этом нечего.
      if (this.line !== -3) {
        this.line = -3;
        this.words.textContent = '';
      }
      return;
    }
    // Та же шкала, что в обычном караоке, плюс своя выдержка и личная
    // поправка слов из настроек (минус — слова выходят раньше).
    // Берём шкалу без выдержки строки (K.base) и вычитаем свою выдержку
    // слова: раньше здесь стоял K.clock, в котором выдержка уже вычтена, —
    // она складывалась со своей, и слова опаздывали на ~0.4 с.
    const time = K.clock(raw) - (+S.discLead || 0);
    if (!force && this.lastTime === time) return;
    this.lastTime = time;

    const index = K.indexAt(time);
    if (index !== this.line) {
      this.line = index;
      this.shown = 0;
      this.pageFrom = 0;
      this.words.textContent = '';
      this.words.classList.remove('gone');
    }
    const line = K.lines[index];
    if (!line) return;

    // Проигрыш: допетая строка гаснет, экран остаётся чистым, как в клипе.
    const linger = isFinite(+S.discLinger) && +S.discLinger >= 0
      ? +S.discLinger : this.LINGER;
    const gone = !!(line.end && time > line.end + linger);
    if (gone !== this.words.classList.contains('gone')) {
      this.words.classList.toggle('gone', gone);
    }

    const words = this.wordsOf(line);
    let target = 0;
    while (target < words.length && (+words[target].time || 0) <= time) target++;
    // «Строкой целиком» — как в клипах, где текст появляется куплетом.
    if (target > 0) target = words.length;
    if (target < this.shown) {           // назад внутри строки — перестроить
      this.shown = 0; this.pageFrom = 0; this.words.textContent = '';
    }
    while (this.shown < target) {
      const word = words[this.shown];
      const span = el('span', 'disc-w');
      span.__unit = word;
      span.textContent = String(word.text || '').trim() + (/^[\u3040-\u30ff\u3400-\u9fff]/.test(word.text||'') && !line.text.includes(' ') ? '' : ' ');
      this.words.appendChild(span);
      if (this.words.childNodes.length === 1) span.classList.add('first');
      // Блок вылез за 4 строки — начинаем новую «страницу» с этого слова.
      if (this.overflow() && this.words.childNodes.length > 1) {
        this.words.textContent = '';
        this.words.appendChild(span);
        span.classList.add('first');
        this.pageFrom = this.shown;
      }
      this.shown++;
    }

  },

  overflow() {
    const box = this.words;
    if (!this.lh || this.lhW !== innerWidth + 'x' + innerHeight) {   // пересчёт только при ресайзе
      this.lh = parseFloat(getComputedStyle(box).lineHeight) || 40;
      this.lhW = innerWidth + 'x' + innerHeight;
    }
    const lh = this.lh;
    return box.scrollHeight > lh * this.MAX_ROWS + 2;
  },
};
