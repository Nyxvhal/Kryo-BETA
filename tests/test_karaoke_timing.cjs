const assert=require('node:assert/strict');
const T=require('../kryonyx/web/js/karaoke-timing.js');
let tests=0;function check(name,fn){fn();tests++;}
check('seek inside word',()=>assert.equal(T.progress(1.5,{start:1,end:2}),.5));
check('pause/resume clock does not accumulate wall-time',()=>{const u={start:1,end:3};assert.equal(T.progress(2,u),T.progress(2,u));assert.equal(T.progress(2.5,u),.75);});
check('speed uses media time, not time multiplied twice',()=>assert.equal(T.progress(3,{start:2,end:4}),.5));
check('forward/backward/loop',()=>{const w=[{start:1,end:2},{start:3,end:4}];assert.equal(T.index(w,3.5),1);assert.equal(T.index(w,1.5),0);assert.equal(T.index(w,0),-1);});
check('song end',()=>assert.equal(T.progress(99,{start:1,end:2}),1));
check('zero duration',()=>assert.equal(T.progress(2,{start:2,end:2}),1));
check('quick/slow/long/short',()=>{assert.equal(T.progress(.005,{start:0,end:.01}),.5);assert.equal(T.progress(5,{start:0,end:10}),.5);});
check('precise syllables',()=>{const w={start:1,end:4,syllables:[{text:'ab',start:1,end:2},{text:'cd',start:3,end:4}]};assert.equal(T.wordProgress(1.5,w,'syllable'),.25);assert.equal(T.wordProgress(2.5,w,'syllable'),.5);assert.equal(T.wordProgress(3.5,w,'syllable'),.75);});
check('no syllables fallback',()=>assert.equal(T.wordProgress(2,{start:1,end:3},'syllable'),.5));
check('CJK no forced spaces',()=>{const units=T.units({text:'你好世界',words:[{text:'你好',start:0,end:1},{text:'世界',start:1,end:2}]});assert.equal(units.map(u=>u.before+u.text+(u.after||'')).join(''),'你好世界');});
check('punctuation retained',()=>{const u=T.units({text:'Hello, world!',words:[{text:'Hello',start:1,end:2},{text:'world',start:2,end:3}]});assert.equal(u.map(v=>v.before+v.text+(v.after||'')).join(''),'Hello, world!');});
console.log(`${tests} timing tests passed`);
