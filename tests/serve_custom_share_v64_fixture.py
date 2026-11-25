"""v57 local QA: public poster metadata, synthetic A/V, NO account cookies.
This is NOT a live YouTube access test. Port 8791.
"""
import asyncio,sys,os,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serve_ui_v53_fixture as base
from aiohttp import web
from kryonyx import server,clipstream,paths,clipcache
QA=Path(os.environ.get('VIDEO57_QA_DIR','/data/v64-qa'));QA.mkdir(parents=True,exist_ok=True)
paths._data_dir=str(QA/'private-fixture-state');Path(paths._data_dir).mkdir(exist_ok=True)
STATE={'cookies':'missing','catalogCalls':0,'mediaUpstream':0,'delay':0,'error':False}
TITLES=[('kJQP7kiw5Fk','Luis Fonsi — Despacito ft. Daddy Yankee','Luis Fonsi'),('OPf0YbXqDm0','Mark Ronson — Uptown Funk ft. Bruno Mars','Mark Ronson'),('hT_nvWreIhg','OneRepublic — Counting Stars','OneRepublic'),('JGwWNGJdvx8','Ed Sheeran — Shape of You','Ed Sheeran'),('60ItHLz5WEA','Alan Walker — Faded','Alan Walker'),('fLexgOxsZu0','Bruno Mars — The Lazy Song','Bruno Mars')]
def cookies():
 mode=STATE['cookies']
 return {'present':mode in ('ready','expired'),'signed_in':mode=='ready','expired':mode=='expired','browser':'firefox' if mode=='browser' else '', 'count':8 if mode=='ready' else 0,'updated_at':57,'browsers':['firefox','chrome']}
server.ytcookies.state=cookies
async def catalog(q,n):
 STATE['catalogCalls']+=1
 await asyncio.sleep(.65 if q.startswith('slow') else .03)
 if STATE['error']:raise RuntimeError('Synthetic catalog failure')
 if q=='nothing':return []
 rows=[{'id':'yt:'+i,'title':t,'artist':a,'duration':0,'thumbnail':'http://127.0.0.1:8791/fixture-poster57/'+i+'.jpg'} for i,t,a in TITLES]
 return rows[:n]
server.ytmusic.video_search=catalog
async def fallback(*args,**kw):return []
server.youtube.search=fallback
async def poster(req):
 name=req.match_info['name'];path=Path(__file__).parent/'fixtures/video57-posters'/name
 if name not in [i+'.jpg' for i,_,_ in TITLES]:raise web.HTTPNotFound()
 return web.FileResponse(path)
async def source(req):
 STATE['mediaUpstream']+=1;kind=req.match_info['name']
 if kind not in ['video.mp4','audio.m4a']:raise web.HTTPNotFound()
 path=QA/kind;total=path.stat().st_size;a,b,partial=clipstream.ranges(req.headers.get('Range',''),total)
 headers={'Content-Length':str(b-a+1),'Accept-Ranges':'bytes','Content-Type':'video/mp4' if kind=='video.mp4' else 'audio/mp4'}
 if partial:headers['Content-Range']=f'bytes {a}-{b}/{total}'
 resp=web.StreamResponse(status=206 if partial else 200,headers=headers);await resp.prepare(req)
 try:
  with path.open('rb') as f:
   f.seek(a)
   while a<=b:
    chunk=f.read(min(32768,b-a+1));await resp.write(chunk);a+=len(chunk);await asyncio.sleep(.06)
 except (ConnectionResetError,asyncio.CancelledError):pass
 return resp

# Synthetic metadata + real local audio/vault. Production wave ranking remains active.
from kryonyx import recommend, audiovault
WAVE={'calls':0,'mode':'ok','last_seed':'','prefetch':[]}
async def wave_related(seed,artist,title,limit,**kwargs):
 WAVE['calls']+=1;WAVE['last_seed']=seed
 if WAVE['mode']=='slow':await asyncio.sleep(2)
 if WAVE['mode']=='error':raise RuntimeError('Synthetic provider outage')
 if WAVE['mode']=='empty':return []
 import hashlib
 token=hashlib.sha1(seed.encode()).hexdigest()[:7]
 return [dict(id=f'yt:wave-{token}-{i}',title=['Ночной маршрут','Линии света','Ближе к тебе','После полуночи','Тихий пульс','Другие берега','Лови момент','Город не спит'][i%8]+' · '+str(i+1),artist=['Демо · Север','Демо · Маяк','Демо · Полюс','Демо · Апрель'][i%4],source='youtube',duration=10,thumbnail=base.TRACKS[i%4]['thumbnail']) for i in range(16)]
