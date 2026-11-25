'use strict';const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');let code=fs.readFileSync(__dirname+'/../kryonyx/web/js/redesign-v52.js','utf8').split('// Intercept the removed mode')[0];const ctx={console,LANG:'en',S:{appearance52:{}},DEFAULTS:{layout48:{sidebar:'left',dock:'bottom',transport:'center',density:'comfortable',motion:'smooth',quality:'balanced',sidebarWidth:232,radius:12}},hex2rgb:h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16))};vm.createContext(ctx);vm.runInContext(code+';globalThis.UI=UI52',ctx);const u=ctx.UI;let n=0;function check(name,fn){fn();n++;console.log('PASS',name)}
check('defaults are complete',()=>assert.equal(Object.keys(u.prefs()).length,12));
for(const raw of [null,undefined,[],5,'bad'])check('invalid settings input '+String(raw),()=>assert.equal(u.normalize(raw).palette,'graphite'));
check('unknown properties never survive',()=>assert.equal(u.normalize({password:'secret',css:'body{}'}).password,undefined));
check('invalid palette rejected',()=>assert.equal(u.normalize({palette:'evil'}).palette,'graphite'));
check('invalid colour rejected',()=>assert.equal(u.normalize({accent:'url(javascript:bad)'}).accent,u.defaults.accent));
check('valid colour accepted',()=>assert.equal(u.normalize({accent:'#ff00aa'}).accent,'#ff00aa'));
check('font clamped',()=>assert.equal(u.normalize({fontSize:900}).fontSize,19));
check('card width clamped',()=>assert.equal(u.normalize({cards:-99}).cards,150));
check('NaN rejected',()=>assert.equal(u.normalize({radius:NaN}).radius,12));
check('booleans are strict',()=>assert.equal(u.normalize({showLike:'false'}).showLike,true));
check('false remains false',()=>assert.equal(u.normalize({showLike:false}).showLike,false));
const payload={format:'kryonyx-appearance',version:1,appearance:{...u.defaults},layout:{...ctx.DEFAULTS.layout48}};
check('import round trip',()=>assert.equal(JSON.stringify(u.validateImport(payload).appearance),JSON.stringify(u.defaults)));
for(const d of [{},{format:'kryonyx-layout',version:1},{...payload,version:2},{...payload,appearance:{}},{...payload,appearance:{...u.defaults,accent:'bad'}},{...payload,appearance:[]}])check('invalid import rejected '+n,()=>assert.throws(()=>u.validateImport(d)));
check('import ignores credential fields',()=>assert.equal(u.validateImport({...payload,accounts:['secret'],appearance:{...u.defaults,token:'secret'}}).appearance.token,undefined));
check('layout whitelist',()=>assert.equal(u.validateImport({...payload,layout:{dock:'script',sidebar:'right',sidebarWidth:9999}}).layout.dock,'bottom'));
check('layout width clamped',()=>assert.equal(u.validateImport({...payload,layout:{sidebarWidth:9999}}).layout.sidebarWidth,340));
check('light accent chooses dark ink',()=>assert(u.contrast('#ffffff')>.179));check('dark accent chooses light ink',()=>assert(u.contrast('#000000')<.179));
const ratio=(a,b)=>(Math.max(u.contrast(a),u.contrast(b))+.05)/(Math.min(u.contrast(a),u.contrast(b))+.05);
for(const [name,p]of Object.entries(u.palettes)){if(!p)continue;check(name+' primary text contrast',()=>assert(ratio(p.text,p.bg)>=4.5));check(name+' secondary text contrast',()=>assert(ratio(p.muted,p.panel)>=4.5));check(name+' control edge contrast',()=>assert(ratio(u.edgeColor(p.line,p.panel),p.panel)>=3));check(name+' focus contrast',()=>assert(ratio(u.edgeColor('#8bb9ff',p.panel),p.panel)>=3));}
console.log(n+' checks passed');
