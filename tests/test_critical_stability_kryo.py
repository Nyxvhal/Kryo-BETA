"""Deterministic concurrency/identity regressions: real SQLite and local HTTP only."""
import asyncio
import concurrent.futures
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from kryonyx import audiovault as v, audiocache, clipcache, server
from types import SimpleNamespace

class VaultConcurrency(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(v,'cache_dir',return_value=self.tmp.name);self.patch.start()
  self.data=bytes(range(256))*8192
 def store(self,name,data=None):
  p=Path(self.tmp.name)/(name+'.part');p.write_bytes(data or self.data);return v.store(name,str(p),'audio/wav')
 async def asyncTearDown(self):self.patch.stop();self.tmp.cleanup()
 async def test_thread_owned_connections_concurrent_read_write_stats(self):
  token=self.store('seed');errors=[]
  def work(i):
   try:
    if i%4==0:self.store('write'+str(i),bytes([i%255])*30000)
    elif i%4==1:assert v.find('seed')==token
    elif i%4==2:assert v.stats()['tracks']>=1
    else:assert v.fingerprint(token)
   except Exception as e:errors.append(e)
  with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
   await asyncio.get_running_loop().run_in_executor(None,lambda:list(executor.map(work,range(80))))
  self.assertEqual(errors,[])
  with v.connect() as c:self.assertEqual(c.execute('PRAGMA journal_mode').fetchone()[0].lower(),'wal');self.assertEqual(c.execute('PRAGMA busy_timeout').fetchone()[0],30000)
 async def test_rollback_keeps_previous_committed_value(self):
  token=self.store('seed',b'original'*4000);p=Path(self.tmp.name)/'replacement.part';p.write_bytes(b'replaced'*4000)
  with patch.object(v,'_meta_for',side_effect=ValueError('metadata')):
   with self.assertRaises(ValueError):v.store('seed',str(p),'audio/wav')
  path=v.materialize(token);self.assertEqual(Path(path).read_bytes(),b'original'*4000);os.unlink(path)
 async def test_cancelled_worker_is_drained_before_resource_closed(self):
  entered=threading.Event();release=threading.Event();closed=threading.Event()
  def slow():
   entered.set();release.wait(5);self.assertFalse(closed.is_set());return 1
  async def owner():
   try:await v.run_blocking_owned(slow)
   finally:closed.set()
  task=asyncio.create_task(owner());self.assertTrue(await asyncio.to_thread(entered.wait,2));task.cancel();await asyncio.sleep(.05);self.assertFalse(closed.is_set());self.assertFalse(task.done());task.cancel();release.set()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertTrue(closed.is_set())
 async def test_cancelled_materialization_cleans_worker_result(self):
  entered=threading.Event();release=threading.Event();path=Path(self.tmp.name)/'decoded.tmp'
  def make():entered.set();release.wait(5);path.write_bytes(b'decoded');return str(path)
  task=asyncio.create_task(v.run_blocking_owned(make,_cancel_cleanup=os.remove))
  self.assertTrue(await asyncio.to_thread(entered.wait,2));task.cancel();await asyncio.sleep(.05);self.assertFalse(task.done());release.set()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertFalse(path.exists())
 async def test_parallel_legacy_migration_is_single_copy(self):
  path=Path(v.folder())/(v.key('old')+'.mp3');path.write_bytes(self.data)
  results=await asyncio.gather(*(asyncio.to_thread(v.find,'old') for _ in range(12)))
  self.assertEqual(len(set(results)),1);self.assertTrue(results[0].startswith('vault:'));self.assertEqual(v.stats()['tracks'],1)
 async def test_reopen_and_independent_connections(self):
  token=self.store('persist');a=v.connect();b=v.connect()
  a.close();self.assertEqual(b.execute('SELECT count(*) FROM audio').fetchone()[0],1);b.close()
  self.assertEqual(v.find('persist'),token);path=v.materialize(token);self.assertEqual(Path(path).read_bytes(),self.data);os.unlink(path)
 async def test_stream_statistics_eviction_and_parallel_requests(self):
  self.store('play');started=asyncio.Event();resume=asyncio.Event();original=v.run_blocking_owned
  async def gated(fn,*args,**kwargs):
   if isinstance(getattr(fn,'__self__',None),sqlite3.Blob) and getattr(fn,'__name__','')=='read':
    started.set();await resume.wait()
   return await original(fn,*args,**kwargs)
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  try:
   with patch.object(v,'run_blocking_owned',side_effect=gated):
    responses=await asyncio.gather(*(client.get('/api/stream?id=play') for _ in range(4)))
    await asyncio.wait_for(started.wait(),3)
    stats=await asyncio.gather(*(client.get('/api/cache/audio') for _ in range(8)))
    self.assertTrue(all(r.status==200 for r in stats));await asyncio.to_thread(v.trim,0)
    self.assertIsNone(v.find('play'));resume.set()
    bodies=await asyncio.wait_for(asyncio.gather(*(r.read() for r in responses)),10)
    self.assertTrue(all(body==self.data for body in bodies))
  finally:resume.set();await client.close()
 async def test_shutdown_waits_for_cancelled_prefetch_worker(self):
  entered=threading.Event();release=threading.Event();finished=threading.Event()
  def work():entered.set();release.wait(5);finished.set()
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  task=asyncio.create_task(v.run_blocking_owned(work));server._prefetch_tasks30.add(task);task.add_done_callback(server._prefetch_tasks30.discard)
  try:
   self.assertTrue(await asyncio.to_thread(entered.wait,2));shutdown=asyncio.create_task(client.close());await asyncio.sleep(.1)
   self.assertFalse(shutdown.done());self.assertFalse(finished.is_set());release.set();await asyncio.wait_for(shutdown,5)
   self.assertTrue(finished.is_set());self.assertTrue(task.done());self.assertNotIn(task,server._prefetch_tasks30)
  finally:release.set();await client.close()
 async def test_shutdown_while_live_http_cache_read_is_running(self):
  self.store('shutdown-stream');entered=threading.Event();release=threading.Event();finished=threading.Event();original=v.run_blocking_owned
  async def delayed(fn,*args,**kwargs):
   if isinstance(getattr(fn,'__self__',None),sqlite3.Blob) and getattr(fn,'__name__','')=='read':
    def read():
     entered.set();release.wait(5)
     try:return fn(*args,**kwargs)
     finally:finished.set()
    return await original(read)
   return await original(fn,*args,**kwargs)
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  try:
   with patch.object(v,'run_blocking_owned',side_effect=delayed):
    response=await client.get('/api/stream?id=shutdown-stream');self.assertEqual(response.status,200)
    self.assertTrue(await asyncio.to_thread(entered.wait,2));shutdown=asyncio.create_task(client.close());await asyncio.sleep(.1)
    self.assertFalse(shutdown.done());self.assertFalse(finished.is_set());release.set();await asyncio.wait_for(shutdown,5);self.assertTrue(finished.is_set())
  finally:release.set();await client.close()
 async def test_shutdown_drains_detached_tasks_and_clip_jobs(self):
  started=asyncio.Event();finished=[]
  async def job(name):
   try:started.set();await asyncio.Event().wait()
   finally:finished.append(name)
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  detached=server._background(client.server.app,job('detached'))
  clip=asyncio.create_task(job('clip'))
  with patch.dict(clipcache._jobs,{'test-shutdown':SimpleNamespace(task=clip)}):
   await asyncio.wait_for(started.wait(),2);await asyncio.sleep(.01);await client.close()
   self.assertTrue(detached.done());self.assertTrue(clip.done());self.assertCountEqual(finished,['detached','clip'])
 async def test_serve_cancellation_waits_for_inflight_blob_read(self):
  entered=threading.Event();release=threading.Event();closed=threading.Event();used_closed=threading.Event()
  class Blob:
   def __enter__(self):return self
   def __exit__(self,*args):closed.set()
   def seek(self,n):pass
   def read(self,n):
    entered.set();release.wait(5)
    if closed.is_set():used_closed.set()
    return b'x'
  class Result:
   def fetchone(self):return (1,'audio/wav',1)
  class Conn:
   def execute(self,*args):return Result()
   def blobopen(self,*args,**kwargs):return Blob()
   def close(self):pass
  class Response:
   def __init__(self,**kwargs):pass
   async def prepare(self,request):pass
   async def write(self,chunk):pass
   async def write_eof(self):pass
  request=SimpleNamespace(headers={},method='GET')
  with patch.object(v,'connect',return_value=Conn()),patch.object(web,'StreamResponse',Response):
   task=asyncio.create_task(v.serve(request,'vault:key'))
   try:
    self.assertTrue(await asyncio.to_thread(entered.wait,2));task.cancel();await asyncio.sleep(.05)
    self.assertFalse(closed.is_set());release.set()
    with self.assertRaises(asyncio.CancelledError):await task
    self.assertTrue(closed.is_set());self.assertFalse(used_closed.is_set())
   finally:release.set()
 async def test_cancel_download_does_not_delete_part_while_commit_owns_it(self):
  async def upstream(req):return web.Response(body=self.data,content_type='audio/wav')
  app=web.Application();app.router.add_get('/audio',upstream);up=TestServer(app);await up.start_server()
  entered=threading.Event();release=threading.Event();store=v.store
  def slow_store(*args,**kwargs):entered.set();release.wait(5);return store(*args,**kwargs)
  try:
   async with aiohttp.ClientSession() as session:
    with patch.object(v,'store',side_effect=slow_store):
     task=asyncio.create_task(audiocache.download(session,'cancelled',{'url':str(up.make_url('/audio')),'mime':'audio/wav'}))
     self.assertTrue(await asyncio.to_thread(entered.wait,3));task.cancel();await asyncio.sleep(.05)
     self.assertTrue(Path(audiocache.paths_for('cancelled',{'mime':'audio/wav'})[0]).exists());self.assertFalse(task.done())
     release.set()
     with self.assertRaises(asyncio.CancelledError):await task
     token=v.find('cancelled');self.assertIsNotNone(token);path=v.materialize(token);self.assertEqual(Path(path).read_bytes(),self.data);os.unlink(path)
  finally:release.set();await up.close()
 async def test_eviction_between_find_and_open_resolves_source(self):
  self.store('evicted');data=b'FALLBACK'*6000
  async def upstream(req):return web.Response(body=data,content_type='audio/wav')
  app=web.Application();app.router.add_get('/audio',upstream);up=TestServer(app);await up.start_server()
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  try:
   with patch.object(v,'serve',AsyncMock(side_effect=web.HTTPNotFound())),patch.object(server,'_media_for',AsyncMock(return_value=('evicted',{'url':str(up.make_url('/audio')),'mime':'audio/wav'}))):
    response=await client.get('/api/stream?id=evicted&q=any');self.assertEqual(response.status,200);self.assertEqual(await response.read(),data)
  finally:await client.close();await up.close()
 async def test_many_tracks_stream_across_restart(self):
  expected={f'track{i}':bytes([i])*50000 for i in range(8)}
  for k,data in expected.items():self.store(k,data)
  for cycle in range(2):
   client=TestClient(TestServer(server.build_app()));await client.start_server()
   try:
    for k,data in expected.items():
     r=await client.get('/api/stream?id='+k);self.assertEqual(r.status,200);self.assertEqual(await r.read(),data)
   finally:await client.close()

class LyricsIdentity(unittest.IsolatedAsyncioTestCase):
 def row(self,artist,title,duration=227,synced=True,**kw):
  return {'id':kw.pop('id',1),'artistName':artist,'trackName':title,'duration':duration,'syncedLyrics':'[00:01]one\n[00:02]two\n[00:03]three' if synced else '', 'plainLyrics':'one\ntwo\nthree',**kw}
 def test_exact_identity_beats_remix_cover_and_sync(self):
  song='Beauty And A Beat';artist='Justin Bieber'
  exact=self.row(artist,song,synced=False);remix=self.row('DJ Laszlo',song+' (Remix)',synced=True);cover=self.row('Alex Goot',song+' (Cover)',synced=True)
  scores=[server._lyrics_score(x,song,artist,227) for x in (exact,remix,cover)]
  self.assertGreater(scores[0],scores[1]);self.assertGreater(scores[0],scores[2]);self.assertEqual(scores[1:],[-1000,-1000])
 def test_version_duration_and_recording_id_rejection(self):
  row=self.row('Justin Bieber','Beauty And A Beat')
  self.assertEqual(server._lyrics_score(row,'Beauty And A Beat (Remix)','Justin Bieber',227),-1000)
  self.assertEqual(server._lyrics_score(row,'Beauty And A Beat','Justin Bieber',400),-1000)
  self.assertEqual(server._lyrics_score({**row,'recordingMbid':'other'},'Beauty And A Beat','Justin Bieber',227,'wanted'),-1000)
  self.assertGreater(server._lyrics_score({**row,'recordingMbid':'wanted'},'Beauty And A Beat','Justin Bieber',227,'wanted'),0)
  self.assertEqual(server._lyrics_score(row,'Different song','Justin Bieber',227),-1000)
  self.assertEqual(server._lyrics_score(row,'Beauty And A Beat','',227),-1000)
 async def test_lookup_refuses_wrong_versions_and_selects_original(self):
  original=self.row('Justin Bieber','Beauty And A Beat',id=3,synced=False)
  cover=self.row('Alex Goot','Beauty And A Beat (Cover)',id=1)
  remix=self.row('DJ Laszlo','Beauty And A Beat (Remix)',id=2)
  class Response:
   status=200
   def __init__(self,rows):self.rows=rows
   async def __aenter__(self):return self
   async def __aexit__(self,*_):pass
   async def json(self,**kw):return self.rows
  class Session:
   def __init__(self,rows):self.rows=rows
   def get(self,*a,**kw):return Response(self.rows)
  with patch.object(server,'http',AsyncMock(return_value=Session([cover,remix,original]))):
   result=await server._lyrics_lookup('Beauty And A Beat','Justin Bieber',227);self.assertEqual(result['id'],3)
  with patch.object(server,'http',AsyncMock(return_value=Session([cover,remix]))):
   self.assertEqual(await server._lyrics_lookup('Beauty And A Beat','Justin Bieber',227),{})
 async def test_api_does_not_cache_empty_response_or_cross_track_identity(self):
  server._lyrics_cache.clear();row=self.row('Justin Bieber','Beauty And A Beat',synced=False)
  lookup=AsyncMock(side_effect=[{},row,row]);fallback=AsyncMock(return_value=[])
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  try:
   with patch.object(server,'_lyrics_lookup',lookup),patch.object(server.extras,'plain_lyrics',fallback),patch.object(server.karaoke_jobs,'load_track',return_value=None),patch.object(server.karaoke_jobs,'binding',return_value=Path('/nonexistent/kryo-test')):
    query='title=Beauty+And+A+Beat&artist=Justin+Bieber&duration=227.5'
    first=await (await client.get('/api/lyrics?track_id=yt:first&'+query)).json();self.assertFalse(first['lines'])
    second=await (await client.get('/api/lyrics?track_id=yt:first&'+query)).json();self.assertTrue(second['lines'])
    await (await client.get('/api/lyrics?track_id=yt:second&'+query)).json()
    self.assertEqual(lookup.await_count,3);self.assertEqual(lookup.await_args.args[2],227.5)
  finally:await client.close();server._lyrics_cache.clear()
 def test_youtube_title_noise_and_case(self):
  row=self.row('Justin Bieber','Beauty and a Beat')
  self.assertGreater(server._lyrics_score(row,'Justin Bieber - Beauty and a Beat (Official Video)','Justin Bieber',227),0)

if __name__=='__main__':unittest.main()
