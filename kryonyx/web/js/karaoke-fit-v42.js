/* Auto-sync search stays off the media/lyric frame. No network or audio upload.
   Generator is also the bounded, cancellable fallback when workers are unavailable. */
'use strict';
function* karaokeFit42(input) {
  const {times:at,values,spans,range,step,min,max,gain}=input,count=at.length;
  if(!count||count!==values.length)return {done:false};
  const span=input.span;
  if(span<min)return {done:false};
  if(!spans.length)return {done:true};
  const sorted=values.slice().sort((a,b)=>a-b),median=sorted[count>>1];
  let spread=0;for(const v of values)spread+=Math.abs(v-median);spread/=count;
  if(!(spread>.004))return {done:span>max};
  const z=new Float32Array(count);for(let i=0;i<count;i++)z[i]=Math.max(-2,Math.min(2,(values[i]-median)/spread));
  // Both media sample times and disjoint vocal intervals are ordered. A sweep
  // replaces a binary search for every sample at every candidate offset.
  const score=shift=>{let sum=0,j=0,voiced=0;for(let i=0;i<count;i++){const x=at[i]+shift;while(j<spans.length&&x>spans[j][1])j++;const yes=j<spans.length&&x>=spans[j][0];sum+=yes?z[i]:-z[i];if(yes)voiced++;}return {value:sum/count,part:voiced/count};};
  const base=score(0);if(base.part<.1||base.part>.95)return {done:span>max};
  const sweep=[],TIE=.02;
  function* pick(from,to,step,keep){const found=[];let top=-Infinity;for(let x=from;x<=to+1e-9;x+=step){const value=score(x).value;found.push([Math.round(x*100)/100,value]);if(keep)sweep.push(value);top=Math.max(top,value);yield;}let at=0,value=-Infinity;for(const[x,got]of found){if(got<top-TIE)continue;if(Math.abs(x)<Math.abs(at)-1e-9||value===-Infinity){at=x;value=got;}}return [at,value];}
  let [shift,best]=yield* pick(-range,range,.5,true);
  if(shift){const[fine,got]=yield* pick(shift-.5,shift+.5,step,false);if(got>=best-TIE){shift=Math.round(fine*20)/20;best=got;}}
  let mean=0;for(const v of sweep)mean+=v;mean/=sweep.length;let variance=0;for(const v of sweep)variance+=(v-mean)**2;const spreadScore=Math.sqrt(variance/sweep.length),sharp=spreadScore>1e-6?(best-mean)/spreadScore:0;
  if(Math.abs(shift)<.3||best-base.value<gain||best<.12||sharp<3.5)return {done:span>max,wrong:span>max&&base.value<.04&&best-base.value<gain};
  return {done:true,accepted:true,shift,confidence:sharp};
}
if(typeof window==='undefined'&&typeof self!=='undefined'&&typeof self.postMessage==='function'){
 self.onmessage=event=>{try{const g=karaokeFit42(event.data);let r;do{r=g.next();}while(!r.done);self.postMessage({result:r.value});}catch(e){self.postMessage({error:String(e)});}};
}else if(typeof window!=='undefined'){
 const KFit42={job:null,cancel(){const j=this.job;if(!j)return;this.job=null;j.cancelled=true;j.worker?.terminate();clearTimeout(j.timer);j.resolve(null);},run(input){this.cancel();return new Promise(resolve=>{const j=this.job={resolve,cancelled:false,worker:null,timer:0};const finish=result=>{if(j.cancelled)return;j.cancelled=true;clearTimeout(j.timer);j.worker?.terminate();if(this.job===j)this.job=null;resolve(result);};const fallback=()=>{if(j.cancelled||j.fallbackStarted)return;j.fallbackStarted=true;clearTimeout(j.timer);j.worker?.terminate();j.worker=null;const g=karaokeFit42(input);const slice=()=>{if(j.cancelled)return;try{const stop=performance.now()+2;let r;do{r=g.next();if(r.done){finish(r.value);return;}}while(performance.now()<stop);j.timer=setTimeout(slice,0);}catch{finish(null);}};j.timer=setTimeout(slice,0);};try{j.worker=new Worker('/js/karaoke-fit-v42.js?v=42');j.worker.onmessage=e=>{if(e.data.error)fallback();else finish(e.data.result);};j.worker.onerror=e=>{e.preventDefault();fallback();};j.worker.postMessage(input);j.timer=setTimeout(fallback,5000);}catch{fallback();}});}};
 window.KFit42=KFit42;
}
if(typeof module!=='undefined')module.exports={karaokeFit42};
