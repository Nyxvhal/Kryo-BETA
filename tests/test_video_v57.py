"""Cookie gate + metadata catalog: no YouTube account or public network."""
import asyncio, json, unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request
from kryonyx import server, clipcatalog

READY={'present':True,'signed_in':True,'expired':False,'updated_at':57,'count':8}
class GateTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.cookies=patch.object(server.ytcookies,'state',return_value={});self.state=self.cookies.start()
  self.job=SimpleNamespace(state='paused',resume=AsyncMock(),pause=AsyncMock(),public=lambda:{'state':'paused'})
  self.manager=SimpleNamespace(get=lambda _:self.job,create=AsyncMock(),sessions={'test':self.job})
  self.manager_patch=patch.object(server,'_clip_studio_manager',new=AsyncMock(return_value=self.manager));self.get_manager=self.manager_patch.start()
  app=web.Application();app.add_routes(server.routes);self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):
  await self.client.close();self.manager_patch.stop();self.cookies.stop()
 async def test_cookie_states(self):
  for state in ({},{'present':True,'signed_in':False},{**READY,'expired':True}):
   self.state.return_value=state;self.assertEqual(server._clip_cookie_gate().status,403)
  for state in (READY,{'browser':'firefox'}):
   self.state.return_value=state;self.assertIsNone(server._clip_cookie_gate())
 async def test_create_blocks_before_resolver(self):
  r=await self.client.post('/api/clips/sessions',json={'id':'ytvideo:kJQP7kiw5Fk'});self.assertEqual(r.status,403)
  self.assertEqual((await r.json())['code'],'youtube_cookies_required');self.get_manager.assert_not_awaited();self.manager.create.assert_not_awaited()
 async def test_invalid_options_still_400(self):
  for payload in ({},{'id':'test','quality':999}):
   r=await self.client.post('/api/clips/sessions',json=payload);self.assertEqual(r.status,400)
  self.get_manager.assert_not_awaited()
 async def test_catalog_blocks_before_provider(self):
  with patch.object(server.ytmusic,'video_search',new=AsyncMock()) as search:
   r=await self.client.get('/api/clips/catalog?q=music');self.assertEqual(r.status,403);search.assert_not_awaited()
 async def test_media_and_file_gate_even_cached(self):
  for path in ('media/video','file'):
   r=await self.client.get('/api/clips/sessions/test/'+path);self.assertEqual(r.status,403)
  self.get_manager.assert_not_awaited()
 async def test_resume_blocked_pause_allowed(self):
  r=await self.client.post('/api/clips/sessions/test/control',json={'action':'resume'});self.assertEqual(r.status,403);self.job.resume.assert_not_awaited()
  r=await self.client.post('/api/clips/sessions/test/control',json={'action':'pause'});self.assertEqual(r.status,200);self.job.pause.assert_awaited_once()
 async def test_removal_pauses_running_sessions(self):
  self.job.state='downloading';request=SimpleNamespace(app={'clip_streams':self.manager})
  await server._pause_clips_without_cookies(request);self.job.pause.assert_awaited_once()
 async def test_valid_catalog_is_metadata_only(self):
  self.state.return_value=READY
  with patch.object(server.ytmusic,'video_search',new=AsyncMock(return_value=[{'id':'yt:kJQP7kiw5Fk','title':'Test'}])) as search:
   r=await self.client.get('/api/clips/catalog?q=music&limit=36');self.assertEqual(r.status,200)
   self.assertEqual((await r.json())['items'][0]['id'],'ytvideo:kJQP7kiw5Fk');search.assert_awaited_once_with('music',36);self.get_manager.assert_not_awaited()

class CatalogTests(unittest.IsolatedAsyncioTestCase):
 async def test_singleflight_dedupe_and_no_secrets(self):
  async def provider(q,n):
   await asyncio.sleep(.02)
   return [{'id':'yt:kJQP7kiw5Fk','title':'x','headers':{'Cookie':'secret'}},{'id':'ytvideo:kJQP7kiw5Fk'},{'id':'invalid'}]
  search=AsyncMock(side_effect=provider);c=clipcatalog.Catalog(search)
  a,b=await asyncio.gather(c.get('Music',24,(57,'',8)),c.get('music',24,(57,'',8)))
  self.assertEqual(a,b);self.assertEqual(len(a),1);search.assert_awaited_once();self.assertNotIn('secret',json.dumps(a));self.assertFalse(c.pending)
 async def test_bounded_cache_identity_and_expiry(self):
  search=AsyncMock(return_value=[]);c=clipcatalog.Catalog(search,ttl=.01,max_entries=2)
  for q in ('aa','bb','cc'):await c.get(q,24,(1,))
  self.assertEqual(len(c.cache),2)
  await c.get('cc',24,(1,));self.assertEqual(search.await_count,3)
  await asyncio.sleep(.02);await c.get('cc',24,(1,));self.assertEqual(search.await_count,4)
  await c.get('cc',24,(2,));self.assertEqual(search.await_count,5)
 async def test_failure_releases_singleflight(self):
  c=clipcatalog.Catalog(AsyncMock(side_effect=RuntimeError('test')))
  with self.assertRaises(RuntimeError):await c.get('music',24,())
  self.assertFalse(c.pending);self.assertFalse(c.cache)
 async def test_results_capped(self):
  c=clipcatalog.Catalog(AsyncMock(return_value=[{'id':f'{n:011d}'} for n in range(100)]))
  self.assertEqual(len(await c.get('music',36,())),36)
if __name__=='__main__':unittest.main()
