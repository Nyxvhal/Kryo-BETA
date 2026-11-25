/* Reference-matched performance layout. Existing lyric nodes/timing remain authoritative. */
'use strict';
const ReferenceScene24={
 ready:false,
 duration(){const d=Player.audio?.duration;return Number.isFinite(d)&&d>0?d:Math.max(0,Number(Player.current?.duration)||0);},
 active(){return $('now')?.classList.contains('reference24');},
 button(id,label,markup,action){const b=el('button','');if(id)b.id=id;b.type='button';b.innerHTML=markup;b.setAttribute('aria-label',label);b.title=label;b.onclick=action;return b;},
 icons:{
  pause:'<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="5" height="16" rx="1"/><rect x="13" y="4" width="5" height="16" rx="1"/></svg>',
  prev:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 6v12L2 12zm10 0v12l-10-6z"/></svg>',
  next:'<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 6v12l10-6zm10 0v12l10-6z"/></svg>',
  lyrics:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 4h14a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-5l-4 4v-4H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z"/><path d="M8 8h3v3H8zm6 0h3v3h-3"/></svg>'
 },
 init(){
  if(!S.albumReferenceRev24){if(S.karaokeStyle==='albumflow'){S.karaokeMode='split';S.karaokeBare=false;}S.albumReferenceRev24=true;saveSettings();}
  const layer=el('div','');layer.id='referenceScene24';const deck=el('section','');deck.id='albumDeck24';deck.setAttribute('aria-label',t('Player'));deck.innerHTML='<img id="albumArt24" alt=""><div id="albumTitle24" data-entity-name></div><div id="albumArtist24" data-entity-name></div><div id="albumTimeline24"><span id="albumElapsed24">0:00</span><div id="albumSeek24" tabindex="0" role="slider" aria-valuemin="0" aria-valuemax="100"><i><b></b></i></div><span id="albumRemaining24">−0:00</span></div><div id="albumButtons24"><div id="albumTools24"></div><div id="albumTransport24"></div></div><div id="albumVolumeBox24" hidden><input id="albumVolume24" type="range" min="0" max="100" step="1"></div>';
  const tools=deck.querySelector('#albumTools24'),transport=deck.querySelector('#albumTransport24'),buttons=deck.querySelector('#albumButtons24');
  tools.append(this.button('albumVolumeButton24',t('Volume'),icon('vol'),()=>this.popup('albumVolumeBox24','albumVolumeButton24')));
  transport.append(this.button('albumPrev24',t('Previous'),this.icons.prev,()=>Player.prev()),this.button('albumPlay24',t('Play'),icon('play','ic f'),()=>Player.toggle()),this.button('albumNext24',t('Next'),this.icons.next,()=>Player.next(false)));
  buttons.append(this.button('albumLyrics24',t('Lyrics'),this.icons.lyrics,()=>{S.albumLyricsVisible24=S.albumLyricsVisible24===false;saveSettings();this.apply();if(Karaoke.synced)Karaoke.center(true);}));
  const volume=deck.querySelector('#albumVolume24');volume.setAttribute('aria-label',t('Volume'));volume.oninput=e=>MiniPlayer.volume(+e.target.value);
  const seek=deck.querySelector('#albumSeek24');seek.setAttribute('aria-label',t('Seek'));
  const seekAt=e=>{const b=seek.getBoundingClientRect();Player.seek(Math.max(0,Math.min(1,(e.clientX-b.left)/Math.max(1,b.width))));this.time();};
  seek.onpointerdown=e=>{if(e.button!==0)return;e.preventDefault();seek.setPointerCapture(e.pointerId);seekAt(e);};seek.onpointermove=e=>{if(seek.hasPointerCapture(e.pointerId)&&e.buttons)seekAt(e);};seek.onpointerup=e=>{if(seek.hasPointerCapture(e.pointerId)){seekAt(e);seek.releasePointerCapture(e.pointerId);}};
  seek.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();e.stopPropagation();const d=this.duration(),a=Player.audio;if(!d)return;Player.seek((e.key==='Home'?0:e.key==='End'?d:Math.max(0,Math.min(d,a.currentTime+(e.key==='ArrowRight'?5:-5))))/d);this.time();};
  layer.append(deck);$('now').append(layer);
  $('albumVolumeButton24').setAttribute('aria-expanded','false');$('albumVolumeButton24').setAttribute('aria-controls','albumVolumeBox24');
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('#albumVolumeBox24,#albumVolumeButton24'))this.closePopups();});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('albumVolumeBox24').hidden){e.preventDefault();e.stopImmediatePropagation();this.closePopups();$('albumVolumeButton24').focus();}},true);
  const lang=App.afterLangChange.bind(App);App.afterLangChange=(...args)=>{const v=lang(...args);for(const [id,key] of [['albumFull24','Fullscreen'],['albumClose24','Close'],['albumVolumeButton24','Volume'],['albumLyrics24','Lyrics'],['albumPrev24','Previous'],['albumNext24','Next']]){const b=$(id);if(b){b.title=t(key);b.setAttribute('aria-label',t(key));}}this.state();return v;};
  for(const name of ['paintTrack','paintState','paintTime','paintProgress']){const old=Player[name].bind(Player);Player[name]=(...args)=>{const result=old(...args);if(name==='paintTrack')this.track();else if(name==='paintState')this.state();else this.time();return result;};}
  const old=App.applyKaraoke.bind(App);App.applyKaraoke=(...args)=>{const result=old(...args);this.apply();return result;};
  const center=Karaoke.center.bind(Karaoke);Karaoke.center=(instant=false)=>{if(!this.active())return center(instant);const box=$('lyrics'),node=Karaoke.lineNodes[Karaoke.active];if(!box||!node)return;const rect=box.getBoundingClientRect(),zoom=box.offsetHeight?rect.height/box.offsetHeight:1;const relative=(node.getBoundingClientRect().top-rect.top)/(zoom||1)+box.scrollTop;Karaoke.scrollTo=Math.max(0,relative-box.clientHeight*(innerWidth<=760?.18:.4));if(instant||S.noAnim||matchMedia('(prefers-reduced-motion: reduce)').matches){box.scrollTop=Karaoke.scrollTo;Karaoke.scrollTo=null;}else Karaoke.glide();};
  addEventListener('resize',debounce(()=>{if(this.active()&&Karaoke.synced)Karaoke.center(true);},150));
  this.ready=true;FluidCover24.init();this.track();this.state();App.applyKaraoke();this.apply();document.body.classList.add('ui-v24');
 },
 popup(id,button){const open=$(id).hidden;this.closePopups();$(id).hidden=!open;$(button).setAttribute('aria-expanded',String(open));if(open)$(id).querySelector('input,button')?.focus();},
 closePopups(){for(const [id,b]of [['albumVolumeBox24','albumVolumeButton24']]){if($(id))$(id).hidden=true;if($(b))$(b).setAttribute('aria-expanded','false');}},
 apply(){const n=$('now');n.classList.toggle('reference24',n.classList.contains('album-flow23')&&S.karaokeMode==='split');n.classList.toggle('reference-no-lyrics24',S.albumLyricsVisible24===false);$('albumLyrics24')?.setAttribute('aria-pressed',String(S.albumLyricsVisible24!==false));if(!this.active())this.closePopups();this.time();FluidCover24.sync();},
 track(){const t24=Player.current;if(!t24)return;const art=typeof KCustom!=='undefined'?KCustom.cover(t24.thumbnail):t24.thumbnail;if($('albumArt24').dataset.cover!==art){$('albumArt24').dataset.cover=art||'';setImg($('albumArt24'),art,720);}for(const [id,text]of [['albumTitle24',t24.title],['albumArtist24',t24.artist]]){KMarquee.set($(id),text||'',S.noAnim);$(id).title=text||'';}this.time();},
 state(){if(!$('albumPlay24'))return;const playing=!Player.audio.paused&&!Player.audio.ended;$('albumPlay24').innerHTML=playing?this.icons.pause:icon('play','ic f');for(const n of ['albumPlay24']){$(n).title=t(playing?'Pause':'Play');$(n).setAttribute('aria-label',$(n).title);}this.time();FluidCover24.sync();Player.paintLoading();},
 time(){if(!$('albumSeek24')||!this.active()||!$('now')?.classList.contains('on')||document.hidden||document.querySelector('.modal.on'))return;const a=Player.audio,d=this.duration(),pos=Math.max(0,(Player.seeking||Player.holdUntilSeeked)&&Player.seekRatio!=null?Player.seekRatio*d:Number(a?.currentTime)||0),p=Player.seeking||Player.holdUntilSeeked?Player.seekRatio:(d?pos/d:0),ratio=Math.max(0,Math.min(1,p||0));paintText40($('albumElapsed24'),fmt(pos));paintText40($('albumRemaining24'),'−'+fmt(Math.max(0,Math.floor(d)-Math.floor(pos))));paintStyle40($('albumSeek24').querySelector('b'),'width',(ratio*100).toFixed(3)+'%');paintAttr40($('albumSeek24'),'aria-valuenow',String(Math.round(ratio*100)));paintAttr40($('albumSeek24'),'aria-valuetext',fmt(pos)+' / '+fmt(d));if(document.activeElement!==$('albumVolume24'))$('albumVolume24').value=S.volume;}
};
const boot24=App.boot.bind(App);App.boot=async function(...args){await boot24(...args);ReferenceScene24.init();};
