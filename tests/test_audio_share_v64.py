import asyncio,base64,io,json,os,tempfile,time,unittest,wave
from pathlib import Path
from unittest.mock import patch
from aiohttp import web,ClientSession
from aiohttp.test_utils import TestServer
from PIL import Image
from kryonyx import audio_share as share,server

class ShareValidation64(unittest.TestCase):
 def test_invalid_tracks(self):
  for track in (None,{}, {'id':'https://evil/file','title':'x'}, {'id':'yt:a\nb','title':'x'}, {'id':'yt:valid','title':''}):
   with self.subTest(track=track),self.assertRaises(share.ShareError):share.clean_track(track)
 def test_text_tags_preserve_names(self):
  t=share.clean_track({'id':'yt:abc','title':'Play','artist':'Radio','thumbnail':''});self.assertEqual((t['title'],t['artist']),('Play','Radio'))
 def test_portable_filename(self):
  self.assertEqual(share.portable_name('Автор — Название.mp3'),'Avtor - Nazvanie.mp3')
 def test_paths_rejected(self):
  for key in ['../../etc/passwd','f'*47,'/tmp/audio.mp3','a'*48+'/x',None]:
   with self.subTest(key=key),self.assertRaises(share.ShareError):share.completed(key)
 def test_artwork_decode(self):
  with tempfile.TemporaryDirectory() as d:
   self.assertFalse(share.prepare_cover(b'not image',Path(d)/'cover.jpg'));b=io.BytesIO();Image.new('RGB',(1000,800),'blue').save(b,'PNG');self.assertTrue(share.prepare_cover(b.getvalue(),Path(d)/'cover.jpg'))
   with Image.open(Path(d)/'cover.jpg') as im:self.assertEqual(im.size,(600,480))

class ShareJobs64(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.cache=patch('kryonyx.audio_share.paths.cache_dir',return_value=str(self.path));self.cache.start();self.find=patch('kryonyx.audio_share.audiocache.find',return_value=None);self.find.start()
  b=io.BytesIO()
  with wave.open(b,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(44100);f.writeframes(b'\x00\x00'*44100)
  self.audio=b.getvalue();im=io.BytesIO();Image.new('RGB',(100,100),'red').save(im,'PNG');self.cover='data:image/png;base64,'+base64.b64encode(im.getvalue()).decode()
  app=web.Application();app.router.add_get('/tone',lambda r:web.Response(body=self.audio,content_type='audio/wav'));self.up=TestServer(app);await self.up.start_server();self.http=ClientSession();self.jobs=share.Jobs();await self.jobs.start()
 async def asyncTearDown(self):
  await self.jobs.close();await self.http.close();await self.up.close();self.find.stop();self.cache.stop();self.tmp.cleanup()
 async def resolve(self,*args):return args[0],{'url':str(self.up.make_url('/tone')),'mime':'audio/wav'}
 def track(self):return {'id':'yt:sharingtest','title':'Трек · Play','artist':'Автор — Radio','thumbnail':self.cover}
 async def ready(self,j):
  await asyncio.wait_for(self.jobs.jobs[j['token']]['task'],30);return self.jobs.get(j['token'])
 async def test_real_mp3_tags_and_cover(self):
  j=await self.ready(self.jobs.create(self.track(),self.resolve,self.http));self.assertEqual(j['state'],'ready',j);self.assertTrue(j['artwork']);path,name=share.completed(j['token']);self.assertTrue(name.endswith('.mp3'))
  p=await asyncio.create_subprocess_exec('ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(path),stdout=asyncio.subprocess.PIPE);data=json.loads((await p.communicate())[0]);self.assertEqual(data['format']['tags']['title'],'Трек · Play');self.assertEqual(data['format']['tags']['artist'],'Автор — Radio');self.assertTrue(any(s['disposition']['attached_pic'] for s in data['streams']));self.assertGreater(float(data['format']['duration']),.9)
  self.assertFalse((path.parent/'source.bin').exists());self.assertFalse((path.parent/'cover.jpg').exists())
 async def test_missing_artwork_reported(self):
  t=self.track();t['thumbnail']='';j=await self.ready(self.jobs.create(t,self.resolve,self.http));self.assertEqual(j['state'],'ready');self.assertFalse(j['artwork'])
 async def test_error_not_empty_success(self):
  async def fail(*a):raise RuntimeError('secret provider detail')
  j=await self.ready(self.jobs.create(self.track(),fail,self.http));self.assertEqual(j['state'],'error');self.assertNotIn('secret',j['error'])
 async def test_metadata_source_does_not_silently_substitute(self):
  t=self.track();t['id']='sp:metadataonly'
  j=await self.ready(self.jobs.create(t,self.resolve,self.http));self.assertEqual(j['state'],'error');self.assertIn('playable source',j['error'])
 async def test_cancel_cleans_files(self):
  async def slow(*a):await asyncio.sleep(60)
  j=self.jobs.create(self.track(),slow,self.http);await asyncio.sleep(.05);await self.jobs.cancel(j['token']);self.assertFalse((share.root()/j['token']).exists())
 async def test_job_limit(self):
  async def slow(*a):await asyncio.sleep(60)
  self.jobs.create(self.track(),slow,self.http);self.jobs.create(self.track(),slow,self.http)
  with self.assertRaises(share.ShareError):self.jobs.create(self.track(),slow,self.http)
 async def test_expiry(self):
  j=await self.ready(self.jobs.create(self.track(),self.resolve,self.http));p=share.root()/j['token'];os.utime(p,(0,0));self.jobs.sweep();self.assertFalse(p.exists())
 async def test_cover_private_addresses(self):
  for url in ('http://127.0.0.1/private','https://127.0.0.1/private','https://[::1]/private','file:///etc/passwd','/img/../../server.py','https://public.example:bad/file','https://[broken/file'):
   self.assertIsNone(await share.cover_bytes(url))

class ShareRoute64(unittest.IsolatedAsyncioTestCase):
 async def test_route_consent_and_origin(self):
  from aiohttp.test_utils import TestClient
  app=web.Application();app.add_routes([r for r in server.routes if r.path.startswith('/api/audio-share')]);client=TestClient(TestServer(app));await client.start_server()
  try:
   r=await client.post('/api/audio-share',json={});self.assertEqual(r.status,400)
   r=await client.post('/api/audio-share',json={},headers={'Origin':'https://attacker.invalid'});self.assertEqual(r.status,403)
  finally:await client.close()
