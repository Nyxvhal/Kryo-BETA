'use strict';
const {chromium}=require('playwright'),assert=require('assert/strict');
const {setup}=require('./reference_fixture_v24.cjs');
(async()=>{const browser=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});const page=await browser.newPage({viewport:{width:1280,height:720},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await setup(page);
 await page.evaluate(()=>{Player.audio.pause();Player.wantPlay=false;Karaoke.trackId='test';Karaoke.fetchToken=100;Karaoke.lines=[{text:'Hello world.',time:0,end:1},{text:'',time:1,end:2},{text:'I love\nmusic.',time:2,end:3},{text:'Hello world.',time:3,end:4}];Karaoke.document=null;Karaoke.synced=true;Karaoke.render();Repair33.openTranslation($('sceneMore33'));});
 await page.selectOption('#lt22Source','en');await page.selectOption('#lt22Target','ru');
 const orig=await page.evaluate(()=>JSON.stringify(Karaoke.lines));
 await page.click('#lt22Run');await page.waitForFunction(()=>!LyricsTranslate.pending,{timeout:180000});
 const result=await page.evaluate(()=>({result:LyricsTranslate.result,status:$('lt22Status').textContent}));
 console.log('result',JSON.stringify(result));assert.equal(result.result?.state,'complete');assert.equal(result.result.provider,'argos-offline-v1');assert.deepEqual(result.result.rows.map(x=>x.status),['ok','empty','ok','ok']);assert.match(result.result.rows[0].translation,/мир/i);assert.equal(result.result.rows[0].translation,result.result.rows[3].translation);assert.equal(await page.evaluate(()=>JSON.stringify(Karaoke.lines)),orig);assert.equal(await page.locator('.lyric-translated22').count(),3);
 assert.equal(await page.locator('#lt22Consent').count(),0);assert.equal(await page.locator('#karaokeSearch45').count(),0);assert.equal(await page.locator('#sceneFind34').count(),1);assert(await page.evaluate(()=>!Object.values(THEME_LIBRARY).some(x=>x.group==='vtuber')));assert(await page.evaluate(()=>['tide82','dusk82','mineral82','morning82'].every(x=>THEME_LIBRARY[x])));
 await page.evaluate(()=>LyricsTranslate.changed());await page.selectOption('#lt22Source','ja');await page.click('#lt22Run');await page.waitForFunction(()=>!LyricsTranslate.pending,{timeout:180000});assert.match(await page.locator('#lt22Status').textContent(),/setup-translate/i);
 await page.selectOption('#lt22Source','en');await page.selectOption('#lt22Target','en');await page.click('#lt22Run');assert.match(await page.locator('#lt22Status').textContent(),/разные|different/i);
 await page.selectOption('#lt22Target','ru');await page.evaluate(()=>{Repair33.closeTranslation(false);App.setPlayerControls(true)});await page.locator('#sceneMore33').click();assert(await page.locator('#sceneMenu33').isVisible());await page.keyboard.press('Escape');assert(await page.locator('#sceneMenu33').isHidden());
 for(const mode of ['split','focus','cinema','disc','viz']){await page.evaluate(mode=>{S.karaokeMode=mode;App.applyKaraoke()},mode);assert(await page.locator('#sceneMode33').count());}
 assert.deepEqual(errors,[]);console.log('PASS: real Argos translation, alignment, errors, themes and menus');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
