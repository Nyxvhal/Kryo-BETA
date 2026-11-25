'use strict';
const {chromium}=require('playwright');
const assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.route('**/api/state?key=lyrics*',async route=>{await new Promise(r=>setTimeout(r,2500));await route.continue()});
  await page.goto('http://127.0.0.1:8779');
  await page.waitForFunction(()=>document.body.classList.contains('ui-v9')&&!Video57.ready&&!!App.bootReady,{timeout:10000});
  await page.evaluate(()=>{window.earlyClipOpen=Clips.open(null)});
  await page.evaluate(()=>window.earlyClipOpen);
  assert.deepEqual(await page.evaluate(()=>({ready:Video57.ready,active:Clips.active,mode:$('clips').dataset.videoMode57,nav:document.querySelectorAll('.video-nav57').length,gate:document.querySelectorAll('#videoGate57').length})),{ready:true,active:true,mode:'gate',nav:1,gate:1});
  await page.evaluate(async()=>{await Clips.close();await Clips.open(null)});
  assert.deepEqual(await page.evaluate(()=>({active:Clips.active,mode:$('clips').dataset.videoMode57,nav:document.querySelectorAll('.video-nav57').length,gate:document.querySelectorAll('#videoGate57').length})),{active:true,mode:'gate',nav:1,gate:1});
  assert.deepEqual(errors,[]);console.log('EARLY_CLIPS_BOOT_PASS');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
