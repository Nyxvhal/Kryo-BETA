"""v72 local QA for the optional AI module: tiny synthetic clip (192x108,
12 fps, 4 s + tone), real AI endpoints, real worker when an AI Python exists.
Port 8792. NOT a live YouTube test and NOT a GPU performance test.

/fixture/ai72?engine=real|missing  switches the AI interpreter
(real: $AI72_PYTHON or /data/kryo/aivenv/bin/python; missing: a Python without torch).
Weights are copied from $AI72_MODELS (default /data/kryo/ai/test72/models) when present.
"""
import asyncio, os, shutil, subprocess, sys
from pathlib import Path
os.environ.setdefault('VIDEO57_QA_DIR', '/data/v72-ai-qa')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import serve_classic_v63_fixture as cl   # noqa: E402  (sets the fixture data dir)
from aiohttp import web   # noqa: E402
from kryonyx import server, clipstream, clipcache, ai_models, paths   # noqa: E402

PORT = 8792
QA = cl.QA
REAL = os.environ.get('AI72_PYTHON', '/data/kryo/aivenv/bin/python')
MISSING = shutil.which('python3') or sys.executable
AI = {'engine': 'real' if Path(REAL).is_file() else 'missing'}


async def fixture_media72(*a, **k):
    # The classic fixture points demo tracks at its own port (8790); serve the tone from this one,
    # so the v72 suites do not depend on the v63 fixture running at the same time.
    return 'fixture-wave61', {'url': f'http://127.0.0.1:{PORT}/fixture-tone.wav', 'mime': 'audio/wav'}
server._media_for = fixture_media72


def use_engine(mode):
    AI['engine'] = mode
    os.environ['KRYONYX_AI_PYTHON'] = REAL if mode == 'real' and Path(REAL).is_file() else MISSING


@web.middleware
async def fixture(req, handler):
    p = req.path
    if p == '/fixture/ai72':
        if 'engine' in req.query:
            use_engine(req.query['engine'])
            jobs = req.app.get('ai_jobs72')
            if jobs: jobs._probe = None
        return web.json_response({**AI, 'python': os.environ.get('KRYONYX_AI_PYTHON'), 'data': paths.data_dir()})
    if p.startswith(('/api/ai/', '/api/wallpaper/')):
        return await handler(req)
    if p.startswith('/fixture-source72/'):
        return await handler(req)
    return await cl.fixture(req, handler)


async def main():
    ff = clipcache.ffmpeg_exe() or 'ffmpeg'
    if not (QA / 'video.mp4').exists():
        subprocess.run([ff, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=192x108:rate=12:duration=4',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-g', '12', '-an', '-movflags', '+faststart', str(QA / 'video.mp4')], check=True)
        subprocess.run([ff, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=4',
                        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(QA / 'audio.m4a')], check=True)
    models = Path(os.environ.get('AI72_MODELS', '/data/kryo/ai/test72/models'))
    if models.is_dir():
        for spec in ai_models.MODELS.values():
            src, dst = models / spec['file'], ai_models.folder() / spec['file']
            if src.is_file() and not dst.exists():
                shutil.copyfile(src, dst)
    use_engine(AI['engine'])
    app = server.build_app(); app.middlewares.insert(0, fixture)
    app.router.add_get('/fixture/video57', lambda r: web.json_response(cl.STATE))
    app.router.add_get('/fixture-poster57/{name}', cl.poster)
    app.router.add_get('/fixture-source72/{name}', cl.source)

    async def identify(ident, *args):
        return ident.removeprefix('ytvideo:') if ident.startswith('ytvideo:') else 'kJQP7kiw5Fk'

    async def resolve(ident, q, refresh):
        base = f'http://127.0.0.1:{PORT}/fixture-source72/'
        return {'video': {'url': base + 'video.mp4', 'mime': 'video/mp4', 'height': 108, 'itag': 160},
                'audio': {'url': base + 'audio.m4a', 'mime': 'audio/mp4', 'itag': 140}, 'container': 'mp4'}
    app['clip_streams'] = clipstream.Manager(await server.http(), identify, resolve)
    runner = web.AppRunner(app); await runner.setup(); await web.TCPSite(runner, '127.0.0.1', PORT).start()
    print('AI72_FIXTURE_READY', AI['engine'], flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()

if __name__ == '__main__':
    asyncio.run(main())
