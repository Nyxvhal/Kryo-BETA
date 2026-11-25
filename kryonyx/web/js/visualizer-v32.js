/* Cinematic Canvas2D visualizer. Reuses the one Player audio graph and frame clock. */
'use strict';
const Visualizer32={
 frames:0,lastSize:0,lastStyle:0,quality:1,slow:0,stars:null,signal:null,
 keys:['Visualizer atmosphere','Aurora ribbons','Orbital field','Classic scenes','Audio reactive','Waiting for audio'],

 // A single media-query object, a bounded render budget and cached geometry.
 profile(){return ['auto','economy','quality'].includes(S.vizBudget51)?S.vizBudget51:'auto';},
 budget(){const economy=this.profile()==='economy'||(this.profile()==='auto'&&S.layout48?.quality==='economy'),limited=economy||(this.profile()==='auto'&&this.limited51);return {spectrum:limited?30:60,background:limited?10:30,scale:economy?.55:1,dpr:limited?1:1.5,bars:limited?48:128,shadow:this.profile()==='quality'};},
 feedback(now,cost){
  if(this.profile()!=='auto'){this.frameAt51=now;return;}
  const budget=this.budget(),gap=this.frameAt51?now-this.frameAt51:0;this.frameAt51=now;
  if(gap>500||!gap)return;
  const late=gap>1000/budget.spectrum*1.65||cost>10;
  this.slow51=late?(this.slow51||0)+1:Math.max(0,(this.slow51||0)-.2);
  if(this.slow51>=8&&!this.limited51){this.limited51=true;this.quality=Math.min(this.quality,.55);this.lastSize=0;this.slow51=0;this.recover51=0;}
  if(this.limited51){this.recover51=!late&&cost<5?(this.recover51||0)+1:0;if(this.recover51>360){this.limited51=false;this.quality=1;this.lastSize=0;this.slow51=0;this.recover51=0;}}
 },
 ranges(bins,n,low=30,high=18000){
  const length=bins?.length||0,nyquist=(Player.ctx?.sampleRate||48000)/2,key=[length,nyquist,n,low,high].join('|');
  this.rangeCache51 ||= new Map();let ranges=this.rangeCache51.get(key);if(ranges)return ranges;
  ranges=new Uint32Array(n*2);high=Math.min(high,nyquist);
  for(let i=0;i<n;i++){const a=Math.min(Math.max(0,length-1),Math.floor(low*Math.pow(high/low,i/n)/nyquist*length));ranges[i*2]=a;ranges[i*2+1]=Math.min(length,Math.max(a+1,Math.ceil(low*Math.pow(high/low,(i+1)/n)/nyquist*length)));}
  if(this.rangeCache51.size>=12)this.rangeCache51.delete(this.rangeCache51.keys().next().value);this.rangeCache51.set(key,ranges);return ranges;
 },
 watchSize51(){
  if(this.resizeObserver51||typeof ResizeObserver==='undefined')return;
  this.resizeObserver51=new ResizeObserver(entries=>{for(const e of entries){const key=e.target===Viz.bg?'background':'spectrum';(this.dimensions51 ||= {})[key]={w:e.contentRect.width,h:e.contentRect.height};}this.lastSize=0;Viz.w=0;if(Viz.on)Player.wake42();});this.resizeObserver51.observe(Viz.bg);this.resizeObserver51.observe(Viz.spec);
 },
 mode(){return ['aurora','orbit','classic'].includes(S.vizExperience32)?S.vizExperience32:'aurora';},
 init(){
  document.body.classList.add('ui-v32','ui-v51');this.reduce51=matchMedia('(prefers-reduced-motion: reduce)');
  const perf=el('label','set viz-setting32');perf.innerHTML='<span class="l" id="vizBudgetLabel51"></span><select id="vizBudget51" aria-labelledby="vizBudgetLabel51"></select>';
  $('vizScene').closest('.set').before(perf);$('vizBudget51').onchange=e=>{S.vizBudget51=e.target.value;this.limited51=false;this.quality=1;this.slow51=0;this.recover51=0;this.lastSize=0;Viz.w=0;this.frameAt51=0;Viz.last=0;saveSettings();Viz.recolor();Atmo.kick();};
  this.reduce51.addEventListener('change',()=>{this.frameAt51=0;Player.wake42();});
  const row=el('label','set viz-setting32');row.innerHTML='<span class="l" id="vizLabel32"></span><select id="vizExperience32" aria-labelledby="vizLabel32"></select>';
  $('vizScene').closest('.set').before(row);
  $('vizExperience32').onchange=e=>{S.vizExperience32=e.target.value;saveSettings();this.lastSize=0;Viz.w=0;Viz.apply();Viz.recolor();};
  const lang=App.afterLangChange.bind(App);App.afterLangChange=(...args)=>{const v=lang(...args);this.labels();Viz.paintButtons();return v;};
  this.labels();
  document.addEventListener('visibilitychange',()=>{Viz.last=0;this.lastSize=0;});
  addEventListener('resize',()=>{this.lastSize=0;});
 },
 labels(){
  if($('vizBudget51')){const select=$('vizBudget51');select.replaceChildren();for(const [value,en,ru]of [['auto','Auto · adaptive load','Авто · адаптивная нагрузка'],['economy','Economy · fewer effects','Экономия · меньше эффектов'],['quality','Quality · higher load','Качество · выше нагрузка']])select.add(new Option(LANG==='ru'?ru:en,value));select.value=this.profile();$('vizBudgetLabel51').textContent=LANG==='ru'?'Производительность визуализатора':'Visualizer performance';}
  if($('vizExperience32')){const node=$('vizExperience32');node.replaceChildren();for(const [v,k]of [['aurora',1],['orbit',2],['classic',3]]){const option=document.createElement('option');option.value=v;option.textContent=t(this.keys[k]);node.append(option);}node.value=this.mode();$('vizLabel32').textContent=t(this.keys[0]);}
  if($('vizSignal32'))$('vizSignal32').textContent=t(this.keys[this.signal?4:5]);
  for(const [id,key]of [['vProg','Seek'],['vTrack','Audio spectrum']])if($(id))$(id).setAttribute('aria-label',t(key));
 },
 mount(){
  if(!Viz.root||$('vizOrbit32'))return;
  const canvas=el('canvas','viz-orbit32');canvas.id='vizOrbit32';canvas.width=canvas.height=560;canvas.setAttribute('aria-hidden','true');Viz.root.querySelector('.viz-artwrap').prepend(canvas);this.orbit=canvas;this.orbitCtx=canvas.getContext('2d');this.watchSize51();
  const label=el('span','viz-signal32');label.id='vizSignal32';label.dataset.noI18n='';Viz.root.querySelector('.viz-info').prepend(label);this.labels();
 },
 size(){
  const now=performance.now(),budget=this.budget(),dpr=Math.min(budget.dpr,window.devicePixelRatio||1);
  if(!this.dimensions51||(!this.resizeObserver51&&(!this.lastSize||now-this.lastSize>500))){this.dimensions51={background:{w:Viz.bg.clientWidth,h:Viz.bg.clientHeight},spectrum:{w:Viz.spec.clientWidth,h:Viz.spec.clientHeight}};}
  const bw=this.dimensions51.background?.w||0,bh=this.dimensions51.background?.h||0,sw=this.dimensions51.spectrum?.w||0,sh=this.dimensions51.spectrum?.h||0;
  if(!bw||!bh||!sw||!sh){this.lastSize=0;Viz.w=Viz.h=0;return false;}
  this.lastSize=now;const scale=Math.min(1,960/bw,600/bh)*this.quality*budget.scale,w=Math.max(1,Math.round(bw*scale)),h=Math.max(1,Math.round(bh*scale));
  if(Viz.bg.width!==w||Viz.bg.height!==h){Viz.bg.width=w;Viz.bg.height=h;}Viz.w=bw;Viz.h=bh;
  if(Viz.sw!==sw||Viz.sh!==sh||Viz.pixelRatio!==dpr){Viz.sw=sw;Viz.sh=sh;Viz.spec.width=Math.max(1,Math.round(sw*dpr));Viz.spec.height=Math.max(1,Math.round(sh*dpr));Viz.sctx?.setTransform(dpr,0,0,dpr,0,0);}Viz.pixelRatio=dpr;
  if(this.orbit){const pixels=budget.spectrum===30?320:560;if(this.orbit.width!==pixels){this.orbit.width=this.orbit.height=pixels;}}
  const key=this.profile()+(budget.spectrum===30?'-limited':'');if(Viz.root&&Viz.root.dataset.budget51!==key)Viz.root.dataset.budget51=key;
  return true;
 },
 band(bins,low,high){if(!bins?.length)return 0;const nyquist=(Player.ctx?.sampleRate||48000)/2,a=Math.min(bins.length-1,Math.floor(low/nyquist*bins.length)),b=Math.min(bins.length,Math.max(a+1,Math.ceil(high/nyquist*bins.length)));let sum=0;for(let i=a;i<b;i++)sum+=(bins[i]/255)**2;return Math.sqrt(sum/(b-a));},
 sense(lv,beat,dt){
  const m=Viz.mood||(Viz.mood={bass:0,mid:0,air:0,drive:0,punch:0,bpm:0}),ease=(a,b,up,down)=>a+(b-a)*(1-Math.exp(-dt/(b>a?up:down)));
  m.bass=ease(m.bass,this.band(lv.bins,30,220),.04,.25);m.mid=ease(m.mid,this.band(lv.bins,220,2400),.06,.3);m.air=ease(m.air,this.band(lv.bins,2400,16000),.08,.38);m.drive=ease(m.drive,Math.min(1,lv.energy*2.6),.2,.9);m.punch=Math.max(beat,m.punch-dt*2);
  // BPM uses media seconds, never the animation speed setting. A seek resets the estimator.
  const at=Player.audio?.currentTime||0;if(at<(this.audioAt||0)||at-(this.audioAt||at)>2){Viz.beatAt=0;m.bpm=0;}this.audioAt=at;
  if(beat>.85&&Viz.beatPrev<=.85){const gap=at-Viz.beatAt;Viz.beatAt=at;if(gap>.25&&gap<1.6)m.bpm=m.bpm?m.bpm*.82+60/gap*.18:60/gap;}
  return m;
 },
 draw(c1,c2,energy,beat,calm,bins){
  this.frames++;const mode=this.mode(),ctx=Viz.ctx,w=Viz.bg.width,h=Viz.bg.height;if(!ctx)return;
  const playing=!!Player.current&&!Player.audio?.paused&&!Player.audio?.ended,signal=playing&&!!bins&&bins.some(v=>v>2);
  if(signal!==this.signal){this.signal=signal;this.labels();}
  // Pause/reduced-motion retains the composition without fictitious beat or star motion.
  const time=calm?0:(this.visualTime||0);if(!calm&&playing)this.visualTime=time+Viz.dt*Viz.motion();
  const m=Viz.mood||{bass:0,mid:0,air:0,punch:0};const punch=calm||!playing?0:(m.punch||0);ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;ctx.clearRect(0,0,w,h);
  if(!document.body.classList.contains('k-vbg')&&!document.body.classList.contains('k-custom')){ctx.fillStyle='#060810';ctx.fillRect(0,0,w,h);}
  const level=Math.max(0,Math.min(1.5,Viz.bgLevel())),glow=(x,y,r,color,alpha)=>{ctx.globalAlpha=alpha*level;const g=ctx.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,color);g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.fillRect(x-r,y-r,r*2,r*2);};
  ctx.globalCompositeOperation='screen';glow(w*(.22+.08*Math.sin(time*.12)),h*.35,w*.65,c1,.22+m.bass*.25+punch*.12);glow(w*.85,h*.65,w*.65,c2,.2+m.air*.2);
  if(mode==='aurora'){
   for(let j=0;j<5;j++){ctx.beginPath();for(let i=0;i<=60;i++){const x=i/60*w,y=h*(.48+.12*Math.sin(i*.07+time*.13+j*.6)+.07*Math.sin(i*.16-time*.2+j))+(j-2)*h*(.055+punch*.012); if(!i)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.lineTo(w,h);ctx.lineTo(0,h);ctx.closePath();const g=ctx.createLinearGradient(0,h*.25,0,h*.95);g.addColorStop(0,'transparent');g.addColorStop(.48,j%2?c1:c2);g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.globalAlpha=(.04+m.mid*.055+punch*.025)*level;ctx.fill();}
  }else{
   for(let j=0;j<8;j++){ctx.save();ctx.translate(w*.5,h*.54);ctx.rotate(time*.035+j*.19);ctx.scale(1,.32+j*.035);ctx.beginPath();ctx.arc(0,0,w*(.12+j*.047)*(1+m.bass*.03+punch*.05),0,Math.PI*2);ctx.strokeStyle=j%2?c1:c2;ctx.lineWidth=1;ctx.globalAlpha=(.12+(7-j)*.012)*level;ctx.stroke();ctx.restore();}
  }
  if(S.vizParticles!==false){ctx.fillStyle=c1;ctx.globalAlpha=(.2+m.air*.35)*level;ctx.beginPath();for(let i=0;i<52;i++){const x=((i*.6180339887+time*.001*(1+i%3))%1)*w,y=((i*.3819660113+Math.sin(time*.1+i)*.015+1)%1)*h;ctx.moveTo(x+1,y);ctx.arc(x,y,(i%4===0?1.2:.65),0,6.283);}ctx.fill();}
  ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;this.drawOrbit(c1,c2,bins,playing);Viz.beatPrev=beat;
 },
 drawOrbit(c1,c2,bins,playing){
  const ctx=this.orbitCtx;if(!ctx)return;const w=560,mid=w/2,scale=(this.orbit?.width||560)/560;ctx.setTransform(scale,0,0,scale,0,0);ctx.clearRect(0,0,w,w);ctx.save();ctx.translate(mid,mid);
  const gradient=ctx.createLinearGradient(-mid,0,mid,0);gradient.addColorStop(0,c1);gradient.addColorStop(1,c2);ctx.strokeStyle=gradient;ctx.lineWidth=1.2;ctx.globalAlpha=.24;
  for(const r of [227,256]){ctx.beginPath();ctx.arc(0,0,r,0,6.283);ctx.stroke();}
  if(!this.radial)this.radial=new Float32Array(80);ctx.globalAlpha=.85;ctx.lineWidth=2.2;ctx.lineCap='round';ctx.beginPath();
  if(!this.orbitGeometry51){this.orbitGeometry51=new Float32Array(160);for(let i=0;i<80;i++){const angle=i/80*Math.PI*2;this.orbitGeometry51[i*2]=Math.cos(angle);this.orbitGeometry51[i*2+1]=Math.sin(angle);}}
  const ranges=this.ranges(bins,80,40,16000),up=1-Math.exp(-Viz.dt*18),down=1-Math.exp(-Viz.dt*5),punch=S.noAnim||this.reduce51?.matches?0:(Viz.mood?.punch||0),r=235+punch*5;
  for(let i=0;i<80;i++){let sum=0;const a=ranges[i*2],b=ranges[i*2+1];if(playing&&bins)for(let k=a;k<b;k++)sum+=(bins[k]/255)**2;const target=playing?Math.sqrt(sum/Math.max(1,b-a)):0;this.radial[i]+=(target-this.radial[i])*(target>this.radial[i]?up:down);const len=2+this.radial[i]*43+punch*9,x=this.orbitGeometry51[i*2],y=this.orbitGeometry51[i*2+1];ctx.moveTo(x*r,y*r);ctx.lineTo(x*(r+len),y*(r+len));}ctx.stroke();ctx.restore();
 },
};
const build32=Viz.build.bind(Viz);Viz.build=function(...a){const value=build32(...a);Visualizer32.mount();return value;};
const apply32=Viz.apply.bind(Viz);Viz.apply=function(...a){const v=apply32(...a);if(this.root){this.root.dataset.experience32=Visualizer32.mode();const signal=$('vizSignal32');if(signal)signal.hidden=Visualizer32.mode()==='classic';}return v;};
const size32=Viz.size.bind(Viz);Viz.size=function(){return Visualizer32.mode()==='classic'?size32():Visualizer32.size();};
const sense32=Viz.sense.bind(Viz);Viz.sense=(lv,beat,dt)=>Visualizer32.sense(lv,beat,dt);
const bg32=Viz.drawBg.bind(Viz);Viz.drawBg=function(...a){if(Visualizer32.mode()==='classic')return bg32(...a);return Visualizer32.draw(...a);};
const vars32=Viz.setVars.bind(Viz);Viz.setVars=function(...args){const now=performance.now();const colorKey=args.slice(0,2).join('|');if(now-Visualizer32.lastStyle<16&&colorKey===Visualizer32.colorKey)return;Visualizer32.colorKey=colorKey;Visualizer32.lastStyle=now;return vars32(...args);};
const reset32=Viz.reset.bind(Viz);Viz.reset=function(...a){Visualizer32.radial=null;Visualizer32.audioAt=0;this.last=0;this.beatPrev=0;return reset32(...a);};
const paint32=Viz.paintButtons.bind(Viz);Viz.paintButtons=function(...a){const v=paint32(...a);for(const [action,key]of [['play',Player.audio?.paused?'Play':'Pause'],['prev','Previous'],['next','Next'],['like',K.likes.has(Player.current?.id)?'Unlike':'Like'],['mix','Mixer'],['close','Close']]){const b=this.root?.querySelector(`[data-a="${action}"]`);if(b){b.title=t(key);b.setAttribute('aria-label',t(key));if(action==='like')b.setAttribute('aria-pressed',String(K.likes.has(Player.current?.id)));}}return v;};
const frame32=Viz.frame.bind(Viz);Viz.frame=function(...args){const at=performance.now(),last=this.last,result=frame32(...args);if(this.last!==last&&this.on)Visualizer32.feedback(at,performance.now()-at);return result;};
const boot32=App.boot.bind(App);App.boot=async function(...a){await boot32(...a);Visualizer32.init();};
