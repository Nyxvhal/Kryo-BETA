const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
const path=require('path');const root=path.resolve(__dirname,'..');const out=path.join(root,'verification/home-v5');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/local/bin/chromium',args:['--no-sandbox']});let theme='nebula',populated=false,fail=false;const results=[];
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
await page.route('**/api/**',r=>{const p=new URL(r.request().url()).pathname;let data={ok:true,items:[]};
if(fail&&(p==='/api/recommend'||p==='/api/history'))return r.fulfill({status:503,json:{error:'Local QA: unavailable'}});
const tracks=[1,2,3,4].map((n)=>({id:`qa:${n}`,title:['Локальный тест · музыка звучит','Локальный тест · вечерний микс','Локальный тест · новый ритм','Локальный тест · избранное'][n-1],artist:'Тестовая библиотека',source:'local',thumbnail:`/img/avatars/kryonyx-0${n+1}-${['black-violet','black-blue','black-red','emerald'][n-1]}.png`,duration:180}));
if(p==='/api/settings')data={lang:'ru',theme,settingsRev:8,noAnim:true,workspace:{compactPlayer:true}};
else if(p==='/api/health')data={ok:true,sources:[],stats:{}};
else if(p==='/api/state')data={value:null};else if(p==='/api/likes')data={items:[],ids:[]};
else if(p==='/api/recommend')data={rows:populated?[{kind:'tracks',title:'Локальная тестовая подборка',items:tracks}]:[]};else if(p==='/api/discovery')data={rows:[]};
else if(p==='/api/history')data={items:populated?tracks:[]};
else if(p==='/api/youtube/cookies')data={present:false,signed_in:false,browsers:[]};return r.fulfill({json:data});});
await page.route('**/icon.png',r=>r.fulfill({body:fs.readFileSync(root+'/build/icon-1024.png'),contentType:'image/png'}));
async function boot(){await page.goto(process.env.HOME_QA_URL||'http://127.0.0.1:8768');await page.waitForTimeout(1100);assert.deepEqual(await page.evaluate(()=>App.bootErrors||[]),[]);await page.evaluate(x=>{useTheme(x);App.go('home');},theme);await page.waitForTimeout(150);}
async function shot(name,width,height){await page.setViewportSize({width,height});await page.evaluate(()=>$('toast').classList.remove('on'));await page.screenshot({path:out+'/'+name+'.png'});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false,name+' horizontal overflow');results.push({screenshot:name,width,height,overflow});}
await boot();await shot('Kryonyx — новая главная',1440,1000);assert.equal(await page.locator('#rows .home-neutral-empty').count(),1);
await page.locator('.home-new-playlist').click();assert(await page.locator('#mNewPl').evaluate(e=>e.classList.contains('on')));await page.evaluate(()=>closeModals());results.push({newPlaylistDialog:true});
await page.locator('.home-destination').nth(1).click();assert(await page.locator('#clips').evaluate(e=>e.classList.contains('on')));await page.evaluate(()=>Clips.close());results.push({clipShortcut:true});
await page.locator('.home-destination').nth(2).click();assert(await page.locator('#vSearch').isVisible());assert(await page.locator('#top').isVisible());await page.evaluate(()=>App.go('home'));results.push({karaokeEmptyRoutesToSearch:true});
await page.locator('#homeQuery').fill('Локальный тест');await page.locator('.home-search-form button').click();await page.waitForTimeout(200);assert(await page.locator('#vSearch').isVisible());assert.equal(await page.evaluate(()=>K.search.query),'Локальный тест');await page.evaluate(()=>App.go('home'));results.push({searchSubmit:true});
await shot('Kryonyx — главная на телефоне',390,844);
theme='paper';await boot();await shot('Kryonyx — светлая главная',1440,1000);
populated=true;theme='nebula';await boot();assert.equal(await page.locator('.workspace-recent-track').count(),4);assert.equal(await page.locator('.home-feature strong').textContent(),'Локальный тест · музыка звучит');await shot('Kryonyx — тестовая библиотека',1440,1000);await shot('Kryonyx — тестовая библиотека мобильная',390,844);
fail=true;await boot();assert((await page.locator('#rows').innerText()).includes('Local QA: unavailable'));assert((await page.locator('#workspaceRecentTracks').innerText()).includes('недоступна'));results.push({serviceErrorsPreserved:true});
assert.deepEqual(errors,[]);fs.mkdirSync(root+'/verification/home-v5',{recursive:true});fs.writeFileSync(root+'/verification/home-v5/browser.json',JSON.stringify({profile:'Isolated local fixtures, no account/live catalogue',results,errors},null,2));await browser.close();console.log('HOME_QA_PASS',JSON.stringify(results));})().catch(e=>{console.error(e);process.exit(1)});
