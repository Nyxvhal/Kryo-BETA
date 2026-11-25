'use strict';
// v72 «Polish» layer (css/polish-v72.css) and the layout regressions found in the v72 sweep:
// the page must never shrink to a popover width, queue row buttons sit on the title line,
// "move up" points up, the settings search is one field, buttons ease their press scale,
// cover art leans in on hover. Runs against tests/serve_ai_v72_fixture.py (port 8792).
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs');
const BASE='http://127.0.0.1:8792',out='verification/polish-v72';fs.mkdirSync(out,{recursive:true});
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
const errors=[],checks=[];
const ok=(name,condition)=>{assert(condition,name);checks.push(name);console.log('PASS',name);};
const ready=async p=>{await p.goto(BASE);await p.waitForFunction(()=>typeof App!=='undefined'&&document.body.classList.contains('ui-v72')&&!$('boot45')&&document.querySelector('#rows .card'),null,{timeout:30000});};
try{
 // 1. Desktop
 const p=await b.newPage({viewport:{width:1440,height:900}});p.on('pageerror',e=>errors.push(e.message));
 await ready(p);
 ok('polish sheet is loaded last',await p.evaluate(()=>{const l=[...document.querySelectorAll('link[rel=stylesheet]')].map(x=>x.getAttribute('href'));const at=l.findIndex(h=>/polish-v72\.css/.test(h));/* v73: later polish layers (polish-v73.css) may follow it */return at>=0&&l.slice(at+1).every(h=>/polish-v\d+\.css/.test(h));}));
 ok('page spans the window (no popover class on <body>)',await p.evaluate(()=>!document.body.classList.contains('sound72')&&Math.abs(document.body.getBoundingClientRect().width-innerWidth)<=1));
 ok('buttons ease their press scale',await p.evaluate(()=>{const s=getComputedStyle(document.querySelector('.ib'));return /transform/.test(s.transitionProperty);}));
 const card=await p.$('#rows .card');const bb=await card.boundingBox();
 await p.mouse.move(bb.x+bb.width/2,bb.y+bb.height/3);await p.waitForTimeout(700);
 ok('cover art leans in on hover',await p.evaluate(()=>getComputedStyle(document.querySelector('#rows .card .art img')).scale==='1.035'));
 await p.mouse.move(4,4);
 await p.evaluate(()=>document.querySelector('#rows .card').click());
 await p.waitForFunction(()=>Player.audio&&!Player.audio.paused,null,{timeout:30000});await p.waitForTimeout(600);
 await p.evaluate(()=>$('pQueue').click());await p.waitForTimeout(900);
 const q=await p.evaluate(()=>{const row=[...document.querySelectorAll('#queue .q-row')].find(r=>r.getBoundingClientRect().height>0);if(!row)return null;
  const mid=e=>{const r=e.getBoundingClientRect();return r.top+r.height/2;};const acts=row.querySelector(':scope > .acts'),moves=row.querySelector(':scope > .workspace-queue-moves');
  const up=row.querySelector('.workspace-queue-moves .up .ic');return {mt:getComputedStyle(acts).marginTop,dy:moves?Math.abs(mid(acts)-mid(moves)):0,row:mid(row),acts:mid(acts),up:up?getComputedStyle(up).rotate:'none'};});
 ok('queue has rows',!!q);
 ok('queue row buttons are not pushed down by the dialog .acts margin',q.mt==='0px'&&Math.abs(q.acts-q.row)<=2);
 ok('row actions and move buttons share one line',q.dy<=1);
 ok('"move up" arrow is flipped',q.up==='180deg');
 await p.screenshot({path:out+'/queue.png'});
 await p.keyboard.press('Escape');await p.waitForTimeout(300);
 await p.evaluate(()=>{closeModals();Workspace.openSettings();App.openPane('sound');});await p.waitForTimeout(700);
 const f=await p.evaluate(()=>{const i=$('setFind'),s=getComputedStyle(i),w=i.parentElement.getBoundingClientRect(),r=i.getBoundingClientRect();return {bw:s.borderTopWidth,bg:s.backgroundColor,inside:r.top>=w.top&&r.bottom<=w.bottom+.5};});
 ok('settings search is a single field (no inner box)',f.bw==='0px'&&/rgba\(0, 0, 0, 0\)|transparent/.test(f.bg)&&f.inside);
 await p.evaluate(()=>$('setFind').focus());await p.waitForTimeout(250);
 ok('settings search focus uses a soft halo, not a hard outline',await p.evaluate(()=>{const s=getComputedStyle($('setFind').parentElement);return s.outlineStyle==='none'&&s.boxShadow!=='none';}));
 await p.screenshot({path:out+'/settings.png'});
 // Cover palette: the colour loop must end (it used to run 60×/s for the whole session).
 const pal=await p.evaluate(async()=>{const raf=Karaoke.raf;Karaoke.stop();if(Karaoke._pr)cancelAnimationFrame(Karaoke._pr);Karaoke._pr=null;
  Karaoke.palette=['rgb(10,10,10)','rgb(20,20,20)','rgb(30,30,30)'];Karaoke.target=['rgb(200,100,50)','rgb(13,14,15)','#1f1e1d'];
  let calls=0;const orig=Karaoke.blend;Karaoke.blend=function(...a){calls++;return orig.apply(this,a);};
  Karaoke.pushPalette();await new Promise(r=>setTimeout(r,2400));
  const d=Karaoke.palette.map((c,i)=>{const a=c.match(/\d+/g).map(Number),t=i===2?[31,30,29]:Karaoke.target[i].match(/\d+/g).map(Number);return Math.abs(a[0]-t[0])+Math.abs(a[1]-t[1])+Math.abs(a[2]-t[2]);});
  const after=calls;await new Promise(r=>setTimeout(r,500));Karaoke.blend=orig;return {pr:Karaoke._pr,max:Math.max(...d),calls:after,later:calls-after,raf};});
 ok('cover palette loop ends and reaches the cover colours',pal.pr===null&&pal.max<6&&pal.calls>0&&pal.calls<=91&&pal.later===0);
 await p.close();
 // 2. Phone width: the regression that made <body> 360px wide on desktop must not hide anything on phones either.
 const m=await b.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});m.on('pageerror',e=>errors.push(e.message));
 await ready(m);
 ok('phone: page spans the screen',await m.evaluate(()=>Math.abs(document.body.getBoundingClientRect().width-innerWidth)<=1&&document.documentElement.scrollWidth<=innerWidth+1));
 await m.screenshot({path:out+'/phone.png'});
 await m.close();
 ok('no page errors',errors.length===0);
 console.log('V72_POLISH_PASS',checks.length);
}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1);});
