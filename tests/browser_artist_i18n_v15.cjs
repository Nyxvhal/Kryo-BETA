/* Local fixture only; no provider accounts. Backend filtering is tested in Python. */
'use strict';
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
const OUT=path.join(__dirname,'../verification/repair-v15');fs.mkdirSync(OUT,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/local/bin/chromium',args:['--no-sandbox']});
 const p=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});const errors=[],checks=[],languages=[];p.on('pageerror',e=>errors.push(e.message));
 const check=(name,value)=>{assert(value,name);checks.push(name);console.log('PASS',name)};
 const counts={};const tr=(id,artist='CG5')=>({id,title:id,artist,source:'youtube',duration:180,thumbnail:'/img/avatars/kryonyx-02-black-violet.png'});
 await p.route('**/api/author?**',async route=>{
  const name=new URL(route.request().url()).searchParams.get('name'),n=counts[name]=(counts[name]||0)+1;
  let tracks=[],partial=false;
  if(name==='CG5'){tracks=n===1?[tr('Keep'),tr('Removed stale row')]:[tr('Keep')];partial=n===1;}
  else if(name==='Same length'){tracks=[tr(n===1?'Old result':'Replacement')];partial=n===1;}
  else if(name==='Slow Artist'){await new Promise(r=>setTimeout(r,650));tracks=[tr('Slow track','Slow Artist')];}
  else if(name==='Fast Artist')tracks=[tr('Fast track','Fast Artist')];
  else if(name==='Radio')tracks=[tr('Play','Radio')];
  return route.fulfill({json:{name,picture:'/img/avatars/kryonyx-02-black-violet.png',tracks,partial,source:'youtube'}});
 });
 await p.goto('http://127.0.0.1:8779');await p.waitForFunction(()=>document.body.classList.contains('ui-v9'));await p.waitForTimeout(400);
 await p.evaluate(()=>{S.lang='ru';setLang('ru');useTheme('studio6');S.noAnim=true;applyTheme();});
 await p.evaluate(()=>App.openAuthor('CG5',null,'youtube'));check('partial profile initially has two rows',await p.locator('#aTracks .tr').count()===2);
 await p.waitForFunction(()=>App.authorTracks.length===1);check('background refresh replaces even a shorter profile',await p.locator('#aTracks .tr').count()===1&&!(await p.locator('#aTracks').textContent()).includes('Removed stale row'));
 await p.screenshot({path:OUT+'/artist-desktop.png'});
 await p.evaluate(()=>App.openAuthor('Same length',null,'youtube'));await p.waitForFunction(()=>App.authorTracks[0]?.title==='Replacement');check('equal-length refresh replaces stale track IDs',await p.locator('#aTracks').textContent().then(t=>t.includes('Replacement')&&!t.includes('Old result')));
 await p.evaluate(()=>App.openAuthor('Empty',null,'youtube'));check('complete empty profile has no endless skeletons',await p.locator('#aTracks .skeleton').count()===0&&await p.locator('#aTracks .empty').count()===1);
 await p.evaluate(()=>{window.slowRequest=App.openAuthor('Slow Artist',null,'youtube');});await p.evaluate(()=>App.openAuthor('Fast Artist',null,'youtube'));await p.waitForTimeout(750);check('late response cannot overwrite another artist',await p.locator('#aName').textContent()==='Fast Artist'&&await p.locator('#aTracks').textContent().then(t=>t.includes('Fast track')&&!t.includes('Slow track')));
 // Navigate away while a new profile loads. Its request may finish, but must not mutate rows.
 await p.evaluate(()=>{window.away=App.openAuthor('Slow Artist',null,'youtube');App.go('home');});await p.waitForTimeout(750);check('late profile response respects navigation',await p.evaluate(()=>K.view==='home'));
 await p.evaluate(()=>App.openAuthor('Radio',null,'youtube'));await p.setViewportSize({width:390,height:844});await p.waitForTimeout(150);check('artist profile fits narrow window',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await p.screenshot({path:OUT+'/artist-mobile.png'});await p.setViewportSize({width:1440,height:1000});
 const audited=JSON.parse(fs.readFileSync(path.join(OUT,'i18n-source.json'),'utf8')).strings;
 const sourceAudit=await p.evaluate(keys=>Object.entries(PACKS).map(([lang,pack])=>{
  const norm=s=>s.replace(/\s+/g,' ').trim().toLowerCase(),known=new Set(Object.keys(pack).map(norm));
  return{lang,missing:keys.filter(k=>!known.has(norm(k))),badPlaceholders:Object.entries(pack).filter(([k,v])=>JSON.stringify((k.match(/\{\w+\}/g)||[]).sort())!==JSON.stringify((v.match(/\{\w+\}/g)||[]).sort())).map(([k])=>k),badUnicode:Object.entries(pack).filter(([k,v])=>/[\ufffd]/.test(k+v)).map(([k])=>k)};
 }),audited);
 check('all audited UI keys exist in all 11 translation packs',sourceAudit.every(r=>!r.missing.length));
 check('translation placeholders and Unicode are intact',sourceAudit.every(r=>!r.badPlaceholders.length&&!r.badUnicode.length));
 for(const lang of ['ru','es','pt','de','fr','it','tr','pl','uk','zh','ja','en']){
  await p.evaluate(async lang=>{S.lang=lang;setLang(lang);Workspace.openSettings();for(const n of document.querySelectorAll('.set-nav-i[data-pane]'))App.openPane(n.dataset.pane);App.openPane('karaoke');await Clips.open(null);},lang);await p.waitForTimeout(220);
  const result=await p.evaluate(()=>{
   translateDom();const wrong=[],walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);const norm=new Map(Object.entries(PACK).map(([k,v])=>[flatten(k).toLowerCase(),v.trim()]));let node,covered=0;
   while(node=walker.nextNode()){
    if(node.parentElement.closest(NO_I18N)||node.parentElement.closest('script,style,svg'))continue;
    const actual=flatten(node.textContent),expected=norm.get(actual.toLowerCase());
    if(expected&&expected.toLowerCase()!==actual.toLowerCase()){const original=ORIG.get(node)?.src?.trim();if(!original||flatten(t(original))!==actual)wrong.push({text:actual,expected,id:node.parentElement.id});}if(ORIG.has(node))covered++;
   }
   return{lang:LANG,covered,wrong,clipStatus:$('clipStatus').textContent,expectedClip:t('Choose a video from the queue or paste a YouTube link'),mini:MiniPlayer.labels().play,expectedMini:t('Play'),note:$('karaokeV2Settings').querySelector('.hint').textContent,expectedNote:t('Whole lines follow the recording timestamps. Word marks remain available for timing edits.'),artist:$('aName').textContent,tracks:[...$('aTracks').querySelectorAll('.t')].map(n=>n.textContent)};
  });
  check('translated DOM and new karaoke note '+lang,!result.wrong.length&&result.clipStatus===result.expectedClip&&result.note===result.expectedNote&&result.mini===result.expectedMini);
  check('artist and track names never translated '+lang,result.artist==='Radio'&&result.tracks.includes('Play'));
  check('Save As success and error notifications translated '+lang,await p.evaluate(async()=>{
   const job={id:'a'.repeat(24),file_ready:true,download_url:'/fixture-export'};
   window.pywebview={api:{save_clip:async()=>({saved:true})}};await Clips.saveOriginal(job);const success=$('toast').textContent===t('Clip saved to the selected file');
   window.pywebview.api.save_clip=async()=>({error:'Invalid clip session'});await Clips.saveOriginal(job);const error=$('toast').textContent===t('Could not save: ')+t('Invalid clip session');delete window.pywebview;return success&&error;
  }));
  languages.push(result);await p.evaluate(()=>{Clips.close();closeModals();});
 }
 // Verify the streaming browser Save As branch, including ordering before fetch.
 check('browser Save As streams original bytes into chosen file',await p.evaluate(async()=>{
  const oldPicker=window.showSaveFilePicker,oldFetch=window.fetch,events=[],bytes=[];
  window.showSaveFilePicker=async()=>{events.push('picker');return{createWritable:async()=>new WritableStream({write(chunk){bytes.push(...chunk)}})}};
  window.fetch=async()=>{events.push('fetch');return new Response(new Uint8Array([0,1,2,255]))};
  try{await Clips.saveOriginal({id:'a'.repeat(24),file_ready:true,download_url:'/fixture-export'});return events.join(',')==='picker,fetch'&&bytes.join(',')==='0,1,2,255';}finally{window.fetch=oldFetch;window.showSaveFilePicker=oldPicker;}
 }));
 await p.evaluate(()=>{S.lang='ru';setLang('ru');Workspace.openSettings();App.openPane('karaoke');$('toast').classList.remove('on');});await p.waitForTimeout(200);await p.screenshot({path:OUT+'/karaoke-settings-ru.png'});
 check('no runtime exceptions',!errors.length);fs.writeFileSync(OUT+'/browser-artist-i18n-report.json',JSON.stringify({checks,languages,sourceAudit,errors,environment:'Linux Chromium; local fixtures. Translation coverage is not a native-speaker review.'},null,2));
 await browser.close();console.log('ARTIST_I18N_V15_PASS',checks.length);
})().catch(e=>{console.error(e);process.exit(1)});
