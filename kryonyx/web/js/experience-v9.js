/* UI v9: richer discovery, typed search, collaborator profiles, calmer stages. */
'use strict';
const MusicMeta9={
 norm(s){return String(s||'').normalize('NFKC').toLocaleLowerCase().replace(/ё/g,'е').replace(/[\p{P}\p{S}]/gu,' ').replace(/\s+/g,' ').trim();},
 artists(track){
  const structured=Array.isArray(track?.artists)?track.artists:[];
  let list=structured.map(a=>typeof a==='string'?{name:a}:{name:a.name||a.artist,url:a.url||a.author_url,source:a.source||track.source}).filter(a=>a.name);
  if(!list.length){
   // Do not split & / x: these also belong to real band names (AC/DC, Simon & Garfunkel).
   const names=String(track?.artist||'').split(/\s*(?:,|;|\bfeat\.?\s+|\bft\.\s+|\bfeaturing\s+)\s*/i).filter(Boolean);
   list=names.map((name,i)=>({name:name.trim(),source:track.source,url:names.length===1?track.author_url:undefined}));
  }
  const seen=new Set();return list.filter(a=>{const key=this.norm(a.name);if(!key||seen.has(key))return false;seen.add(key);return true;}).slice(0,20);
 },
 rank(track,query){const q=this.norm(query),title=this.norm(track.title),artist=this.norm(track.artist),both=title+' '+artist;if(!q)return 0;const words=q.split(' ');return (title===q?140:0)+(artist===q?100:0)+(title.startsWith(q)?55:0)+(artist.startsWith(q)?35:0)+words.reduce((v,w)=>v+(both.includes(w)?12:-5),0);}
};
if(typeof module!=='undefined'&&module.exports)module.exports=MusicMeta9;
const ExperienceV9={
 tr(en, ru) { return t(en); },
 button(label,fn,cls='btn g'){const b=el('button',cls);b.type='button';b.textContent=label;b.onclick=fn;return b;},
 init(){document.body.classList.add('ui-v9');this.search();this.artistProfiles();this.shelves();this.performance(); /* Clip layout is owned by Interface45. */},
 recent(){try{const d=JSON.parse(localStorage.getItem('kryonyx.search.rich.v9')||'[]');return Array.isArray(d)?d.filter(x=>x&&['track','author','history'].includes(x.kind)&&typeof x.text==='string').slice(0,20):[];}catch{return[];}},
 writeRecent(items){try{localStorage.setItem('kryonyx.search.rich.v9',JSON.stringify(items.slice(0,20)));}catch{}},
 remember(item){this.writeRecent([item,...this.recent().filter(x=>!(x.kind===item.kind&&x.text===item.text))]);},
 search(){
  const self=this,input=$('q'),box=$('qPop');input.placeholder=this.tr('What do you want to play?','Что хочешь включить?');input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-controls','qPop');input.setAttribute('aria-expanded','false');box.setAttribute('role','listbox');box.setAttribute('aria-label',this.tr('Search suggestions','Подсказки поиска'));
  const hint=el('kbd','ui9-shortcut');hint.textContent='Ctrl K';hint.setAttribute('aria-hidden','true');$('qClear').before(hint);
  input.addEventListener('input',()=>{Hints.token++;input.removeAttribute('aria-activedescendant');});
  Hints.fetch=async function(query){
   const token=++this.token,q=String(query||'').trim();let data={};
   try{data=await api(q.length>=2?'/api/suggest?'+new URLSearchParams({q,authors:'1',rich:'1',sources:activeSources().join(',')}):'/api/searches',{timeout:9000});}catch{}
   if(token!==this.token)return null;
   const local=self.recent().filter(x=>!q||MusicMeta9.norm(x.text).includes(MusicMeta9.norm(q)));
   const history=(data.items||data.history||[]).filter(x=>typeof x==='string').map(text=>({kind:'history',text}));
   const remote=q.length<2?[]:[...(data.authors||[]).slice(0,4).map(author=>({kind:'author',text:author.name,author})),...(data.tracks||[]).slice(0,5).map(track=>({kind:'track',text:track.title,track})),...(data.queries||[]).slice(0,4).map(text=>({kind:'hint',text}))];
   const seen=new Set();return [...local,...remote,...history].filter(x=>{const key=x.kind+':'+x.text;if(!x.text||seen.has(key))return false;seen.add(key);return true;}).slice(0,14);
  };
  Hints.render=function(){box.replaceChildren();input.setAttribute('aria-expanded','true');const head=el('div','q-pop-h');const title=el('strong');title.textContent=input.value.trim()?self.tr('Quick results','Быстрые результаты'):self.tr('Search history','История поиска');head.append(title);
   const clear=self.button(self.tr('Clear history','Очистить'),async()=>{try{await api('/api/searches',{method:'DELETE'});}catch{toast(self.tr('Could not clear server history','Не удалось очистить историю сервера'));return;}self.writeRecent([]);this.hide();},'q-pop-clear');head.append(clear);box.append(head);
   if(!this.items.length){const empty=el('p','ui9-search-empty');empty.textContent=self.tr('Search for a song or artist. Your recent picks appear here.','Найди трек или исполнителя. Недавние находки появятся здесь.');box.append(empty);}
   this.items.forEach((item,i)=>box.append(this.row(item,i)));
  };
  Hints.row=function(item,index){const row=el('div','q-row ui9-result');row.id='ui9Hint'+index;row.setAttribute('role','option');row.setAttribute('aria-selected',String(index===this.at));row.dataset.kind=item.kind;const isArtist=item.kind==='author',obj=item.track||item.author;
   const image=el('span','ui9-hint-art');if(obj&&(obj.thumbnail||obj.picture)){const img=el('img');img.alt='';setImg(img,obj.thumbnail||obj.picture,48);image.append(img);}else image.innerHTML=icon(isArtist?'user':item.kind==='track'?'note':'clock','ic');
   const copy=el('span','ui9-hint-copy'),title=el('strong'),sub=el('small');title.textContent=item.text;title.dataset.entityName='';sub.textContent=isArtist?self.tr('Artist','Исполнитель'):item.track?self.tr('Track · ','Трек · ')+(item.track.artist||''):self.tr('Recent search','Поисковый запрос');if(item.track){const artistName=el('span');artistName.dataset.entityName='';artistName.textContent=item.track.artist||'';sub.replaceChildren(document.createTextNode(self.tr('Track · ','Трек · ')),artistName);}copy.append(title,sub);row.append(image,copy);
   if(self.recent().some(x=>x.kind===item.kind&&x.text===item.text)||item.kind==='history'){const drop=self.button('×',async event=>{event.preventDefault();event.stopPropagation();if(item.kind==='history'){try{await api('/api/searches?q='+encodeURIComponent(item.text),{method:'DELETE'});}catch{toast(self.tr('Could not remove query','Не удалось удалить запрос'));return;}}self.writeRecent(self.recent().filter(x=>!(x.kind===item.kind&&x.text===item.text)));this.items=this.items.filter(x=>x!==item);this.at=-1;input.removeAttribute('aria-activedescendant');this.render();},'q-drop');drop.setAttribute('aria-label',self.tr('Remove ','Удалить ')+item.text);drop.onmousedown=e=>e.preventDefault();row.append(drop);}
   row.onmousedown=e=>{if(e.target.closest('.q-drop'))return;e.preventDefault();this.pick(item);};return row;
  };
  Hints.pick=function(item){this.armed=false;this.hide();self.remember(item);input.blur();if(item.kind==='track'){const queue=this.items.filter(x=>x.kind==='track'&&x.track?.id).map(x=>x.track);if(!queue.some(x=>x.id===item.track.id))queue.unshift(item.track);return Player.play(item.track,queue);}if(item.kind==='author')return App.openAuthor(item.author.name,item.author.url,item.author.source);input.value=item.text;$('qClear').style.display='';App.search(item.text);};
  const hide=Hints.hide.bind(Hints);Hints.hide=()=>{hide();input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');};
  Hints.move=step=>{if(!Hints.open||!Hints.items.length)return;const n=Hints.items.length+1;Hints.at=(Hints.at+1+step+n)%n-1;box.querySelectorAll('.q-row').forEach((node,i)=>{node.classList.toggle('on',i===Hints.at);node.setAttribute('aria-selected',String(i===Hints.at));});if(Hints.at>=0){input.setAttribute('aria-activedescendant','ui9Hint'+Hints.at);$('ui9Hint'+Hints.at)?.scrollIntoView({block:'nearest'});}else input.removeAttribute('aria-activedescendant');};
  // Show an honest empty state instead of an empty floating box.
  Hints.show=async function(query){if(!this.armed)return;const items=await this.fetch(query);if(items===null||!this.armed)return;this.items=items;this.at=-1;this.render();box.hidden=false;box.classList.add('on');this.open=true;};
  const search=App.search.bind(App);App.search=(query,...args)=>{const q=String(query||'').trim();if(q&&!Convert.looksLikeLink(q)){self.remember({kind:'history',text:q});input.value=q;}Hints.armed=false;Hints.hide();return search(query,...args);};
  // v73: rows ranked by the server (search_score: catalogue signals, copies
  // folded) keep that order — re-sorting them by this title-only score put
  // songs merely *named* like the query above the original («земфира» showed
  // other artists' songs called «Земфира» first; «бесконечность» buried
  // Земфира's own «Бесконечность»). Only unranked rows (plugins) are sorted.
  const filter=Studio.filterTracks.bind(Studio);Studio.filterTracks=tracks=>{const found=filter(tracks);if(Studio.search.sort!=='relevance'||!K.search.query)return found;const scored=t=>typeof t.search_score==='number';if(found.every(scored))return found;return [...found.filter(scored),...found.filter(t=>!scored(t)).sort((a,b)=>MusicMeta9.rank(b,K.search.query)-MusicMeta9.rank(a,K.search.query))];};
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&['k','л'].includes(e.key.toLowerCase())){e.preventDefault();closeModals();$('now').classList.remove('on');if(Clips.active)Clips.close();App.go('search');input.focus();input.select();}});
 },
 artistProfiles(){
  const modal=el('section','modal ui9-artists');modal.id='mArtists9';modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','ui9ArtistTitle');modal.innerHTML=`<div class="mh"><div><span class="ui8-eyebrow">ARTISTS</span><h3 id="ui9ArtistTitle"></h3><p id="ui9ArtistTrack"></p></div></div><div class="mb" id="ui9ArtistChoices"></div><div class="acts"></div>`;document.body.append(modal);modal.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();closeModals();this.artistFocus?.focus();}if(e.key==='Tab'){const buttons=[...modal.querySelectorAll('button')];const i=buttons.indexOf(document.activeElement);if(e.shiftKey&&i===0){e.preventDefault();buttons.at(-1).focus();}else if(!e.shiftKey&&i===buttons.length-1){e.preventDefault();buttons[0].focus();}}});modal.querySelector('.acts').append(this.button(this.tr('Close','Закрыть'),()=>{closeModals();this.artistFocus?.focus();}));
  App.openTrackArtists=(track)=>{const choices=MusicMeta9.artists(track);if(!choices.length)return;if(choices.length===1){const a=choices[0];return open(a.name,a.url,a.source||track.source);}this.artistFocus=document.activeElement;$('ui9ArtistTitle').textContent=this.tr('Whose profile?','Чей профиль открыть?');$('ui9ArtistTrack').textContent=track.title||track.artist;$('ui9ArtistTrack').dataset.entityName='';$('ui9ArtistChoices').replaceChildren();choices.forEach(a=>{const b=this.button(a.name,()=>{closeModals();open(a.name,a.url,a.source||track.source);},'ui9-artist-choice');b.dataset.entityName='';b.insertAdjacentHTML('afterbegin',icon('user'));b.insertAdjacentHTML('beforeend',icon('next','ic s'));$('ui9ArtistChoices').append(b);});openModal('mArtists9');modal.querySelector('.ui9-artist-choice').focus();};
  const originalOpen=App.openAuthor.bind(App);const open=(...args)=>{$('now')?.classList.remove('on');return originalOpen(...args);};App.openAuthor=(name,url,source)=>{if(Player.current&&name===Player.current.artist&&MusicMeta9.artists(Player.current).length>1)return App.openTrackArtists(Player.current);return open(name,url,source);};
 },
 shelves(){
  $('ui8RecTools').querySelector('.ui8-eyebrow').textContent='DISCOVERY / 09';
  const help=el('p','ui9-rec-hint');help.textContent=this.tr('Up to 60 tracks per mix. Open “All tracks” for the full list. Availability depends on your sources.','До 60 треков в миксе. «Все треки» открывает полный список. Количество зависит от доступных источников.');$('ui8RecTools').after(help);
  const shelf=Views.shelf.bind(Views);Views.shelf=row=>{const host=shelf(row);if(!row.unresolved&&row.kind!=='albums'&&row.kind!=='playlists'&&row.items?.length){const all=this.button(this.tr('All tracks · ','Все треки · ')+row.items.length,()=>{const title=row.title_key?tf(row.title_key,row.title_args):t(row.title);App.showList(title,row.items,{type:'mix',id:row.id,name:title});},'chip ui9-all-tracks');host.querySelector('.shelf-h').append(all);}return host;};
 },
 clips(){
  const clips=$('clips'),main=clips.querySelector('.cs-main');clips.querySelector('h1').textContent=this.tr('Music videos','Клипы');clips.querySelector('.cs-eyebrow').textContent='KRYO / CINEMA';
  const advanced=el('details','ui9-clip-details');advanced.id='ui9ClipDetails';const sum=el('summary');sum.textContent=this.tr('Tools & downloads','Инструменты и загрузка');advanced.append(sum);main.append(advanced);advanced.append(clips.querySelector('.cs-tabs'),...['download','tools','settings'].map(n=>$('clipPanel-'+n)));
  const session=el('details','ui9-clip-session');session.id='ui9ClipSession';const s=el('summary');s.textContent=this.tr('YouTube session · if playback asks you to sign in','Сессия YouTube · если сервис просит войти');session.append(s,clips.querySelector('.cs-advisory'));advanced.append(session);
  // Secondary transport remains reachable, but not mixed into the primary row.
  const secondary=el('div','ui9-clip-secondary');secondary.append($('clipBack'),$('clipFwd'),clips.querySelector('.cs-volume'));$('clipPanel-tools').prepend(secondary);
  const toggle=this.button(this.tr('Search & queue','Поиск и очередь'),()=>{const on=!clips.classList.contains('ui9-queue-open');clips.classList.toggle('ui9-queue-open',on);toggle.setAttribute('aria-expanded',String(on));if(on&&innerWidth<=760)clips.querySelector('.cs-sidebar').scrollIntoView({block:'start',behavior:S.noAnim?'instant':'smooth'});},'btn g ui9-queue-toggle');toggle.id='ui9ClipQueue';toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-controls','ui9ClipSidebar');clips.querySelector('.cs-sidebar').id='ui9ClipSidebar';clips.querySelector('.cs-controls').append(toggle);const back=this.button(this.tr('Back to video','Назад к клипу'),()=>{clips.classList.remove('ui9-queue-open');toggle.setAttribute('aria-expanded','false');toggle.scrollIntoView({block:'center'});},'btn g ui9-sidebar-back');clips.querySelector('.cs-sidebar').prepend(back);
  const tab=Clips.tab.bind(Clips);Clips.tab=name=>{advanced.open=true;tab(name);};
 },
 performance(){
  const now=$('now'),top=$('nowTop');addEventListener('resize',debounce(()=>{if(now.classList.contains('on')&&!Viz.on&&Karaoke.follow)Karaoke.center(true);},200));const controls=el('div','ui9-stage-controls');controls.id='ui9StageControls';
  const mode=el('div','ui9-mode-group');mode.setAttribute('role','group');mode.setAttribute('aria-label',this.tr('Performance mode','Режим сцены'));
  [['split','Lyrics','Текст'],['focus','Focus','Фокус'],['cinema','Cinema','Кино'],['disc','Disc','Диск']].forEach(([value,en,ru])=>{const b=this.button(this.tr(en,ru),()=>{S.karaokeMode=value;saveSettings();App.applyKaraoke();sync();},'ui9-mode');b.dataset.mode9=value;mode.append(b);});
  const skin=el('select','ui9-skin');skin.id='ui9StageSkin';skin.setAttribute('aria-label',this.tr('Stage appearance','Оформление сцены'));[['aurora','Aurora','Северное сияние'],['ink','Ink','Тушь'],['concert','Concert','Концерт']].forEach(([v,en,ru])=>skin.add(new Option(this.tr(en,ru),v)));skin.value=S.ui9?.stage||'aurora';skin.onchange=()=>{S.ui9={...S.ui9,stage:skin.value};now.dataset.performance=skin.value;saveSettings();};now.dataset.performance=skin.value;
  controls.append(mode,skin);top.after(controls);
  const sync=()=>{const current=S.karaokeMode||'split';mode.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode9===current)));};sync();
  const apply=App.applyKaraoke.bind(App);App.applyKaraoke=()=>{apply();sync();};
  const stage=$('kStage');if(stage){const editDetails=el('details','ui9-lyric-tools');const summary=el('summary');summary.textContent=this.tr('Lyrics tools','Работа с текстом');editDetails.append(summary,stage.querySelector('.k-stage-actions'));stage.append(editDetails);}
  const details=el('details','ui9-timing');details.append(el('summary','',this.tr('Lyrics timing','Синхронизация текста')));$('nSyncRow').before(details);details.append($('nSyncRow'));
  // Track-specific collaborator chooser is used here too.
  const bindArtists=()=>['nArtist','vizArtist','pArtist'].forEach(id=>{const node=$(id);if(!node)return;node.setAttribute('role','button');node.tabIndex=0;node.title=this.tr('Open artist / choose collaborator','Открыть исполнителя / выбрать участника');node.onclick=e=>{e.stopPropagation();if(Player.current)App.openTrackArtists(Player.current);};node.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();e.stopPropagation();node.click();}};});
  const build=Viz.build.bind(Viz);Viz.build=()=>{build();bindArtists();};bindArtists();
 }
};
