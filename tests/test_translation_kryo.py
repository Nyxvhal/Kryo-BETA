import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from kryonyx import lyric_translate as tr, server
from aiohttp.test_utils import TestClient, TestServer

class TranslationTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  tr._memory_cache.clear()
  self._disk=patch.object(tr,'_load_disk_cache',return_value={});self._save=patch.object(tr,'_save_disk_cache')
  self._disk.start();self._save.start()
 async def asyncTearDown(self):
  self._disk.stop();self._save.stop()
 async def test_positions_unicode_and_immutable_input(self):
  lines=['Hello','','Hello','你好世界','😀 «мир»']; original=copy.deepcopy(lines)
  async def fake_google(session,text,source,target): return target+':'+text,'en'
  with patch.object(tr,'_translate_line_google',side_effect=fake_google):
   out=await tr.translate_offline(lines,'ru','auto')
  self.assertEqual(lines,original);self.assertEqual([r['index'] for r in out['results']],list(range(5)))
  self.assertEqual([r['translation'] for r in out['results']],['ru:Hello','','ru:Hello','ru:你好世界','ru:😀 «мир»'])
  self.assertEqual(out['fingerprint'],tr.fingerprint(lines));self.assertEqual(out['state'],'complete')
 async def test_languages_and_isolation(self):
  async def fake_google(session,text,source,target): return target+':'+text,'ru'
  with patch.object(tr,'_translate_line_google',side_effect=fake_google):
   for lang in ['ru','en','uk','de','fr','es','ja','ko','zh-CN']:
    src='en' if lang=='ru' else 'auto'
    self.assertEqual((await tr.translate_offline(['Привет'],lang,src))['results'][0]['translation'],lang+':Привет')
 async def test_invalid_inputs(self):
  for lines,target in [([], 'ru'),(['x']*241,'ru'),(['x'*2001],'ru'),(['x\ny'],'ru'),([{}],'ru'),(['x'],'auto'),(['x'],[]),([' '],'ru'),(['x'*2000]*13,'ru')]:
   with self.subTest(target=target,lines=str(lines)[:20]),self.assertRaises(ValueError): tr.validate(lines,target)
 async def test_partial_retry_and_cache(self):
  calls=[]
  async def flaky(session,text,source,target):
   calls.append((text,target))
   if text=='fail' and len(calls)<=2: raise tr.TranslationUnavailable('offline')
   return target+':'+text,'ru'
  with patch.object(tr,'_translate_line_google',side_effect=flaky),patch.object(tr,'_translate_line_mymemory',AsyncMock(side_effect=tr.TranslationUnavailable('offline'))):
   first=await tr.translate_offline(['ok','fail'],'en','auto');self.assertEqual(first['state'],'partial');self.assertEqual(first['results'][1]['status'],'error')
   second=await tr.translate_offline(['ok','fail'],'en','auto');self.assertEqual(second['state'],'complete')
 async def test_empty_and_bad_payload_are_errors(self):
  for payload in [[],{},[[[''], [None], None]]]:
   with self.assertRaises(tr.TranslationUnavailable): tr._parse_google_payload(payload)
 async def test_http_and_malformed_json_are_explicit(self):
  for status,payload in [(429,[]),(500,[]),(200,{}),(200,[[[''], [None], None]])]:
   context=MagicMock();context.__aenter__=AsyncMock(return_value=SimpleNamespace(status=status,json=AsyncMock(return_value=payload)));context.__aexit__=AsyncMock(return_value=False)
   session=MagicMock();session.get.return_value=context
   with self.subTest(status=status),self.assertRaises(tr.TranslationUnavailable): await tr._translate_line_google(session,'hello','auto','ru')
  context=MagicMock();context.__aenter__=AsyncMock(return_value=SimpleNamespace(status=200,json=AsyncMock(side_effect=ValueError('malformed'))));context.__aexit__=AsyncMock(return_value=False)
  session=MagicMock();session.get.return_value=context
  with self.assertRaises(ValueError): await tr._translate_line_google(session,'hello','auto','ru')
 async def test_cancel_releases_slot(self):
  started=asyncio.Event()
  async def wait(*args): started.set();await asyncio.sleep(60)
  with patch.object(tr,'_translate_line_google',side_effect=wait):
   task=asyncio.create_task(tr.translate_offline(['x'],'en','auto'));await started.wait();task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
  with patch.object(tr,'_translate_line_google',AsyncMock(return_value=('en:a','ru'))):
   self.assertEqual((await tr.translate_offline(['a'],'en','auto'))['state'],'complete')

class ApiTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  tr._memory_cache.clear()
  self._disk=patch.object(tr,'_load_disk_cache',return_value={});self._save=patch.object(tr,'_save_disk_cache')
  self._disk.start();self._save.start()
  app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):
  await self.client.close();self._disk.stop();self._save.stop()
 async def test_consent_origin_types_and_success(self):
  url='/api/lyrics/translate'
  self.assertEqual((await self.client.post(url,json={'lines':['a'],'target':'ru'})).status,400)
  self.assertEqual((await self.client.post(url,json={'source':'auto'},headers={'Origin':'https://evil.invalid'})).status,403)
  self.assertEqual((await self.client.post(url,json={'source':'auto','lines':[3],'target':'ru'})).status,400)
  with patch.object(tr,'_translate_line_google',AsyncMock(return_value=('Привет','en'))):
   r=await self.client.post(url,json={'source':'auto','lines':['Hello','','Hello'],'target':'ru'});data=await r.json()
  self.assertEqual(r.status,200);self.assertEqual(data['state'],'complete');self.assertEqual([x['status'] for x in data['results']],['ok','empty','ok'])
