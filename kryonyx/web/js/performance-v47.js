/* Render only the current transport; audio and lyric timing keep their original clock. */
'use strict';
const Performance47={
 ready:false,force:false,tracks:new WeakMap(),bgAt:0,bgHit:0,
 host(node){if(!node)return '';const id=node.id;const map={pFill:'pTrack',pFillM:'pTrackM',nFill:'nTrack',dFill:'dTrack',vFill:'vProg',s33Fill:'s33Track'};if(map[id])return map[id];if(node.classList.contains('knob'))return node.parentElement?.id||'';if(node.closest('#albumSeek24'))return 'albumSeek24';return '';},
 visible(id){
  if(this.force)return true;
  if(document.hidden||document.querySelector('.modal.on')||Clips.active)return false;
  if(!$('now')?.classList.contains('on'))return id==='pTrack'||id==='pTrackM';
  if(Viz.on)return id==='vProg';if(Disc.on)return id==='dTrack';
  if(ReferenceScene24.active())return id==='albumSeek24';return id==='nTrack'||id==='s33Track';
 },
 paint(node,name,value,original){
  const host=this.host(node);if(!host||!['width','left'].includes(name))return original(node,name,value);
  if(!this.visible(host))return;
  const ratio=Number.parseFloat(value)/100;if(!Number.isFinite(ratio))return original(node,name,value);
  if(name==='width'){
   if(!node.classList.contains('gpu-fill47'))node.classList.add('gpu-fill47');
   original(node,'width','100%');original(node,'transform','scaleX('+Math.max(0,Math.min(1,ratio)).toFixed(5)+')');return;
  }
  const parent=node.parentElement;if(!parent)return original(node,name,value);
  let record=this.tracks.get(parent);if(!record){record={width:0,knob:node,ratio};this.tracks.set(parent,record);this.resize.observe(parent);}record.ratio=ratio;
  if(!record.width)return original(node,name,value);
  original(node,'left','0px');original(node,'translate',(record.width*ratio).toFixed(2)+'px 0px');
 },
 init(){
  if(this.ready)return;this.ready=true;document.body.classList.add('ui-v47');
  this.resize=new ResizeObserver(entries=>{for(const e of entries){if(!e.target.isConnected){this.resize.unobserve(e.target);this.tracks.delete(e.target);continue;}const r=this.tracks.get(e.target);if(!r)continue;r.width=e.contentRect.width;if(r.width){paintStyle40(r.knob,'left',(r.ratio*100)+'%');}}});
  const style=paintStyle40;paintStyle40=(node,name,value)=>this.paint(node,name,value,style);
  // Inactive sleep timers need no repeated DOM writes.
  const sleep=InterfaceV7.tickSleep.bind(InterfaceV7);let sleepKey='';InterfaceV7.tickSleep=()=>{const key=[InterfaceV7.sleepDeadline||0,LANG,!!$('ui7SleepDialogStatus')].join('|');if(!InterfaceV7.sleepDeadline&&key===sleepKey)return;sleepKey=key;return sleep();};
  // The translation text changes at lyric boundaries, not at the display refresh rate.
  const scene=LyricsTranslate.scene.bind(LyricsTranslate);let last=[];
  LyricsTranslate.scene=()=>{const i=Karaoke.synced?Karaoke.indexAt(Karaoke.clock(Player.audio?.currentTime||0)):-1,d=Karaoke.lines[Disc.line],v=Karaoke.lines[i];const key=[Disc.on,Viz.on,Karaoke.synced,LyricsTranslate.result,LyricsTranslate.renderSignature,S.lyricTranslationVisible,Disc.words?.classList.contains('gone'),d?LyricsTranslate.value(d,Disc.line):'',v?LyricsTranslate.value(v,i):'',$('discTranslation22'),$('vizTranslation22')];if(key.every((v,i)=>v===last[i])&&last.length)return;last=key;return scene();};
  // Cap background pixels in classic scenes too; foreground spectrum stays sharp.
  if(typeof Visualizer32!=='undefined'){
   Viz.size=()=>Visualizer32.size();
   const center=Viz.center.bind(Viz);Viz.center=()=>{const c=center();return c?{x:c.x*Viz.bg.width/Math.max(1,Viz.w),y:c.y*Viz.bg.height/Math.max(1,Viz.h)}:null;};
   // Background is a bounded 30fps layer. Spectrum and audio analysis retain the frame clock.
   const bg=Viz.drawBg.bind(Viz);Viz.drawBg=(...args)=>{
    const now=performance.now(),playing=!Player.audio?.paused&&!Player.audio?.ended;
    const fps=Visualizer32.budget().background;
    if(playing&&this.bgAt&&now-this.bgAt<1000/fps-.8)return;
    const dt=Viz.dt,k=Viz.k,gap=this.bgAt?Math.min(.08,(now-this.bgAt)/1000):1/30;this.bgAt=now;
    Viz.dt=gap;Viz.k=gap*60;
    if(playing&&Karaoke._beatAt&&Karaoke._beatAt!==this.bgHit&&now-Karaoke._beatAt<180){args[3]=1;this.bgHit=Karaoke._beatAt;}
    try{return bg(...args);}finally{Viz.dt=dt;Viz.k=k;}
   };
   const reset=Viz.reset.bind(Viz);Viz.reset=(...a)=>{this.bgAt=0;this.bgHit=Karaoke._beatAt||0;return reset(...a);};
  }
  const open=App.openNow.bind(App);App.openNow=(...a)=>{const r=open(...a);this.refresh();return r;};
  const apply=App.applyKaraoke.bind(App);App.applyKaraoke=(...a)=>{this.bgAt=0;const r=apply(...a);this.refresh();return r;};
  $('nClose').addEventListener('click',()=>queueMicrotask(()=>this.refresh()));
  addEventListener('resize',()=>{this.bgAt=0;});document.addEventListener('visibilitychange',()=>{this.bgAt=0;});
  const fluid=FluidCover24.visible.bind(FluidCover24);FluidCover24.visible=()=>!Clips.active&&!$('clips').classList.contains('on')&&fluid();
  const videoTick=VMedia.tick.bind(VMedia);VMedia.tick=()=>{if(document.hidden||Clips.active||document.querySelector('.modal.on')){for(const v of [...Object.values(VMedia.vids),$('nowVid')])if(v&&!v.paused)v.pause();return;}return videoTick();};
  const clipsOpen=Clips.open.bind(Clips);Clips.open=(...a)=>{const r=clipsOpen(...a);document.body.classList.add('clip-open47');FluidCover24.sync();VMedia.tick();return r;};
  const clipsClose=Clips.close.bind(Clips);Clips.close=async(...a)=>{try{return await clipsClose(...a);}finally{document.body.classList.toggle('clip-open47',Clips.active);FluidCover24.sync();VMedia.tick();}};
  this.refresh();Motion47.init();
 },
 refresh(){if(!Player.audio)return;this.force=true;try{Player.paintProgress();Player.paintTime();Player.paintBuffer();}finally{this.force=false;}}
};
const Motion47={
 active:new Set(),reduce:matchMedia('(prefers-reduced-motion: reduce)'),lastTrack:'',
 allowed(){return !S.noAnim&&!this.reduce.matches&&!document.hidden;},
 enter(node){if(!node?.animate||!node.isConnected||!this.allowed())return;for(const a of this.active)if(a.effect?.target===node)a.cancel();const a=node.animate([{opacity:.5,transform:'translateY(4px)'},{opacity:1,transform:'none'}],{duration:180,easing:'cubic-bezier(.2,.75,.25,1)'});this.active.add(a);const release=setTimeout(()=>{a.cancel();this.active.delete(a);},400);a.finished.catch(()=>{}).finally(()=>{clearTimeout(release);this.active.delete(a);});},
 cancel(){for(const a of this.active)a.cancel();this.active.clear();},
 init(){
  const stagger=()=>[...$('rows').children].slice(0,12).forEach((n,i)=>n.style.setProperty('--order47',String(i)));
  const render=Home31.render.bind(Home31);Home31.render=(...a)=>{const r=render(...a);stagger();return r;};stagger();
  const paint=Player.paintTrack.bind(Player);Player.paintTrack=(...args)=>{const r=paint(...args),id=Player.current?.id||'';if(id!==this.lastTrack){this.lastTrack=id;this.enter($('pCover'));}return r;};
  const pane=App.openPane.bind(App);App.openPane=(name,...a)=>{const r=pane(name,...a);this.enter(document.querySelector('.pane[data-pane="'+CSS.escape(name)+'"]'));return r;};
  const theme=applyTheme;applyTheme=(...a)=>{const r=theme(...a);if(!this.allowed())this.cancel();return r;};
  this.reduce.addEventListener('change',()=>{if(!this.allowed())this.cancel();});document.addEventListener('visibilitychange',()=>{if(document.hidden)this.cancel();});
 }
};
const boot47=App.boot.bind(App);App.boot=async function(...a){await boot47(...a);Performance47.init();};
