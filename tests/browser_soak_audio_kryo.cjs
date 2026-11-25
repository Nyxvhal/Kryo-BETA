'use strict';
// Requires serve_soak_kryo.py, whose SQLite cache lives in a TemporaryDirectory.
// Generated tone and local HTTP only; this is not a live provider or hardware test.
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs');
const {execFileSync}=require('child_process');
const out='verification/soak-kryo';fs.mkdirSync(out,{recursive:true});
function chromeRss(){try{const lines=execFileSync('ps',['-eo','pid=,ppid=,rss=,comm='],{encoding:'utf8'}).trim().split('\n').map(x=>x.trim().split(/\s+/));const descendants=new Set([process.pid]);for(let n=0;n<8;n++)for(const [pid,ppid] of lines)if(descendants.has(+ppid))descendants.add(+pid);return lines.filter(([pid,,,cmd])=>descendants.has(+pid)&&/chrom/i.test(cmd)).reduce((a,x)=>a+Number(x[2]||0),0)}catch{return null}}
(async()=>{const browser=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
const p=await browser.newPage({viewport:{width:1280,height:720},reducedMotion:'reduce'}),errors=[],samples=[];p.on('pageerror',e=>errors.push(e.message));
try{
 await p.goto('http://127.0.0.1:18779');await p.waitForFunction(()=>document.body.classList.contains('ui-v24')&&typeof Player!=='undefined');
 await p.evaluate(async()=>{
  S.noAnim=true;S.fade=0;S.repeat='off';S.shuffle=false;S.endlessRadio=false;S.prefetch=false;
  window.soak={ends:[],audioErrors:[],requests:[],begin:Date.now()};
  const finish=Player.finish.bind(Player);Player.finish=function(a){if(a===this.audio&&a.ended&&this.current&&this.completedToken!==this.loadToken)soak.ends.push(this.current.id);return finish(a)};
  Player.deck.forEach(a=>a.addEventListener('error',()=>soak.audioErrors.push({code:a.error?.code,id:Player.current?.id})));
  const tracks=Array.from({length:12},(_,i)=>({id:'local:soak-'+i,title:'Soak '+i,artist:'Local test',source:'local',duration:10,thumbnail:'/img/avatars/kryonyx-core.png'}));
  window.soakTimers=[setInterval(async()=>{try{const r=await fetch('/api/cache/audio');soak.requests.push({kind:'stats',status:r.status})}catch(e){soak.requests.push({kind:'stats',error:String(e)})}},1500),setInterval(async()=>{try{const r=await fetch('/api/cache/audio',{method:'DELETE'});soak.requests.push({kind:'clear',status:r.status})}catch(e){soak.requests.push({kind:'clear',error:String(e)})}},20000),setInterval(async()=>{let id=Player.current?.id;if(!id)return;try{const r=await fetch('/api/stream?id='+encodeURIComponent(id));const b=await r.arrayBuffer();soak.requests.push({kind:'parallel',status:r.status,bytes:b.byteLength})}catch(e){soak.requests.push({kind:'parallel',error:String(e)})}},11000)];
  Player.play(tracks[0],tracks,0);
 });
 const cdp=await p.context().newCDPSession(p);await cdp.send('Performance.enable');
 const started=Date.now();while(Date.now()-started<132000){await p.waitForTimeout(5000);const state=await p.evaluate(()=>({id:Player.current?.id,time:Player.audio.currentTime,paused:Player.audio.paused,ended:Player.audio.ended,index:Player.index,ends:soak.ends.length,requests:soak.requests.length}));const metrics=(await cdp.send('Performance.getMetrics')).metrics;const get=n=>metrics.find(m=>m.name===n)?.value;samples.push({atSeconds:Math.round((Date.now()-started)/1000),state,jsHeapBytes:get('JSHeapUsedSize'),rendererTaskSeconds:get('TaskDuration'),browserProcessTreeRssKiB:chromeRss()});if(state.ends>=12)break;}
 const result=await p.evaluate(()=>{soakTimers.forEach(clearInterval);Player.wantPlay=false;Player.audio.pause();return soak});
 result.samples=samples;result.pageErrors=errors;result.environment='Linux headless Chromium, synthetic 10-second WAV, isolated local fixture and temporary SQLite cache; process RSS sums Chromium processes and may double count shared memory.';
 fs.writeFileSync(out+'/audio-soak.json',JSON.stringify(result,null,2));
 assert.equal(result.ends.length,12,'12 natural completions observed by player' );assert.deepEqual(result.ends,Array.from({length:12},(_,i)=>'local:soak-'+i));assert.equal(result.audioErrors.length,0);assert.equal(errors.length,0);
 assert(result.requests.some(r=>r.kind==='clear'&&r.status===200));assert(result.requests.some(r=>r.kind==='parallel'&&r.status===200&&r.bytes>0));assert(result.requests.filter(r=>r.kind==='stats').length>30);assert(result.requests.every(r=>r.status===200),'cache and parallel requests succeed');
 console.log('AUDIO_SOAK_PASS',result.ends.length,'tracks',result.requests.length,'requests',samples.length,'samples');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
