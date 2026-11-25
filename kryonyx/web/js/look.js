/* look.js — внешний вид плеера: обои и тонкая настройка интерфейса.

   Две независимые вещи, но живут в одной вкладке настроек «Вид», поэтому
   лежат рядом.

   Обои. Картинка кладётся отдельным слоем под интерфейс (#wall), а не в
   background самого body: так её можно двигать, размывать и гасить, не
   задевая живой фон темы. Источников четыре: встроенные узоры (рисуются
   SVG из цветов текущей темы, поэтому ничего не весят), файл с диска,
   ссылка и обложка играющего трека.

   Файл с диска не уезжает в базу настроек: картинка на 4 мегабайта в
   каждом PUT /api/settings — это гарантированные тормоза. Поэтому файл
   уменьшается до 3840 px, пережимается в JPEG и лежит в localStorage, а
   в настройках остаётся только отметка 'local'. */
'use strict';

const WALL_PRESETS = [
  ['p:grid', 'Grid'], ['p:dots', 'Dots'], ['p:waves', 'Waves'],
  ['p:blobs', 'Blobs'], ['p:rays', 'Rays'], ['p:tiles', 'Tiles'],
];
const WALL_KEY = 'kryonyx.wall';

const Wall = {
  // All source changes share one generation: a late URL/file must never undo
  // a newer preset, clear action, or file selection.
  beginChange36() {
    const ticket = this.changeTicket36 = (this.changeTicket36 || 0) + 1;
    $('wallUrl')?.removeAttribute('aria-busy');
    return ticket;
  },

  select(source) {
    this.beginChange36();
    S.wallSrc = source;
    this.apply(); saveSettings(); this.build();
  },
  /* Встроенный узор рисуется цветами активной темы: обои не спорят с ней. */
  preset(id) {
    const a = encodeURIComponent(S.accent);
    const b = encodeURIComponent(S.accent2);
    /* Узор намеренно рисуется без залитой подложки: он ложится поверх фона
       темы, и ползунок «сила» управляет именно рисунком, а не прямоугольником
       цвета фона. С подложкой любой узор выглядел просто тёмным пятном. */
    const svg = {
      grid: `<svg xmlns='http://www.w3.org/2000/svg' width='80' height='80'>` +
            `<g stroke='${a}' stroke-width='1.4'><path d='M0 .7H80M.7 0V80'/></g></svg>`,
      dots: `<svg xmlns='http://www.w3.org/2000/svg' width='44' height='44'>` +
            `<circle cx='6' cy='6' r='2.6' fill='${a}'/></svg>`,
      waves: `<svg xmlns='http://www.w3.org/2000/svg' width='160' height='60'>` +
             `<g fill='none' stroke='${a}' stroke-width='2.8'>` +
             `<path d='M0 20c20-16 40 16 60 0s40 16 60 0 40 16 60 0'/></g>` +
             `<g fill='none' stroke='${b}' stroke-width='2.8'>` +
             `<path d='M0 46c20-16 40 16 60 0s40 16 60 0 40 16 60 0'/></g></svg>`,
      blobs: `<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='800'>` +
             `<circle cx='220' cy='180' r='320' fill='${a}'/>` +
             `<circle cx='980' cy='140' r='270' fill='${b}'/>` +
             `<circle cx='760' cy='700' r='350' fill='${a}'/>` +
             `<circle cx='120' cy='640' r='220' fill='${b}'/></svg>`,
      rays: `<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'>` +
            `<g stroke='${a}' stroke-width='12'>` +
            `<path d='M-20 140L140 -20M20 180L180 20M-60 100L100 -60'/></g></svg>`,
      tiles: `<svg xmlns='http://www.w3.org/2000/svg' width='96' height='96'>` +
             `<g fill='none' stroke='${a}' stroke-width='2.4'>` +
             `<rect x='8' y='8' width='34' height='34' rx='8'/></g>` +
             `<g fill='none' stroke='${b}' stroke-width='2.4'>` +
             `<rect x='54' y='54' width='34' height='34' rx='8'/></g></svg>`,
    }[id];
    return svg ? `url("data:image/svg+xml;utf8,${svg.replace(/#/g, '%23')}")` : '';
  },

  /* Адрес картинки для текущего источника. */
  src() {
    const v = S.wallSrc || '';
    if (!v) return '';
    if (v.startsWith('p:')) return this.preset(v.slice(2));
    if (v === 'local') {
      let data = '';
      try { data = localStorage.getItem(WALL_KEY) || ''; } catch {}
      return data ? `url("${data}")` : '';
    }
    if (v === 'cover') {
      const art = (typeof Player !== 'undefined' && Player.current
                   && Player.current.thumbnail) || '';
      return art ? `url("${art}")` : '';
    }
    return `url("${v.replace(/"/g, '%22')}")`;
  },

  apply() {
    const root = document.documentElement.style;
    const img = this.src();
    const scope = S.wallScope || 'both';
    root.setProperty('--wall-img', img || 'none');
    root.setProperty('--wall-op', ((+S.wallOpacity || 0) / 100).toFixed(2));
    root.setProperty('--wall-blur', (+S.wallBlur || 0) + 'px');
    // Затемнение обоев берёт цвет из темы: на светлой бумаге чёрная пелена
    // выглядит грязью, нужна белая.
    const light = document.body.classList.contains('light');
    const dim = Math.max(0, Math.min(90, +S.wallDim || 0)) / 100;
    root.setProperty('--wall-scrim',
      `rgba(${light ? '255, 255, 255' : '0, 0, 0'}, ${dim.toFixed(2)})`);
    const mode = S.wallMode || 'cover';
    root.setProperty('--wall-size',
      mode === 'contain' ? 'contain' : mode === 'tile' ? 'auto' : mode === 'center' ? 'auto' : 'cover');
    root.setProperty('--wall-repeat', mode === 'tile' ? 'repeat' : 'no-repeat');
    document.body.classList.toggle('wall', !!img && scope !== 'player');
    document.body.classList.toggle('wall-now', !!img && scope !== 'app');
  },

  /* Обложка сменилась — обои «по обложке» должны поехать за ней. */
  onTrack() { if (S.wallSrc === 'cover') this.apply(); },

  /* Файл с диска: уменьшаем и пережимаем, иначе обои весят как альбом. */
  async pickFile(file) {
    if (!file) return;
    const ticket = this.beginChange36();
    if (file.size > 20 * 1024 * 1024) { toast(t('The image is too large for this browser')); return; }
    if (file.type && !/^image\//i.test(file.type)) { toast(t('Could not load wallpaper')); return; }
    try {
      const data = await new Promise((done, fail) => {
        const fr = new FileReader();
        fr.onload = () => done(fr.result);
        fr.onerror = () => fail(new Error('Image read failed'));
        fr.onabort = () => fail(new Error('Image read cancelled'));
        fr.readAsDataURL(file);
      });
      if (ticket !== this.changeTicket36) return;
      const small = await this.shrink(data);
      if (ticket !== this.changeTicket36) return;
      try { localStorage.setItem(WALL_KEY, small); }
      catch { toast(t('The image is too large for this browser')); return; }
      S.wallSrc = 'local';
      this.apply(); saveSettings(); this.build();
      toast(t('Wallpaper set'));
    } catch {
      if (ticket === this.changeTicket36) toast(t('Could not load wallpaper'));
    }
  },

  shrink(data) {
    return new Promise((done, fail) => {
      const img = new Image();
      img.onload = () => {
        try {
          const width = img.naturalWidth || img.width, height = img.naturalHeight || img.height;
          if (!width || !height || width * height > 40000000) throw new Error('Invalid image dimensions');
          const max = 3840;
          const k = Math.min(1, max / Math.max(width, height));
          if (k >= 1 && data.length < 900000) return done(data);
          const c = document.createElement('canvas');
          c.width = Math.max(1, Math.round(width * k));
          c.height = Math.max(1, Math.round(height * k));
          const ctx = c.getContext('2d');
          if (!ctx) throw new Error('Canvas unavailable');
          ctx.drawImage(img, 0, 0, c.width, c.height);
          const encoded = c.toDataURL('image/jpeg', 0.93);
          if (!encoded.startsWith('data:image/')) throw new Error('Image encoding failed');
          done(encoded);
        } catch (error) { fail(error); }
      };
      img.onerror = fail;
      img.src = data;
    });
  },

  clear() {
    this.beginChange36();
    S.wallSrc = '';
    try { localStorage.removeItem(WALL_KEY); } catch {}
    this.apply(); saveSettings(); this.build();
  },

  build() {
    const box = $('wallPresets');
    if (box) {
      box.innerHTML = '';
      const add = (id, label, style) => {
        const node = el('button', 'wall-i' + (S.wallSrc === id ? ' on' : ''));
        const prev = el('div', 'wall-p');
        if (style) prev.style.cssText = style;
        node.appendChild(prev);
        node.appendChild(el('span', '', t(label)));
        node.onclick = () => this.select(id);
        box.appendChild(node);
        return prev;
      };
      add('', 'None', 'background: var(--surface-2)');
      WALL_PRESETS.forEach(([id, label]) => {
        const prev = add(id, label);
        prev.style.backgroundImage = this.preset(id.slice(2));
        prev.style.backgroundSize = id === 'p:blobs' ? 'cover' : 'auto';
        prev.style.backgroundColor = 'var(--bg)';
      });
      add('cover', 'Current cover', 'background: var(--accent-soft)');
      let local = '';
      try { local = localStorage.getItem(WALL_KEY) || ''; } catch {}
      if (local) {
        const prev = add('local', 'My image');
        prev.style.background = `center/cover no-repeat url("${local}")`;
      }
    }

    const pick = (id, key, options) => {
      const host = $(id);
      if (!host) return;
      host.innerHTML = '';
      options.forEach(([value, label]) => {
        const chip = el('button', 'chip' + (S[key] === value ? ' on' : ''), t(label));
        chip.onclick = () => { S[key] = value; this.apply(); saveSettings(); this.build(); };
        host.appendChild(chip);
      });
    };
    pick('wallMode', 'wallMode',
         [['cover', 'Fill'], ['contain', 'Fit'], ['tile', 'Tile'], ['center', 'Centre']]);
    pick('wallScope', 'wallScope',
         [['app', 'App'], ['player', 'Full-screen player'], ['both', 'Everywhere']]);

    const set = (id, v) => { const n = $(id); if (n) n.value = v; };
    const txt = (id, v) => { const n = $(id); if (n) n.textContent = v; };
    set('sWallOpacity', S.wallOpacity); txt('vWallOpacity', S.wallOpacity);
    set('sWallBlur', S.wallBlur); txt('vWallBlur', S.wallBlur);
    set('sWallDim', S.wallDim); txt('vWallDim', S.wallDim);
    set('wallUrl', (S.wallSrc && !S.wallSrc.startsWith('p:')
                    && S.wallSrc !== 'local' && S.wallSrc !== 'cover') ? S.wallSrc : '');
  },

  bind() {
    const file = $('wallFile');
    if (file) file.onchange = event => {
      const f = event.target.files && event.target.files[0];
      event.target.value = '';
      this.pickFile(f);
    };
    const pickBtn = $('wallPick');
    if (pickBtn && file) pickBtn.onclick = () => file.click();
    const url = $('wallUrl');
    if (url) url.onchange = async () => {
      const v = url.value.trim(); if (!v) { this.clear(); return; }
      const ticket = this.beginChange36();
      url.setAttribute('aria-busy','true');
      try { const data = await api('/api/wallpaper/resolve', {method:'POST',body:{url:v},timeout:45000});
        if(ticket!==this.changeTicket36)return;
        if (!data || typeof data.file !== 'string' || !/^[a-f0-9]{64}\.jpg$/.test(data.file)) throw new Error(t('Could not load wallpaper'));
        const src='/api/wallpaper/file/'+encodeURIComponent(data.file);
        S.wallSrc=src; this.apply(); saveSettings(); this.build(); toast(t('Wallpaper set'));
      } catch(e) { if(ticket===this.changeTicket36)toast(t('Could not load wallpaper')+': '+e.message); }
      finally { if(ticket===this.changeTicket36)url.removeAttribute('aria-busy'); }
    };
    const off = $('wallClear');
    if (off) off.onclick = () => this.clear();
    [['sWallOpacity', 'wallOpacity'], ['sWallBlur', 'wallBlur'], ['sWallDim', 'wallDim']]
      .forEach(([id, key]) => {
        const node = $(id);
        if (!node) return;
        node.oninput = event => {
          S[key] = Math.round(+event.target.value);
          this.apply(); saveSettings();
          const n = $('v' + id.slice(1)); if (n) n.textContent = S[key];
        };
      });
  },
};

/* ------------------------------------------------------- вид интерфейса */
/* Всё, что раньше было зашито в app.css одним значением: шрифт, масштаб,
   форма обложек, вид полосы времени, сила размытия панелей. Каждая
   настройка — это класс на body или переменная, поэтому они складываются
   с любой темой, включая рисованную. */
const UI_FONTS = [
  ['system', 'System'], ['rounded', 'Rounded'], ['serif', 'Serif'],
  ['mono', 'Monospace'], ['hand', 'Handwritten'], ['condensed', 'Condensed'],
];
const UI_SHAPES = [['rounded', 'Rounded'], ['square', 'Square'], ['circle', 'Circle']];
const UI_BARS = [['slim', 'Thin line'], ['round', 'Rounded'], ['thick', 'Thick'], ['step', 'Segmented']];

const SCALE_HELP41="Release the slider to apply the interface size.";
for(const [lang,text] of Object.entries({"ru": "Отпусти ползунок, чтобы применить размер интерфейса.", "es": "Suelta el control para aplicar el tamaño de la interfaz.", "pt": "Solte o controle para aplicar o tamanho da interface.", "de": "Loslassen, um die Größe der Oberfläche anzuwenden.", "fr": "Relâchez le curseur pour appliquer la taille de l’interface.", "it": "Rilascia il cursore per applicare la dimensione dell’interfaccia.", "tr": "Arayüz boyutunu uygulamak için kaydırıcıyı bırakın.", "pl": "Puść suwak, aby zastosować rozmiar interfejsu.", "uk": "Відпусти повзунок, щоб застосувати розмір інтерфейсу.", "zh": "松开滑块以应用界面大小。", "ja": "スライダーを離すとインターフェースのサイズが適用されます。"}))if(PACKS[lang])PACKS[lang][SCALE_HELP41]=text;

const Look = {
  apply() {
    const root = document.documentElement.style;
    const body = document.body;
    ['system', 'rounded', 'serif', 'mono', 'hand', 'condensed']
      .forEach(f => body.classList.toggle('font-' + f, S.uiFont === f));
    ['rounded', 'square', 'circle']
      .forEach(f => body.classList.toggle('shape-' + f, (S.coverShape || 'rounded') === f));
    ['slim', 'round', 'thick', 'step']
      .forEach(f => body.classList.toggle('bar-' + f, (S.barStyle || 'slim') === f));
    const scale = Number(S.uiScale);
    S.uiScale = Math.max(85, Math.min(125, Number.isFinite(scale) ? scale : 100));
    root.setProperty('--ui-scale', (S.uiScale / 100).toFixed(3));
    const unit = (S.uiScale / 100);
    body.classList.toggle('layout-tight65', innerWidth > 900 && innerWidth / unit < 1100);
    const tools65=document.getElementById('pRight');if(tools65){if(!tools65.dataset.keys65){tools65.dataset.keys65='1';tools65.addEventListener('keydown',e=>{if(e.target!==tools65||!document.body.classList.contains('layout-tight65'))return;const max=tools65.scrollWidth-tools65.clientWidth;let next=tools65.scrollLeft;if(e.key==='Home')next=0;else if(e.key==='End')next=max;else if(e.key==='ArrowRight')next+=88;else if(e.key==='ArrowLeft')next-=88;else return;e.preventDefault();tools65.scrollTo({left:next,behavior:'instant'})})}const tight=body.classList.contains('layout-tight65');if(tight){const label=LANG==='ru'?'Дополнительные кнопки плеера — прокрутите вправо':'Additional player controls — scroll right';tools65.tabIndex=0;tools65.setAttribute('role','group');tools65.setAttribute('aria-label',label);tools65.title=label}else{tools65.removeAttribute('tabindex');tools65.removeAttribute('role');tools65.removeAttribute('aria-label');tools65.removeAttribute('title')}}
    root.setProperty('--layout-vw37', (innerWidth / unit / 100) + 'px');
    root.setProperty('--layout-vh37', (innerHeight / unit / 100) + 'px');
    // Re-layout is not a window resize event. Notify only geometry-dependent renderers.
    const geometry38=JSON.stringify([S.uiScale,innerWidth,innerHeight,S.uiFont]);
    if(this._geometry38!==geometry38){this._geometry38=geometry38;
    cancelAnimationFrame(this._layout37 || 0);
    this._layout37 = requestAnimationFrame(() => {
      if (typeof Karaoke !== 'undefined' && Karaoke.synced) Karaoke.center(true);
      if (typeof FluidCover24 !== 'undefined') { FluidCover24.resize(); FluidCover24.draw(); }
      if (typeof Viz !== 'undefined' && Viz.resize) Viz.resize();
    });
    }
    root.setProperty('--blur', (+S.glass >= 0 ? +S.glass : 22) + 'px');
    // Explicit appearance choice wins over a flat theme's inherited --blur:0.
    body.style.setProperty('--blur', (+S.glass >= 0 ? +S.glass : 22) + 'px');
    body.classList.toggle('glassy', (+S.glass || 0) > 0);

    // Своё правило пользователя кладём в отдельный <style>: перезаписывать
    // его целиком дешевле, чем следить за отдельными свойствами.
    let node = document.getElementById('userCss');
    if (!node) {
      node = document.createElement('style');
      node.id = 'userCss';
      document.head.appendChild(node);
    }
    if(node.textContent!==(S.customCss||''))node.textContent = S.customCss || '';
  },

  build() {
    const pick = (id, key, options) => {
      const host = $(id);
      if (!host) return;
      host.innerHTML = '';
      options.forEach(([value, label]) => {
        const chip = el('button', 'chip' + (S[key] === value ? ' on' : ''), t(label));
        chip.onclick = () => { S[key] = value; this.apply(); saveSettings(); this.build(); };
        host.appendChild(chip);
      });
    };
    pick('uiFont', 'uiFont', UI_FONTS);
    pick('uiShape', 'coverShape', UI_SHAPES);
    pick('uiBar', 'barStyle', UI_BARS);
    const set = (id, v) => { const n = $(id); if (n) n.value = v; };
    const txt = (id, v) => { const n = $(id); if (n) n.textContent = v; };
    set('sUiScale', S.uiScale); txt('vUiScale', S.uiScale);
    set('sGlass', S.glass); txt('vGlass', S.glass);
    const css = $('uiCss');
    if (css && css.value !== (S.customCss || '')) css.value = S.customCss || '';
  },

  // Native range pointer coordinates are unreliable under body CSS zoom in
  // Chromium/WebView2. Use physical client coordinates and never move the rail
  // under a held pointer. Draft changes the thumb; one commit resizes the app.
  bindScale41() {
    const node=$('sUiScale');if(!node||node.dataset.scaleBound41)return;
    node.dataset.scaleBound41='1';
    const hint=el('div','h',t(SCALE_HELP41));hint.id='scaleHelp41';hint.dataset.uiI18n='';node.closest('.set').firstElementChild.append(hint);node.setAttribute('aria-describedby','scaleHelp41');
    const normalized=value=>Math.max(85,Math.min(125,85+Math.round((Number(value)-85)/5)*5));
    const show=value=>{node.value=normalized(value);const label=$('vUiScale');if(label)label.textContent=node.value;};
    const commit=()=>{S.uiScale=normalized(node.value);cancelAnimationFrame(this._apply38||0);this.apply();show(S.uiScale);requestAnimationFrame(()=>node.closest('.set')?.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'}));saveSettings(true);};
    const at=event=>{const d=this.scaleDrag41;if(!d)return;const ratio=Math.max(0,Math.min(1,(event.clientX-d.left)/d.width));show(85+ratio*40);};
    const cancel=()=>{const d=this.scaleDrag41;if(!d)return;this.scaleDrag41=null;show(S.uiScale);if(node.hasPointerCapture(d.id))node.releasePointerCapture(d.id);};
    node.onpointerdown=event=>{
      if(event.button!==0||this.scaleDrag41)return;
      event.preventDefault();node.focus({preventScroll:true});
      const r=node.getBoundingClientRect(),zoom=r.width/Math.max(1,node.offsetWidth);
      const thumb=parseFloat(getComputedStyle(node).getPropertyValue('--scale-thumb41'))||18;
      const inset=Math.min(r.width/2,thumb*zoom/2);
      this.scaleDrag41={id:event.pointerId,left:r.left+inset,width:Math.max(1,r.width-2*inset)};
      node.setPointerCapture(event.pointerId);at(event);
    };
    node.onpointermove=event=>{if(this.scaleDrag41?.id===event.pointerId){event.preventDefault();at(event);}};
    node.onpointerup=event=>{if(this.scaleDrag41?.id!==event.pointerId)return;event.preventDefault();at(event);this.scaleDrag41=null;if(node.hasPointerCapture(event.pointerId))node.releasePointerCapture(event.pointerId);commit();};
    node.onpointercancel=cancel;node.onlostpointercapture=cancel;
    node.addEventListener('keydown',event=>{if(event.key==='Escape'&&this.scaleDrag41){event.preventDefault();event.stopPropagation();cancel();}});
    node.oninput=()=>{if(this.scaleDrag41)return;show(node.value);S.uiScale=normalized(node.value);cancelAnimationFrame(this._apply38||0);this._apply38=requestAnimationFrame(()=>this.apply());};
    node.onchange=()=>{if(!this.scaleDrag41)commit();};
  },

  bind() {
    if (!this._resize37) { this._resize37 = true; addEventListener('resize', debounce(() => this.apply(), 80)); }
    this.bindScale41();
    [['sGlass', 'glass']].forEach(([id, key]) => {
      const node = $(id);
      if (!node) return;
      node.oninput = event => {
        S[key] = Math.round(+event.target.value);
        cancelAnimationFrame(this._apply38||0);this._apply38=requestAnimationFrame(()=>this.apply());
        clearTimeout(this._save37); this._save37=setTimeout(()=>saveSettings(),180);
        const n = $('v' + id.slice(1)); if (n) n.textContent = S[key];
      };
    });
    const css = $('uiCss');
    if (css) {
      css.oninput = debounce(() => {
        S.customCss = css.value.slice(0, 20000);
        this.apply(); saveSettings();
      }, 400);
    }
    const reset = $('uiReset');
    if (reset) reset.onclick = () => {
      ['uiFont', 'uiScale', 'coverShape', 'barStyle', 'glass', 'customCss']
        .forEach(k => { S[k] = DEFAULTS[k]; });
      this.apply(); saveSettings(); this.build();
      toast(t('Look reset'));
    };
  },
};

