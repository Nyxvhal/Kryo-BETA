'use strict';
// v71 setup wizard: stepper, update detection, free space, running app, real progress, specific errors.
// Linux Chromium with a mock pywebview bridge; the native Windows engine is not run here.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict'),path=require('path');
const root=path.resolve(__dirname,'..'),out=root+'/verification/installer-v71';fs.mkdirSync(out,{recursive:true});
const legal={},legal_ru={};for(const n of ['LICENSE','TERMS.md','PRIVACY.md','THIRD_PARTY_NOTICES.md']){legal[n]=fs.readFileSync(root+'/'+n,'utf8');if(fs.existsSync(root+'/docs/ru/'+n))legal_ru[n]=fs.readFileSync(root+'/docs/ru/'+n,'utf8');}
const home='C:\\Users\\QA\\AppData\\Local\\Programs\\Kryonyx Music',GB=1024**3,MB=1024**2;
const checks=[],errors=[],ok=(n,v)=>{assert(v,n);checks.push(n);console.log('PASS',n);};
async function open(b,info,viewport={width:990,height:700}){
  const p=await b.newPage({viewport});p.on('pageerror',e=>errors.push(e.message));p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await p.addInitScript(info=>{window.qa={phase:'installing',progress:null,step:'prepare',files:0,total:0,error:null,code:null,log:false,opened:0,spaceCalls:0};
    window.pywebview={api:{info:async()=>info,browse:async()=>'C:\\Users\\QA\\Kryonyx',
      space:async p=>{qa.spaceCalls++;return p.startsWith('D:')?{need:300*1024**2,free:120*1024**2,ok:false}:{need:300*1024**2,free:118*1024**3,ok:true};},
      running:async()=>!!info.running,
      install:async(...args)=>{window.installArgs=args;return String(args[0]).startsWith('E:')?{ok:false,error:'space',need:300*1024**2,free:50*1024**2}:{ok:true};},
      status:async()=>({phase:qa.phase,progress:qa.progress,step:qa.step,files:qa.files,total:qa.total,error:qa.error,code:qa.code,log:qa.log}),
      open_log:async()=>{qa.opened++;return true;},close:async()=>true,finish:async l=>{window.launched=l;return true;}}};},info);
  await p.goto('file://'+root+'/installer/wizard.html');await p.evaluate(()=>dispatchEvent(new Event('pywebviewready')));await p.waitForTimeout(450);return p;}
