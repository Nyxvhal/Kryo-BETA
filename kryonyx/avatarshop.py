"""Local avatar shop: user supplied assets; no payments or remote accounts."""
import os,json,zipfile,threading,tempfile
from pathlib import Path
from . import avatars
from .paths import resource_dir,cache_dir
_lock=threading.Lock()
def asset(aid,fmt='png'):
 item=avatars.by_id(aid)
 if not item or fmt not in item.get('formats',['png']):raise ValueError('Unknown avatar or format')
 if item.get('custom'):
  return avatars.custom_avatars.asset(avatars.data_dir(),aid)
 base=Path(resource_dir())/'web/img/avatars'
 p=base/'svg'/(item['id']+'.svg') if fmt=='svg' else base/(item['id']+'.png')
 if not p.is_file():raise ValueError('Asset is not available')
 return p

def pack(collection='all'):
 if collection not in ('all','original','redesigned','signature','portraits','custom'):raise ValueError('Unknown collection')
 items=[i for i in avatars.catalog() if collection=='all' or i.get('collection','original')==collection]
 # Revision is bound to catalogue + file metadata, no user-controlled paths.
 import hashlib
 revision=hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest()[:12]
 target=Path(cache_dir())/f'avatars-{collection}-{revision}.zip'
 with _lock:
  if target.is_file():return target
  fd,tmp=tempfile.mkstemp(prefix='avatars-',suffix='.part',dir=cache_dir());os.close(fd)
  try:
   with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('README.txt','Kryo avatar collection. User-supplied assets. No payment required in this app.\nNo asset licence is granted by the code licence. See RIGHTS and manifest.json.\n')
    z.writestr('manifest.json',json.dumps(items,ensure_ascii=False,indent=2))
    for item in items:
     for fmt in item.get('formats',['png']):z.write(asset(item['id'],fmt),item.get('collection','original')+'/'+fmt+'/'+item['id']+'.'+fmt)
    notices=Path(resource_dir())/'avatar-notices'
    if notices.exists():
     for p in notices.rglob('*'):
      if p.is_file():z.write(p,'RIGHTS/'+str(p.relative_to(notices)))
   os.replace(tmp,target)
  finally:
   if os.path.exists(tmp):os.remove(tmp)
 return target
