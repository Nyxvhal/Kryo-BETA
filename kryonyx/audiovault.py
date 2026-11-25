"""Private, bounded SQLite audio cache. Not encryption or DRM.
No loose music exports; only complete objects are committed. Python 3.10+.
"""
from __future__ import annotations
import asyncio,functools,hashlib,json,logging,os,sqlite3,stat,time,tempfile,threading

log=logging.getLogger(__name__)
_lock=threading.RLock()
_generation=0
def generation():
 with _lock:return _generation
from .paths import cache_dir
MAX_TRACK = 256 * 1024**2

def folder():
 p=os.path.join(cache_dir(),'audio');os.makedirs(p,exist_ok=True);return p

def key(track_id):return hashlib.sha1(track_id.encode()).hexdigest()
def config():
 try:
  with open(os.path.join(folder(),'policy.json')) as f:d=json.load(f)
  if d.get('mode') in ('internal','stream') and d.get('limit_mb') in (256,1024,2048,6144):return d
 except (OSError,ValueError,AttributeError):pass
 return {'mode':'internal','limit_mb':2048}
def configure(mode,limit_mb):
 if mode not in ('internal','stream') or type(limit_mb) is not int or limit_mb not in (256,1024,2048,6144):raise ValueError('Invalid audio cache policy')
 with _lock:
  p=os.path.join(folder(),'policy.json');tmp=p+'.tmp'
  with open(tmp,'w') as f:json.dump({'mode':mode,'limit_mb':limit_mb},f)
  os.replace(tmp,p)
  if mode=='stream':clear()
  else:trim()
  return stats()
def enabled():return config()['mode']=='internal'
class ClosingConnection(sqlite3.Connection):
 def __exit__(self,*args):
  try:return super().__exit__(*args)
  finally:self.close()
# Each caller owns its connection. The schema lock serializes setup/migration,
# never a shared SQLite connection; SQLite WAL coordinates separate readers.
_schema_lock=threading.RLock()
def connect():
 path=os.path.join(folder(),'audio-vault.sqlite')
 c=sqlite3.connect(path,timeout=30,check_same_thread=False,factory=ClosingConnection)
 try:
  c.execute('PRAGMA busy_timeout=30000')
  with _schema_lock:
   c.execute('PRAGMA auto_vacuum=FULL')
   if c.execute('PRAGMA journal_mode').fetchone()[0].lower()!='wal':
    c.execute('PRAGMA journal_mode=WAL')
   c.execute('PRAGMA journal_size_limit=8388608')
   c.execute('CREATE TABLE IF NOT EXISTS audio (key TEXT PRIMARY KEY,mime TEXT NOT NULL,size INTEGER NOT NULL,touched REAL NOT NULL,data BLOB NOT NULL,meta TEXT)')
   cols={r[1] for r in c.execute('PRAGMA table_info(audio)')}
   if 'meta' not in cols:
    # SQLite's write lock also serializes migration against a second process.
    c.execute('BEGIN IMMEDIATE')
    cols={r[1] for r in c.execute('PRAGMA table_info(audio)')}
    if 'meta' not in cols:c.execute('ALTER TABLE audio ADD COLUMN meta TEXT')
    c.commit()
  return c
 except BaseException:
  c.close()
  raise

async def run_blocking_owned(fn,*args,_cancel_cleanup=None,**kwargs):
 """Do not release an owned file/SQLite resource until its worker completes.

 Cancelling asyncio.to_thread alone does not stop the underlying OS thread.
 Shield the actual executor future and drain it even after repeated cancellation.
 """
 loop=asyncio.get_running_loop()
 future=loop.run_in_executor(None,functools.partial(fn,*args,**kwargs))
 try:
  return await asyncio.shield(future)
 except asyncio.CancelledError:
  while not future.done():
   try:await asyncio.shield(future)
   except asyncio.CancelledError:continue
   except Exception:break
  try:
   result=future.result()
   if _cancel_cleanup is not None:_cancel_cleanup(result)
  except Exception:log.exception('[audio-cache] worker failed during cancellation')
  raise

TIERS={'data':0,'balanced':1,'best':2}
def _meta_for(track_id,tier=None,extra=None):
 if tier not in TIERS:
  try:
   from .audio_quality import mode
   tier=mode()
  except Exception:tier='best'
 doc={'tier':tier}
 for k,v in (extra or {}).items():
  if k in ('codec','kbps','source') and v not in (None,''):doc[k]=v
 return json.dumps(doc,separators=(',',':'))

def info(token):
 """Size, mime and stored quality metadata of one committed object."""
 if not token or not token.startswith('vault:'):return None
 with connect() as c:r=c.execute('SELECT size,mime,meta FROM audio WHERE key=?',(token[6:],)).fetchone()
 if not r:return None
 try:meta=json.loads(r[2]) if r[2] else {}
 except ValueError:meta={}
 if not isinstance(meta,dict):meta={}
 return {'size':r[0],'mime':r[1],'tier':meta.get('tier') if meta.get('tier') in TIERS else None,'codec':meta.get('codec'),'kbps':meta.get('kbps'),'source':meta.get('source')}

