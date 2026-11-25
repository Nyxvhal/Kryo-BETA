// v73: the Rust shell's window bridge (desktop-rs/core/src/bridge.rs, SHIM) inside the real UI.
// The script is assembled from the Rust source exactly like bridge::shim() does (or taken from
// SHIM_DIR, written by `cargo run -p kryonyx-shell-core --example dump_shim -- OUT_DIR`);
// window.ipc stands in for wry's IPC channel and answers like desktop-rs/src/main.rs.
const fs=require('fs'),path=require('path');
const ROOT=path.join(__dirname,'..','..');
function shims(){
 const dir=process.env.SHIM_DIR;
 if(dir)return {main:fs.readFileSync(dir+'/shim-main.js','utf8'),mini:fs.readFileSync(dir+'/shim-mini.js','utf8'),resolve:fs.readFileSync(dir+'/resolve.js','utf8')};
 const rs=fs.readFileSync(path.join(ROOT,'desktop-rs','core','src','bridge.rs'),'utf8');
 const list=name=>JSON.stringify([...rs.match(new RegExp('pub const '+name+': &\\[&str\\] = &\\[([\\s\\S]*?)\\];'))[1].matchAll(/"([^"]+)"/g)].map(m=>m[1]));
 const str=name=>JSON.stringify(rs.match(new RegExp('pub const '+name+': &str = "([^"]*)";'))[1]);
 const SHIM=rs.match(/const SHIM: &str = r#"([\s\S]*?)"#;/)[1];
 const build=(api,drag)=>SHIM.split('__API__').join(list(api)).split('__DRAG__').join(str(drag));
 const value={n:1.5,s:'\u2028',title:'</script><b>x</b>'};
 return {main:build('MAIN_API','MAIN_DRAG'),mini:build('MINI_API','MINI_DRAG'),resolve:'window.__kryonyxShell&&window.__kryonyxShell.resolve(7,true,'+JSON.stringify(value)+')'};
}
module.exports=async(p,h,args)=>{
 const R=[];const ok=(n,c,x)=>{R.push([n,!!c]);console.log((c?'PASS ':'FAIL ')+n+(x!==undefined?' '+JSON.stringify(x).slice(0,300):''))};
 const S=shims(),shimMain=S.main,shimMini=S.mini;
 const splash=fs.readFileSync(path.join(ROOT,'desktop-rs','src','splash.html'),'utf8');
 const fake=src=>{window.__posted=[];window.__max=false;
  window.ipc={postMessage(s){const m=JSON.parse(s);__posted.push(m);if(!m.id)return;
   setTimeout(()=>{const r=(ok,v)=>window.__kryonyxShell.resolve(m.id,ok,v);
    switch(m.cmd){
     case 'info':return r(true,{version:'1.0.0',desktop:true,frameless:true,maximized:__max,on_top:false,remember:true,min_width:400,min_height:560,shell:'rust'});
     case 'toggle_maximize':__max=!__max;return r(true,__max);
     case 'maximized':return r(true,__max);
     case 'bounds':return r(true,{x:10,y:20,width:1360,height:860});
     case 'screen':return r(false,'no monitor');
     case 'state':return r(true,{title:'Mini song',artist:'Artist',playing:true,duration:200,position:20});
     case 'resize':return r(true,{width:m.args[0],height:m.args[1]});
     default:return r(true,true);}},3)}};
  (0,eval)(src)};
 const posted=()=>p.evaluate(()=>__posted.map(m=>m.cmd+(m.args&&m.args.length?':'+JSON.stringify(m.args):'')));
 const clear=()=>p.evaluate(()=>{__posted.length=0});

 // ---------------- main window
 await p.addInitScript(fake,shimMain);
 await h.boot();await h.wait(600);
 const api=await p.evaluate(()=>({names:Object.keys((window.pywebview||{}).api||{}),platform:window.pywebview&&pywebview.platform,framed:document.body.classList.contains('framed'),native:window.__kryonyxShell&&__kryonyxShell.native}));
 ok('window.pywebview.api has the 22 DesktopApi methods',api.names.length===22&&['minimize','toggle_maximize','close','info','bounds','set_bounds','screen','set_on_top','mini_open','mini_update','save_export','save_clip','save_shared_audio','now_playing'].every(n=>api.names.includes(n)),api.names);
 ok('pywebviewready reached frame.js (custom frame on)',api.framed&&api.platform==='kryonyx-shell'&&api.native==='rust',api);
 ok('frame.js asked the window for info',(await posted()).includes('info'));
 const calls=await p.evaluate(async()=>{const b=await pywebview.api.bounds();let err='';try{await pywebview.api.screen()}catch(e){err=e instanceof Error?e.message:'not an Error'}return {b,err}});
 ok('calls resolve with the shell value',calls.b&&calls.b.width===1360,calls);
 ok('failed calls reject with an Error carrying the message',calls.err==='no monitor',calls);
 const stale=await p.evaluate(()=>{try{__kryonyxShell.resolve(99999,true,1);__kryonyxShell.resolve('x',false,'y');return true}catch(e){return e.message}});
 ok('unknown ids are ignored',stale===true,stale);
 // drag region
 await clear();const d=await p.locator('#titlebarDrag').boundingBox();
 await p.mouse.move(d.x+d.width*0.6,d.y+d.height/2);await p.mouse.down();await p.mouse.up();await h.wait(80);
 ok('mousedown on the title bar starts the native move',JSON.stringify(await posted())==='["__drag"]',await posted());
 await clear();await p.click('#winMin');await h.wait(80);
 let list=await posted();ok('window buttons click, never drag',list.includes('minimize')&&!list.includes('__drag'),list);
 // resize edges (not maximized)
 await clear();
 const edges=await p.evaluate(async()=>{const out=[];for(const e of ['top','bottom','left','right','topleft','topright','bottomleft','bottomright']){const n=document.querySelector('#resizers .rz[data-edge="'+e+'"]');n.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,button:0,detail:1}));}await new Promise(r=>setTimeout(r,60));return __posted.map(m=>m.cmd+':'+(m.args||[]).join())});
 ok('each edge starts the native resize in its direction',JSON.stringify(edges)===JSON.stringify(['__resize:n','__resize:s','__resize:w','__resize:e','__resize:nw','__resize:ne','__resize:sw','__resize:se']),edges);
 ok('frame.js JS resize did not run as well (no bounds/set_bounds)',!edges.some(x=>/bounds/.test(x)),edges);
 // double click maximizes once
 await clear();await p.mouse.dblclick(d.x+d.width*0.6,d.y+d.height/2);await h.wait(250);
 list=await posted();const maxed=await p.evaluate(()=>({max:__max,body:document.body.classList.contains('max')}));
 ok('double click on the title bar toggles maximize exactly once',list.filter(x=>x==='toggle_maximize').length===1&&maxed.max,{list,maxed});
 ok('the frame shows the maximized state',maxed.body,maxed);
 await clear();await p.evaluate(()=>document.querySelector('#resizers .rz[data-edge="bottomright"]').dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,button:0,detail:1})));await h.wait(50);
 ok('no resize while maximized',!(await posted()).some(x=>x.startsWith('__resize')),await posted());
 await clear();await p.mouse.dblclick(d.x+d.width*0.6,d.y+d.height/2);await h.wait(250);
 ok('second double click restores',!(await p.evaluate(()=>__max))&&!(await p.evaluate(()=>document.body.classList.contains('max'))),await posted());
 await clear();await p.mouse.click(d.x+d.width*0.6,d.y+d.height/2,{button:'right'});await h.wait(50);
 ok('right button does not move the window',!(await posted()).includes('__drag'),await posted());
 // the settled-value scripts that the shell evaluates
 const evald=await p.evaluate(src=>new Promise(res=>{const id=1e6;const shell=window.__kryonyxShell;const orig=shell.resolve;shell.resolve=(i,ok,v)=>{shell.resolve=orig;res({i,ok,v})};(0,eval)(src)}),S.resolve);
 ok('resolve_js output is valid script and keeps the value',evald.i===7&&evald.ok===true&&evald.v.title==='</script><b>x</b>'&&evald.v.s==='\u2028',evald);

 // ---------------- splash (served from the shell's own scheme, not loopback)
 const p2=await p.context().newPage();
 await p2.route('http://kryonyx.localhost/**',r=>r.fulfill({status:200,contentType:'text/html',body:splash}));
 await p2.addInitScript(fake,shimMain);
 await p2.goto('http://kryonyx.localhost/splash');await p2.waitForTimeout(200);
 const sp=await p2.evaluate(()=>({api:typeof window.pywebview,posted:__posted.map(m=>m.cmd),status:document.getElementById('status').textContent}));
 ok('splash gets no window API (not the backend origin)',sp.api==='undefined',sp);
 ok('splash asks for its status when it is up',sp.posted.includes('__splash'),sp);
 await p2.evaluate(()=>__splash.status(12,'Installing yt-dlp…'));
 const st=await p2.evaluate(()=>({s:document.getElementById('status').textContent,h:document.getElementById('hint').textContent,l:document.getElementById('line').textContent}));
 ok('status shows seconds, slow-start hint and the last backend line',/12/.test(st.s)&&st.h.length>10&&st.l==='Installing yt-dlp…',st);
 await p2.screenshot({path:h.OUT+'/shim73-splash-wait.png'});
 await p2.evaluate(()=>__splash.fail('The backend stopped (exit code 1).','Traceback (most recent call last):\n  File "run.py", line 3\nModuleNotFoundError: No module named \'webview\'','KryonyxMusic.exe --server-only'));
 const fl=await p2.evaluate(()=>({failed:document.body.classList.contains('failed'),log:document.getElementById('log').textContent,retry:getComputedStyle(document.getElementById('retry')).display}));
 ok('failure view shows the log and Retry',fl.failed&&/ModuleNotFoundError/.test(fl.log)&&fl.retry!=='none',fl);
 await p2.screenshot({path:h.OUT+'/shim73-splash-fail.png'});
 await p2.evaluate(()=>{__posted.length=0});await p2.click('#retry');await p2.click('#close');
 const bt=await p2.evaluate(()=>({posted:__posted.map(m=>m.cmd),failed:document.body.classList.contains('failed')}));
 ok('Retry and Close reach the shell',JSON.stringify(bt.posted)==='["__retry","__quit"]'&&!bt.failed,bt);
 await p2.evaluate(()=>{__posted.length=0});const bb=await p2.locator('.bar').boundingBox();await p2.mouse.move(bb.x+60,bb.y+20);await p2.mouse.down();await p2.mouse.up();
 ok('splash bar moves the window',(await p2.evaluate(()=>__posted.map(m=>m.cmd))).includes('__drag'));
 await p2.close();

 // ---------------- mini player
 const p3=await p.context().newPage();await p3.setViewportSize({width:420,height:180});
 await p3.addInitScript(fake,shimMini);await p3.goto(h.BASE+'/mini.html');await p3.waitForSelector('.mini .mini-art');await p3.waitForTimeout(400);
 const mn=await p3.evaluate(()=>Object.keys(window.pywebview.api));
 ok('mini gets only the 8 MiniApi methods',mn.length===8&&!mn.includes('mini_open')&&!mn.includes('save_export'),mn);
 await p3.evaluate(()=>{__posted.length=0});const a=await p3.locator('.mini-art').boundingBox();
 await p3.mouse.move(a.x+a.width/2,a.y+a.height/2);await p3.mouse.down();await p3.mouse.move(a.x+a.width/2+40,a.y+a.height/2+12,{steps:6});await p3.mouse.up();await p3.waitForTimeout(200);
 list=await p3.evaluate(()=>__posted.map(m=>m.cmd));
 ok('dragging the mini card hands the move to the native loop once',list.filter(x=>x==='__drag').length===1&&!list.includes('move_by'),list);
 await p3.evaluate(()=>{__posted.length=0});await p3.click('.mini .next');await p3.waitForTimeout(100);
 list=await p3.evaluate(()=>__posted.map(m=>m.cmd+(m.args&&m.args.length?':'+m.args.join():'')));
 ok('mini buttons still act',list.includes('action:next')&&!list.includes('__drag'),list);
 await p3.close();

 const bad=h.errors.filter(e=>!/favicon|ERR_|404|net::/.test(e));
 ok('no page errors',bad.length===0,bad);
 const pass=R.filter(r=>r[1]).length;console.log(`RESULT ${pass}/${R.length}`);if(pass!==R.length)process.exitCode=1;
};
