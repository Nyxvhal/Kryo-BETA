'use strict';
// v72 optional AI module in the UI: clip AI tab (Real-ESRGAN ×2 + RIFE on a tiny synthetic clip), version switching
// without losing the position, deletion; wallpaper dialog after picking a file, «Fast» model, undo/restore, «don't ask»,
// and the install state when the AI Python is missing.
// Runs against tests/serve_ai_v72_fixture.py (port 8792). The real-engine part needs an AI Python with torch
// (AI72_PYTHON, default /data/kryo/aivenv/bin/python) and the weights in the fixture data dir; otherwise it is skipped
// and only the «not installed» paths are checked. CPU only: this is NOT a GPU performance test.
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs');
const BASE='http://127.0.0.1:8792',out='verification/ai-v72';fs.mkdirSync(out,{recursive:true});
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
const p=await b.newPage({viewport:{width:1440,height:900}}),errors=[],checks=[],notes=[];
p.on('pageerror',e=>errors.push(e.message));
const ok=(name,condition)=>{assert(condition,name);checks.push(name);console.log('PASS',name);};
const shot=async name=>{await p.waitForTimeout(250);await p.screenshot({path:out+'/'+name+'.png'});};
const text=sel=>p.evaluate(s=>{const n=document.querySelector(s);return n?n.innerText.replace(/\s+/g,' ').trim():'';},sel);
try{
 const fx=await (await p.request.get(BASE+'/fixture/ai72?engine=real')).json();
 const real=fx.engine==='real';
 await p.request.put(BASE+'/api/settings',{data:{clipAutoNext:false,clipLoop:true,aiWallAsk72:true,aiClip72:{target:216,style:'general',smooth:false}}});
 await p.request.get(BASE+'/fixture/video57?cookies=ready');
 await p.addInitScript(()=>{window.pywebview={api:{close(){},minimize(){},maximize(){},restore(){},info:async()=>({maximized:true,min_width:400,min_height:560,frameless:true}),set_on_top:async()=>true,toggle_fullscreen:async()=>true}};addEventListener('DOMContentLoaded',()=>setTimeout(()=>dispatchEvent(new Event('pywebviewready')),0));});
 await p.goto(BASE);
 await p.waitForFunction(()=>typeof AI72!=='undefined'&&AI72.ready&&typeof Cinema72!=='undefined'&&Cinema72.ready&&!$('boot45'),null,{timeout:30000});
 await p.evaluate(()=>{localStorage.removeItem('kryonyx.aiwall72');localStorage.removeItem('kryonyx.aiclip72');setLang('ru');return Clips.open(null);});

 /* ---------- Clip: AI tab */
 await p.waitForSelector('.video-card57');await p.locator('.video-card57').first().click();
 await p.waitForFunction(()=>Clips.job&&Clips.job.offline_ready&&Clips.video.currentTime>.3,null,{timeout:60000});
 // Results of an earlier run against the same fixture would turn «Enhance» into «Play this version».
 await p.evaluate(async()=>{const d=await api('/api/ai/clip?session='+Clips.job.id);for(const v of d.items||[])await api('/api/ai/result/'+v.key+'.mp4',{method:'DELETE'}).catch(()=>{});await AI72.loadVersions(true);});
 await p.mouse.move(700,400);await p.click('#watchSettings58');await p.click('#cxTab72-ai');
 await p.waitForFunction(()=>AI72.info&&document.querySelector('#cxPage72-ai .ai72-device'),null,{timeout:120000});
 ok('AI tab shows the «powerful PC» badge',await text('#cxPage72-ai .ai72-badge')==='Нужен мощный ПК');
 ok('AI tab names the device and warns about it',(await text('#cxPage72-ai .ai72-device')).length>3&&(await text('#cxPage72-ai p.ai72-warn')).includes('NVIDIA'));
 if(real){
  ok('CPU-only machine gets the slow-processor warning',(await text('#cxPage72-ai p.ai72-warn')).includes('процессоре'));
  ok('resolution choices stop at ×4 of the source',await p.evaluate(()=>[...$('aiRes72').options].map(o=>o.value).join()==='0,216'));
  ok('start button and summary are ready',await p.evaluate(()=>!$('aiStart72').disabled&&document.querySelector('.ai72-run-note').textContent.includes('108p → 216p')));
  ok('menu stays inside the player',await p.evaluate(()=>{const m=$('watchMenu58').getBoundingClientRect(),s=$('clipStage').getBoundingClientRect();return m.top>=s.top-1&&m.bottom<=s.bottom+1&&m.right<=s.right+1;}));
  await shot('clip-ai-tab');
  await p.click('#aiSmooth72');
  ok('request combines upscale and smooth motion',await p.evaluate(()=>{const r=AI72.request(Clips.job);return r.upscale==='x2'&&r.height===216&&r.smooth;}));
  await p.click('#aiStart72');
  await p.waitForSelector('#aiProg72:not([hidden])',{timeout:30000});
  await p.waitForFunction(()=>/кадр/.test($('aiProg72').textContent),null,{timeout:60000});
  ok('progress shows stage, target and frame count',await p.evaluate(()=>/216p/.test($('aiProg72').textContent)&&/24 к\/с/.test($('aiProg72').textContent)));
  await shot('clip-ai-progress');
  const t0=Date.now();
  await p.waitForFunction(()=>AI72.versions.length>0&&!AI72.runningFor(Clips.job.id),null,{timeout:400000});
  notes.push('CPU job ×2+RIFE on 4 s 192×108 12 fps: '+Math.round((Date.now()-t0)/1000)+' s');
  const v=await p.evaluate(()=>AI72.versions[0]);
  ok('finished version is 384×216 at 24 fps',v.width===384&&v.height===216&&Math.round(v.fps)===24);
  ok('finish toast offers to switch',(await p.evaluate(()=>$('toast').textContent)).includes('Включить'));
  ok('versions list shows original and AI version',await p.evaluate(k=>!!$('aiVer72-original')&&!!$('aiVer72-'+k),v.key));
  await shot('clip-ai-versions');
  await p.evaluate(()=>{Clips.video.currentTime=1.5;});await p.waitForTimeout(300);
  const before=await p.evaluate(()=>Clips.video.currentTime);
  await p.click('#aiVer72-'+v.key);
  await p.waitForFunction(k=>Clips.video.getAttribute('src').includes(k)&&Clips.video.readyState>=2,v.key,{timeout:20000});
  const after=await p.evaluate(()=>({t:Clips.video.currentTime,w:Clips.video.videoWidth,paused:Clips.video.paused,audio:!Clips.audio.paused,err:!$('clipError').hidden}));
  ok('AI version plays at the same moment with the original sound',after.w===384&&!after.paused&&after.audio&&!after.err&&Math.abs(after.t-before)<1.2);
  ok('active version is marked',await p.evaluate(k=>$('aiVer72-'+k).getAttribute('aria-checked')==='true',v.key));
  await shot('clip-ai-playing');
  await p.click('#aiVer72-original');
  await p.waitForFunction(()=>!Clips.video.getAttribute('src').includes('/api/ai/')&&Clips.video.readyState>=2,null,{timeout:15000});
  ok('original comes back',await p.evaluate(()=>Clips.video.videoWidth===192&&!Clips.video.paused));
  ok('same options now offer the saved version',await p.evaluate(()=>/версию/.test($('aiStart72').textContent)));
  await p.click('#aiDel72-'+v.key);
  ok('delete asks for a second click',(await p.evaluate(k=>$('aiDel72-'+k).textContent,v.key)).includes('Удалить?'));
  await p.click('#aiDel72-'+v.key);await p.waitForFunction(()=>AI72.versions.length===0,null,{timeout:15000});
  ok('deleted version disappears',await p.evaluate(()=>!document.querySelector('#cxPage72-ai .ai72-versions')));
 }else notes.push('Real AI engine not available: processing checks skipped');
 await p.click('#watchSettings58').catch(()=>{});
 await p.evaluate(()=>Clips.close());

 /* ---------- Wallpaper */
 const img=await p.evaluate(()=>{const c=document.createElement('canvas');c.width=320;c.height=180;const g=c.getContext('2d');const gr=g.createLinearGradient(0,0,320,180);gr.addColorStop(0,'#5b2a86');gr.addColorStop(1,'#3fb5c8');g.fillStyle=gr;g.fillRect(0,0,320,180);g.strokeStyle='#fff3d6';g.lineWidth=5;g.beginPath();g.arc(160,90,52,0,7);g.stroke();return c.toDataURL('image/jpeg',.9).split(',')[1];});
 const file={name:'wall72.jpg',mimeType:'image/jpeg',buffer:Buffer.from(img,'base64')};
 await p.evaluate(()=>{Workspace.openSettings();App.openPane('look2');});
 await p.waitForSelector('#wallAiRow72');
 ok('AI rows follow the image-link row',await p.evaluate(()=>$('wallUrl').closest('.set').nextElementSibling===$('wallAiRow72')&&$('wallAiRow72').nextElementSibling===$('wallAiAskRow72')));
 ok('enhance button waits for a custom picture',await p.evaluate(()=>S.wallSrc==='local'||$('wallAi72').disabled));
 await p.setInputFiles('#wallFile',file);
 await p.waitForSelector('#aiWall72:not([hidden])',{timeout:15000});
 await p.waitForFunction(()=>/1280 × 720/.test($('aiWall72').textContent),null,{timeout:20000});
 ok('dialog offers AI or keeping the picture',await p.evaluate(()=>$('aiWallGo72').textContent.includes('Улучшить')&&$('aiWallKeep72').textContent.includes('Оставить')));
 ok('dialog warns that a powerful PC is needed',(await text('#aiWall72 .ai72-kicker')).includes('Нужен мощный ПК')&&(await text('#aiWall72 p.ai72-warn')).includes('NVIDIA'));
 ok('dialog keeps focus inside without a focus frame',await p.evaluate(()=>$('aiWall72').contains(document.activeElement)&&getComputedStyle(document.querySelector('#aiWall72 .ai72-dialog')).outlineStyle==='none'));
 await shot('wall-dialog');
 if(real){
  await p.click('#aiWallStyle72-fast');await p.click('#aiWallGo72');
  await p.waitForFunction(()=>/^\/api\/wallpaper\/file\//.test(S.wallSrc||''),null,{timeout:240000});
  const size=await p.evaluate(async()=>{const im=new Image();im.src=S.wallSrc;await im.decode();return [im.naturalWidth,im.naturalHeight];});
  ok('enhanced wallpaper is applied at 1280×720',size[0]===1280&&size[1]===720);
  ok('undo toast is shown',(await p.evaluate(()=>$('toast').textContent)).includes('Отменить'));
  ok('done state offers restoring the original',await p.evaluate(()=>AI72.wall&&AI72.wall.phase==='done'?$('aiWallKeep72').textContent.includes('Вернуть'):true));
  await shot('wall-done');
  await p.waitForFunction(()=>$('aiWall72').hidden,null,{timeout:5000});
  ok('settings button switches to «Restore original»',(await p.evaluate(()=>$('wallAi72').textContent)).includes('Вернуть оригинал'));
  await p.click('#wallAi72');await p.waitForFunction(()=>S.wallSrc==='local',null,{timeout:10000});
  ok('restore returns the original picture',await p.evaluate(()=>$('wallAi72').textContent.includes('Улучшить')));
 }else{await p.click('#aiWallKeep72');await p.waitForFunction(()=>$('aiWall72').hidden);}
 // «Don't ask» stops the dialog for the next picture
 await p.evaluate(()=>{S.aiWallAsk72=false;saveSettings(true);AI72.paintWallRow();});
 ok('ask switch reflects the setting',await p.evaluate(()=>$('wallAiAsk72').getAttribute('aria-checked')==='false'));
 await p.setInputFiles('#wallFile',{...file,buffer:Buffer.concat([file.buffer,Buffer.from([0])])});
 await p.waitForTimeout(1500);
 ok('no dialog when asking is turned off',await p.evaluate(()=>$('aiWall72').hidden));
 await p.evaluate(()=>{S.aiWallAsk72=true;saveSettings(true);AI72.paintWallRow();});
 // AI Python missing → install UI
 await p.request.get(BASE+'/fixture/ai72?engine=missing');
 await p.evaluate(()=>{AI72.info=null;AI72.infoAt=0;});
 await p.click('#wallAi72');await p.waitForSelector('#aiWall72:not([hidden])');
 await p.waitForFunction(()=>AI72.info&&!AI72.engine().installed,null,{timeout:30000});await p.waitForTimeout(300);
 ok('missing module shows a readable install button',await p.evaluate(()=>{const b=document.querySelector('#aiWall72 .ai72-install .ai72-primary');if(!b)return false;const c=getComputedStyle(b);return b.textContent.includes('Установить')&&c.color!==c.backgroundColor;}));
 ok('enhance is disabled until installed',await p.evaluate(()=>$('aiWallGo72').disabled));
 await shot('wall-missing');
 await p.keyboard.press('Escape');await p.waitForTimeout(300);
 ok('Escape closes the dialog',await p.evaluate(()=>$('aiWall72').hidden));
 await p.evaluate(()=>closeModals());
 await p.evaluate(()=>Clips.open(null));await p.waitForSelector('.video-card57');await p.locator('.video-card57').first().click();
 await p.waitForFunction(()=>Clips.video.currentTime>.2,null,{timeout:60000});
 await p.mouse.move(700,400);await p.click('#watchSettings58');await p.click('#cxTab72-ai');
 await p.waitForSelector('#cxPage72-ai .ai72-setup',{timeout:30000});
 ok('clip tab offers installing instead of starting',await p.evaluate(()=>!$('aiStart72')&&/Установить/.test(document.querySelector('#cxPage72-ai .ai72-setup').textContent)));
 await shot('clip-missing');
 ok('no runtime errors',errors.length===0);
 fs.writeFileSync(out+'/checks.json',JSON.stringify({checks,errors,notes,real,scope:'Local synthetic 4 s 192x108 clip and 320x180 picture; CPU-only PyTorch in the sandbox. No GPU/CUDA, Windows or WebView2 verification.'},null,2));
 console.log('V72_AI_PASS',checks.length,notes.join(' | '));
}finally{await p.request.get(BASE+'/fixture/ai72?engine=real').catch(()=>{});await b.close();}})().catch(e=>{console.error(e);process.exit(1);});
