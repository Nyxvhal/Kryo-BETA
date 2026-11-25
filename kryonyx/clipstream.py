"""Clip Studio: contiguous disk cache with native parallel A/V playback.

HD no longer waits for full download + mux. The browser can read each source
via real Range responses while background jobs keep filling disk. Source URLs
and headers (possibly containing auth) never leave this module's resolver.
"""
from __future__ import annotations
import asyncio, hashlib, json, math, os, re, shutil, time
from pathlib import Path
from typing import Awaitable, Callable
import aiohttp
from aiohttp import web
from . import clipcache
from .paths import data_dir

WINDOW = 2*1024*1024
MAX_TRACK = 2*1024**3
MAX_CLIP = 3*1024**3
READ_SIZE = 128*1024
CACHE_LIMIT = 3*1024**3
_gate = asyncio.Semaphore(4)


def root():
    p=Path(data_dir())/'clip-studio';p.mkdir(parents=True,exist_ok=True);return p

def key_for(track_id, quality):
    return hashlib.sha256((str(track_id)+'\n'+str(quality)).encode()).hexdigest()[:24]

def ranges(header, total):
    """One byte range, inclusive. Malformed/multiple/unsatisfiable -> 416."""
    if not header:return 0,total-1,False
    m=re.fullmatch(r'bytes=(\d*)-(\d*)',header.strip(),re.I)
    if not m or not any(m.groups()):raise ValueError('Invalid byte range')
    a,b=m.groups()
    if not a:
        n=int(b)
        if n<=0:raise ValueError('Invalid suffix range')
        return max(0,total-n),total-1,True
    a=int(a);b=min(int(b) if b else total-1,total-1)
    if a>=total or b<a:raise ValueError('Range outside file')
    return a,b,True

def safe_reason(exc):
    # Never expose signed CDN query strings, request headers or raw cookies.
    text=str(exc) or type(exc).__name__
    text=re.sub(r'https?://\S+','[source URL hidden]',text)
    text=re.sub(r"(?i)(cookie|authorization|sapisid|session_token)[\"']?\s*[:=].*",r'\1: [hidden]',text)
    return text[:360]