def tier_ok(token,wanted=None):
 """A cached object satisfies the requested quality mode (higher or equal tier)."""
 if wanted not in TIERS:
  try:
   from .audio_quality import mode
   wanted=mode()
  except Exception:wanted='best'
 doc=info(token)
 if not doc:return False
 return TIERS.get(doc['tier'] or 'best',2)>=TIERS[wanted]

def forget(track_id):
 """Drop one committed object (explicit quality change of that track)."""
 with _lock:
  with connect() as c:n=c.execute('DELETE FROM audio WHERE key=?',(key(track_id),)).rowcount
 return n

def store(track_id,path,mime,raw_key=None,expected_generation=None,tier=None,meta=None):
 with _lock:return _store(track_id,path,mime,raw_key,expected_generation,tier,meta)
def _store(track_id,path,mime,raw_key=None,expected_generation=None,tier=None,meta=None):
 if expected_generation is not None and expected_generation != _generation:
  os.remove(path);return None
 size=os.path.getsize(path)
 if not enabled() or not 0<size<=min(MAX_TRACK,config()['limit_mb']*1024**2):
  os.remove(path);return None
 k=raw_key or key(track_id)
 with connect() as c:
  # Python 3.11+ writes in small chunks, without loading a whole track into RAM.
  if hasattr(c,'blobopen'):
   c.execute('INSERT OR REPLACE INTO audio(key,mime,size,touched,data,meta) VALUES(?,?,?,?,zeroblob(?),?)',(k,mime,size,time.time(),size,_meta_for(track_id,tier,meta)))
   rowid=c.execute('SELECT rowid FROM audio WHERE key=?',(k,)).fetchone()[0]
   written=0
   with c.blobopen('audio','data',rowid,readonly=False) as blob,open(path,'rb') as f:
    while chunk:=f.read(512*1024):
     written+=len(chunk)
     if written>size:raise ValueError('Audio changed while committing')
     blob.write(chunk)
   if written!=size:raise ValueError('Audio changed while committing')
  else:
   # Python 3.10 fallback: bounded to MAX_TRACK, no new runtime dependency.
   with open(path,'rb') as f:data=f.read(MAX_TRACK+1)
   if len(data)!=size:raise ValueError('Audio changed while committing')
   c.execute('INSERT OR REPLACE INTO audio(key,mime,size,touched,data,meta) VALUES(?,?,?,?,?,?)',(k,mime,size,time.time(),data,_meta_for(track_id,tier,meta)))

 os.remove(path);trim();return 'vault:'+k

def find(track_id):
 if not enabled():return None
 k=key(track_id)
 with connect() as c:
  row=c.execute('SELECT size,touched FROM audio WHERE key=?',(k,)).fetchone()
  if row:
   if row[1]<time.time()-300:c.execute('UPDATE audio SET touched=? WHERE key=?',(time.time(),k))
   return 'vault:'+k
 # Migrate old loose audio on access, preserving its bytes; no network.
 old=hashlib.sha1(track_id.encode()).hexdigest()
 from .audiocache import MIME_BY_EXT
 with _lock:
  # Another finder may have committed and removed the legacy file while this
  # caller waited for the migration lock; re-check the committed row first.
  with connect() as c:existing=c.execute('SELECT 1 FROM audio WHERE key=?',(k,)).fetchone()
  if existing:return 'vault:'+k
  for ext,mime in MIME_BY_EXT.items():
   p=os.path.join(folder(),old+ext)
   if os.path.isfile(p):return store(track_id,p,mime)
 return None

def mime_for(token):
 if not token.startswith('vault:'):return 'application/octet-stream'
 with connect() as c:r=c.execute('SELECT mime FROM audio WHERE key=?',(token[6:],)).fetchone()
 return r[0] if r else 'application/octet-stream'

def trim(max_bytes=None):
 with _lock:
  limit=max_bytes if max_bytes is not None else config()['limit_mb']*1024**2
  with connect() as c:
   c.execute('BEGIN IMMEDIATE')
   total=c.execute('SELECT COALESCE(SUM(size),0) FROM audio').fetchone()[0]
   for k,size in c.execute('SELECT key,size FROM audio ORDER BY touched').fetchall():
    if total<=limit:break
    c.execute('DELETE FROM audio WHERE key=?',(k,));total-=size
 # Never delete active .part files: writers own them.

