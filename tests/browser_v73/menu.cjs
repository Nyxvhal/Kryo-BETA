// v73: the ⋮ menu of the player opens beside its button (never on top of it), stays inside the
// window and works from the keyboard. Checked at three window sizes.
module.exports=async(p,h)=>{
 const ok=(n,c,x)=>console.log((c?'PASS ':'FAIL ')+n+(x!==undefined?' :: '+JSON.stringify(x):''));
 await h.boot();
 await p.evaluate(async()=>{const r=await api('/api/history');if(r.items?.length)Player.play(r.items[0],r.items,0)});await h.wait(1500);
 for(const [w,hh] of [[1920,1080],[1280,720],[900,640]]){
  await p.setViewportSize({width:w,height:hh});await h.wait(500);
  const sel=await p.evaluate(()=>{const b=$('workspacePlayerMore');return b&&b.offsetParent?'#workspacePlayerMore':'#workspaceMobileControls button:last-child'});
  const btn=await p.$(sel);const bb=await btn.boundingBox();await btn.click();await h.wait(450);
  const info=await p.evaluate(()=>{const m=$('ctxMenu');const r=m.getBoundingClientRect();return {open:m.classList.contains('on'),x:r.x,y:r.y,w:r.width,h:r.height,items:m.querySelectorAll('button').length,inner:[innerWidth,innerHeight]}});
  const overlap=!(info.x+info.w<=bb.x+0.5||info.x>=bb.x+bb.width-0.5||info.y+info.h<=bb.y+0.5||info.y>=bb.y+bb.height-0.5);
  ok(`${w}×${hh}: the menu opens with its items`,info.open&&info.items>3,info);
  ok(`${w}×${hh}: the menu does not cover the ⋮ button`,!overlap,{menu:info,button:bb});
  ok(`${w}×${hh}: the menu stays inside the window`,info.x>=0&&info.y>=0&&info.x+info.w<=info.inner[0]+0.5&&info.y+info.h<=info.inner[1]+0.5,info);
  await h.shot('menu73_'+w);
  await p.keyboard.press('Escape');await h.wait(250);
  await p.focus(sel);await p.keyboard.press('Enter');await h.wait(350);
  const k1=await p.evaluate(()=>({open:$('ctxMenu').classList.contains('on'),inMenu:$('ctxMenu').contains(document.activeElement),text:document.activeElement?.textContent?.trim().slice(0,30)}));
  await p.keyboard.press('ArrowUp');
  const k2=await p.evaluate(()=>({inMenu:$('ctxMenu').contains(document.activeElement),text:document.activeElement?.textContent?.trim().slice(0,30)}));
  await p.keyboard.press('Escape');await h.wait(250);
  const k3=await p.evaluate(sel=>({open:$('ctxMenu').classList.contains('on'),back:document.activeElement===document.querySelector(sel)}),sel);
  ok(`${w}×${hh}: Enter opens the menu with the first item focused`,k1.open&&k1.inMenu,k1);
  ok(`${w}×${hh}: ArrowUp wraps to the last item`,k2.inMenu&&k2.text!==k1.text,k2);
  ok(`${w}×${hh}: Escape closes the menu and returns focus to ⋮`,!k3.open&&k3.back,k3);
 }
};
