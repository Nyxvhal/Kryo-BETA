/* Shared scene backgrounds and bounded beat accents; no additional audio graph or frame loop. */
'use strict';
const Scene46={
 init(){
  document.body.classList.add('ui-v46');
  const apply=KCustom.apply.bind(KCustom);KCustom.apply=(...a)=>{const v=apply(...a);this.background();return v;};
  const video=VMedia.applyBg.bind(VMedia);VMedia.applyBg=async(...a)=>{try{return await video(...a);}finally{this.background();}};
  const karaoke=App.applyKaraoke.bind(App);App.applyKaraoke=(...a)=>{const v=karaoke(...a);this.background();return v;};
  const visible=FluidCover24.visible.bind(FluidCover24);FluidCover24.visible=()=>!['custom','video'].includes($('now')?.dataset.background46)&&visible();
  this.audio();this.controls();
  const lang=App.afterLangChange.bind(App);App.afterLangChange=(...a)=>{const v=lang(...a);this.labels();return v;};
  const bg=Viz.drawBg.bind(Viz);Viz.drawBg=(...a)=>{if(typeof Visualizer32==='undefined')return;if(Player.audio?.paused||Player.audio?.ended){Viz.vals?.fill(0);Viz.peaks?.fill(0);Visualizer32.radial?.fill(0);if(Viz.mood)Object.assign(Viz.mood,{bass:0,mid:0,air:0,punch:0,drive:0});}bg(...a);BeatFX46.draw(...a);};
  const reset=Viz.reset.bind(Viz);Viz.reset=(...a)=>{BeatFX46.reset();if(typeof Visualizer32!=='undefined'){Visualizer32.visualTime=0;Visualizer32.lastSize=0;}return reset(...a);};
  this.background();this.labels();
 },
 background(){
  const now=$('now');if(!now)return;
  const mode=document.body.classList.contains('k-vbg')?'video':document.body.classList.contains('k-custom')?'custom':'auto';
  if(now.dataset.background46!==mode){now.dataset.background46=mode;FluidCover24.sync();}
  const dim=Math.max(0,Math.min(90,Number(S.kBgDim)||0));
  $('nowCustom')?.style.setProperty('--custom-bright46',String(1-dim/100));
 },
 audio(){
  Karaoke.detector34=new BeatDetector34();
  Karaoke.level=function(){
   const a=Player.audio,analyser=Player.analyser,now=performance.now(),at=a?.currentTime||0;
   if(!analyser||!a||a.paused||a.ended){this.detector34.reset();this.beat=0;this._lvAt=0;return this._lv={energy:0,bass:0,bins:null};}
   const identity=Player.current?.id||'';
   if(this.audioKey46!==identity||(this.audioTime46!=null&&(at<this.audioTime46-.1||at-this.audioTime46>.5))){this.detector34.reset();this._lvAt=0;}
   this.audioKey46=identity;this.audioTime46=at;
   if(this._lvAt&&now-this._lvAt<8&&this._lv)return this._lv;
   this._lvAt=now;
   if(!this.data||this.data.length!==analyser.frequencyBinCount)this.data=new Uint8Array(analyser.frequencyBinCount);
   try{analyser.getByteFrequencyData(this.data);}catch{this.detector34.reset();this.beat=0;return this._lv={energy:0,bass:0,bins:null};}
   const result=this.detector34.process(this.data,Player.ctx?.sampleRate||48000,now,this.sense(),true);
   this.beat=result.beat;if(result.hit)this._beatAt=now;
   return this._lv={energy:result.energy,bass:result.bass,bins:this.data};
  };
 },
 controls(){
  const expRow=$('vizExperience32')?.closest('.set');
  if(expRow){
   const row=el('label','set effects-setting46'),label=el('span','l'),select=el('select');label.id='beatLabel46';label.dataset.label46='Beat accents';select.id='beatEffect46';select.setAttribute('aria-labelledby',label.id);row.append(label,select);expRow.after(row);
   const strength=el('label','set effects-setting46'),name=el('span','l'),range=el('input'),value=el('output');name.id='beatStrengthLabel46';name.dataset.label46='Beat intensity';range.id='beatStrength46';range.type='range';range.min=0;range.max=100;range.step=5;range.value=String(S.vizEffectIntensity46??70);range.setAttribute('aria-labelledby',name.id);value.id='beatValue46';value.htmlFor=range.id;value.textContent=range.value+'%';strength.append(name,range,value);row.after(strength);
   select.onchange=()=>{S.vizEffect46=select.value;BeatFX46.reset();saveSettings();};range.oninput=()=>{S.vizEffectIntensity46=Number(range.value);value.textContent=range.value+'%';if(!Number(range.value))BeatFX46.reset();};range.onchange=()=>saveSettings();
  }
  // Make the actual background controls reachable from the karaoke menu.
  const button=el('button','btn g');button.id='karaokeBackground46';button.dataset.label46='Karaoke background';button.onclick=()=>{Interface45.closeKaraoke();Workspace.openSettings();App.openPane('karaoke');$('kbKind')?.closest('.set')?.scrollIntoView({block:'center'});};$('karaokeMenu45')?.append(button);
 },
 labels(){
  document.querySelectorAll('[data-label46]').forEach(n=>n.textContent=t(n.dataset.label46));
  const select=$('beatEffect46');if(select){select.replaceChildren();for(const [v,key]of [['off','Off'],['rings','Beat rings'],['tunnel','Bass tunnel'],['sparks','Spectral sparks']]){const opt=document.createElement('option');opt.value=v;opt.textContent=t(key);select.append(opt);}select.value=S.vizEffect46||'rings';}
 }
};
const BeatFX46={
 waves:[],sparks:[],hits:0,previous:0,warm:0,lastMedia:null,key:'',
 reset(){this.waves=[];this.sparks=[];this.previous=0;this.warm=0;this.lastMedia=null;},
 draw(c1,c2,energy,beat,calm,bins){
  const ctx=Viz.ctx,w=Viz.bg?.width,h=Viz.bg?.height;if(!ctx||!w||!h)return;
  const id=Player.current?.id||'',at=Player.audio?.currentTime||0,dt=Viz.dt||1/60;
  if(this.key!==id||(this.lastMedia!==null&&(at<this.lastMedia-.1||at-this.lastMedia>.5))){this.reset();this.key=id;}
  this.lastMedia=at;
  const strength=Math.max(0,Math.min(1,Number(S.vizEffectIntensity46??70)/100)),mode=S.vizEffect46||'rings';
  const active=!calm&&!S.noAnim&&!!Player.current&&!Player.audio?.paused&&!Player.audio?.ended&&strength>0&&mode!=='off';
  if(!active){this.reset();return;}
  this.warm+=dt;
  const onset=beat>.85&&this.previous<=.85&&this.warm>.22&&bins?.some(v=>v>8);this.previous=beat;
  if(onset){
   this.hits++;this.waves.push({age:0,level:strength});if(this.waves.length>6)this.waves.shift();
   if(mode==='sparks')for(let i=0;i<20;i++){const angle=i*Math.PI/10+this.hits*.37;this.sparks.push({age:0,angle,speed:100+(i%5)*26});}
   if(this.sparks.length>100)this.sparks.splice(0,this.sparks.length-100);
  }
  this.waves=this.waves.filter(p=>(p.age+=dt)<1.1);this.sparks=this.sparks.filter(p=>(p.age+=dt)<.85);
  ctx.save();ctx.globalCompositeOperation='screen';ctx.lineWidth=1.5;ctx.strokeStyle=c1;ctx.fillStyle=c2;
  const cx=w*.5,cy=h*.5,base=Math.min(w,h);
  if(mode==='rings')for(const p of this.waves){ctx.globalAlpha=(1-p.age/1.1)*.6*p.level;ctx.beginPath();ctx.ellipse(cx,cy,base*(.16+p.age*.65),base*(.16+p.age*.65)*.66,0,0,Math.PI*2);ctx.stroke();}
  if(mode==='tunnel'){
   const bass=Viz.mood?.bass||0;
   for(let i=0;i<9;i++){const r=base*(.1+i*.064)*(1+bass*.06*strength);ctx.globalAlpha=(.06+bass*.16)*strength;ctx.beginPath();ctx.ellipse(cx,cy,r,r*.58,0,0,Math.PI*2);ctx.stroke();}
   for(const p of this.waves){ctx.globalAlpha=(1-p.age/1.1)*.5*p.level;ctx.lineWidth=2.5;ctx.beginPath();ctx.ellipse(cx,cy,base*(.1+p.age*.7),base*(.1+p.age*.7)*.58,0,0,Math.PI*2);ctx.stroke();}
  }
  if(mode==='sparks')for(const p of this.sparks){const distance=base*.18+p.age*p.speed;ctx.globalAlpha=(1-p.age/.85)*strength*.8;ctx.beginPath();ctx.arc(cx+Math.cos(p.angle)*distance,cy+Math.sin(p.angle)*distance*.7,1.4+(1-p.age/.85)*1.4,0,Math.PI*2);ctx.fill();}
  ctx.restore();
 }
};
const boot46=App.boot.bind(App);App.boot=async function(...a){await boot46(...a);Scene46.init();};
