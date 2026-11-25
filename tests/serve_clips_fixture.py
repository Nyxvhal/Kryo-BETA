"""Local throttled media fixture, deliberately NOT a YouTube-access test."""
import sys,asyncio,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
QA=Path(os.environ.get('CLIPS_QA_DIR','/tmp/kryonyx-clip-qa'));QA.mkdir(parents=True,exist_ok=True)
os.environ['XDG_DATA_HOME']=str(QA/'state')
if os.name=='nt':
 os.environ['LOCALAPPDATA']=str(QA/'state');os.environ['APPDATA']=str(QA/'state')
from aiohttp import web,ClientSession
from kryonyx import server,clipstream as cs,storage,paths
paths._data_dir=str(QA/"state"/"kryonyx-music");Path(paths._data_dir).mkdir(parents=True,exist_ok=True)
MEDIA=QA/'media';MEDIA.mkdir(exist_ok=True)
async def main():
 storage.init(str(QA/'test.sqlite'))
 if not (MEDIA/'video.mp4').exists():
  import subprocess
  from kryonyx import clipcache
  ff=clipcache.ffmpeg_exe()
  if not ff:raise RuntimeError('Install imageio-ffmpeg or ffmpeg for this fixture')
  art=Path(__file__).resolve().parents[1]/'kryonyx/web/img/avatars/kryonyx-02-black-violet.png'
  subprocess.run([ff,'-y','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=1280x720:rate=25:duration=30','-i',str(art),'-filter_complex','[0:v][1:v]overlay=40:40','-c:v','libx264','-preset','ultrafast','-b:v','1800k','-maxrate','1800k','-bufsize','3600k','-g','25','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(MEDIA/'video.mp4')],check=True)
  subprocess.run([ff,'-y','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=30','-c:a','aac','-b:a','128k','-vn','-movflags','+faststart',str(MEDIA/'audio.m4a')],check=True)
  subprocess.run([ff,'-y','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=330:duration=30',str(MEDIA/'music.wav')],check=True)
 async def source(req):
  name=req.match_info['name']
  if name not in ('video.mp4','audio.m4a'):raise web.HTTPNotFound()
  path=MEDIA/name;total=path.stat().st_size
  try:a,b,partial=cs.ranges(req.headers.get('Range',''),total)
  except ValueError:raise web.HTTPRequestRangeNotSatisfiable(headers={'Content-Range':f'bytes */{total}'})
  resp=web.StreamResponse(status=206 if partial else 200,headers={'Content-Length':str(b-a+1),'Accept-Ranges':'bytes',**({'Content-Range':f'bytes {a}-{b}/{total}'} if partial else {})});await resp.prepare(req)
  try:
   with path.open('rb') as f:
    f.seek(a)
    while a<=b:
     chunk=f.read(min(32768,b-a+1));await resp.write(chunk);a+=len(chunk);await asyncio.sleep(.065 if path.suffix=='.mp4' else .18)
   await resp.write_eof()
  except (ConnectionResetError,asyncio.CancelledError):pass
  return resp
 app=web.Application();app.router.add_get('/cdn/{name}',source);runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8770).start()
 http=ClientSession()
 async def identify(id,*args):
  if 'ERROR' in id:raise RuntimeError('Test fixture: simulated unavailable original')
  return id[8:] if id.startswith('ytvideo:') else 'TESTVIDEO01'
 async def resolve(id,q,refresh):
  return {'video':{'url':'http://127.0.0.1:8770/cdn/video.mp4','mime':'video/mp4','height':720,'itag':136},'audio':{'url':'http://127.0.0.1:8770/cdn/audio.m4a','mime':'audio/mp4','itag':140},'container':'mp4'}
 app=server.build_app();app['clip_streams']=cs.Manager(http,identify,resolve)
 @web.middleware
 async def fixture_marker(request,handler):
  if request.path=='/api/clips/fixture':return web.json_response({'fixture':True,'realYouTube':False})
  return await handler(request)
 app.middlewares.append(fixture_marker)
 app.router.add_get('/fixture-music.wav',lambda req:web.FileResponse(MEDIA/'music.wav'))
 runner2=web.AppRunner(app);await runner2.setup();await web.TCPSite(runner2,'127.0.0.1',8766).start();print('CLIP_QA_READY',flush=True)
 try:await asyncio.Event().wait()
 finally:await runner2.cleanup();await http.close();await runner.cleanup()
asyncio.run(main())
