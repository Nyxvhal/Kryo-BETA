/* Shared controls and customization. No second audio/animation clock. */
'use strict';
const Repair33={
 labels:{
  'Player mode':['Режим плеера'],'Lyrics & artwork':['Текст и обложка'],'Disc':['Диск'],
  'Interface opacity':['Непрозрачность интерфейса'],'Audio quality':['Качество музыки'],
  'Best available source':['Лучшее у источника'],'Balanced · up to 160 kbps':['Баланс · до 160 кбит/с'],'Data saver · up to 80 kbps':['Экономия · до 80 кбит/с'],
  'Quality applies to newly resolved streams. Existing cached audio is unchanged. No upsampling or guaranteed lossless.':['Качество применяется к новым потокам. Уже сохранённое аудио не меняется. Без апсемплинга и обещаний lossless.'],
  'All mixes':['Все подборки'],'Updating in background…':['Обновляется в фоне…'],'Could not load wallpaper':['Не удалось загрузить обои'],
  'Direct image, Google Images, Yandex Images or Pinterest share link':['Прямая ссылка, Google Картинки, Яндекс Картинки или Pinterest'],
 },
 init(){
  document.body.classList.add('ui-v33');
  // Migrate only the former unintentional defaults, once. Custom colours remain.
  if(!S.repair33){if(S.vizColor==='white')S.vizColor='cover';S.repair33=true;saveSettings();}
  for(const theme of Object.values(THEME_LIBRARY))if(theme.group==='ironmouse')theme.group='vtuber';
  if(Themes.group==='ironmouse')Themes.group='vtuber';Themes.build();
  if($('lt22Target'))$('lt22Target').value=S.lyricTranslationTarget||'en';
  this.controls();this.preferences();this.categories();this.opacity();
  const colors=()=>{if(S.vizColor==='cover')Viz.recolor();};addEventListener('kryonyx:coverpalette',colors);
  const apply=App.applyKaraoke.bind(App);App.applyKaraoke=(...a)=>{const v=apply(...a);this.mode();return v;};
  const language=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const v=language(...a);this.labelsUI();return v;};
  const sync=App.syncSettingsUI.bind(App);App.syncSettingsUI=(...a)=>{const v=sync(...a);this.opacity();if($('audioQuality33'))$('audioQuality33').value=S.audioQuality||'best';return v;};
  this.labelsUI();this.mode();if(typeof Player!=='undefined'&&Player.paintState)Player.paintState();
 },
 controls(){
  const top=$('sceneTools30');
  const mode=el('select');mode.id='sceneMode33';mode.onchange=()=>{S.karaokeMode=mode.value;App.applyKaraoke();saveSettings();};top.prepend(mode);
  const trBtn=el('button','ib',icon('translate'));trBtn.id='sceneTranslate87';trBtn.type='button';trBtn.setAttribute('aria-pressed','false');trBtn.onclick=()=>{if(!this.translation?.hidden)this.closeTranslation(true);else this.openTranslation(trBtn);};
  const shufBtn=el('button','ib',icon('shuffle'));shufBtn.id='sceneShuffle87';shufBtn.type='button';shufBtn.onclick=()=>$('pShuffle').click();
  const repBtn=el('button','ib',icon('repeat'));repBtn.id='sceneRepeat87';repBtn.type='button';repBtn.onclick=()=>$('pRepeat').click();
  const menu=el('div','scene-menu33');menu.id='sceneMenu33';menu.hidden=true;menu.setAttribute('role','dialog');menu.setAttribute('aria-label',t('Player'));
  const more=el('button','ib',icon('queue'));more.id='sceneMore33';more.setAttribute('aria-expanded','false');more.setAttribute('aria-controls',menu.id);more.onclick=()=>{menu.hidden=!menu.hidden;more.setAttribute('aria-expanded',String(!menu.hidden));if(!menu.hidden)menu.querySelector('button')?.focus();};
  top.insertBefore(trBtn,$('sceneSettings30'));
  top.insertBefore(shufBtn,$('sceneSettings30'));
  top.insertBefore(repBtn,$('sceneSettings30'));
  top.insertBefore(more,$('sceneSettings30'));
  const action=(id,key,fn)=>{const b=el('button','btn g');b.id=id;b.dataset.label33=key;b.onclick=()=>{menu.hidden=true;more.setAttribute('aria-expanded','false');fn();};menu.append(b);};
  action('sceneVideo33','Watch clip',()=>{App.setPlayerControls(true);$('nVideo').click();});
  action('sceneLyrics33','Reload lyrics',()=>$('nLyrics').click());
  action('sceneTranslation33','Lyrics translation',()=>this.openTranslation(trBtn));
  action('sceneQueue33','Queue',()=>{App.setPlayerControls(true);$('pQueue').click();});
  // These remain in More for compact modes, where the full transport is hidden.
  action('sceneShuffle33','Shuffle',()=>$('nShuffle').click());action('sceneRepeat33','Repeat',()=>$('nRepeat').click());
  const tr=el('div','translation-panel33');tr.id='translationPanel33';tr.hidden=true;tr.setAttribute('role','dialog');tr.setAttribute('aria-label',t('Lyrics translation'));const close=el('button','ib',icon('close'));close.id='translationClose33';close.onclick=()=>this.closeTranslation(true);tr.append(close,$('lyricsTranslate22'));this.translation=tr;
  $('now').append(menu);document.body.append(tr);this.transport();
  // Keep IDs for existing integrations but remove the duplicate toolbar.
  for(const id of ['nClose','nVideo','nCtl','nFocus','nLyrics','nQueue'])$(id)?.setAttribute('hidden','');
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('#sceneMenu33,#sceneMore33')){menu.hidden=true;more.setAttribute('aria-expanded','false');}if(!tr.hidden&&!tr.contains(e.target)&&!this.translationAnchor?.contains(e.target))this.closeTranslation(false);});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&(!menu.hidden||!tr.hidden)){e.preventDefault();e.stopImmediatePropagation();const wasTranslation=!tr.hidden;menu.hidden=true;more.setAttribute('aria-expanded','false');if(wasTranslation)this.closeTranslation(true);else more.focus();}},true);
  const track=Karaoke.onTrack.bind(Karaoke);Karaoke.onTrack=async(...a)=>{this.closeTranslation(false);return track(...a);};
  const position=()=>{if(!tr.hidden)this.positionTranslation();};addEventListener('resize',position);addEventListener('scroll',position,true);window.visualViewport?.addEventListener('resize',position);window.visualViewport?.addEventListener('scroll',position);this.translationObserver=new ResizeObserver(position);this.translationObserver.observe(tr);new MutationObserver(()=>{if(!$('now').classList.contains('on'))this.closeTranslation(false);}).observe($('now'),{attributes:true,attributeFilter:['class']});
 },
 openTranslation(anchor){
  const tr=this.translation;this.translationAnchor=anchor||$('sceneTranslate87')||$('sceneMore33');this.translationObserver.disconnect();this.translationObserver.observe(tr);if(this.translationAnchor)this.translationObserver.observe(this.translationAnchor);
  tr.hidden=false;$('lyricsTranslate22').open=true;$('sceneTranslate87')?.classList.add('on');$('sceneTranslate87')?.setAttribute('aria-pressed','true');this.positionTranslation();$('lt22Target').focus({preventScroll:true});
  if(!this.translationFrame){let last=0,key='';const tick=now=>{if(tr.hidden){this.translationFrame=0;return;}if(now-last>=120){last=now;const r=this.translationAnchor.getBoundingClientRect(),p=tr.getBoundingClientRect();const next=[r.left,r.top,r.width,r.height,p.width,p.height,innerWidth,innerHeight].join(',');if(next!==key){key=next;this.positionTranslation();}}this.translationFrame=requestAnimationFrame(tick);};this.translationFrame=requestAnimationFrame(tick);}
 },
 closeTranslation(focus){if(!this.translation||this.translation.hidden)return;this.translation.hidden=true;$('sceneTranslate87')?.classList.remove('on');$('sceneTranslate87')?.setAttribute('aria-pressed','false');if(this.translationFrame){cancelAnimationFrame(this.translationFrame);this.translationFrame=0;}if(focus&&this.translationAnchor?.isConnected)this.translationAnchor.focus({preventScroll:true});},
 positionTranslation(){
  const tr=this.translation,anchor=this.translationAnchor;if(!tr||tr.hidden||!anchor)return;
  const viewport=window.visualViewport, left=viewport?.offsetLeft||0, top=viewport?.offsetTop||0, width=viewport?.width||innerWidth, height=viewport?.height||innerHeight, margin=8, gap=8;
  // Rectangles and the visual viewport use screen CSS pixels; positioned
  // values inside a zoomed body use its unzoomed CSS pixels.
  const zoom=Number.parseFloat(getComputedStyle(document.body).zoom)||1;
  tr.style.maxWidth=(Math.max(0,width-2*margin)/zoom)+'px';tr.style.maxHeight=(Math.max(0,height-2*margin)/zoom)+'px';
  const a=anchor.getBoundingClientRect(),p=tr.getBoundingClientRect();
  const x=Math.max(left+margin,Math.min(a.right-p.width,left+width-margin-p.width));
  const below=a.bottom+gap,above=a.top-gap-p.height;
  const y=below+p.height<=top+height-margin?below:above>=top+margin?above:Math.max(top+margin,Math.min(below,top+height-margin-p.height));
  tr.style.left=(x/zoom)+'px';tr.style.top=(y/zoom)+'px';
 },
 mode(){
  if($('sceneMode33'))$('sceneMode33').value=['split','focus','cinema','disc'].includes(S.karaokeMode)?S.karaokeMode:'split';
  if($('sceneMode33'))$('sceneMode33').title=$('sceneMode33').selectedOptions[0]?.textContent||t('Player mode');
  $('now')?.classList.remove('chrome-hidden38');
  $('now')?.classList.toggle('float33',!!S.spin&&!S.noAnim);const compact=['focus','cinema'].includes(S.karaokeMode),changed=$('now').classList.contains('compact-transport33')!==compact;$('now').classList.toggle('compact-transport33',compact);if(changed)requestAnimationFrame(()=>{if(Karaoke.synced&&Karaoke.follow)Karaoke.center(true);});
 },
 transport(){
  const dock=el('div','compact-dock33');dock.id='sceneDock33';
  dock.innerHTML='<div class="compact-seek33"><span id="s33Cur">0:00</span><div class="track" id="s33Track" tabindex="0" role="slider" aria-valuemin="0" aria-valuemax="100"><div class="rail"></div><div class="fill" id="s33Fill"></div><div class="knob"></div></div><span id="s33Dur">0:00</span></div><div class="compact-buttons33"></div>';
  const actions=dock.querySelector('.compact-buttons33');
  for(const [id,key,ico,fn]of [['s33Prev','Previous','prev',()=>Player.prev()],['s33Play','Play','play',()=>Player.toggle()],['s33Next','Next','next',()=>Player.next(false)]]){const b=el('button','ib',icon(ico));b.id=id;b.dataset.action33=key;b.setAttribute('aria-label',t(key));b.onclick=fn;actions.append(b);}
  $('now').append(dock);Player.bindSeek($('s33Track'));
  $('s33Track').onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();e.stopPropagation();if(e.key==='Home')Player.seek(0);else if(e.key==='End')Player.seek(1);else Player.nudge(e.key==='ArrowRight'?5:-5);};
  const update=()=>{const playing=!Player.audio.paused&&!Player.audio.ended,key=playing?'Pause':'Play';const play=$('s33Play');if(play.dataset.state40!==key){play.dataset.state40=key;play.innerHTML=icon(playing?'pause':'play');}paintAttr40(play,'title',t(key));paintAttr40(play,'aria-label',t(key));const duration=Player.realDuration(),pos=(Player.seeking||Player.holdUntilSeeked)&&Player.seekRatio!=null?Player.seekRatio*duration:Player.audio.currentTime;paintAttr40($('s33Track'),'aria-label',t('Seek'));paintAttr40($('s33Track'),'aria-valuenow',String(duration?Math.round(pos/duration*100):0));paintAttr40($('s33Track'),'aria-valuetext',fmt(pos)+' / '+fmt(duration));};
  for(const name of ['paintState','paintTime']){const old=Player[name].bind(Player);Player[name]=(...a)=>{const v=old(...a);update();if(name==='paintState')Player.paintLoading();return v;};}
  update();Player.paintTime();Player.paintProgress();Player.paintLoading();
 },
 preferences(){
  const pane=document.querySelector('.pane[data-pane="look2"]')||$('sWallOpacity')?.closest('.pane');
  const row=el('label','set');row.id='opacityRow33';const name=el('span');name.dataset.label33='Interface opacity';const out=el('output');out.id='opacityOut33';const input=el('input');input.type='range';input.min=0;input.max=100;input.step=1;input.id='panelOpacity33';input.value=S.panelOpacity33??75;input.setAttribute('aria-labelledby','opacityLabel33');name.id='opacityLabel33';input.oninput=()=>{S.panelOpacity33=+input.value;if(out)out.value=Math.round(S.panelOpacity33)+'%';if(!this._opacityRaf){this._opacityRaf=requestAnimationFrame(()=>{this._opacityRaf=0;this.opacity();});}};input.onchange=()=>saveSettings();row.append(name,out,input);const glass=$('sGlass')?.closest('.set');if(glass)glass.after(row);else pane?.append(row);
  const audio=el('label','set');const label=el('span');label.id='qualityLabel33';label.dataset.label33='Audio quality';const select=el('select');select.id='audioQuality33';select.setAttribute('aria-labelledby',label.id);select.onchange=()=>{S.audioQuality=select.value;Player._prefetchController30?.abort();Player._prefetchKey30=null;saveSettings(true);};audio.append(label,select);const note=el('p','hint');note.dataset.label33='Quality applies to newly resolved streams. Existing cached audio is unchanged. No upsampling or guaranteed lossless.';document.querySelector('.pane[data-pane="sound"]')?.append(audio,note);
  $('wallUrl')?.setAttribute('placeholder',t('Direct image, Google Images, Yandex Images or Pinterest share link'));
  const old=Look.apply.bind(Look);Look.apply=(...a)=>{const v=old(...a);this.opacity();this.mode();return v;};
 },
 opacity(){const v=Number(S.panelOpacity33??75);const opacity=Math.min(1,Math.max(0,Number.isFinite(v)?v/100:.75));for(const id of ['side','player','workspaceNavBar','top','mSettings','queue']){const node=$(id);if(node)node.style.setProperty('--panel-opacity33',opacity);}if($('opacityOut33'))$('opacityOut33').value=Math.round(opacity*100)+'%';if($('panelOpacity33')&&document.activeElement!==$('panelOpacity33'))$('panelOpacity33').value=Math.round(opacity*100);},
 labelsUI(){
  document.querySelectorAll('[data-label33]').forEach(n=>n.textContent=t(n.dataset.label33));
  const select=$('sceneMode33');select.setAttribute('aria-label',t('Player mode'));select.replaceChildren();for(const [id,key]of [['split','Lyrics & artwork'],['focus','Lyrics only'],['cinema','Cinema'],['disc','Disc']]){const o=el('option','',t(key));o.value=id;select.append(o);}
  $('sceneMore33').title=t('More');$('sceneMore33').setAttribute('aria-label',t('More'));$('translationClose33').setAttribute('aria-label',t('Close'));
  if($('sceneTranslate87')){$('sceneTranslate87').title=t('Lyrics translation');$('sceneTranslate87').setAttribute('aria-label',t('Lyrics translation'));}
  if($('sceneShuffle87')){$('sceneShuffle87').title=t('Shuffle');$('sceneShuffle87').setAttribute('aria-label',t('Shuffle'));}
  if($('sceneRepeat87')){$('sceneRepeat87').title=t('Repeat');$('sceneRepeat87').setAttribute('aria-label',t('Repeat'));}
  const quality=$('audioQuality33');quality.replaceChildren();for(const [v,key]of [['best','Best available source'],['balanced','Balanced · up to 160 kbps'],['data','Data saver · up to 80 kbps']]){const o=el('option','',t(key));o.value=v;quality.append(o);}quality.value=S.audioQuality||'best';this.mode();this.categoryLabels();
 },
 categories(){
  this.category='all';const host=el('div','recommend-categories33');host.id='homeCategories33';host.setAttribute('role','group');$('homeFilter31').append(host);
  const receive=Home31.receive.bind(Home31);Home31.receive=data=>{receive(data);this.categoryLabels();Home31.render();};
  const filter=Home31.filtered.bind(Home31);Home31.filtered=()=>{const items=filter();if(this.category==='all')return items;const row=this.categoryRows36().find(x=>x.key===this.category)?.row;const ids=new Set((row?.items||[]).map(x=>x.id));return items.filter(x=>ids.has(x.id));};this.categoryLabels();
 },
 categoryRows36(){
  return (Home31.data?.rows||[]).map((row,index)=>({row,key:row.id!=null&&String(row.id)!==''?'id:'+String(row.id):'row:'+index})).filter(({row})=>!row.unresolved&&(row.kind||'tracks')===(Home31.kind||'tracks'));
 },
 categoryLabels(){
  const host=$('homeCategories33');if(!host)return;host.replaceChildren();const rows=this.categoryRows36();
  if(!rows.some(x=>x.key===this.category))this.category='all';
  for(const [id,key]of [['all',t('All mixes')],...rows.map(({row,key})=>[key,row.title||t('Recommendations')])]){const b=el('button','chip'+(id===this.category?' on':''));b.textContent=key;b.setAttribute('aria-pressed',String(id===this.category));b.onclick=()=>{this.category=id;Home31.limit=24;this.categoryLabels();Home31.render();};host.append(b);}
 }
};
for(const [key,values]of Object.entries(Repair33.labels))PACKS.ru[key]=values[0];
const boot33=App.boot.bind(App);App.boot=async function(...a){await boot33(...a);Repair33.init();};
