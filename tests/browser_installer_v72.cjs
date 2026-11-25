'use strict';
// v72 setup wizard redesign: aurora visual, sliding step pill, switches, reflowed legal text, burst on finish,
// compositor-only idle motion that pauses while minimised, and the 150 % display-scaling fallback size.
// Linux Chromium with a mock pywebview bridge; the native Windows engine and WebView2 are not run here.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict'),path=require('path');
const root=path.resolve(__dirname,'..'),out=root+'/verification/installer-v72';fs.mkdirSync(out,{recursive:true});
const legal={},legal_ru={};for(const n of ['LICENSE','TERMS.md','PRIVACY.md','THIRD_PARTY_NOTICES.md']){legal[n]=fs.readFileSync(root+'/'+n,'utf8');if(fs.existsSync(root+'/docs/ru/'+n))legal_ru[n]=fs.readFileSync(root+'/docs/ru/'+n,'utf8');}
const home='C:\\Users\\QA\\AppData\\Local\\Programs\\Kryonyx Music',GB=1024**3,MB=1024**2;
const base={path:home,legal,legal_ru,version:'1.0.0',space:{need:300*MB,free:118*GB,ok:true},running:false,windows:true,previous:null,tasks:null};
const checks=[],errors=[],ok=(n,v)=>{assert(v,n);checks.push(n);console.log('PASS',n);};
async function open(b,viewport={width:990,height:700},media){
  const p=await b.newPage({viewport});p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  if(media)await p.emulateMedia(media);
  await p.addInitScript(info=>{window.qa={phase:'installing',progress:null,step:'prepare',files:0,total:0};
    window.pywebview={api:{info:async()=>info,browse:async()=>'C:\\Users\\QA\\Kryonyx',space:async()=>({need:300*1024**2,free:118*1024**3,ok:true}),running:async()=>false,
      install:async(...a)=>{window.installArgs=a;return {ok:true};},status:async()=>({phase:qa.phase,progress:qa.progress,step:qa.step,files:qa.files,total:qa.total}),
      open_log:async()=>true,close:async()=>true,finish:async l=>{window.launched=l;return true;}}};},base);
  await p.goto('file://'+root+'/installer/wizard.html');await p.evaluate(()=>dispatchEvent(new Event('pywebviewready')));await p.waitForTimeout(500);return p;}
const pill=p=>p.evaluate(()=>{const ol=document.getElementById('steps'),s=getComputedStyle(ol),li=ol.querySelector('li.s-active'),n=li.querySelector('.n'),l=li.querySelector('.l');
  return {x:parseFloat(s.getPropertyValue('--px')),w:parseFloat(s.getPropertyValue('--pw')),o:s.getPropertyValue('--po').trim(),n:li.offsetLeft+n.offsetLeft,end:li.offsetLeft+(l.offsetWidth?l.offsetLeft+l.offsetWidth:n.offsetLeft+n.offsetWidth)};});
