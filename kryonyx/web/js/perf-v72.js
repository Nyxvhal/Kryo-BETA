/* v72 performance: paint the progress bar only when it moves by a device pixel.
   A 3-minute track on a 660 px bar advances ~4 px per second, yet the bar was
   repainted 30 times per second — and every repaint re-ran the player's glass
   blur. Seeks, forced paints and resizes still paint immediately. */
'use strict';
const Perf72={
 ready:false,last:'',widths:new Map(),
 hosts:['pTrack','pTrackM','nTrack','dTrack','vProg','s33Track','albumSeek24'],
 visible(id){try{return typeof Performance47==='undefined'||Performance47.visible(id)}catch(_){return true}},
 width(){let w=0;for(const [id,v] of this.widths)if(v>w&&this.visible(id))w=v;return Math.max(1,w||660)*(window.devicePixelRatio||1)},
 key(){const a=Player.audio,dur=Player.realDuration?.();if(!a||!dur||!Number.isFinite(dur)||dur<=0)return '';const w=this.width();return Math.round(Math.max(0,Math.min(1,a.currentTime/dur))*w)+'|'+w+'|'+(Player.current?.id||'')},
 init(){
  if(this.ready||typeof Player==='undefined'||!Player.paintProgress)return;this.ready=true;document.body.classList.add('ui-v72');
  const ro=new ResizeObserver(entries=>{for(const e of entries)this.widths.set(e.target.id,e.contentRect.width);this.last='';});
  this.hosts.forEach(id=>{const n=$(id);if(n)ro.observe(n);});
  const paint=Player.paintProgress.bind(Player);
  Player.paintProgress=(forced,...rest)=>{
   const pass=forced!=null||Player.seeking||Player.holdUntilSeeked||(typeof Performance47!=='undefined'&&Performance47.force)||!Player.audio||Player.audio.paused;
   if(!pass){const k=this.key();if(k&&k===this.last)return;this.last=k;}else this.last='';
   return paint(forced,...rest);
  };
  document.addEventListener('visibilitychange',()=>{this.last='';});
 }
};
if(typeof App!=='undefined'&&App.boot){const boot72=App.boot.bind(App);App.boot=async function(...a){await boot72(...a);Perf72.init();};}

/* Cover-colour palette (karaoke.js is kept byte-identical for provenance, so the
   fix lives here). blend() rounded each step, so the last few units never
   arrived; pushPalette()'s close() then never became true and its frame loop ran
   for the whole session — 60 callbacks per second while music played. Now every
   step moves at least one unit and the loop ends after ~1.5 s at the latest. */
if(typeof Karaoke!=='undefined'){
 const rgb72=c=>{if(typeof c!=='string')return[0,0,0];if(c.startsWith('#'))return hex2rgb(c);const m=c.match(/-?\d+/g)||[0,0,0];return[+m[0],+m[1],+m[2]];};
 Karaoke.blend=function(speed){
  if(!this.target)return;
  if(!this.palette||this.palette.length!==this.target.length){this.palette=this.target.slice();return;}
  const k=speed||0.04,mix=(x,y)=>{const d=y-x;if(!d)return x;const s=Math.round(d*k);return x+(s||Math.sign(d));};
  this.palette=this.palette.map((current,i)=>{const a=rgb72(current),b=rgb72(this.target[i]||this.target[0]);return `rgb(${mix(a[0],b[0])},${mix(a[1],b[1])},${mix(a[2],b[2])})`;});
 };
 Karaoke.pushPalette=function(){
  if(this._pr)return;
  const close=()=>{if(!this.target||!this.palette)return true;return this.palette.every((c,i)=>{const a=rgb72(c),b=rgb72(this.target[i]||this.target[0]);return Math.abs(a[0]-b[0])+Math.abs(a[1]-b[1])+Math.abs(a[2]-b[2])<6;});};
  let frames=0;
  const step=()=>{
   if(this.raf){this._pr=null;return;}            // the main karaoke loop blends by itself
   this.blend(0.12);
   if(++frames>90&&this.target)this.palette=this.target.slice();
   Disc.paintGlow();
   if(typeof Viz!=='undefined'&&Viz.on&&Viz.repaintColors)Viz.repaintColors();
   if(close()||frames>90){this._pr=null;return;}
   this._pr=requestAnimationFrame(step);
  };
  this._pr=requestAnimationFrame(step);
 };
}
