"""Real local HTTP upstream + player routes, no provider account required."""
import asyncio,io,json,os,tempfile,unittest,wave,zipfile
from pathlib import Path
from unittest.mock import patch,AsyncMock
import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer,TestClient
from kryonyx import audiovault as v,audiocache as ac,server,avatars,avatarshop,recommend

class VaultTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(v,'cache_dir',return_value=self.tmp.name);self.p.start()
 def tearDown(self):self.p.stop();self.tmp.cleanup()
 def store(self,tid,data=b'abc'*10000,mime='audio/wav'):
  p=Path(self.tmp.name)/'transfer.part';p.write_bytes(data);return v.store(tid,str(p),mime)
 def test_sqlite_not_loose_audio(self):
  token=self.store('a');self.assertTrue(token.startswith('vault:'));self.assertEqual(v.find('a'),token);self.assertEqual(v.mime_for(token),'audio/wav');self.assertEqual(v.stats()['tracks'],1);self.assertEqual(list(Path(v.folder()).glob('*.wav')),[])
 def test_survives_new_connection(self):self.store('b');self.assertIsNotNone(v.find('b'))
 def test_clear_and_generation(self):
  before=v.generation();self.store('c');self.assertEqual(v.clear(),1);self.assertIsNone(v.find('c'));p=Path(self.tmp.name)/'old.part';p.write_bytes(b'x'*20000);self.assertIsNone(v.store('x',str(p),'audio/mpeg',expected_generation=before));self.assertFalse(p.exists())
 def test_stream_only_never_persists(self):
  self.store('x');v.configure('stream',256);self.assertEqual(v.stats()['tracks'],0);self.assertIsNone(self.store('new'));self.assertIsNone(v.find('new'))
 def test_invalid_policy(self):
  for mode,size in [('bad',256),('internal',-1),('internal',True),('internal',999)]:
   with self.assertRaises(ValueError):v.configure(mode,size)
 def test_lru_trim(self):
  self.store('old',b'o'*20000);self.store('new',b'n'*20000);v.trim(25000);self.assertIsNone(v.find('old'));self.assertIsNotNone(v.find('new'))
 def test_legacy_migration(self):
  old=Path(v.folder())/(v.key('legacy')+'.mp3');old.write_bytes(b'a'*20000);self.assertEqual(v.migrate_legacy(),1);self.assertFalse(old.exists());self.assertIsNotNone(v.find('legacy'))
 def test_karaoke_temporary_input(self):
  token=self.store('karaoke');p=v.materialize(token);self.assertEqual(Path(p).read_bytes(),b'abc'*10000);os.remove(p)
 def test_oversized_object_not_saved(self):
  with patch.object(v,'MAX_TRACK',5):self.assertIsNone(self.store('large',b'abcdef'))

