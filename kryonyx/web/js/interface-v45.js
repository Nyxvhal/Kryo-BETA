/* v45: atomic first paint, shared seek preview and explicit karaoke actions.
   Reuses the existing media, lyric search, translation and settings pipelines. */
'use strict';
const Interface45 = {
 init(){
  document.body.classList.add('ui-v45');
  this.seekPreview();this.karaokeMenu();this.clips();
  // Persist while dragging, not only on change/blur. Keep the original scene module intact.
  $('panelOpacity33')?.addEventListener('input',()=>saveSettings());
  const old=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const v=old(...a);this.labels();return v;};
  const apply=applyTheme;applyTheme=function(...a){const v=apply(...a);Repair33.opacity();Interface45.clipContrast();return v;};
  this.clipContrast();this.labels();
 },
 clipContrast(){
  const rgb=hex2rgb(S.accent||'#9f80f6').map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
  const lum=.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];
  document.documentElement.style.setProperty('--clip-ink45',lum>.179?'#000':'#fff');
 },
 seekPreview(){
  const tip=el('div','seek-preview45');tip.id='seekPreview45';tip.hidden=true;tip.setAttribute('aria-hidden','true');document.body.append(tip);
  const selector='#pTrack,#pTrackM,#nTrack,#s33Track,#dTrack,#vProg,#albumSeek24';/* v73: #clipSeek has its own tooltip (clips-v69.js); two followed the pointer */const widths=new Map();
  const show=(node,x,y,ratio)=>{
   const duration=node.id==='clipSeek'?Clips.video?.duration:Player.audio?.duration;
   if(!Number.isFinite(duration)||duration<=0){tip.hidden=true;return;}
   const text=fmt(duration*Math.max(0,Math.min(1,ratio)));if(tip.textContent!==text)tip.textContent=text;tip.hidden=false;
   const scale=Number(S.uiScale||100)/100;
   // Fixed children inherit body's zoom. Convert viewport coordinates once.
   // v73: measure once per text length instead of forcing a layout on every move.
   const wkey=text.length+'|'+scale;let width=widths.get(wkey);if(!width){width=tip.getBoundingClientRect().width||54;widths.set(wkey,width);}
   tip.style.left=(Math.max(width/2+8,Math.min(innerWidth-width/2-8,x))/scale)+'px';
   tip.style.top=(Math.max(44,y-12)/scale)+'px';
  };
  let dragging=null;
  document.addEventListener('pointermove',e=>{
   const node=dragging||e.target.closest?.(selector);if(!node){tip.hidden=true;return;}
   if(e.pointerType==='touch'&&!dragging)return;
   const r=node.getBoundingClientRect();if(!r.width){tip.hidden=true;return;}
   // Native range thumbs are inset by half their 14px width.
   const inset=node.id==='clipSeek'?7*(Number(S.uiScale||100)/100):0,ratio=(e.clientX-r.left-inset)/Math.max(1,r.width-2*inset);
   show(node,e.clientX,r.top,ratio);
  },{passive:true});
  document.addEventListener('pointerdown',e=>{if(e.button===0)dragging=e.target.closest?.(selector)||null;},{passive:true});
  const hide=()=>{dragging=null;if(!tip.hidden)tip.hidden=true;};document.addEventListener('pointerup',hide);document.addEventListener('pointercancel',hide);addEventListener('blur',hide);document.addEventListener('scroll',hide,true);
  document.addEventListener('pointerout',e=>{if(!dragging&&e.target.closest?.(selector)&&!e.target.closest(selector).contains(e.relatedTarget))tip.hidden=true;});
  document.addEventListener('focusout',hide);
  document.addEventListener('keydown',e=>{const node=e.target.closest?.(selector);if(!node||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(e.key))return;requestAnimationFrame(()=>{const r=node.getBoundingClientRect(),d=node.id==='clipSeek'?Clips.video?.duration:Player.audio?.duration;const ratio=node.id==='clipSeek'?Number(node.value)/1000:(Player.audio?.currentTime||0)/d;show(node,r.left+r.width*ratio,r.top,ratio);});});
 },
 karaokeMenu(){
  const host=$('sceneTools30'),button=el('button','ib',icon('clock'));button.id='karaokeMenuButton45';button.type='button';button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls','karaokeMenu45');host.insertBefore(button,$('sceneTranslate87')||$('sceneMore33'));
  const menu=el('div','karaoke-menu45');menu.id='karaokeMenu45';menu.hidden=true;menu.setAttribute('role','dialog');host.append(menu);
  const heading=el('b');heading.dataset.label45='Karaoke';menu.append(heading);
  const settings=el('button','btn g');settings.type='button';settings.dataset.label45='Settings';settings.onclick=()=>{$('sceneMenu33').hidden=true;$('sceneMore33').setAttribute('aria-expanded','false');Workspace.openSettings();App.openPane('karaoke');};$('sceneMenu33').append(settings);
  $('sceneSettings30').hidden=true;
  const action=(id,key,fn)=>{const b=el('button','btn g');b.id=id;b.type='button';b.dataset.label45=key;b.onclick=()=>{this.closeKaraoke();fn();};menu.append(b);return b;};
  action('karaokeAuto45','Match this track automatically',()=>{
   if(!Player.current)return;S.autoLyrics=true;saveSettings();App.syncSettingsUI();
   // The existing clearPick guard expects the track the chooser was opened for.
   Karaoke.findFor=Player.current.id;Karaoke.clearPick();
  });
  const label=el('label','karaoke-auto45'),toggle=el('input');toggle.type='checkbox';toggle.id='karaokeAutoToggle45';const text=el('span');text.dataset.label45='Auto-match on track change';label.append(toggle,text);menu.append(label);
  toggle.onchange=()=>{S.autoLyrics=toggle.checked;saveSettings();App.syncSettingsUI();if(Player.current)Karaoke.onTrack(Player.current);};
  const note=el('p','muted');note.dataset.label45='Uses title and artist. Search manually if the match is wrong.';menu.append(note);
  // v19's clean scene hides #kStage, including its only editor button.
  // Expose the same existing action in the already-present karaoke menu.
  // Quick per-track offset; the same value is used by the detailed settings.
  const timing=el('div','karaoke-timing45'),timingLabel=el('div');timingLabel.dataset.label45='Track offset (positive = lyrics earlier)';timing.append(timingLabel);
  const timingControls=el('div','karaoke-timing-controls45');
  for(const [id,text,delta] of [['karaokeTimingMinus45','−1s',-1],['karaokeTimingFineMinus78','−0.1s',-.1],['karaokeTimingFinePlus78','+0.1s',.1],['karaokeTimingPlus45','+1s',1]]){
   const b=el('button','btn g',text);b.type='button';b.id=id;b.onclick=()=>{if(!Player.current||Player.current.id!==Karaoke.trackId)return;const current=+Karaoke.offsets[Karaoke.trackId]||0;Karaoke.nudge(Math.max(-30,Math.min(30,current+delta))-current);};timingControls.append(b);
  }
  const value=el('output');value.id='karaokeTimingValue45';value.setAttribute('aria-live','polite');timingControls.insertBefore(value,timingControls.querySelector('#karaokeTimingFinePlus78'));
  const reset=el('button','btn g');reset.id='karaokeTimingReset45';reset.type='button';reset.dataset.label45='Reset';reset.onclick=()=>Karaoke.resetOffset();timingControls.append(reset);
  const tap=el('button','btn g');tap.id='karaokeTimingTap87';tap.type='button';tap.dataset.label45='Tap · T';tap.onclick=()=>Karaoke.tap();timingControls.append(tap);
  timing.append(timingControls);menu.append(timing);Karaoke.paintSync();
  action('karaokeEdit45','Edit timing',()=>KaraokeEditor.openCurrent());
  action('karaokeStudio45','Karaoke studio',()=>KaraokeTools.open());
  button.onclick=()=>{const open=menu.hidden;this.closeKaraoke();if(open){$('sceneMenu33').hidden=true;$('sceneMore33').setAttribute('aria-expanded','false');menu.hidden=false;button.setAttribute('aria-expanded','true');button.classList.add('on');toggle.checked=!!S.autoLyrics;this.labels();menu.querySelector('button:not(:disabled),input:not(:disabled)')?.focus();}};
  document.addEventListener('pointerdown',e=>{if(!menu.hidden&&!menu.contains(e.target)&&!button.contains(e.target))this.closeKaraoke();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!menu.hidden&&!document.querySelector('.modal.on')){e.preventDefault();e.stopImmediatePropagation();this.closeKaraoke();button.focus();}},true);
  new MutationObserver(()=>{if(!$('now').classList.contains('on'))this.closeKaraoke();}).observe($('now'),{attributes:true,attributeFilter:['class']});
  menu.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();this.closeKaraoke();button.focus();}if(e.key==='Tab'){const a=[...menu.querySelectorAll('button,input')].filter(n=>!n.disabled),i=a.indexOf(document.activeElement);if(e.shiftKey&&i===0){e.preventDefault();a.at(-1).focus();}else if(!e.shiftKey&&i===a.length-1){e.preventDefault();a[0].focus();}}});
  $('nClose').addEventListener('click',()=>this.closeKaraoke());
 },
 closeKaraoke(){if($('karaokeMenu45'))$('karaokeMenu45').hidden=true;$('karaokeMenuButton45')?.setAttribute('aria-expanded','false');$('karaokeMenuButton45')?.classList.remove('on');},
 clips(){
  const root=$('clips'),head=root.querySelector('.cs-head');
  const search=$('clipSearchForm');head.querySelector('div').after(search);
  const advisory=root.querySelector('.cs-advisory'),details=el('details','clip-session45'),summary=document.createElement('summary');
  summary.textContent=t('Configure session');summary.dataset.label45='Configure session';details.append(summary,advisory);root.querySelector('.cs-sidebar').append(details);
  root.querySelector('.cs-eyebrow').setAttribute('data-no-i18n','');
  // Technical setup is optional; video, transport and the queue are primary.
  const tech=el('details','clip-details45'),name=document.createElement('summary');name.dataset.label45='Clip tools';name.textContent=t('Clip tools');tech.append(name);
  root.querySelector('.cs-transport').after(tech);
  for(const node of [root.querySelector('.cs-status'),$('clipProgress'),root.querySelector('.cs-tabs'),...root.querySelectorAll('.cs-panel')])tech.append(node);
  root.querySelectorAll('[data-clip-tab]').forEach(b=>b.addEventListener('click',()=>{tech.open=true;}));
 },
 labels(){
  document.querySelectorAll('[data-label45]').forEach(n=>{n.textContent=t(n.dataset.label45);});
  const b=$('karaokeMenuButton45');if(b){b.title=t('Timing & karaoke');b.setAttribute('aria-label',t('Timing & karaoke'));}
  $('karaokeMenu45')?.setAttribute('aria-label',t('Karaoke'));
  for(const id of ['karaokeSearch45','karaokeAuto45'])if($(id))$(id).disabled=!Player.current;
  if($('karaokeEdit45'))$('karaokeEdit45').disabled=!Player.current||!(Karaoke.document||Karaoke.lines?.length);
 }
};
const boot45=App.boot.bind(App);App.boot=async function(...a){await boot45(...a);Interface45.init();};
