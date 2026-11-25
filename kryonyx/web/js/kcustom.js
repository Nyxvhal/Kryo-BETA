/* kcustom.js — свой вид экрана караоке: обложка, фон, размер обложки.

   Обложка и фон хранятся в браузере (localStorage): картинка с диска
   пережимается, чтобы не упереться в лимит. Сцена по умолчанию («Авто»)
   остаётся как была — свой фон включается только по желанию. */
'use strict';

const KC_COVER = 'kryonyx.kcover';
const KC_BG = 'kryonyx.kbg';

const KCustom = {
  store(key) { try { return localStorage.getItem(key) || ''; } catch { return ''; } },

  /* Какую обложку показывать на экране караоке. */
  cover(original) {
    if (!S.kCoverOn) return original;
    const mine = this.store(KC_COVER) || String(S.kCoverUrl || '');
    if (!mine) return original;
    if ((S.kCoverMode || 'always') === 'missing' && original) return original;
    return mine;
  },

  repaint() { if (typeof Player !== 'undefined' && Player.current) Player.paintTrack(); },

  bgValue() {
    const kind = S.kBgKind || 'auto';
    if (kind === 'image') {
      const u = this.store(KC_BG) || String(S.kBgUrl || '');
      return u ? `url("${u.replace(/"/g, '%22')}")` : '';
    }
    if (kind === 'color') return S.kBgColor || '#101018';
    if (kind === 'gradient') {
      return `linear-gradient(${+S.kBgAngle || 0}deg, ${S.kBgColor || '#101018'}, ${S.kBgColor2 || '#3a1c71'})`;
    }
    return '';
  },

  apply() {
    const node = $('nowCustom');
    const value = this.bgValue();
    const on = (S.kBgKind || 'auto') !== 'auto' && !!value;
    const root = document.documentElement.style;
    if (node) {
      node.style.background = '';
      node.style.backgroundImage = on && value.startsWith('url') ? value : '';
      node.style.backgroundColor = '';
      if (on && !value.startsWith('url')) node.style.background = value;
    }
    root.setProperty('--kb-size', (S.kBgFit || 'cover') === 'contain' ? 'contain' : 'cover');
    root.setProperty('--kb-blur', (+S.kBgBlur || 0) + 'px');
    root.setProperty('--kb-dim', (Math.max(0, Math.min(90, +S.kBgDim || 0)) / 100).toFixed(2));
    root.setProperty('--kb-veil', document.body.classList.contains('light') ? '255, 255, 255' : '0, 0, 0');
    root.setProperty('--k-art', ((+S.kArt || 100) / 100).toFixed(2));
    document.body.classList.toggle('k-custom', on);
    document.body.classList.toggle('k-scene', on && !!S.kbScene);
  },

  /* Файл → уменьшенная картинка; GIF не трогаем, иначе он перестанет двигаться. */
  async load(file, max) {
    const data = await new Promise((done, fail) => {
      const fr = new FileReader();
      fr.onload = () => done(fr.result);
      fr.onerror = fail;
      fr.readAsDataURL(file);
    });
    if (/^data:image\/gif/.test(data) && data.length < 3.5e6) return data;
    return new Promise((done, fail) => {
      const img = new Image();
      img.onload = () => {
        const k = Math.min(1, max / Math.max(img.width, img.height));
        if (k >= 1 && data.length < 900000) return done(data);
        const c = document.createElement('canvas');
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        done(c.toDataURL('image/jpeg', 0.88));
      };
      img.onerror = fail;
      img.src = data;
    });
  },

  async pick(file, key, max, after) {
    if (!file) return;
    try {
      const data = await this.load(file, max);
      localStorage.setItem(key, data);
    } catch {
      toast(t('The image is too large for this browser'));
      return;
    }
    after();
  },

  save() { if ((S.kBgKind || 'auto') !== 'auto' && S.vbgOn) { S.vbgOn = false; if (typeof VMedia !== 'undefined') VMedia.applyBg(); } saveSettings(); this.apply(); this.build(); },

  build() {
    const chips = (id, key, options, after) => {
      const host = $(id);
      if (!host) return;
      host.innerHTML = '';
      options.forEach(([value, label]) => {
        const chip = el('button', 'chip' + ((S[key] || options[0][0]) === value ? ' on' : ''), t(label));
        chip.onclick = () => { S[key] = value; this.save(); if (after) after(); };
        host.appendChild(chip);
      });
    };
    chips('kcMode', 'kCoverMode', [['always', 'Always'], ['missing', 'Only when a track has none']],
          () => this.repaint());
    chips('kbKind', 'kBgKind', [['auto', 'Automatic'], ['image', 'Picture'],
                                ['color', 'Colour'], ['gradient', 'Gradient']]);
    chips('kbFit', 'kBgFit', [['cover', 'Fill'], ['contain', 'Fit']]);

    const kind = S.kBgKind || 'auto';
    const show = (id, yes) => { const n = $(id); if (n) n.style.display = yes ? '' : 'none'; };
    show('kbRowImg', kind === 'image');
    show('kbRowCol', kind === 'color' || kind === 'gradient');
    show('kbRowFit', kind === 'image');
    show('kbRowFx', kind === 'image');
    show('kbRowDim', kind !== 'auto');
    show('kbRowScene', kind !== 'auto');
    show('kbC2', kind === 'gradient');
    show('sKbAngle', kind === 'gradient');

    const val = (id, v) => { const n = $(id); if (n && n !== document.activeElement) n.value = v; };
    const txt = (id, v) => { const n = $(id); if (n) n.textContent = v; };
    val('kbC1', S.kBgColor || '#101018'); val('kbC2', S.kBgColor2 || '#3a1c71');
    val('sKbAngle', S.kBgAngle == null ? 135 : S.kBgAngle);
    val('sKbBlur', S.kBgBlur || 0); txt('vKbBlur', S.kBgBlur || 0);
    val('sKbDim', S.kBgDim == null ? 30 : S.kBgDim); txt('vKbDim', S.kBgDim == null ? 30 : S.kBgDim);
    val('sKArt', S.kArt || 100); txt('vKArt', S.kArt || 100);
    const mineCover = this.store(KC_COVER);
    val('kcUrl', mineCover ? '' : (S.kCoverUrl || ''));
    const mineBg = this.store(KC_BG);
    val('kbUrl', mineBg ? '' : (S.kBgUrl || ''));
    const prev = (id, src) => { const n = $(id); if (n) n.style.backgroundImage = src ? `url("${src}")` : ''; };
    prev('kcPrev', mineCover || S.kCoverUrl);
    prev('kbPrev', mineBg || S.kBgUrl);
  },

  bind() {
    const file = (inputId, btnId, key, max, after) => {
      const input = $(inputId), btn = $(btnId);
      if (btn && input) btn.onclick = () => input.click();
      if (input) input.onchange = event => {
        const f = event.target.files && event.target.files[0];
        event.target.value = '';
        this.pick(f, key, max, after);
      };
    };
    file('kcFile', 'kcPick', KC_COVER, 1200, () => {
      S.kCoverUrl = ''; S.kCoverOn = true;
      document.querySelectorAll('[data-sw="kCoverOn"]').forEach(n => n.classList.add('on'));
      this.save(); this.repaint(); toast(t('Cover set'));
    });
    file('kbFile', 'kbPick', KC_BG, 1920, () => {
      S.kBgUrl = ''; S.kBgKind = 'image'; this.save(); toast(t('Background set'));
    });
    const clear = (btnId, key, field, after) => {
      const b = $(btnId);
      if (b) b.onclick = () => {
        try { localStorage.removeItem(key); } catch {}
        S[field] = ''; this.save(); if (after) after();
      };
    };
    clear('kcClear', KC_COVER, 'kCoverUrl', () => this.repaint());
    clear('kbClear', KC_BG, 'kBgUrl');
    const url = (id, key, field, after) => {
      const n = $(id);
      if (n) n.onchange = () => {
        try { localStorage.removeItem(key); } catch {}
        S[field] = n.value.trim(); this.save(); if (after) after();
      };
    };
    url('kcUrl', KC_COVER, 'kCoverUrl', () => { if (S.kCoverUrl) S.kCoverOn = true; this.repaint(); });
    url('kbUrl', KC_BG, 'kBgUrl', () => { if (S.kBgUrl) { S.kBgKind = 'image'; this.save(); } });
    const range = (id, key) => {
      const n = $(id);
      if (n) n.oninput = () => { S[key] = +n.value; this.apply(); this.build(); };
      if (n) n.onchange = () => saveSettings();
    };
    range('sKbBlur', 'kBgBlur'); range('sKbDim', 'kBgDim'); range('sKArt', 'kArt');
    range('sKbAngle', 'kBgAngle');
    ['kbC1', 'kbC2'].forEach((id, i) => {
      const n = $(id);
      if (n) n.oninput = () => { S[i ? 'kBgColor2' : 'kBgColor'] = n.value; this.apply(); };
      if (n) n.onchange = () => saveSettings();
    });
    // Смена светлой/тёмной темы меняет цвет вуали.
    let light40=document.body.classList.contains('light');
    new MutationObserver(() => {const next=document.body.classList.contains('light');if(next!==light40){light40=next;this.apply();}})
      .observe(document.body, { attributes: true, attributeFilter: ['class'] });
  },
};
