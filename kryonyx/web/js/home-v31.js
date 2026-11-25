/* One recommendation surface. No per-track reloads or duplicate home widgets. */
'use strict';
const Home31={
 kind:'tracks',groups38:{tracks:[],albums:[],playlists:[]},timeoutMs36:30000,ready:false,items:[],limit:24,source:'all',busy:false,data:null,pending:null,
 init(){
  this.ready=true;document.body.classList.add('ui-v31');
  const head=el('header','home-head31');head.id='homeHead31';
  head.innerHTML=`<div><span class="home-kicker31" data-no-i18n>KRYO / MUSIC</span><h1 id="homeTitle31"></h1><p id="homeCount31" class="muted" data-no-i18n></p></div><div class="home-actions31"><button class="btn" id="homePlay31">${icon('play','ic s f')}<span></span></button><button class="btn g" id="homeRefresh31">${icon('refresh','ic s')}<span></span></button></div>`;
  const tools=el('div','home-filter31');tools.id='homeFilter31';tools.innerHTML='<label for="homeSource31" id="homeSourceLabel31"></label><select id="homeSource31"></select><span id="homeStatus31" role="status" aria-live="polite"></span>';
  const more=el('button','btn g home-more31');more.id='homeMore31';more.onclick=()=>{this.limit+=24;this.render(true);};
  const kinds=el('div','home-kinds38');kinds.id='homeKinds38';kinds.setAttribute('role','tablist');tools.prepend(kinds);for(const [kind,key]of [['tracks','Tracks'],['albums','Albums'],['playlists','Playlists']]){const b=el('button','chip');b.type='button';b.setAttribute('role','tab');b.dataset.kind38=kind;b.textContent=t(key);b.onclick=()=>{this.kind=kind;this.source='all';this.items=this.groups38[kind];this.limit=24;Repair33.category='all';this.labels();Repair33.categoryLabels();this.render();};kinds.append(b);}
  $('vHome').prepend(head,tools);$('rows').after(more);$('rows').classList.add('home-grid31');$('rows').setAttribute('aria-labelledby','homeTitle31');
  $('homeSource31').onchange=e=>{this.source=e.target.value;this.limit=24;this.render();};
  $('homeRefresh31').onclick=()=>this.load(true);$('homePlay31').onclick=()=>{const a=this.filtered();if(a.length)Player.playList(a,false);};
  // Keep legacy IDs for settings and older integrations, but expose only one home surface.
  for(const child of $('vHome').children)if(!['homeHead31','homeFilter31','rows','homeMore31'].includes(child.id)){child.hidden=true;child.setAttribute('aria-hidden','true');}
  this.sidebar();this.labels();
  const data=Views.recommendSnapshot30?.data||ExperienceV8.lastRecommendationData;
  if(data){this.receive(data);if(data.refreshing)this.poll33(12);}else this.load(false);
  const lang=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const v=lang(...a);this.labels();this.render();return v;};

 },
 sidebar(){
  const details=document.createElement('details');details.id='sideMore31';const summary=document.createElement('summary');summary.className='nav';summary.id='sideMoreLabel31';details.append(summary);
  const side=$('side');side.querySelector('.side-h')?.before(details);
  for(const node of [side.querySelector('[data-nav="history"]'),$('navClips'),$('navIdentify'),side.querySelector('[data-convert-open]'),$('navStore8')])if(node)details.append(node);
  details.addEventListener('keydown',e=>{if(e.key==='Escape'){details.open=false;summary.focus();}});
 },
 labels(){
  for(const b of document.querySelectorAll('[data-kind38]')){b.textContent=t({tracks:'Tracks',albums:'Albums',playlists:'Playlists'}[b.dataset.kind38]);b.setAttribute('aria-selected',String(b.dataset.kind38===this.kind));b.classList.toggle('on',b.dataset.kind38===this.kind);}
  $('homeTitle31').textContent=t('Recommendations');$('homePlay31').querySelector('span').textContent=t('Play recommendations');$('homeRefresh31').querySelector('span').textContent=t('Refresh recommendations');$('homeMore31').textContent=t('Show more');$('homeSourceLabel31').textContent=t('Source');$('sideMoreLabel31').innerHTML=icon('queue')+'<span>'+esc(t('More'))+'</span>';$('sideMoreLabel31').setAttribute('aria-label',t('More'));$('sideMoreLabel31').title=t('More');
  const select=$('homeSource31');select.replaceChildren();const all=document.createElement('option');all.value='all';all.textContent=t('All sources');select.append(all);
  for(const source of [...new Set(this.items.map(x=>x.source||x.id.split(':')[0]))].sort()){const op=document.createElement('option');op.value=source;op.textContent=source==='local'?t('Local library'):source.charAt(0).toUpperCase()+source.slice(1);select.append(op);}select.value=this.source;
 },
 receive(data){
  this.data=data;Studio.homeData=data.rows||[];this.groups38={tracks:[],albums:[],playlists:[]};
  for(const kind of ['tracks','albums','playlists']){
   const ids=new Set(),names=new Set(),out=[];
   const groups=(data.rows||[]).filter(r=>!r.unresolved&&(r.kind||'tracks')===kind);
   const max=Math.max(0,...groups.map(r=>(r.items||[]).length));
   for(let i=0;i<max;i++)for(const row of groups){const raw=row.items?.[i];if(!raw?.id||!raw.title)continue;
    const x=kind==='tracks'?raw:{...raw,kind:kind==='albums'?'album':'playlist'};
    const name=(String(x.artist||'')+'|'+x.title).normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,' ').trim();
    if(ids.has(x.id)||names.has(name))continue;ids.add(x.id);names.add(name);out.push(x);
   }
   this.groups38[kind]=out;
  }
  this.items=this.groups38[this.kind];this.limit=24;if(!this.items.some(x=>(x.source||x.id.split(':')[0])===this.source))this.source='all';this.labels();this.render();
 },
 filtered(){return this.items.filter(x=>this.source==='all'||(x.source||x.id.split(':')[0])===this.source);},
 render(append=false){
  if(!this.ready)return;const scrollEl=$('scroll'),prevScroll=scrollEl?scrollEl.scrollTop:0;
  const tracks=this.filtered(),box=$('rows'),focused=box.contains(document.activeElement)?[...box.children].indexOf(document.activeElement.closest('.track-shell30')):-1;
  const start=append?box.children.length:0;
  const nodes=tracks.slice(start,this.limit).map(x=>this.kind==='tracks'?Views.trackCard(x,tracks,{stats:false,recommendRadio66:true}):Views.collectionCard(x));
  if(!nodes.length){const empty=el('div','empty');empty.textContent=t('Nothing to show yet — find your first track and the picks will build themselves');nodes.push(empty);}
  if(append)box.append(...nodes);else box.replaceChildren(...nodes);
  if(scrollEl&&!append)scrollEl.scrollTop=prevScroll;
  if(focused>=0)box.children[focused]?.querySelector('button')?.focus({preventScroll:true});
  $('homeCount31').textContent=tracks.length?`${Math.min(this.limit,tracks.length)} / ${tracks.length}`:'';$('homeMore31').hidden=this.limit>=tracks.length;$('homePlay31').disabled=!tracks.length||this.kind!=='tracks';$('homeRefresh31').disabled=this.busy;box.setAttribute('aria-busy',String(this.busy));
 },
 async poll33(rows, ticket){
  for(let attempt=0;attempt<32;attempt++){
   await new Promise(r=>setTimeout(r,1500));if(ticket!==this.pollTicket33)return;
   try{
    const data=await api('/api/recommend?rows='+rows+'&poll=1',{timeout:this.timeoutMs36,signal:this.abort33?.signal});
    if(ticket!==this.pollTicket33)return;
    if(!data.refreshing){
     Views.recommendSnapshot30={rows,data};ExperienceV8.recommendStatus(data);
     if(data.rows?.length||!this.items.length)this.receive(data);
     $('homeStatus31').textContent='';return;
    }
   }catch(e){
    if(e?.name==='AbortError'||ticket!==this.pollTicket33)return;
    $('homeStatus31').textContent=t('Could not build the selections:')+' '+e.message;return;
   }
  }
  if(ticket===this.pollTicket33)$('homeStatus31').textContent=t('Could not build the selections:')+' '+t('Please retry');
 },
 async load(force){
  if(this.busy)return this.pending;
  if(!force&&this.data){this.labels();return;}
  const ticket=this.pollTicket33=(this.pollTicket33||0)+1;
  this.abort33?.abort();
  const controller=this.abort33=typeof AbortController!=='undefined'?new AbortController():null;
  this.busy=true;$('homeStatus31').textContent=t('Looking for new music…');$('homeRefresh31').disabled=true;$('rows').setAttribute('aria-busy','true');
  this.pending=(async()=>{try{
   if(force)dropCache('/api/recommend');const rows=[8,12,16].includes(S.ui8?.recommendRows)?S.ui8.recommendRows:12;
   const exclude=force?this.items.slice(0,48).map(x=>x.id).filter(Boolean):[];
   const url='/api/recommend?rows='+rows+(force?'&fresh=1':'')+(exclude.length?'&exclude='+encodeURIComponent(exclude.join(',')):'');
   const data=force
    ? await api(url,{timeout:this.timeoutMs36,signal:controller?.signal})
    : await cachedApi(url,300000,{timeout:this.timeoutMs36,signal:controller?.signal});
   if(ticket!==this.pollTicket33)return;
   if(data.rows?.length||!data.refreshing){
    Views.recommendSnapshot30={rows,data};ExperienceV8.recommendStatus(data);this.receive(data);
   }
   $('homeStatus31').textContent=data.refreshing?t('Updating in background…'):'';
   if(data.refreshing)await this.poll33(rows,ticket);
  }catch(e){
   if(e?.name==='AbortError'||ticket!==this.pollTicket33)return;
   $('homeStatus31').textContent=t('Could not build the selections:')+' '+e.message;
  }finally{
   if(ticket===this.pollTicket33){this.busy=false;this.pending=null;$('homeRefresh31').disabled=false;$('rows').setAttribute('aria-busy','false');}
  }})();return this.pending;
 }
};
// Hidden legacy home widgets neither fetch nor rebuild their DOM on every navigation.
InterfaceV6.home=()=>{};
HomePicks20.load=async()=>{};HomePicks20.render=()=>{};Home.paintHero=()=>{};Workspace.loadRecent=async()=>{};
const boot31=App.boot.bind(App);App.boot=async function(...a){await boot31(...a);Home31.init();};
