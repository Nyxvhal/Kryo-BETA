/* Event-driven feedback: no background canvas, timers or fake audio levels. */
'use strict';
addEventListener('DOMContentLoaded',()=>{
 const reduce=matchMedia('(prefers-reduced-motion: reduce)');
 const allowed=()=>!reduce.matches&&!S.noAnim&&!document.hidden;
 const audio=document.getElementById('audio');
 const sync=()=>document.body.classList.toggle('kx12-playing',!!audio&&!audio.paused&&!audio.ended&&!document.hidden);
 ['play','pause','ended','emptied','waiting','playing'].forEach(e=>audio?.addEventListener(e,sync));
 document.addEventListener('visibilitychange',sync);
 document.addEventListener('click',e=>{
  if(document.body.classList.contains('ui-v47'))return;
  const b=e.target.closest('button');if(!b||b.disabled||!allowed()||!b.animate)return;if(typeof Motion73!=='undefined'&&Motion73.handles(b))return;
  // Additive transform doesn't fight the existing hover or layout styles.
  b.animate([{opacity:.65},{opacity:1}],{duration:210,easing:'ease-out'});
 });
 const host=document.getElementById('skSkins');
 if(host){const stagger=()=>[...host.children].forEach((n,i)=>n.style.setProperty('--kx-order',String(i)));new MutationObserver(stagger).observe(host,{childList:true});stagger();}
 reduce.addEventListener('change',()=>{if(reduce.matches)document.getAnimations().forEach(a=>a.cancel());});
});
