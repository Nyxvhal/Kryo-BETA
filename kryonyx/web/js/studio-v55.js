/* v53 / Forma. Structural UI exploration on the real application engines.
   Preserves media controls, settings controls, data APIs and karaoke. No animation loop. */
'use strict';
const UI53={
 ready:false,
 tr(en,ru){return LANG==='ru'?ru:en;},
 n(tag,cls,text){return UI52.node(tag,cls,text);},
 b(label,ico,fn,cls='button53'){const b=this.n('button',cls,label);b.type='button';b.dataset.noI18n='';if(ico)b.prepend(UI52.icon(ico));b.onclick=fn;return b;},
 init(){if(this.ready)return;this.ready=true;document.body.classList.add('ui-v53');this.shell();this.home();this.settings();this.clips();this.labels();
 const oldRender=Home31.render.bind(Home31);Home31.render=(...a)=>{const r=oldRender(...a);this.paintHome();return r;};
 const oldLabels=UI52.homeLabels.bind(UI52);UI52.homeLabels=(...a)=>{const r=oldLabels(...a);this.labels();return r;};
 const oldAppearance=UI52.renderAppearance.bind(UI52);UI52.renderAppearance=(...a)=>{const r=oldAppearance(...a);this.arrangeAppearance();return r;};
 const oldSettings=UI52.renderSettings.bind(UI52);UI52.renderSettings=(...a)=>{const r=oldSettings(...a);this.settingsHome();return r;};
 const oldOpen=App.openPane.bind(App);App.openPane=(name)=>{const r=oldOpen(name);this.settingsActive(name);return r;};
 const lang=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const r=lang(...a);this.labels();this.navSettings();this.settingsHome();this.arrangeAppearance();this.paintHome();return r;};
 this.paintHome();
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('collection53')?.classList.contains('on'))this.closeCollection();});
 },
 shell(){
 const brand=$('side').querySelector('.brand');brand.title='Kryo';brand.setAttribute('aria-label','Kryo');
 const first=$('side').querySelector('.side-h'),drawer=this.n('aside','collection53');drawer.id='collection53';drawer.setAttribute('aria-label',this.tr('Your playlists','Твои плейлисты'));const head=this.n('header');head.append(this.n('h2','',this.tr('Your collection','Твоя коллекция')),this.b(this.tr('Close','Закрыть'),'close',()=>this.closeCollection(),'ib'));drawer.append(head);
 for(const n of [first,$('side').querySelector('.workspace-side-filter'),$('sidePl'),$('workspaceCreatePlaylist')||$('side').querySelector('.workspace-create-playlist')])if(n)drawer.append(n);
 // Move the actual existing controls, not their clones. Collection actions keep their listeners.
 for(const n of [...$('side').children])if(n.className?.includes('playlist')||n.classList?.contains('workspace-side-filter'))drawer.append(n);
 const open=this.b(this.tr('Playlists','Плейлисты'),'queue',()=>this.toggleCollection(),'nav collection-toggle53');open.id='collectionToggle53';open.setAttribute('aria-expanded','false');$('sideMore31').before(open);$('app').append(drawer);
 const space=this.n('div','rail-space53');$('navSettings').before(space);$('personalize52').title=this.tr('Appearance','Оформление');
 const label=this.n('div','brandline53');label.dataset.noI18n='';label.innerHTML='<strong>KRYO</strong><span>'+this.tr('music, without the noise','музыка. ничего лишнего.')+'</span>';$('workspaceNavBar').prepend(label);
 const chip=this.b(this.tr('Your space','Твоё пространство'),'palette',()=>{Workspace.openSettings();App.openPane('appearance52');},'profile53');chip.id='profile53';$('workspaceNavBar').append(chip);
 const go=App.go.bind(App);App.go=(route,...a)=>{this.closeCollection();return go(route,...a);};
 // Put the timeline at the top of the floating transport instead of a second full-width toolbar.
 const mobile=$('workspaceMobileControls'),more=mobile?.lastElementChild;if(more){more.id='mobileMore53';$('pBtns').append(more);}if(mobile)mobile.hidden=true;
 const line=$('pCtl').querySelector('.bar');line.classList.add('timeline53');$('player').prepend(line);$('pCtl').classList.add('transport53');
 },
 toggleCollection(){const on=!$('collection53').classList.contains('on');$('collection53').classList.toggle('on',on);$('collectionToggle53').setAttribute('aria-expanded',String(on));if(on)$('collection53').querySelector('input,button')?.focus();},
 closeCollection(){$('collection53')?.classList.remove('on');$('collectionToggle53')?.setAttribute('aria-expanded','false');},
 home(){
 const root=$('vHome'),head=$('homeHead31');head.classList.add('hero53');const art=this.n('div','hero-art53');art.setAttribute('aria-hidden','true');art.innerHTML='<img id="heroArt53" alt=""><span class="hero-art-caption53">KRYO / DAILY MIX</span>';head.append(art);
 const count=$('homeCount31');count.classList.add('hero-count53');$('homeLede52').after(count);const acts=head.querySelector('.home-actions31');head.firstElementChild.append(acts);
 const filter=this.n('details','filter53');filter.id='filter53';const sum=this.n('summary');sum.append(UI52.icon('mixer'),document.createTextNode(this.tr('Fine-tune','Подстроить под себя')));filter.append(sum);const inner=this.n('div','filter-body53');for(const n of [$('homeSourceLabel31'),$('homeSource31'),$('homeFilter31').querySelector('.categories52'),$('homeFilter31').querySelector('.taste52'),$('homeFilter31').querySelector('.btn')])if(n)inner.append(n);filter.append(inner);
 const tools=$('homeFilter31');tools.append(filter);$('homeRefresh31').title=this.tr('Refresh recommendations','Обновить рекомендации');tools.append($('homeRefresh31'));
 const heading=this.n('div','section-head53');heading.id='picksHeading53';heading.append(this.n('div','',this.tr('Selected for you','Под твой ритм')),this.n('span','',this.tr('From your recommendations','Из твоих рекомендаций')));$('rows').before(heading);
 const quick=this.n('section','quick53');quick.id='quick53';quick.append(this.n('header','',this.tr('Press play','Сразу к музыке')));quick.append(this.n('div','quick-list53'));head.after(quick);
 },
 paintHome(){if(!this.ready)return;const list=Home31.groups38.tracks||[];const first=list[0];const img=$('heroArt53');if(first?.thumbnail&&img.getAttribute('src')!==first.thumbnail)img.src=first.thumbnail;img.hidden=!first?.thumbnail;
 const box=$('quick53').querySelector('.quick-list53');box.replaceChildren();for(const [i,track]of list.slice(0,3).entries()){const b=this.b('','',()=>Player.play(track,list,i),'quick-track53');b.title=this.tr('Play ','Включить ')+track.title;const image=this.n('img');image.src=track.thumbnail||'/icon.png';image.alt='';const meta=this.n('span');meta.append(this.n('strong','',track.title),this.n('small','',track.artist||''));b.append(this.n('span','quick-index53',String(i+1).padStart(2,'0')),image,meta,UI52.icon('play'));box.append(b);}
 $('quick53').hidden=!list.length;
 },
 labels(){if(!this.ready)return;$('homeTitle31').textContent=this.tr('Your music.\nYour moment.','Твоя музыка.\nТвой момент.');$('homeLede52').textContent=this.tr('A familiar favourite or something completely new. Just press play.','Знакомое любимое или что-то совсем новое. Просто нажми play.');$('homeHead31').querySelector('.home-kicker31').textContent=this.tr('MADE FOR YOUR EVERYDAY','НА КАЖДЫЙ ТВОЙ ДЕНЬ');$('homePlay31').querySelector('span').textContent=this.tr('Play my mix','Включить мой микс');const profile=$('profile53');if(profile){profile.replaceChildren(UI52.icon('palette'));profile.setAttribute('aria-label',this.tr('Your space','Твоё пространство'));profile.title=this.tr('Your space','Твоё пространство');}const bl=document.querySelector('.brandline53');if(bl){bl.querySelector('strong').textContent='KRYO';bl.querySelector('span').textContent=this.tr('music, without the noise','музыка. ничего лишнего.');}const summary=$('filter53')?.querySelector('summary');if(summary){summary.replaceChildren(UI52.icon('mixer'),document.createTextNode(this.tr('Fine-tune','Подстроить под себя')));}if($('quick53'))$('quick53').querySelector('header').textContent=this.tr('Press play','Сразу к музыке');if($('picksHeading53')){$('picksHeading53').firstChild.textContent=this.tr('Selected for you','Под твой ритм');$('picksHeading53').lastChild.textContent=this.tr('From your recommendations','Из твоих рекомендаций');}$('homeRefresh31').querySelector('span').textContent=this.tr('Refresh','Обновить');$('heroArt53').alt='';if($('collectionToggle53'))$('collectionToggle53').lastChild.textContent=this.tr('Playlists','Плейлисты');
 },
 settings(){
 const shell=$('mSettings').querySelector('.set-shell'),nav=this.n('nav','settings-nav53');nav.id='settingsNav53';nav.setAttribute('aria-label',this.tr('Settings sections','Разделы настроек'));shell.prepend($('mSettings').querySelector('.workspace-settings-head'),nav);this.navSettings();const find=$('setFind').closest('.set-find');if(find){find.classList.add('find53');shell.querySelector('.workspace-settings-head').append(find);}
 this.settingsHome();this.arrangeAppearance();
 for(const id of ['navSettings','bSettings','mobSettings'])$(id).addEventListener('click',()=>{Workspace.openSettings();App.openPane('appearance52');});
 },
 navSettings(){const nav=$('settingsNav53');if(!nav)return;nav.replaceChildren();for(const [name,en,ru,ico]of [['appearance52','Appearance','Оформление','palette'],['sound','Sound','Звук','vol'],['lib','Sources','Источники','radio'],['profile50','My taste','Мой вкус','heart'],['importPane','Transfer','Перенос','import'],['karaoke','Karaoke','Караоке','lyrics']]){const b=this.b(this.tr(en,ru),ico,()=>{UI52.clearFind();App.openPane(name);},'settings-nav-item53');b.dataset.section53=name;nav.append(b);}
 const more=this.n('label','settings-more53');more.append(this.n('span','',this.tr('Other settings','Остальные настройки')));const select=this.n('select');select.id='settingsMore53';select.setAttribute('aria-label',this.tr('Other settings','Остальные настройки'));select.add(new Option(this.tr('More…','Ещё…'),''));for(const tab of $('setTabs').querySelectorAll('[data-pane]'))select.add(new Option(tab.textContent.trim(),tab.dataset.pane));select.onchange=()=>{if(select.value){UI52.clearFind();App.openPane(select.value);select.value='';}};more.append(select);nav.append(more);
 },
 settingsActive(name){const root=$('mSettings'),shell=root.querySelector('.set-shell'),head=root.querySelector('.workspace-settings-head'),find=$('setFind').closest('.set-find');if(name==='karaoke'){root.insertBefore(head,shell);if(find)$('setTabs').prepend(find);}else{shell.prepend(head,$('settingsNav53'));if(find)head.append(find);}for(const n of document.querySelectorAll('[data-section53]'))n.setAttribute('aria-current',n.dataset.section53===name?'page':'false');},
 settingsHome(){const pane=document.querySelector('.pane[data-pane=settings52]');pane.replaceChildren();const header=this.n('header','settings-intro53');header.append(this.n('span','eyebrow52',this.tr('CONTROL CENTRE','ЦЕНТР УПРАВЛЕНИЯ')),this.n('h2','',this.tr('A space that feels like you.','Место, где всё по-твоему.')),this.n('p','',this.tr('Choose what to change. Your music and collections stay where they are.','Выбери, что изменить. Музыка и коллекции останутся на месте.')));pane.append(header);
 const list=this.n('div','settings-list53');for(const [name,en,ru,desc,descr,ico]of [['appearance52','Make it yours','Сделать своим','Palette, proportions, layout','Палитра, размеры и компоновка','palette'],['sound','Find your sound','Найти своё звучание','Equalizer and playback','Эквалайзер и воспроизведение','vol'],['lib','Connect your music','Подключить музыку','Sources and libraries','Источники и библиотеки','radio'],['profile50','Bring your taste','Перенести свой вкус','Favourites and music history','Избранное и музыкальная история','heart'],['keys','Move faster','Меньше лишних действий','Keyboard shortcuts','Быстрые клавиши','keyboard']]){const b=this.b('','',()=>App.openPane(name),'settings-command53'),meta=this.n('span');meta.append(this.n('strong','',this.tr(en,ru)),this.n('small','',this.tr(desc,descr)));b.append(UI52.icon(ico),meta,UI52.icon('next'));list.append(b);}pane.append(list);},
 arrangeAppearance(){const pane=document.querySelector('.pane[data-pane=appearance52]');if(pane.querySelector('.appearance-workspace53'))return;const intro=pane.querySelector('.intro52');intro.querySelector('h2').textContent=this.tr('Make room for your style.','Пусть здесь будет по-твоему.');intro.querySelector('p').textContent=this.tr('Change the way it looks. Not the way you love karaoke.','Меняй оформление и удобство. Караоке останется привычным.');
 const workspace=this.n('div','appearance-workspace53'),aside=this.n('aside','appearance-stage53'),form=this.n('div','appearance-form53');const preview=$('appearancePreview52');aside.append(this.n('span','eyebrow52',this.tr('LIVE PREVIEW','ТАК БУДЕТ ВЫГЛЯДЕТЬ')),preview);const legend=this.n('div','preview-caption53');legend.append(this.n('strong','',this.tr('Your own listening room','Твоя личная музыкальная комната')),this.n('p','',this.tr('Colours, controls and proportions change instantly.','Цвета, элементы и пропорции меняются сразу.')));aside.append(legend);
 // The preview now uses actual cover assets from the current recommendations.
 const images=preview.querySelectorAll('.preview-cards52 i');for(const [i,n]of [...images].entries()){const t=Home31.groups38.tracks[i];if(t?.thumbnail){const image=this.n('img');image.src=t.thumbnail;image.alt='';n.replaceChildren(image);}}
 for(const n of [...pane.children])if(n!==intro)form.append(n);workspace.append(aside,form);pane.append(workspace);
 },
 clips(){const root=$('clips');root.classList.add('cinema53');const layout=root.querySelector('.cs-layout'),sidebar=root.querySelector('.cs-sidebar'),main=root.querySelector('.cs-main');sidebar.classList.add('filmstrip53');layout.append(sidebar);
 const tools=main.querySelector('.clip-details45');if(tools){tools.classList.add('tools-drawer53');tools.open=false;const sum=tools.querySelector('summary');sum.innerHTML=icon('mixer','ic s')+' '+this.tr('Playback & downloads','Просмотр и загрузка');}
 const intro=$('clipEmpty');intro.querySelector('b').textContent=this.tr('Music.\nIn a different light.','Музыка.\nВ другом свете.');intro.querySelector('span').textContent=this.tr('Open a video link or pick a track from your queue.','Открой ссылку на клип или выбери трек из очереди.');
 const top=root.querySelector('.cs-head');top.querySelector('h1').textContent=this.tr('Watch','Смотреть');top.querySelector('.cs-eyebrow').textContent='KRYO / CINEMA';
 const oldLabels=UI52.clipLabels.bind(UI52);UI52.clipLabels=(...a)=>{const r=oldLabels(...a);intro.querySelector('b').textContent=this.tr('Music.\nIn a different light.','Музыка.\nВ другом свете.');intro.querySelector('span').textContent=this.tr('Open a video link or pick a track from your queue.','Открой ссылку на клип или выбери трек из очереди.');top.querySelector('h1').textContent=this.tr('Watch','Смотреть');top.querySelector('.cs-eyebrow').textContent='KRYO / CINEMA';return r;};
 }
};
const boot53=App.boot.bind(App);App.boot=async function(...a){await boot53(...a);UI53.init();};

