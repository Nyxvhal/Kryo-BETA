// v73 sweep: every control of the player bar, its ⋮ menu, now playing and the queue
// must do something observable (DOM change outside the clock/progress, or player state), without page errors.
module.exports=async(p,h,args)=>{
 const errs=[];p.on('pageerror',e=>errs.push('pageerror: '+e.message));p.on('console',m=>{if(m.type()==='error')errs.push('console: '+m.text().slice(0,200))});
 await h.boot();
 await p.waitForFunction(()=>typeof Home31!=='undefined'&&Home31.filtered().length>3,null,{timeout:30000});
 await p.evaluate(()=>{const l=Home31.filtered().filter(t=>t&&t.id);Player.playList(l.slice(0,6),false);});
 await p.waitForFunction(()=>Player.audio&&!Player.audio.paused&&Player.audio.currentTime>.3,null,{timeout:30000});
 await p.evaluate(()=>{window.__mut73=0;const skip=n=>{const e=n&&(n.nodeType===1?n:n.parentElement);return !e||!!e.closest('#pCur,#pDur,#pTime,#pBar,.pbar,.prog,.progress,[id*=Time],[id*=Cur],[id*=Dur],canvas,.viz,.eq-bars,[class*=wave-bars],#boot45,.kx-marquee')};
  new MutationObserver(list=>{for(const m of list){if(skip(m.target))continue;if(m.type==='attributes'&&m.attributeName==='style'&&m.target.closest&&m.target.closest('#player')&&/width|transform|left/.test(m.target.getAttribute('style')||'')&&!m.target.matches('dialog,[role=dialog],.menu,#ctxMenu'))continue;window.__mut73++;}}).observe(document.body,{subtree:true,childList:true,attributes:true,characterData:true});});
 const state=()=>p.evaluate(()=>JSON.stringify({paused:Player.audio?.paused,id:(Player.current||Player.track||{}).id,t:Math.floor(Player.audio?.currentTime||0)===0,shuffle:S.shuffle,repeat:S.repeat,vol:S.volume,muted:Player.audio?.muted,liked:K.likes&&K.likes.has((Player.current||Player.track||{}).id),view:K.view,menu:$('ctxMenu')?.classList.contains('on'),modal:!!document.querySelector('.modal.on,dialog[open],.sheet.on,[role=dialog]:not([hidden])'),queue:document.body.className}));
 const results=[];const report=(name,ok,info)=>{const line=(ok?'PASS ':'FAIL ')+name+(info?' :: '+info:'');results.push(line);console.log(line);};
 const cleanup=async()=>{await p.keyboard.press('Escape');await h.wait(150);await p.evaluate(()=>{try{hideMenu()}catch{};try{closeModals()}catch{};document.querySelectorAll('.sound72:not([hidden]),#sound72:not([hidden])').forEach(x=>x.hidden=true);});await h.wait(150);};
 const probe=async(name,clickFn,expect)=>{const e0=errs.length;const s0=await state();await p.evaluate(()=>window.__mut73=0);let clickErr='';try{await clickFn();}catch(e){clickErr=e.message.split('\n')[0];}await h.wait(700);const s1=await state();const mut=await p.evaluate(()=>window.__mut73);const newErr=errs.slice(e0);
  let ok=!clickErr&&(mut>0||s0!==s1)&&!newErr.length;let extra='';if(expect){try{const r=await expect(JSON.parse(s0),JSON.parse(s1));if(r!==true){ok=false;extra=' expect='+r;}}catch(e){ok=false;extra=' expect-err '+e.message}}
  report(name,ok,`mut=${mut} changed=${s0!==s1}${clickErr?' clickErr='+clickErr:''}${newErr.length?' errors='+newErr.join(' | '):''}${extra}`);return {s0:JSON.parse(s0),s1:JSON.parse(s1),mut};};
 const click=sel=>()=>p.click(sel,{timeout:4000});
 const restart=async()=>{await p.evaluate(()=>{if(Wave61.active)Wave61.stop(false);if(Player.audio.paused||!Player.current){const l=Home31.filtered().filter(t=>t&&t.id);Player.playList(l.slice(0,6),false);}});await h.wait(800);};
 // ---------- player bar
 await probe('play/pause',click('#pPlay'),(a,b)=>a.paused!==b.paused||'paused unchanged');
 await probe('play again',click('#pPlay'),(a,b)=>b.paused===false||'still paused');
 await probe('next',click('#pNext'),(a,b)=>a.id!==b.id||'same track');
 await probe('previous',click('#pPrev'),(a,b)=>(a.id!==b.id||b.t)||'no restart/prev');
 await probe('shuffle',click('#pShuffle'),(a,b)=>a.shuffle!==b.shuffle||'shuffle unchanged');await p.click('#pShuffle');await h.wait(200);
 await probe('repeat',click('#pRepeat'),(a,b)=>a.repeat!==b.repeat||'repeat unchanged');
 await p.evaluate(()=>{for(let i=0;i<3&&S.repeat&&S.repeat!=='off'&&S.repeat!=='none';i++)$('pRepeat').click();});
 await probe('like',click('#pLike'),(a,b)=>a.liked!==b.liked||'like unchanged');await p.click('#pLike');await h.wait(300);
 await probe('mute',click('#pMute'),(a,b)=>(a.vol!==b.vol&&(a.vol===0||b.vol===0))||'mute unchanged '+a.vol+'->'+b.vol);await p.click('#pMute');await h.wait(200);
 await p.focus('#vol');await probe('volume keys',async()=>{await p.keyboard.press('ArrowLeft');await p.keyboard.press('ArrowLeft');},(a,b)=>a.vol!==b.vol||'volume unchanged');
 for(const [sel,name] of [['#pAdd','add to playlist'],['#pQueue','queue'],['#ui7Sleep','sleep timer'],['#pQuality72','sound & quality'],['#pSource','source switch'],['#waveDock61','wave'],['#pVideo','clip'],['#pInfo','now playing'],['#pArtist','artist']]){
  if(!await p.$(sel+':visible')){report(name,false,'not visible');continue;}
  await probe(name,click(sel));await cleanup();
  await p.evaluate(()=>{if(typeof Cinema71!=='undefined'&&Cinema71.close)try{Cinema71.close()}catch{};if(K.view!=='home')App.go('home');});await h.wait(300);await restart();}
 // ---------- wave mode: shuffle/repeat explain instead of silently doing nothing
 await p.evaluate(()=>document.querySelector('#rows .card, .card').click());await h.wait(1500);
 if(await p.evaluate(()=>Wave61.active)){for(const sel of ['#pShuffle','#pRepeat']){const st=await p.evaluate(s=>({dis:$(s.slice(1)).disabled,aria:$(s.slice(1)).getAttribute('aria-disabled')}),sel);
   if(st.dis){report('wave: '+sel+' clickable with explanation',false,'native disabled — click does nothing');continue;}
   await probe('wave: '+sel+' explains',()=>p.click(sel,{timeout:4000,force:true}),async()=>await p.evaluate(()=>$('toast').classList.contains('on')&&/wave|волн/i.test($('toast').textContent))||'no toast');await cleanup();}
  await restart();}
 // ---------- ⋮ menu items
 await p.click('#workspacePlayerMore');await h.wait(400);
 const items=await p.evaluate(()=>[...$('ctxMenu').querySelectorAll('button')].map(b=>b.textContent.trim()));await cleanup();
 console.log('MENU: '+items.join(' | '));
 for(let i=0;i<items.length;i++){
  await p.click('#workspacePlayerMore');await h.wait(350);
  const label=items[i];
  await probe('menu: '+label,async()=>{const b=(await p.$$('#ctxMenu button'))[i];await b.click({timeout:3000});});
  await cleanup();await p.evaluate(()=>{if(K.view!=='home')App.go('home');});await h.wait(300);await restart();}
 // ---------- now playing view
 await p.evaluate(()=>App.openNow());await h.wait(900);
 const npBtns=await p.evaluate(()=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>2&&r.height>2&&getComputedStyle(e).visibility!=='hidden'&&r.top<innerHeight&&r.bottom>0&&r.left<innerWidth&&r.right>0};return [...$('now').querySelectorAll('button,[role=button]')].filter(vis).map((b,i)=>{b.dataset.sweep73='n'+i;return {key:'n'+i,label:(b.getAttribute('aria-label')||b.title||b.textContent||'').trim().replace(/\s+/g,' ').slice(0,40),id:b.id}})});
 console.log('NOW buttons: '+npBtns.length);
 for(const b of npBtns){const sel=b.id?'#'+b.id:`[data-sweep73="${b.key}"]`;if(!await p.$(sel+':visible')){await p.evaluate(()=>App.openNow());await h.wait(500);}
  if(!await p.$(sel+':visible')){report('now: '+(b.label||b.id),false,'not visible after reopen');continue;}
  await probe('now: '+(b.label||b.id||b.key),click(sel));
  await cleanup();await restart();if(!await p.evaluate(()=>$('now').classList.contains('on'))){await p.evaluate(()=>App.openNow());await h.wait(500);}}
 await p.evaluate(()=>$('now').classList.remove('on'));await h.wait(300);
 // ---------- queue panel
 await p.click('#pQueue');await h.wait(700);
 const qHost=await p.evaluate(()=>{const c=[...document.querySelectorAll('#queue,#queuePanel,.queue-panel,[id*=queue i]')].filter(e=>{const r=e.getBoundingClientRect();return r.width>150&&r.height>150&&getComputedStyle(e).visibility!=='hidden'});return c[0]?(c[0].id?'#'+c[0].id:''):''});
 console.log('QUEUE host: '+qHost);
 if(qHost){const qb=await p.evaluate(h=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width>2&&r.height>2&&getComputedStyle(e).visibility!=='hidden'&&r.top<innerHeight&&r.bottom>0};return [...document.querySelector(h).querySelectorAll('button')].filter(vis).filter(b=>!b.closest('[data-id]')||b===b.closest('[data-id]').querySelector('button')).slice(0,24).map((b,i)=>{b.dataset.sweep73='q'+i;return {key:'q'+i,label:(b.getAttribute('aria-label')||b.title||b.textContent||'').trim().replace(/\s+/g,' ').slice(0,40),id:b.id}})},qHost);
  for(const b of qb){
   const find=async()=>p.evaluateHandle(({h,label,id})=>{if(id)return $(id);const vis=e=>{const r=e.getBoundingClientRect();return r.width>2&&r.height>2&&getComputedStyle(e).visibility!=='hidden'};return [...document.querySelector(h).querySelectorAll('button')].filter(vis).find(x=>(x.getAttribute('aria-label')||x.title||x.textContent||'').trim().replace(/\s+/g,' ').slice(0,40)===label)||null},{h:qHost,label:b.label,id:b.id});
   let el=(await find()).asElement();if(!el){await p.click('#pQueue').catch(()=>{});await h.wait(600);el=(await find()).asElement();}
   if(!el){console.log('SKIP queue: '+b.label+' (gone)');continue;}
   if(await el.evaluate(x=>x.disabled)){console.log('SKIP queue: '+b.label+' (disabled: nothing to act on yet)');continue;}
   await probe('queue: '+(b.label||b.id||b.key),()=>el.click({timeout:4000}));await cleanup();await restart();
   if(!await p.evaluate(h=>{const e=document.querySelector(h);return !!e&&e.classList.contains('on')},qHost)){await p.click('#pQueue').catch(()=>{});await h.wait(600);}}}
 // ---------- queue: Clear → Confirm → Undo brings the upcoming tracks back
 await cleanup();await p.evaluate(()=>{if(Wave61.active)Wave61.stop(false);const l=Home31.filtered().filter(t=>t&&t.id);Player.playList(l.slice(0,6),false);});
 await p.waitForFunction(()=>Player.audio&&!Player.audio.paused&&Player.queue.length>Player.index+1,null,{timeout:30000});
 // The queue panel slides out with a transform, so a closed panel still has a
 // width: "open" means the Clear button is inside the viewport and not moving.
 const clearInView=()=>p.evaluate(()=>{const e=document.querySelector('#queueClear');if(!e)return false;const r=e.getBoundingClientRect();return r.width>0&&r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight;});
 for(let i=0;i<3&&!await clearInView();i++){await p.click('#pQueue').catch(()=>{});await h.wait(700);}
 await p.waitForFunction(()=>{const e=document.querySelector('#queueClear');const r=e.getBoundingClientRect();const k=r.left+','+r.top;const same=window.__qc73===k;window.__qc73=k;return same;},null,{polling:120,timeout:5000}).catch(()=>{});
 const before=await p.evaluate(()=>({n:Player.queue.length,undo:$('workspaceQueueUndo')?.disabled}));
 await p.click('#queueClear');await h.wait(400);
 await p.locator('#mWorkspaceConfirm .workspace-dialog-actions .btn').last().click();await h.wait(500);
 const cleared=await p.evaluate(()=>({n:Player.queue.length,undo:$('workspaceQueueUndo')?.disabled}));
 await p.click('#workspaceQueueUndo');await h.wait(500);
 const undone=await p.evaluate(()=>({n:Player.queue.length,undo:$('workspaceQueueUndo')?.disabled}));
 report('queue: Clear asks, clears, and enables Undo',before.n>1&&cleared.n<before.n&&cleared.undo===false,JSON.stringify({before,cleared}));
 report('queue: Undo restores the queue and disables itself',undone.n===before.n&&undone.undo===true,JSON.stringify(undone));
 await h.shot('btn73');
 console.log('SUMMARY '+results.filter(r=>r.startsWith('PASS')).length+'/'+results.length+' pass');
};
