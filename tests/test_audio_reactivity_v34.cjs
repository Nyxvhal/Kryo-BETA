'use strict';const assert=require('assert/strict'),Beat=require('../kryonyx/web/js/audio-reactivity-v34.js');
const d=new Beat(),bins=new Uint8Array(1024);let now=0,hits=0,detected=[];
for(let frame=0;frame<360;frame++){
 now=frame*1000/60;bins.fill(0);const kick=frame%30<3;
 for(let i=2;i<=7;i++)bins[i]=kick?225:15;
 const s=d.process(bins,48000,now,1,true);if(s.hit){hits++;detected.push(frame);}
 assert(s.energy>=0&&s.energy<=1);assert(s.beat>=0&&s.beat<=1);
}
assert.equal(hits,11);assert(detected.every(f=>f%30===0));
d.reset();bins.fill(150);for(let i=0;i<120;i++)assert.equal(d.process(bins,48000,i*16,1,true).hit,false,'steady tone must not generate fictitious beats');
assert.equal(d.process(bins,48000,3000,1,false).beat,0,'pause resets');
d.reset();bins.fill(0);for(let i=0;i<180;i++)assert.equal(d.process(bins,48000,i*16,1,true).hit,false,'silence');
// Cymbal/snare onset even without bass growth.
d.reset();bins.fill(0);d.process(bins,48000,0);for(let i=20;i<120;i++)bins[i]=210;assert(d.process(bins,48000,200).hit);
console.log('AUDIO_REACTIVITY_V34_PASS: 11 kicks aligned, sustained tone, silence, pause, percussion');
