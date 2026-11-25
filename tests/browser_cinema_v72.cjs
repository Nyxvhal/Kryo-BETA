'use strict';
// v72 «Cinema+» playback menu: tabs, speed/pitch/A-V controls, size slider that previews a frame while dragging and
// applies on release (viewing mode), fit and picture options, keys page, mobile layout.
// Runs against tests/serve_ai_v72_fixture.py (port 8792) with its synthetic local clip. No Windows/WebView2 verification.
const {chromium}=require('playwright'),assert=require('assert/strict'),fs=require('fs');
const BASE='http://127.0.0.1:8792',out='verification/cinema-v72';fs.mkdirSync(out,{recursive:true});
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
const p=await b.newPage({viewport:{width:1440,height:900}}),errors=[],checks=[];
p.on('pageerror',e=>errors.push(e.message));
const ok=(name,condition)=>{assert(condition,name);checks.push(name);console.log('PASS',name);};
const shot=async name=>{await p.waitForTimeout(250);await p.screenshot({path:out+'/'+name+'.png'});};
const menu=async open=>{const now=await p.evaluate(()=>!$('watchMenu58').hidden);if(now!==open){await p.mouse.move(700,420);await p.click('#watchSettings58');}await p.waitForFunction(o=>$('watchMenu58').hidden===!o,open);};
try{
 await p.request.put(BASE+'/api/settings',{data:{clipAutoNext:false,clipLoop:true,clipSpeed:1,clipPitch72:true,clipFocusSize71:90,clipFit72:'contain',clipPicture72:{brightness:100,contrast:100,saturation:100},clipAmbient66:{enabled:true,blur:24,dim:40,size:70}}});
 await p.request.get(BASE+'/fixture/video57?cookies=ready');
 await p.addInitScript(()=>{window.pywebview={api:{close(){},minimize(){},maximize(){},restore(){},info:async()=>({maximized:true,min_width:400,min_height:560,frameless:true}),set_on_top:async()=>true,toggle_fullscreen:async()=>true}};addEventListener('DOMContentLoaded',()=>setTimeout(()=>dispatchEvent(new Event('pywebviewready')),0));});
 await p.goto(BASE);
 await p.waitForFunction(()=>typeof Cinema72!=='undefined'&&Cinema72.ready&&!$('boot45'),null,{timeout:30000});
 await p.evaluate(()=>{setLang('ru');return Clips.open(null);});
 await p.waitForSelector('.video-card57');await p.locator('.video-card57').first().click();
 await p.waitForFunction(()=>Clips.video.currentTime>.4&&!Clips.video.paused,null,{timeout:60000});
 await menu(true);
 const tabs=await p.evaluate(()=>[...document.querySelectorAll('#watchMenu58 .cx-tab72')].map(t=>({id:t.dataset.tab72,role:t.getAttribute('role'),label:t.textContent.trim(),cut:t.lastChild.scrollWidth>t.lastChild.clientWidth+1})));
 ok('six tabs in the menu',tabs.length===6&&tabs.every(t=>t.role==='tab'));
 ok('tab labels are translated and not cut off',tabs.map(t=>t.label).join()==='Клип,Экран,Цвет,Фон,ИИ,Клавиши'&&tabs.every(t=>!t.cut));
 ok('tab labels use the compact font',await p.evaluate(()=>getComputedStyle(document.querySelector('.cx-tab72')).fontSize==='11px'));
 ok('pitch follows speed by default (record-style)',await p.evaluate(()=>$('cxPitch72').checked&&Clips.video.preservesPitch===false&&Clips.audio.preservesPitch===false));
 await shot('video-tab');
 await p.click('#cxPitch72');
 ok('pitch switch keeps the natural voice when off',await p.evaluate(()=>Clips.video.preservesPitch===true&&Clips.audio.preservesPitch===true&&S.clipPitch72===false&&/естественно/.test($('cxPage72-video').textContent)));
 await p.click('#cxPitch72');
 for(const id of ['screen','color','ambient','ai','keys','video']){
  await p.click('#cxTab72-'+id);
  ok('tab «'+id+'» shows only its page',await p.evaluate(id=>[...document.querySelectorAll('#watchMenu58 .cx-page72')].every(pg=>pg.hidden===(pg.dataset.page72!==id))&&$('cxTab72-'+id).getAttribute('aria-selected')==='true',id));
 }
 await p.click('#cxTab72-keys');
 ok('keys page lists the shortcuts',await p.evaluate(()=>document.querySelectorAll('#cxPage72-keys dt').length===10&&/Режим просмотра/.test($('cxPage72-keys').textContent)));
 await shot('keys-tab');
 await menu(false);
 // Speed keys with the badge
 await p.keyboard.press(']');
 ok('] speeds up video and sound together',await p.evaluate(()=>Number($('clipSpeed').value)>1&&Math.abs(Clips.audio.playbackRate-Number($('clipSpeed').value))<.001));
 ok('speed badge appears on the video',await p.evaluate(()=>$('cxBadge72')&&$('cxBadge72').classList.contains('on')&&/×/.test($('cxBadge72').textContent)));
 await p.keyboard.press('[');
 ok('[ returns to normal speed',await p.evaluate(()=>Number($('clipSpeed').value)===1));
 // Size slider: preview while dragging, apply on release (viewing mode)
 await p.keyboard.press('t');await p.waitForFunction(()=>Cinema71.focus,null,{timeout:5000});await p.waitForTimeout(700);
 await menu(true);await p.click('#cxTab72-screen');await p.waitForTimeout(250);
 const before=await p.evaluate(()=>{const m=$('watchMenu58').getBoundingClientRect(),v=$('clipVideo').getBoundingClientRect();return {mx:Math.round(m.right),my:Math.round(m.bottom),vw:Math.round(v.width)};});
 const box=await p.locator('#cxFocusSize71').boundingBox(),y=box.y+box.height/2;
 await p.mouse.move(box.x+box.width*.8,y);await p.mouse.down();await p.mouse.move(box.x+box.width*.25,y,{steps:8});await p.waitForTimeout(200);
 const mid=await p.evaluate(()=>{const v=$('clipVideo').getBoundingClientRect(),f=$('cx72SizePreview').getBoundingClientRect(),m=$('watchMenu58').getBoundingClientRect();return {cls:$('clips').classList.contains('cx-previewing72'),fw:Math.round(f.width),vw:Math.round(v.width),label:$('cx72SizePreview').textContent,saved:S.clipFocusSize71,mx:Math.round(m.right),my:Math.round(m.bottom)};});
 ok('dragging shows a preview frame',mid.cls&&mid.fw>0&&/%/.test(mid.label));
 ok('video keeps its size while dragging',Math.abs(mid.vw-before.vw)<=2&&mid.saved===90);
 ok('menu stays in place while dragging',Math.abs(mid.mx-before.mx)<=1&&Math.abs(mid.my-before.my)<=1);
 await shot('size-preview');
 await p.mouse.up();await p.waitForTimeout(700);
 const after=await p.evaluate(()=>({cls:$('clips').classList.contains('cx-previewing72'),vw:Math.round($('clipVideo').getBoundingClientRect().width),saved:S.clipFocusSize71}));
 ok('size is applied on release',!after.cls&&after.saved<90&&after.vw<before.vw-20);
 await p.click('.cx-size-chips72 [data-size72="90"]');await p.waitForTimeout(600);
 ok('size chips set an exact size',await p.evaluate(()=>S.clipFocusSize71===90&&document.querySelector('.cx-size-chips72 [data-size72="90"]').getAttribute('aria-pressed')==='true'));
 await p.click('.cx-fit72 [data-fit72="cover"]');
 ok('fill-screen fit is applied',await p.evaluate(()=>$('clips').dataset.cxFit72==='cover'&&getComputedStyle($('clipVideo')).objectFit==='cover'));
 await p.click('.cx-fit72 [data-fit72="contain"]');
 await p.keyboard.press('Escape');await p.waitForTimeout(300);
 if(await p.evaluate(()=>Cinema71.focus)){await p.keyboard.press('t');await p.waitForTimeout(500);}
 // Colour page
 await menu(true);await p.click('#cxTab72-color');
 await p.locator('#cxPic72-brightness').fill('130');await p.locator('#cxPic72-brightness').dispatchEvent('change');
 ok('brightness changes the picture filter',await p.evaluate(()=>$('clips').classList.contains('cx-picture72')&&/brightness\(1\.3\)/.test(getComputedStyle($('clipVideo')).filter)));
 await shot('color-tab');
 await p.click('#cxPicReset72');
 ok('reset returns the original picture',await p.evaluate(()=>!$('clips').classList.contains('cx-picture72')&&S.clipPicture72.brightness===100&&$('cxPicReset72').disabled));
 // Mobile
 await menu(false);await p.setViewportSize({width:390,height:844});await p.waitForTimeout(400);
 await p.evaluate(()=>$('clipStage').scrollIntoView({block:'start'}));await menu(true);await p.waitForTimeout(300);
 ok('mobile menu fits the screen',await p.evaluate(()=>{const r=$('watchMenu58').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.width>300;}));
 ok('mobile tabs all visible',await p.evaluate(()=>[...document.querySelectorAll('.cx-tab72')].every(t=>{const r=t.getBoundingClientRect();return r.width>40&&r.right<=innerWidth;})));
 await shot('mobile-menu');
 ok('no runtime errors',errors.length===0);
 fs.writeFileSync(out+'/checks.json',JSON.stringify({checks,errors,scope:'Local synthetic 4 s 192x108 clip in Chromium; no Windows/WebView2 or live YouTube verification.'},null,2));
 console.log('V72_CINEMA_PASS',checks.length);
}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1);});
