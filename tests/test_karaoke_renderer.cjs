/* Regression: whole-line highlighting despite legacy word-mode settings. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context=vm.createContext({S:{karaokeTiming:'word',lyricsAutoSync:false},
 Disc:{on:false,reset(){}},Viz:{on:false},Player:{audio:{currentTime:0,playbackRate:1},ctx:null},
 performance:{now:()=>0},Date,console,$:()=>null,api:async()=>({}),setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync('kryonyx/web/js/karaoke.js','utf8')+';globalThis.K=Karaoke;',context);
const K=context.K;let writes=0;
function node(){const classes=new Set();return {classes,style:{setProperty(){writes++}},classList:{toggle(n,on){if(on)classes.add(n);else classes.delete(n)},remove(n){classes.delete(n)},add(n){classes.add(n)}},__sig:null};}
K.lines=[{time:1,end:3,text:'a long'},{time:5,end:7,text:'second line'}];K.synced=true;K.precise=true;K.trackId='fixture';K.lineNodes=[node(),node()];K.lineRows=K.lines.map(()=>({span:node(),units:[],timings:[],state:-1}));K.dotNodes=[];K.center=()=>{};K.chip=()=>{};K.active=-1;K.painted=null;K.lastTime=null;K.offsets={};
const lit=i=>K.lineRows[i].span.classes.has('lit');
K.seek(.9);assert.equal(K.active,-1);assert(!lit(0));
K.seek(1);assert.equal(K.active,0);assert(lit(0));assert(!lit(1));
K.seek(2.5);assert(lit(0));assert.equal(K.active,0);
K.seek(5);assert.equal(K.active,1);assert(lit(1));
const before=writes;K.onTime(5);K.onTime(5);assert.equal(writes,before);
context.Player.audio.playbackRate=1.5;K.seek(1);assert.equal(K.active,0);assert.equal(K.clock(1),1);
K.offsets.fixture=.2;K.seek(.8);assert.equal(K.active,0);assert.equal(K.lines[0].time,1);
K.offsets={};K.seek(6);K.seek(0);assert(!lit(0));assert(!lit(1));
K.precise=false;context.S.lyricsFit=false;K.seek(1);assert.equal(K.active,0,'no arbitrary 180ms delay for LRC lines');
console.log('LINE_RENDERER_PASS 9');
