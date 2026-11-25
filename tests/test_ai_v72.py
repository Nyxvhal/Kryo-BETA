"""v72 optional AI module: verified model downloads, the separate worker process and the HTTP API.

Default tests need no torch, no GPU and no network: model downloads use a fake HTTPS session and the
worker is replaced by a small fake process that speaks the same JSON-lines protocol. Set
KRYONYX_AI_TEST_PYTHON to a Python with torch (e.g. .ai-venv) to also run the real worker on CPU with
randomly initialised networks (pipeline check, not a quality or speed test)."""
import asyncio, hashlib, io, json, os, shutil, subprocess, sys, tempfile, time, unittest, zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yarl
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from kryonyx import ai_jobs, ai_models, ai_worker, audiovault, clipcache, server, wallpaper

ROOT = Path(__file__).resolve().parents[1]
POSIX = os.name != 'nt'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tiny_spec(blob, **extra):
    return {'file': 'tiny.pth', 'kind': 'upscale', 'arch': 'compact', 'num_conv': 2, 'title': 'Tiny', 'use': 'video',
            'license': 'MIT', 'url': 'https://models.test/tiny.pth', 'size': len(blob), 'sha256': sha(blob), **extra}


class Sandbox:
    """Temporary data folder for every AI path (models, work files, clip results, wallpapers)."""

    def start_sandbox(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.patches = [patch.object(ai_models, 'data_dir', return_value=self.tmp.name),
                        patch.object(ai_jobs, 'data_dir', return_value=self.tmp.name),
                        patch.object(wallpaper, 'cache_dir', return_value=self.tmp.name),
                        patch.object(audiovault, 'cache_dir', return_value=self.tmp.name)]
        for p in self.patches:
            p.start()
        ai_models._verified.clear()

    def stop_sandbox(self):
        for p in reversed(self.patches):
            p.stop()
        ai_models._verified.clear(); self.tmp.cleanup()


# ---------------------------------------------------------------------------------------------- registry
class Registry(Sandbox, unittest.TestCase):
    def setUp(self):
        self.start_sandbox()

    def tearDown(self):
        self.stop_sandbox()

    def test_every_model_is_pinned_to_https_size_and_digest(self):
        for model_id, spec in ai_models.MODELS.items():
            self.assertTrue(spec['url'].startswith('https://'), model_id)
            self.assertGreater(spec['size'], 100_000, model_id)
            self.assertRegex(spec['sha256'], r'^[0-9a-f]{64}$', model_id)
            self.assertIn(spec['arch'], ('compact', 'rrdb', 'ifnet'), model_id)
            if spec.get('member'):
                self.assertRegex(spec['member_sha256'], r'^[0-9a-f]{64}$')
                self.assertGreater(spec['member_size'], 100_000)
        for feature, ids in ai_models.NEEDS.items():
            self.assertTrue(ids and all(m in ai_models.MODELS for m in ids), feature)
        self.assertEqual(set(server._AI_WALL_MODELS72.values()) | set(server._AI_CLIP_MODELS72.values()),
                         {m for m in ai_models.MODELS if ai_models.MODELS[m]['kind'] == 'upscale'})

    def test_present_requires_the_exact_size_and_digest(self):
        blob = os.urandom(4096)
        with patch.dict(ai_models.MODELS, {'tiny': tiny_spec(blob)}):
            target = ai_models.path('tiny')
            self.assertFalse(ai_models.present('tiny'))
            target.write_bytes(blob[:-1])
            self.assertFalse(ai_models.present('tiny', verify=False))
            target.write_bytes(bytes(4096))                     # right size, wrong contents
            self.assertTrue(ai_models.present('tiny', verify=False))
            self.assertFalse(ai_models.present('tiny'))
            target.write_bytes(blob)
            self.assertTrue(ai_models.present('tiny'))
            self.assertTrue(ai_models.present('tiny'))          # cached by stat
            time.sleep(.02); target.write_bytes(bytes(4096))    # replaced later: re-verified
            os.utime(target, ns=(time.time_ns(), time.time_ns() + 5_000_000))
            self.assertFalse(ai_models.present('tiny'))

    def test_summary_and_missing_follow_the_files(self):
        blob = os.urandom(512)
        with patch.dict(ai_models.MODELS, {'tiny': tiny_spec(blob)}), \
                patch.dict(ai_models.NEEDS, {'clip:tiny': ['tiny', 'rife']}):
            self.assertEqual(ai_models.missing('clip:tiny'), ['tiny', 'rife'])
            ai_models.path('tiny').write_bytes(blob)
            self.assertEqual(ai_models.missing('clip:tiny'), ['rife'])
            info = ai_models.summary()
            self.assertEqual(set(info), set(ai_models.MODELS))
            self.assertTrue(info['tiny']['present'])
            self.assertFalse(info['rife']['present'])
            self.assertEqual(ai_models.missing('unknown'), [])


# ---------------------------------------------------------------------------------------------- downloads
class FakeResponse:
    def __init__(self, body, status=200, url='https://models.test/file', chunk=700):
        self.body, self.status, self.url, self.chunk = body, status, yarl.URL(url), chunk
        self.content = self

    def iter_chunked(self, _size):
        async def gen():
            for i in range(0, len(self.body), self.chunk):
                yield self.body[i:i + self.chunk]
        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def get(self, url, **kw):
        self.calls.append(url)
        return self.responses[url]


class Downloads(Sandbox, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.start_sandbox()

    async def asyncTearDown(self):
        self.stop_sandbox()

    async def fetch(self, specs, responses, ids=None):
        session = FakeSession(responses)

        async def factory():
            return session
        with patch.dict(ai_models.MODELS, specs):
            d = ai_models.Downloads()
            d.start(ids or list(specs), factory)
            if d.task:
                await d.task
            return d.public(), session, {m: ai_models.present(m) for m in specs}

    def leftovers(self):
        return sorted(p.name for p in ai_models.folder().iterdir() if p.suffix in ('.download', '.part'))

    async def test_verified_download_is_installed(self):
        blob = os.urandom(5000)
        state, session, present = await self.fetch({'tiny': tiny_spec(blob)}, {'https://models.test/tiny.pth': FakeResponse(blob)})
        self.assertEqual(state['tiny']['stage'], 'done')
        self.assertEqual(state['tiny']['done'], 5000)
        self.assertTrue(present['tiny'])
        self.assertEqual(self.leftovers(), [])
        # Already installed: nothing is downloaded again.
        state, session, _ = await self.fetch({'tiny': tiny_spec(blob)}, {})
        self.assertEqual((state['tiny']['stage'], session.calls), ('done', []))

    async def test_substituted_file_is_discarded(self):
        blob = os.urandom(5000)
        state, _, present = await self.fetch({'tiny': tiny_spec(blob)},
                                             {'https://models.test/tiny.pth': FakeResponse(os.urandom(5000))})
        self.assertEqual(state['tiny']['stage'], 'error')
        self.assertIn('checksum', state['tiny']['error'])
        self.assertFalse(present['tiny'])
        self.assertFalse(ai_models.path('tiny').exists() if 'tiny' in ai_models.MODELS else False)
        self.assertEqual(self.leftovers(), [])

    async def test_oversized_redirected_and_failed_downloads_are_refused(self):
        blob = os.urandom(3000)
        cases = {'big': (FakeResponse(blob + b'x'), 'larger than the published size'),
                 'http': (FakeResponse(blob, url='http://mirror.test/tiny.pth'), 'non-HTTPS'),
                 'gone': (FakeResponse(b'', status=404), 'HTTP 404')}
        for name, (response, message) in cases.items():
            spec = tiny_spec(blob, file=name + '.pth', url='https://models.test/' + name)
            state, _, present = await self.fetch({name: spec}, {spec['url']: response})
            self.assertEqual(state[name]['stage'], 'error', name)
            self.assertIn(message, state[name]['error'], name)
            self.assertFalse(present[name], name)
            self.assertFalse((ai_models.folder() / spec['file']).exists(), name)
        self.assertEqual(self.leftovers(), [])

    def archive(self, member, extra=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('log/flownet.pkl', member)
            for name, data in (extra or {}).items():
                zf.writestr(name, data)
        return buf.getvalue()

    async def test_archive_member_is_extracted_alone_and_verified(self):
        member = os.urandom(6000)
        packed = self.archive(member, {'../escape.txt': b'x', 'log/other.bin': b'y'})
        spec = tiny_spec(packed, file='flow.pkl', kind='interpolate', arch='ifnet', url='https://models.test/log.zip',
                         member='log/flownet.pkl', member_size=len(member), member_sha256=sha(member))
        state, _, present = await self.fetch({'flow': spec}, {spec['url']: FakeResponse(packed)})
        self.assertEqual(state['flow']['stage'], 'done')
        self.assertTrue(present['flow'])
        self.assertEqual((ai_models.folder() / 'flow.pkl').read_bytes(), member)
        everything = sorted(p.name for p in self.root.rglob('*') if p.is_file())
        self.assertEqual(everything, ['flow.pkl'])            # nothing else from the archive, no temp files

    async def test_unexpected_archive_contents_are_refused(self):
        member = os.urandom(6000)
        for name, packed, size in (('size', self.archive(member), len(member) + 1),
                                   ('name', self.archive(member, {'log/x': b'1'}), len(member))):
            spec = tiny_spec(packed, file=name + '.pkl', url='https://models.test/' + name,
                             member='log/flownet.pkl' if name == 'size' else 'log/missing.pkl',
                             member_size=size, member_sha256=sha(member))
            state, _, present = await self.fetch({name: spec}, {spec['url']: FakeResponse(packed)})
            self.assertEqual(state[name]['stage'], 'error', name)
            self.assertIn('Unexpected model archive contents', state[name]['error'])
            self.assertFalse(present[name])
        self.assertEqual(sorted(p.name for p in self.root.rglob('*') if p.is_file()), [])

    async def test_unknown_ids_are_rejected_and_queued_ids_are_not_repeated(self):
        d = ai_models.Downloads()
        with self.assertRaises(ValueError):
            d.start(['../../etc/passwd'], None)
        blob = os.urandom(800); gate = asyncio.Event()

        class Slow(FakeResponse):
            async def __aenter__(self):
                await gate.wait(); return self
        session = FakeSession({'https://models.test/tiny.pth': Slow(blob)})

        async def factory():
            return session
        with patch.dict(ai_models.MODELS, {'tiny': tiny_spec(blob)}):
            d.start(['tiny'], factory); await asyncio.sleep(.05)
            d.start(['tiny', 'nope'], factory)
            self.assertEqual(d.queue, [])
            gate.set(); await d.task
            self.assertEqual(session.calls, ['https://models.test/tiny.pth'])
            self.assertEqual(d.public()['tiny']['stage'], 'done')


# ---------------------------------------------------------------------------------------------- worker helpers
class WorkerHelpers(unittest.TestCase):
    def test_frame_rates(self):
        self.assertEqual(ai_worker.rate_expr(29.97), '30000/1001')
        self.assertEqual(ai_worker.rate_expr(24.0), '24')
        self.assertEqual(ai_worker.rate_expr(12.5), '12.5')
        self.assertEqual(ai_worker.double_rate('30000/1001'), '60000/1001')
        self.assertEqual(ai_worker.double_rate('24'), '48')
        self.assertEqual(ai_worker.double_rate('12.5'), '25')
        self.assertEqual(ai_worker.rate_value('60000/1001'), 59.94)
        self.assertEqual(ai_worker.rate_value('48'), 48.0)
        self.assertIsNone(ai_worker.rate_value('1/0'))
        self.assertIsNone(ai_worker.rate_value('fast'))

    def test_video_info_reads_size_rate_rotation_duration_audio(self):
        text = ('  Duration: 00:03:21.45, start: 0.000000, bitrate: 4800 kb/s\n'
                '  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709, progressive), '
                '1920x1080 [SAR 1:1 DAR 16:9], 4500 kb/s, 29.97 fps, 29.97 tbr, 30k tbn (default)\n'
                '      Side data:\n        displaymatrix: rotation of -90.00 degrees\n'
                '  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 128 kb/s\n')
        with patch.object(ai_worker.subprocess, 'run', return_value=SimpleNamespace(stderr=text, returncode=1)):
            info = ai_worker.video_info('ffmpeg', 'clip.mp4')
        self.assertEqual(info, {'width': 1080, 'height': 1920, 'fps': 29.97, 'duration': 201.45, 'audio': True})
        with patch.object(ai_worker.subprocess, 'run', return_value=SimpleNamespace(stderr='Stream #0:0: Audio: opus', returncode=1)):
            with self.assertRaises(RuntimeError):
                ai_worker.video_info('ffmpeg', 'song.webm')

    def run_worker(self, request, *args):
        proc = subprocess.run([sys.executable, '-m', 'kryonyx.ai_worker', *args], cwd=ROOT, input=json.dumps(request) + '\n',
                              capture_output=True, text=True, timeout=60)
        return proc.returncode, [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]

    def test_worker_protocol_reports_errors_as_json(self):
        code, lines = self.run_worker({'mode': 'nonsense'})
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1], {'stage': 'error', 'error': 'Unknown AI job'})
        code, lines = self.run_worker({}, '--probe')
        self.assertEqual(code, 0)
        self.assertTrue({'python', 'torch', 'cuda', 'device', 'numpy', 'pillow'} <= set(lines[0]))

    def test_out_of_memory_is_explained(self):
        out = io.StringIO()
        with patch.object(sys, 'stdin', io.StringIO('{"mode": "image"}\n')), patch.object(sys, 'stdout', out), \
                patch.object(sys, 'argv', ['ai_worker']), \
                patch.object(ai_worker, 'run_image', side_effect=RuntimeError('CUDA out of memory. Tried to allocate 2 GiB')):
            self.assertEqual(ai_worker.main(), 1)
        self.assertEqual(json.loads(out.getvalue().splitlines()[-1])['error'],
                         'Not enough memory for this resolution; choose a lower target')


# ---------------------------------------------------------------------------------------------- jobs
FAKE_WORKER = r'''
import json, os, sys, time
mode = os.environ.get('FAKE_AI72', 'ok')
def say(**m): print(json.dumps(m), flush=True)
if '--probe' in sys.argv:
    say(python='3', torch=None if mode == 'missing' else '2.0', numpy=True, pillow=True,
        cuda=mode == 'gpu', device='cuda' if mode == 'gpu' else 'cpu', vram_gb=4 if mode == 'gpu' else 0)
    sys.exit(0)
if os.environ.get('FAKE_AI72_PIDS'):
    with open(os.environ['FAKE_AI72_PIDS'], 'a') as fh: fh.write('%d\n' % os.getpid())
req = json.loads(sys.stdin.readline())
if os.environ.get('FAKE_AI72_LOG'):
    with open(os.environ['FAKE_AI72_LOG'], 'a') as fh: fh.write(json.dumps(req) + '\n')
say(stage='loading', device='cpu')
print('not json', flush=True)
say(stage='processing', done=1, total=4, unit='tiles')
if mode == 'hang':
    open(req['output'] + '.part', 'w').close(); time.sleep(60)
if mode == 'fail':
    say(stage='error', error='Not enough memory for this resolution; choose a lower target'); sys.exit(1)
if mode == 'wrongfile':
    say(stage='done', result=req['output'] + '.elsewhere'); sys.exit(0)
if req['mode'] == 'image':
    from PIL import Image
    Image.new('RGB', (req['out_w'], req['out_h']), (20, 40, 60)).save(req['output'], 'JPEG')
    say(stage='done', result=req['output'], width=req['out_w'], height=req['out_h'])
else:
    with open(req['output'], 'wb') as fh: fh.write(b'\0\0\0\x18ftypmp42' + bytes(64))
    say(stage='done', result=req['output'], frames=96, width=384, height=216, fps=24.0)
'''


class FakeEngine(Sandbox):
    def start_engine(self, mode='ok'):
        self.start_sandbox()
        script = self.root / 'fake_worker.py'; script.write_text(FAKE_WORKER, encoding='utf-8')
        wrapper = self.root / 'fake-python'
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding='utf-8'); wrapper.chmod(0o755)
        self.log = self.root / 'requests.jsonl'; self.pids = self.root / 'pids.txt'
        self.env = patch.dict(os.environ, {'KRYONYX_AI_PYTHON': str(wrapper), 'FAKE_AI72': mode, 'FAKE_AI72_LOG': str(self.log),
                                           'FAKE_AI72_PIDS': str(self.pids)})
        self.env.start()

    def running_workers(self):
        alive = []
        for pid in (int(x) for x in (self.pids.read_text().split() if self.pids.exists() else [])):
            try:
                state = Path(f'/proc/{pid}/status').read_text()
            except OSError:
                continue
            if '\nState:\tZ' not in state:
                alive.append(pid)
        return alive

    def stop_engine(self):
        self.env.stop(); self.stop_sandbox()

    def requests(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def install_tiny(self, *ids):
        blob = os.urandom(2048)
        specs = {m: {**ai_models.MODELS[m], 'size': len(blob), 'sha256': sha(blob), 'member_size': None, 'member_sha256': None}
                 for m in ids}
        self.models = patch.dict(ai_models.MODELS, specs); self.models.start()
        for m in ids:
            ai_models.path(m).write_bytes(blob)

    async def until_finished(self, status, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            item = await status()
            if item and item.get('finished'):
                return item
            await asyncio.sleep(.05)
        raise AssertionError('AI job did not finish')


@unittest.skipUnless(POSIX, 'fake worker uses a POSIX shell wrapper')
class Jobs(FakeEngine, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.start_engine(); self.jobs = ai_jobs.AIJobs()

    async def asyncTearDown(self):
        await self.jobs.close(); self.stop_engine()

    def image_job(self):
        src = self.root / 'in.png'; Image.new('RGB', (64, 48), 'red').save(src)
        return {'mode': 'image', 'input': str(src), 'output': str(ai_jobs.work_dir() / 'out.jpg'), 'out_w': 256, 'out_h': 192,
                'upscale': {'path': 'x', 'arch': 'compact'}, '_cleanup': [str(src)]}

    async def test_probe_reads_the_engine_and_device_class(self):
        info = await self.jobs.probe(force=True)
        self.assertEqual((info['installed'], info['advice'], info['torch']), (True, 'cpu', '2.0'))
        previous = 'cpu'
        for mode, advice in (('gpu', 'gpu-low'), ('missing', 'missing')):
            os.environ['FAKE_AI72'] = mode
            self.assertEqual((await self.jobs.probe())['advice'], previous)     # cached for ten minutes
            info = await self.jobs.probe(force=True)
            self.assertEqual(info['advice'], advice); previous = advice
        self.assertIn('PyTorch', info['error'])
        os.environ['KRYONYX_AI_PYTHON'] = str(self.root / 'nowhere' / 'python')
        info = await self.jobs.probe(force=True)
        self.assertEqual((info['installed'], info['advice']), (False, 'missing'))
        self.assertEqual(ai_jobs.advice({'installed': True, 'cuda': True, 'vram_gb': 8}), 'gpu')

    async def test_wallpaper_job_runs_in_the_worker_and_is_stored(self):
        job = self.image_job()
        first = self.jobs.submit('wallpaper', job, {'original': 'local'})
        self.assertEqual(first['stage'], 'queued')
        self.assertTrue(self.jobs.busy())
        done = await self.until_finished(lambda: asyncio.sleep(0, self.jobs.status(first['id'])))
        self.assertEqual(done['stage'], 'done', done)
        self.assertRegex(done['file'], r'^[0-9a-f]{64}\.jpg$')
        with Image.open(wallpaper.directory() / done['file']) as im:
            self.assertEqual(im.size, (256, 192))
        self.assertFalse(Path(job['output']).exists())       # moved into the wallpaper store
        self.assertFalse(Path(job['input']).exists())        # owned upload cleaned up
        self.assertFalse(self.jobs.busy())
        sent = self.requests()[0]
        self.assertFalse([k for k in sent if k.startswith('_')])
        self.assertEqual(sent['threads'], ai_jobs.threads())
        self.assertEqual(done['device'], 'cpu')

    async def test_worker_errors_and_unexpected_results_are_reported(self):
        for mode, message in (('fail', 'Not enough memory'), ('wrongfile', 'unexpected file')):
            os.environ['FAKE_AI72'] = mode
            job = self.image_job()
            item = self.jobs.submit('wallpaper', job, {})
            done = await self.until_finished(lambda: asyncio.sleep(0, self.jobs.status(item['id'])))
            self.assertEqual(done['stage'], 'error', mode)
            self.assertIn(message, done['error'], mode)
            self.assertFalse(Path(job['output']).exists())

    async def test_cancel_kills_the_worker_and_removes_partial_output(self):
        os.environ['FAKE_AI72'] = 'hang'
        job = self.image_job()
        item = self.jobs.submit('wallpaper', job, {})
        second = self.jobs.submit('wallpaper', {**self.image_job(), 'output': str(ai_jobs.work_dir() / 'b.jpg')}, {})
        deadline = time.monotonic() + 15
        while self.jobs.status(item['id'])['stage'] != 'processing' and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        self.assertEqual(self.jobs.status(second['id'])['stage'], 'queued')     # one job at a time
        proc = self.jobs.procs[item['id']]
        cancelled = await self.jobs.cancel(item['id'])
        self.assertEqual((cancelled['stage'], cancelled['finished']), ('cancelled', True))
        self.assertIsNotNone(proc.returncode)
        self.assertFalse(Path(job['output'] + '.part').exists())
        await self.jobs.cancel(second['id'])
        self.assertEqual(self.jobs.status(second['id'])['stage'], 'cancelled')
        self.assertIsNone(await self.jobs.cancel('missing'))
        self.assertEqual(self.running_workers(), [])

    async def test_queue_is_bounded_and_closing_stops_everything(self):
        os.environ['FAKE_AI72'] = 'hang'
        for wait in (False, True):                 # closing right after submitting, and while a job is running
            jobs = self.jobs if not wait else ai_jobs.AIJobs()
            uploads = []
            for _ in range(4):
                job = self.image_job(); upload = self.root / f'upload{len(uploads)}{wait}.img'
                upload.write_bytes(b'x'); job['_cleanup'] = [str(upload)]; uploads.append(upload)
                jobs.submit('wallpaper', job, {})
            with self.assertRaises(ValueError):
                jobs.submit('wallpaper', self.image_job(), {})
            if wait:
                deadline = time.monotonic() + 15
                while not jobs.procs and time.monotonic() < deadline:
                    await asyncio.sleep(.05)
                self.assertTrue(jobs.procs)
            await jobs.close()
            self.assertEqual({j['stage'] for j in jobs.list()}, {'cancelled'})
            self.assertTrue(all(j['finished'] for j in jobs.list()))
            self.assertFalse(jobs.busy())
            self.assertEqual((jobs.tasks, jobs.procs, jobs.requests), ({}, {}, {}))
            self.assertFalse([u for u in uploads if u.exists()])
            await asyncio.sleep(.2)
            self.assertEqual(self.running_workers(), [])


class ClipStore(Sandbox, unittest.TestCase):
    def setUp(self):
        self.start_sandbox()

    def tearDown(self):
        self.stop_sandbox()

    def test_clip_key_tracks_source_files_and_options(self):
        video = self.root / 'v.mp4'; video.write_bytes(b'1' * 10)
        a = ai_jobs.clip_key(str(video), None, {'height': 720})
        self.assertEqual(a, ai_jobs.clip_key(str(video), None, {'height': 720}))
        self.assertNotEqual(a, ai_jobs.clip_key(str(video), None, {'height': 1080}))
        video.write_bytes(b'1' * 11)
        self.assertNotEqual(a, ai_jobs.clip_key(str(video), None, {'height': 720}))
        self.assertRegex(a, r'^[0-9a-f]{32}$')

    def test_results_are_only_served_for_well_formed_keys(self):
        key = 'ab' * 16
        (ai_jobs.clips_dir() / (key + '.mp4')).write_bytes(b'x')
        self.assertEqual(ai_jobs.clip_result(key), ai_jobs.clips_dir() / (key + '.mp4'))
        for bad in ('../' + key[3:], key.upper(), key[:-1], '', None, key + '0'):
            self.assertIsNone(ai_jobs.clip_result(bad), bad)

    def test_clips_for_session_and_budget(self):
        made = []
        for i, session in enumerate(('s1', 's1', 's2')):
            key = f'{i:032x}'
            (ai_jobs.clips_dir() / (key + '.mp4')).write_bytes(b'x' * 100)
            (ai_jobs.clips_dir() / (key + '.json')).write_text(json.dumps({'key': key, 'session': session}))
            os.utime(ai_jobs.clips_dir() / (key + '.mp4'), (1000 + i, 1000 + i)); made.append(key)
        (ai_jobs.clips_dir() / ('f' * 32 + '.json')).write_text(json.dumps({'key': 'f' * 32, 'session': 's1'}))  # no video
        self.assertEqual(sorted(c['key'] for c in ai_jobs.clips_for('s1')), made[:2])
        self.assertTrue(all(c['url'] == f"/api/ai/result/{c['key']}.mp4" for c in ai_jobs.clips_for('s1')))
        with patch.object(ai_jobs, 'CLIP_BUDGET', 150):
            ai_jobs.prune_clips(keep=made[0])
        left = sorted(p.stem for p in ai_jobs.clips_dir().glob('*.mp4'))
        self.assertEqual(left, [made[0], made[2]])           # newest kept, the protected one kept
        self.assertFalse((ai_jobs.clips_dir() / (made[1] + '.json')).exists())

    def test_interpreter_override_must_exist(self):
        with patch.dict(os.environ, {'KRYONYX_AI_PYTHON': str(self.root / 'missing-python')}):
            with self.assertRaises(ValueError):
                ai_jobs.interpreter()
        with patch.dict(os.environ, {'KRYONYX_AI_PYTHON': sys.executable}):
            self.assertEqual(ai_jobs.interpreter(), sys.executable)


# ---------------------------------------------------------------------------------------------- HTTP API
class FakeClips:
    def __init__(self, sessions):
        self.sessions = sessions

    def get(self, sid):
        return self.sessions.get(sid)

    async def close(self):
        pass


@unittest.skipUnless(POSIX, 'fake worker uses a POSIX shell wrapper')
class HTTP(FakeEngine, unittest.IsolatedAsyncioTestCase):
    SID = 'a' * 24

    async def asyncSetUp(self):
        self.start_engine(); self.models = None
        video = self.root / 'clip.mp4'; video.write_bytes(b'video' * 100)
        audio = self.root / 'clip.m4a'; audio.write_bytes(b'audio' * 100)
        src = lambda p, done=True: SimpleNamespace(done=done, final=p)
        self.session = SimpleNamespace(height=108, sources={'video': src(video), 'audio': src(audio)})
        self.ff = patch.object(clipcache, 'ffmpeg_exe', return_value=sys.executable); self.ff.start()
        app = server.build_app(); app['clip_streams'] = FakeClips({self.SID: self.session})
        self.client = TestClient(TestServer(app)); await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close(); self.ff.stop()
        if self.models: self.models.stop()
        self.stop_engine()

    async def call(self, method, url, **kw):
        r = await self.client.request(method, url, **kw)
        return r.status, (await r.json() if r.content_type == 'application/json' else await r.read())

    def png(self):
        out = io.BytesIO(); Image.new('RGB', (64, 48), 'blue').save(out, 'PNG'); return out.getvalue()

    async def wallpaper(self, query='?model=fast'):
        return await self.call('POST', '/api/ai/wallpaper' + query, data=self.png(), headers={'Content-Type': 'image/png'})

    async def test_status_lists_engine_models_and_setup(self):
        code, body = await self.call('GET', '/api/ai/status')
        self.assertEqual(code, 200)
        self.assertEqual((body['engine']['installed'], body['engine']['advice'], body['busy']), (True, 'cpu', False))
        self.assertEqual(set(body['models']), set(ai_models.MODELS))
        self.assertFalse(any(m['present'] for m in body['models'].values()))
        self.assertEqual(body['setup'], {'script': 'setup-ai.sh', 'available': True, 'launch': False})
        code, body = await self.call('POST', '/api/ai/install')
        self.assertEqual((code, body), (200, {'launched': False, 'command': 'sh setup-ai.sh'}))

    async def test_missing_engine_or_weights_answer_409_and_leave_no_upload(self):
        os.environ['FAKE_AI72'] = 'missing'
        code, body = await self.call('GET', '/api/ai/status?refresh=1')
        self.assertFalse(body['engine']['installed'])
        code, body = await self.wallpaper()
        self.assertEqual((code, body['code']), (409, 'engine'))
        os.environ['FAKE_AI72'] = 'ok'; await self.call('GET', '/api/ai/status?refresh=1')
        code, body = await self.wallpaper('?model=photo')
        self.assertEqual((code, body['code'], body['missing']), (409, 'models', ['RealESRGAN_x4plus']))
        code, body = await self.call('POST', '/api/ai/clip', json={'session': self.SID, 'upscale': 'x2', 'smooth': True})
        self.assertEqual((code, body['missing']), (409, ['realesr-general-x4v3', 'rife']))
        self.assertEqual(list(ai_jobs.work_dir().iterdir()), [])
        code, body = await self.wallpaper('?model=../../x')
        self.assertEqual((code, body['error']), (400, 'Unknown AI model'))
        code, body = await self.call('POST', '/api/ai/wallpaper', json={'file': '../secret.jpg'})
        self.assertEqual(code, 400)

    async def test_wallpaper_enhancement_end_to_end(self):
        self.install_tiny('realesr-general-x4v3')
        code, job = await self.wallpaper('?model=fast&target=2560')
        self.assertEqual((code, job['stage'], job['options']['factor']), (200, 'queued', 4.0))
        self.assertEqual((job['options']['out_width'], job['options']['out_height']), (256, 192))
        done = await self.until_finished(lambda: self.call('GET', f"/api/ai/jobs/{job['id']}").__await__().__next__ and None) \
            if False else await self.poll(job['id'])
        self.assertEqual(done['stage'], 'done', done)
        self.assertTrue((wallpaper.directory() / done['file']).is_file())
        sent = self.requests()[0]
        self.assertEqual(sent['upscale'], {'path': str(ai_models.path('realesr-general-x4v3')), 'arch': 'compact', 'num_conv': 32})
        self.assertEqual(list(ai_jobs.work_dir().iterdir()), [])

    async def poll(self, jid):
        async def status():
            code, body = await self.call('GET', f'/api/ai/jobs/{jid}')
            return body if code == 200 else None
        return await self.until_finished(status)

    async def test_clip_options_are_validated(self):
        cases = [({'session': 'b' * 24}, 404), ({'session': self.SID, 'upscale': 'off'}, 400),
                 ({'session': self.SID, 'upscale': '8k'}, 400), ({'session': self.SID, 'style': 'oil'}, 400),
                 ({'session': self.SID, 'upscale': '1080', 'style': 'anime'}, None)]
        self.session.height = 1080
        for data, expected in cases[:-1]:
            code, body = await self.call('POST', '/api/ai/clip', json=data)
            self.assertEqual(code, expected, data)
        code, body = await self.call('POST', '/api/ai/clip', json=cases[-1][0])
        self.assertEqual((code, body['error']), (400, 'The clip is already at this resolution or higher'))
        self.session.sources['video'].done = False
        code, body = await self.call('POST', '/api/ai/clip', json={'session': self.SID, 'smooth': True})
        self.assertEqual(code, 409)
        code, _ = await self.call('POST', '/api/ai/clip', json={'session': self.SID, 'smooth': True},
                                  headers={'Origin': 'https://evil.example'})
        self.assertEqual(code, 403)
        self.assertEqual((await self.call('GET', '/api/ai/clip?session=nope'))[0], 400)
        self.assertEqual((await self.call('GET', '/api/ai/jobs/unknown'))[0], 404)
        self.assertEqual((await self.call('GET', '/api/ai/result/' + 'a' * 32 + '.mp4'))[0], 404)
        self.assertEqual((await self.call('GET', '/api/ai/result/..%2F..%2Fsecret.mp4'))[0], 404)

    async def test_clip_upscale_and_smoothing_end_to_end_and_cached(self):
        self.install_tiny('realesr-general-x4v3', 'rife')
        options = {'session': self.SID, 'upscale': 'x2', 'style': 'general', 'smooth': True}
        code, job = await self.call('POST', '/api/ai/clip', json=options)
        self.assertEqual((code, job['kind'], job['options']['height']), (200, 'clip', 216))
        done = await self.poll(job['id'])
        self.assertEqual(done['stage'], 'done', done)
        sent = self.requests()[0]
        self.assertEqual((sent['height'], sent['interpolate']['arch'], sent['audio']), (216, 'ifnet', str(self.root / 'clip.m4a')))
        code, listing = await self.call('GET', f'/api/ai/clip?session={self.SID}')
        self.assertEqual([i['key'] for i in listing['items']], [done['key']])
        self.assertEqual((listing['items'][0]['height'], listing['items'][0]['fps']), (384 and 216, 24.0))
        r = await self.client.get(done['url'])
        self.assertEqual((r.status, r.headers['Content-Type'], r.headers['X-Content-Type-Options']), (200, 'video/mp4', 'nosniff'))
        await r.read()
        code, again = await self.call('POST', '/api/ai/clip', json=options)
        self.assertEqual((again['cached'], again['stage'], again['key']), (True, 'done', done['key']))
        self.assertEqual(len(self.requests()), 1)                        # reused, not recomputed
        code, body = await self.call('DELETE', done['url'])
        self.assertEqual((code, body), (200, {'deleted': done['key']}))
        self.assertEqual((await self.call('GET', done['url']))[0], 404)
        self.assertEqual((await self.call('GET', f'/api/ai/clip?session={self.SID}'))[1]['items'], [])

    async def test_model_download_endpoint_validates_ids(self):
        code, body = await self.call('POST', '/api/ai/models', json={'ids': ['../../evil']})
        self.assertEqual((code, body['error']), (400, 'Unknown model'))
        blob = os.urandom(1500)
        session = FakeSession({'https://models.test/tiny.pth': FakeResponse(blob)})

        async def factory():
            return session
        with patch.dict(ai_models.MODELS, {'tiny': tiny_spec(blob)}), patch.dict(ai_models.NEEDS, {'clip:tiny': ['tiny']}), \
                patch.object(server, 'http', factory):
            code, body = await self.call('POST', '/api/ai/models', json={'feature': 'clip:tiny'})
            self.assertEqual((code, body['downloads']['tiny']['stage']), (200, 'queued'))
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                state = (await self.call('GET', '/api/ai/status'))[1]['downloads']['tiny']
                if state['stage'] not in ('queued', 'downloading', 'verifying'):
                    break
                await asyncio.sleep(.05)
            self.assertEqual(state['stage'], 'done')
            self.assertTrue(ai_models.present('tiny'))


# ---------------------------------------------------------------------------------------------- real worker
AI_PYTHON = os.environ.get('KRYONYX_AI_TEST_PYTHON', '')
MAKE_WEIGHTS = r'''
import sys, torch
from kryonyx import ai_arch
torch.manual_seed(0)
sr = ai_arch.SRVGGNetCompact(num_conv=2)
torch.save({'params': sr.state_dict()}, sys.argv[1])
flow = ai_arch.IFNet()
torch.save({'module.' + k: v for k, v in flow.state_dict().items()}, sys.argv[2])
'''


@unittest.skipUnless(AI_PYTHON and Path(AI_PYTHON).is_file(), 'set KRYONYX_AI_TEST_PYTHON to a Python with torch')
class RealWorker(unittest.TestCase):
    """Real torch pipeline on CPU with random weights: shapes, tiling, frame doubling, audio mux."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.root = Path(cls.tmp.name)
        cls.env = {**os.environ, 'PYTHONPATH': str(ROOT), 'OMP_NUM_THREADS': '1'}
        cls.sr, cls.flow = cls.root / 'sr.pth', cls.root / 'flow.pkl'
        subprocess.run([AI_PYTHON, '-c', MAKE_WEIGHTS, str(cls.sr), str(cls.flow)], cwd=ROOT, env=cls.env, check=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def work(self, request):
        proc = subprocess.run([AI_PYTHON, '-m', 'kryonyx.ai_worker'], cwd=ROOT, env=self.env, input=json.dumps(request) + '\n',
                              capture_output=True, text=True, timeout=600)
        lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
        self.assertEqual(proc.returncode, 0, lines[-1:] or proc.stderr[-500:])
        return lines

    def test_image_upscale_tiles_and_resizes(self):
        src = self.root / 'in.png'; Image.new('RGB', (40, 30), 'green').save(src)
        out = self.root / 'out.jpg'
        lines = self.work({'mode': 'image', 'input': str(src), 'output': str(out), 'out_w': 150, 'out_h': 112, 'tile': 16,
                           'device': 'cpu', 'threads': 1, 'upscale': {'path': str(self.sr), 'arch': 'compact', 'num_conv': 2}})
        self.assertEqual(max(l.get('total', 0) for l in lines), 6)
        self.assertEqual(lines[-1]['result'], str(out))
        with Image.open(out) as im:
            self.assertEqual(im.size, (150, 112))

    @unittest.skipUnless(shutil.which('ffmpeg') or clipcache.ffmpeg_exe(), 'ffmpeg is required')
    def test_clip_upscale_and_double_frame_rate_keep_audio(self):
        ff = clipcache.ffmpeg_exe() or shutil.which('ffmpeg')
        clip = self.root / 'clip.mp4'
        subprocess.run([ff, '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=64x36:rate=12:duration=2', '-f', 'lavfi',
                        '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                        '-shortest', str(clip)], check=True, timeout=120)
        out = self.root / 'out.mp4'
        lines = self.work({'mode': 'video', 'input': str(clip), 'output': str(out), 'ffmpeg': ff, 'height': 72, 'device': 'cpu',
                           'threads': 1, 'upscale': {'path': str(self.sr), 'arch': 'compact', 'num_conv': 2},
                           'interpolate': {'path': str(self.flow), 'arch': 'ifnet'}})
        self.assertEqual((lines[-1]['width'], lines[-1]['height'], lines[-1]['fps'], lines[-1]['frames']), (128, 72, 24.0, 24))
        info = ai_worker.video_info(ff, str(out))
        self.assertEqual((info['width'], info['height'], info['fps'], info['audio']), (128, 72, 24.0, True))
        self.assertAlmostEqual(info['duration'], 2.0, delta=.25)


if __name__ == '__main__':
    unittest.main()
