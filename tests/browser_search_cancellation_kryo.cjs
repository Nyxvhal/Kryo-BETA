'use strict';
const {chromium}=require('playwright'), assert=require('assert/strict'), fs=require('fs');
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:800}}), errors=[],checks=[], counts={};
 const check=(name,val)=>{assert(val,name);checks.push(name);console.log('PASS',name)};
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{const f=window.fetch;window.__aborts=[];window.fetch=async(...args)=>{try{return await f(...args)}catch(e){if(e.name==='AbortError')window.__aborts.push(String(args[0]));throw e}}});
 await page.route('**/api/search?*',async route=>{
   const u=new URL(route.request().url()),q=u.searchParams.get('q'),pg=+u.searchParams.get('page'),source=u.searchParams.get('sources');
   const sk=q+':'+pg+':'+source;counts[sk]=(counts[sk]||0)+1;
   counts[q+':'+pg]=(counts[q+':'+pg]||0)+1;
   const n=counts[q+':'+pg];
   if(q==='old'||q==='landing'||q==='waitpage'&&pg===1)await wait(1700);
   else await wait(60);
   if((q==='retry'&&pg===1&&n===1)||(q==='partial'&&pg===1&&source==='youtube'&&counts[sk]===1)){try{await route.fulfill({status:503,body:'temporary'});}catch{}return}
   const item={id:'local:'+q+pg+source,title:q+' page '+pg,artist:'Test Artist',source:'youtube',duration:180};
   try{await route.fulfill({json:{tracks:[item],authors:[],has_more:pg===0,degraded:q==='degradedpage'&&pg===1&&n===1}})}catch{}
 });
 await page.route('**/api/search/extra?*',async route=>{
   const q=new URL(route.request().url()).searchParams.get('q');
   if(q==='old'||q==='landing'||q==='waitpage')await wait(1900); else await wait(40);
   try{await route.fulfill({json:{authors:[],albums:[],playlists:[]}})}catch{}
 });
 await page.route('**/api/cache-test?*',async route=>{
   const u=new URL(route.request().url()),key=u.searchParams.get('key');counts[key]=(counts[key]||0)+1;const n=counts[key];
   await wait(key==='ordering'&&n===1?350:key==='shared'&&n===1?500:key==='timeout'?500:80);
   try{await route.fulfill({json:{sequence:n,degraded:key==='degraded'&&n===1}})}catch{}
 });
 try{
   await page.goto('http://127.0.0.1:8779');await page.waitForFunction(()=>document.body.classList.contains('ui-v24')&&typeof App!=='undefined');
   await page.evaluate(()=>{S.sources=['youtube'];S.noAnim=true;App.search('old')});await wait(150);
   await page.fill('#q','new');
   await page.waitForFunction(()=>window.__aborts.filter(x=>x.includes('q=old')).length>=2);
   check('editing input aborts both old track and extra requests',await page.evaluate(()=>!K.search.loading&&!$('loadBar').classList.contains('on')&&K.search.cancelled&&Studio.statuses.youtube==='cancelled'));
   await page.evaluate(()=>App.search('new'));await page.waitForFunction(()=>K.search.query==='new'&&!K.search.loading&&K.search.extraDone);
   await wait(100);check('new query renders without stale results',await page.evaluate(()=>K.search.tracks.length===1&&K.search.tracks[0].title==='new page 0'));
   await page.evaluate(()=>{dropCache();App.search('waitpage')});await page.waitForFunction(()=>K.search.query==='waitpage'&&!K.search.loading&&K.search.more);
   await page.evaluate(()=>{App.more()});await wait(120);await page.fill('#q','cancel');
   await page.waitForFunction(()=>window.__aborts.some(x=>x.includes('q=waitpage')&&x.includes('page=1'))&&window.__aborts.some(x=>x.includes('/extra?')&&x.includes('q=waitpage')));
   check('pagination and overlapping extra request both abort',await page.evaluate(()=>!App.searchController&&!App.moreController&&!K.search.loading));
   await page.evaluate(()=>{dropCache();App.search('retry')});await page.waitForFunction(()=>K.search.query==='retry'&&!K.search.loading&&K.search.more);
   await page.evaluate(()=>App.more());await page.waitForFunction(()=>!K.search.loading);check('failed page remains retryable',await page.evaluate(()=>K.search.page===0&&K.search.more));
   await page.evaluate(()=>App.more());await page.waitForFunction(()=>!K.search.loading&&K.search.page===1);check('retry adds page once without duplicates',await page.evaluate(()=>K.search.tracks.length===2&&new Set(K.search.tracks.map(x=>x.id)).size===2));
   await page.evaluate(()=>{dropCache();App.search('degradedpage')});await page.waitForFunction(()=>K.search.query==='degradedpage'&&!K.search.loading&&K.search.more);
   await page.evaluate(()=>App.more());check('degraded page retains useful rows and remains retryable',await page.evaluate(()=>K.search.page===0&&K.search.more&&K.search.tracks.length===2));
   await page.evaluate(()=>App.more());check('recovered degraded page does not duplicate rows',await page.evaluate(()=>K.search.page===1&&K.search.tracks.length===2));
   await page.evaluate(()=>{S.sources=['youtube','soundcloud'];dropCache();App.search('partial')});await page.waitForFunction(()=>K.search.query==='partial'&&!K.search.loading&&K.search.more);
   await page.evaluate(()=>App.more());check('partial source failure preserves loaded rows and retry',await page.evaluate(()=>K.search.page===0&&K.search.more&&K.search.tracks.length===3));
   await page.evaluate(()=>App.more());check('retry preserves all source pages without duplicates',await page.evaluate(()=>K.search.page===1&&K.search.tracks.length===4&&new Set(K.search.tracks.map(x=>x.id)).size===4));
   await page.evaluate(()=>{S.sources=['youtube'];dropCache();App.search('landing')});await wait(120);await page.evaluate(()=>Studio.showSearchLanding());
   await page.waitForFunction(()=>window.__aborts.filter(x=>x.includes('q=landing')).length>=2);
   check('returning to search landing aborts active requests',await page.evaluate(()=>!K.search.query&&!App.searchController&&!App.moreController));
   let result=await page.evaluate(async()=>{dropCache();const c=new AbortController(),url='/api/cache-test?key=shared';const a=cachedApi(url,10000,{signal:c.signal}).catch(e=>e.name),b=cachedApi(url,10000);setTimeout(()=>c.abort(),40);return [await a,await b]});
   check('caller cancellation does not cancel independent request',result[0]==='AbortError'&&result[1].sequence===2);
   result=await page.evaluate(async()=>{dropCache();const c=new AbortController(),url='/api/cache-test?key=ordering';const old=cachedApi(url,10000,{signal:c.signal});await new Promise(r=>setTimeout(r,20));const newer=cachedApi(url,10000);await Promise.all([old,newer]);return cachedApi(url,10000)});
   check('older slow response cannot overwrite newer cache value',result.sequence===2);
   result=await page.evaluate(async()=>{dropCache();const url='/api/cache-test?key=degraded',opts={cacheIf:d=>!d.degraded};return [await cachedApi(url,10000,opts),await cachedApi(url,10000,opts),await cachedApi(url,10000,opts)]});
   check('incomplete response is not cached; complete response is cached',result[0].degraded&&result[1].sequence===2&&result[2].sequence===2);
   result=await page.evaluate(async()=>{dropCache();const c=new AbortController(),p=cachedApi('/api/cache-test?key=timeout',10000,{signal:c.signal});setTimeout(()=>dropCache('/api/cache-test'),20);await p;return memo.has('/api/cache-test?key=timeout')});
   check('invalidation prevents late cache repopulation',result===false);
   result=await page.evaluate(async()=>{const c=new AbortController();let a=api('/api/cache-test?key=timeout',{signal:c.signal,timeout:2000}).catch(e=>e.name);setTimeout(()=>c.abort(),20);let b=api('/api/cache-test?key=timeout',{timeout:20}).catch(e=>e.message);return [await a,await b]});
   check('external cancellation differs from request timeout',result[0]==='AbortError'&&result[1]!=='AbortError');
   check('no uncaught browser errors',errors.length===0);
   fs.writeFileSync('verification/search-cancellation/report.json',JSON.stringify({checks,errors,counts},null,2));console.log('SEARCH_CANCELLATION_PASS',checks.length);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
