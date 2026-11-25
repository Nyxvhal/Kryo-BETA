"""Optional AI enhancement jobs (wallpapers and clips) on a separate worker.

The player never imports torch: a worker process (kryonyx.ai_worker) runs in
its own Python environment (".ai-venv", created by setup-ai.bat/.sh). One job
runs at a time; progress is polled; cancelling kills the whole process tree.
Clip results are cached by source identity + options, so a finished upscale
is reused instead of recomputed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path

from . import ai_models, audiovault
from .paths import app_dir, data_dir

CLIP_BUDGET = 12 * 1024 ** 3
PUBLIC_KEYS = ('id', 'kind', 'stage', 'done', 'total', 'fps', 'eta', 'unit', 'error', 'device', 'out_width',
               'out_height', 'out_fps', 'session', 'file', 'original', 'url', 'key', 'created', 'source',
               'options', 'finished', 'elapsed')


def folder():
    path = Path(data_dir()) / 'ai'
    path.mkdir(parents=True, exist_ok=True)
    return path


def clips_dir():
    path = folder() / 'clips'
    path.mkdir(parents=True, exist_ok=True)
    return path


def work_dir():
    path = folder() / 'work'
    path.mkdir(parents=True, exist_ok=True)
    return path


def worker_path():
    """Where `kryonyx.ai_worker` can be imported from by the external Python."""
    frozen = getattr(sys, '_MEIPASS', None)
    if frozen and (Path(frozen) / 'ai_worker' / 'kryonyx' / 'ai_worker.py').is_file():
        return str(Path(frozen) / 'ai_worker')
    return app_dir()


def interpreter():
    custom = os.environ.get('KRYONYX_AI_PYTHON')
    if custom:
        if not Path(custom).is_file():
            raise ValueError('KRYONYX_AI_PYTHON does not exist')
        return custom
    for name in ('.ai-venv', '.karaoke-venv'):
        base = Path(app_dir()) / name
        exe = base / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if exe.exists():
            return str(exe)
    if getattr(sys, 'frozen', False):
        raise ValueError('AI module is not installed')
    return sys.executable


def threads():
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def clip_key(video, audio, options):
    parts = []
    for item in (video, audio):
        if item:
            stat = Path(item).stat(); parts.append(f'{Path(item).name}:{stat.st_size}:{stat.st_mtime_ns}')
    blob = json.dumps({'src': parts, 'opt': options}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def clip_result(key):
    if not key or len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
        return None
    path = clips_dir() / (key + '.mp4')
    return path if path.is_file() else None


def clip_manifest(key):
    try:
        return json.loads((clips_dir() / (key + '.json')).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def clips_for(session_id):
    out = []
    for meta in sorted(clips_dir().glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(meta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if data.get('session') == session_id and clip_result(data.get('key')):
            out.append({**data, 'url': f"/api/ai/result/{data['key']}.mp4"})
    return out


def prune_clips(keep=None):
    files = sorted(clips_dir().glob('*.mp4'), key=lambda p: p.stat().st_mtime, reverse=True)
    used = 0
    for path in files:
        used += path.stat().st_size
        if used > CLIP_BUDGET and path.stem != keep:
            path.unlink(missing_ok=True); (clips_dir() / (path.stem + '.json')).unlink(missing_ok=True)


def advice(info):
    """Device class shown next to the "needs a strong device" warning."""
    if not info.get('installed'):
        return 'missing'
    if info.get('cuda'):
        return 'gpu' if (info.get('vram_gb') or 0) >= 6 else 'gpu-low'
    return 'cpu'


class AIJobs:
    def __init__(self):
        self.items = {}; self.tasks = {}; self.procs = {}; self.requests = {}; self.lock = asyncio.Lock()
        self.downloads = ai_models.Downloads(); self._probe = None; self._probe_at = 0.0

    # ---------------------------------------------------------------- probe
    async def probe(self, force=False):
        if not force and self._probe and time.monotonic() - self._probe_at < 600:
            return self._probe
        info = {'installed': False, 'cuda': False, 'device': 'cpu', 'device_name': '', 'vram_gb': 0,
                'cpu_threads': os.cpu_count() or 1}
        try:
            exe = interpreter()
            env = self._env()
            proc = await asyncio.create_subprocess_exec(exe, '-m', 'kryonyx.ai_worker', '--probe', cwd=worker_path(),
                                                        env=env, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.DEVNULL, **self._spawn())
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), 90)
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait(); raise ValueError('AI module did not respond')
            data = json.loads(out or b'{}')
            info.update({k: v for k, v in data.items() if k in ('python', 'torch', 'cuda', 'device', 'device_name', 'vram_gb', 'cpu_threads', 'numpy', 'pillow', 'error')})
            info['installed'] = bool(data.get('torch') and data.get('numpy') and data.get('pillow'))
            if not info['installed'] and not info.get('error'):
                info['error'] = 'PyTorch, NumPy or Pillow is missing in the AI environment'
        except (ValueError, OSError) as exc:
            info['error'] = str(exc)[:300]
        info['advice'] = advice(info)
        self._probe, self._probe_at = info, time.monotonic()
        return info

    def busy(self):
        return any(not j.get('finished') for j in self.items.values())

    # ------------------------------------------------------------------ jobs
    def submit(self, kind, request, public):
        active = sum(not j.get('finished') for j in self.items.values())
        if active >= 4:
            raise ValueError('At most four AI jobs can be queued')
        if len(self.items) >= 40:
            for key in [k for k, v in self.items.items() if v.get('finished')][:20]:
                self.items.pop(key, None)
        jid = uuid.uuid4().hex
        item = {'id': jid, 'kind': kind, 'stage': 'queued', 'done': 0, 'total': 0, 'created': time.time(),
                'finished': False, **public}
        self.items[jid] = item; self.requests[jid] = request
        self.tasks[jid] = asyncio.create_task(self._run(jid, request))
        return self.status(jid)

    def status(self, jid):
        item = self.items.get(jid)
        if item is None:
            return None
        out = {k: v for k, v in item.items() if k in PUBLIC_KEYS}
        if item.get('started'):
            out['elapsed'] = round((item.get('ended') or time.time()) - item['started'])
        return out

    def list(self):
        return [self.status(j) for j in sorted(self.items, key=lambda k: self.items[k]['created'], reverse=True)]

    def _env(self):
        env = os.environ.copy()
        env['PYTHONPATH'] = worker_path() + os.pathsep + env.get('PYTHONPATH', '')
        env['OMP_NUM_THREADS'] = str(threads()); env['MKL_NUM_THREADS'] = str(threads())
        env['PYTHONIOENCODING'] = 'utf-8'
        return env

    @staticmethod
    def _spawn():
        # Own process group: cancelling kills ffmpeg children too; no console window on Windows.
        return {'creationflags': 0x08000200} if os.name == 'nt' else {'start_new_session': True}

    async def _run(self, jid, request):
        item = self.items[jid]; acquired = False; proc = None
        try:
            await self.lock.acquire(); acquired = True
            if item['stage'] == 'cancelled':
                return
            item['stage'] = 'starting'; item['started'] = time.time()
            proc = await asyncio.create_subprocess_exec(interpreter(), '-m', 'kryonyx.ai_worker', cwd=worker_path(),
                                                        env=self._env(), stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                                                        **self._spawn())
            self.procs[jid] = proc
            payload = {k: v for k, v in request.items() if not k.startswith('_')}
            payload.setdefault('threads', threads())
            proc.stdin.write((json.dumps(payload) + '\n').encode()); await proc.stdin.drain(); proc.stdin.close()
            result = None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                try:
                    info = json.loads(raw)
                except (ValueError, UnicodeError):
                    continue
                for key in ('stage', 'done', 'total', 'fps', 'eta', 'unit', 'error', 'device', 'out_width', 'out_height', 'out_fps', 'source'):
                    if key in info and not (key == 'stage' and info[key] == 'done'):
                        item[key] = info[key]
                if info.get('result'):
                    result = info
            code = await proc.wait()
            if code or not result:
                item['stage'] = 'error'; item.setdefault('error', 'AI processing failed')
                if not item.get('error'): item['error'] = 'AI processing failed'
                return
            await self._finish(item, request, result)
            item['stage'] = 'done'
        except asyncio.CancelledError:
            item['stage'] = 'cancelled'
        except Exception as exc:
            item['stage'] = 'error'; item['error'] = str(exc)[:400] or 'AI processing failed'
        finally:
            try:
                await asyncio.shield(self._kill(self.procs.pop(jid, None)))
            finally:
                self._settle(jid)
                if acquired:
                    self.lock.release()

    def _settle(self, jid):
        """Final bookkeeping; also runs for a job cancelled before its task ever started."""
        item = self.items.get(jid); request = self.requests.pop(jid, None)
        self.tasks.pop(jid, None)
        if item is None or item.get('finished'):
            return
        if item['stage'] not in ('done', 'error'):
            item['stage'] = 'cancelled'
        for leftover in (request or {}).get('_cleanup', []):
            try: Path(leftover).unlink(missing_ok=True)
            except OSError: pass
        if item['stage'] != 'done' and (request or {}).get('output'):
            for path in (request['output'], request['output'] + '.part', request['output'] + '.part.mp4'):
                try: Path(path).unlink(missing_ok=True)
                except OSError: pass
        item['ended'] = time.time(); item['finished'] = True

    async def _finish(self, item, request, result):
        output = Path(result['result']).resolve()
        if output != Path(request['output']).resolve() or not output.is_file():
            raise ValueError('AI worker returned an unexpected file')
        if item['kind'] == 'wallpaper':
            from . import wallpaper
            body = await audiovault.run_blocking_owned(output.read_bytes)
            item['file'] = await audiovault.run_blocking_owned(wallpaper.store, body)
            output.unlink(missing_ok=True)
        else:
            key = request['_key']
            manifest = {'key': key, 'session': request['_session'], 'options': request['_options'],
                        'width': result.get('width'), 'height': result.get('height'), 'fps': result.get('fps'),
                        'frames': result.get('frames'), 'created': time.time(), 'size': output.stat().st_size}
            tmp = clips_dir() / (key + '.json.tmp')
            tmp.write_text(json.dumps(manifest), encoding='utf-8'); os.replace(tmp, clips_dir() / (key + '.json'))
            item['url'] = f'/api/ai/result/{key}.mp4'; item['key'] = key
            await audiovault.run_blocking_owned(prune_clips, key)

    async def _kill(self, proc):
        if not proc or proc.returncode is not None:
            return
        try:
            if os.name == 'nt':
                killer = await asyncio.create_subprocess_exec('taskkill', '/PID', str(proc.pid), '/T', '/F',
                                                              stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await killer.wait()
                if proc.returncode is None: proc.kill()
            else:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
        except OSError:
            if proc.returncode is None: proc.kill()
        await proc.wait()

    async def cancel(self, jid):
        task = self.tasks.get(jid)
        if task:
            self.items[jid]['stage'] = 'cancelled'
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
            self._settle(jid)
        return self.status(jid)

    async def close(self):
        for jid in list(self.tasks):   # queued jobs must not start while the running one is stopped
            self.items[jid]['stage'] = 'cancelled'
        for jid in list(self.tasks):
            await self.cancel(jid)
        if self.downloads.task and not self.downloads.task.done():
            self.downloads.task.cancel()
            await asyncio.gather(self.downloads.task, return_exceptions=True)
        for model_id in self.downloads.queue:
            if self.downloads.state.get(model_id, {}).get('stage') == 'queued':
                self.downloads.state[model_id]['stage'] = 'cancelled'
        self.downloads.queue.clear()
