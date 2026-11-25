/* v38 scene chrome is independent from layout and timed lyric state. */
'use strict';
document.body.classList.add('ui-v38');
const UI38={
 near(){
  const nodes=Karaoke.lineNodes;if(!nodes)return;const active=Karaoke.active;
  if(this.nearNodes40!==nodes){this.nearNodes40=nodes;nodes.forEach((n,i)=>n.classList.toggle('near38',Math.abs(i-active)<=1));}
  else {const indices=new Set();for(const index of [this.nearActive40,active])if(Number.isInteger(index))for(let i=Math.max(0,index-1);i<=Math.min(nodes.length-1,index+1);i++)indices.add(i);for(const i of indices)nodes[i].classList.toggle('near38',Math.abs(i-active)<=1);}
  this.nearActive40=active;
 },
 init(){
  $('sceneReturn')?.remove();
  // Deprecated auto-hide preferences no longer run competing idle timers.
  $('idleDelay30')?.closest('label')?.remove();
  document.querySelector('[data-sw="karaokeBare"]')?.closest('.set')?.remove();
  for(const name of ['onTime','render']){const old=Karaoke[name].bind(Karaoke);Karaoke[name]=(...a)=>{const result=old(...a);if(this.lastActive!==Karaoke.active||name==='render'){this.lastActive=Karaoke.active;this.near();}return result;};}
  // Counters are removed, not hidden for later fetching.
  for(const id of ['nStats','workspaceNowStats'])$(id)?.remove();
  document.querySelectorAll('.studio-stats,[data-global-id],[data-local-id]').forEach(n=>n.remove());
  for(const key of ['stats','localStats'])document.querySelector(`[data-studio="${key}"]`)?.closest('label')?.remove();
  // Newly mounted transports must show the paused position immediately.
  const apply=App.applyKaraoke.bind(App);App.applyKaraoke=(...a)=>{const result=apply(...a);Player.paintProgress();Player.paintTime();Player.paintBuffer();return result;};
  App.applyKaraoke();this.near();
 }
};
const boot38=App.boot.bind(App);App.boot=async function(...a){await boot38(...a);UI38.init();};

