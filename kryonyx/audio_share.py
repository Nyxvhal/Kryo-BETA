"""Explicit, bounded MP3 sharing jobs. No destination paths or media URLs from JS.
Sources are resolved by the existing provider layer; no DRM bypass or fallback match.
Temporary files are capability-addressed and removed on cancel, expiry or shutdown.
"""
from __future__ import annotations
import asyncio, base64, io, ipaddress, json, os, re, secrets, shutil, socket, time
from pathlib import Path
from urllib.parse import urlsplit
import unicodedata
import aiohttp
from PIL import Image, ImageOps
from . import audiocache, audiovault, clipcache, paths
from .file_exports import safe_name
MAX_INPUT=256*1024**2
MAX_OUTPUT=128*1024**2
TTL=30*60
class ShareError(ValueError): pass

def clean_track(value):
    if not isinstance(value,dict): raise ShareError('Invalid track')
    out={k:str(value.get(k) or '').strip() for k in ('id','title','artist','thumbnail')}
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,25}:[^\s\x00-\x1f]{1,500}',out['id']) or '://' in out['id']:
        raise ShareError('Invalid track')
    for key in ('title','artist'):
        out[key]=re.sub(r'[\x00-\x1f\x7f]',' ',out[key])[:300].strip()
    if not out['title']:raise ShareError('Invalid track')
    if len(out['thumbnail'])>7*1024**2:raise ShareError('Invalid artwork')
    return out

def root():
    p=Path(paths.cache_dir())/'audio-share64';p.mkdir(parents=True,exist_ok=True);return p

def portable_name(name):
    # Some browser download handlers replace non-ASCII filenames with "download".
    # Tags and native/Web Share filenames retain Unicode; only this fallback is portable.
    letters='абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїєґ'
    latin=['a','b','v','g','d','e','yo','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya','i','yi','ye','g']
    table=dict(zip(letters,latin));table.update({k.upper():v.capitalize() for k,v in list(table.items())})
    value=''.join(table.get(c,c) for c in str(name)).replace('—','-').replace('–','-')
    value=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode()
    value=re.sub(r'[^A-Za-z0-9 ._()-]','_',value).strip(' ._')
    return safe_name(value if value and value.lower()!='mp3' else 'track','.mp3')

def completed(token):
    if not isinstance(token,str) or not re.fullmatch(r'[a-f0-9]{48}',token):raise ShareError('Shared file expired')
    p=root()/token
    if p.is_symlink():raise ShareError('Shared file expired')
    try:
        d=json.loads((p/'ready.json').read_text());f=p/'track.mp3'
        if time.time()-d['created']>TTL or f.is_symlink() or not f.is_file() or not 0<f.stat().st_size<=MAX_OUTPUT:raise ValueError()
        return f,safe_name(d['name'],'.mp3')
    except (OSError,ValueError,KeyError,TypeError):raise ShareError('Shared file expired') from None

class PublicResolver(aiohttp.abc.AbstractResolver):
    async def resolve(self,host,port=0,family=socket.AF_INET):
        records=await aiohttp.resolver.DefaultResolver().resolve(host,port,family)
        if not records or any(not ipaddress.ip_address(r['host']).is_global for r in records):raise OSError('Private artwork address')
        return records
    async def close(self):pass

async def cover_bytes(url):
    if not url:return None
    if url.startswith('/img/'):
        p=(Path(paths.web_dir())/url.lstrip('/')).resolve();base=(Path(paths.web_dir())/'img').resolve()
        if base not in p.parents or not p.is_file() or p.stat().st_size>5*1024**2:return None
        return await asyncio.to_thread(p.read_bytes)
    if url.startswith('data:image/'):
        try:
            head,data=url.split(',',1)
            if ';base64' not in head:return None
            result=base64.b64decode(data,validate=True)
            return result if len(result)<=5*1024**2 else None
        except (ValueError,TypeError):return None
    try:
        u=urlsplit(url)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.port not in (None,443):return None
        try:
            if not ipaddress.ip_address(u.hostname).is_global:return None
        except ValueError:pass
    except ValueError:return None
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver()),timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(url,allow_redirects=False) as r:
                if r.status!=200 or not r.headers.get('Content-Type','').startswith('image/'):return None
                out=bytearray()
                async for part in r.content.iter_chunked(65536):
                    out.extend(part)
                    if len(out)>5*1024**2:return None
                return bytes(out)
    except (OSError,ValueError,aiohttp.ClientError,asyncio.TimeoutError):return None

def prepare_cover(data,dest):
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width*im.height>24_000_000:return False
            im=ImageOps.exif_transpose(im);im.thumbnail((600,600));im.convert('RGB').save(dest,'JPEG',quality=90)
        return True
    except (OSError,ValueError,Image.DecompressionBombError):return False

