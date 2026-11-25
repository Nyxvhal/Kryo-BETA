import asyncio,copy,unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,MagicMock,patch
from aiohttp.test_utils import TestClient,TestServer
from kryonyx import lyric_translate as tr,server,songfinder,tray,main

class TranslationTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):tr._cache.clear()
 async def test_preserves_line_order_blanks_and_source(self):
  lines=['Morning','','Quiet sea'];source=copy.deepcopy(lines)
  with patch.object(tr,'_request',AsyncMock(side_effect=['Утро','Тихое море'])) as request:
   result=await tr.translate(lines,'ru',object())
  self.assertEqual(result,['Утро','','Тихое море']);self.assertEqual(lines,source);self.assertEqual(request.await_count,2)
 async def test_separate_requests_prevent_batch_reordering(self):
  with patch.object(tr,'_request',AsyncMock(side_effect=['Утро','Море'])):
   self.assertEqual(await tr.translate(['Morning','Sea'],'ru',object()),['Утро','Море'])
 async def test_large_group_falls_back_without_losing_alignment(self):
  lines=[f'Line {i}' for i in range(20)]
  async def request(session,text,target):
   if '\n' in text:return 'merged row'
   return 'Translated '+text
  with patch.object(tr,'_request',side_effect=request):
   self.assertEqual(await tr.translate(lines,'ru',object()),['Translated '+line for line in lines])
 async def test_cache_is_target_and_text_specific(self):
  with patch.object(tr,'_request',AsyncMock(side_effect=['Привет','Hello','Пока'])) as request:
   a=await tr.translate(['Hello'],'ru',None);a[0]='changed'
   self.assertEqual(await tr.translate(['Hello'],'ru',None),['Привет'])
   self.assertEqual(await tr.translate(['Hello'],'en',None),['Hello'])
   self.assertEqual(await tr.translate(['Bye'],'ru',None),['Пока']);self.assertEqual(request.await_count,3)
 async def test_failure_is_not_cached(self):
  with patch.object(tr,'_request',AsyncMock(side_effect=tr.TranslationUnavailable('offline'))):
   with self.assertRaises(tr.TranslationUnavailable):await tr.translate(['Hello'],'ru',None)
  self.assertEqual(len(tr._cache),0)
 async def test_input_limits_and_target_validation(self):
  for lines,target in [([], 'ru'),(['x']*241,'ru'),(['x'*2001],'ru'),(['x\ny'],'ru'),([{}],'ru'),(['x'],'auto'),(['x'],[]),([' '],'ru'),(['x'*2000]*13,'ru')]:
   with self.subTest(lines=str(lines)[:30],target=target):
    with self.assertRaises(ValueError):tr.validate(lines,target)
 async def test_remote_response_is_bounded_and_timed(self):
  context=MagicMock();context.__aenter__=AsyncMock(return_value=SimpleNamespace(status=200,json=AsyncMock(return_value=[[['Привет','Hello']]])));context.__aexit__=AsyncMock()
  session=MagicMock();session.post.return_value=context
  self.assertEqual(await tr._request(session,'Hello','ru'),'Привет')
  self.assertEqual(session.post.call_args.args[0],'https://translate.googleapis.com/translate_a/single')
  self.assertEqual(session.post.call_args.kwargs['data']['q'],'Hello')
 async def test_catalog_outage_is_not_no_matches(self):
  with patch.object(songfinder.providers,'search',AsyncMock(side_effect=OSError('offline'))):
   with self.assertRaisesRegex(ValueError,'catalogues'):await songfinder.candidates('Skyfall')
 async def test_legitimate_empty_catalogue_remains_empty(self):
  with patch.object(songfinder.providers,'search',AsyncMock(return_value={'tracks':[]})):
   self.assertEqual(await songfinder.candidates('Skyfall'),[])

class TranslationApiTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  tr._cache.clear();app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close()
 async def test_explicit_consent_required(self):
  with patch.object(tr,'translate',AsyncMock()) as call:
   r=await self.client.post('/api/lyrics/translate',json={'lines':['Hello'],'target':'ru'});self.assertEqual(r.status,400);call.assert_not_awaited()
 async def test_foreign_origin_is_rejected(self):
  r=await self.client.post('/api/lyrics/translate',json={'consent':True},headers={'Origin':'https://foreign.example'});self.assertEqual(r.status,403)
 async def test_success_keeps_array_and_target(self):
  with patch.object(tr,'_request',AsyncMock(side_effect=['Привет','Море'])):
   r=await self.client.post('/api/lyrics/translate',json={'consent':True,'lines':['Hello','Sea'],'target':'ru'});d=await r.json()
  self.assertEqual(r.status,200);self.assertEqual(d['translations'],['Привет','Море']);self.assertTrue(d['machine_translation'])
 async def test_invalid_input_returns_400(self):
  for lines,target in [(['a'],{}),(['x\ny'],'ru'),([], 'ru')]:
   r=await self.client.post('/api/lyrics/translate',json={'consent':True,'lines':lines,'target':target});self.assertEqual(r.status,400)
 async def test_provider_failure_is_explicit(self):
  with patch.object(tr,'translate_lines',AsyncMock(side_effect=tr.TranslationUnavailable('offline'))):
   r=await self.client.post('/api/lyrics/translate',json={'consent':True,'lines':['Hello'],'target':'ru'});self.assertEqual(r.status,502)
 async def test_recognized_identity_survives_catalogue_outage(self):
  from aiohttp import FormData
  from test_repair_v20 import tone
  form=FormData();form.add_field('file',tone(),filename='sample.wav',content_type='audio/wav')
  with patch.object(songfinder,'recognize',AsyncMock(return_value={'title':'Skyfall','artist':'Adele'})),patch.object(songfinder,'candidates',AsyncMock(side_effect=ValueError('catalogues offline'))):
   r=await self.client.post('/api/song-finder/file?consent=1',data=form);d=await r.json()
  self.assertEqual(r.status,200);self.assertEqual(d['recognition']['title'],'Skyfall');self.assertEqual(d['items'],[]);self.assertEqual(d['catalogue_error'],'catalogues offline')
 async def test_text_search_outage_returns_error(self):
  with patch.object(songfinder,'candidates',AsyncMock(side_effect=ValueError('Music catalogues unavailable'))):
   r=await self.client.post('/api/song-finder/text',json={'query':'Hello'});self.assertEqual(r.status,502)

class SilentTrayTests(unittest.TestCase):
 def test_no_notifications_even_direct_legacy_request(self):
  icon=tray.Tray('Kryonyx',None,lambda _:None);icon.update('One','Artist',True,notify=True);icon.update('Two','Artist',True,notify=True)
  self.assertIsNone(icon._balloon);self.assertIn('Two',icon.tooltip())
 def test_bridge_never_requests_notifications(self):
  api=main.DesktopApi.__new__(main.DesktopApi);api._window=None;api._minimized=True;api._tray=MagicMock();api.now_playing({'title':'Song','playing':True,'notify':True})
  self.assertFalse(api._tray.update.call_args.kwargs['notify'])

if __name__=='__main__':unittest.main()
