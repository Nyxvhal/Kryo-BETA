import asyncio, io, socket, unittest
from unittest.mock import patch, AsyncMock
from PIL import Image
from kryonyx import wallpaper, audio_quality, youtube, ytdlp_bin

class Repair33(unittest.TestCase):
 def test_public_wall_urls(self):
  for u in ['file:///etc/passwd','http://localhost/a','http://127.0.0.1/a','http://[::1]/','http://192.168.1.1/','https://user:pass@example.com/a','https://example.com:8080/a','http://printer.local/a']:
   self.assertFalse(wallpaper.public_url(u),u)
  self.assertTrue(wallpaper.public_url('https://i.pinimg.com/originals/a.jpg'))
 def test_unwrap_google_yandex(self):
  for u in ['https://www.google.com/imgres?imgurl=https%3A%2F%2Fexample.com%2Flarge.jpg','https://yandex.ru/images/search?img_url=https%3A%2F%2Fexample.com%2Flarge.jpg']:
   self.assertEqual(wallpaper.unwrap(u),'https://example.com/large.jpg')
  with self.assertRaises(ValueError):wallpaper.unwrap('https://www.google.com/imgres?imgurl=http%3A%2F%2F127.0.0.1%2Fa')
 def test_pinterest_metadata(self):
  self.assertEqual(wallpaper.page_image('<meta content="https://i.pinimg.com/originals/a.jpg?x=1&amp;y=2" property="og:image">','https://pinterest.com/pin/1/'),'https://i.pinimg.com/originals/a.jpg?x=1&y=2')
  with self.assertRaises(ValueError):wallpaper.page_image('<script>alert(1)</script>','https://example.com')
 def test_policies(self):
  streams=[dict(url='https://example.com/'+str(n),mimeType='audio/mp4',bitrate=n) for n in [64000,128000,256000]]
  for mode,expected in [('best',256000),('balanced',128000),('data',64000)]:
   with patch('kryonyx.audio_quality.mode',return_value=mode):
    self.assertEqual(youtube._pick(streams)['bitrate'],expected)
    self.assertIn('bestaudio',audio_quality.format_selector())
    formats=[dict(url=s['url'],acodec='aac',vcodec='none',protocol='https',abr=s['bitrate']/1000) for s in streams]
    self.assertEqual(ytdlp_bin._pick_format({'formats':formats})['abr'],expected/1000)
 def test_cached_wallpaper_strips_metadata(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d,patch('kryonyx.wallpaper.directory',return_value=Path(d)):
   b=io.BytesIO();Image.new('RGB',(128,64),'red').save(b,'PNG');name=wallpaper.store(b.getvalue())
   self.assertRegex(name,r'^[a-f0-9]{64}\.jpg$')
   with Image.open(Path(d)/name) as im:self.assertEqual(im.size,(128,64));self.assertFalse(im.getexif())

class AsyncRepair33(unittest.IsolatedAsyncioTestCase):
 async def test_dns_private_rejected(self):
  with patch.object(asyncio.get_running_loop(),'getaddrinfo',new=AsyncMock(return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])):
   with self.assertRaises(OSError):await wallpaper.PublicResolver().resolve('public.example',443)
 async def test_identity_portrait_preferred(self):
  from kryonyx import artist_portraits
  with patch('kryonyx.ytmusic._call',new=AsyncMock(return_value={'thumbnails':[{'url':'https://example.com/profile.jpg','width':100,'height':100}]})):
   result=await artist_portraits.portrait('Ironmouse','https://music.youtube.com/channel/UCabc','youtube')
   self.assertEqual(result.get('picture'),'https://example.com/profile.jpg')

class Recommendations33(unittest.IsolatedAsyncioTestCase):
 async def test_slow_refresh_returns_saved_and_deduplicates(self):
  from kryonyx import server
  from types import SimpleNamespace
  import json,time
  hold=asyncio.Event();calls=[]
  async def refresh(limit):calls.append(limit);await hold.wait()
  saved=[{'id':'saved','items':[]}];app={};req=SimpleNamespace(query={'fresh':'1'},app=app)
  with patch('kryonyx.server.recommend.cached_rows',return_value=saved),patch('kryonyx.server.recommend.invalidate'),patch('kryonyx.server._refresh_rows',side_effect=refresh),patch('kryonyx.server.extras.fill_thumbnails',new=AsyncMock()):
   before=time.monotonic();a=await server.api_recommend(req);b=await server.api_recommend(req);await asyncio.sleep(0)
   self.assertLess(time.monotonic()-before,.5)
   self.assertEqual(len(calls),1)
   data=json.loads(a.body);self.assertTrue(data['refreshing']);self.assertEqual(data['rows'],saved)
   hold.set();await app['recommend_refresh33']
   poll=await server.api_recommend(SimpleNamespace(query={'poll':'1'},app=app))
   self.assertFalse(json.loads(poll.body)['refreshing'])