/* v54: compact listening-first surfaces, optional track list and usable filters.
   All playback/data actions are the existing application actions. */
'use strict';
const UI54={
 ready:false,
 tr(en,ru){return UI53.tr(en,ru)},
 init(){if(this.ready)return;this.ready=true;document.body.classList.add('ui-v54');
 const labels=UI53.labels.bind(UI53);UI53.labels=(...a)=>{const r=labels(...a);this.labels();return r};
 const paint=UI53.paintHome.bind(UI53);UI53.paintHome=(...a)=>{const r=paint(...a);this.cards();return r};
 const appearance=UI53.arrangeAppearance.bind(UI53);UI53.arrangeAppearance=(...a)=>{const r=appearance(...a);this.preview();return r};
 const acts=$('homeHead31').querySelector('.home-actions31');const search=UI53.b('','search',()=>App.go('search'),'hero-search54');search.id='heroSearch54';acts.append(search);
 const view=UI53.n('div','view-switch54');view.setAttribute('role','group');view.id='viewSwitch54';for(const [mode,en,ru]of [['grid','Cards','Карточки'],['list','List','Список']]){const b=UI53.b(this.tr(en,ru),'',()=>this.setView(mode));b.dataset.view54=mode;view.append(b)}$('homeFilter31').insertBefore(view,$('filter53'));
 this.setView(localStorage.getItem('kryonyx-home-view54')==='list'?'list':'grid');
 const filter=$('filter53');filter.addEventListener('toggle',()=>filter.querySelector('summary').setAttribute('aria-expanded',String(filter.open)));
 document.addEventListener('pointerdown',e=>{if(filter.open&&!filter.contains(e.target))filter.open=false});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&filter.open){filter.open=false;filter.querySelector('summary').focus();e.stopPropagation()}});
 const settingsHead=$('mSettings').querySelector('.workspace-settings-head');const searchSettings=UI53.b('','search',()=>{settingsHead.classList.toggle('searching54');if(settingsHead.classList.contains('searching54'))$('setFind').focus();else UI52.clearFind()},'ib settings-search54');searchSettings.id='settingsSearch54';settingsHead.append(searchSettings);
 this.preview();this.labels();this.cards();const media=matchMedia('(max-width:560px)');const adapt=()=>{const v=$('viewSwitch54');if(media.matches)$('picksHeading53').insertBefore(v,$('picksHeading53').lastElementChild);else $('homeFilter31').insertBefore(v,$('filter53'));};adapt();media.addEventListener('change',adapt);const small=matchMedia('(max-width:900px)');small.addEventListener('change',()=>{const preview=document.querySelector('.appearance-preview54');if(preview)preview.open=!small.matches;});
 },
 setView(mode){document.body.dataset.homeView54=mode;localStorage.setItem('kryonyx-home-view54',mode);for(const b of document.querySelectorAll('[data-view54]'))b.setAttribute('aria-pressed',String(b.dataset.view54===mode))},
 labels(){if(!this.ready)return;
 $('homeTitle31').textContent=this.tr('Your day.\nYour music.','Твой день.\nТвоя музыка.');$('homeLede52').textContent=this.tr('Familiar favourites. New discoveries. A mix that feels like you.','Любимое и новые открытия — в миксе под твоё настроение.');
 $('heroSearch54').replaceChildren(UI52.icon('search'),document.createTextNode(this.tr('Find music','Найти музыку')));
 $('filter53').querySelector('summary').replaceChildren(UI52.icon('mixer'),document.createTextNode(this.tr('Filters','Фильтры')));
 $('quick53').querySelector('header').textContent=this.tr('One tap away','Быстрый старт');
 $('picksHeading53').firstChild.textContent=this.tr('Made for your rhythm','В твоём ритме');
 for(const b of document.querySelectorAll('[data-view54]'))b.textContent=this.tr(b.dataset.view54==='grid'?'Cards':'List',b.dataset.view54==='grid'?'Карточки':'Список');
 $('viewSwitch54').setAttribute('aria-label',this.tr('Track display','Отображение треков'));$('settingsSearch54').title=this.tr('Search settings','Поиск по настройкам');$('settingsSearch54').setAttribute('aria-label',$('settingsSearch54').title);
 const d=document.querySelector('.appearance-preview54');if(d)d.querySelector('summary').textContent=this.tr('Preview appearance','Предпросмотр оформления');
 },
 cards(){document.body.dataset.homeKind54=Home31.kind;$('viewSwitch54').hidden=Home31.kind!=='tracks';for(const card of document.querySelectorAll('#rows .card')){const title=card.querySelector('.t')?.textContent||'';card.setAttribute('aria-label',this.tr('Play: ','Включить: ')+title);card.querySelector('.play-fab')?.setAttribute('aria-hidden','true')}},
 preview(){const aside=document.querySelector('.appearance-stage53');if(!aside||aside.classList.contains('appearance-preview54'))return;const d=document.createElement('details');d.className='appearance-stage53 appearance-preview54';const sum=document.createElement('summary');sum.textContent=this.tr('Preview appearance','Предпросмотр оформления');const content=document.createElement('div');content.className='preview-content54';while(aside.firstChild)content.append(aside.firstChild);content.querySelector('.eyebrow52')?.remove();d.append(sum,content);d.open=matchMedia('(min-width:901px)').matches;aside.replaceWith(d);
 const intro=document.querySelector('[data-pane=appearance52] .intro52');intro.querySelector('h2').textContent=this.tr('Your style. Your comfort.','Твой стиль. Твоё удобство.');intro.querySelector('p').textContent=this.tr('Changes apply immediately and are saved automatically.','Изменения видны сразу и сохраняются автоматически.');
 }
};
const boot54=App.boot.bind(App);App.boot=async function(...a){await boot54(...a);UI54.init()};

