/* Spectral onsets in real Hz bands. No synthetic clock or guessed beat grid. */
'use strict';
class BeatDetector34 {
 constructor(){this.reset();}
 reset(){this.at=null;this.prev=null;this.average=0;this.fluxAverage=0;this.beat=0;this.lastHit=-Infinity;}
 process(bins,sampleRate,now,sensitivity=1,active=true){
  if(!active||!bins?.length){this.reset();return {energy:0,bass:0,beat:0,hit:false};}
  const dt=Math.min(.1,Math.max(.001,(now-(this.at??now-16))/1000));this.at=now;
  const gain=Math.min(2,Math.max(.2,sensitivity)),hz=sampleRate/(bins.length*2);
  let all=0,bass=0,n=0,flux=0,fn=0;
  for(let i=0;i<bins.length;i++){
   const v=bins[i]/255;all+=v*v;
   if(i*hz>=30&&i*hz<=190){bass+=v*v;n++;}
   if(i*hz>=30&&i*hz<=3000){flux+=Math.max(0,v-(this.prev?.[i]??v));fn++;}
  }
  bass=Math.sqrt(bass/Math.max(1,n));flux/=Math.max(1,fn);
  const first=!this.prev,old=this.bassPrev??bass,rise=bass-old,threshold=Math.max(.012,this.fluxAverage*1.65)/Math.sqrt(gain);
  const hit=!first&&now-this.lastHit>=145&&((bass>.07&&rise>.035/Math.sqrt(gain)&&bass>this.average+.02)||flux>threshold);
  this.average+=(bass-this.average)*(1-Math.exp(-dt/.42));
  this.fluxAverage+=(flux-this.fluxAverage)*(1-Math.exp(-dt/.65));
  this.bassPrev=bass;
  if(!this.prev||this.prev.length!==bins.length)this.prev=new Float32Array(bins.length);
  for(let i=0;i<bins.length;i++)this.prev[i]=bins[i]/255;
  this.beat=hit?1:this.beat*Math.exp(-dt/.12);if(hit)this.lastHit=now;
  return {energy:Math.min(1,Math.sqrt(all/bins.length)*gain),bass:Math.min(1,bass*gain),beat:this.beat,hit};
 }
}
if(typeof module!=='undefined')module.exports=BeatDetector34;