class AudioHTTP(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(v,'cache_dir',return_value=self.tmp.name);self.p.start();self.calls=0;self.offline=False
  b=io.BytesIO()
  with wave.open(b,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(b'\0\1'*22050*2)
  self.data=b.getvalue()
  async def upstream(req):
   self.calls+=1
   if self.offline:return web.Response(status=503)
   a,b,part=server.clipstream.ranges(req.headers.get('Range',''),len(self.data));headers={'Content-Type':'audio/wav'}
   if part:headers['Content-Range']=f'bytes {a}-{b}/{len(self.data)}'
   return web.Response(body=self.data[a:b+1],headers=headers,status=206 if part else 200)
  app=web.Application();app.router.add_get('/audio',upstream);self.up=TestServer(app);await self.up.start_server()
  self.resolve=AsyncMock(return_value=('replacement-id',{'url':str(self.up.make_url('/audio')),'mime':'audio/wav'}));self.r=patch.object(server,'_media_for',self.resolve);self.r.start()
  self.client=TestClient(TestServer(server.build_app()));await self.client.start_server()
 async def asyncTearDown(self):
  await self.client.close();await self.up.close();self.r.stop();self.p.stop();self.tmp.cleanup()
 async def test_first_stream_then_offline_hit_no_resolver(self):
  r=await self.client.get('/api/stream?id=original');self.assertEqual(await r.read(),self.data);self.assertEqual(r.headers['X-Kryonyx-Cache'],'miss');n=self.calls;resolved=self.resolve.await_count;self.offline=True
  r=await self.client.get('/api/stream?id=original');self.assertEqual(await r.read(),self.data);self.assertEqual(r.headers['X-Kryonyx-Cache'],'hit');self.assertEqual(self.calls,n);self.assertEqual(self.resolve.await_count,resolved);self.assertEqual(v.stats()['tracks'],1)
 async def test_browser_zero_range_populates_cache(self):
  r=await self.client.get('/api/stream?id=zero',headers={'Range':'bytes=0-'});self.assertEqual(await r.read(),self.data);
  for _ in range(100):
   if v.find('zero'):break
   await asyncio.sleep(.01)
  self.assertIsNotNone(v.find('zero'))
 async def test_cached_ranges_and_head(self):
  r=await self.client.get('/api/stream?id=range');await r.read();self.offline=True
  for h,a,b in [('bytes=12-38',12,38),('bytes=-64',len(self.data)-64,len(self.data)-1),('bytes=44-',44,len(self.data)-1)]:
   r=await self.client.get('/api/stream?id=range',headers={'Range':h});self.assertEqual(r.status,206);self.assertEqual(await r.read(),self.data[a:b+1]);self.assertEqual(r.headers['Content-Range'],f'bytes {a}-{b}/{len(self.data)}')
  r=await self.client.head('/api/stream?id=range',headers={'Range':'bytes=1-4'});self.assertEqual(r.status,206);self.assertEqual(await r.read(),b'');self.assertEqual(r.headers['Content-Length'],'4')
  r=await self.client.get('/api/stream?id=range',headers={'Range':'bytes=999999-'});self.assertEqual(r.status,416)
 async def test_partial_not_marked_complete(self):
  r=await self.client.get('/api/stream?id=part',headers={'Range':'bytes=100-300'});self.assertEqual(r.status,206);self.assertEqual(await r.read(),self.data[100:301]);self.assertIsNone(v.find('part'))
 async def test_stream_only_has_no_audio_object(self):
  v.configure('stream',256);r=await self.client.get('/api/stream?id=ephemeral');self.assertEqual(await r.read(),self.data);self.assertEqual(v.stats()['tracks'],0);self.assertFalse(list(Path(v.folder()).glob('*.part')))
 async def test_policy_api_and_clear(self):
  r=await self.client.put('/api/cache/audio',json={'mode':'internal','limit_mb':256});self.assertEqual(r.status,200)
  r=await self.client.put('/api/cache/audio',json={'mode':'internal','limit_mb':999});self.assertEqual(r.status,400)
  r=await self.client.get('/api/stream?id=clear');await r.read();r=await self.client.delete('/api/cache/audio');self.assertEqual((await r.json())['removed'],1)
 async def test_avatar_catalog_and_single_download(self):
  r=await self.client.get('/api/avatars');d=await r.json();self.assertEqual(len(d['items']),233);self.assertEqual(sum(i.get('collection')=='signature' for i in d['items']),20)
  item=next(x for x in d['items'] if x['collection']=='signature')
  for fmt in ('png','svg'):
   r=await self.client.get('/api/avatarshop/download/'+item['id']+'?format='+fmt);self.assertEqual(r.status,200);self.assertIn('attachment',r.headers['Content-Disposition']);self.assertTrue(await r.read())
  r=await self.client.get('/api/avatarshop/download/missing');self.assertEqual(r.status,404)
 async def test_pack_contains_assets_manifest_rights(self):
  with patch.object(avatarshop,'cache_dir',return_value=self.tmp.name):
   r=await self.client.get('/api/avatarshop/pack?collection=signature');self.assertEqual(r.status,200);z=zipfile.ZipFile(io.BytesIO(await r.read()));self.assertEqual(len([n for n in z.namelist() if n.endswith('.png')]),20);self.assertEqual(len([n for n in z.namelist() if n.endswith('.svg')]),20);self.assertIn('manifest.json',z.namelist());self.assertTrue(any(n.startswith('RIGHTS/') for n in z.namelist()))
  r=await self.client.get('/api/avatarshop/pack?collection=../../bad');self.assertEqual(r.status,400)

class RecommendationTests(unittest.IsolatedAsyncioTestCase):
 def test_dedupe_and_blocked(self):
  tracks=[{'id':'a','title':'Song','artist':'A'},{'id':'b','title':'Song','artist':'A'},{'id':'c','title':'Other','artist':'Bad'}];self.assertEqual([t['id'] for t in recommend._score(tracks,{},set(),{'bad'})],['a'])
 def test_artist_diversity(self):
  tracks=[{'id':str(i),'title':str(i),'artist':'A' if i<8 else 'B'} for i in range(10)];out=recommend._score(tracks,{},set(),set());self.assertEqual([t['artist'] for t in out[:4]],['A','A','B','B'])
 async def test_more_rows_and_exact_limit(self):
  async def search(q,**kwargs):return {'tracks':[{'id':q+str(i),'title':q+str(i),'artist':'artist'+str(i)} for i in range(30)]}
  recommend.invalidate()
  with tempfile.TemporaryDirectory() as temp,patch.object(recommend,'cache_dir',return_value=temp),patch.object(recommend.storage,'top_artists',return_value=[]),patch.object(recommend.storage,'recent_seed_tracks',return_value=[]),patch.object(recommend.storage,'played_ids',return_value=set()),patch.object(recommend.storage,'disliked_artists',return_value=[]),patch.object(recommend.storage,'list_likes',return_value=[]),patch.object(recommend.storage,'history',return_value=[]),patch.object(recommend.providers,'search',side_effect=search),patch.object(recommend,'_collection_rows',AsyncMock(return_value=[])),patch.object(recommend.extras,'fill_thumbnails',AsyncMock()):
   rows=await recommend.build_rows(16);self.assertEqual(len(rows),16);self.assertTrue(all(4<=len(r['items'])<=60 for r in rows));rows8=await recommend.build_rows(8);self.assertEqual(len(rows8),8);ids=[t['id'] for r in rows for t in r['items']];self.assertEqual(len(ids),len(set(ids)))
  recommend.invalidate()

class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
 async def test_active_reader_does_not_block_new_cache_write(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(v,'cache_dir',return_value=tmp):
   p=Path(tmp)/'one.part';p.write_bytes(b'a'*20000);v.store('one',str(p),'audio/wav');c=v.connect();c.execute('BEGIN');c.execute('SELECT size FROM audio').fetchone()
   try:
    p=Path(tmp)/'two.part';p.write_bytes(b'b'*20000);await asyncio.wait_for(asyncio.to_thread(v.store,'two',str(p),'audio/wav'),2);self.assertIsNotNone(v.find('two'))
   finally:c.close()
 async def test_interrupted_tee_does_not_commit(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(v,'cache_dir',return_value=tmp):
   async def source(req):return web.Response(body=b'a'*50000,content_type='audio/wav')
   app=web.Application();app.router.add_get('/source',source);up=TestServer(app);await up.start_server()
   async def broken(chunk):raise ConnectionResetError('listener left')
   try:
    async with aiohttp.ClientSession() as session:
     with self.assertRaises(ConnectionResetError):await ac.tee(session,'partial',{'url':str(up.make_url('/source')),'mime':'audio/wav'},on_chunk=broken)
    self.assertIsNone(v.find('partial'));self.assertFalse(list(Path(v.folder()).glob('*.part')))
   finally:await up.close()
 async def test_prefetch_commits_and_uses_cache_next_time(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(v,'cache_dir',return_value=tmp):
   data=b'a'*50000
   async def source(req):return web.Response(body=data,content_type='audio/wav')
   app=web.Application();app.router.add_get('/source',source);up=TestServer(app);await up.start_server()
   try:
    async with aiohttp.ClientSession() as session:
     token=await ac.download(session,'prefetch',{'url':str(up.make_url('/source')),'mime':'audio/wav'});self.assertEqual(token,v.find('prefetch'))
    self.assertEqual(v.stats()['tracks'],1)
   finally:await up.close()

class LargeTransferTests(unittest.IsolatedAsyncioTestCase):
 async def transfer(self,ignore=False,tee=False,bad=False):
  data=bytes(range(256))*28672
  async def source(req):
   h=req.headers.get('Range','');a,b,part=server.clipstream.ranges(h,len(data))
   if ignore and h!='bytes=0-1':a,b,part=0,len(data)-1,False
   headers={'Content-Type':'audio/mpeg'}
   if part:headers['Content-Range']=f'bytes {a+int(bad)}-{b}/{len(data)}'
   return web.Response(body=data[a:b+1],status=206 if part else 200,headers=headers)
  with tempfile.TemporaryDirectory() as tmp,patch.object(v,'cache_dir',return_value=tmp):
   app=web.Application();app.router.add_get('/source',source);up=TestServer(app);await up.start_server()
   try:
    async with aiohttp.ClientSession() as session:
     media={'url':str(up.make_url('/source')),'mime':'audio/mpeg'}
     if tee:
      received=bytearray()
      async def consume(chunk):received.extend(chunk)
      await ac.tee(session,'large',media,on_chunk=consume);self.assertEqual(bytes(received),data)
     else:await ac.download(session,'large',media)
     token=v.find('large');self.assertIsNotNone(token);p=v.materialize(token);self.assertEqual(Path(p).read_bytes(),data);os.remove(p)
   finally:await up.close()
 async def test_parallel_download_integrity(self):await self.transfer()
 async def test_ignored_ranges_fall_back_without_corruption(self):await self.transfer(ignore=True)
 async def test_play_while_caching_segments_integrity(self):await self.transfer(tee=True)

class RecommendationCacheTests(unittest.TestCase):
 def test_cache_does_not_leak_old_source_selection(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(recommend,'cache_dir',return_value=tmp),patch.object(recommend,'_user_sources',return_value=['archive']):
   recommend._save_rows([{'id':'demo','items':[]}]);self.assertIsNotNone(recommend._load_rows())
   with patch.object(recommend,'_user_sources',return_value=['youtube']):self.assertIsNone(recommend._load_rows())
 def test_unicode_identity_does_not_merge_all_non_latin_tracks(self):
  self.assertNotEqual(recommend._norm('夜空'),recommend._norm('春天'));self.assertEqual(recommend._norm('Björk'), 'björk')

class KaraokeVaultTests(unittest.TestCase):
 def test_existing_audio_binding_survives_migration_and_rejects_changed_audio(self):
  from kryonyx import karaoke_jobs
  from test_karaoke import sample
  import hashlib
  with tempfile.TemporaryDirectory() as tmp,patch.object(v,'cache_dir',return_value=tmp),patch.object(karaoke_jobs,'data_dir',return_value=tmp):
   data=b'original'*4000;p=Path(tmp)/'one.part';p.write_bytes(data);v.store('bound',str(p),'audio/wav');doc=sample();doc['source_fingerprint']={'audio_sha256':hashlib.sha256(data).hexdigest()};doc['binding']={'source':'audio-cache','stat':[len(data),123]};karaoke_jobs.save_track('bound',doc);self.assertIsNotNone(karaoke_jobs.load_track('bound'));p.write_bytes(b'changed'*4000);v.store('bound',str(p),'audio/wav');self.assertIsNone(karaoke_jobs.load_track('bound'))
