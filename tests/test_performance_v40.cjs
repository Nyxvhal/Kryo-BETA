'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');let callbacks=[],time=0,quantize=false;
const box={scrollHeight:1600,clientHeight:600,_top:0,get scrollTop(){return this._top},set scrollTop(v){this._top=Math.max(0,Math.min(1000,quantize?Math.round(v):v))}};
const env={S:{noAnim:false},document:{hidden:false},$:id=>id==='lyrics'?box:id==='now'?{classList:{contains:()=>true}}:null,matchMedia:()=>({matches:false}),requestAnimationFrame:f=>(callbacks.push(f),callbacks.length),cancelAnimationFrame(){},console};vm.createContext(env);vm.runInContext(fs.readFileSync('kryonyx/web/js/karaoke.js','utf8')+';globalThis.K=Karaoke;',env);const K=env.K;let checks=0;function ok(n,v){assert(v,n);checks++;console.log('PASS',n)}
function run(step,limit=500){let count=0;while(callbacks.length&&count<limit){const f=callbacks.shift();time+=step;f(time);count++;}return count}
K.follow=true;K.scrollTo=3000;K.glide();run(1000/60);ok('unreachable scroll target clamps to real bottom',box.scrollTop===1000);ok('bottom scroll releases RAF and target',!K.glideRaf&&K.scrollTo===null&&callbacks.length===0);
function position(step){box.scrollTop=0;K.scrollTo=600;K.glide();let count=Math.round(300/step);while(count--){time+=step;callbacks.shift()(time)}const pos=box.scrollTop;callbacks=[];K.glideRaf=null;return pos}
const a=position(1000/60),b=position(1000/144);ok('scroll easing independent of 60/144Hz refresh',Math.abs(a-b)<4);
quantize=true;box.scrollTop=999;K.follow=true;K.scrollTo=1000;K.glide();run(16);ok('integer scroll rounding cannot strand a one-pixel RAF loop',box.scrollTop===1000&&!K.glideRaf);quantize=false;
K.scrollTo=600;K.glide();env.document.hidden=true;run(16);ok('hidden stage stops scroll RAF',!K.glideRaf&&callbacks.length===0);env.document.hidden=false;
K.scrollTo=600;K.follow=false;K.glide();run(16);ok('manual follow-off cancels animation',!K.glideRaf);
K.follow=true;box.scrollTop=0;K.scrollTo=700;env.S.noAnim=true;K.glide();run(16);ok('reduced animation jumps once then releases RAF',box.scrollTop===700&&!K.glideRaf);
let writes=0,attrs={},node={textContent:'same',style:{width:'25%'},getAttribute:k=>attrs[k],setAttribute:(k,v)=>{writes++;attrs[k]=v}};let text=node.textContent;Object.defineProperty(node,'textContent',{get:()=>text,set:v=>{text=v;writes++}});let width='25%';Object.defineProperty(node.style,'width',{get:()=>width,set:v=>{width=v;writes++}});
const core=fs.readFileSync('kryonyx/web/js/core.js','utf8');vm.runInContext(core.slice(core.indexOf('function paintText40'),core.indexOf('// Modals pause decoration')),env);
for(let i=0;i<1000;i++){env.paintText40(node,'same');env.paintStyle40(node,'width','25%');env.paintAttr40(node,'aria-valuenow','25')};ok('1000 equal paints perform only the first missing attribute write',writes===1);
const fresh={textContent:'',style:{},getAttribute:()=>null,setAttribute(){}};env.paintText40(fresh,'same');env.paintStyle40(fresh,'width','25%');ok('remounted controls still receive current values',fresh.textContent==='same'&&fresh.style.width==='25%');console.log('PERFORMANCE40_UNIT',checks)
