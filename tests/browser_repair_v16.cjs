'use strict';
const{chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs'),path=require('path');
const OUT=path.join(__dirname,'../verification/repair-v16');fs.mkdirSync(OUT,{recursive:true});
(async()=>{
 const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
 const p=await b.newPage({viewport:{width:1440,height:1000}}),errors=[],checks=[];
 p.on('pageerror',e=>errors.push(e.message));const check=(n,v)=>{assert(v,n);checks.push(n);console.log('PASS',n)};
 await p.goto('http://127.0.0.1:8779');await p.waitForFunction(()=>document.body.classList.contains('ui-v9'));
 check('no boot step failed',await p.evaluate(()=>!App.bootErrors?.length));
 const track={id:'local:qa0',title:'An exceptionally long track title with a second half that must scroll into view '.repeat(3),artist:'Very long artist name and another collaborator with a long nickname '.repeat(2),source:'local',duration:143,thumbnail:'/img/avatars/portrait-v12-ironmouse-season-2.png'};
 await p.evaluate(track=>{S.lang='ru';setLang('ru');S.noAnim=false;Player.current=track;Player.paintTrack();Player.paintProgress(.986);},track);await p.waitForTimeout(100);
 check('progress fill and knob agree at end of track',await p.evaluate(()=>{const t=$('pTrack').getBoundingClientRect(),f=$('pFill').getBoundingClientRect(),k=$('pKnob').getBoundingClientRect();return Math.abs(f.width/t.width-.986)<.005&&Math.abs((k.left+k.width/2)-(f.left+f.width))<2}));
 check('long track and artist both use conveyor',await p.evaluate(()=>['pTitle','pArtist'].every(id=>$(id).classList.contains('kx-running'))));
 check('one-way conveyor has duplicate hidden from assistive tech',await p.evaluate(()=>['pTitle','pArtist'].every(id=>$(id).querySelectorAll('.kx-marquee-copy').length===2&&$(id).querySelector('[aria-hidden=true]'))));
 check('short metadata has no conveyor',await p.evaluate(()=>{const n=document.createElement('div');n.style.width='400px';document.body.append(n);KMarquee.set(n,'Short');const result=!n.classList.contains('kx-running');n.remove();return result}));
 check('reduced motion stops conveyor',await p.evaluate(()=>{const n=$('pTitle');KMarquee.set(n,Player.current.title,true);const result=!n.classList.contains('kx-running');KMarquee.set(n,Player.current.title,false);return result}));
 check('theme selection never changes avatar or posts avatar API',await p.evaluate(async()=>{
  const id=S.avatar,active=Avatars.id;let mutations=0;const old=window.fetch;window.fetch=(...a)=>{if(String(a[0]).endsWith('/api/avatar')&&a[1]?.method==='POST')mutations++;return old(...a)};
  try{for(const s of ['vt-ironmouse','vt-ironmouse-season-1','vt-ironmouse-season-2','vt-ironmouse-season-3','vt-ironmouse-season-4'])useTheme('sketch:'+s);return id===S.avatar&&active===Avatars.id&&$('brandAva').src.includes(id)&&mutations===0}finally{window.fetch=old;}
 }));
 check('Ironmouse and seasons lead the sketch gallery',await p.evaluate(()=>{ThemeStudio.filter='all';ThemeStudio.query='';return ThemeStudio.entries().slice(0,5).map(x=>x[0]).join(',')==='vt-ironmouse,vt-ironmouse-season-1,vt-ironmouse-season-2,vt-ironmouse-season-3,vt-ironmouse-season-4'}));
 check('season zero unavailable in themes',await p.evaluate(()=>!SKETCH_SKINS['vt-ironmouse-season-0']&&!THEMES['sketch:vt-ironmouse-season-0']));
 await p.evaluate(()=>{Workspace.openSettings();App.openPane('look');});
 check('switch dot remains inside and matches checked state',await p.evaluate(()=>{const n=document.querySelector('[data-sw=flat]');n.classList.add('on');const c=getComputedStyle(n,'::after'),left=parseFloat(c.left),w=parseFloat(c.width);return c.transform==='none'&&left>15&&left+w<=n.clientWidth+1}));
 await p.evaluate(()=>{Workspace.update({sidebarCollapsed:true});S.lang='ru';setLang('ru');Workspace.playerMenu({clientX:1100,clientY:900});});
 check('Russian player menu and More tooltip translated synchronously',await p.evaluate(()=>$('workspacePlayerMore').title==='Ещё'&&$('ctxMenu').textContent.includes('Очередь')&&!$('ctxMenu').textContent.includes('Settings')));
 await p.waitForTimeout(350);check('extended menu stays within the viewport',await p.locator('#ctxMenu').evaluate(n=>{const r=n.getBoundingClientRect();return r.top>=9&&r.bottom<=innerHeight-9}));await p.screenshot({path:OUT+'/controls-menu-ru.png'});
 await p.evaluate(()=>{hideMenu();Workspace.openSettings();App.openPane('look');$('taskbarStripRow').scrollIntoView({block:'center'});});await p.waitForTimeout(900);await p.screenshot({path:OUT+'/settings-ru.png'});
 // Explicit open is separate from play and from the title link.
 check('playlist card has independent Play button',await p.evaluate(()=>{const pl={id:917,name:'Playlist fixture',count:5};const c=Workspace.libraryCard(pl);const button=c.querySelector('[data-play-playlist="917"]');if(!button||c.querySelector('[data-open-playlist]'))return false;const old=Workspace.playPlaylist;let called=false;Workspace.playPlaylist=x=>{called=x.id===917};button.click();Workspace.playPlaylist=old;return called}));
 await p.evaluate(()=>{closeModals();K.playlists=[{id:917,name:'My playlist',count:5},{id:918,name:'A second playlist with a long name',count:8}];App.go('lib');Workspace.renderLibrary();});await p.waitForTimeout(900);await p.screenshot({path:OUT+'/playlists-ru.png'});
 const languageResults=[];
 // Open every settings pane and the clip studio, not just the first screen.
 for(const lang of ['en','ru','es','pt','de','fr','it','tr','pl','uk','zh','ja']){
  await p.evaluate(async lang=>{S.lang=lang;setLang(lang);Workspace.openSettings();for(const n of document.querySelectorAll('.set-nav-i[data-pane]'))App.openPane(n.dataset.pane);closeModals();await Clips.open(null);translateDom();},lang);
  const result=await p.evaluate(()=>{
   const strings=[],walk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
   while(n=walk.nextNode()){const e=n.parentElement;if(!e||e.closest(NO_I18N)||e.closest('script,style,svg'))continue;const v=n.textContent.trim();if(v&&v.length<700)strings.push({text:v,id:e.id,visible:!!e.getClientRects().length});}
   for(const e of document.querySelectorAll('[title],[placeholder],[aria-label]')){if(e.closest('[data-entity-name],[data-no-i18n]'))continue;for(const key of ['title','placeholder','aria-label']){const value=e.getAttribute(key);if(value)strings.push({text:value,id:e.id,attribute:key,visible:!!e.getClientRects().length})}}
   return{lang:LANG,cyrillic:LANG==='en'?strings.filter(x=>/[А-Яа-яЁё]/.test(x.text)):[],clipStatus:$('clipStatus').textContent,bodyText:$('clips').innerText};
  });result.uiResidue=result.cyrillic.filter(x=>x.text!=='Русский'&&!x.text.startsWith('Open artist: Демо')&&!x.text.startsWith('Choose artist: Демо'));languageResults.push(result);
  if(lang==='en'){
   fs.writeFileSync(OUT+'/english-cyrillic-scan.json',JSON.stringify({uiResidue:result.uiResidue,preservedMetadata:result.cyrillic.length-result.uiResidue.length},null,2));
   check('English interface has no Russian UI text or attributes',result.uiResidue.length===0);
   await p.waitForTimeout(900);await p.screenshot({path:OUT+'/clips-en.png'});
  }
  check('clip start labels translated '+lang,await p.evaluate(()=>$('clipStatus').textContent===t('Choose a video from the queue or paste a YouTube link')&&$('clips').textContent.includes(t('Your separate video player'))));
  await p.evaluate(()=>Clips.close());
 }
 await p.evaluate(track=>{S.lang='ru';setLang('ru');closeModals();S.noAnim=false;S.karaokeMode='viz';Player.current=track;Player.paintTrack();App.openNow();App.applyKaraoke();},track);await p.waitForTimeout(1400);
 check('visualizer separates frequency spectrum and timeline',await p.evaluate(()=>!$('vTrack').classList.contains('track')&&$('vProg').classList.contains('track')&&$('vProg').getAttribute('role')==='slider'&&document.querySelectorAll('.viz-frequency span').length===4));
 check('visualizer long title and artist convey',await p.evaluate(()=>$('vizTitleIn').classList.contains('kx-running')&&$('vizArtist').classList.contains('kx-running')));
 check('visualizer uses high DPI canvas backing',await p.evaluate(()=>Viz.spec.width>=Viz.spec.clientWidth&&Viz.spec.height>=Viz.spec.clientHeight));
 check('spectrum canvas stays inside its frequency card',await p.evaluate(()=>{const a=$('vTrack').getBoundingClientRect(),c=Viz.spec.getBoundingClientRect();return Math.abs(c.height-a.height)<3&&c.top>=a.top&&c.bottom<=a.bottom+1}));
 // Deterministic audio fixture to inspect dynamic spectrum without provider requests.
 await p.evaluate(()=>{Player.audio.pause();const bins=new Uint8Array(512);for(let i=0;i<bins.length;i++)bins[i]=Math.round(180*Math.exp(-i/150)*(0.4+0.6*Math.sin(i/13)**2));const old=Player.audio;Player.audio={paused:false,ended:false,duration:143,currentTime:141};Viz.size();for(let i=0;i<50;i++)Viz.drawSpec(bins,'#dad2ff','#9d84ef',.3);Player.audio=old;});
 await p.screenshot({path:OUT+'/visualizer-desktop.png'});await p.setViewportSize({width:390,height:844});await p.waitForTimeout(250);await p.screenshot({path:OUT+'/visualizer-mobile.png'});
 check('mobile visualizer has no page horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await p.goto('http://127.0.0.1:8779/mini.html');await p.setViewportSize({width:480,height:160});await p.waitForSelector('.mini');
 const mini={...track,cover:track.thumbnail,playing:true,position:141,duration:143,labels:{prev:'Назад',next:'Вперёд',pause:'Пауза',play:'Играть',close:'Закрыть',seek:'Перемотка'}};
 await p.evaluate(st=>Mini.update(st),mini);await p.waitForTimeout(80);
 check('mini player title and artist both convey',await p.locator('.mini-t.kx-running,.mini-a.kx-running').count()===2);
 check('mini progress is near the actual end',await p.locator('.mini-seek b').evaluate(n=>n.clientWidth/n.parentElement.clientWidth>.98));
 check('mini seek has translated keyboard slider label',await p.locator('.mini-seek').getAttribute('aria-label')==='Перемотка');await p.screenshot({path:OUT+'/mini-desktop.png'});
 const animationSame=await p.evaluate(st=>{const a=KMarquee.items.get(document.querySelector('.mini-t')).animation;Mini.update(st);return a===KMarquee.items.get(document.querySelector('.mini-t')).animation},mini);check('frequent updates do not restart conveyor',animationSame);
 await p.setViewportSize({width:360,height:128});await p.waitForTimeout(80);check('compact title does not overlap close button',await p.evaluate(()=>document.querySelector('.mini-t').getBoundingClientRect().right<=document.querySelector('.mini .x').getBoundingClientRect().left));check('mini fits minimum native size',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight));await p.screenshot({path:OUT+'/mini-compact.png'});
 await p.evaluate(st=>Mini.update({...st,reducedMotion:true}),mini);check('mini respects reduced motion',await p.locator('.kx-running').count()===0);
 check('no runtime errors',errors.length===0);
 fs.writeFileSync(OUT+'/browser-report.json',JSON.stringify({checks,errors,languages:languageResults.map(x=>({lang:x.lang,untranslatedRussian:x.uiResidue}))},null,2));
 await b.close();console.log('REPAIR_V16_PASS',checks.length);
})().catch(e=>{console.error(e);process.exit(1)});
