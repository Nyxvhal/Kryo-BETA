/* v69: clip room bug fixes + motion feedback. Download, gate and media engine untouched. */
'use strict';
const Clips69={ready:false,drag:false,
 init(){if(this.ready||typeof Clips==='undefined'||typeof Watch58==='undefined'||!Watch58.ready)return;this.ready=true;
  const v=Clips.video,stage=$('clipStage'),seek=$('clipSeek'),wrap=seek.closest('.cs-seek');this.stage=stage;
  // 1. Seek: the slider no longer jumps back under the finger while timeupdate fires; hover/drag tooltip.
  const tip=document.createElement('span');tip.className='m69-tip';tip.setAttribute('aria-hidden','true');wrap.append(tip);
  const at=x=>{const r=seek.getBoundingClientRect();return Math.min(1,Math.max(0,(x-r.left)/r.width))};
  const showTip=ratio=>{if(!Number.isFinite(v.duration))return;const text=ClipUtils.time(v.duration*ratio);if(tip.textContent!==text)tip.textContent=text;tip.style.left=(ratio*100)+'%';if(!wrap.classList.contains('m69-tipon'))wrap.classList.add('m69-tipon')};
  seek.addEventListener('pointermove',e=>showTip(at(e.clientX)));seek.addEventListener('pointerleave',()=>{if(!this.drag)wrap.classList.remove('m69-tipon')});
  seek.addEventListener('pointerdown',e=>{this.drag=true;seek.classList.add('m69-drag');showTip(at(e.clientX))});
  const end=()=>{if(!this.drag)return;this.drag=false;seek.classList.remove('m69-drag');wrap.classList.remove('m69-tipon');Clips.paintTime()};
  addEventListener('pointerup',end);addEventListener('pointercancel',end);seek.addEventListener('change',end);
  seek.addEventListener('input',()=>{const r=Number(seek.value)/1000;seek.style.setProperty('--cs-position',(r*100)+'%');if(this.drag)showTip(r)});
  const paintTime=Clips.paintTime.bind(Clips);Clips.paintTime=()=>{if(this.drag){const text=ClipUtils.time(v.duration*Number(seek.value)/1000)+' / '+ClipUtils.time(v.duration);if($('clipTime').textContent!==text)$('clipTime').textContent=text;return}paintTime();this.buffer()};
  for(const ev of ['progress','durationchange','loadedmetadata','emptied'])v.addEventListener(ev,()=>this.buffer());
  // 2. Keys keep working after a control was clicked; digits are ignored until duration is known.
  const onKey=Clips.onKey.bind(Clips);Clips.onKey=e=>{const k=(e.key||'').toLowerCase();if(Clips.active&&/^[0-9]$/.test(k)&&!/INPUT|TEXTAREA|SELECT/.test(e.target?.tagName)&&!Number.isFinite(v.duration))return;
   if(Clips.active&&e.target?.tagName==='BUTTON'&&!e.target.closest('#watchMenu58')&&!['enter',' ','tab','escape'].includes(k)&&!e.ctrlKey&&!e.altKey&&!e.metaKey){const proxy={key:e.key,target:document.body,ctrlKey:false,altKey:false,metaKey:false,get defaultPrevented(){return e.defaultPrevented},preventDefault:()=>e.preventDefault(),stopImmediatePropagation:()=>e.stopImmediatePropagation(),stopPropagation:()=>e.stopPropagation()};onKey(proxy);this.feedback(k);return}
   const before=e.defaultPrevented;onKey(e);if(Clips.active&&!before&&e.defaultPrevented)this.feedback(k)};
  // 3. Single click no longer fires play/pause twice around a double-click (fullscreen).
  let timer=0;stage.addEventListener('click',e=>{if(e.target!==v)return;e.stopPropagation();if(matchMedia('(pointer:coarse)').matches){Watch58.show();return}clearTimeout(timer);timer=setTimeout(()=>{Clips.toggle();Watch58.show();this.feedback(' ')},220)},true);
  stage.addEventListener('dblclick',e=>{if(e.target===v)clearTimeout(timer)},true);
  // 4. Controls hide again after mouse use; stay while hovering the bar, keyboard focus or menu.
  const transport=stage.querySelector('.watch-transport58');let over=false;transport.addEventListener('pointerenter',()=>{over=true;Watch58.show()});transport.addEventListener('pointerleave',()=>{over=false;Watch58.show()});
  Watch58.show=function(){clearTimeout(this.hideTimer);this.stage.classList.add('controls-visible58');if(Clips.wantPlay&&!this.menuOpen)this.hideTimer=setTimeout(()=>{const f=document.activeElement;if(over||this.menuOpen||Clips69.drag||(Clips69.kbd&&this.stage.contains(f)))return this.show();this.stage.classList.remove('controls-visible58');if(this.stage.contains(f)&&f!==v)f.blur()},2600)};
  addEventListener('keydown',e=>{if(e.key==='Tab'){this.kbd=true;stage.classList.add('m69-kbd')}},true);addEventListener('pointerdown',()=>{this.kbd=false;stage.classList.remove('m69-kbd')},true);
  // 5. Buffering state dims the frame instead of freezing silently.
  let waitTimer=0;const wait=on=>{clearTimeout(waitTimer);if(on)waitTimer=setTimeout(()=>{if(v.readyState<3||v.seeking)stage.dataset.m69Wait='1'},320);else if(stage.dataset.m69Wait)stage.dataset.m69Wait=''};/* v73: a short seek no longer flashes the buffering dim */v.addEventListener('waiting',()=>wait(true));for(const ev of ['playing','pause','emptied','canplay'])v.addEventListener(ev,()=>wait(false));
  // 6. Closing the room always releases a stuck drag/tooltip/timers.
  const close=Clips.close.bind(Clips);Clips.close=async(...a)=>{clearTimeout(timer);end();wait(false);return close(...a)};
  this.buffer()},
 buffer(){const v=Clips.video,s=$('clipSeek');if(!v||!s)return;let p=0;try{const d=v.duration,t=v.currentTime;if(Number.isFinite(d)&&d>0)for(let i=0;i<v.buffered.length;i++)if(v.buffered.start(i)<=t+.5&&v.buffered.end(i)>=t){p=v.buffered.end(i)/d;break}}catch{}s.style.setProperty('--cs-buffer69',(Math.min(1,p)*100)+'%')},
 feedback(k){if(!this.stage||matchMedia('(prefers-reduced-motion: reduce)').matches)return;const map={' ':[Clips.wantPlay?'play':'pause',''],k:[Clips.wantPlay?'play':'pause',''],arrowleft:['','−5','left'],arrowright:['','+5','right'],j:['','−10','left'],l:['','+10','right'],m:[Clips.muted?'mute':'volume','']};const m=map[k];if(!m)return;this.stage.querySelector('.m69-flash')?.remove();const d=document.createElement('div');d.className='m69-flash'+(m[2]?' '+m[2]:'');if(m[0]&&window.KryoIcons60)d.append(KryoIcons60.create(m[0]));else d.textContent=m[1];this.stage.append(d);setTimeout(()=>d.remove(),650)}
};
const boot69=App.boot.bind(App);App.boot=async function(...a){await boot69(...a);Clips69.init()};
