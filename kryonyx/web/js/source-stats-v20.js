/* Exact source ID backfill; never replace source views with local play history. */
'use strict';
const SourceStats20={
 tracks:new Map(),cache:new Map(),pending:new Set(),seen:new WeakSet(),busy:false,
 remember(track){if(track.play_count==='')track.play_count=null;this.tracks.set(track.id,track);const cached=this.cache.get(track.id);if(cached?.value)Object.assign(track,cached.value);return track;},
 init(){
  this.observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){this.enqueue(e.target.dataset.globalId);this.observer.unobserve(e.target);}},{rootMargin:'120px'});
  const scan=()=>{document.querySelectorAll('[data-global-id]').forEach(n=>{if(!this.seen.has(n)){this.seen.add(n);this.observer.observe(n);}});};
  new MutationObserver(records=>{if(records.some(r=>[...r.addedNodes].some(n=>n.nodeType===1&&n.tagName!=='RIP-73'&&(n.hasAttribute('data-global-id')||n.querySelector?.('[data-global-id]'))))){clearTimeout(this.scanTimer);this.scanTimer=setTimeout(scan,100);}}).observe(document.body,{childList:true,subtree:true});scan();
 },
 enqueue(id){const t=this.tracks.get(id),hit=this.cache.get(id);if(!(/^(yt:[\w-]{11}|sc:[\w=-]+)$/.test(id))||!t||(hit&&Date.now()-hit.at<300000)||Studio.number(t)!==null)return;this.pending.add(id);clearTimeout(this.timer);this.timer=setTimeout(()=>this.flush(),150);},
 async flush(){if(this.busy||!this.pending.size)return;this.busy=true;const ids=[...this.pending].slice(0,12);ids.forEach(id=>this.pending.delete(id));try{const d=await api('/api/track-stats',{method:'POST',body:{ids},timeout:100000});for(const id of ids){const value=d.items?.[id]||null;this.cache.set(id,{at:Date.now(),value});if(!value)continue;const track=this.tracks.get(id);if(track)Object.assign(track,value);for(const n of document.querySelectorAll(`[data-global-id="${CSS.escape(id)}"]`)){const span=document.createElement('span');span.innerHTML=Studio.stats(track);const fresh=span.querySelector('.studio-global');n.replaceWith(fresh);}for(const list of [K.likedTracks,Player.queue,Workspace.listData])for(const t of list||[])if(t.id===id)Object.assign(t,value);}}catch{for(const id of ids)this.cache.set(id,{at:Date.now(),value:null});}finally{this.busy=false;if(this.pending.size)this.timer=setTimeout(()=>this.flush(),200);}}
};
