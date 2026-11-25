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
