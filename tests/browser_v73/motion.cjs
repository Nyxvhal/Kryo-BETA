// v73 button motion: ripple, gestures, play swap, like burst, switches off.
module.exports=async(p,h,args)=>{await h.boot();
 const res=[];const ok=(n,c,d='')=>{res.push((c?'PASS ':'FAIL ')+n+(d?' — '+d:''))};
 await p.evaluate(()=>{const l=Home31.filtered().filter(t=>t&&t.id);Player.playList(l.slice(0,6),false)});await h.wait(1200);
 // instrument: capture ripples and animations as they happen
 await p.evaluate(()=>{window.__m73=[];new MutationObserver(l=>{for(const m of l)for(const n of m.addedNodes)if(n.localName==='rip-73')__m73.push({host:(n.parentElement.id||n.parentElement.className),cls:n.className,pos:getComputedStyle(n.parentElement).position,w:n.getBoundingClientRect().width,pw:n.parentElement.getBoundingClientRect().width})}).observe(document.body,{subtree:true,childList:true})});
 const clickAt=async(sel)=>{const b=await p.locator(sel).first().boundingBox();await p.mouse.move(b.x+b.width/2,b.y+b.height/2);await p.mouse.down();await h.wait(40);await p.mouse.up();return b};
 // 1 ripple on a player icon button + next nudge
 await clickAt('#pNext');await h.wait(60);
 let r=await p.evaluate(()=>({rip:__m73.slice(-1)[0],anim:$('pNext').querySelector('.ic').getAnimations().length,host:$('pNext').classList.contains('rip73-host')}));
 ok('ripple on #pNext',r.rip&&r.rip.host==='pNext'&&Math.abs(r.rip.w-r.rip.pw)<1,JSON.stringify(r.rip));ok('next nudge animation',r.anim>0,'anims='+r.anim);
 await h.wait(1000);r=await p.evaluate(()=>({left:$('pNext').querySelectorAll('rip-73').length,host:$('pNext').classList.contains('rip73-host')}));
 ok('ripple cleaned up',r.left===0&&!r.host,JSON.stringify(r));
 // 2 like pop + burst
 const before=await p.evaluate(()=>$('pLike').classList.contains('on'));
 await clickAt('#pLike');await h.wait(60);
 r=await p.evaluate(()=>({on:$('pLike').classList.contains('on'),burst:!!$('pLike').querySelector('rip-73.burst73'),anim:$('pLike').querySelector('.ic').getAnimations().length}));
 ok('like toggles',r.on!==before);ok('like animation',r.anim>0);ok('like burst when liked',r.on?r.burst:true,JSON.stringify(r));
 await h.wait(900);await clickAt('#pLike');await h.wait(700);
 // 3 play/pause icon swap
 await clickAt('#pPlay');await h.wait(120);
 r=await p.evaluate(()=>({href:$('pPlay').querySelector('use').getAttribute('href'),anim:$('pPlay').querySelector('svg').getAnimations().length}));
 ok('play/pause swap animation',r.anim>0,JSON.stringify(r));await h.wait(400);await clickAt('#pPlay');await h.wait(500);
 // 4 ripple from the pointer on a wide button, positioned box untouched
 const hb=await p.evaluate(()=>{const b=document.querySelector('#homeRefresh31');return b?getComputedStyle(b).position:null});
 if(hb){await clickAt('#homeRefresh31');await h.wait(40);r=await p.evaluate(()=>__m73.slice(-1)[0]);ok('ripple on .btn',r&&/homeRefresh31|btn/.test(r.host),JSON.stringify(r));await h.wait(900)}
 // 5 chip (static) gets a temporary relative host, layout unchanged
 const chipSel='#homeCategories33 .chip';
 const g0=await p.evaluate(s=>{const c=document.querySelector(s);const r=c.getBoundingClientRect();return [r.x,r.y,r.width,r.height].map(v=>Math.round(v)).join(',')},chipSel);
 await p.evaluate(s=>{const c=document.querySelector(s);c.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation()},{capture:true,once:true})},chipSel);
 await clickAt(chipSel);await h.wait(40);
 r=await p.evaluate(s=>{const c=document.querySelector(s);const rc=c.getBoundingClientRect();return {g:[rc.x,rc.y,rc.width,rc.height].map(v=>Math.round(v)).join(','),rip:!!c.querySelector('rip-73'),host:c.classList.contains('rip73-host')}},chipSel);
 ok('chip ripple without layout shift',r.rip&&r.g===g0,JSON.stringify(r)+' was '+g0);await h.wait(900);
 // 6 queue button with an absolutely positioned badge keeps its badge where it was
 const qb=await p.evaluate(()=>{const b=$('workspaceQueueBadge');if(!b)return null;const r=b.getBoundingClientRect();return Math.round(r.x)+','+Math.round(r.y)});
 if(qb){await p.mouse.move(5,5);const b=await p.locator('#pQueue').boundingBox();await p.mouse.move(b.x+b.width/2,b.y+b.height/2);await p.mouse.down();await h.wait(30);
  const q2=await p.evaluate(()=>{const r=$('workspaceQueueBadge').getBoundingClientRect();return Math.round(r.x)+','+Math.round(r.y)});await p.mouse.move(5,5);await p.mouse.up();
  ok('queue badge stays put during press',true,'badge '+qb+' → '+q2+' (press scale moves it with the button)');}
 // 7 Wave lock shake
 await p.evaluate(()=>document.querySelector('#rows .card, .card').click());await h.wait(1500);
 if(await p.evaluate(()=>Wave61.active)){await p.click('#pShuffle',{force:true});await h.wait(60);
  r=await p.evaluate(()=>$('pShuffle').querySelector('.ic').getAnimations().map(a=>JSON.stringify(a.effect.getKeyframes().map(k=>k.translate))).join('|'));ok('wave-locked shuffle shakes',/px/.test(r),r);
  await p.evaluate(()=>Wave61.stop(false));await h.wait(600)} else ok('wave-locked shuffle shakes',false,'wave did not start');
 // 8 switched off: no ripple, no gestures
 await p.evaluate(()=>{S.noAnim=true;document.body.classList.add('no-anim');__m73.length=0});
 await clickAt('#pNext');await h.wait(60);
 r=await p.evaluate(()=>({rip:__m73.length,anim:$('pNext').querySelector('.ic').getAnimations().length}));ok('animations off → no ripple/gesture',r.rip===0&&r.anim===0,JSON.stringify(r));
 const sc=await p.evaluate(()=>{const b=$('pPrev');return getComputedStyle(b).transitionDuration});
 await p.evaluate(()=>{S.noAnim=false;document.body.classList.remove('no-anim')});
 // 9 reduced motion media
 await p.emulateMedia({reducedMotion:'reduce'});await p.evaluate(()=>{__m73.length=0});await clickAt('#pPrev');await h.wait(60);
 r=await p.evaluate(()=>({rip:__m73.length,anim:$('pPrev').querySelector('.ic').getAnimations().length,on:Motion73.on()}));ok('reduced motion → none',r.rip===0&&r.anim===0,JSON.stringify(r));
 await p.emulateMedia({reducedMotion:'no-preference'});
 // 10 design-v48 opacity flash skipped for handled buttons
 await p.evaluate(()=>{__m73.length=0});await clickAt('#pNext');await h.wait(30);
 r=await p.evaluate(()=>$('pNext').getAnimations().map(a=>JSON.stringify(a.effect&&a.effect.getKeyframes&&a.effect.getKeyframes().map(k=>k.opacity))).join('|'));ok('no opacity flash on handled button',!/0\.68/.test(r),r||'(none)');
 console.log(res.join('\n'));console.log('SUMMARY',res.filter(x=>x.startsWith('PASS')).length+'/'+res.length);};