/* Studio / v55. Listening-first composition; no media engine replacement. */
'use strict';
const UI55={
 ready:false,
 tr(en,ru){return UI53.tr(en,ru)},
 init(){if(this.ready)return;this.ready=true;document.body.classList.add('ui-v55');
 const originalView=UI54.setView.bind(UI54);UI54.setView=(mode)=>{const y=$('scroll').scrollTop;originalView(mode);requestAnimationFrame(()=>{$('scroll').scrollTop=y;});};
 const originalTitle=$('homeTitle31');if(originalTitle.tagName==='H1'){const title=document.createElement('h2');for(const a of originalTitle.attributes)title.setAttribute(a.name,a.value);title.textContent=originalTitle.textContent;originalTitle.replaceWith(title);}
 const root=$('vHome'),welcome=UI53.n('header','welcome55');welcome.id='welcome55';const text=UI53.n('div');text.append(UI53.n('h1','',this.tr('For you','Для тебя')),UI53.n('p','',this.tr('Good music. Nothing in the way.','Хорошая музыка. Ничего лишнего.')));welcome.append(text,$('heroSearch54'));root.prepend(welcome);
 const shelf=UI53.n('div','home-shelf55');shelf.id='homeShelf55';$('homeHead31').before(shelf);shelf.append($('homeHead31'));
 const collection=UI53.n('section','collection-home55');collection.id='collectionHome55';collection.append(UI53.n('h2','',this.tr('Your collection','Твоя коллекция')));for(const [id,ico,fn]of [['liked','heart',()=>App.openLiked()],['playlists','lib',()=>App.go('lib')],['history','clock',()=>App.openHistory()]]){const b=UI53.b('',ico,fn,'collection-link55');b.dataset.collection55=id;b.append(UI53.n('span','collection-label55'),UI53.n('span','collection-count55'));collection.append(b);}shelf.append(collection);
 const side=$('side');for(const [before,id]of [[side.querySelector('[data-nav=home]'),'listen55'],[$('collectionToggle53'),'space55']])if(before){const label=UI53.n('div','side-section55');label.id=id;before.before(label)}
 const more=$('sideMore31');const pop=UI53.n('div','tools-pop55');for(const n of [...more.children])if(n.tagName!=='SUMMARY')pop.append(n);more.append(pop);
 const originalLabels=UI54.labels.bind(UI54);UI54.labels=(...a)=>{const r=originalLabels(...a);this.labels();return r};
 const originalPaint=Workspace.paintState.bind(Workspace);Workspace.paintState=(...a)=>{const r=originalPaint(...a);this.counts();return r};
 const originalHome=UI54.cards.bind(UI54);UI54.cards=(...a)=>{const r=originalHome(...a);this.counts();return r};
 const oldLanguage=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const r=oldLanguage(...a);this.labels();return r};
 // Keep focus on the trigger when dismissing the original playlist drawer.
 const close=UI53.closeCollection.bind(UI53);UI53.closeCollection=()=>{const active=$('collection53').contains(document.activeElement);close();if(active)$('collectionToggle53').focus({preventScroll:true})};
 document.addEventListener('pointerdown',e=>{if(more.open&&!more.contains(e.target))more.open=false});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&more.open){more.open=false;more.querySelector('summary').focus()}});
 const quick=$('quick53'),details=document.createElement('details'),summary=document.createElement('summary');details.id=quick.id;details.className=quick.className+' quick-disclosure55';summary.append(quick.querySelector('header'));details.append(summary,quick.querySelector('.quick-list53'));details.open=false;quick.replaceWith(details);this.labels();this.counts();
 },
 labels(){if(!this.ready)return;
 $('welcome55').querySelector('h1').textContent=this.tr('For you','Для тебя');$('welcome55').querySelector('p').textContent=this.tr('Good music. Nothing in the way.','Хорошая музыка. Ничего лишнего.');
 $('homeTitle31').textContent=this.tr('Your daily mix','Твой микс дня');$('homeLede52').textContent=this.tr('Favourites. And a little discovery.','Любимое. И немного нового.');$('homeHead31').querySelector('.home-kicker31').textContent=this.tr('PICKED FOR YOU','ПОДОБРАНО ДЛЯ ТЕБЯ');
 $('homePlay31').querySelector('span').textContent=this.tr('Play mix','Слушать микс');$('quick53').querySelector('header').textContent=this.tr('Ready when you are','Сразу слушать');$('picksHeading53').firstChild.textContent=this.tr('Worth a listen','Стоит послушать');$('picksHeading53').lastElementChild.textContent=this.tr('Selected for you','Подобрано для тебя');
 $('collectionHome55').querySelector('h2').textContent=this.tr('Your collection','Твоя коллекция');for(const [id,en,ru]of [['liked','Liked','Любимое'],['playlists','Playlists','Плейлисты'],['history','History','История']])document.querySelector('[data-collection55='+id+'] .collection-label55').textContent=this.tr(en,ru);
 if($('listen55'))$('listen55').textContent=this.tr('LISTEN','СЛУШАТЬ');if($('space55'))$('space55').textContent=this.tr('YOUR SPACE','ТВОЁ ПРОСТРАНСТВО');
 const brand=$('side').querySelector('.brand>span');if(brand){brand.dataset.noI18n='';brand.textContent='KRYO'}
 const line=document.querySelector('.brandline53');line.querySelector('strong').textContent=this.tr('Music, your way','Музыка по-твоему');line.querySelector('span').textContent='';
 this.counts();
 },
 counts(){if(!this.ready)return;const likes=K.likedTracks?.length??K.likes?.size??0;const playlists=K.playlists?.length??0;for(const [id,n]of [['liked',likes],['playlists',playlists],['history','→']]){const box=document.querySelector('[data-collection55='+id+'] .collection-count55');box.textContent=n;box.setAttribute('aria-label',id==='history'?this.tr('Open history','Открыть историю'):String(n))}}
};
const boot55=App.boot.bind(App);App.boot=async function(...a){await boot55(...a);UI55.init()};
