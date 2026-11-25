'use strict';
// v73 browser checks, one fresh page per part (tests/browser_v73/*.cjs):
//   menu      the ⋮ menu opens beside its button, inside the window, keyboard works
//   search    races between queries, hints, tabs, source chips, "show more", Back
//   buttons   every control of the player bar, its menu, Now Playing and the queue does something
//   motion    button animations: ripple, press, play/pause swap, like burst, reduced motion
//   settings  themes gallery is kept between visits, filters, deferred tab scroll
//   minidrag  the mini player moves by its whole card, fractions kept, controls stay clicks
//   shell     the Rust shell's window bridge (desktop-rs) with frame.js, mini.html and the splash
// Runs against tests/serve_classic_v63_fixture.py (port 8790). ONLY=menu,shell runs a subset.
const {chromium}=require('playwright'),fs=require('fs'),path=require('path');
const BASE=process.env.BASE||'http://127.0.0.1:8790',OUT=process.env.OUT||'verification/v73';
const PARTS=(process.env.ONLY||'menu,search,buttons,motion,settings,minidrag,shell').split(',').map(s=>s.trim()).filter(Boolean);
(async()=>{
 fs.mkdirSync(OUT,{recursive:true});
 const b=await chromium.launch({executablePath:process.env.CHROMIUM||'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
 const summary=[],failures=[];const log=console.log;
 for(const part of PARTS){
  const scenario=require(path.join(__dirname,'browser_v73',part+'.cjs'));
  const ctx=await b.newContext({viewport:{width:1920,height:1080}});const p=await ctx.newPage();
  const errors=[];p.on('pageerror',e=>errors.push('pageerror: '+e.message));
  const h={BASE,OUT,errors,
   boot:async(url=BASE)=>{await p.goto(url);await p.waitForFunction(()=>typeof App!=='undefined'&&!document.getElementById('boot45')&&!document.documentElement.classList.contains('booting45'),null,{timeout:30000});},
   shot:async(name,opt={})=>{await p.screenshot({path:OUT+'/'+name+'.png',...opt});},
   ctl:async q=>p.request.get(BASE+'/fixture/video57?'+q),
   wait:ms=>p.waitForTimeout(ms)};
  let pass=0,fail=0;
  console.log=(...a)=>{for(const line of a.join(' ').split('\n')){if(/^PASS /.test(line))pass++;else if(/^FAIL /.test(line)){fail++;failures.push(part+': '+line.slice(0,400));}}log(...a);};
  const t0=Date.now();
  try{await scenario(p,h,[]);}catch(e){fail++;failures.push(part+': SCENARIO ERROR '+(e.stack||e).toString().slice(0,600));}
  console.log=log;
  const pageErrors=errors.filter(e=>!/favicon|net::ERR_|404/.test(e));
  if(pageErrors.length){fail++;failures.push(part+': page errors: '+pageErrors.slice(0,5).join(' | '));}
  if(!pass&&!fail){fail++;failures.push(part+': no checks ran');}
  summary.push(`${part}: ${pass} passed, ${fail} failed (${((Date.now()-t0)/1000).toFixed(0)} s)`);
  await ctx.close();
 }
 await b.close();
 log('\n'+summary.join('\n'));
 if(failures.length){log('\nFAILURES:\n'+failures.join('\n'));process.exit(1);}
 log(`\nOK ${PARTS.length} parts`);process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
