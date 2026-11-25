/* avatars.js — каталог аватарок приложения.

   Аватарка живёт сразу в трёх местах: значок на полосе заголовка и в
   боковом меню, favicon вкладки и — главное — иконка окна, панели задач и
   ярлыков. Картинки и готовые .ico лежат в сборке, поэтому выбор ничего не
   скачивает и ничего не пережимает: сервер просто копирует нужный .ico в
   папку данных и правит ярлыки (kryonyx/avatars.py). */
'use strict';

const Avatars = {
  items: [],
  id: '',
  shortcuts: false,
  loaded: false,
  pickRevision: 0,
  pendingRevision: 0,
  confirmedId: '',
  pickChain: Promise.resolve(),


  /* Значок берём у сервера: он знает, что выбрано, даже после
     переустановки интерфейса. */
  async load(force) {
    if (this.loaded && !force) return;
    if (this.RENAMED[S.avatar]) { S.avatar = this.RENAMED[S.avatar]; saveSettings(); }
    const revision=this.pickRevision;
    try {
      const data = await api('/api/avatars', { timeout: 6000 });
      this.items = data.items || [];
      if(revision===this.pickRevision&&!this.pendingRevision){this.id=data.id||S.avatar||'';this.confirmedId=this.id;}
      this.shortcuts = !!data.shortcuts;
      this.loaded = true;
      if (this.id && S.avatar !== this.id) { S.avatar = this.id; saveSettings(); }
    } catch {
      // Сервер ещё поднимается — покажем то, что помним из настроек.
      this.id = S.avatar || '';
    }
    this.paint();
  },

  // Старое имя файла несло служебный тег персонажа. Тег убран, а выбор,
  // сохранённый прежней версией, переносится на новое имя.
  RENAMED: { 'kryonyx-02-black-violet':'kryonyx-core', 'kryonyx-01-saba-sky': 'kryonyx-01-sky', 'portrait-v12-ironmouse-season-0':'kryonyx-core', 'portrait-v12-ironmouse':'kryonyx-core', 'portrait-v12-ironmouse-season-1':'kryonyx-core', 'portrait-v12-ironmouse-season-2':'kryonyx-core', 'portrait-v12-ironmouse-season-3':'kryonyx-core', 'portrait-v12-ironmouse-season-4':'kryonyx-core' },

  src(id) { return /^custom-[a-f0-9]{32}$/.test(id) ? `/api/avatars/custom/${id}/image.png` : `/img/avatars/${this.RENAMED[id] || id}.png`; },

  /* Значки в интерфейсе. Картинку пересоздавать не нужно — меняем src. */
  paint() {
    const id = this.id || S.avatar;
    if (!id) return;
    const url = this.src(id);
    const bar = $('titlebarIcon');
    if (bar) bar.src = url;
    const brand = $('brandAva');
    if (brand) brand.src = url;
    const fav = document.querySelector('link[rel=icon]');
    // Хвост со временем заставляет WebView перечитать favicon.
    if (fav) fav.href = url + '?v=' + Date.now();
  },

  repaintSelection() {
    this.paint(); this.build();
    if(typeof ExperienceV8!=='undefined' && ExperienceV8.items?.length)ExperienceV8.renderStore();
  },

  async pick(id) {
    id=this.RENAMED[id]||id;
    if(!this.confirmedId)this.confirmedId=this.id||S.avatar;
    const revision=++this.pickRevision;this.pendingRevision=revision;
    this.id=id;S.avatar=id;this.repaintSelection();
    // Requests are serialized: a slow older choice must never win on disk.
    const operation=this.pickChain.catch(()=>{}).then(async()=>{
      if(revision!==this.pickRevision)return;
      const res=await api('/api/avatar',{method:'POST',body:{id},timeout:45000});
      this.confirmedId=res.id||id;
      if(revision!==this.pickRevision)return res;
      this.id=this.confirmedId;S.avatar=this.id;saveSettings(true);this.repaintSelection();
      toast(res.shortcuts ? t('Avatar changed — the shortcut icon is updated too') : t('Avatar changed'));
      return res;
    });
    this.pickChain=operation.catch(()=>{});
    try{return await operation;}catch(err){
      if(revision===this.pickRevision){
        this.id=this.confirmedId;S.avatar=this.id;saveSettings(true);this.repaintSelection();
        toast(err.message||t('The avatar was not applied'));
      }
      throw err;
    }finally{if(this.pendingRevision===revision)this.pendingRevision=0;}
  },

  build() {
    if (!this.loaded) { this.load().then(() => this.build()); return; }
    const list = $('avaList');
    if (!list) return;
    list.innerHTML = '';
    let shown = 0;
    this.items.forEach((item) => {
      shown++;
      const node = el('button', 'ava' + (this.id === item.id ? ' on' : ''));
      const img = el('img');
      img.src = this.src(item.id);
      img.alt = item.name;
      img.loading = 'lazy';
      img.decoding = 'async';
      node.appendChild(img);
      node.appendChild(el('span', 'ava-n', esc(item.name)));
      node.title = item.name;
      node.onclick = () => this.pick(item.id);
      list.appendChild(node);
    });
    const counter = $('avaCount');
    if (counter) counter.textContent = `${shown} / ${this.items.length}`;
    const hint = $('avaHint');
    if (hint) {
      hint.textContent = this.shortcuts
        ? t('The picked avatar becomes the icon of the window, the taskbar and the Kryo shortcuts.')
        : t('The picked avatar becomes the icon of the window and the browser tab.');
    }
  },

  bind() {
    // Значок нужен сразу, а не при первом заходе в настройки.
    this.load();
  },
};
