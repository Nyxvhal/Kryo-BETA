"""Regressions for safe manual lyrics fallback and owned export workers."""
import asyncio, json, os, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
from kryonyx import server, audio_share as share

class LyricsFallback(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  server._lyrics_cache.clear(); self.client=TestClient(TestServer(server.build_app())); await self.client.start_server()
  self.patches=[patch.object(server.karaoke_jobs,'load_track',return_value=None),patch.object(server.karaoke_jobs,'binding',return_value=Path('/nonexistent/kryo-test'))]
  for p in self.patches:p.start()
 async def asyncTearDown(self):
  for p in self.patches:p.stop()
  await self.client.close();server._lyrics_cache.clear()
 async def get(self,**params):
  r=await self.client.get('/api/lyrics',params=params);self.assertEqual(r.status,200);return await r.json()
 async def test_unverified_fallback_never_overrides_auto_rejection_or_bad_pick(self):
  fallback=AsyncMock(return_value=[{'time':None,'text':'Wrong lyrics'}])
  with patch.object(server,'_lyrics_lookup',AsyncMock(return_value={})),patch.object(server,'_lyrics_by_id',AsyncMock(return_value={})),patch.object(server.extras,'plain_lyrics',fallback):
   for picked in ('','12345','ovh:not json','ovh:["", "Title"]'):
    result=await self.get(title='Beauty And A Beat',artist='Justin Bieber',lrc=picked)
    self.assertFalse(result['lines'])
   fallback.assert_not_awaited()
 async def test_explicit_manual_fallback_uses_requested_identity_and_is_labelled(self):
  fallback=AsyncMock(return_value=[{'time':None,'text':'Manually selected words'}])
  with patch.object(server,'_lyrics_lookup',AsyncMock()) as lookup,patch.object(server.extras,'plain_lyrics',fallback):
   result=await self.get(title='Track metadata',artist='Other artist',lrc='ovh:'+json.dumps(['Chosen artist','Chosen title']))
   self.assertEqual(result['source'],'lyrics.ovh');self.assertFalse(result['identity_verified']);self.assertEqual(result['lines'][0]['text'],'Manually selected words')
   lookup.assert_not_awaited();fallback.assert_awaited_once_with('Chosen artist','Chosen title')

class ShareOwnership(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.p=patch.object(share.paths,'cache_dir',return_value=self.tmp.name);self.p.start();self.jobs=share.Jobs();await self.jobs.start()
 async def asyncTearDown(self):
  await self.jobs.close();self.p.stop();self.tmp.cleanup()
 def track(self):return {'id':'yt:race','title':'Track','artist':'Artist','thumbnail':''}
 async def test_expiry_does_not_delete_or_forget_active_job(self):
  started=asyncio.Event()
  async def slow(*a):started.set();await asyncio.Event().wait()
  with patch.object(share.audiocache,'find',return_value=None):
   job=self.jobs.create(self.track(),slow,None);await asyncio.wait_for(started.wait(),2)
   folder=share.root()/job['token'];os.utime(folder,(0,0));self.jobs.sweep()
   self.assertTrue(folder.exists());self.assertIn(job['token'],self.jobs.jobs);self.assertFalse(self.jobs.jobs[job['token']]['task'].done())
   await self.jobs.cancel(job['token']);self.assertFalse(folder.exists())
 async def test_cancel_waits_for_materialize_and_cleans_result(self):
  entered=threading.Event();release=threading.Event();created=self.path/'temporary-materialized'
  def materialize(_):entered.set();release.wait(5);created.write_bytes(b'audio');return str(created)
  try:
   with patch.object(share.audiocache,'find',return_value='vault:x'),patch.object(share.audiovault,'materialize',side_effect=materialize),patch.object(share.clipcache,'ffmpeg_exe',return_value='ffmpeg'):
    job=self.jobs.create(self.track(),None,None);self.assertTrue(await asyncio.to_thread(entered.wait,2));folder=share.root()/job['token']
    cancel=asyncio.create_task(self.jobs.cancel(job['token']));await asyncio.sleep(.05);self.assertFalse(cancel.done());self.assertTrue(folder.exists())
    os.utime(folder,(0,0));self.jobs.sweep();self.assertTrue(folder.exists());self.assertIn(job['token'],self.jobs.jobs)
    release.set();await asyncio.wait_for(cancel,3);self.assertFalse(folder.exists());self.assertFalse(created.exists())
  finally:release.set()
 async def test_cancel_waits_for_cover_write_before_deleting_directory(self):
  entered=threading.Event();release=threading.Event()
  def cover(_data,path):entered.set();release.wait(5);Path(path).write_bytes(b'cover');return True
  async def bytes_(_):return b'image'
  async def resolve(*a):raise AssertionError('source should be cached')
  def materialize(_):
   p=self.path/'source';p.write_bytes(b'audio');return str(p)
  try:
   with patch.object(share.audiocache,'find',return_value='vault:x'),patch.object(share.audiovault,'materialize',side_effect=materialize),patch.object(share,'cover_bytes',side_effect=bytes_),patch.object(share,'prepare_cover',side_effect=cover),patch.object(share.clipcache,'ffmpeg_exe',return_value='ffmpeg'):
    job=self.jobs.create(self.track(),resolve,None);self.assertTrue(await asyncio.to_thread(entered.wait,2));folder=share.root()/job['token']
    cancel=asyncio.create_task(self.jobs.cancel(job['token']));await asyncio.sleep(.05);self.assertFalse(cancel.done());self.assertTrue(folder.exists());release.set();await asyncio.wait_for(cancel,3);self.assertFalse(folder.exists())
  finally:release.set()

class ModelOwnership(unittest.IsolatedAsyncioTestCase):
 async def test_cancel_waits_for_model_extraction_before_removing_download(self):
  import hashlib, io, zipfile
  from types import SimpleNamespace
  from kryonyx import ai_models
  member=b'weights'*100;buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w') as z:z.writestr('weights.dat',member)
  archive=buf.getvalue();sha=lambda b:hashlib.sha256(b).hexdigest()
  spec={'file':'model.bin','url':'https://models.example/test','size':len(archive),'sha256':sha(archive),'member':'weights.dat','member_size':len(member),'member_sha256':sha(member)}
  class Content:
   async def iter_chunked(self,n):yield archive
  class Response:
   status=200;url=SimpleNamespace(scheme='https');content=Content()
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
  class Session:
   def get(self,*a,**kw):return Response()
  async def factory():return Session()
  entered=threading.Event();release=threading.Event();orig=ai_models._extract_member
  def extract(part,spec,target):entered.set();release.wait(5);self.assertTrue(part.exists());return orig(part,spec,target)
  with tempfile.TemporaryDirectory() as tmp,patch.object(ai_models,'data_dir',return_value=tmp),patch.dict(ai_models.MODELS,{'fixture':spec}),patch.object(ai_models,'_extract_member',side_effect=extract):
   d=ai_models.Downloads();d.start(['fixture'],factory)
   try:
    self.assertTrue(await asyncio.to_thread(entered.wait,2));part=ai_models.folder()/'model.bin.download';self.assertTrue(part.exists());d.task.cancel();await asyncio.sleep(.05);self.assertFalse(d.task.done());self.assertTrue(part.exists());release.set()
    with self.assertRaises(asyncio.CancelledError):await d.task
    self.assertFalse(part.exists());self.assertEqual(ai_models.path('fixture').read_bytes(),member);self.assertEqual(d.state['fixture']['stage'],'cancelled')
   finally:release.set()