async def no_search(*a,**k):return []
recommend.providers.related=wave_related
recommend._search_many=no_search
async def _no_catalog70(*a,**k):return []
recommend._curated=_no_catalog70;recommend._starter_playlists=_no_catalog70;recommend._starter_albums=_no_catalog70
recommend._user_sources=lambda:['youtube']
recommend._top_artists=lambda *a:[]
recommend._external=lambda:{'artists':[],'played':set(),'liked':set(),'queries':[]}
recommend.storage.get_settings=lambda:{}
recommend.storage.played_ids=lambda *a:set()
recommend.storage.list_likes=lambda *a:[]
recommend.storage.disliked_artists=lambda:[]
async def fixture_media(*a,**k):return 'fixture-wave61',{'url':'http://127.0.0.1:8791/fixture-tone.wav','mime':'audio/wav'}
server._media_for=fixture_media

@web.middleware
async def fixture(req,handler):
 p=req.path
 if p=='/fixture/wave61':
  if 'mode' in req.query:WAVE['mode']=req.query['mode']
  return web.json_response(WAVE)
 if p=='/api/likes' and req.method=='POST':
  data=await req.json();key=data['track']['id'];likes=WAVE.setdefault('likes',[]);liked=key not in likes
  if liked:likes.append(key)
  else:likes.remove(key)
  return web.json_response({'liked':liked})
 if p=='/api/wave':return await server.api_wave61(req)
 if p=='/api/prefetch' and req.query.get('status')!='1':WAVE['prefetch'].append(req.query.get('id'))
 if p=='/fixture/video57':
  if 'cookies' in req.query:STATE['cookies']=req.query['cookies']
  if 'error' in req.query:STATE['error']=req.query['error']=='1'
  return web.json_response(STATE)
 if p=='/api/youtube/cookies':
  if STATE['cookies']=='unavailable':return web.json_response({'error':'Fixture unavailable'},status=503)
  return web.json_response(cookies())
 if p.startswith(('/api/audio-share', '/api/clips/','/fixture-source57/','/fixture-poster57/')):return await handler(req)
 return await base.fixture(req,handler)
async def main():
 if not (QA/'video.mp4').exists():
  ff=clipcache.ffmpeg_exe() or 'ffmpeg'
  subprocess.run([ff,'-y','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=1280x720:rate=25:duration=18','-c:v','libx264','-preset','ultrafast','-b:v','1800k','-g','25','-an','-movflags','+faststart',str(QA/'video.mp4')],check=True)
  subprocess.run([ff,'-y','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=18','-c:a','aac','-b:a','128k','-movflags','+faststart',str(QA/'audio.m4a')],check=True)
 app=server.build_app();app.middlewares.insert(0,fixture);app.router.add_get('/fixture/video57',lambda r:web.json_response(STATE));app.router.add_get('/fixture-poster57/{name}',poster);app.router.add_get('/fixture-source57/{name}',source)
 async def identify(ident,*args):return ident.removeprefix('ytvideo:') if ident.startswith('ytvideo:') else 'kJQP7kiw5Fk'
 async def resolve(ident,q,refresh):return {'video':{'url':'http://127.0.0.1:8791/fixture-source57/video.mp4','mime':'video/mp4','height':720,'itag':136},'audio':{'url':'http://127.0.0.1:8791/fixture-source57/audio.m4a','mime':'audio/mp4','itag':140},'container':'mp4'}
 app['clip_streams']=clipstream.Manager(await server.http(),identify,resolve)
 runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,'127.0.0.1',8791).start();print('VIDEO57_FIXTURE_READY',flush=True)
 try:await asyncio.Event().wait()
 finally:await runner.cleanup()
if __name__=='__main__':asyncio.run(main())