def stats():
 with connect() as c:n,size=c.execute('SELECT COUNT(*),COALESCE(SUM(size),0) FROM audio').fetchone()
 legacy=[]
 for nme in os.listdir(folder()):
  if nme.rsplit('.',1)[-1] in ('mp3','m4a','mp4','opus','ogg','webm','flac','wav'):legacy.append(os.path.join(folder(),nme))
 disk=0
 for name in os.listdir(folder()):
  try:
   entry=os.stat(os.path.join(folder(),name))
   if stat.S_ISREG(entry.st_mode):disk+=entry.st_size
  except FileNotFoundError:continue  # WAL/SHM files can disappear during a checkpoint
 return {'tracks':n,'bytes':size,'mb':round(size/1048576,1),'disk_bytes':disk,'legacy_files':len(legacy),**config(),'storage':'sqlite','encrypted':False}
def clear():
 with _lock:return _clear()
def _clear():
 global _generation
 _generation+=1
 with connect() as c:n=c.execute('SELECT COUNT(*) FROM audio').fetchone()[0];c.execute('DELETE FROM audio')
 for name in os.listdir(folder()):
  # Old media only; do not remove active partials or the database under readers.
  if name.rsplit('.',1)[-1] in ('mp3','m4a','mp4','opus','ogg','webm','flac','wav'):
   try:os.remove(os.path.join(folder(),name));n+=1
   except OSError:pass
 return n

def materialize(token):
 """Temporary decode input for explicitly requested karaoke jobs, owned by job."""
 c=connect()
 try:
  c.execute('BEGIN')  # Pin one consistent snapshot while copying chunks.
  r=c.execute('SELECT size FROM audio WHERE key=?',(token[6:],)).fetchone()
  if not r:return None
  fd,path=tempfile.mkstemp(prefix='kryonyx-decode-',suffix='.tmp',dir=cache_dir())
  try:
   with os.fdopen(fd,'wb') as f:
    for at in range(0,r[0],512*1024):f.write(c.execute('SELECT substr(data,?,?) FROM audio WHERE key=?',(at+1,512*1024,token[6:])).fetchone()[0])
   return path
  except BaseException:
   os.remove(path);raise
 finally:c.close()

async def serve(request,token):
 from aiohttp import web
 from .clipstream import ranges
 import asyncio
 c=connect()
 try:
  c.execute('BEGIN');r=c.execute('SELECT size,mime,rowid FROM audio WHERE key=?',(token[6:],)).fetchone()
  if not r:raise web.HTTPNotFound()
  size,mime,rowid=r
  try:a,b,partial=ranges(request.headers.get('Range',''),size)
  except ValueError:return web.Response(status=416,headers={'Content-Range':f'bytes */{size}'})
  headers={'Content-Type':mime,'Content-Length':str(b-a+1),'Accept-Ranges':'bytes','Cache-Control':'no-store','X-Kryonyx-Cache':'hit'}
  if partial:headers['Content-Range']=f'bytes {a}-{b}/{size}'
  resp=web.StreamResponse(status=206 if partial else 200,headers=headers);await resp.prepare(request)
  if request.method!='HEAD':
   if hasattr(c,'blobopen'):
    with c.blobopen('audio','data',rowid,readonly=True) as blob:
     blob.seek(a);remaining=b-a+1
     while remaining:
      chunk=await run_blocking_owned(blob.read,min(512*1024,remaining))
      if not chunk:raise IOError('Incomplete cached audio')
      remaining-=len(chunk);await resp.write(chunk)
   else:
    for at in range(a,b+1,512*1024):
     chunk=await run_blocking_owned(lambda at=at:c.execute('SELECT substr(data,?,?) FROM audio WHERE key=?',(at+1,min(512*1024,b-at+1),token[6:])).fetchone()[0])
     await resp.write(chunk)
  await resp.write_eof();return resp
 finally:c.close()

def migrate_legacy():
 from .audiocache import MIME_BY_EXT
 migrated=0
 for name in os.listdir(folder()):
  stem,ext=os.path.splitext(name)
  if ext not in MIME_BY_EXT or len(stem)!=40 or any(c not in '0123456789abcdef' for c in stem):continue
  try:
   if store('',os.path.join(folder(),name),MIME_BY_EXT[ext],raw_key=stem):migrated+=1
  except (OSError,sqlite3.Error,ValueError):pass
 return migrated

def fingerprint(token):
 c=connect()
 try:
  c.execute('BEGIN');r=c.execute('SELECT rowid,size FROM audio WHERE key=?',(token[6:],)).fetchone()
  if not r:return None
  h=hashlib.sha256()
  if hasattr(c,'blobopen'):
   with c.blobopen('audio','data',r[0],readonly=True) as blob:
    while chunk:=blob.read(512*1024):h.update(chunk)
  else:
   for at in range(0,r[1],512*1024):h.update(c.execute('SELECT substr(data,?,?) FROM audio WHERE key=?',(at+1,512*1024,token[6:])).fetchone()[0])
  return h.hexdigest()
 finally:c.close()
