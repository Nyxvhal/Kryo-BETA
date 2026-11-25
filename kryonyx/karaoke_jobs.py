"""Local ML-job management and content-addressed lyric storage.

The existing aiohttp server owns the API. Workers have no listening ports.
Only one worker runs at a time, on an optional separate Python environment.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import signal
import uuid
from .paths import data_dir, app_dir
from . import lyrics, audiocache, karaoke_quality, audiovault
from .karaoke_worker import atomic_json, digest, MODELS, LANGUAGES

MAX_AUDIO = 256 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024


def folder():
    path=Path(data_dir())/'karaoke';path.mkdir(parents=True,exist_ok=True);return path


def interpreter():
    custom=os.environ.get('KRYONYX_KARAOKE_PYTHON')
    if custom:
        if not Path(custom).is_file():raise ValueError('KRYONYX_KARAOKE_PYTHON does not exist')
        return custom
    base=Path(app_dir())/'.karaoke-venv'
    exe=base/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if exe.exists():return str(exe)
    if getattr(sys,'frozen',False):raise ValueError('Configure a separate Python worker for the EXE build')
    return sys.executable


def binding(track):
    return folder()/'bindings'/(hashlib.sha256(track.encode()).hexdigest()+'.json')


def save_track(track,doc):
    if not track or len(track)>2048:raise ValueError('Track id is required')
    doc=lyrics.karaoke_document(doc)
    doc['quality']=karaoke_quality.assess(doc)
    previous=binding(track)
    if previous.exists():
        try: atomic_json(previous.with_suffix('.previous.json'),json.loads(previous.read_text(encoding='utf-8')))
        except (ValueError,OSError): pass
    atomic_json(previous,doc)
    return doc


def load_track(track):
    path=binding(track)
    if not track or not path.exists():return None
    try:
        doc=lyrics.karaoke_document(json.loads(path.read_text(encoding='utf-8')))
        bound=doc.get('binding',{})
        if bound.get('source') in ('audio-cache','audio-vault'):
            audio=audiocache.find(track)
            if audio and audio.startswith('vault:'):
                if audiovault.fingerprint(audio)!=doc.get('source_fingerprint',{}).get('audio_sha256'):return None
            elif audio:
                stat=Path(audio).stat();identity=[stat.st_size,stat.st_mtime_ns]
                if bound.get('stat')!=identity:
                    if digest(audio)!=doc.get('source_fingerprint',{}).get('audio_sha256'):return None
                    bound['stat']=identity;atomic_json(path,doc)
        return doc
    except (OSError,ValueError):return None


class Jobs:
    def __init__(self):
        self.items={};self.tasks={};self.processes={};self.owned={};self.lock=asyncio.Lock()

    def submit(self,request,owned=False):
        # Bound retained metadata; completed results live on disk, not RAM.
        active=sum(j['stage'] not in ('done','error','cancelled') for j in self.items.values())
        if active>=8:raise ValueError('At most eight karaoke jobs can be queued')
        if len(self.items)>=64:
            for key in list(self.items):
                if key not in self.tasks:self.items.pop(key,None)
                if len(self.items)<48:break
        jid=uuid.uuid4().hex
        self.items[jid]={'id':jid,'stage':'queued','track_id':request.get('track_id',''),'finished':False}
        if owned:self.owned[jid]=request['audio']
        self.tasks[jid]=asyncio.create_task(self.run(jid,request,owned))
        return dict(self.items[jid])

    async def run(self,jid,request,owned):
        item=self.items[jid]
        acquired=False
        try:
            await self.lock.acquire()
            acquired=True
            if item['stage']=='cancelled':return
            item['stage']='starting'
            env=os.environ.copy();env['PYTHONPATH']=app_dir()+os.pathsep+env.get('PYTHONPATH','')
            # Background processing is bounded, never executed on the event loop.
            env['OMP_NUM_THREADS']='2';env['MKL_NUM_THREADS']='2'
            proc=await asyncio.create_subprocess_exec(interpreter(),'-m','kryonyx.karaoke_worker',
                   cwd=app_dir(),env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
                   stderr=asyncio.subprocess.DEVNULL,**({'creationflags':0x08000200} if os.name=='nt' else {'start_new_session':True}))
            self.processes[jid]=proc
            proc.stdin.write((json.dumps({**request,'cache':str(folder()/'cache')})+'\n').encode());await proc.stdin.drain();proc.stdin.close()
            async def receive():
                while True:
                    raw=await proc.stdout.readline()
                    if not raw:break
                    try:info=json.loads(raw)
                    except (ValueError,UnicodeError):continue
                    item.update({k:v for k,v in info.items() if k in ('stage','error','cached','key','engine','device','processed_seconds','total_seconds','reason') and not (k=='stage' and v=='done')})
                    if info.get('result'):
                        result=Path(info['result']).resolve(); cache=(folder()/'cache').resolve()
                        if result.parent!=cache:raise ValueError('Worker result is outside the cache')
                        doc=lyrics.karaoke_document(json.loads(result.read_text(encoding='utf-8')))
                        item['quality']=karaoke_quality.assess(doc)
                        if request.get('track_id') and request.get('auto_bind', False):
                            if request.get('_vault_audio'):
                                doc['binding']={'source':'audio-vault'}
                            elif not owned:
                                stat=Path(request['audio']).stat()
                                doc['binding']={'source':'audio-cache','stat':[stat.st_size,stat.st_mtime_ns]}
                            await audiovault.run_blocking_owned(save_track,request['track_id'],doc)
                        item['result']=str(result);item['stage']='done'
            await asyncio.wait_for(receive(),timeout=4*3600)
            code=await proc.wait()
            if code or 'result' not in item:
                item['stage']='error';item.setdefault('error','Processing failed; LRC/plain lyrics remain available')
        except asyncio.CancelledError:
            item['stage']='cancelled'
        except Exception as e:
            item['stage']='error';item['error']=str(e)[:500]
        finally:
            proc=self.processes.pop(jid,None)
            if proc and proc.returncode is None:
                try:
                    if os.name=='nt':
                        killer=await asyncio.create_subprocess_exec('taskkill','/PID',str(proc.pid),'/T','/F',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
                        await killer.wait()
                        if killer.returncode and proc.returncode is None:proc.kill()
                    else:
                        try:os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                except OSError:
                    if proc.returncode is None:proc.kill()
                await proc.wait()
            owned_path=self.owned.pop(jid,None)
            if owned_path:
                try:Path(owned_path).unlink(missing_ok=True)
                except OSError:pass
            item["finished"]=True
            self.tasks.pop(jid,None)
            if acquired:self.lock.release()

    def status(self,jid):
        item=self.items.get(jid)
        if item is None:return None
        result={k:v for k,v in item.items() if k!='result'}
        if not item.get('finished') and item['stage'] in ('done','error','cancelled'):result['stage']='finishing'
        return result

    async def cancel(self,jid):
        task=self.tasks.get(jid)
        if task:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            self.tasks.pop(jid,None)
            self.items[jid]['stage']='cancelled';self.items[jid]['finished']=True
            owned_path=self.owned.pop(jid,None)
            if owned_path:Path(owned_path).unlink(missing_ok=True)
        return self.status(jid)

    async def close(self):
        # Cancel queued and running jobs together, before releasing the lock.
        await asyncio.gather(*(self.cancel(jid) for jid in list(self.tasks)))

    async def hardware(self):
        env=os.environ.copy();env['PYTHONPATH']=app_dir()+os.pathsep+env.get('PYTHONPATH','')
        try:
            p=await asyncio.create_subprocess_exec(interpreter(),'-m','kryonyx.karaoke_worker','--probe',
                 cwd=app_dir(),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
            try:out,_=await asyncio.wait_for(p.communicate(),30)
            except asyncio.TimeoutError:p.kill();await p.wait();raise
            if p.returncode:raise ValueError('Worker probe failed')
            return json.loads(out)
        except Exception as e:return {'cpu':True,'cuda':False,'error':str(e),'faster_whisper':False,'stable_ts':False}
