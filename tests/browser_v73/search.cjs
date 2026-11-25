// Search UI flows: race between queries, hints, tabs, source chips, show more, back, home input.
module.exports=async(p,h,args)=>{const only=(args[0]||'');
 const resp=[];p.on('response',async r=>{const u=r.url();if(!u.includes('/api/search?'))return;try{const j=await r.json();const d=j.data||j;resp.push({q:new URL(u).searchParams.get('q'),page:+new URL(u).searchParams.get('page'),ids:(d.tracks||[]).map(t=>t.id)})}catch{}});
 await h.boot();const out=[];const ok=(name,cond,info)=>{const line=(cond?'PASS ':'FAIL ')+name+(info?' :: '+info:'');out.push(line);console.log(line);};
 const settle=async(ms=20000)=>{const t=Date.now();while(Date.now()-t<ms){await h.wait(150);if(await p.evaluate(()=>K.search&&!K.search.loading&&K.search.extraDone))return true;}return false;};
 await p.evaluate(()=>App.go('search'));await h.wait(300);
 // 1. race: A then B quickly
 await p.fill('#q','metallica');await p.press('#q','Enter');await h.wait(250);await p.fill('#q','adele hello');await p.press('#q','Enter');await settle();
 const raceIds=await p.evaluate(()=>K.search.tracks.map(t=>t.id));const bIds=new Set(resp.filter(r=>r.q==='adele hello').flatMap(r=>r.ids));
 const foreign=raceIds.filter(id=>!bIds.has(id));ok('race: only the last query rows',foreign.length===0&&raceIds.length>0,`rows=${raceIds.length} foreign=${foreign.length}`);
 ok('race: title shows last query',(await p.textContent('#sTitle')).includes('adele hello'));
 // 2. hints popup
 await p.fill('#q','');await p.click('#q');await p.type('#q','imagine drag',{delay:40});await h.wait(1500);
 const pop=await p.evaluate(()=>{const x=$('qPop');return {shown:!x.hidden&&x.getBoundingClientRect().height>0,items:x.querySelectorAll('[role=option],.q-item,button').length}});ok('hints appear while typing',pop.shown&&pop.items>0,JSON.stringify(pop));
 await p.keyboard.press('Escape');await h.wait(200);ok('Esc closes hints',await p.evaluate(()=>$('qPop').hidden||$('qPop').getBoundingClientRect().height===0));
 await p.keyboard.press('Enter');await settle();ok('Enter after Esc searches typed text',(await p.evaluate(()=>K.search.query))==='imagine drag',await p.evaluate(()=>K.search.query));
 ok('hints hidden after search',await p.evaluate(()=>$('qPop').hidden||$('qPop').getBoundingClientRect().height===0));
 // 3. tabs
 for(const tab of ['tracks','authors','albums','playlists','all']){await p.click(`#sTabs [data-stab="${tab}"]`);await h.wait(250);const vis=await p.evaluate(()=>({tr:$('sTracks').style.display!=='none'&&$('sTracks').offsetHeight>0,au:$('sAuthors').style.display!=='none',al:$('sAlbums').style.display!=='none',pl:$('sPlaylists').style.display!=='none',on:document.querySelector('#sTabs .on')?.dataset.stab}));
  const exp={tracks:vis.tr&&!vis.au&&!vis.al&&!vis.pl,authors:!vis.tr&&vis.au,albums:!vis.tr&&vis.al,playlists:!vis.tr&&vis.pl,all:vis.tr}[tab];ok('tab '+tab,exp&&vis.on===tab,JSON.stringify(vis));}
 // 4. source chips
 const chips=await p.$$eval('#searchSources26 button',bs=>bs.map(b=>b.dataset.source26));
 for(const src of chips.filter(Boolean)){await p.click(`#searchSources26 button[data-source26="${src}"]`);await h.wait(300);const st=await p.evaluate(s=>{const rows=Studio.filterTracks(K.search.tracks);return {n:rows.length,bad:rows.filter(t=>t.source!==s).length,shown:document.querySelectorAll('#sTracks [data-id]').length}},src);ok('source chip '+src,st.bad===0&&(st.n===0||st.shown>0),JSON.stringify(st));}
 await p.click('#searchSources26 button[data-source26=""]');await h.wait(300);
 // 5. show more — the fixture always answers 4 rows with has_more:false, so the
 // pager is exercised with a routed multi-page answer (page 1 repeats one row of
 // page 0 to prove de-duplication; pages 0-1 have more, page 2 is the end). Page 0
 // is longer than the window, so the button is used before scrolling loads more.
 const mk=i=>({id:'yt:more73-'+i,title:'Love pager '+i,artist:'Demo '+(i%3),source:'youtube',duration:180,thumbnail:''});
 await p.route(/\/api\/search\?/,async route=>{const u=new URL(route.request().url());if(u.searchParams.get('q')!=='love')return route.continue();const pg=+(u.searchParams.get('page')||0);const tracks=pg===0?[...Array(24)].map((_,i)=>mk(i)):[mk(23),...[...Array(8)].map((_,i)=>mk(100*pg+i))];await route.fulfill({contentType:'application/json',body:JSON.stringify({tracks,has_more:pg<2})});});
 await p.fill('#q','love');await p.press('#q','Enter');await settle();
 // "All" shows a short preview with an "All tracks" button; the pager lives on the Tracks tab.
 await p.click('#sTabs [data-stab="all"]');await h.wait(250);
 const first=await p.evaluate(()=>K.search.tracks.map(t=>t.id));
 const prev=await p.evaluate(()=>({rows:[...document.querySelectorAll('#sTracks [data-id]')].filter(e=>e.offsetHeight>0).length,all:!!$('sAllTracks73')&&!$('sAllTracks73').hidden&&$('sAllTracks73').offsetHeight>0,pager:$('bMore').offsetHeight>0}));
 ok('all tab: 8-row preview + "All tracks" button, no pager',prev.all&&!prev.pager&&prev.rows===8,JSON.stringify(prev));
 if(prev.all){await p.click('#sAllTracks73');await h.wait(300);}else await p.click('#sTabs [data-stab="tracks"]');
 ok('"All tracks" opens the Tracks tab',await p.evaluate(()=>document.querySelector('#sTabs .on')?.dataset.stab==='tracks'));
 // Pages load by scrolling near the end (app.js) or with the button; page 2 is the last one.
 const idle=async()=>{for(let i=0;i<120;i++){await h.wait(150);if(await p.evaluate(()=>!K.search.loading))return;}};
 await idle();let clicks=0;
 for(let i=0;i<4;i++){if(!await p.evaluate(()=>$('sMore').style.display!=='none'&&$('bMore').offsetHeight>0))break;await p.click('#bMore');clicks++;await h.wait(200);await idle();}
 const after=await p.evaluate(()=>K.search.tracks.map(t=>t.id));const moved=first.map((id,i)=>after[i]===id?-1:i).filter(i=>i>=0);
 const pages=[...new Set(resp.filter(r=>r.q==='love').map(r=>r.page))].sort();
 ok('show more appends below, order kept',after.length===40&&!moved.length&&clicks>=1,`first=${first.length} after=${after.length} clicks=${clicks} pages=${pages} moved=${moved.slice(0,8)}`);
 ok('show more drops duplicates across pages',new Set(after).size===after.length&&after.filter(id=>id==='yt:more73-23').length===1);
 ok('pager hides after the last page',await p.evaluate(()=>!K.search.more&&$('sMore').style.display==='none'));
 await p.unroute(/\/api\/search\?/);
 // 6. artist page and back
 const autL=p.locator('#sAuthorsG > *:visible').first();const aut=await autL.count()?autL:null;if(aut){await aut.click({timeout:5000});await h.wait(1200);ok('author opens',await p.evaluate(()=>K.view==='author'));await p.evaluate(()=>App.back());await h.wait(1500);ok('back returns to search',await p.evaluate(()=>K.view==='search'&&K.search.query==='love'),await p.evaluate(()=>K.view+' '+K.search.query));}
 // 7. home input
 await p.evaluate(()=>App.go('home'));await h.wait(600);const hqL=p.locator('#homeQuery:visible');const hq=await hqL.count()?hqL.first():null;if(!hq)console.log('SKIP home input (this home layout has no search box)');if(hq){await hq.fill('queen');await hq.press('Enter');await settle();ok('home input searches',await p.evaluate(()=>K.view==='search'&&K.search.query==='queen'));}
 // 8. top card play
 const playL=p.locator('#studioBest .btn:visible');const play=await playL.count()?playL.first():null;if(play){await play.click();await h.wait(1500);ok('top card play starts the track',await p.evaluate(()=>!!(Player.current||Player.track||K.current)),await p.evaluate(()=>String((Player.current||Player.track||{}).title||'')));}
 // 9. empty query does nothing harmful / garbage query
 await p.evaluate(()=>App.go('search'));await h.wait(400);await p.fill('#q','zzqxjvkwq qqxxzz 0000');await p.press('#q','Enter');await settle();ok('garbage query ends with a state',await p.evaluate(()=>!K.search.loading),await p.evaluate(()=>K.search.tracks.length+' rows; empty='+!!document.querySelector('#sTracks .empty')));
 // 10. Ctrl+K from another view focuses search
 await p.evaluate(()=>App.go('library'));await h.wait(400);await p.keyboard.press('Control+k');await h.wait(500);ok('Ctrl+K opens search',await p.evaluate(()=>document.activeElement&&(document.activeElement.id==='q'||!!document.activeElement.closest('[role=dialog],.palette,.cmdk'))),await p.evaluate(()=>K.view+' '+(document.activeElement&&(document.activeElement.id||document.activeElement.className))));
 await h.shot('search73b');};
