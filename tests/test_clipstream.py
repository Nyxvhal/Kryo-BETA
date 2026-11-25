"""Deterministic local CDN tests. No YouTube account or network required."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer,TestClient
from kryonyx import clipstream as cs

class Helpers(unittest.TestCase):
 def test_ranges(self):
  self.assertEqual(cs.ranges('bytes=2-9',20),(2,9,True));self.assertEqual(cs.ranges('bytes=-4',20),(16,19,True));self.assertEqual(cs.ranges('bytes=18-',20),(18,19,True));self.assertEqual(cs.ranges('',20),(0,19,False))
 def test_invalid_ranges(self):
  for h in ['bytes=20-','bytes=5-4','bytes=-0','bytes=0-1,3-4','bytes=-','bogus']:
   with self.assertRaises(ValueError):cs.ranges(h,20)
 def test_redaction(self):
  for text in ['Cookie: secret-value',"headers={'Cookie': 'secret-value'}",'Authorization=secret-value','https://cdn.test/v?token=secret-value']:
   self.assertNotIn('secret-value',cs.safe_reason(Exception(text)))

class StreamTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(cs,'data_dir',return_value=self.tmp.name);self.patch.start();self.data=bytes(range(256))*4096;self.ignore=False;self.unknown=False;self.bad_range=False;self.refreshes=0;self.forbid=False
  async def upstream(req):
   if self.forbid:self.forbid=False;return web.Response(status=403)
   a,b,_=cs.ranges(req.headers.get('Range',''),len(self.data));code=200 if self.ignore or self.unknown else 206
   if code==200:a,b=0,len(self.data)-1
   headers={} if self.unknown else {'Content-Length':str(b-a+1)}
   if code==206:headers['Content-Range']=f'bytes {a+int(self.bad_range)}-{b}/{len(self.data)}'
   resp=web.StreamResponse(status=code,headers=headers);await resp.prepare(req)
   try:
    for i in range(a,b+1,16384):await resp.write(self.data[i:min(i+16384,b+1)]);await asyncio.sleep(.005)
    await resp.write_eof()
   except (ConnectionResetError,asyncio.CancelledError):pass
   return resp
  app=web.Application();app.router.add_get('/source',upstream);self.up=TestServer(app);await self.up.start_server();self.http=aiohttp.ClientSession()
  async def identify(*args):return 'ABCDEFGHIJK'
  async def resolve(v,q,refresh):
   if refresh:self.refreshes+=1
   return {'video':{'url':str(self.up.make_url('/source')),'mime':'video/mp4','size':99,'headers':{'Cookie':'private-value'},'height':720,'itag':22},'audio':None,'container':'mp4'}
  self.manager=cs.Manager(self.http,identify,resolve)
  async def media(req):return await self.session.sources['video'].serve(req)
  app=web.Application();app.router.add_get('/media',media);self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):
  await self.manager.close();await self.client.close();await self.http.close();await self.up.close();self.patch.stop();self.tmp.cleanup()
 async def create(self):
  self.session=await self.manager.create('ytvideo:ABCDEFGHIJK','Test',quality=720)
  for _ in range(100):
   if self.session.sources and self.session.sources['video'].written>0:return self.session.sources['video']
   await asyncio.sleep(.01)
  self.fail('No source bytes')
 async def complete(self):
  for _ in range(300):
   if self.session.state in ('done','error'):break
   await asyncio.sleep(.01)
  self.assertEqual(self.session.state,'done',self.session.error)
 async def test_partial_before_complete_and_range_headers(self):
  src=await self.create();r=await self.client.get('/media',headers={'Range':'bytes=0-16383'});self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Range'],f'bytes 0-16383/{len(self.data)}');self.assertEqual(await r.read(),self.data[:16384]);self.assertLess(src.written,src.total);self.assertEqual(src.total,len(self.data))
 async def test_pause_resume_keeps_prefix(self):
  src=await self.create();await self.session.pause();size=src.written;await asyncio.sleep(.07);self.assertEqual(size,src.written);self.assertEqual(self.session.public()['state'],'paused');await self.session.resume();await self.complete();self.assertEqual(src.final.read_bytes(),self.data)
 async def test_ignored_range_and_far_tail(self):
  self.ignore=True;src=await self.create();r=await self.client.get('/media',headers={'Range':f'bytes={len(self.data)-512}-'});self.assertEqual(await r.read(),self.data[-512:]);await self.complete();self.assertEqual(src.final.read_bytes(),self.data)
 async def test_unknown_size_not_faked(self):
  self.unknown=True;src=await self.create();self.assertIsNone(self.session.public()['progress']);await self.complete();self.assertEqual(src.total,len(self.data));self.assertEqual(src.final.read_bytes(),self.data)
 async def test_expired_url_refresh(self):
  self.forbid=True;await self.create();await self.complete();self.assertGreater(self.refreshes,0)
 async def test_invalid_request_and_head(self):
  await self.create();r=await self.client.get('/media',headers={'Range':'bytes=0-4,8-9'});self.assertEqual(r.status,416);r=await self.client.head('/media',headers={'Range':'bytes=2-8'});self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Length'],'7');self.assertEqual(await r.read(),b'')
 async def test_cancel_retry(self):
  src=await self.create();await self.session.cancel();self.assertEqual(self.session.state,'cancelled');r=await self.client.get('/media');self.assertEqual(r.status,410);new=await self.manager.create(self.session.track_id,quality=720,retry=True);self.assertIsNot(new,self.session);self.session=new;await self.complete()
 async def test_metadata_and_status_never_expose_secrets(self):
  await self.create();await self.complete();p=json.loads((self.session.directory/'metadata.json').read_text());text=json.dumps(p)+json.dumps(self.session.public());self.assertNotIn('private-value',text);self.assertNotIn(str(self.up.make_url('/source')),text)
 async def test_completed_cache_survives_restart_without_resolver(self):
  await self.create();await self.complete();await self.manager.close()
  async def forbidden(*args):self.fail('Offline cache called resolver')
  self.manager=cs.Manager(self.http,forbidden,forbidden);self.session=await self.manager.create('ytvideo:ABCDEFGHIJK',quality=720);await asyncio.sleep(.03);self.assertTrue(self.session.public()['offline_ready']);r=await self.client.get('/media',headers={'Range':'bytes=-256'});self.assertEqual(await r.read(),self.data[-256:])
 async def test_wrong_upstream_range_rejected(self):
  self.bad_range=True;self.session=await self.manager.create('bad',quality=720)
  for _ in range(1200):
   if self.session.state=='error':break
   await asyncio.sleep(.01)
  self.assertEqual(self.session.state,'error');self.assertEqual(self.session.sources['video'].written,0)

class RestoredMuxTests(unittest.IsolatedAsyncioTestCase):
 async def test_complete_tracks_rebuild_missing_export_without_network(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(cs,'data_dir',return_value=temp):
   async def forbidden(*args):raise AssertionError('Offline restore used a resolver')
   manager=cs.Manager(None,forbidden,forbidden);old=cs.Session(manager,'restored','Test','',720);old.directory.mkdir(parents=True)
   (old.directory/'video.bin').write_bytes(b'video');(old.directory/'audio.bin').write_bytes(b'audio')
   (old.directory/'metadata.json').write_text(json.dumps({'track_id':'restored','quality':720,'video_id':'ABCDEFGHIJK','height':720,'container':'mp4','sources':{'video':{'size':5,'mime':'video/mp4','complete':True},'audio':{'size':5,'mime':'audio/mp4','complete':True}}}))
   async def mux(video,audio,dest,container):Path(dest).write_bytes(Path(video).read_bytes()+Path(audio).read_bytes())
   with patch.object(cs.clipcache,'_mux',side_effect=mux):
    job=await manager.create('restored',quality=720);await job.task;self.assertTrue(job.public()['file_ready']);self.assertEqual(job.final.read_bytes(),b'videoaudio')
   await manager.close()

class APITests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from kryonyx import server
  self.client=TestClient(TestServer(server.build_app()));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close()
 async def test_invalid_create_before_network(self):
  for data in [{},{'id':'test','quality':999},{'id':'x'*2049},{'id':'test','quality':'no'}]:
   r=await self.client.post('/api/clips/sessions',json=data);self.assertEqual(r.status,400)
 async def test_foreign_origin_rejected_before_network(self):
  r=await self.client.post('/api/clips/sessions',json={'id':'test'},headers={'Origin':'https://foreign.test'});self.assertEqual(r.status,403)
