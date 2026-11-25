/* Local artwork analysis. Area-weighted colours; no artwork is uploaded. */
'use strict';
window.CoverPalette23={
 neutral:['#34343b','#25262d','#3a363c','#22282b'],key:'',colors:null,cache:new Map(),pending:false,
 luminance(rgb){return rgb.map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);},
 fromPixels(data){
  const buckets=new Map();let total=0;
  for(let i=0;i<data.length;i+=4){const alpha=data[i+3]/255;if(alpha<.32)continue;const rgb=[data[i],data[i+1],data[i+2]],key=rgb.map(x=>x>>5).join(':');let b=buckets.get(key);if(!b){b={n:0,rgb:[0,0,0]};buckets.set(key,b);}b.n+=alpha;total+=alpha;rgb.forEach((v,j)=>b.rgb[j]+=v*alpha);}
  if(!total)return this.neutral.slice();
  const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
  const ranked=[...buckets.values()].map(b=>{const rgb=b.rgb.map(v=>v/b.n),hi=Math.max(...rgb),sat=hi?(hi-Math.min(...rgb))/hi:0;return{rgb,n:b.n,score:b.n*(.65+.35*sat)*(.30+.70*Math.sqrt(hi/255))};}).sort((a,b)=>b.score-a.score);
  // Merge nearby quantisation cells so a broad background beats a tiny bright logo.
  const clusters=[];for(const b of ranked){let c=clusters.find(c=>distance(c.rgb,b.rgb)<55);if(!c){clusters.push({...b,rgb:b.rgb.slice()});continue;}const n=c.n+b.n;c.rgb=c.rgb.map((v,i)=>(v*c.n+b.rgb[i]*b.n)/n);c.n=n;c.score+=b.score;}
  clusters.sort((a,b)=>b.score-a.score);const usable=clusters.filter(c=>c.n/total>=.025);const pool=usable.length?usable:clusters;
  const picked=[pool[0]];
  while(picked.length<4){const rest=pool.filter(c=>!picked.includes(c));if(!rest.length)break;rest.sort((a,b)=>{const score=c=>c.score*Math.min(1,Math.min(...picked.map(p=>distance(c.rgb,p.rgb)))/115);return score(b)-score(a);});const next=rest[0];if(Math.min(...picked.map(p=>distance(next.rgb,p.rgb)))<36)break;picked.push(next);}
  // Reuse real source colours on monochrome covers; never invent purple/blue accents.
  const result=picked.map(c=>c.rgb);while(result.length<4)result.push(result[result.length%picked.length].slice());
  return result.map(values=>{let rgb=values.map(Math.round);const hi=Math.max(...rgb);if(hi>0&&hi<72)rgb=rgb.map(v=>Math.round(v*72/hi));while(this.luminance(rgb)>.18)rgb=rgb.map(v=>Math.floor(v*.97));return '#'+rgb.map(v=>v.toString(16).padStart(2,'0')).join('');});
 },
 begin(url){url=url||'';if(this.key===url)return;this.key=url;this.pending=!!url&&!this.cache.has(url);this.colors=this.cache.get(url)?.slice()||(url?(this.colors||this.neutral).slice():this.neutral.slice());this.emit();},
 publish(url,data){if((url||'')!==this.key)return false;this.colors=this.fromPixels(data);this.pending=false;if(url){this.cache.delete(url);this.cache.set(url,this.colors.slice());while(this.cache.size>48)this.cache.delete(this.cache.keys().next().value);}this.emit();return true;},
 fail(url){if((url||'')!==this.key)return false;this.pending=false;this.colors=this.cache.get(url)?.slice()||this.neutral.slice();this.emit();return true;},
 forCover(url){url=typeof KCustom!=='undefined'?KCustom.cover(url):url;return (this.key===(url||'')&&this.colors?this.colors:this.neutral).slice();},
 emit(){dispatchEvent(new CustomEvent('kryonyx:coverpalette',{detail:{key:this.key,colors:this.forCover(this.key),pending:this.pending}}));}
};
