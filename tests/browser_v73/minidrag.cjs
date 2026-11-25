// v73: mini player drag — whole card draggable, controls still click, fractions kept, native hook.
module.exports=async(p,h,args)=>{
 const R=[];const ok=(n,c,x)=>{R.push([n,!!c]);console.log((c?'PASS ':'FAIL ')+n+(x!==undefined?' '+JSON.stringify(x):''))};
 const mock=native=>{window.moves73=[];window.acts73=[];window.pywebview={api:{
   move_by:async(dx,dy)=>{moves73.push([dx,dy]);return true},state:async()=>({title:'Mini song',artist:'Artist',playing:true,duration:200,position:20}),
   action:async n=>{acts73.push(n);return true},seek:async f=>{acts73.push('seek');return true},volume:async()=>true,close:async()=>true,resize:async(w,h)=>({width:w,height:h})}};
   if(native){window.native73=0;window.__kryonyxShell={post:m=>{if(m.cmd==='__drag')native73++}}}
   addEventListener('DOMContentLoaded',()=>setTimeout(()=>dispatchEvent(new Event('pywebviewready')),0))};
 await p.setViewportSize({width:420,height:180});
 await p.addInitScript(mock,false);await p.goto(h.BASE+'/mini.html');await p.waitForSelector('.mini .mini-art');await h.wait(300);
 const box=s=>p.locator(s).first().boundingBox();
 // 1) drag by the cover (not the strip)
 let a=await box('.mini-art');await p.mouse.move(a.x+a.width/2,a.y+a.height/2);await p.mouse.down();
 await p.mouse.move(a.x+a.width/2+2,a.y+a.height/2+1);await h.wait(60);
 const early=await p.evaluate(()=>moves73.length);
 await p.mouse.move(a.x+a.width/2+90,a.y+a.height/2+30,{steps:9});await p.mouse.up();await h.wait(250);
 let m=await p.evaluate(()=>moves73.reduce((s,[x,y])=>[s[0]+x,s[1]+y],[0,0]));
 ok('below 4 px threshold nothing moves',early===0,early);
 ok('drag by the cover moves the window by the full pointer distance',Math.abs(m[0]-90)<1.5&&Math.abs(m[1]-30)<1.5,m);
 // 2) drag by the title text
 await p.evaluate(()=>{moves73.length=0});a=await box('.mini-t');await p.mouse.move(a.x+10,a.y+a.height/2);await p.mouse.down();await p.mouse.move(a.x-50,a.y+a.height/2-20,{steps:6});await p.mouse.up();await h.wait(250);
 m=await p.evaluate(()=>moves73.reduce((s,[x,y])=>[s[0]+x,s[1]+y],[0,0]));ok('drag by the title moves left/up',Math.abs(m[0]+60)<1.5&&Math.abs(m[1]+20)<1.5,m);
 ok('no text got selected while dragging',await p.evaluate(()=>String(getSelection()).length===0));
 // 3) the strip on top still starts immediately
 await p.evaluate(()=>{moves73.length=0});a=await box('.mini-drag38');await p.mouse.move(a.x+20,a.y+12);await p.mouse.down();await p.mouse.move(a.x+22,a.y+13);await p.mouse.move(a.x+60,a.y+30,{steps:4});await p.mouse.up();await h.wait(250);
 m=await p.evaluate(()=>moves73.reduce((s,[x,y])=>[s[0]+x,s[1]+y],[0,0]));ok('strip drag works',Math.abs(m[0]-40)<1.5&&Math.abs(m[1]-18)<1.5,m);
 // 4) controls stay clicks, never drags
 await p.evaluate(()=>{moves73.length=0;acts73.length=0});a=await box('.mini .play');await p.mouse.move(a.x+a.width/2,a.y+a.height/2);await p.mouse.down();await p.mouse.move(a.x+a.width/2+30,a.y+a.height/2,{steps:3});await p.mouse.up();
 await p.click('.mini .next');await h.wait(200);
 const c=await p.evaluate(()=>({moves:moves73.length,acts:[...acts73]}));ok('buttons do not drag the window',c.moves===0,c);ok('next button still clicks',c.acts.includes('next'),c);
 const seekBox=await box('.mini-seek');await p.mouse.click(seekBox.x+seekBox.width*.5,seekBox.y+seekBox.height/2);await h.wait(150);
 ok('seek bar still seeks',await p.evaluate(()=>acts73.includes('seek')&&moves73.length===0));
 // 5) double click on the cover still opens the main window
 await p.evaluate(()=>{acts73.length=0});a=await box('.mini-art');await p.mouse.dblclick(a.x+a.width/2,a.y+a.height/2);await h.wait(150);
 ok('double click on the cover = show',await p.evaluate(()=>acts73.includes('show')));
 // 6) fractional pointer steps are kept (150 % scaling sends 0.67 px)
 const frac=await p.evaluate(async()=>{moves73.length=0;const root=document.querySelector('.mini'),art=document.querySelector('.mini-art');const r=art.getBoundingClientRect();let x=r.x+20,y=r.y+20;
   const ev=(t,b)=>art.dispatchEvent(new PointerEvent(t,{bubbles:true,pointerId:7,pointerType:'mouse',button:0,buttons:b,screenX:x,screenY:y,clientX:x,clientY:y}));
   ev('pointerdown',1);for(let i=0;i<30;i++){x+=0.6667;ev('pointermove',1);await new Promise(r=>requestAnimationFrame(r));}ev('pointerup',0);await new Promise(r=>setTimeout(r,120));
   return moves73.reduce((s,[dx])=>s+dx,0)});
 ok('fractional steps add up (30 × 0.667 px ≈ 20 px)',Math.abs(frac-20)<0.05,frac);
 await h.shot('minidrag73_card');
 // 7) native shell hook: the system move loop takes over, no JS moves
 const p2=await p.context().newPage();await p2.setViewportSize({width:420,height:180});await p2.addInitScript(mock,true);await p2.goto(h.BASE+'/mini.html');await p2.waitForSelector('.mini .mini-art');await p2.waitForTimeout(300);
 a=await p2.locator('.mini-art').boundingBox();await p2.mouse.move(a.x+20,a.y+20);await p2.mouse.down();await p2.mouse.move(a.x+60,a.y+40,{steps:5});await p2.mouse.up();await p2.waitForTimeout(200);
 const n=await p2.evaluate(()=>({native:native73,moves:moves73.length}));ok('Rust shell: one native drag, no JS moves',n.native===1&&n.moves===0,n);
 await p2.close();
 const failed=R.filter(r=>!r[1]);console.log(`RESULT ${R.length-failed.length}/${R.length}`);if(failed.length)process.exitCode=1;
};
