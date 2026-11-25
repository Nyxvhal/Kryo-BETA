"""v62 cancellation contract; no network or account credentials."""
import asyncio,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp import web
from kryonyx import server
class Cancellation62(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tasks=[]
  self.old=server._prefetch_tasks30
  server._prefetch_tasks30=set()
 async def asyncTearDown(self):
  for t in self.tasks:t.cancel()
  await asyncio.gather(*self.tasks,return_exceptions=True)
  server._prefetch_tasks30=self.old
 async def task(self,name):
  t=asyncio.create_task(asyncio.Event().wait(),name='prefetch:'+name)
  self.tasks.append(t);server._prefetch_tasks30.add(t);await asyncio.sleep(0);return t
 def req(self,query,origin=None):
  return SimpleNamespace(query=query,headers={'Origin':origin} if origin else {},scheme='http',host='127.0.0.1:8789')
 async def test_cancel_only_obsolete(self):
  current=await self.task('current');future=await self.task('future')
  r=await server.api_prefetch(self.req({'cancel':'1','current':'current'}))
  self.assertEqual(json.loads(r.text)['cancelled'],1);self.assertTrue(future.cancelled());self.assertFalse(current.done())
 async def test_cancel_no_work_is_idempotent(self):
  r=await server.api_prefetch(self.req({'cancel':'1'}));self.assertEqual(json.loads(r.text)['cancelled'],0)
 async def test_cross_origin_cannot_cancel(self):
  task=await self.task('future')
  with self.assertRaises(web.HTTPForbidden):await server.api_prefetch(self.req({'cancel':'1'},'https://untrusted.invalid'))
  self.assertFalse(task.done())
 async def test_evicted_download_never_claims_cached(self):
  with patch.dict(server._prefetch_status61,{'v62-evicted':{'state':'downloaded','cached':True}}),patch.object(server.audiocache,'find',return_value=None):
   r=await server.api_prefetch(self.req({'id':'v62-evicted','status':'1'}));self.assertEqual(json.loads(r.text),{'state':'error','cached':False})
 async def test_file_presence_is_authoritative(self):
  with patch.object(server.audiocache,'find',return_value='/fixture/audio.wav'):
   r=await server.api_prefetch(self.req({'id':'v62-cached','status':'1'}));self.assertEqual(json.loads(r.text),{'state':'downloaded','cached':True})
