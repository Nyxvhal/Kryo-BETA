/* Theme-native editorial surfaces using existing credited artwork, not donor code. */
'use strict';
const Interface22={
 tr(en,ru){return LANG==='ru'?ru:t(en);},
 init(){
  document.body.classList.add('ui-v22');LyricsTranslate.init();this.gallery();
  if($('studioHero')&&$('homePicks20'))$('studioHero').after($('homePicks20'));
  const apply=Sketch.apply.bind(Sketch);Sketch.apply=()=>{apply();this.identity();};
  const clear=Sketch.clear.bind(Sketch);Sketch.clear=()=>{clear();this.identity();};
  const hero=Home.paintHero.bind(Home);Home.paintHero=(...args)=>{hero(...args);this.identity();};
  const render=ThemeStudio.render.bind(ThemeStudio);ThemeStudio.render=()=>{render();this.gallery();};
  this.identity();this.finder();
 },
 gallery(){
  if(!$('sk10Studio'))return;
  $('sk10Studio').classList.add('gallery22');
  document.querySelectorAll('.sk10-card').forEach(card=>{const id=card.dataset.skinId,s=SKETCH_SKINS[id];card.dataset.family=s.avatar?'character':'paper';const foot=card.querySelector('.sk10-foot span');if(foot)foot.textContent=this.tr(s.avatar?'Character · ':'Paper · ',s.avatar?'Персонаж · ':'Бумага · ')+this.tr(s.dark?'Night':'Light',s.dark?'Тёмная':'Светлая');});
 },
 identity(){
  const hero=$('studioHero');if(!hero)return;
  let note=$('themeIdentity22');
  if(!S.sketch){note?.remove();document.body.removeAttribute('data-sketch22');return;}
  const s=Sketch.skin();document.body.dataset.sketch22=S.sketchSkin;
  if(!note){note=el('div','theme-identity22');note.id='themeIdentity22';hero.append(note);}
  note.replaceChildren();
  const visual=el('div','theme-visual22');
  if(S.themeArtwork!=='clean'&&s.referenceImage){const image=el('img');image.src=s.referenceImage;image.alt=s.name;image.decoding='async';image.onerror=()=>{image.remove();visual.classList.add('art-unavailable');};visual.append(image);}
  else{visual.style.backgroundImage=getComputedStyle(document.body).getPropertyValue('--sk-emblem');visual.classList.add('theme-emblem22');if(!ThemeStudio.motifs[s.doodles]){visual.classList.add('theme-type22');visual.append(el('span','','Aa'));}const swatches=el('div','theme-palette22');for(const color of [s.paper,s.ink,s.sky,s.gold]){const swatch=el('i');swatch.style.background=color;swatches.append(swatch);}visual.append(swatches);}
  const copy=el('div','theme-copy22');copy.append(el('span','',this.tr('YOUR SKETCH EDITION','ТВОЯ СКЕТЧ-ТЕМА')),el('strong','',s.name));
  copy.querySelector('strong').dataset.entityName='';
  const controls=el('div','theme-actions22');const change=el('button','',this.tr('Change theme','Выбрать тему'));change.type='button';change.onclick=()=>{Workspace.openSettings();App.openPane('sketch');Sketch.build();};controls.append(change);copy.append(controls);note.append(visual,copy);
 },
 finder(){
  const file=$('songFinderFile');if(!file||$('finderFile22'))return;
  const pick=el('button','btn g',t('Choose a file'));pick.id='finderChoose22';pick.type='button';pick.setAttribute('aria-controls','songFinderFile');pick.onclick=e=>{e.preventDefault();file.click();};file.classList.add('file-input22');file.tabIndex=-1;file.after(pick);
  const preview=el('div','finder-file22');preview.id='finderFile22';preview.hidden=true;preview.dataset.noI18n='';file.after(preview);
  file.addEventListener('change',()=>{if(SongFinder.searching)SongFinder.cancel();const f=file.files[0];preview.hidden=!f;preview.textContent=f?f.name+' · '+(f.size/1024/1024).toFixed(1)+' MB':'';});
  const help=el('p','finder-help22');help.textContent=this.tr('Choose a clear music passage. Speech, silence, background noise and remixes can prevent recognition.','Выбери отрывок, где хорошо слышна музыка. Речь, тишина, шум и ремиксы могут помешать распознаванию.');$('songFinderOffset').closest('label').after(help);
 }
};
const boot22=App.boot.bind(App);App.boot=async function(...args){await boot22(...args);Interface22.init();};
