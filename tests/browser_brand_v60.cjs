'use strict';
const{chromium}=require('playwright'),assert=require('assert/strict');
(async()=>{const b=await chromium.launch({executablePath:'/usr/local/bin/chromium',args:['--no-sandbox']});try{const p=await b.newPage({viewport:{width:1440,height:1000}}),errors=[];p.on('pageerror',e=>errors.push(e.message));await p.goto('http://127.0.0.1:8787');await p.waitForFunction(()=>typeof Brand60!=='undefined'&&Brand60.ready);const r=await p.evaluate(()=>{
 const check=(n,v)=>{if(!v)throw Error(n);return n},checks=[];
 checks.push(check('default core',Avatars.id==='kryonyx-core'));
 checks.push(check('brand logo',$('brandAva').src.includes('kryonyx-core')));
 checks.push(check('bottom empty logo',$('pArt').src.includes('kryonyx-core')));
 checks.push(check('panel empty logo',!$('sessionArt56').hidden&&$('sessionArt56').src.includes('kryonyx-core')));
 const src=$('sessionArt56').src;for(let i=0;i<100;i++)UI56.render();checks.push(check('stable repeated rendering',$('sessionArt56').src===src));
 const old=Avatars.id;Avatars.id='kryonyx-01-sky';Brand60.paint();Brand60.paintPanel();checks.push(check('chosen avatar respected',$('pArt').src.includes('kryonyx-01-sky')&&$('videoBrand60').src.includes('kryonyx-01-sky')));Avatars.id=old;Brand60.paint();Brand60.paintPanel();
 checks.push(check('all symbols use shared set',[...document.querySelectorAll('symbol[id^="i-"]')].every(n=>n.dataset.kryo60)));
 const s=Watch58.icon('settings');checks.push(check('video uses same gear',s.dataset.kryo60==='gear'));
 return checks;
});assert.equal(errors.length,0,JSON.stringify(errors));console.log(JSON.stringify({checks:r,errors},null,2))}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
