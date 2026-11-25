import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from kryonyx import lyric_translate as tr, server
from aiohttp.test_utils import TestClient, TestServer

class FakeProvider:
 id='fake-v1'
 def __init__(self, fail=None): self.fail=fail; self.calls=[]
 async def translate_line(self, text, target):
  self.calls.append((text,target))
  if text==self.fail: raise tr.TranslationUnavailable('offline')
  return target+':'+text

class TranslationTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self): tr._cache.clear()
 async def test_positions_unicode_and_immutable_input(self):
  lines=['Hello','','Hello','你好世界','😀 «мир»']; original=copy.deepcopy(lines); p=FakeProvider()
  out=await tr.translate_lines(lines,'ru',p)
  self.assertEqual(lines,original);self.assertEqual([r['index'] for r in out['results']],list(range(5)))
  self.assertEqual([r['translation'] for r in out['results']],['ru:Hello','','ru:Hello','ru:你好世界','ru:😀 «мир»'])
  self.assertEqual(out['fingerprint'],tr.fingerprint(lines));self.assertEqual(out['state'],'complete')
 async def test_languages_and_isolation(self):
  p=FakeProvider()
  for lang in ['ru','en','uk','de','fr','es','ja','ko','zh-CN']:
   self.assertEqual((await tr.translate_lines(['Привет'],lang,p))['results'][0]['translation'],lang+':Привет')
 async def test_invalid_inputs(self):
  for lines,target in [([], 'ru'),(['x']*241,'ru'),(['x'*2001],'ru'),(['x\ny'],'ru'),([{}],'ru'),(['x'],'auto'),(['x'],[]),([' '],'ru'),(['x'*2000]*13,'ru')]:
   with self.subTest(target=target,lines=str(lines)[:20]),self.assertRaises(ValueError): tr.validate(lines,target)
 async def test_partial_retry_and_cache(self):
  p=FakeProvider('fail');first=await tr.translate_lines(['ok','fail'],'en',p);self.assertEqual(first['state'],'partial');self.assertEqual(first['results'][1]['status'],'error')
  p.fail=None;second=await tr.translate_lines(['ok','fail'],'en',p);self.assertEqual(second['state'],'complete');self.assertEqual(p.calls.count(('ok','en')),1)
 async def test_empty_and_bad_multiline_result_are_errors(self):
  p=FakeProvider();p.translate_line=AsyncMock(side_effect=['','a\nb']);out=await tr.translate_lines(['x','y'],'en',p);self.assertEqual([r['status'] for r in out['results']],['error','error']);self.assertEqual(len(tr._cache),0)
 async def test_http_and_malformed_json_are_explicit(self):
  for status,payload in [(429,[]),(500,[]),(200,{}),(200,[[['ok'], ['bad', 2], None]])]:
   context=MagicMock();context.__aenter__=AsyncMock(return_value=SimpleNamespace(status=status,json=AsyncMock(return_value=payload)));context.__aexit__=AsyncMock(return_value=False)
   session=MagicMock();session.post.return_value=context
   with self.subTest(status=status),self.assertRaises(tr.TranslationUnavailable): await tr._request(session,'hello','ru')
  context=MagicMock();context.__aenter__=AsyncMock(return_value=SimpleNamespace(status=200,json=AsyncMock(side_effect=ValueError('malformed'))));context.__aexit__=AsyncMock(return_value=False)
  session=MagicMock();session.post.return_value=context
  with self.assertRaises(tr.TranslationUnavailable): await tr._request(session,'hello','ru')
 async def test_cancel_releases_slot(self):
  p=FakeProvider();started=asyncio.Event()
  async def wait(*args): started.set();await asyncio.sleep(60)
  p.translate_line=wait; task=asyncio.create_task(tr.translate_lines(['x'],'en',p));await started.wait();task.cancel()
  with self.assertRaises(asyncio.CancelledError):await task
  self.assertEqual((await tr.translate_lines(['a'],'en',FakeProvider()))['state'],'complete')

class ApiTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close()
 async def test_consent_origin_types_and_success(self):
  url='/api/lyrics/translate'
  self.assertEqual((await self.client.post(url,json={'lines':['a'],'target':'ru'})).status,400)
  self.assertEqual((await self.client.post(url,json={'consent':True},headers={'Origin':'https://evil.invalid'})).status,403)
  self.assertEqual((await self.client.post(url,json={'consent':True,'lines':[3],'target':'ru'})).status,400)
  with patch.object(tr.GoogleUnofficial,'translate_line',AsyncMock(return_value='Привет')):
   r=await self.client.post(url,json={'consent':True,'lines':['Hello','','Hello'],'target':'ru'});data=await r.json()
  self.assertEqual(r.status,200);self.assertEqual(data['state'],'complete');self.assertEqual([x['status'] for x in data['results']],['ok','empty','ok'])
