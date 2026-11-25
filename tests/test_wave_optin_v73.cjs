'use strict';
// Legacy renderer unit test. v73 does not load viz.js in the application.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const S={vizScene:'off',vizRings:false,vizBolts:false,vizParticles:false,vizVignette:false};
const env=vm.createContext({S,document:{body:{classList:{contains:()=>false}}},console});
vm.runInContext(fs.readFileSync('kryonyx/web/js/viz.js','utf8')+';globalThis.viz=Viz;',env);
const viz=env.viz;viz.bg={width:300,height:200};viz.ctx={fillRect(){},clearRect(){},createRadialGradient(){return{addColorStop(){}}}};
let calls=0;viz.drawWave=()=>calls++;
for(const [value,count] of [[undefined,0],[false,0],[true,1],[false,1],['true',1]]){S.vizWave=value;viz.drawBg('#fff','#fff',.5,1,false,new Uint8Array(3));assert.equal(calls,count)}
console.log('PASS legacy renderer draws wave only for explicit true');