const scaleX=p=>p.evaluate(()=>{const m=getComputedStyle(document.querySelector('.top'),'::after').transform;return m==='none'?1:+new DOMMatrixReadOnly(m).a.toFixed(3);});
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});try{
  let p=await open(b);await p.selectOption('#lang','ru');await p.waitForTimeout(900);
  ok('welcome shows two feature cards with icons and three facts',await p.evaluate(()=>document.querySelectorAll('.feature .fi svg').length===2&&document.querySelectorAll('.chip').length===3));
  ok('aurora visual is built (mark, sweep, orbit dots, 22-bar equaliser, 16 burst sparks)',await p.evaluate(()=>!!document.querySelector('.mark').src&&!!document.querySelector('.sweep .arc')&&document.querySelectorAll('.orbit b').length===2&&document.querySelectorAll('#eq i').length===22&&document.querySelectorAll('#burst i').length===16));
  let pl=await pill(p);ok('step pill covers the current step',pl.o==='1'&&pl.x<=pl.n&&pl.x+pl.w>=pl.end);
  ok('header hairline shows step 1 of 5',await scaleX(p)===0.2);
  ok('language picker and legal tabs use the 12px UI font (v71 shorthand bug fixed)',await p.evaluate(()=>getComputedStyle(document.getElementById('lang')).fontSize==='12px'));
  const c=await p.context().newCDPSession(p);await c.send('Performance.enable');
  const metric=async()=>Object.fromEntries((await c.send('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]));
  await p.waitForTimeout(1200);const m0=await metric();await p.waitForTimeout(1500);const m1=await metric();
  ok('idle motion needs no layout or style work on the main thread',m1.LayoutCount-m0.LayoutCount===0&&m1.RecalcStyleCount-m0.RecalcStyleCount<=2);
  ok('every endless animation moves only transform/opacity',await p.evaluate(()=>document.getAnimations().filter(a=>a.effect.getTiming().iterations===Infinity).every(a=>a.effect.getKeyframes().every(k=>Object.keys(k).every(x=>['offset','easing','composite','computedOffset','transform','opacity'].includes(x))))));
  await p.evaluate(()=>{Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'));});
  ok('animations pause while the window is minimised',await p.evaluate(()=>document.documentElement.classList.contains('paused')&&getComputedStyle(document.querySelector('.mark')).animationPlayState==='paused'));
  await p.evaluate(()=>{Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'));});
  ok('and resume when it is shown again',await p.evaluate(()=>!document.documentElement.classList.contains('paused')&&getComputedStyle(document.querySelector('.mark')).animationPlayState==='running'));
  await p.screenshot({path:out+'/welcome-ru.png'});
  await p.click('#next');await p.waitForTimeout(120);
  ok('step change replays the slide-in',await p.evaluate(()=>{const a=document.querySelector('#main > header').getAnimations()[0];return !!a&&a.currentTime<450;}));
  await p.waitForTimeout(800);
  ok('legal text is reflowed into sentences',(await p.locator('#legalText').textContent()).includes('to deal in the Software'));
  ok('the four legal tabs fit on one row',await p.evaluate(()=>{const t=[...document.querySelectorAll('[data-tab]')];return t.length===4&&new Set(t.map(x=>x.offsetTop)).size===1&&getComputedStyle(t[0]).fontSize==='12px';}));
  const before=pl.x;pl=await pill(p);ok('pill slides to the next step',pl.x>before&&pl.x<=pl.n&&pl.x+pl.w>=pl.end);
  await p.check('#accept');await p.check('#privacy');await p.click('#next');await p.waitForTimeout(900);
  ok('header hairline shows step 3 of 5',await scaleX(p)===0.6);
  ok('options are switches inside cards',await p.evaluate(()=>{const d=document.getElementById('desktop');return d.closest('label').classList.contains('opt')&&Math.round(d.getBoundingClientRect().width)===38;}));
  await p.click('label:has(#autostart)');
  ok('a click anywhere on the option card toggles it and updates the review',await p.isChecked('#autostart')&&(await p.locator('#reviewOptions48').textContent()).includes('включён'));
  await p.screenshot({path:out+'/options-ru.png'});
  await p.click('#next');await p.waitForTimeout(500);
  await p.evaluate(()=>Object.assign(qa,{progress:.64,step:'copy',files:1170,total:1834}));await p.waitForTimeout(900);
  ok('determinate bar fills by transform with the real percentage',await p.evaluate(()=>{const i=document.querySelector('.progress i'),m=new DOMMatrixReadOnly(getComputedStyle(i).transform);return Math.abs(m.a-.64)<.02;})&&(await p.locator('#pct48').textContent())==='64%');
  ok('progress ring appears around the mark',await p.evaluate(()=>getComputedStyle(document.querySelector('.pring')).opacity==='1'));
  await p.screenshot({path:out+'/progress-ru.png'});
  await p.evaluate(()=>{qa.phase='done';});await p.waitForTimeout(700);
  ok('finish: sparks burst once around the check mark',await p.evaluate(()=>{const a=document.querySelector('#burst i').getAnimations();return a.length===1&&a[0].animationName==='burst'&&a[0].effect.getTiming().iterations===1;}));
  await p.waitForTimeout(1600);
  ok('finish: the check mark is drawn',await p.evaluate(()=>getComputedStyle(document.querySelector('.done')).opacity==='1'&&getComputedStyle(document.querySelector('.done path')).strokeDashoffset==='0px'));
  ok('launch is a switch too',await p.evaluate(()=>document.getElementById('launch').closest('label').classList.contains('opt')));
  await p.screenshot({path:out+'/done-ru.png'});
  await p.close();
  // 990×700 is a physical size when Windows display scaling is not applied: 150 % leaves 660×466 CSS pixels.
  p=await open(b,{width:660,height:466});await p.selectOption('#lang','ru');await p.waitForTimeout(700);
  ok('660×466: no overflow, footer and heading visible',await p.evaluate(()=>{const n=document.getElementById('next').getBoundingClientRect(),h=document.getElementById('heading').getBoundingClientRect();return document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight+1&&n.bottom<=innerHeight&&n.right<=innerWidth&&h.top>=0&&h.bottom<innerHeight;}));
  ok('660×466: the mark stays inside the visual panel',await p.evaluate(()=>{const v=document.getElementById('visual').getBoundingClientRect(),m=document.querySelector('.mark').getBoundingClientRect();return m.top>=v.top&&m.bottom<=v.bottom&&m.left>=v.left&&m.right<=v.right;}));
  await p.screenshot({path:out+'/welcome-660x466.png'});
  await p.click('#next');await p.check('#accept');await p.check('#privacy');await p.click('#next');await p.waitForTimeout(700);
  ok('660×466: options scroll inside the page, buttons stay put',await p.evaluate(()=>{const m=document.getElementById('main');m.scrollTop=m.scrollHeight;const r=document.getElementById('autostart').getBoundingClientRect(),n=document.getElementById('next').getBoundingClientRect();return r.bottom<=n.top&&n.bottom<=innerHeight;}));
  await p.screenshot({path:out+'/options-660x466.png'});
  await p.close();
  p=await open(b,{width:390,height:844});await p.waitForTimeout(500);
  ok('narrow: the mark is centred in the top strip',await p.evaluate(()=>{const v=document.getElementById('visual').getBoundingClientRect(),m=document.querySelector('.mark').getBoundingClientRect();return m.top>=v.top&&m.bottom<=v.bottom&&Math.abs((m.left+m.right)/2-(v.left+v.right)/2)<2;})&&await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await p.screenshot({path:out+'/welcome-390.png'});
  await p.close();
  p=await open(b,{width:990,height:700},{reducedMotion:'reduce'});
  ok('reduced motion: nothing animates',await p.evaluate(()=>document.getAnimations().length===0));
  await p.close();
  ok('no runtime errors',errors.length===0);
  console.log('INSTALLER_V72_PASS',checks.length);
}finally{fs.writeFileSync(out+'/report.json',JSON.stringify({checks,errors,scope:'Linux Chromium with a mock pywebview bridge. The native Windows engine, WebView2 and the PyInstaller setup were not run.'},null,2));await b.close();}})().catch(e=>{console.error(e);process.exit(1);});
