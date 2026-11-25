'use strict';
const Repair34={
 init(){
  document.body.classList.add('ui-v34','ui-v43','ui-v44');
  const button=el('button','ib',icon('search'));button.id='sceneFind34';button.type='button';button.onclick=()=>Karaoke.openFind();$('sceneTools30').insertBefore(button,$('sceneMore33'));
  const update=()=>this.update();
  for(const name of ['applyKaraoke','afterLangChange','setPlayerControls']){const old=App[name].bind(App);App[name]=(...args)=>{const result=old(...args);update();return result;};}
  const paint=Player.paintTrack.bind(Player);Player.paintTrack=(...a)=>{const v=paint(...a);update();return v;};
  for(const name of ['usePick','clearPick']){const original=Karaoke[name].bind(Karaoke);Karaoke[name]=(...a)=>{if(Player.current?.id!==Karaoke.findFor)return;return original(...a);};}
  this.update();
 },
 update(){
  const button=$('sceneFind34');if(button){button.title=t('Find lyrics');button.setAttribute('aria-label',t('Find lyrics'));button.disabled=!Player.current;}
  $('now')?.classList.remove('chrome-hidden38');
 }
};
const boot34=App.boot.bind(App);App.boot=async function(...a){await boot34(...a);Repair34.init();};
