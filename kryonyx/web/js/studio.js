/* Studio — customizable discovery and search, with honest source/local stats. */
'use strict';
const Studio = {
  search: { source: '', duration: '', sort: 'relevance', liked: false, layout: 'list' },
  counts: new Map(), pending: new Set(), statuses: {}, homeData: [],
  defaults: { searchLayout: 'list', searchSort: 'relevance', density: 'comfortable', cards: 180, stats: true, localStats: true, hero: true, quick: true, hidden: [], order: [], saved: [] },
  prefs() { return { ...this.defaults, ...(S.studio || {}) }; },
  tr(en, ru) { return t(en); },
  init() {
    this.search.layout=this.prefs().searchLayout==='grid'?'grid':'list';
    this.search.sort=['relevance','popular','title','duration'].includes(this.prefs().searchSort)?this.prefs().searchSort:'relevance';
    const q = $('q'); q.setAttribute('aria-label', t('Search'));
    q.placeholder = this.tr('Search tracks, artists, albums or paste a link', 'Трек, исполнитель, альбом или ссылка');
    const home = $('vHome');
    const head = el('div', 'studio-page-head');
    head.innerHTML = `<div><span class="studio-eyebrow" data-ui-i18n>${this.tr('YOUR MUSIC SPACE', 'ВАША МУЗЫКА')}</span></div>`;
    head.firstChild.appendChild($('greet'));
    const custom = el('button', 'btn g', `${icon('mixer','ic s')}<span data-ui-i18n>${this.tr('Customize', 'Настроить')}</span>`);
    custom.onclick = () => this.openSettings(); head.appendChild(custom); home.prepend(head);
    const hero = el('div', 'studio-hero'); hero.id = 'studioHero'; head.after(hero);
    const quick = el('div', 'studio-quick'); quick.id = 'studioQuick'; hero.after(quick);
    const buttons = [ ['heart','Liked','Любимое', () => App.go('liked')], ['clock','History','История',() => App.go('history')], ['lib','My library','Медиатека',() => App.go('lib')], ['search','Discover music','Найти музыку',() => App.go('search')] ];
    buttons.forEach(([ico,en,ru,fn]) => { const b = el('button','studio-shortcut',`${icon(ico)}<span data-ui-i18n>${this.tr(en,ru)}</span>${icon('next','ic s')}`); b.onclick=fn; quick.appendChild(b); });
    this.paintHero([]); this.buildSearch(); this.apply(); this.searchLanding();
    const top = el('button','ib studio-custom',icon('mixer')); top.title=this.tr('Customize interface','Настроить интерфейс'); top.setAttribute('aria-label',top.title); top.onclick=()=>this.openSettings(); $('top').appendChild(top);
    addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase()==='k') { e.preventDefault(); App.go('search'); q.focus(); q.select(); } });
    // Repaint local labels after a cleared history; no stale cache survives navigation.
    document.querySelectorAll('[data-nav]').forEach(b=>b.addEventListener('click',()=>{ this.counts.clear(); this.refreshVisible(); }));
  },
  update(patch) { S.studio = { ...this.prefs(), ...patch }; saveSettings(); this.apply(); },
  apply() {
    const p=this.prefs();
    document.body.classList.toggle('studio-compact',p.density==='compact');
    document.body.classList.toggle('studio-has-hero',p.hero);
    document.body.classList.toggle('studio-no-global',!p.stats);
    document.body.classList.toggle('studio-no-local',!p.localStats);
    document.documentElement.style.setProperty('--studio-card',Math.max(150,Math.min(240,+p.cards || 180))+'px');
    if($('studioHero')) $('studioHero').hidden=!p.hero;
    if($('studioQuick')) $('studioQuick').hidden=!p.quick;
    this.layoutShelves(); this.refreshVisible();
  },
  paintHero(rows) {
    const track=rows.flatMap(r=>r.unresolved || r.kind==='albums' || r.kind==='playlists' ? [] : r.items || []).find(t=>t.id && t.title);
    const box=$('studioHero'); if(!box)return;
    box.innerHTML=`<div class="studio-hero-copy"><span class="studio-eyebrow" data-ui-i18n>${this.tr('DAILY DISCOVERY','ОТКРЫТИЯ ДНЯ')}</span><h2 data-ui-i18n>${this.tr('Find your next favourite.','Музыка в вашем ритме.')}</h2><p data-ui-i18n>${this.tr('Your picks, open catalogues and a mix that evolves with you.','Ваши подборки, открытые каталоги и микс, который меняется вместе с вами.')}</p><div class="row-acts"><button class="btn studio-hero-play">${icon('play','ic s f')}<span data-ui-i18n>${this.tr('My mix','Мой микс')}</span></button><button class="btn g studio-hero-search" data-ui-i18n>${this.tr('Explore music','Открыть поиск')}</button></div></div><div class="studio-featured">${track ? '<img alt=""><span class="studio-featured-label" data-ui-i18n>'+this.tr('IN YOUR PICKS','В ПОДБОРКАХ')+'</span><strong data-ui-i18n>'+esc(track.title)+'</strong><span data-ui-i18n>'+esc(track.artist || '')+'</span>' : icon('note','studio-hero-note')+'<strong data-ui-i18n>'+this.tr('Start with a song','Начните с любимой песни')+'</strong><span data-ui-i18n>'+this.tr('Your picks grow as you listen','Подборки появятся по мере прослушивания')+'</span>'}</div>`;
    box.querySelector('.studio-hero-play').onclick=()=> $('bMix').click();
    box.querySelector('.studio-hero-search').onclick=()=>App.go('search');
    if(track){box.querySelector('.studio-featured strong').dataset.entityName='';box.querySelector('.studio-featured>span:last-child').dataset.entityName='';setImg(box.querySelector('img'),track.thumbnail,320);const featured=box.querySelector('.studio-featured');featured.setAttribute('role','button');featured.tabIndex=0;featured.setAttribute('aria-label',this.tr('Play ','Воспроизвести ')+track.title);featured.onclick=()=>Player.play(track,rows.flatMap(r=>r.items || []).filter(t=>t.id));featured.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();featured.click();}};}
  },
  shelfKey(row) { return JSON.stringify([row.kind || '',row.title_key || row.title || '',row.title_args || {}]); },
  decorateShelf(shelf,row) { shelf.dataset.studioKey=this.shelfKey(row); },
  layoutShelves() {
    const box=$('rows');if(!box)return;const p=this.prefs();const shelves=[...box.querySelectorAll(':scope > .shelf[data-studio-key]')];
    shelves.forEach((s,i)=>{s.dataset.originalOrder ??= i; s.hidden=p.hidden.includes(s.dataset.studioKey);});
    const rank=s=>{const i=p.order.indexOf(s.dataset.studioKey);return i<0 ? 10000 + +s.dataset.originalOrder : i;};
    shelves.sort((a,b)=>rank(a)-rank(b)).forEach(s=>box.appendChild(s));
  },
  openSettings() {
    let modal=$('mStudio');if(modal)modal.remove();const p=this.prefs();
    modal=el('div','modal studio-modal');modal.id='mStudio';modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','studioSetTitle');
    modal.innerHTML=`<div class="studio-modal-head"><div><span class="studio-eyebrow" data-ui-i18n>${this.tr('MAKE IT YOURS','ПОДСТРОЙТЕ ПОД СЕБЯ')}</span><h2 id="studioSetTitle" data-ui-i18n>${this.tr('Your workspace','Ваш интерфейс')}</h2></div><button class="ib" data-studio-close aria-label="${this.tr('Close','Закрыть')}">${icon('close')}</button></div><div class="studio-modal-body"><div class="studio-setting"><label for="studioDensity" data-ui-i18n>${this.tr('Track density','Плотность списка')}</label><select id="studioDensity"><option value="comfortable">${this.tr('Comfortable','Свободно')}</option><option value="compact">${this.tr('Compact','Компактно')}</option></select></div><div class="studio-setting"><label for="studioCardSize" data-ui-i18n>${this.tr('Cover size','Размер карточек')}</label><input id="studioCardSize" type="range" min="150" max="240" step="10" value="${p.cards}"></div><div id="studioToggles"></div></div><div class="studio-modal-foot"><button class="btn g" id="studioReset" data-ui-i18n>${this.tr('Reset layout','Сбросить оформление')}</button><button class="btn" data-studio-close data-ui-i18n>${this.tr('Done','Готово')}</button></div>`;
    document.body.appendChild(modal);
    $('studioDensity').value=p.density;$('studioDensity').onchange=e=>this.update({density:e.target.value});$('studioCardSize').oninput=e=>this.update({cards:+e.target.value});
    const buildSections=()=>{
      const host=$('studioSections');if(!host)return;host.replaceChildren();
      const shelves=[...$('rows').querySelectorAll(':scope > [data-studio-key]')];
      shelves.forEach((s,i)=>{const key=s.dataset.studioKey;const line=el('div','studio-section-setting');const lab=el('label','',`<input type="checkbox" ${this.prefs().hidden.includes(key)?'':'checked'}><span data-ui-i18n>${esc(s.querySelector('h2')?.textContent || key)}</span>`);lab.querySelector('input').onchange=e=>{let hidden=this.prefs().hidden.filter(x=>x!==key);if(!e.target.checked)hidden.push(key);this.update({hidden});};line.appendChild(lab);
        [-1,1].forEach(dir=>{const b=el('button','ib',icon(dir<0?'prev':'next','ic s'));b.title=this.tr(dir<0?'Move up':'Move down',dir<0?'Выше':'Ниже');b.setAttribute('aria-label',b.title);b.disabled=i+dir<0||i+dir>=shelves.length;b.onclick=()=>{const order=shelves.map(s=>s.dataset.studioKey);[order[i],order[i+dir]]=[order[i+dir],order[i]];this.update({order});buildSections();};line.appendChild(b);});host.appendChild(line);});
      if(!shelves.length)host.innerHTML=`<p class="studio-note" data-ui-i18n>${this.tr('Sections become available when picks load.','Блоки станут доступны после загрузки подборок.')}</p>`;
    };buildSections();
    $('studioReset').onclick=()=>{this.update({...this.defaults,saved:this.prefs().saved});this.search.layout=this.defaults.searchLayout;this.search.sort=this.defaults.searchSort;$('studioSort').value=this.search.sort;['list','grid'].forEach(m=>$('studio'+(m==='list'?'List':'Grid')).classList.toggle('on',m===this.search.layout));if(K.search.query)App.renderSearchState(!K.search.loading);closeModals();this.openSettings();};
    modal.querySelectorAll('[data-studio-close]').forEach(b=>b.onclick=()=>{closeModals();$('q').focus();});openModal('mStudio');setTimeout(()=>$('studioDensity').focus(),100);
    modal.addEventListener('keydown',e=>{if(e.key!=='Tab')return;const nodes=[...modal.querySelectorAll('button:not(:disabled),input,select')];const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}});
  },
  buildSearch() {
    const host=$('vSearch');const intro=el('div','studio-search-intro',`<span class="studio-eyebrow" data-ui-i18n>${this.tr('ONE SEARCH. MORE MUSIC.','ОДИН ПОИСК. БОЛЬШЕ МУЗЫКИ.')}</span>`);host.prepend(intro);
    const overview=el('button','chip studio-overview',this.tr('Browse search','Обзор поиска'));overview.setAttribute('data-ui-i18n','');overview.onclick=()=>this.showSearchLanding();intro.appendChild(overview);
    const landing=el('div','studio-search-landing');landing.id='studioLanding';$('sTitle').after(landing);
    const toolbar=el('div','studio-search-tools');toolbar.id='studioSearchTools';
    toolbar.innerHTML=`<label><span data-ui-i18n>${this.tr('Source','Источник')}</span><select id="studioSource"><option value="">${this.tr('All sources','Все источники')}</option></select></label><label><span data-ui-i18n>${this.tr('Duration','Длительность')}</span><select id="studioDuration"><option value="">${this.tr('Any length','Любая')}</option><option value="short">${this.tr('Under 3 min','До 3 минут')}</option><option value="medium">${t('3–6 min')}</option><option value="long">${this.tr('Over 6 min','Более 6 минут')}</option></select></label><label><span data-ui-i18n>${this.tr('Sort','Сортировка')}</span><select id="studioSort"><option value="relevance">${this.tr('Relevance','Релевантность')}</option><option value="popular">${this.tr('Service popularity','Популярность в сервисе')}</option><option value="title">${this.tr('Title A–Z','Название А–Я')}</option><option value="duration">${this.tr('Shortest first','Сначала короткие')}</option></select></label><label class="studio-likes"><input id="studioLiked" type="checkbox"><span data-ui-i18n>${this.tr('Liked only','Только любимые')}</span></label><div class="studio-layout"><button class="ib on" id="studioList" aria-label="${this.tr('List','Список')}">${icon('queue')}</button><button class="ib" id="studioGrid" aria-label="${this.tr('Grid','Карточки')}">${icon('plug')}</button></div>`;
    const filterToggle=el('button','chip studio-filter-toggle',`${icon('mixer','ic s')}<span data-ui-i18n>${this.tr('Filters and sorting','Фильтры и сортировка')}</span>`);filterToggle.setAttribute('aria-expanded','false');filterToggle.setAttribute('aria-controls','studioSearchTools');filterToggle.id='studioFilterToggle';filterToggle.onclick=()=>{const open=!host.classList.contains('studio-filters-open');host.classList.toggle('studio-filters-open',open);filterToggle.setAttribute('aria-expanded',String(open));};
    $('sTabs').after(filterToggle);filterToggle.after(toolbar);
    const summary=el('div','studio-search-summary');summary.id='studioSearchSummary';toolbar.after(summary);
    const best=el('div','studio-best');best.id='studioBest';summary.after(best);
    $('studioSort').value=this.search.sort;
    ['list','grid'].forEach(m=>$('studio'+(m==='list'?'List':'Grid')).classList.toggle('on',m===this.search.layout));
    const change=(key,value)=>{this.search[key]=value;if(key==='sort')this.update({searchSort:value});App.renderSearchState(!K.search.loading);};
    [['studioSource','source'],['studioDuration','duration'],['studioSort','sort']].forEach(([id,key])=>$(id).onchange=e=>change(key,e.target.value));$('studioLiked').onchange=e=>change('liked',e.target.checked);
    ['list','grid'].forEach(mode=>$('studio'+(mode==='list'?'List':'Grid')).onclick=()=>{this.search.layout=mode;this.update({searchLayout:mode});['list','grid'].forEach(m=>$('studio'+(m==='list'?'List':'Grid')).classList.toggle('on',m===mode));App.renderSearchState(!K.search.loading);});
  },
  showSearchLanding() {
    App.cancelSearch(); ++App.searchToken; App.loading(false); K.search={query:'',page:0,tracks:[],authors:[],albums:[],playlists:[],loading:false,more:false};
    $('q').value='';$('qClear').style.display='none';Hints.hide();App.go('search');this.searchLanding();
  },
  searchLanding() {
    if(K.search.query)return;
    $('sTitle').textContent=this.tr('What will you listen to?','Что послушаем?');
    $('studioFilterToggle').hidden=true;document.querySelector('.studio-overview').hidden=true;
    ['sAuthors','sAlbums','sPlaylists','sTracksH','sMore'].forEach(id=>$(id).style.display='none');$('sTracks').replaceChildren();
    $('studioSearchTools').hidden=true;$('sTabs').hidden=true;$('studioSearchSummary').hidden=true;$('studioBest').hidden=true;$('studioLanding').hidden=false;
    const host=$('studioLanding');host.innerHTML=`<p data-ui-i18n>${this.tr('Find a song, discover an artist or paste a playlist link. Ctrl / ⌘ K opens search from anywhere.','Найдите песню, откройте исполнителя или вставьте ссылку на плейлист. Ctrl / ⌘ K — быстрый переход к поиску.')}</p><h3 data-ui-i18n>${this.tr('Explore a mood','Выберите настроение')}</h3><div class="studio-moods"></div><h3 data-ui-i18n>${this.tr('Saved searches','Сохранённые запросы')}</h3><div class="studio-saved"></div>`;
    [['jazz','Late-night jazz','Ночной джаз','jazz'],['focus','Deep focus','Для концентрации','ambient focus'],['energy','Energy boost','Заряд энергии','energetic electronic'],['calm','Slow morning','Спокойное утро','acoustic chill']].forEach(([key,en,ru,query])=>{const b=el('button','studio-mood '+key,`<span>${icon(key==='energy'?'spark':'note')}</span><strong data-ui-i18n>${this.tr(en,ru)}</strong><small data-ui-i18n>${this.tr('Explore','Слушать и искать')} →</small>`);b.onclick=()=>this.runSearch(query);host.querySelector('.studio-moods').appendChild(b);});
    const saved=host.querySelector('.studio-saved');this.prefs().saved.forEach(query=>{const b=el('button','chip',esc(query));b.setAttribute('data-ui-i18n','');b.onclick=()=>this.runSearch(query);saved.appendChild(b);});if(!saved.children.length)saved.innerHTML=`<p class="studio-note" data-ui-i18n>${this.tr('Save a query from the results to return to it later.','Сохраните запрос в результатах поиска, чтобы вернуться к нему позже.')}</p>`;
  },
  runSearch(query) { $('q').value=query;$('qClear').style.display=query?'':'none';Hints.hide();App.search(query); },
  startSearch() {
    this.statuses=Object.fromEntries(activeSources().map(s=>[s,'loading']));
    $('studioFilterToggle').hidden=false;document.querySelector('.studio-overview').hidden=false;
    $('studioLanding').hidden=true;['studioSearchTools','sTabs','studioSearchSummary'].forEach(id=>$(id).hidden=false);
    this.search.source='';$('studioSource').value='';this.searchSummary([],false);
  },
  sourceStatus(source,status) {this.statuses[source]=status;},
  number(track) {
    // v73: plays_n is the server's numeric reading of YouTube's "18M views".
    const value=track.play_count ?? track.plays_n ?? track.views;
    if(typeof value==='number')return Number.isFinite(value)&&value>=0?value:null;
    if(typeof value!=='string'||!value.trim())return null;
    // Exact digits only. Abbreviated/localized service strings are shown as-is,
    // never guessed for a cross-source popularity comparison.
    const raw=value.trim().replace(/[\s,\u00a0]/g,'');const parsed=Number(raw);return /^\d+$/.test(raw)&&Number.isFinite(parsed)?parsed:null;
  },
  filterTracks(tracks) {
    const s=this.search;let list=tracks.filter(t=>(!s.source||t.source===s.source)&&(!s.liked||K.likes.has(t.id))&&(!s.duration||(t.duration>0&&(s.duration==='short'?t.duration<180:s.duration==='medium'?t.duration>=180&&t.duration<=360:t.duration>360))));
    if(s.sort==='title')list.sort((a,b)=>String(a.title).localeCompare(String(b.title),LANG));
    if(s.sort==='duration')list.sort((a,b)=>(a.duration||Infinity)-(b.duration||Infinity));
    if(s.sort==='popular')list.sort((a,b)=>{const x=this.number(a),y=this.number(b);return x===null?y===null?0:1:y===null?-1:y-x;});
    return list;
  },
  searchSummary(tracks,done) {
    if(!$('studioSearchSummary'))return;const query=K.search.query||'';const total=K.search.tracks.length;
    const sources=[...new Set([...activeSources(),...K.search.tracks.map(t=>t.source)])];const select=$('studioSource');
    if(select.dataset.sources!==sources.join(',')){const value=this.search.source;select.replaceChildren(new Option(this.tr('All sources','Все источники'),''),...sources.map(s=>new Option(sourceName(s),s)));select.value=value;select.dataset.sources=sources.join(',');}
    const summary=$('studioSearchSummary');summary.innerHTML=`<div class="studio-found" data-ui-i18n><strong>${tracks.length}</strong> ${this.tr('of','из')} ${total} ${this.tr('loaded tracks','загруженных треков')}<span>${K.search.cancelled?this.tr('Search cancelled','Поиск отменён'):done?this.tr('Search complete','Поиск завершён'):this.tr('Searching sources…','Источники отвечают…')}</span></div><div class="studio-summary-actions"><button class="chip" id="studioFilterReset" data-ui-i18n>${this.tr('Reset filters','Сбросить фильтры')}</button><button class="chip" id="studioSaveSearch">${icon('plus','ic s')}<span data-ui-i18n>${this.prefs().saved.includes(query)?this.tr('Unsave query','Убрать запрос'):this.tr('Save query','Сохранить запрос')}</span></button></div><div class="studio-source-state" data-ui-i18n>${Object.entries(this.statuses).map(([s,state])=>`<span class="${state}">${esc(sourceName(s))} · ${this.tr(state==='ok'?'Ready':state==='error'?'Unavailable':state==='cancelled'?'Cancelled':'Searching',state==='ok'?'Готово':state==='error'?'Недоступен':state==='cancelled'?'Отменён':'Поиск')}</span>`).join('')}</div>`;
    $('studioFilterReset').onclick=()=>{Object.assign(this.search,{source:'',duration:'',sort:'relevance',liked:false});$('studioSource').value='';$('studioDuration').value='';$('studioSort').value='relevance';$('studioLiked').checked=false;this.update({searchSort:'relevance'});App.renderSearchState(!K.search.loading);};
    $('studioSaveSearch').disabled=!query;$('studioSaveSearch').onclick=()=>{const saved=this.prefs().saved.filter(q=>q!==query);if(saved.length===this.prefs().saved.length)saved.unshift(query);this.update({saved:saved.slice(0,20)});this.searchSummary(tracks,done);};
    const best=$('studioBest');const track=tracks[0];best.hidden=!track || (App.searchTab && !['all','tracks'].includes(App.searchTab));best.replaceChildren();
    if(track){const copy=el('div','',`<span class="studio-eyebrow" data-ui-i18n>${this.tr(this.search.sort==='relevance'?'TOP RESULT':'FIRST IN YOUR FILTERS',this.search.sort==='relevance'?'ПЕРВЫЙ РЕЗУЛЬТАТ':'ПЕРВЫЙ ПО ВАШИМ ФИЛЬТРАМ')}</span><h2 data-entity-name>${esc(track.title)}</h2><p data-entity-name>${esc(track.artist || '')} · ${esc(sourceName(track.source))}</p>${this.stats(track)}`);const img=el('img');img.alt='';setImg(img,track.thumbnail,180);const play=el('button','btn',`${icon('play','ic s f')}<span>${t('Play')}</span>`);play.setAttribute('aria-label',t('Play')+' '+track.title);play.onclick=()=>Player.play(track,tracks);best.append(img,copy,play);}
  },
  stats() { return ''; },
  queueStats() {},
  refreshVisible() {},
  refreshStats() {},
  async flushStats() {},
};
