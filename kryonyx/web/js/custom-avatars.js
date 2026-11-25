/* Custom avatars stay in the application data folder; only the crop is uploaded. */
'use strict';
const CustomAvatars = {
 image:null, objectUrl:null, busy:false, pendingDelete:'', returnFocus:null,
 init() {
  const dialog=document.createElement('dialog');dialog.id='customAvatarDialog';dialog.className='ca13-dialog';dialog.setAttribute('aria-labelledby','ca13Title');
  dialog.innerHTML=`<header class="ca13-head"><div><p class="ca13-eyebrow" data-ca-key="MAKE IT YOURS"></p><h2 id="ca13Title" data-ca-key="Your own avatar"></h2><p class="ca13-muted" data-ca-key="Crop it. Preview it. Make it yours."></p></div><button type="button" class="btn g ca13-close" id="ca13Close" aria-label="Close">×</button></header>
  <div class="ca13-body"><section class="ca13-editor"><div class="ca13-preview"><canvas id="ca13Canvas" width="512" height="512" role="img" aria-label="Avatar crop preview"></canvas><span id="ca13Empty" data-ca-key="Your picture goes here"></span></div><div class="ca13-controls"><label class="btn ca13-file"><span data-ca-key="Choose image"></span><input id="ca13File" type="file" accept="image/png,image/jpeg,image/webp"></label><p class="ca13-muted" data-ca-key="PNG, JPEG or WebP · up to 8 MB · still images only"></p><label class="ca13-field"><span data-ca-key="Avatar name"></span><input id="ca13Name" type="text" maxlength="80" autocomplete="off" data-no-i18n></label>
  <label class="ca13-field"><span data-ca-key="Zoom"></span><input id="ca13Zoom" type="range" min="1" max="3" step="0.01" value="1"></label><label class="ca13-field"><span data-ca-key="Horizontal position"></span><input id="ca13X" type="range" min="-100" max="100" value="0"></label><label class="ca13-field"><span data-ca-key="Vertical position"></span><input id="ca13Y" type="range" min="-100" max="100" value="0"></label><button type="button" class="btn g" id="ca13Reset" data-ca-key="Reset crop"></button></div></section>
  <p class="ca13-privacy" data-ca-key="Saved on this device, not published online. Your picture is also used for the app and shortcut icons."></p><p id="ca13Status" role="alert" aria-live="polite"></p><section class="ca13-saved"><div class="ca13-section-head"><h3 data-ca-key="Custom avatars"></h3><span id="ca13Count"></span></div><div id="ca13List" class="ca13-list"></div></section></div>
  <footer class="ca13-footer"><button type="button" class="btn g" id="ca13Cancel" data-ca-key="Cancel"></button><button type="button" class="btn" id="ca13Save" data-ca-key="Save and apply avatar" disabled></button></footer>`;
  document.body.append(dialog);this.dialog=dialog;
  $('ca13Close').onclick=$('ca13Cancel').onclick=()=>this.close();
  dialog.addEventListener('cancel',e=>{e.preventDefault();this.close();});
  $('ca13File').onchange=()=>this.read($('ca13File').files[0]);
  for(const id of ['ca13Zoom','ca13X','ca13Y'])$(id).oninput=()=>this.draw();
  $('ca13Name').oninput=()=>this.enable();$('ca13Save').onclick=()=>this.save();$('ca13Reset').onclick=()=>this.reset();
  const upload=()=>{const b=document.createElement('button');b.type='button';b.className='btn ca13-upload';b.dataset.caKey='Upload your avatar';b.onclick=()=>this.open();return b;};
  document.querySelector('#vShop8 .ui8-pack').prepend(upload());
  document.querySelector('.pane[data-pane="avatar"]').prepend(upload());
  const option=new Option('', 'custom');option.dataset.caKey='Custom avatars';$('ui8Collection').add(option);
  this.refreshLabels();this.enable();
 },
 refreshLabels() {
  document.querySelectorAll('[data-ca-key]').forEach(n=>n.textContent=t(n.dataset.caKey));
  $('ca13Close').setAttribute('aria-label',t('Close'));$('ca13Canvas').setAttribute('aria-label',t('Avatar crop preview'));
  if(this.statusKey)$('ca13Status').textContent=t(this.statusKey);
  this.renderSaved();
 },
 status(key='') {this.statusKey=key;$('ca13Status').textContent=key?t(key):'';},
 async open() {
  this.returnFocus=document.activeElement;this.status();this.pendingDelete='';
  this.dialog.showModal();this.refreshLabels();$('ca13File').focus();
  try{await this.reload();}catch{this.status('Custom avatars could not be loaded');}
 },
 close() {if(this.busy)return;this.dialog.close();this.release();this.image=null;$('ca13File').value='';$('ca13Name').value='';this.reset();this.returnFocus?.focus();},
 release(){if(this.objectUrl){URL.revokeObjectURL(this.objectUrl);this.objectUrl=null;}},
 enable(){const ready=!!this.image;for(const id of ['ca13Zoom','ca13X','ca13Y','ca13Reset'])$(id).disabled=!ready||this.busy;$('ca13Save').disabled=!ready||this.busy||!$('ca13Name').value.trim();$('ca13File').disabled=this.busy;$('ca13Name').disabled=this.busy;$('ca13Close').disabled=$('ca13Cancel').disabled=this.busy;this.dialog.setAttribute('aria-busy',String(this.busy));},
 async read(file) {
  if(!file||this.busy)return;
  this.status();this.image=null;this.enable();this.draw();this.release();
  if(file.size>8*1024*1024){this.status('Choose an image smaller than 8 MB');return;}
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){this.status('Choose a still PNG, JPEG or WebP image');return;}
  const url=URL.createObjectURL(file);this.objectUrl=url;
  try {
   const image=new Image();image.src=url;await image.decode();
   if(this.objectUrl!==url)return;
   if(Math.min(image.naturalWidth,image.naturalHeight)<16||Math.max(image.naturalWidth,image.naturalHeight)>8192||image.naturalWidth*image.naturalHeight>32000000)throw Error('Image dimensions must be between 16 and 8192 pixels (maximum 32 MP)');
   // Animated PNG/WebP must not silently become an arbitrary first frame.
   const bytes=new Uint8Array(await file.arrayBuffer());
   if(this.objectUrl!==url)return;
   if(file.type==='image/png'){for(let p=8;p+12<=bytes.length;){const n=new DataView(bytes.buffer).getUint32(p);const tag=String.fromCharCode(...bytes.subarray(p+4,p+8));if(tag==='acTL')throw Error('Choose a still PNG, JPEG or WebP image');p+=12+n;}}
   if(file.type==='image/webp'){for(let p=12;p+8<=bytes.length;){const n=new DataView(bytes.buffer).getUint32(p+4,true),tag=String.fromCharCode(...bytes.subarray(p,p+4));if(tag==='ANIM'||tag==='ANMF')throw Error('Choose a still PNG, JPEG or WebP image');p+=8+n+(n%2);}}
   this.image=image;$('ca13Name').value=file.name.replace(/\.[^.]+$/,'').slice(0,80);this.reset();
  } catch(e) {if(this.objectUrl===url){this.status(['Image dimensions must be between 16 and 8192 pixels (maximum 32 MP)','Choose a still PNG, JPEG or WebP image'].includes(e.message)?e.message:'This image could not be read');this.release();}}
 },
 reset(){$('ca13Zoom').value='1';$('ca13X').value=$('ca13Y').value='0';this.draw();this.enable();},
 draw(){const c=$('ca13Canvas'),ctx=c.getContext('2d');ctx.clearRect(0,0,512,512);$('ca13Empty').hidden=!!this.image;if(!this.image)return;const im=this.image,s=Math.max(512/im.naturalWidth,512/im.naturalHeight)*+$('ca13Zoom').value,w=im.naturalWidth*s,h=im.naturalHeight*s;ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(im,(512-w)/2+(w-512)*+$('ca13X').value/200,(512-h)/2+(h-512)*+$('ca13Y').value/200,w,h);},
 async reload() {
  await Avatars.load(true);if(!Avatars.loaded)throw Error('Custom avatars could not be loaded');
  ExperienceV8.items=Avatars.items;
  const cat=$('ui8Category'),selected=cat.value;cat.replaceChildren(new Option(t('All categories'),'all'));
  [...new Set(Avatars.items.map(i=>i.category||'Классика'))].sort().forEach(c=>cat.add(new Option(t(c),c)));
  cat.value=[...cat.options].some(o=>o.value===selected)?selected:'all';ExperienceV8.category=cat.value;
  Avatars.build();ExperienceV8.renderStore();this.renderSaved();
 },
 renderSaved() {
  if(!$('ca13List'))return;const items=Avatars.items.filter(i=>i.custom),list=$('ca13List');list.replaceChildren();$('ca13Count').textContent=items.length+' / 100';
  if(!items.length){const p=document.createElement('p');p.className='ca13-muted';p.textContent=t('Your saved avatars will appear here');list.append(p);return;}
  for(const item of items){const card=document.createElement('article');card.className='ca13-card';const img=new Image();img.src=item.preview;img.alt='';const name=document.createElement('strong');name.dataset.entityName='';name.textContent=item.name;const apply=document.createElement('button');apply.type='button';apply.className='btn g';apply.textContent=t(Avatars.id===item.id?'Selected':'Apply avatar');apply.disabled=Avatars.id===item.id||this.busy;apply.onclick=async()=>{try{await Avatars.pick(item.id);this.renderSaved();}catch{this.status('The avatar was not applied');}};const del=document.createElement('button');del.type='button';del.className='btn g ca13-delete';del.disabled=this.busy;del.dataset.deleteAvatar=item.id;del.textContent=t(this.pendingDelete===item.id?'Click again to delete':'Delete avatar');del.onclick=()=>{if(this.pendingDelete!==item.id){this.pendingDelete=item.id;this.renderSaved();this.status('Click Delete again to permanently remove this avatar');return;}this.remove(item.id);};card.append(img,name,apply,del);list.append(card);}
 },
 async save() {
  if(this.busy||!this.image||!$('ca13Name').value.trim())return;
  this.busy=true;this.enable();this.renderSaved();this.status('Saving your avatar…');
  try {
   const blob=await new Promise(resolve=>$('ca13Canvas').toBlob(resolve,'image/png'));
   if(!blob)throw Error('Avatar could not be saved');
   const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),30000);let response;
   try{response=await fetch('/api/avatars/custom?name='+encodeURIComponent($('ca13Name').value.trim()),{method:'POST',headers:{'Content-Type':'image/png'},body:blob,signal:ctrl.signal});}finally{clearTimeout(timer);}
   const data=await response.json();if(!response.ok)throw Error(data.error||'Avatar could not be saved');
   await this.reload();await Avatars.pick(data.item.id);this.status('Your avatar is saved and applied');this.pendingDelete='';
  }catch(e){this.status(['Avatar upload is too large','Avatar storage is unavailable','You can save up to 100 custom avatars','Enter an avatar name (1–80 characters)','This image could not be read'].includes(e.message)?e.message:'Avatar could not be saved');}
  finally{this.busy=false;this.enable();this.renderSaved();}
 },
 async remove(id) {
  this.busy=true;this.enable();this.renderSaved();this.status();
  try{await api('/api/avatars/custom/'+encodeURIComponent(id),{method:'DELETE',timeout:15000});await this.reload();this.pendingDelete='';this.status('Avatar deleted');}catch{this.status('Avatar could not be deleted');}
  finally{this.busy=false;this.enable();this.renderSaved();}
 }
};
