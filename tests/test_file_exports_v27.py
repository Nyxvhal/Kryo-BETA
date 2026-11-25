import asyncio, base64, io, json, tempfile, threading, unittest, zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from PIL import Image
from aiohttp.test_utils import TestClient, TestServer
from kryonyx import file_exports as f, server
from kryonyx.main import DesktopApi

def png():
 out=io.BytesIO();Image.new('RGB',(4,3),'red').save(out,format='PNG');return out.getvalue()

class ExportTests(unittest.TestCase):
 def test_reject_all_audio_and_arbitrary_sources(self):
  for spec in [{'kind':x,'url':'/api/stream?id=test'} for x in ['audio','track','mp3','layout','cover','avatar','karaoke','m3u','avatar-pack']]+[None,{}, {'kind':'theme','url':'file:///etc/passwd'}]:
   with self.subTest(spec=spec),self.assertRaises(ValueError):f.checked_spec(spec)
 def test_allow_only_fixed_urls(self):
  valid=[('avatar','/api/avatarshop/download/test?format=png'),('avatar','/api/avatarshop/download/test?format=svg'),('avatar-pack','/api/avatarshop/pack?collection=all'),('karaoke','/api/karaoke/jobs/'+'a'*32+'/result'),('m3u','/api/playlists/2/export.m3u')]
  for kind,url in valid:self.assertEqual(f.checked_spec({'kind':kind,'url':url})[0],kind)
 def test_reject_remote_traversal_query_and_source_substitution(self):
  for url in ['https://example.com/api/avatarshop/pack?collection=all','//127.0.0.1/api/avatarshop/pack','/api/avatarshop/pack?collection=all&url=/api/stream','/api/avatarshop/../stream?collection=all','/api/avatarshop/pack?collection=all&collection=custom','/api/avatarshop/pack?collection=all#fragment','/api/avatarshop/pack?collection=../../audio']:
   with self.subTest(url=url),self.assertRaises(ValueError):f.checked_spec({'kind':'avatar-pack','url':url})
 def test_names_unicode_reserved_and_extension(self):
  self.assertEqual(f.safe_name('../Обложка:*?','.png'),'_Обложка___.png')
  self.assertEqual(f.safe_name('CON','.json'),'_CON.json')
  self.assertEqual(f.safe_name('песня.mp3','.png'),'песня.mp3.png')
 def test_generated_json(self):
  for kind in ['layout','theme','karaoke']:
   data,name,ext=f.prepare({'kind':kind,'name':'Тест','text':'{"hello":"мир"}'},'')
   self.assertEqual(json.loads(data),{'hello':'мир'});self.assertEqual(ext,'.json');self.assertTrue(name.endswith('.json'))
 def test_json_rejects_audio_bytes(self):
  for text in ['ID3audio','[]','null']:
   with self.assertRaises((ValueError,UnicodeDecodeError)):f.prepare({'kind':'theme','text':text},'')
 def test_playlist_is_metadata_not_audio(self):
  from kryonyx.extras import pack_playlist
  text=pack_playlist('demo',[{'id':'yt:test','title':'Title'}]);self.assertEqual(f.prepare({'kind':'playlist','text':text},'')[0],text.encode())
 def test_frame_validates_actual_png(self):
  data=png();value='data:image/png;base64,'+base64.b64encode(data).decode();self.assertEqual(f.prepare({'kind':'frame','data':value},'')[0],data)
  with self.assertRaises(ValueError):f.prepare({'kind':'frame','data':'data:audio/mp3;base64,SUQz'},'')
  with self.assertRaises(OSError):f.prepare({'kind':'frame','data':'data:image/png;base64,SUQz'},'')
 def test_svg_validates_no_dtd_or_non_svg(self):
  self.assertTrue(f.validate_data('avatar','.svg',b'<svg xmlns="http://www.w3.org/2000/svg"/>'))
  for data in [b'<html/>',b'<!DOCTYPE svg [<!ENTITY x "1">]><svg/>']:
   with self.assertRaises(ValueError):f.validate_data('avatar','.svg',data)
 def test_archive_rejects_audio(self):
  for name,valid in [('test.png',True),('music.mp3',False)]:
   out=io.BytesIO()
   with zipfile.ZipFile(out,'w') as z:z.writestr(name,'data')
   if valid:self.assertTrue(f.validate_data('avatar-pack','.zip',out.getvalue()))
   else:
    with self.assertRaises(ValueError):f.validate_data('avatar-pack','.zip',out.getvalue())
 def test_no_redirect_or_remote_local_server(self):
  with self.assertRaises(ValueError):f.NoRedirect().redirect_request(None,None,None,None,None,None)
  for base in ['https://127.0.0.1:9','http://evil.test:9','http://127.0.0.1:9/path','http://user@127.0.0.1:9']:
   with self.assertRaises(ValueError):f.fetch_local(base,'/api/avatarshop/pack?collection=all')
 def test_atomic_write_does_not_truncate_existing(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'chosen.json';path.write_bytes(b'old')
   with patch.object(f.os,'replace',side_effect=OSError('disk full')):
    with self.assertRaises(OSError):f.write_atomic(path,b'new')
   self.assertEqual(path.read_bytes(),b'old');self.assertEqual(list(Path(temp).glob('.kryonyx-save-*')),[])
   f.write_atomic(path,b'new');self.assertEqual(path.read_bytes(),b'new')
 def native(self,selected):
  api=DesktopApi.__new__(DesktopApi);api._export_lock=threading.Lock();api._base_url='http://127.0.0.1:9000';calls=[]
  api._window=SimpleNamespace(create_file_dialog=lambda *a,**k:(calls.append(k),selected)[1]);return api,calls
 def test_native_save_cancel_busy_and_extension(self):
  with tempfile.TemporaryDirectory() as temp:
   dest=Path(temp)/'my selected file';api,calls=self.native([str(dest)])
   with patch.dict('sys.modules',{'webview':SimpleNamespace(FileDialog=SimpleNamespace(SAVE=99))}):
    r=api.save_export({'kind':'theme','name':'Имя','text':'{}'});self.assertTrue(r['saved']);self.assertEqual(Path(str(dest)+'.json').read_bytes(),b'{}');self.assertEqual(calls[0]['save_filename'],'Имя.json')
    api._export_lock.acquire();self.assertIn('error',api.save_export({'kind':'theme','text':'{}'}));api._export_lock.release()
    api._window.create_file_dialog=lambda *a,**k:None
    self.assertEqual(api.save_export({'kind':'theme','text':'{}'}),{'cancelled':True});self.assertFalse(api._export_lock.locked())
 def test_native_error_never_calls_dialog_or_fallback(self):
  api,calls=self.native('test.mp3')
  with patch.dict('sys.modules',{'webview':SimpleNamespace()}):self.assertIn('error',api.save_export({'kind':'audio','text':'ID3'}))
  self.assertEqual(calls,[]);self.assertFalse(api._export_lock.locked())
 def test_cover_and_remote_assets_only_use_approved_local_routes(self):
  with patch.object(f,'fetch_local',return_value=png()) as fetch:
   f.prepare({'kind':'cover','urls':['https://example.com/image.jpg'],'name':'Обложка'},'http://127.0.0.1:1');self.assertEqual(fetch.call_args.args[1],'/api/image/export')

class ExportApiTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close()
 async def test_old_image_save_never_writes_a_default_path(self):
  with patch.object(server,'covers_dir') as folder:
   r=await self.client.post('/api/image/save',json={'urls':['http://example.com/test.png']});self.assertEqual(r.status,409);folder.assert_not_called()
 async def test_both_audio_bulk_routes_are_blocked(self):
  with patch.object(server,'_ensure_file',AsyncMock()) as download:
   for method in [self.client.get,self.client.post]:
    r=await method('/api/playlists/1/offline');self.assertEqual(r.status,403)
   download.assert_not_awaited()
 async def test_image_exports_png_without_writing(self):
  with patch.object(server,'_grab_image',AsyncMock(return_value=(png(),'image/png'))),patch.object(server,'_write_bytes') as write:
   r=await self.client.post('/api/image/export',json={'urls':['https://example.com/image.png']});self.assertEqual(r.status,200);self.assertEqual(r.content_type,'image/png');Image.open(io.BytesIO(await r.read())).verify();write.assert_not_called()
 async def test_image_rejects_audio_disguised_as_cover(self):
  with patch.object(server,'_grab_image',AsyncMock(return_value=(b'ID3 music','image/png'))):
   r=await self.client.post('/api/image/export',json={'urls':['https://example.com/a']});self.assertEqual(r.status,502)
 async def test_image_fallback_to_next_resolution(self):
  with patch.object(server,'_grab_image',AsyncMock(side_effect=[None,(png(),'image/png')])) as fetch:
   r=await self.client.post('/api/image/export',json={'urls':['https://example.com/large','https://example.com/small']});self.assertEqual(r.status,200);self.assertEqual(fetch.await_count,2)
 async def test_cross_origin_and_malformed_image_requests(self):
  r=await self.client.post('/api/image/export',json={'urls':['https://example.com/a']},headers={'Origin':'https://evil.test'});self.assertEqual(r.status,403)
  for urls in [None,'not a list',[],['a']*13,[1]]:
   r=await self.client.post('/api/image/export',json={'urls':urls});self.assertEqual(r.status,400)
 async def test_actual_local_http_export_through_native_bridge(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(server,'_grab_image',AsyncMock(return_value=(png(),'image/png'))),patch.dict('sys.modules',{'webview':SimpleNamespace(FileDialog=SimpleNamespace(SAVE=99))}):
   chosen=Path(temp)/'chosen.png';api=DesktopApi.__new__(DesktopApi);api._export_lock=threading.Lock();api._base_url=str(self.client.make_url('')).rstrip('/');api._window=SimpleNamespace(create_file_dialog=lambda *a,**k:[str(chosen)])
   result=await asyncio.to_thread(api.save_export,{'kind':'cover','name':'Обложка.png','urls':['https://example.com/a']});self.assertTrue(result.get('saved'),result);Image.open(chosen).verify()

 async def test_actual_avatar_png_svg_and_pack_native_exports(self):
  from kryonyx import avatars,avatarshop
  item=next(i for i in avatars.catalog() if 'svg' in i.get('formats',[]))
  with tempfile.TemporaryDirectory() as temp,patch.dict('sys.modules',{'webview':SimpleNamespace(FileDialog=SimpleNamespace(SAVE=99))}):
   api=DesktopApi.__new__(DesktopApi);api._export_lock=threading.Lock();api._base_url=str(self.client.make_url('')).rstrip('/')
   for fmt in ['png','svg']:
    destination=Path(temp)/('chosen.'+fmt);api._window=SimpleNamespace(create_file_dialog=lambda *a,**k:[str(destination)])
    result=await asyncio.to_thread(api.save_export,{'kind':'avatar','url':'/api/avatarshop/download/'+item['id']+'?format='+fmt,'name':'Avatar.'+fmt});self.assertTrue(result.get('saved'),result);self.assertEqual(destination.read_bytes(),avatarshop.asset(item['id'],fmt).read_bytes())
   destination=Path(temp)/'collection.zip';api._window=SimpleNamespace(create_file_dialog=lambda *a,**k:[str(destination)])
   result=await asyncio.to_thread(api.save_export,{'kind':'avatar-pack','url':'/api/avatarshop/pack?collection=original','name':'Avatars.zip'});self.assertTrue(result.get('saved'),result)
   with zipfile.ZipFile(destination) as archive:self.assertIsNone(archive.testzip());self.assertIn('manifest.json',archive.namelist())

if __name__=='__main__':unittest.main()
