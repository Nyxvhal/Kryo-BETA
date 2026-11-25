'use strict';
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs');
(async()=>{const browser=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
const folder=__dirname+'/../verification/settings-kryo';fs.mkdirSync(folder,{recursive:true});
try{for(const dpr of [1,1.25,1.5,2]){
 const page=await browser.newPage({viewport:{width:1280,height:720},deviceScaleFactor:dpr,reducedMotion:'reduce'});let errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8779');await page.waitForFunction(()=>typeof Workspace!=='undefined'&&Workspace.ready);
 for(const [w,h] of [[390,844],[768,900],[1280,720],[1366,768],[1920,1080]])for(const scale of [85,100,125])for(const framed of [false,true]){
  await page.setViewportSize({width:w,height:h});await page.evaluate(({scale,framed})=>{document.body.classList.toggle('framed',framed);S.uiScale=scale;Look.apply();Workspace.openSettings();},{scale,framed});await page.waitForTimeout(30);
  const g=await page.evaluate(()=>{let r=$('mSettings').getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height,r:r.right,b:r.bottom,zoom:parseFloat(getComputedStyle(document.body).zoom)||1,transform:getComputedStyle($('mSettings')).transform};});
  const title=framed?34*g.zoom:0, tolerance=2;
  assert(g.x>=-tolerance&&g.y>=title-tolerance&&g.r<=w+tolerance&&g.b<=h+tolerance,`${w}x${h} scale ${scale} framed ${framed}: ${JSON.stringify(g)}`);
  assert(Math.abs(g.x+g.w/2-w/2)<tolerance&&Math.abs(g.y+g.h/2-(h+title)/2)<tolerance,`${w}x${h} center scale ${scale} framed ${framed}: ${JSON.stringify(g)}`);
  assert.equal(g.transform,'none');
  if(dpr===1&&scale===100&&framed)await page.screenshot({path:folder+`/settings-framed-${w}x${h}.png`});
 }
 assert.deepEqual(errors,[]);console.log(`PASS 30 settings layouts with emulated deviceScaleFactor ${dpr}`);await page.close();
}
 const p=await browser.newPage({viewport:{width:1280,height:720}});await p.goto('http://127.0.0.1:8779');await p.waitForFunction(()=>typeof Workspace!=='undefined'&&Workspace.ready);
 await p.locator('#navSettings').click();await p.waitForSelector('#mSettings.on');assert.equal(await p.getAttribute('#mSettings','role'),'dialog');
 await p.setViewportSize({width:768,height:900});await p.waitForTimeout(150);const resized=await p.locator('#mSettings').boundingBox();assert(resized.x>=0&&resized.y>=0&&resized.x+resized.width<=768&&resized.y+resized.height<=900);await p.keyboard.press('Tab');assert(await p.evaluate(()=>$('mSettings').contains(document.activeElement)));await p.setViewportSize({width:1280,height:720});
 await p.keyboard.press('Escape');await p.waitForFunction(()=>!$('mSettings').classList.contains('on'));await p.waitForTimeout(50);assert.equal(await p.evaluate(()=>document.activeElement.id),'navSettings');
 await p.locator('#navSettings').click();await p.waitForSelector('#mSettings.on');await p.locator('#mSettings .workspace-settings-head button.ib').click();await p.waitForFunction(()=>!$('mSettings').classList.contains('on'));await p.waitForTimeout(50);assert.equal(await p.evaluate(()=>document.activeElement.id),'navSettings');await p.locator('#navSettings').click();await p.waitForSelector('#mSettings.on');await p.mouse.click(5,5);await p.waitForFunction(()=>!$('mSettings').classList.contains('on'));await p.waitForTimeout(50);assert.equal(await p.evaluate(()=>document.activeElement.id),'navSettings');console.log('PASS real settings button, Escape, close, outside click, focus restoration');await p.close();
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
