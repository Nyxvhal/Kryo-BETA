/* One-direction conveyor for metadata. No translation, HTML injection or timers. */
'use strict';
window.KMarquee={
  items:new Map(),documents51:new WeakMap(),
  initDocument51(doc){
    let state=this.documents51.get(doc);if(state)return state;
    const win=doc.defaultView;state={media:win.matchMedia('(prefers-reduced-motion: reduce)')};this.documents51.set(doc,state);
    state.sync=()=>{state.covered=!!doc.querySelector('.modal.on');for(const item of this.items.values()){if(item.node.ownerDocument!==doc)continue;if(!item.node.isConnected){this.forget(item.node);continue;}this.play51(item);}};
    if(win.IntersectionObserver)state.observer=new win.IntersectionObserver(entries=>{for(const e of entries){const item=this.items.get(e.target);if(item){item.visible51=e.isIntersecting;this.play51(item);}}});
    state.removals=new win.MutationObserver(records=>{if(!this.items.size)return;if(!records.some(r=>[...r.removedNodes].some(n=>n.nodeType===1&&n.tagName!=='RIP-73')))return;for(const item of this.items.values())if(item.node.ownerDocument===doc&&!item.node.isConnected)this.forget(item.node);});state.removals.observe(doc.body,{childList:true,subtree:true});
    doc.addEventListener('visibilitychange',state.sync);state.media.addEventListener('change',()=>{for(const item of this.items.values())if(item.node.ownerDocument===doc)this.measure(item);});
    for(const event of ['play','pause','ended','emptied'])doc.addEventListener(event,state.sync,true);
    doc.addEventListener('pointerover',e=>{const node=e.target.closest?.('.kx-marquee'),item=this.items.get(node);if(item&&!item.interacting51){item.interacting51=true;this.play51(item);}},true);
    doc.addEventListener('pointerout',e=>{const node=e.target.closest?.('.kx-marquee'),item=this.items.get(node);if(item&&!node.contains(e.relatedTarget)){item.interacting51=false;this.play51(item);}},true);
    doc.addEventListener('focusin',state.sync);doc.addEventListener('focusout',state.sync);
    win.addEventListener('pagehide',()=>{for(const item of [...this.items.values()])if(item.node.ownerDocument===doc)this.forget(item.node);state.observer?.disconnect();state.removals.disconnect();},{once:true});
    return state;
  },
  play51(item){
    if(!item.animation)return;const doc=item.node.ownerDocument,state=this.initDocument51(doc),playing=typeof Player==='undefined'||!Player.audio||!Player.audio.paused&&!Player.audio.ended;
    const focused=item.node.contains(doc.activeElement),allowed=!doc.hidden&&item.visible51!==false&&!item.reduce&&!(typeof S!=='undefined'&&S.noAnim)&&!state.media.matches&&(!state.covered||!!item.node.closest('.modal.on'))&&(playing||item.interacting51||focused);
    if(allowed&&item.animation.playState==='paused')item.animation.play();else if(!allowed&&item.animation.playState==='running')item.animation.pause();
  },
  visibility51(){const docs=new Set([...this.items.values()].map(x=>x.node.ownerDocument));for(const doc of docs)this.documents51.get(doc)?.sync();},
  set(node,text,reduce=false){
    if(!node)return;
    if(!node.ownerDocument.getElementById('kx-marquee-css')){const style=node.ownerDocument.createElement('style');style.id='kx-marquee-css';style.textContent=this.CSS;node.ownerDocument.head.append(style);}
    text=String(text||'');
    let item=this.items.get(node);
    if(!item){
      item={node,text:null,reduce:false,animation:null,visible51:false};this.items.set(node,item);const state=this.initDocument51(node.ownerDocument);state.observer?.observe(node);if(!state.observer)item.visible51=true;
      if(typeof ResizeObserver!=='undefined'){item.observer=new ResizeObserver(()=>this.measure(item));item.observer.observe(node);}
    }
    const same=item.text===text&&item.reduce===!!reduce&&node.querySelector(':scope > .kx-marquee-lane');item.reduce=!!reduce;
    if(same){this.play51(item);return;}
    if(item.text!==text||!node.querySelector(':scope > .kx-marquee-lane')){
      item.animation?.cancel();item.text=text;
      node.classList.add('kx-marquee');node.dataset.entityName='';node.title=text;
      const lane=node.ownerDocument.createElement('span');lane.className='kx-marquee-lane';
      const first=node.ownerDocument.createElement('span');first.textContent=text;first.className='kx-marquee-copy';lane.append(first);
      node.replaceChildren(lane);item.lane=lane;item.first=first;item.distance=0;
    }
    this.measure(item);
  },
  measure(item){
    const {node,lane,first}=item;if(!lane||!node.isConnected)return;
    const width=first.scrollWidth,over=width>node.clientWidth+2;
    const reduce=item.reduce||this.initDocument51(node.ownerDocument).media.matches;
    const distance=over&&!reduce?Math.ceil(width)+36:0;
    if(item.distance===distance&&item.animation){this.play51(item);return;}
    item.animation?.cancel();item.animation=null;item.distance=distance;
    lane.querySelector('[aria-hidden]')?.remove();node.classList.toggle('kx-running',distance>0);
    if(distance){
      const clone=first.cloneNode(true);clone.setAttribute('aria-hidden','true');lane.append(clone);
      item.animation=lane.animate([{transform:'translateX(0)'},{transform:`translateX(-${distance}px)`}],{duration:Math.max(9000,distance/27*1000),iterations:Infinity,easing:'linear'});
    }
    this.play51(item);
  },
  forget(node){const item=this.items.get(node);if(item){item.animation?.cancel();item.observer?.disconnect();this.documents51.get(node.ownerDocument)?.observer?.unobserve(node);this.items.delete(node);}},
  sync(){
    const reduce=typeof S!=='undefined'&&!!S.noAnim;
    for(const id of ['pTitle','pArtist','nTitle','nArtist']){
      const node=document.getElementById(id);if(!node)continue;
      const item=this.items.get(node),text=node.querySelector(':scope>.kx-marquee-lane')?item?.text:node.textContent;
      this.set(node,text,reduce);
    }
  },
};
KMarquee.CSS=`
.kx-marquee{display:block!important;overflow:hidden!important;white-space:nowrap!important;min-width:0;text-overflow:ellipsis}
.kx-marquee-lane{display:flex!important;align-items:baseline;gap:36px;width:max-content;max-width:none;animation:none!important;will-change:transform}
.kx-marquee-copy{display:block!important;white-space:nowrap;flex:none;max-width:none;width:max-content}
.kx-marquee:not(.kx-running) .kx-marquee-lane{display:block!important;max-width:100%;overflow:hidden;text-overflow:ellipsis;will-change:auto}
`;