class Jobs:
    def __init__(self):self.jobs={};self.janitor=None
    async def start(self):
        self.sweep();self.janitor=asyncio.create_task(self.reaper())
    def sweep(self):
        now=time.time()
        for p in root().iterdir():
            if p.is_dir() and not p.is_symlink() and re.fullmatch('[a-f0-9]{48}',p.name) and now-p.stat().st_mtime>TTL:
                # Never remove a directory or forget its owner while a task is
                # still using it. Explicit cancellation waits for the task.
                job=self.jobs.get(p.name)
                if job and job.get('task') and not job['task'].done():continue
                self.jobs.pop(p.name,None)
                shutil.rmtree(p,ignore_errors=True)
    async def reaper(self):
        while True:
            await asyncio.sleep(60);self.sweep()
    def create(self,track,resolve,session):
        self.sweep()
        if sum(j['state'] in ('queued','loading','encoding') for j in self.jobs.values())>=2:raise ShareError('Another track is being prepared')
        if len(self.jobs)>=4:raise ShareError('Close an earlier share before preparing another')
        track=clean_track(track);token=secrets.token_hex(24);p=root()/token;p.mkdir(mode=0o700)
        j={'token':token,'state':'queued','track':track,'created':time.time(),'artwork':False,'name':safe_name(' — '.join(x for x in (track['artist'],track['title']) if x),'.mp3')}
        self.jobs[token]=j;j['task']=asyncio.create_task(self.run(j,resolve,session));return self.public(j)
    def public(self,j):return {k:j[k] for k in ('token','state','name','artwork') }|({'error':j['error']} if j.get('error') else {})
    def get(self,token):
        self.sweep();j=self.jobs.get(token)
        if not j:raise ShareError('Shared file expired')
        if j['state']=='ready':completed(token)
        return self.public(j)
    async def cancel(self,token):
        j=self.jobs.get(token)
        if not j:return
        # Keep ownership registered while cancellation drains the worker. A
        # concurrent sweep must not mistake the live directory for an orphan.
        task=j['task']
        if not task.done() and not task.cancelling():task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        if self.jobs.get(token) is j:self.jobs.pop(token,None)
        shutil.rmtree(root()/token,ignore_errors=True)
    async def close(self):
        if self.janitor:self.janitor.cancel();await asyncio.gather(self.janitor,return_exceptions=True)
        for token in list(self.jobs):await self.cancel(token)
    async def run(self,j,resolve,session):
        p=root()/j['token'];source=p/'source.bin';proc=None
        try:
            exe=clipcache.ffmpeg_exe()
            if not exe:raise ShareError('FFmpeg is required to prepare an audio file')
            j['state']='loading';t=j['track'];cached=audiocache.find(t['id'])
            if cached and cached.startswith('vault:'):
                materialized=await audiovault.run_blocking_owned(
                    audiovault.materialize,cached,
                    _cancel_cleanup=lambda path: os.unlink(path) if path and os.path.exists(path) else None)
                if materialized:os.replace(materialized,source)
            if not source.exists():
                if t['id'].startswith(('sp:','dz:')):raise ShareError('Choose a playable source before sharing this track')
                # Do not substitute another recording using title/artist matching.
                _id,media=await resolve(t['id'],t['title'],t['artist'],False)
                async with session.get(media['url'],headers=media.get('headers') or {},timeout=aiohttp.ClientTimeout(total=180)) as r:
                    if r.status!=200:raise ShareError('Audio source is unavailable')
                    expected=r.headers.get('Content-Length');written=0
                    if expected and int(expected)>MAX_INPUT:raise ShareError('Audio file is too large')
                    with source.open('wb') as f:
                        async for part in r.content.iter_chunked(256*1024):
                            written+=len(part)
                            if written>MAX_INPUT:raise ShareError('Audio file is too large')
                            f.write(part)
                    if not written or (expected and written!=int(expected)):raise ShareError('Audio source is incomplete')
            data=await cover_bytes(t['thumbnail'])
            j['artwork']=bool(data and await audiovault.run_blocking_owned(prepare_cover,data,p/'cover.jpg'))
            j['state']='encoding'
            cmd=[exe,'-nostdin','-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe','-format_whitelist','mp3,mov,matroska,webm,ogg,wav,flac,aac','-i',str(source)]
            if j['artwork']:cmd+=['-i',str(p/'cover.jpg')]
            cmd+=['-map','0:a:0','-map_metadata','-1','-c:a','libmp3lame','-b:a','192k','-fs',str(MAX_OUTPUT)]
            if j['artwork']:cmd+=['-map','1:v:0','-c:v','copy','-disposition:v:0','attached_pic','-metadata:s:v','title=Album cover','-metadata:s:v','comment=Cover (front)']
            else:cmd+=['-vn']
            cmd+=['-id3v2_version','3','-metadata','title='+t['title'],'-metadata','artist='+t['artist'],str(p/'track.mp3')]
            proc=await asyncio.create_subprocess_exec(*cmd,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0))
            await asyncio.wait_for(proc.wait(),180)
            if proc.returncode or not (p/'track.mp3').exists() or not 0<(p/'track.mp3').stat().st_size<MAX_OUTPUT:raise ShareError('Could not prepare the audio file')
            (p/'ready.json').write_text(json.dumps({'name':j['name'],'created':time.time()},ensure_ascii=False),encoding='utf-8');j['state']='ready'
        except asyncio.CancelledError:raise
        except Exception as e:
            j['state']='error';j['error']=str(e) if isinstance(e,ShareError) else 'Could not prepare the audio file'
        finally:
            if proc and proc.returncode is None:proc.kill();await proc.wait()
            for name in ('source.bin','cover.jpg'):(p/name).unlink(missing_ok=True)
            if j['state']!='ready':(p/'track.mp3').unlink(missing_ok=True)
