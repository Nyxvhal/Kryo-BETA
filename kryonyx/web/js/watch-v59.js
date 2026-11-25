/* v59: conventional video surface. Native media, gate and downloads remain v57. */
'use strict';
const Watch58={
 ready:false,t(en,ru){return LANG==='ru'?ru:en},
 icon(name){return KryoIcons60.create(name)},
 button(id,icon,label,fn){let b=document.createElement('button');b.id=id;b.type='button';b.className='watch-icon58';this.label(b,icon,label);b.onclick=fn;return b},
 label(b,icon,label){b.replaceChildren(this.icon(icon));b.title=label;b.setAttribute('aria-label',label)},
 init(){if(this.ready)return;this.ready=true;document.body.classList.add('ui-v58');const root=$('clips'),stage=$('clipStage');root.classList.add('watch58');this.stage=stage;
 const transport=root.querySelector('.cs-transport');stage.append(transport);transport.classList.add('watch-transport58');transport.setAttribute('aria-label',this.t('Video controls','Управление видео'));
 const controls=transport.querySelector('.cs-controls');this.controls=controls;
 this.label($('clipNext'),'next',this.t('Next video','Следующий клип'));this.label($('clipFull'),'full',this.t('Fullscreen (F)','Во весь экран (F)'));
 const mute=this.button('watchMute58','volume',this.t('Mute (M)','Выключить звук (M)'),()=>{Clips.muted=!Clips.muted;Clips.applyAudio();this.audio()});const volume=root.querySelector('.cs-volume');for(const n of [...volume.childNodes])if(n.nodeType===3)n.remove();volume.prepend(mute);$('clipVolume').setAttribute('aria-label',this.t('Volume','Громкость'));
 const spacer=document.createElement('span');spacer.className='watch-spacer58';controls.insertBefore(spacer,$('clipFull'));
 const settings=this.button('watchSettings58','settings',this.t('Settings','Настройки'),()=>this.menu(!this.menuOpen));settings.setAttribute('aria-expanded','false');settings.setAttribute('aria-controls','watchMenu58');
 const unused=document.createElement('div');unused.id='watchUnused59';unused.hidden=true;unused.inert=true;for(const id of ['clipPip','clipTheater'])unused.append($(id));root.append(unused);
 controls.replaceChildren($('clipPlay'),$('clipNext'),volume,$('clipTime'),spacer,settings,$('clipFull'));
 const caption=$('clipCaption');caption.disabled=true;caption.onchange=null;caption.closest('label').hidden=true;caption.closest('label').classList.add('watch-removed59');
 const menu=document.createElement('div');menu.id='watchMenu58';menu.className='watch-menu58';menu.hidden=true;menu.setAttribute('role','region');menu.setAttribute('aria-label',this.t('Playback settings','Настройки просмотра'));
 for(const [id,en,ru]of [['clipQuality','Quality','Качество'],['clipSpeed','Playback speed','Скорость воспроизведения']]){const select=$(id),oldLabel=select.parentElement;if(id==='clipQuality'){const change=select.onchange;select.onchange=(...a)=>{this.menu(false);return change?.apply(select,a)}}const row=document.createElement('label');const text=document.createElement('span');text.textContent=this.t(en,ru);row.append(text,select);menu.append(row);if(oldLabel?.tagName==='LABEL')oldLabel.remove()}
 const hint=document.createElement('p');hint.id='watchHint58';hint.textContent=this.t('Quality availability depends on the source.','Доступное качество зависит от источника.');menu.append(hint);stage.append(menu);
 const center=this.button('watchCenter58','play',this.t('Play video','Смотреть клип'),()=>{Clips.toggle();this.show()});stage.append(center);
 const prevPaint=Clips.paintPlay.bind(Clips);Clips.paintPlay=()=>{prevPaint();this.paint()};const prevAudio=Clips.applyAudio.bind(Clips);Clips.applyAudio=()=>{prevAudio();this.audio()};
 const prevClose=Clips.close.bind(Clips);Clips.close=async(...a)=>{clearTimeout(this.hideTimer);this.menu(false);await prevClose(...a)};
 stage.addEventListener('pointermove',()=>this.show());stage.addEventListener('pointerleave',()=>{if(Clips.wantPlay&&!this.menuOpen)stage.classList.remove('controls-visible58')});stage.addEventListener('focusin',()=>this.show());
 Clips.video.addEventListener('click',()=>{if(matchMedia('(pointer:coarse)').matches){this.show();return}Clips.toggle();this.show()});Clips.video.addEventListener('dblclick',()=>Clips.fullscreen());Clips.video.addEventListener('play',()=>this.paint());Clips.video.addEventListener('pause',()=>this.paint());
 document.addEventListener('pointerdown',e=>{if(this.menuOpen&&!menu.contains(e.target)&&!settings.contains(e.target))this.menu(false)});
 settings.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();this.menu(false);settings.focus()}});menu.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();this.menu(false);settings.focus()}},true);
 const oldKey=Clips.onKey.bind(Clips);Clips.onKey=e=>{if(this.menuOpen&&e.key==='Escape'){e.preventDefault();this.menu(false);$('watchSettings58').focus();return}oldKey(e)};
 const oldMode=Video57.mode.bind(Video57);Video57.mode=name=>{oldMode(name);if(name==='watch'){Video57.heading(this.t('Up next','Следующие клипы'));$('clipListLabel').textContent=this.t('Videos','Клипы')+' · '+Clips.items.length;this.paint();this.show()}else{clearTimeout(this.hideTimer);this.menu(false)}};
 $('clipStage').addEventListener('fullscreenchange',()=>this.show());const oldLabels58=UI52.clipLabels.bind(UI52);UI52.clipLabels=(...a)=>{const r=oldLabels58(...a);this.relabel();return r};this.relabel();this.paint();this.audio();
 },
 relabel(){const note=$('clipPanel-tools').querySelector('.cs-note');if(note)note.textContent=this.t('Space — pause · ← / → — seek · M — mute · F — fullscreen · N — next.','Пробел — пауза · ← / → — перемотка · M — звук · F — полный экран · N — следующий клип.');if($('watchHint58'))$('watchHint58').textContent=this.t('Quality availability depends on the source.','Доступное качество зависит от источника.');for(const [id,icon,en,ru]of [['clipNext','next','Next video','Следующий клип'],['clipFull','full','Fullscreen (F)','Во весь экран (F)']])this.label($(id),icon,this.t(en,ru));this.paint();this.audio()},
 menu(open){this.menuOpen=!!open;if($('watchMenu58'))$('watchMenu58').hidden=!open;$('watchSettings58')?.setAttribute('aria-expanded',String(!!open));if(open)this.show()},
 show(){clearTimeout(this.hideTimer);this.stage.classList.add('controls-visible58');if(Clips.wantPlay&&!this.menuOpen)this.hideTimer=setTimeout(()=>{if(!this.stage.contains(document.activeElement))this.stage.classList.remove('controls-visible58')},2600)},
 paint(){if(!this.ready)return;this.label($('clipPlay'),Clips.wantPlay?'pause':'play',Clips.wantPlay?this.t('Pause (Space)','Пауза (Пробел)'):this.t('Play (Space)','Воспроизвести (Пробел)'));this.stage.classList.toggle('paused58',!Clips.wantPlay);$('watchCenter58').hidden=Clips.wantPlay||!Clips.job?.video_url;this.show()},
 audio(){if(!this.ready)return;this.label($('watchMute58'),Clips.muted?'mute':'volume',Clips.muted?this.t('Unmute (M)','Включить звук (M)'):this.t('Mute (M)','Выключить звук (M)'))}
};
const boot58=App.boot.bind(App);App.boot=async function(...a){await boot58(...a);Watch58.init()};
