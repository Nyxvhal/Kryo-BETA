/* Offline regression: start `python -m http.server 8766 --directory kryonyx/web` first. */
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.KRYO_TEST_URL||'http://127.0.0.1:8766';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM||'/usr/local/bin/chromium',args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1280,height:800}});let settings={settingsRev:8,upgrade30:true,repair33:true}, state={lyricsPicks:{'test:a':42},lyricsOffsets:{'test:a':1.25},lyricsAutoResults:{},player:{queue:[{id:'test:a',title:'A',artist:'Artist',duration:100}],index:0,position:0}};let requests=[],errors=[];
 await context.route('**/api/**',async r=>{const u=new URL(r.request().url()),path=u.pathname,method=r.request().method();requests.push([path,u.search,method]);
  if(path==='/api/settings'){if(method==='PUT')settings={...settings,...r.request().postDataJSON()};return r.fulfill({json:method==='GET'?settings:{ok:true}})}
  if(path==='/api/state'){const k=u.searchParams.get('key');if(method==='PUT'){const v=r.request().postDataJSON();state[v.key]=v.value;return r.fulfill({json:{ok:true}})}if(k==='lyricsPicks')await new Promise(r=>setTimeout(r,120));return r.fulfill({json:{value:state[k]??null}})}
  if(path==='/api/lyrics/search'){await new Promise(r=>setTimeout(r,80));return r.fulfill({json:{items:[{id:88,title:'Manual',artist:'Artist',synced:true}]}})}
  if(path==='/api/lyrics'){const id=u.searchParams.get('track_id');if(id==='test:slow')await new Promise(r=>setTimeout(r,250));if(id==='test:error')return r.fulfill({status:503,json:{error:'offline'}});if(id==='test:none')return r.fulfill({json:{lines:[],synced:false}});return r.fulfill({json:{synced:true,duration:100,lines:[{time:1,text:(u.searchParams.get('lrc')?'picked:':'auto:')+id},{time:4,text:'second'}],document:id==='test:a'?{version:2,lines:[{text:'A',start:1,end:2}]}:null}})}
  if(path==='/api/health')return r.fulfill({json:{ok:true,sources:[],stats:{}}});
  if(path==='/api/likes')return r.fulfill({json:{items:[],ids:[]}});
  if(path==='/api/recommend'||path==='/api/discovery')return r.fulfill({json:{rows:[]}});
  return r.fulfill({json:{ok:true,items:[]}});
 });
 const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error'&&m.text().includes('[boot]'))errors.push(m.text())});
 const boot=async()=>{await p.goto(base);await p.waitForFunction(()=>!document.documentElement.classList.contains('booting45'));await p.waitForFunction(()=>Karaoke.trackId==='test:a'&&Karaoke.lines.length>0)};
 try{
  let cacheCalls=0;
  await p.route('**/api/test-cache',async r=>{const n=++cacheCalls;if(n===1)await new Promise(resolve=>setTimeout(resolve,200));await r.fulfill({json:{n}})});
  await boot();const cache=await p.evaluate(async()=>{const first=cachedApi('/api/test-cache');await new Promise(r=>setTimeout(r,40));dropCache('/api/test-cache');const fresh=await cachedApi('/api/test-cache');await first;return [fresh.n,(await cachedApi('/api/test-cache')).n]});assert.deepEqual(cache,[2,2]);assert.equal(await p.evaluate(()=>S.vizWave),false);assert.equal(await p.evaluate(()=>Karaoke.lines[0].text),'picked:test:a');assert.equal(await p.evaluate(()=>Karaoke.offsets['test:a']),1.25);assert(requests.some(([path,q])=>path==='/api/lyrics'&&q.includes('lrc=42')));
  await p.evaluate(()=>App.openNow());await p.locator('#karaokeMenuButton45').click();assert(await p.locator('#karaokeMenu45').isVisible());assert(await p.locator('#karaokeEdit45').isEnabled());await p.keyboard.press('Escape');assert(await p.locator('#karaokeMenu45').isHidden());assert(await p.locator('#now').evaluate(n=>n.classList.contains('on')));
  await p.locator('#karaokeMenuButton45').click();await p.locator('#karaokeStudio45').click();assert(await p.locator('#mKaraokeGenerate').isVisible());await p.evaluate(()=>closeModals());
  await p.locator('#karaokeMenuButton45').click();await p.locator('#karaokeBackground46').click();assert(await p.locator('.pane[data-pane=karaoke]').isVisible());
  await p.locator('#kSize button').last().click();await p.locator('#kAlign button').last().click();await p.locator('[data-sw=karaokeDim]').click();await p.locator('[data-sw=autoLyrics]').click();assert.equal(await p.evaluate(()=>S.autoLyrics),false);assert.match(await p.locator('#lyrics').textContent(),/turned off/);
  await p.locator('#kFind').click();await p.waitForSelector('.lyr-pick');await p.locator('.lyr-pick').first().click();await p.waitForFunction(()=>Karaoke.lines[0]?.text==='picked:test:a');assert.equal(await p.evaluate(()=>S.autoLyrics),false);
  await p.evaluate(async()=>{await Karaoke.onTrack(Player.current,{force:true});Karaoke.nudge(.5);await new Promise(r=>setTimeout(r,800));await saveSettings(true)});assert.equal(state.lyricsOffsets['test:a'],1.75);assert.equal(state.lyricsPicks['test:a'],88);
  await p.reload();await p.waitForFunction(()=>!document.documentElement.classList.contains('booting45'));await p.waitForFunction(()=>Karaoke.trackId==='test:a');assert.deepEqual(await p.evaluate(()=>[S.karaokeSize,S.karaokeAlign,S.karaokeDim,S.autoLyrics,S.vizWave]),['l','center',false,false,false]);assert.equal(await p.evaluate(()=>Karaoke.offsets['test:a']),1.75);
  await p.evaluate(async()=>{S.autoLyrics=true;Player.current={id:'test:slow',title:'slow'};const a=Karaoke.onTrack(Player.current);Player.current={id:'test:none',title:'none'};await Karaoke.onTrack(Player.current);await a;});assert.match(await p.locator('#lyrics').textContent(),/Lyrics not found/);assert.equal(await p.evaluate(()=>Karaoke.trackId),'test:none');assert.equal(await p.locator('#kEditNow').isDisabled(),true);
  await p.evaluate(async()=>{Player.current={id:'test:error',title:'error'};await Karaoke.onTrack(Player.current)});assert.match(await p.locator('#lyrics').textContent(),/Search failed/);
  await p.evaluate(async()=>{Player.current={id:'test:a',title:'A'};await Karaoke.onTrack(Player.current);Karaoke.openFind();Player.current={id:'test:none',title:'none'};await Karaoke.onTrack(Player.current)});await p.waitForTimeout(150);assert(!(await p.locator('#mLyrics').evaluate(n=>n.classList.contains('on'))));assert.equal(state.lyricsPicks['test:none'],undefined);
  await p.evaluate(()=>{App.openNow();});await p.locator('#karaokeMenuButton45').click();await p.evaluate(()=>$('now').classList.remove('on'));await p.waitForTimeout(30);assert(await p.locator('#karaokeMenu45').isHidden());
  for(const value of [true,false]){await p.evaluate(async v=>{S.vizWave=v;await saveSettings(true)},value);await p.reload();await p.waitForFunction(()=>!document.documentElement.classList.contains('booting45'));assert.equal(await p.evaluate(()=>S.vizWave),value)}
  await p.setViewportSize({width:390,height:844});await p.evaluate(()=>App.openNow());await p.locator('#karaokeMenuButton45').click();const rect=await p.locator('#karaokeMenu45').boundingBox();assert(rect.x>=0&&rect.x+rect.width<=391);await p.keyboard.press('Escape');assert(await p.locator('#karaokeMenu45').isHidden());
  settings={...settings,upgrade30:false,repair33:false,karaokeStyle:'stars',lyricsFit:true};await p.reload();await p.waitForFunction(()=>!document.documentElement.classList.contains('booting45'));assert.deepEqual(await p.evaluate(()=>[S.karaokeStyle,S.lyricsFit]),['stars',true]);
  assert.deepEqual(errors,[]);console.log('PASS: boot, restored pick/offset, menu, settings, manual search, track races, missing/error, persistence, mobile.');
 }finally{await context.close();await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
