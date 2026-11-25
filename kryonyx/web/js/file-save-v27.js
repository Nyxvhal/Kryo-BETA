/* Every user export asks where to save. No anchor/download-directory fallback. */
'use strict';
const FileSave27={
 busy:false,
 name(value,ext){let name=String(value||'export').replace(/[\\/:*?"<>|\x00-\x1f]/g,'_').replace(/[. ]+$/,'').slice(0,170);if(!name)name='export';return name.toLowerCase().endsWith(ext)?name:name+ext;},
 kinds:{layout:['.json','application/json'],theme:['.json','application/json'],karaoke:['.json','application/json'],playlist:['.kryx','text/plain'],frame:['.png','image/png'],cover:['.png','image/png'],avatar:['.png','image/png'],'avatar-pack':['.zip','application/zip'],m3u:['.m3u8','audio/x-mpegurl']},
 specForLink(a){
  const u=new URL(a.href,location.href);if(u.origin!==location.origin)return null;
  let kind,name,ext;
  if(/^\/api\/avatarshop\/download\/[A-Za-z0-9_-]+$/.test(u.pathname)&&['png','svg'].includes(u.searchParams.get('format'))){kind='avatar';ext=u.searchParams.get('format');name=u.pathname.split('/').pop()+'.'+ext;}
  else if(u.pathname==='/api/avatarshop/pack'){kind='avatar-pack';name='Kryo-Avatars-'+u.searchParams.get('collection')+'.zip';}
  else if(/^\/api\/karaoke\/jobs\/[a-f0-9-]{8,64}\/result$/.test(u.pathname)){kind='karaoke';name='track.karaoke.json';}
  else if(/^\/api\/playlists\/\d+\/export.m3u$/.test(u.pathname)){kind='m3u';name='playlist-'+u.pathname.split('/')[3]+'.m3u8';}
  else return null;
  return{kind,name,url:u.pathname+u.search};
 },
 async payload(spec){
  if(typeof spec.text==='string')return new Blob([spec.text],{type:this.kinds[spec.kind][1]});
  let response;
  if(spec.kind==='cover')response=await fetch('/api/image/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls:spec.urls}),signal:AbortSignal.timeout(90000)});
  else if(spec.kind==='frame')response=await fetch(spec.data);
  else{const allowed=this.specForLink({href:new URL(spec.url,location.href).href});if(!allowed||allowed.kind!==spec.kind)throw Error(t('This file type cannot be exported'));response=await fetch(spec.url,{signal:AbortSignal.timeout(120000)});}
  if(!response.ok)throw Error(t('Could not load the file'));
  const mime=(response.headers.get('Content-Type')||'').toLowerCase();if(spec.kind!=='m3u'&&/^(audio|video)\//.test(mime))throw Error(t('Audio track downloads are disabled'));
  return response.blob();
 },
 async save(spec){
  if(this.busy){toast(t('Another save dialog is already open'));return{busy:true};}
  if(!spec||!this.kinds[spec.kind]){toast(t('This file type cannot be exported'));return{error:true};}
  const extension=spec.kind==='avatar'&&spec.url?.includes('format=svg')?'.svg':this.kinds[spec.kind][0];spec={...spec,name:this.name(spec.name,extension)};
  this.busy=true;let output;
  try{
   let result;
   if(window.pywebview?.api){
    if(typeof window.pywebview.api.save_export!=='function')throw Error(t('Restart the updated desktop app to enable Save As'));
    result=await window.pywebview.api.save_export(spec);
    if(result?.error)throw Error(t(result.error));
    if(!result?.saved&&!result?.cancelled)throw Error(t('Could not save the file. Check the source and destination.'));
   }else{
    if(!window.showSaveFilePicker)throw Error(t('Save As is unavailable here. Open the desktop app or a browser with a file picker. No file was saved.'));
    const [defaultExt,defaultMime]=this.kinds[spec.kind],ext=spec.kind==='avatar'&&spec.url?.includes('format=svg')?'.svg':defaultExt,mime=ext==='.svg'?'image/svg+xml':defaultMime;
    // Call the picker in the original user gesture, before any fetch or canvas await.
    const handle=await window.showSaveFilePicker({suggestedName:spec.name,types:[{description:t('Export file'),accept:{[mime]:[ext]}}],excludeAcceptAllOption:true});
    const blob=await this.payload(spec);output=await handle.createWritable();await output.write(blob);await output.close();output=null;result={saved:true,name:handle.name};
   }
   if(result?.saved)toast(t('Saved to the selected file')+(result.path?' — '+result.path:result.name?' — '+result.name:''),6500);
   return result;
  }catch(e){if(output)await output.abort().catch(()=>{});if(e.name==='AbortError')return{cancelled:true};toast(t('Could not save: ')+t(e.message),6500);return{error:true};}
  finally{this.busy=false;}
 },
 init(){document.addEventListener('auxclick',event=>{const a=event.target.closest?.('a[href]');if(a&&this.specForLink(a)){event.preventDefault();event.stopImmediatePropagation();}},true);document.addEventListener('click',event=>{const a=event.target.closest?.('a[href]');if(!a)return;const spec=this.specForLink(a);if(!spec)return;event.preventDefault();event.stopImmediatePropagation();this.save(spec);},true);}
};
FileSave27.init();
