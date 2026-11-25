/* Search and next-listening workflow. Existing provider/taste engine remains authoritative. */
'use strict';
const SearchDiscovery26={
 ready:false,items:[],seed:null,key:'',token:0,controller:null,pending:false,error:false,mode:'all',count:8,undo:null,loaded:false,timeoutMs:26000,
 hidden(){return Array.isArray(S.search26Hidden)?S.search26Hidden.filter(v=>typeof v==='string').slice(-200):[];},
 identity(track){const norm=s=>String(s||'').toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu,'');return 'meta:'+norm(track.artist)+'|'+norm(track.title);},
 button(label,action,cls='btn g'){const n=el('button',cls);n.type='button';n.textContent=t(label);n.setAttribute('aria-label',t(label));n.onclick=action;return n;},
 chooseSeed(){return Player.current?.id?Player.current:K.view==='search'?K.search?.tracks?.find(track=>track.id)||null:null;},
 init(){
  if(this.ready)return;this.ready=true;
  const submit=this.button('Search',()=>{const q=$('q').value.trim();if(q)Studio.runSearch(q);else $('q').focus();},'ib search-submit26');submit.id='searchSubmit26';submit.title=t('Search');submit.innerHTML=icon('search');$('searchBox').append(submit);$('qClear').setAttribute('aria-label',t('Clear search'));
  const search=$('vSearch'),grid=el('div','search-grid26'),main=el('div','search-main26');grid.id='searchGrid26';main.id='searchMain26';
  [...search.children].filter(n=>n.id!=='sTitle'&&!n.classList.contains('studio-search-intro')).forEach(n=>main.append(n));grid.append(main);search.append(grid);
  const actions=el('div','search-actions26');actions.id='searchActions26';const detail=el('p','muted');detail.id='searchCount26';detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');
  const play=this.button('Play results',()=>{const tracks=Studio.filterTracks(K.search.tracks);if(tracks.length)Player.play(tracks[0],tracks);});play.id='searchPlay26';const retry=this.button('Retry search',()=>App.search(K.search.query,true));retry.id='searchRetry26';retry.hidden=true;actions.append(detail,play,retry);$('sTitle').after(actions);const overview=document.querySelector('.studio-overview');if(overview)actions.append(overview);
  const chips=el('div','search-sources26');chips.id='searchSources26';chips.setAttribute('role','group');chips.setAttribute('aria-label',t('Source'));$('sTabs').after(chips);
  const feed=el('aside','next-feed26');feed.id='nextFeed26';feed.setAttribute('aria-labelledby','nextHeading26');
  feed.innerHTML='<div class="next-head26"><div><span id="nextEyebrow26"></span><h2 id="nextHeading26"></h2></div></div><p id="nextReason26"></p><p id="nextSeed26" data-entity-name></p><div class="next-filters26" role="group"></div><label class="next-auto26"><input type="checkbox" id="nextAuto26"><span id="nextAutoLabel26"></span></label><div class="next-actions26"></div><p id="nextStatus26" role="status" aria-live="polite"></p><div id="nextList26"></div>';
  grid.append(feed);
  const refresh=this.button('Refresh recommendations',()=>this.load(true),'ib');refresh.id='nextRefresh26';refresh.innerHTML=icon('refresh');refresh.title=t('Refresh recommendations');feed.querySelector('.next-head26').append(refresh);
  for(const [mode,key]of [['all','For you'],['discover','Discoveries'],['familiar','Listen again']]){const b=this.button(key,()=>{this.mode=mode;this.count=8;this.render();},'chip');b.dataset.mode26=mode;feed.querySelector('.next-filters26').append(b);}
  $('nextAuto26').onchange=e=>{S.endlessRadio=e.target.checked;saveSettings(true);};
  const mix=this.button('Play recommendations',()=>{const tracks=this.filtered();if(tracks.length)Player.play(tracks[0],tracks);});mix.id='nextPlay26';const undo=this.button('Undo',()=>this.restore());undo.id='nextUndo26';undo.hidden=true;feed.querySelector('.next-actions26').append(mix,undo);
  const more=this.button('Show more',()=>{this.count+=8;this.render();});more.id='nextMore26';feed.append(more);grid.append(feed);
  const navigate=App.go.bind(App);App.go=(...args)=>{const v=navigate(...args);this.update();return v;};
  const render=App.renderSearchState.bind(App);App.renderSearchState=(...args)=>{const v=render(...args);this.update();return v;};
  const landing=Studio.searchLanding.bind(Studio);Studio.searchLanding=(...args)=>{const v=landing(...args);this.update();return v;};
  const track=Player.paintTrack.bind(Player);Player.paintTrack=(...args)=>{const v=track(...args);clearTimeout(this.trackTimer);this.trackTimer=setTimeout(()=>this.update(),100);return v;};
  const language=App.afterLangChange.bind(App);App.afterLangChange=(...args)=>{const v=language(...args);this.update();return v;};
  this.update();document.body.classList.add('ui-v26');
 },
 update(){
  if(!this.ready)return;const query=K.search?.query||'',tracks=Studio.filterTracks(K.search?.tracks||[]),hasQuery=!!query;
  $('searchActions26').hidden=!hasQuery;$('searchSources26').hidden=!hasQuery;$('searchPlay26').textContent=t('Play results');$('searchPlay26').setAttribute('aria-label',t('Play results'));$('searchPlay26').disabled=!tracks.length;
  $('searchCount26').textContent=hasQuery?tf('{count} tracks loaded',{count:tracks.length}):'';
  if($('studioFilterReset'))$('studioFilterReset').hidden=!(Studio.search.source||Studio.search.duration||Studio.search.liked||Studio.search.sort!=='relevance');
  $('searchRetry26').hidden=!hasQuery||!!K.search.loading||!Object.values(Studio.statuses).includes('error');
  $('searchRetry26').textContent=t('Retry search');$('searchSubmit26').title=t('Search');$('searchSubmit26').setAttribute('aria-label',t('Search'));
  const sourceHost=$('searchSources26');sourceHost.replaceChildren();for(const source of ['',...activeSources()]){const label=source?sourceName(source):t('All sources'),b=el('button','chip',label);b.type='button';b.dataset.source26=source;if(source)b.dataset.noI18n='';b.setAttribute('aria-pressed',String(Studio.search.source===source));b.onclick=()=>{Studio.search.source=source;$('studioSource').value=source;App.renderSearchState(!K.search.loading);};sourceHost.append(b);}
  const feed=$('nextFeed26');if(K.view==='home'){$('studioHero').after(feed);feed.classList.add('on-home26');}else if(K.view==='search'){$('searchGrid26').append(feed);feed.classList.remove('on-home26');}
  feed.hidden=K.view!=='search';const seed=this.chooseSeed();if(K.view==='home'&&!seed)feed.hidden=true;feed.setAttribute('aria-hidden',String(feed.hidden));
  const key=seed?JSON.stringify([seed.id,seed.title,seed.artist,activeSources()]):'';
  if(!this.key && key){this.controller?.abort();this.token++;this.key=key;this.seed=seed?{...seed}:null;this.items=[];this.error=false;this.pending=false;this.loaded=false;this.undo=null;this.count=8;this.mode='all';if(seed&&!feed.hidden)this.load();}
  else if(seed&&!feed.hidden&&!this.loaded&&!this.pending)this.load();
  this.render();
 },
 async load(force=false){
  if(force){const seed=this.chooseSeed();if(seed){this.seed={...seed};this.key=JSON.stringify([seed.id,seed.title,seed.artist,activeSources()]);}}
  if(!this.seed)return;this.controller?.abort();const controller=this.controller=new AbortController(),token=++this.token,key=this.key;this.pending=true;this.error=false;this.loaded=false;this.render();let timedOut=false;const timer=setTimeout(()=>{timedOut=true;controller.abort();},this.timeoutMs);
  try{const response=await fetch('/api/recommend/next',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track:this.seed,exclude:this.hidden()}),signal:controller.signal});const d=await response.json();if(!response.ok||d.error)throw Error('Recommendations unavailable');if(token!==this.token||key!==this.key)return;
   if(!Array.isArray(d.items))throw Error('Invalid recommendation response');const seen=new Set(),hidden=new Set(this.hidden()),seedIdentity=this.identity(this.seed);this.items=d.items.filter(track=>{if(!track||!track.id||!track.title||track.id===this.seed.id)return false;const identity=this.identity(track);if(identity===seedIdentity||seen.has(track.id)||seen.has(identity)||hidden.has(track.id)||hidden.has(identity))return false;seen.add(track.id);seen.add(identity);return true;});this.loaded=true;
  }catch(e){if(token!==this.token||(!timedOut&&controller.signal.aborted))return;this.error=true;this.loaded=true;}
  finally{clearTimeout(timer);if(token===this.token){this.pending=false;this.render();}}
 },
 filtered(){const hidden=new Set(this.hidden());return this.items.filter(track=>!hidden.has(track.id)&&!hidden.has(this.identity(track))&&(this.mode==='all'||(this.mode==='familiar'?track.is_familiar:!track.is_familiar)));},
 dismiss(track){this.undo={track,hidden:this.hidden()};S.search26Hidden=[...new Set([...this.hidden(),track.id,this.identity(track)])].slice(-200);saveSettings(true);this.render();},
 restore(){if(!this.undo)return;S.search26Hidden=this.undo.hidden;this.undo=null;saveSettings(true);this.render();},
 render(){
  if(!$('nextList26'))return;const stamp=JSON.stringify([LANG,this.seed,this.items,this.pending,this.error,this.mode,this.count,this.hidden(),!!this.undo,S.endlessRadio,this.items.map(x=>K.likes.has(x.id))]);if(stamp===this.renderStamp30)return;this.renderStamp30=stamp;$('nextEyebrow26').textContent=t('KEEP LISTENING');$('nextHeading26').textContent=t('Up next for you');$('nextReason26').textContent=t('Related tracks, tuned to your listening history.');$('nextSeed26').textContent=this.seed?t('Based on: ')+(this.seed.title||this.seed.artist):'';
  $('nextAutoLabel26').textContent=t('Continue with radio after the queue');$('nextAuto26').checked=!!S.endlessRadio;$('nextPlay26').textContent=t('Play recommendations');$('nextPlay26').setAttribute('aria-label',t('Play recommendations'));$('nextRefresh26').setAttribute('aria-label',t('Refresh recommendations'));$('nextRefresh26').title=t('Refresh recommendations');$('nextRefresh26').disabled=this.pending||!this.seed;
  $('nextUndo26').hidden=!this.undo;$('nextUndo26').textContent=t('Undo');for(const b of document.querySelectorAll('[data-mode26]')){b.textContent=t({all:'For you',discover:'Discoveries',familiar:'Listen again'}[b.dataset.mode26]);b.setAttribute('aria-pressed',String(this.mode===b.dataset.mode26));}
  const tracks=this.filtered();$('nextPlay26').disabled=!tracks.length||this.pending;$('nextMore26').hidden=tracks.length<=this.count||this.pending;$('nextMore26').textContent=t('Show more');
  $('nextStatus26').textContent=this.pending?t('Finding your next tracks…'):this.error?t('Could not load recommendations. Try refreshing.'):!this.seed?t('Play a song to get related recommendations.'):!tracks.length?t('No tracks in this selection. Try another filter or refresh.') : '';
  $('nextFeed26').setAttribute('aria-busy',String(this.pending));const list=$('nextList26');list.replaceChildren();
  if(this.pending&&!tracks.length){for(let i=0;i<3;i++){const skeleton=el('div','next-skeleton26');skeleton.setAttribute('aria-hidden','true');list.append(skeleton);}return;}
  for(const track of tracks.slice(0,this.count)){const article=el('article','next-card26');article.dataset.track26=track.id;const cover=this.button('Play',()=>Player.play(track,this.filtered()),'next-cover26');cover.setAttribute('aria-label',t('Play')+': '+track.title);const image=el('img');image.alt='';image.loading='lazy';setImg(image,track.thumbnail,180);cover.replaceChildren(image);const copy=el('div','next-copy26');const title=el('button','next-title26',esc(track.title));title.type='button';title.dataset.entityName='';title.title=track.title;title.onclick=()=>Player.play(track,this.filtered());const artist=el('button','ar-btn',esc(track.artist||''));artist.type='button';artist.dataset.entityName='';artist.setAttribute('aria-label',t('Open artist')+': '+(track.artist||''));artist.onclick=()=>App.openTrackArtists(track);artist.hidden=!track.artist;const service=el('span','next-service26',esc(sourceName(track.source)));service.dataset.noI18n='';copy.append(title,artist,service);
   const controls=el('div','next-card-actions26'),add=this.button('Add to the queue',()=>Player.addLast(track),'ib'),hide=this.button('Not interested',()=>this.dismiss(track),'ib');add.innerHTML=icon('plus');hide.innerHTML=icon('close');add.title=t('Add to the queue');hide.title=t('Not interested');const like=this.button(K.likes.has(track.id)?'Unlike':'Like',async()=>{await toggleLike(track);this.render();},'ib'),playlist=this.button('Add to playlist',()=>Workspace.addToPlaylistDialog([track]),'ib');like.innerHTML=icon('heart');like.classList.toggle('on',K.likes.has(track.id));like.dataset.like=track.id;like.setAttribute('aria-pressed',String(K.likes.has(track.id)));playlist.innerHTML=icon('lib');playlist.title=t('Add to playlist');controls.append(like,playlist,add,hide);article.append(cover,copy,controls);list.append(article);}
 }
};
const boot26=App.boot.bind(App);App.boot=async function(...args){await boot26(...args);SearchDiscovery26.init();};