const base={path:home,legal,legal_ru,version:'1.0.0',space:{need:300*MB,free:118*GB,ok:true},running:false,windows:true,previous:null,tasks:null};
const text=(p,s)=>p.locator(s).textContent();
const toSettings=async p=>{await p.click('#next');await p.check('#accept');await p.check('#privacy');await p.click('#next');await p.waitForTimeout(250);};
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});try{
  // ---- fresh install, Russian
  let p=await open(b,base);await p.selectOption('#lang','ru');await p.waitForTimeout(300);
  ok('stepper marks the current step for assistive tech',await p.evaluate(()=>{const li=[...document.querySelectorAll('#steps li')];return li.length===5&&li[0].getAttribute('aria-current')==='step'&&li.filter(x=>x.hasAttribute('aria-current')).length===1;}));
  ok('language and close controls are not covered',await p.evaluate(()=>['lang','close'].every(id=>{const n=document.getElementById(id),r=n.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===n;})));
  ok('fresh install shows version, size and no update notice',await p.evaluate(()=>document.querySelectorAll('.chip').length===3&&!document.getElementById('found48')));
  await p.screenshot({path:out+'/welcome-ru.png'});
  await toSettings(p);
  ok('stepper advances and keeps finished steps marked',await p.evaluate(()=>{const li=[...document.querySelectorAll('#steps li')];return li[2].getAttribute('aria-current')==='step'&&li[0].classList.contains('s-done')&&li[1].classList.contains('s-done');}));
  ok('primary action sits at the right edge, secondary to its left',await p.evaluate(()=>{const n=document.getElementById('next').getBoundingClientRect(),c=document.getElementById('cancel').getBoundingClientRect(),f=document.getElementById('next').parentElement.getBoundingClientRect();return Math.abs(f.right-n.right)<40&&c.right<=n.left;}));
  ok('free space is shown for the target drive',(await text(p,'#space48')).includes('ГБ')&&!(await p.locator('#space48').getAttribute('class')).includes('bad'));
  await p.fill('#path','D:\\Kryonyx');await p.waitForTimeout(700);
  ok('low free space is flagged while typing',(await p.locator('#space48').getAttribute('class')).includes('bad')&&(await text(p,'#space48')).includes('МБ'));
  await p.screenshot({path:out+'/settings-lowspace-ru.png'});
  await p.fill('#path','E:\\Kryonyx');await p.click('#next');await p.waitForTimeout(250);
  ok('install refused for space explains need and free',(await text(p,'#error')).includes('300 МБ')&&(await text(p,'#error')).includes('50 МБ')&&await p.locator('#next').isEnabled());
  ok('space refusal has no engine code or log link',!(await text(p,'#error')).includes('код')&&await p.locator('#openLog48').isHidden());
  await p.fill('#path',home);await p.waitForTimeout(450);
  await p.evaluate(()=>Object.assign(qa,{phase:'installing',total:1834}));await p.click('#next');await p.waitForTimeout(300);
  ok('without engine progress the bar stays indeterminate',await p.locator('#bar48').getAttribute('aria-valuenow')===null&&(await text(p,'#pct48'))==='');
  await p.evaluate(()=>Object.assign(qa,{progress:.42,step:'copy',files:770}));await p.waitForTimeout(700);
  ok('real progress is exposed as a percentage',await p.locator('#bar48').getAttribute('aria-valuenow')==='42'&&(await text(p,'#pct48'))==='42%');
  ok('file counter reads X of Y',(await text(p,'#note48')).includes('770')&&(await text(p,'#note48')).includes('1834'));
  ok('closing and language are locked while the engine works',await p.locator('#close').isDisabled()&&await p.locator('#lang').isDisabled());
  await p.screenshot({path:out+'/progress-42-ru.png'});
  await p.evaluate(()=>Object.assign(qa,{phase:'error',error:'locked',code:5,log:true}));await p.waitForTimeout(700);
  ok('locked files map to a specific message with the engine code',(await text(p,'#error')).includes('занята')&&(await text(p,'#error')).includes('(код 5)'));
  ok('engine log is one click away',await p.locator('#openLog48').isVisible());await p.click('#openLog48');await p.waitForTimeout(100);
  ok('log link calls the bridge',await p.evaluate(()=>qa.opened===1));
  ok('after an error the user can retry from settings',await p.locator('#next').isEnabled()&&await p.locator('#path').isVisible());
  await p.screenshot({path:out+'/error-locked-ru.png'});
  await p.evaluate(()=>Object.assign(qa,{phase:'installing',error:null,code:null,log:false,progress:.97,step:'shortcuts',files:1780}));await p.click('#next');await p.waitForTimeout(600);
  await p.evaluate(()=>{qa.phase='done';});await p.waitForTimeout(800);
  ok('done step names the installed folder',(await text(p,'#where48'))===home);
  await p.uncheck('#launch');await p.click('#next');ok('finish respects the launch checkbox',await p.evaluate(()=>window.launched===false));
  await p.close();
  // ---- update over 0.9.4 with autostart on, app running, English
  p=await open(b,{...base,previous:{path:home,version:'0.9.4'},tasks:{desktop:false,autostart:true},running:true});
  ok('update is recognised on the first screen',(await text(p,'#heading')).includes('Update')&&(await text(p,'#found48')).includes('0.9.4'));
  await p.screenshot({path:out+'/welcome-update-en.png'});
  await toSettings(p);
  ok('previous folder and options are prefilled',await p.inputValue('#path')===home&&!(await p.isChecked('#desktop'))&&await p.isChecked('#autostart'));
  ok('primary button says Update and review shows versions',(await text(p,'#next'))==='Update'&&(await text(p,'#reviewMode48')).includes('0.9.4 → 1.0.0'));
  ok('running Kryonyx is announced before installing',await p.locator('#running48').isVisible());
  await p.fill('#path','C:\\Other\\Kryonyx');await p.waitForTimeout(500);
  ok('another folder turns the update into a separate install',(await text(p,'#next'))==='Install'&&await p.locator('#reviewMode48').isHidden());
  await p.fill('#path',home);await p.waitForTimeout(450);await p.screenshot({path:out+'/settings-update-en.png'});
  await p.setViewportSize({width:850,height:620});await p.waitForTimeout(300);
  ok('minimum window size has no overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth&&document.documentElement.scrollHeight<=innerHeight+1));
  ok('footer buttons stay visible at minimum size',await p.evaluate(()=>{const r=document.getElementById('next').getBoundingClientRect();return r.bottom<=innerHeight&&r.right<=innerWidth;}));
  await p.screenshot({path:out+'/settings-update-850.png'});
  await p.setViewportSize({width:390,height:844});await p.waitForTimeout(300);
  ok('narrow window has no horizontal overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await p.screenshot({path:out+'/settings-update-390.png'});
  await p.setViewportSize({width:990,height:700});await p.focus('#path');await p.keyboard.press('Enter');await p.waitForTimeout(400);
  ok('Enter in the folder field starts the update with the prefilled options',await p.evaluate(()=>Array.isArray(window.installArgs)&&window.installArgs[1]===false&&window.installArgs[2]===true&&window.installArgs[3]===true)&&await p.locator('#bar48').isVisible());
  ok('update progress heading names the update',(await text(p,'#heading')).includes('Updating'));
  await p.close();
  // ---- same version already installed, Russian wording must not claim "this version" for a different build
  p=await open(b,{...base,previous:{path:home,version:'1.0.0'},tasks:{desktop:true,autostart:false}});await p.selectOption('#lang','ru');await p.waitForTimeout(300);
  ok('same version installed: neutral reinstall wording',(await text(p,'#found48')).includes('1.0.0')&&(await text(p,'#found48')).includes('будут заменены'));
  await toSettings(p);ok('same version: button reads Reinstall',(await text(p,'#next'))==='Переустановить');
  await p.close();
  ok('no runtime errors',errors.length===0);
}finally{fs.writeFileSync(out+'/report.json',JSON.stringify({checks,errors,scope:'Linux Chromium with a mock pywebview bridge. The native Windows engine, WebView2 and the PyInstaller setup were not run.'},null,2));await b.close();}})().catch(e=>{console.error(e);process.exit(1);});
