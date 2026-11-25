/* UI v7. Progressive enhancements; no catalogue, credentials or audio engine replaced. */
'use strict';
const InterfaceV7 = {
  rows:new Map(), savedDisplay:new Map(), lastLayout:null, sleepDeadline:0, queueMode:'next',
  tr(en, ru) { return t(en); },
  button(label,ico,fn,cls='btn g'){
    const b=Workspace.btn(label,ico,fn,cls);b.type='button';return b;
  },
  init(){
    document.body.classList.add('ui-v7');
    this.settings();this.profiles();this.backup();this.sleep();this.indexSettings();this.searchSettings();
    this.library();this.search();this.queue();this.safety();this.sectionLinks();this.home();
    addEventListener('kryonyx:settings-save',e=>{if(e.detail==='saved'&&$('mSettings').classList.contains('on')){this.syncProfiles();this.paintFavorites();}});
  },
  settings(){
    const tab=this.button(this.tr('Quick access','Быстрый доступ'),'heart',()=>this.openSettingPane('favorites7'),'set-nav-i');tab.dataset.pane='favorites7';
    $('setTabs').querySelector('[data-pane=workspace]').after(tab);
    $('workspaceSettingsSelect').add(new Option(this.tr('Quick access','Быстрый доступ'),'favorites7'));
    const pane=el('section','pane ui7-favorites');pane.dataset.pane='favorites7';
    pane.innerHTML=`<div class="ui7-page-intro"><span class="ui7-eyebrow" data-ui-i18n>${this.tr('ONLY WHAT YOU NEED','ТОЛЬКО ТО, ЧТО НУЖНО')}</span><h2 data-ui-i18n>${this.tr('Your settings, a click away.','Твои настройки — под рукой.')}</h2><p data-ui-i18n>${this.tr('Pin useful controls with the bookmark button. These shortcuts open the original setting, not a copy.','Закрепляй нужные параметры кнопкой-закладкой. Здесь будут ссылки на исходные настройки, без дубликатов.')}</p></div><div id="ui7FavoriteList"></div>`;
    document.querySelector('.set-body').appendChild(pane);
    const overview=document.querySelector('.pane[data-pane=workspace]');
    overview.querySelector('h2').textContent=this.tr('Built around your rhythm.','Настрой под свой ритм.');
    overview.querySelector('p').textContent=this.tr('Start with a layout. Sound and personal data stay untouched.','Начни с удобной компоновки. Звук и личные данные останутся без изменений.');
    const tag=el('span','ui7-version','CONTROL CENTRE / 07');tag.dataset.uiI18n='';overview.querySelector('h2').before(tag);
    const count=el('span','ui7-fav-count');count.id='ui7FavCount';tab.appendChild(count);
    const body=document.querySelector('.set-body');
    const tip=el('p','ui7-settings-tip');tip.id='ui7SettingsTip';tip.dataset.uiI18n='';tip.textContent=this.tr('Changes apply immediately. Use Quick access for the controls you reach for most.','Изменения применяются сразу. Часто используемые параметры можно закрепить.');
    $('mSettings').querySelector('.acts').prepend(tip);
    const open=App.openPane.bind(App);App.openPane=name=>{
      open(name);this.paintFavorites();this.syncProfiles();$('workspaceSettingsTitle').textContent=this.paneLabel(name);if(name==='favorites7')$('uiSettingsDescription').textContent=this.tr('Pinned controls, without the extra clicks','Закреплённые параметры без лишних переходов');
      const selected=$('setTabs').querySelector(`[data-pane="${CSS.escape(name)}"]`);
      if(selected&&$('mSettings').classList.contains('on')&&innerWidth>760)selected.scrollIntoView({block:'nearest'});
      this.paintSectionLinks(name);
    };
  },
  favorites(){return Array.isArray(S.ui7?.favorites)?S.ui7.favorites.filter(x=>typeof x==='string').slice(0,40):[];},
  indexSettings(){
    document.querySelectorAll('#mSettings .pane .set').forEach(row=>{
      const pane=row.closest('.pane')?.dataset.pane,label=row.querySelector('.l');
      const control=row.querySelector('[data-sw],input:not([type=password]),select,textarea');
      if(!label||!pane||!control||['integrations','plugins','importPane','logs'].includes(pane))return;
      if(row.querySelector('input[type=password]'))return;
      const handle=control.dataset.sw||control.id||control.dataset.workspacePref||control.dataset.uiPref;
      if(!handle)return;const key=pane+':'+handle;
      row.dataset.ui7Setting=key;this.rows.set(key,{row,pane,label,control});
      const pin=this.button(this.tr('Pin setting','Закрепить настройку'),'lyrics',e=>{
        e.preventDefault();e.stopPropagation();let pins=this.favorites().filter(x=>x!==key);
        if(pins.length===this.favorites().length){if(pins.length>=40){toast(this.tr('Up to 40 shortcuts','Можно закрепить до 40 параметров'));return;}pins.push(key);}
        S.ui7={favorites:pins};saveSettings();this.paintFavorites();
      },'ib ui7-pin');pin.dataset.pinKey=key;pin.title=this.tr('Pin / unpin setting','Закрепить / открепить настройку');row.appendChild(pin);
    });
    this.paintFavorites();
  },
  paneLabel(name){return $('setTabs').querySelector(`[data-pane="${CSS.escape(name)}"] span`)?.textContent||$('setTabs').querySelector(`[data-pane="${CSS.escape(name)}"]`)?.textContent||name;},
  paintFavorites(){
    const pins=this.favorites(),key38=JSON.stringify([pins,LANG]);if(this._favoritesKey38===key38)return;this._favoritesKey38=key38;document.querySelectorAll('[data-pin-key]').forEach(b=>{const active=pins.includes(b.dataset.pinKey);b.classList.toggle('on',active);b.setAttribute('aria-pressed',String(active));b.setAttribute('aria-label',this.tr(active?'Unpin setting':'Pin setting',active?'Открепить настройку':'Закрепить настройку'));});
    if($('ui7FavCount'))$('ui7FavCount').textContent=pins.length||'';
    const host=$('ui7FavoriteList');if(!host)return;host.replaceChildren();
    const items=pins.map(key=>[key,this.rows.get(key)]).filter(([,item])=>item);
    if(!items.length){
      const empty=el('div','ui7-empty',`${icon('lyrics')}<strong data-ui-i18n>${this.tr('Your essentials belong here','Здесь будет самое нужное')}</strong><p data-ui-i18n>${this.tr('Open Sound or General and pin a control.','Открой «Звук» или «Общие» и закрепи параметр.')}</p>`);
      empty.appendChild(this.button(this.tr('Explore sound settings','Открыть настройки звука'),'vol',()=>this.openSettingPane('sound')));host.appendChild(empty);return;
    }
    items.forEach(([key,item])=>{
      const line=el('div','ui7-favorite-card');const go=this.resultButton(item,()=>this.goToSetting(key));
      const remove=this.button(this.tr('Unpin','Открепить'),'close',()=>{S.ui7={favorites:pins.filter(p=>p!==key)};saveSettings();this.paintFavorites();},'ib');line.append(go,remove);host.appendChild(line);
    });
  },
  openSettingPane(name){$('setFind').value='';InterfaceV6.searchRun();App.openPane(name);},
  goToSetting(key){
    const item=this.rows.get(key);if(!item)return;this.openSettingPane(item.pane);
    requestAnimationFrame(()=>{item.row.scrollIntoView({block:'center',behavior:S.noAnim?'instant':'smooth'});item.row.classList.add('ui7-located');setTimeout(()=>item.row.classList.remove('ui7-located'),1800);if(item.control.getClientRects().length)item.control.focus({preventScroll:true});});
  },
  resultButton(item,fn){
    const b=el('button','ui7-setting-result');b.type='button';
    const kind=el('small','',this.paneLabel(item.pane));const title=el('strong');title.textContent=item.label.textContent;
    const hint=el('span');hint.textContent=item.row.querySelector('.h')?.textContent||this.tr('Open setting','Открыть настройку');
    [kind,title,hint].forEach(n=>n.dataset.uiI18n='');b.append(kind,title,hint);b.insertAdjacentHTML('beforeend',icon('next','ic s'));b.onclick=fn;return b;
  },
  searchSettings(){
    const body=document.querySelector('.set-body');const results=el('div','ui7-setting-results');results.id='ui7SettingResults';results.hidden=true;$('uiSettingsSearchInfo').after(results);
    const restore=()=>{this.savedDisplay.forEach((value,node)=>node.style.display=value);this.savedDisplay.clear();body.classList.remove('finding');results.hidden=true;results.replaceChildren();$('uiSettingsSearchInfo').hidden=true;const name=body.querySelector('.pane.on')?.dataset.pane;if(name)this.paintSectionLinks(name);};
    const norm=s=>s.toLocaleLowerCase().replace(/ё/g,'е').replace(/[ьъ]/g,'');
    const alias={sound:'звук sound audio эквалайзер equalizer бас bass нормализация volume',look:'общие вид интерфейс general animation анимация',themes:'оформление theme color цвет палитра',lib:'библиотеки sources источники',data:'данные cache кэш очистка storage',keys:'клавиши shortcuts keyboard',workspace:'компоновка layout профиль profile'};
    InterfaceV6.searchRun=()=>{
      restore();const q=norm($('setFind').value.trim());if(!q)return;const tokens=q.split(/\s+/).filter(Boolean);
      body.classList.add('finding');if($('ui7SectionLinks'))$('ui7SectionLinks').hidden=true;body.querySelectorAll('.pane').forEach(p=>{this.savedDisplay.set(p,p.style.display);p.style.display='none';});
      const matches=[...this.rows.entries()].filter(([,item])=>{
        const text=norm(item.label.textContent+' '+(item.row.querySelector('.h')?.textContent||'')+' '+item.control.id+' '+(item.control.dataset.sw||''));return tokens.every(t=>text.includes(t));
      }).slice(0,70);
      const sections=[...$('setTabs').querySelectorAll('[data-pane]')].filter(tab=>tokens.every(t=>norm(this.paneLabel(tab.dataset.pane)+' '+(alias[tab.dataset.pane]||'')).includes(t)));
      results.hidden=false;const total=matches.length+sections.length;$('uiSettingsSearchInfo').hidden=false;
      $('uiSettingsSearchInfo').textContent=total?this.tr('Matches: ','Найдено: ')+total:this.tr('Nothing found. Try “sound”, “theme” or “volume”.','Ничего не найдено. Попробуй «звук», «тема» или «громкость».');
      matches.forEach(([key,item])=>results.appendChild(this.resultButton(item,()=>this.goToSetting(key))));
      sections.forEach(tab=>{const b=this.button(this.tr('Section: ','Раздел: ')+this.paneLabel(tab.dataset.pane),'mixer',()=>this.openSettingPane(tab.dataset.pane),'ui7-section-result');results.appendChild(b);});
      body.scrollTop=0;
    };
    $('setTabs').addEventListener('click',e=>{if(e.target.closest('[data-pane]')){$('setFind').value='';restore();}});
    const select=$('workspaceSettingsSelect');select.addEventListener('change',()=>{if($('setFind').value){$('setFind').value='';restore();}});
  },
  layoutSnapshot(){
    const ws=Workspace.prefs(),st=Studio.prefs();return {noAnim:!!S.noAnim,compact:!!S.compact,workspace:{compactPlayer:ws.compactPlayer,sidebarCollapsed:ws.sidebarCollapsed},studio:{density:st.density,cards:st.cards,hero:st.hero,quick:st.quick}};
  },
  applyLayout(snapshot){
    S.noAnim=snapshot.noAnim;S.compact=snapshot.compact;
    S.workspace={...Workspace.prefs(),...snapshot.workspace};S.studio={...Studio.prefs(),...snapshot.studio};
    applyTheme();Workspace.apply();Studio.apply();App.syncSettingsUI();InterfaceV6.syncPrefs();saveSettings();this.syncProfiles();
  },
  profileValues(name){
    const map={comfort:{noAnim:false,compact:false,workspace:{compactPlayer:true,sidebarCollapsed:false},studio:{density:'comfortable',cards:180,hero:true,quick:true}},focus:{noAnim:true,compact:false,workspace:{compactPlayer:true,sidebarCollapsed:false},studio:{density:'comfortable',cards:180,hero:false,quick:false}},compact:{noAnim:true,compact:true,workspace:{compactPlayer:true,sidebarCollapsed:false},studio:{density:'compact',cards:150,hero:true,quick:true}}};return map[name];
  },
  profiles(){
    const block=el('section','ui7-profiles');block.innerHTML=`<div class="ui7-section-head"><h3 data-ui-i18n>${this.tr('A layout for the way you listen','Как тебе удобнее слушать?')}</h3><span data-ui-i18n>${this.tr('Sound stays unchanged','Звук не меняется')}</span></div><div class="ui7-profile-grid" id="ui7Profiles"></div><div class="ui7-profile-feedback"><span id="ui7ProfileMessage" role="status" data-ui-i18n>${this.tr('Three reversible starting points.','Три варианта. Любой можно отменить.')}</span><button id="ui7UndoLayout" type="button" hidden data-ui-i18n>${this.tr('Undo','Отменить')}</button></div>`;
    $('workspaceSettingsLinks').before(block);
    [['comfort','vol','Comfort','Комфорт','Roomy lists, full home screen','Свободные списки и полная главная'],['focus','lyrics','Focus','Фокус','Less motion, no discovery banner','Без анимаций и баннера на главной'],['compact','queue','Compact','Компактно','More tracks, smaller covers','Больше треков, меньше обложки']].forEach(([key,ico,en,ru,de,dr])=>{
      const b=el('button','ui7-profile',`${icon(ico)}<strong data-ui-i18n>${this.tr(en,ru)}</strong><span data-ui-i18n>${this.tr(de,dr)}</span><i class="ui7-profile-indicator" aria-hidden="true"></i>`);b.type='button';b.dataset.profile=key;
      b.onclick=()=>{this.lastLayout=this.layoutSnapshot();this.applyLayout(this.profileValues(key));$('ui7UndoLayout').hidden=false;$('ui7ProfileMessage').textContent=this.tr('Layout applied. Your sound is unchanged.','Компоновка применена. Настройки звука не изменились.');};$('ui7Profiles').appendChild(b);
    });
    $('ui7UndoLayout').onclick=()=>{if(!this.lastLayout)return;this.applyLayout(this.lastLayout);this.lastLayout=null;$('ui7UndoLayout').hidden=true;$('ui7ProfileMessage').textContent=this.tr('Previous layout restored.','Прежнее оформление восстановлено.');};this.syncProfiles();
  },
  syncProfiles(){
    const key38=JSON.stringify([S.noAnim,S.compact,Studio.prefs(),Workspace.prefs()]);if(this._profilesKey38===key38)return;this._profilesKey38=key38;
    document.querySelectorAll('[data-profile]').forEach(b=>{
      const p=this.profileValues(b.dataset.profile),studio=Studio.prefs(),ws=Workspace.prefs();
      const active=!!S.noAnim===p.noAnim&&!!S.compact===p.compact&&Object.entries(p.workspace).every(([k,v])=>ws[k]===v)&&Object.entries(p.studio).every(([k,v])=>studio[k]===v);
      b.classList.toggle('on',active);b.setAttribute('aria-pressed',String(active));
    });
  },
  backup(){
    const block=el('section','ui7-backup');block.innerHTML=`<div><h3 data-ui-i18n>${this.tr('Take your layout with you','Сохрани свой интерфейс')}</h3><p data-ui-i18n>${this.tr('A local JSON file. No music, accounts, tokens or file paths.','Локальный JSON-файл. Без музыки, аккаунтов, токенов и путей к файлам.')}</p></div><div class="ui7-backup-actions" id="ui7BackupActions"></div><input id="ui7LayoutFile" type="file" accept="application/json,.json" hidden><p id="ui7ImportStatus" role="status" data-ui-i18n></p>`;
    document.querySelector('.pane[data-pane=workspace]').appendChild(block);
    const acts=$('ui7BackupActions');acts.append(this.button(this.tr('Export layout','Сохранить в файл'),'import',()=>this.exportLayout()),this.button(this.tr('Import layout','Загрузить из файла'),'lib',()=>$('ui7LayoutFile').click()));
    $('ui7LayoutFile').onchange=async e=>{
      const file=e.target.files[0];if(!file)return;
      try{if(file.size>200000)throw Error(this.tr('File is too large (200 KB maximum)','Файл слишком большой: максимум 200 КБ'));const data=this.validateLayout(JSON.parse(await file.text()));
        Workspace.confirm(this.tr('Apply this layout?','Применить оформление из файла?'),this.tr('Only theme and interface preferences will change. Music, accounts and sound stay unchanged.','Изменятся только тема и интерфейс. Музыка, аккаунты и звук останутся без изменений.'),()=>{this.importLayout(data);toast(this.tr('Layout imported','Оформление загружено'));});
      }catch(err){$('ui7ImportStatus').textContent=this.tr('Could not import: ','Не удалось загрузить: ')+(err.message||'JSON');}finally{e.target.value='';}
    };
  },
  exportData(){
    const ws=Workspace.prefs(),st=Studio.prefs();return {format:'kryonyx-layout',version:1,theme:S.theme,noAnim:!!S.noAnim,compact:!!S.compact,workspace:{compactPlayer:!!ws.compactPlayer,sidebarCollapsed:!!ws.sidebarCollapsed,recent:!!ws.recent,libraryLayout:ws.libraryLayout},studio:{density:st.density,cards:st.cards,hero:!!st.hero,quick:!!st.quick},favorites:this.favorites()};
  },
  validateLayout(data){
    const invalid=()=>{throw Error(this.tr('Unsupported or invalid layout file','Неподдерживаемый или повреждённый файл оформления'));};
    if(!data||data.format!=='kryonyx-layout'||data.version!==1||!Object.hasOwn(THEME_LIBRARY,data.theme))invalid();
    const boolean=v=>{if(typeof v!=='boolean')invalid();return v;},ws=data.workspace,st=data.studio;if(!ws||!st)invalid();
    if(!['grid','list'].includes(ws.libraryLayout)||!['comfortable','compact'].includes(st.density)||!Number.isInteger(st.cards)||st.cards<150||st.cards>240)invalid();
    if(!Array.isArray(data.favorites)||data.favorites.length>40||data.favorites.some(x=>typeof x!=='string'||x.length>160))invalid();
    // Whitelist only. Unknown properties and all account/path/audio fields are ignored.
    return {format:'kryonyx-layout',version:1,theme:data.theme,noAnim:boolean(data.noAnim),compact:boolean(data.compact),workspace:{compactPlayer:boolean(ws.compactPlayer),sidebarCollapsed:boolean(ws.sidebarCollapsed),recent:boolean(ws.recent),libraryLayout:ws.libraryLayout},studio:{density:st.density,cards:st.cards,hero:boolean(st.hero),quick:boolean(st.quick)},favorites:data.favorites.filter(x=>this.rows.has(x))};
  },
  importLayout(data){
    const safe=this.validateLayout(data);useTheme(safe.theme);S.ui7={favorites:safe.favorites};this.applyLayout(safe);this.paintFavorites();$('ui7ImportStatus').textContent=this.tr('Layout applied. Sound and accounts unchanged.','Оформление применено. Звук и аккаунты не изменились.');
  },
  async exportLayout(){
    const result=await FileSave27.save({kind:'layout',name:'Kryo-layout.json',text:JSON.stringify(this.exportData(),null,2)});
    if(result?.saved)$('ui7ImportStatus').textContent=t('Saved to the selected file');
  },
  sectionLinks(){
    const bar=el('nav','ui7-section-links');bar.id='ui7SectionLinks';bar.setAttribute('aria-label',this.tr('Jump within settings','Переход внутри раздела'));$('uiSettingsSearchInfo').before(bar);this.paintSectionLinks('workspace');
  },
  paintSectionLinks(name){
    const bar=$('ui7SectionLinks');if(!bar)return;bar.replaceChildren();const pane=document.querySelector(`.set-body>.pane[data-pane="${CSS.escape(name)}"]`);if(!pane)return;
    const headings=[...pane.querySelectorAll('h4')];bar.hidden=headings.length<2;
    headings.slice(0,10).forEach(h=>bar.appendChild(this.button(h.textContent,'',()=>h.scrollIntoView({block:'start',behavior:S.noAnim?'instant':'smooth'}),'ui7-section-link')));
  },
  safety(){
    const list=[['bClearAudio','Clear audio cache?','Очистить аудиокэш?','Only cached audio on this device is removed.','Будет очищен только аудиокэш устройства.'],['bClearHistory','Clear listening history?','Очистить историю прослушиваний?','Listening history and local taste data will be removed. This cannot be undone.','История и локальные предпочтения будут удалены. Отменить это действие нельзя.'],['bClearSearch','Clear search history?','Очистить историю поиска?','Previous queries will be removed. This cannot be undone.','Предыдущие запросы будут удалены. Отменить это действие нельзя.'],['bResetSettings','Reset all settings?','Сбросить все настройки?','Theme, sound and source preferences return to defaults. Make a layout backup first if needed.','Тема, звук и источники вернутся к значениям по умолчанию. При необходимости сначала сохраните оформление.']];
    list.forEach(([id,en,ru,de,dr])=>{const b=$(id),action=b.onclick;b.classList.add('ui7-danger');b.onclick=()=>Workspace.confirm(this.tr(en,ru),this.tr(de,dr),async()=>{await action();this.syncProfiles();this.paintFavorites();});});
  },
  sleep(){
    const b=this.button(this.tr('Sleep timer','Таймер сна'),'clock',()=>this.openSleep(),'ib');b.id='ui7Sleep';$('pRight').insertBefore(b,$('workspacePlayerMore'));
    const sound=document.querySelector('.pane[data-pane=sound]');const row=el('div','set ui7-sleep-setting',`<div><div class="l" data-ui-i18n>${this.tr('Sleep timer','Таймер сна')}</div><div class="h" id="ui7SleepText" data-ui-i18n>${this.tr('Pause music after 15, 30 or 60 minutes. This session only.','Пауза через 15, 30 или 60 минут. Только в этом сеансе.')}</div></div>`);row.appendChild(this.button(this.tr('Set timer','Настроить'),'clock',()=>this.openSleep()));sound.appendChild(row);
    const menu=Workspace.playerMenu.bind(Workspace);Workspace.playerMenu=e=>{menu(e);const b=this.button(this.tr('Sleep timer','Таймер сна'),'clock',()=>{hideMenu();this.openSleep();},'');$('ctxMenu').appendChild(b);};
    setInterval(()=>this.tickSleep(),1000);addEventListener('visibilitychange',()=>this.tickSleep());
  },
  openSleep(){
    const body=el('div','workspace-dialog-body ui7-sleep-body',`<p data-ui-i18n>${this.tr('The timer pauses music, not the computer. It resets when you close the app.','Таймер поставит музыку на паузу, но не выключит компьютер. После закрытия приложения он сбросится.')}</p><div id="ui7SleepChoices" class="ui7-sleep-choices"></div><p id="ui7SleepDialogStatus" role="status" data-ui-i18n></p>`);
    Workspace.dialog('mSleep7',this.tr('Fall asleep to music','Засыпай под музыку'),body);
    [15,30,60].forEach(min=>$('ui7SleepChoices').appendChild(this.button(min+' '+this.tr('min','мин'),'clock',()=>{this.setSleep(min);this.tickSleep();},'ui7-sleep-choice')));
    body.appendChild(this.button(this.tr('Turn timer off','Выключить таймер'),'close',()=>this.setSleep(0)));
    this.tickSleep();$('ui7SleepChoices').querySelector('button')?.focus();
  },
  setSleep(minutes){
    if(![0,15,30,60].includes(minutes))return;
    this.sleepDeadline=minutes?Date.now()+minutes*60000:0;this.tickSleep();
  },
  tickSleep(){
    if(this.sleepDeadline&&Date.now()>=this.sleepDeadline){
      this.sleepDeadline=0;Player.wantPlay=false;Player.xfToken++;Player.xfFrom=null;
      Player.deck.forEach(deck=>{deck.pause();deck.volume=S.volume/100;});Player.paintState();Player.saveState();toast(this.tr('Sleep timer · music paused','Таймер сна · музыка на паузе'));
    }
    const active=!!this.sleepDeadline;const remaining=Math.max(0,Math.ceil((this.sleepDeadline-Date.now())/1000));
    const status=active?this.tr('Music pauses in ','Музыка остановится через ')+fmt(remaining):this.tr('Timer is off','Таймер выключен');
    $('ui7Sleep')?.classList.toggle('on',active);$('ui7Sleep')?.setAttribute('aria-label',status);$('ui7Sleep')?.setAttribute('title',status);
    if($('ui7SleepDialogStatus'))$('ui7SleepDialogStatus').textContent=status;
    if($('ui7SleepText'))$('ui7SleepText').textContent=active?status:this.tr('Pause after 15, 30 or 60 minutes. This session only.','Пауза через 15, 30 или 60 минут. Только в этом сеансе.');
  },
  home(){
    const resume=$('workspaceResume');if(resume)resume.onclick=()=>{if(Player.current&&!Player.audio.paused)App.openNow();else Player.toggle();};
    const paint=Workspace.paintPlayer.bind(Workspace);Workspace.paintPlayer=()=>{paint();if(resume)resume.onclick=()=>{if(Player.current&&!Player.audio.paused)App.openNow();else Player.toggle();};};
    const hero=$('studioHero');if(hero)hero.classList.add('ui7-hero');
  },
  library(){
    const tools=document.querySelector('.workspace-library-tools');const tabs=el('div','ui7-library-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label',this.tr('Library filter','Фильтр медиатеки'));
    [[false,'All playlists','Все плейлисты'],[true,'Pinned','Закреплённые']].forEach(([p,en,ru])=>{const b=this.button(this.tr(en,ru),p?'lyrics':'lib',()=>{$('workspacePinnedOnly').checked=p;$('workspacePinnedOnly').dispatchEvent(new Event('change',{bubbles:true}));this.paintLibraryTabs();},'chip');b.dataset.pinnedTab=String(p);tabs.appendChild(b);});tools.before(tabs);
    const original=Workspace.renderLibrary.bind(Workspace);Workspace.renderLibrary=()=>{original();this.paintLibraryTabs();
      if(!K.playlists.length&&!Workspace.libraryPinned&&!Workspace.libraryQuery){
        const box=el('div','ui7-library-onboarding',`${icon('lib')}<div><h2 data-ui-i18n>${this.tr('Make room for your favourites','Собери то, что любишь')}</h2><p data-ui-i18n>${this.tr('Create a playlist or transfer one you already have.','Создай плейлист или перенеси уже существующий.')}</p></div><div class="ui7-library-onboarding-actions" id="ui7LibStart"></div>`);$('libG').prepend(box);
        $('ui7LibStart').append(this.button(this.tr('Create playlist','Создать плейлист'),'plus',()=>$('bNewPl').click(),'btn'),this.button(this.tr('Transfer playlist','Перенести плейлист'),'import',()=>document.querySelector('[data-convert-open]').click()));
      }
    };this.paintLibraryTabs();
  },
  paintLibraryTabs(){document.querySelectorAll('[data-pinned-tab]').forEach(b=>b.setAttribute('aria-pressed',String(Workspace.libraryPinned===(b.dataset.pinnedTab==='true'))));},
  search(){
    const original=Studio.searchSummary.bind(Studio);Studio.searchSummary=(tracks,done)=>{original(tracks,done);this.paintSearchChips();};
    const chips=el('div','ui7-search-chips');chips.id='ui7SearchChips';$('studioBest').before(chips);
    const update=App.go.bind(App);App.go=(...args)=>{update(...args);document.body.classList.toggle('ui7-searching',K.view==='search');};
  },
  paintSearchChips(){
    const box=$('ui7SearchChips');if(!box)return;box.replaceChildren();
    [['source','studioSource'],['duration','studioDuration'],['liked','studioLiked']].forEach(([key,id])=>{
      if(!Studio.search[key])return;const field=$(id),label=key==='liked'?this.tr('Favourites','Любимые'):field.selectedOptions?.[0]?.textContent||Studio.search[key];
      const b=this.button(label+' ×','',()=>{if(key==='liked')field.checked=false;else field.value='';field.dispatchEvent(new Event('change',{bubbles:true}));},'ui7-filter-chip');b.setAttribute('aria-label',this.tr('Remove filter: ','Убрать фильтр: ')+label);box.appendChild(b);
    });box.hidden=!box.children.length;
  },
  queue(){
    const card=el('div','ui7-queue-current');card.id='ui7QueueCurrent';$('queue').querySelector('header').after(card);
    const tabs=el('div','ui7-queue-tabs');tabs.id='ui7QueueTabs';tabs.setAttribute('role','group');tabs.setAttribute('aria-label',this.tr('Queue scope','Показать в очереди'));
    [['next','Up next','Далее'],['all','Full queue','Вся очередь']].forEach(([key,en,ru])=>{const b=this.button(this.tr(en,ru),'',()=>{this.queueMode=key;Workspace.filterQueue();},'chip');b.dataset.queueMode=key;tabs.appendChild(b);});$('queueList').before(tabs);
    const empty=el('div','ui7-empty');empty.id='ui7QueueEmpty';empty.hidden=true;empty.setAttribute('role','status');$('queueList').after(empty);
    const original=Views.renderQueue.bind(Views);Views.renderQueue=()=>{original();this.paintQueue();};
    Workspace.filterQueue=()=>{
      const q=Workspace.queueQuery.toLocaleLowerCase();let shown=0;
      $('queueList').querySelectorAll('.tr').forEach(row=>{const at=+row.dataset.at,track=Player.queue[at];row.hidden=(this.queueMode==='next'&&Player.current&&at<=Player.index)||!!q&&!((track?.title||'')+' '+(track?.artist||'')).toLocaleLowerCase().includes(q);if(!row.hidden)shown++;});
      empty.hidden=!!shown||!Player.queue.length;empty.replaceChildren();
      if(!shown&&Player.queue.length){const title=el('strong');title.textContent=q?this.tr('No matching tracks','Подходящих треков нет'):this.tr('Nothing queued next','Далее пока пусто');empty.appendChild(title);if(q)empty.appendChild(this.button(this.tr('Clear search','Сбросить поиск'),'close',()=>{$('workspaceQueueFilter').value='';Workspace.queueQuery='';Workspace.filterQueue();}));else empty.appendChild(this.button(this.tr('Find more music','Найти ещё музыку'),'search',()=>{closeModals();App.go('search');}));}
      document.querySelectorAll('[data-queue-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.queueMode===this.queueMode)));
    };
    const summary=Workspace.queueRendered.bind(Workspace);Workspace.queueRendered=()=>{summary();this.paintQueueCurrent();};
    this.paintQueue();
  },
  paintQueue(){this.paintQueueCurrent();Workspace.filterQueue();},
  paintQueueCurrent(){
    const card=$('ui7QueueCurrent');if(!card)return;card.replaceChildren();card.hidden=!Player.current;if(!Player.current)return;
    const track=Player.current,img=el('img');img.alt='';setImg(img,track.thumbnail,100);img.loading='eager';
    const copy=el('div'),label=el('small'),title=el('strong'),artist=el('span');label.textContent=this.tr(Player.audio.paused?'READY TO PLAY':'NOW PLAYING',Player.audio.paused?'ГОТОВО К ЗАПУСКУ':'СЕЙЧАС ИГРАЕТ');title.textContent=track.title;artist.textContent=track.artist||'';label.dataset.uiI18n='';[title,artist].forEach(n=>n.dataset.entityName='');copy.append(label,title,artist);
    card.append(img,copy,this.button(this.tr('Open player','Открыть плеер'),'expand',()=>{closeModals();App.openNow();},'ib'));
  }
};
