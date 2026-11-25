'use strict';const{chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');const{setup}=require('./reference_fixture_v24.cjs');const out=__dirname+'/../verification/repair-v44';
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});const checks=[],errors=[],ok=(name,value)=>{assert(value,name);checks.push(name);console.log('PASS',name)};
try{
 const p=await b.newPage({viewport:{width:1440,height:1000}});p.on('pageerror',e=>errors.push(e.message));await setup(p);await p.waitForFunction(()=>document.body.classList.contains('ui-v44'));
 for(const mode of ['split','focus','cinema','disc','viz']){
  await p.selectOption('#sceneMode33',mode);await p.waitForTimeout(100);
  ok('lyrics chooser visible: '+mode,await p.locator('#sceneFind34').isVisible());
  ok('hide button only in disc/viz: '+mode,(await p.locator('#sceneRestore30').isVisible())===['disc','viz'].includes(mode));
  if(['disc','viz'].includes(mode)){
   await p.evaluate(()=>App.setPlayerControls(true));const ctl=mode==='disc'?'.disc-ctl':'.viz-ctl';
   ok('controls initially visible: '+mode,await p.locator(ctl).isVisible());await p.click('#sceneRestore30');
   ok('bottom controls hidden: '+mode,await p.locator(ctl).isHidden());
   ok('restore remains visible: '+mode,await p.locator('#sceneRestore30').isVisible());await p.click('#sceneRestore30');ok('restore bottom controls: '+mode,await p.locator(ctl).isVisible());
  }
 }
 await p.selectOption('#sceneMode33','split');
 // Fixture translations are explicitly mocked: integration checks, not a claim of live service availability.
 await p.route('**/api/lyrics/search?**',async r=>{const title=new URL(r.request().url()).searchParams.get('title');if(title==='slow')await new Promise(r=>setTimeout(r,350));await r.fulfill({json:{items:[{id:title==='slow'?901:902,title:title==='slow'?'Stale':'New lyrics',artist:'Test',synced:true,lines:2,duration:172}]}});});
 await p.click('#sceneFind34');ok('lyrics search dialog opens',await p.locator('#mLyrics').isVisible());await p.waitForSelector('.lyr-pick');
 ok('cannot attach chosen lyrics to a different track',await p.evaluate(()=>{const old=Player.current;Player.current={id:'other'};Karaoke.usePick(901);const safe=!Karaoke.picks.other;Player.current=old;return safe;}));
 await p.route('**/api/lyrics?**',r=>r.fulfill({json:{synced:true,duration:172,lines:[{time:0,text:'New selected lyric'},{time:30,text:'Another selected line'}]}}));
 await p.route('**/api/lyrics/translate',r=>{const body=r.request().postDataJSON();return r.fulfill({json:{translations:body.lines.map(x=>'Translated: '+x)}});});
 await p.evaluate(()=>{LyricsTranslate.result={trackId:Karaoke.trackId,texts:Karaoke.lines.map(l=>l.text),lines:Karaoke.lines.map(()=> 'Old translation'),target:'en'};S.autoLyrics=true;});
 await p.click('.lyr-pick');await p.waitForTimeout(350);
 ok('manual lyric selection invalidates old translation',await p.evaluate(()=>LyricsTranslate.result===null));
 // Use chosen lyric text in integration fixture even if a legacy enrichment request transforms API schema.
 await p.evaluate(async()=>{Karaoke.lines=[{time:0,end:30,text:'New selected lyric'},{time:30,end:172,text:'Another selected line'}];Karaoke.synced=true;Karaoke.render();S.lyricTranslationTarget='en';$('lt22Target').value='en';$('lt22Consent').checked=true;await LyricsTranslate.run();});
 ok('new lyrics can be translated without losing alignment',await p.evaluate(()=>LyricsTranslate.result?.lines.length===2&&LyricsTranslate.result.texts[0]==='New selected lyric'&&Karaoke.lines[0].time===0));
 for(const mode of ['split','focus','cinema','disc','viz']){await p.selectOption('#sceneMode33',mode);await p.evaluate(()=>{Disc.line=0;LyricsTranslate.repaint();LyricsTranslate.scene()});ok('translation result survives mode change: '+mode,await p.evaluate(()=>LyricsTranslate.value(Karaoke.lines[0],0)==='Translated: New selected lyric'));}
 const keys=['Find lyrics','Hide extra interface','Restore interface','Lyrics & artwork','Player mode','Lyrics only','Cinema','Disc','Visualizer','Reload lyrics','Lyrics translation','Translate lyrics','Translate into','Translation language','Show translation','Searching…','No lyrics found for this name','Lyrics replaced','Lyrics are matched automatically again','A track list is required','The source returned only part of this playlist. Some tracks may be unavailable.'];
 const langs=await p.evaluate(()=>LANGS.map(([lang])=>lang));
 for(const lang of langs){const audit=await p.evaluate(({lang,keys})=>{setLang(lang);App.afterLangChange();return {missing:lang==='en'?[]:keys.filter(k=>!PACKS[lang]?.[k]),label:$('sceneFind34').getAttribute('aria-label'),expected:t('Find lyrics'),modeLabel:$('sceneMode33').getAttribute('aria-label'),modeExpected:t('Player mode')};},{lang,keys});ok('localized new controls: '+lang,!audit.missing.length&&audit.label===audit.expected&&audit.modeLabel===audit.modeExpected);}
 await p.evaluate(()=>{setLang('ru');App.afterLangChange();});
 for(const width of [390,1440]){
  await p.setViewportSize({width,height:width===390?844:1000});
  for(const mode of ['split','focus','cinema','disc','viz']){await p.selectOption('#sceneMode33',mode);await p.waitForTimeout(100);const box=await p.locator('#sceneFind34').boundingBox();ok('chooser within viewport '+width+' '+mode,box&&box.x>=0&&box.x+box.width<=width);await p.screenshot({path:out+'/'+mode+'-'+width+'.png'});}
 }
 ok('no runtime errors',errors.length===0);fs.writeFileSync(out+'/browser-report.json',JSON.stringify({checks,errors},null,2));console.log('REPAIR_V34_PASS',checks.length);
}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1)});