class Source:
    def __init__(self, owner, kind, media):
        self.owner,self.kind,self.media=owner,kind,media
        self.part=owner.directory/(kind+'.part')
        self.final=owner.directory/(kind+'.bin')
        self.total=(int(media.get('size') or 0) or None) if media.get('complete') else None
        self.written=0;self.done=False;self.paused=False;self.cancelled=False
        self.error='';self.task=None;self.condition=asyncio.Condition()
        self.mime=str(media.get('mime') or ('video/mp4' if kind=='video' else 'audio/mp4')).split(';')[0]
        if self.mime not in ('video/mp4','video/webm','audio/mp4','audio/webm','audio/ogg','audio/mpeg'):
            self.mime='video/mp4' if kind=='video' else 'audio/mp4'
        self.rate=0.0;self.started=time.monotonic();self.readers=0
        if media.get("complete") and self.final.exists():
            size=self.final.stat().st_size
            if size>0 and (not self.total or size==self.total):
                self.total=self.written=size;self.done=True

    def path(self):return self.final if self.done else self.part
    async def notify(self):
        async with self.condition:self.condition.notify_all()
    async def wait(self,timeout=.5):
        try:
            async with self.condition:await asyncio.wait_for(self.condition.wait(),timeout)
        except asyncio.TimeoutError:pass
    async def get(self,refresh=False):
        if refresh:
            pair=await self.owner.refresh()
            new=pair[self.kind]
            old_tag=self.media.get('itag') or self.media.get('format_id')
            new_tag=new.get('itag') or new.get('format_id')
            if old_tag and new_tag and str(old_tag)!=str(new_tag):
                raise RuntimeError('Source format changed. Restart this download.')
            self.media=new
        return self.media
    def validate_window(self,win,start):
        if win.resp.status==206:
            m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)',win.resp.headers.get('Content-Range',''))
            if not m or int(m[1])!=start:raise RuntimeError('Source returned the wrong byte range')
        if win.total:
            if self.total and self.total!=win.total:raise RuntimeError('Source size changed. Restart the clip.')
            if win.total>MAX_TRACK:raise RuntimeError('Video track exceeds the 2 GiB limit')
            self.total=win.total
        if self.owner.total_bytes()>MAX_CLIP:raise RuntimeError('Clip exceeds the 3 GiB limit')

    def start(self):
        if self.done or self.cancelled or (self.task and not self.task.done()):return
        self.paused=False;self.error='';self.started=time.monotonic()
        self.task=asyncio.create_task(self.run())
    async def pause(self):
        self.paused=True
        if self.task and not self.task.done():self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        await self.notify()
    async def cancel(self):
        self.cancelled=True;await self.pause()

    async def run(self):
        initial=self.written
        try:
            async with _gate:
                self.owner.directory.mkdir(parents=True,exist_ok=True)
                if self.part.exists():
                    # Only resume our own contiguous prefix. Never sparse files.
                    self.written=self.part.stat().st_size
                failures=0
                with self.part.open('ab') as f:
                    while not self.total or self.written<self.total:
                        if self.paused or self.cancelled:return
                        start=self.written;end=start+WINDOW-1
                        if self.total:end=min(end,self.total-1)
                        win=None;got=0;reached_eof=False
                        try:
                            win=await clipcache.open_window(self.owner.manager.http,self.get,start,end,refresh=failures>0)
                            if win.resp.status==416:
                                if self.total and self.written==self.total:break
                                raise RuntimeError('Source rejected an unfinished byte range')
                            self.validate_window(win,start)
                            async for chunk in win.chunks():
                                chunk=chunk[:end-self.written+1]
                                if not chunk:break
                                f.write(chunk);f.flush();self.written+=len(chunk);got+=len(chunk)
                                if self.written>MAX_TRACK:raise RuntimeError('Video track exceeds the 2 GiB limit')
                                elapsed=max(.1,time.monotonic()-self.started)
                                self.rate=max(0,(self.written-initial)/elapsed)
                                await self.notify()
                                if self.written>end:break
                            else:reached_eof=True
                            if not self.total and reached_eof and got<end-start+1:
                                self.total=self.written
                            if not got and (not self.total or self.written<self.total):raise RuntimeError('Source returned no bytes')
                            failures=0
                        except (aiohttp.ClientError,asyncio.TimeoutError,RuntimeError,OSError) as exc:
                            failures+=1
                            if failures>=5:raise RuntimeError(safe_reason(exc)) from None
                            await asyncio.sleep(min(3,.3*failures))
                        finally:
                            if win:win.release()
                if not self.written or (self.total and self.written!=self.total):raise RuntimeError('Incomplete source track')
                for attempt in range(20):
                    try:os.replace(self.part,self.final);break
                    except PermissionError:
                        if attempt==19:raise
                        await asyncio.sleep(.05)
                self.done=True;self.total=self.written
                self.owner.persist();await self.notify()
        except asyncio.CancelledError:raise
        except Exception as exc:self.error=safe_reason(exc);await self.notify()
        finally:await self.notify()

    async def serve(self,request):
        # Metadata/range reads must work before background download completes.
        waited=time.monotonic()
        while not self.total and not self.done and not self.error and not self.cancelled:
            if time.monotonic()-waited>15:break
            await self.wait()
        if self.cancelled:raise web.HTTPGone(text='Download cancelled')
        if self.error and not self.written:raise web.HTTPBadGateway(text=self.error)
        total=self.total
        if not total:
            # Do not fabricate Content-Range/Content-Length for unknown lengths.
            if request.headers.get('Range') not in (None,'bytes=0-'):
                raise web.HTTPServiceUnavailable(text='Source size not known yet',headers={'Retry-After':'1'})
            start,stop,partial=0,None,False
        else:
            try:start,stop,partial=ranges(request.headers.get('Range',''),total)
            except ValueError:raise web.HTTPRequestRangeNotSatisfiable(headers={'Content-Range':f'bytes */{total}'})
        headers={'Content-Type':self.mime,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
        if total:
            headers.update({'Accept-Ranges':'bytes','Content-Length':str(stop-start+1)})
            if partial:headers['Content-Range']=f'bytes {start}-{stop}/{total}'
        response=web.StreamResponse(status=206 if partial else 200,headers=headers)
        await response.prepare(request)
        if request.method=='HEAD':return response
        self.readers+=1;win=None
        try:
            pos=start;last_progress=time.monotonic()
            while stop is None or pos<=stop:
                if self.cancelled:break
                if pos<self.written:
                    amount=min(READ_SIZE,self.written-pos,(stop-pos+1) if stop is not None else READ_SIZE)
                    path=self.path()
                    try:data=await asyncio.to_thread(clipcache.read_at,str(path),pos,amount)
                    except FileNotFoundError:
                        # Finalization may rename between path() and open().
                        path=self.path();data=await asyncio.to_thread(clipcache.read_at,str(path),pos,amount)
                    if data:await response.write(data);pos+=len(data);last_progress=time.monotonic();continue
                if self.done:break
                if self.error:break
                if self.paused:
                    await self.wait();continue
                if total and pos>self.written+256*1024:
                    # MP4 index at tail / a far seek: fetch only that range.
                    # These bytes are not falsely counted as cached prefix.
                    end=min(stop,pos+WINDOW-1)
                    win=await clipcache.open_window(self.owner.manager.http,self.get,pos,end)
                    self.validate_window(win,pos)
                    async for chunk in win.chunks():
                        chunk=chunk[:end-pos+1]
                        if not chunk:break
                        await response.write(chunk);pos+=len(chunk);last_progress=time.monotonic()
                        if pos>end:break
                    win.release();win=None;continue
                if time.monotonic()-last_progress>90:break
                await self.wait()
            await response.write_eof()
        except (ConnectionResetError,BrokenPipeError,asyncio.CancelledError):pass
        finally:
            if win:win.release()
            self.readers-=1
        return response

class Session:
    def __init__(self,manager,track_id,title,artist,quality):
        self.manager,self.track_id,self.title,self.artist,self.quality=manager,track_id,title,artist,quality
        self.id=key_for(track_id,quality);self.directory=root()/self.id
        self.video_id='';self.height=0;self.container='mp4';self.state='resolving'
        self.error='';self.mux_error='';self.sources={};self.task=None;self.mux_task=None
        self.final=None;self.created=time.time();self.paused=False;self.cancelled=False;self.last=time.monotonic()
    def total_bytes(self):return sum(s.total or 0 for s in self.sources.values())
    async def refresh(self):return await self.manager.resolve(self.video_id,self.quality,True)
    def persist(self):
        if not self.sources:return
        self.directory.mkdir(parents=True,exist_ok=True)
        data={'track_id':self.track_id,'title':self.title[:500],'artist':self.artist[:500], 'quality':self.quality,
              'video_id':self.video_id,'height':self.height,'container':self.container,
              'sources':{k:{'size':s.total,'mime':s.mime,'complete':s.done} for k,s in self.sources.items()}}
        p=self.directory/'metadata.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data),encoding='utf-8');os.replace(tmp,p)
    def restore(self):
        try:
            d=json.loads((self.directory/'metadata.json').read_text())
            if d['track_id']!=self.track_id or d['quality']!=self.quality:return False
            if not d.get('sources') or not all(x.get('complete') for x in d['sources'].values()):return False
            self.video_id=d['video_id'];self.height=d['height'];self.container=d['container']
            self.sources={k:Source(self,k,m) for k,m in d['sources'].items()}
            if not all(s.done for s in self.sources.values()):self.sources={};return False
            final=self.directory/('clip.'+self.container)
            self.final=final if final.exists() else (self.sources['video'].final if 'audio' not in self.sources else None)
            self.state='done';return True
        except (OSError,ValueError,KeyError,TypeError):self.sources={};return False
    def start(self):
        self.task=asyncio.create_task(self.prepare())
    async def prepare(self):
        try:
            if self.restore():
                if 'audio' in self.sources and not self.final:await self.monitor()
                return
            self.video_id=await self.manager.identify(self.track_id,self.title,self.artist)
            pair=await self.manager.resolve(self.video_id,self.quality,False)
            self.container='webm' if pair.get('container')=='webm' else 'mp4'
            self.height=int(pair['video'].get('height') or pair.get('height') or 0)
            self.sources={'video':Source(self,'video',pair['video'])}
            if pair.get('audio'):self.sources['audio']=Source(self,'audio',pair['audio'])
            if self.total_bytes()>MAX_CLIP:raise RuntimeError('Clip exceeds the 3 GiB limit')
            self.state='downloading'
            for source in self.sources.values():
                # A process restart cannot trust partial bytes without source identity.
                if not source.done:
                    source.part.unlink(missing_ok=True);source.final.unlink(missing_ok=True)
                if not self.paused:source.start()
            self.persist()
            await self.monitor()
        except asyncio.CancelledError:raise
        except Exception as exc:self.state='error';self.error=safe_reason(exc)
    async def monitor(self):
        while not self.cancelled:
            errors=[s.error for s in self.sources.values() if s.error]
            if errors:
                self.state='error';self.error=errors[0]
                for source in self.sources.values():
                    if not source.done:await source.pause()
                return
            if self.sources and all(s.done for s in self.sources.values()):
                self.state='muxing';self.persist()
                if 'audio' in self.sources:
                    try:
                        tmp=self.directory/('clip.'+self.container+'.part')
                        await clipcache._mux(str(self.sources['video'].final),str(self.sources['audio'].final),str(tmp),self.container)
                        self.final=self.directory/('clip.'+self.container);os.replace(tmp,self.final)
                    except asyncio.CancelledError:raise
                    except Exception as exc:self.mux_error=safe_reason(exc)
                else:self.final=self.sources['video'].final
                self.state='done';self.persist();await self.manager.prune();return
            await asyncio.sleep(.25)
    async def pause(self):
        self.paused=True
        for source in self.sources.values():await source.pause()
    async def resume(self):
        if self.cancelled:raise ValueError('Download was cancelled; retry it')
        self.paused=False
        for source in self.sources.values():source.start()
    async def cancel(self):
        self.cancelled=True;self.paused=False
        for source in self.sources.values():await source.cancel()
        if self.task and not self.task.done():self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        self.state='cancelled'
    def public(self):
        self.last=time.monotonic();total=self.total_bytes();known=bool(self.sources) and all(s.total for s in self.sources.values())
        written=sum(s.written for s in self.sources.values());rate=sum(s.rate for s in self.sources.values() if not s.done and not s.paused)
        progress=min(1,written/total) if known and total else None
        prefix=f'/api/clips/sessions/{self.id}'
        return {'id':self.id,'track_id':self.track_id,'video_id':self.video_id,'title':self.title,'artist':self.artist,
                'quality':self.quality,'height':self.height,'container':self.container,'state':'paused' if self.paused and self.state not in ('done','error','cancelled') else self.state,
                'progress':progress,'downloaded':written,'total':total if known else None,'bytes_per_second':round(rate),
                'eta_seconds':round((total-written)/rate) if known and rate>0 else None,
                'error':self.error,'mux_error':self.mux_error,'cached':self.state=='done',
                'offline_ready':bool(self.sources) and all(s.done for s in self.sources.values()),
                'file_ready':bool(self.final and self.final.exists()),'download_url':prefix+'/file' if self.final and self.final.exists() else None,
                'video_url':prefix+'/media/video' if 'video' in self.sources else None,
                'audio_url':prefix+'/media/audio' if 'audio' in self.sources else None,
                'sources':{k:{'downloaded':s.written,'total':s.total,'progress':min(1,s.written/s.total) if s.total else None,'complete':s.done,'mime':s.mime} for k,s in self.sources.items()}}

class Manager:
    def __init__(self,http,identify,resolve):
        self.http=http;self.identify=identify;self.resolve=resolve;self.sessions={}
    async def create(self,track_id,title='',artist='',quality=720,retry=False):
        sid=key_for(track_id,quality);old=self.sessions.get(sid)
        if old and not (retry and (old.state in ('error','cancelled') or old.mux_error)):
            if old.paused:await old.resume()
            return old
        if old:
            await old.cancel()
            for p in old.directory.glob('*.part'):p.unlink(missing_ok=True)
        if len(self.sessions)>=32:
            removable=sorted((s for s in self.sessions.values() if s.state in ('done','error','cancelled') and not any(x.readers for x in s.sources.values())),key=lambda s:s.last)
            if not removable:raise ValueError('Too many clip sessions; cancel unused downloads')
            self.sessions.pop(removable[0].id,None)
        s=Session(self,track_id,title,artist,quality);self.sessions[sid]=s;s.start();return s
    def get(self,sid):
        if not re.fullmatch('[a-f0-9]{24}',sid):return None
        return self.sessions.get(sid)
    async def close(self):
        await asyncio.gather(*(s.cancel() for s in self.sessions.values()),return_exceptions=True)
    async def prune(self):
        # Completed source files + muxed file count toward one disk budget.
        rows=[]
        for p in root().iterdir():
            if not p.is_dir():continue
            session=self.sessions.get(p.name)
            if session and (session.state!='done' or any(s.readers for s in session.sources.values())):continue
            size=sum(f.stat().st_size for f in p.iterdir() if f.is_file())
            rows.append((p.stat().st_mtime,size,p))
        rows.sort(reverse=True);used=0
        for _,size,p in rows:
            used+=size
            if used>CACHE_LIMIT:
                # Never evict current/recent viewers. Old idle sessions can be
                # restored from disk until they exceed this soft budget.
                session=self.sessions.get(p.name)
                if session and time.monotonic()-session.last<60:continue
                self.sessions.pop(p.name,None)
                await asyncio.to_thread(shutil.rmtree,p,True)

def cache_status():
    files=0;size=0
    for p in root().iterdir():
        if not p.is_dir():continue
        try:
            size+=sum(f.stat().st_size for f in p.iterdir() if f.is_file())
            d=json.loads((p/'metadata.json').read_text())
            if all(x.get('complete') for x in d.get('sources',{}).values()) and d.get('sources'):files+=1
        except (OSError,ValueError):pass
    return {'files':files,'bytes':size}

async def clear_cache(manager=None):
    if manager:
        await manager.close();manager.sessions.clear()
    removed=0
    for p in root().iterdir():
        if not p.is_dir():continue
        try:await asyncio.to_thread(shutil.rmtree,p);removed+=1
        except OSError:pass
    return removed
