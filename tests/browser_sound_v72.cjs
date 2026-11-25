'use strict';
// v72 quick «Sound & quality» popover in the player bar: quality pill, Best / Balanced / Data saver switch that keeps
// playing from the same moment, speed chips, «pitch follows speed», keyboard and Escape.
// Runs against tests/serve_ai_v72_fixture.py (port 8792) with its local demo tracks. No live YouTube streaming check.
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs');
const BASE='http://127.0.0.1:8792',out='verification/sound-v72';fs.mkdirSync(out,{recursive:true});
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
const p=await b.newPage({viewport:{width:1440,height:900}}),errors=[],checks=[];
p.on('pageerror',e=>errors.push(e.message));
const ok=(name,condition)=>{assert(condition,name);checks.push(name);console.log('PASS',name);};
const shot=async name=>{await p.waitForTimeout(250);await p.screenshot({path:out+'/'+name+'.png'});};
try{
 await p.request.put(BASE+'/api/settings',{data:{audioQuality:'best',playbackSpeed:1,playbackPitch72:true}});
 await p.goto(BASE);
 await p.waitForFunction(()=>typeof Sound72!=='undefined'&&Sound72.ready&&!$('boot45')&&document.querySelector('#rows .card, .card'),null,{timeout:30000});
 await p.evaluate(()=>setLang('ru'));
 await p.evaluate(()=>document.querySelector('#rows .card, .card').click());
 await p.waitForFunction(()=>Player.audio&&!Player.audio.paused&&Player.audio.currentTime>.3,null,{timeout:30000});
 await p.waitForFunction(()=>$('pQuality72')&&$('pQuality72').textContent.trim().length>0,null,{timeout:15000});
 ok('quality pill sits in the player bar',await p.evaluate(()=>{const r=$('pQuality72').getBoundingClientRect();return r.width>20&&r.height>16&&r.bottom<=innerHeight;}));
 await p.click('#pQuality72');
 await p.waitForFunction(()=>!$('sound72').hidden);
 ok('popover opens and reports it',await p.evaluate(()=>$('pQuality72').getAttribute('aria-expanded')==='true'));
 ok('three quality modes, current one checked',await p.evaluate(()=>{const m=[...document.querySelectorAll('#sound72 [data-mode72]')];return m.length===3&&m.filter(x=>x.getAttribute('aria-checked')==='true').map(x=>x.dataset.mode72).join()==='best';}));
 ok('labels are translated',await p.evaluate(()=>/Лучшее качество|Максимальное качество/.test($('sound72').textContent)&&/Экономия трафика|Экономия/.test($('sound72').textContent)));
 ok('popover fits on screen',await p.evaluate(()=>{const r=$('sound72').getBoundingClientRect();return r.top>=0&&r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;}));
 await shot('open');
 const before=await p.evaluate(()=>Player.audio.currentTime);
 await p.click('#sound72 [data-mode72="data"]');await p.waitForTimeout(2500);
 const after=await p.evaluate(()=>({t:Player.audio.currentTime,paused:Player.audio.paused,S:S.audioQuality,now:$('sound72Now').textContent,checked:document.querySelector('#sound72 [data-mode72="data"]').getAttribute('aria-checked')}));
 ok('data saver is saved and marked',after.S==='data'&&after.checked==='true');
 ok('switching quality keeps playing from the same moment',!after.paused&&after.t>=before-.25);
 ok('status line explains the result',after.now.trim().length>10);
 await shot('switched');
 await p.click('#sound72 [data-speed72="1.25"]');
 ok('speed chip changes the rate',await p.evaluate(()=>Math.abs(Player.audio.playbackRate-1.25)<.001&&S.playbackSpeed===1.25));
 ok('pitch follows speed by default',await p.evaluate(()=>Player.deck.every(a=>a.preservesPitch===false)));
 await p.click('#sound72Pitch');
 ok('pitch switch keeps the natural voice',await p.evaluate(()=>Player.deck.every(a=>a.preservesPitch===true)&&S.playbackPitch72===false));
 await p.focus('#sound72 [data-mode72="data"]');await p.keyboard.press('ArrowLeft');
 ok('arrow keys move between modes',await p.evaluate(()=>S.audioQuality==='balanced'&&document.activeElement.dataset.mode72==='balanced'));
 await p.keyboard.press('Escape');await p.waitForTimeout(250);
 ok('Escape closes and returns focus to the pill',await p.evaluate(()=>$('sound72').hidden&&document.activeElement===$('pQuality72')&&$('pQuality72').getAttribute('aria-expanded')==='false'));
 await p.evaluate(()=>{S.playbackSpeed=1;Player.deck.forEach(a=>a.playbackRate=1);S.playbackPitch72=true;Sound72.applyPitch();S.audioQuality='best';saveSettings(true);});
 ok('no runtime errors',errors.length===0);
 fs.writeFileSync(out+'/checks.json',JSON.stringify({checks,errors,scope:'Local demo tracks in Chromium; quality switching with real YouTube streams is not covered here.'},null,2));
 console.log('V72_SOUND_PASS',checks.length);
}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1);});
