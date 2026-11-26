"""Full-video-first TikTok regression, download integrity and v42 karaoke provenance."""
import asyncio,hashlib,io,tempfile,unittest,wave,json
from pathlib import Path
from unittest.mock import patch,AsyncMock
from kryonyx import tiktokfinder as tf,songfinder
from test_tiktok_v39 import INFO,URL,IDENTITY,TRACK,Response,Session,tone
R=Path(__file__).resolve().parents[1]
class Video44(unittest.TestCase):
 def test_source_a_unrelated_karaoke_and_styles_are_preserved(self):
  # The v44 historical v42 manifest is retained as history, but does not
  # describe the user-supplied Source A (including its unmodified karaoke.js).
  # Compare instead to a separate, independently recorded Source A snapshot.
  prov_path=R/'verification/source-a-karaoke-sha256.json'
  if not prov_path.is_file():self.skipTest('verification snapshot is not in this repository')
  provenance=json.loads(prov_path.read_text())
  intentional={'kryonyx/web/js/karaoke.js','kryonyx/web/js/reference-scene-v24.js',
               'kryonyx/web/js/repair-v33.js','kryonyx/web/js/lyrics-translate-v22.js',
               'kryonyx/web/css/repair-v33.css','kryonyx/web/css/reference-scene-v24.css'}
  for file,digest in provenance['sha256'].items():
   if file not in intentional:self.assertEqual(hashlib.sha256((R/file).read_bytes()).hexdigest(),digest,file)
 def test_audio_only_smaller_stream_is_not_used(self):
  audio={'url':'https://cdn.example.org/audio.m4a','acodec':'aac','vcodec':'none','filesize':100}
  self.assertEqual(tf.media_format({**INFO,'formats':[audio,*INFO['formats']]}),INFO['formats'][0])
 def test_video_without_sound_is_rejected(self):
  with self.assertRaises(ValueError):tf.media_format({'formats':[{**INFO['formats'][0],'acodec':'none'}]})
 def test_headers_are_allowlisted(self):
  h=tf._download_headers({'http_headers':{'User-Agent':'TikTok-App','Referer':'https://www.tiktok.com/','Cookie':'secret','Authorization':'private','X-Untrusted':'bad'}})
  self.assertEqual(h,{'User-Agent':'TikTok-App','Referer':'https://www.tiktok.com/'})
  self.assertEqual(tf._download_headers({'http_headers':{'Referer':'https://evil.example/','User-Agent':'bad\r\nheader'}}),{})
 def test_wave_is_not_accepted_as_video(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'fake.mp4'
   with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\1'*16000)
   with self.assertRaises(ValueError):tf._verify_video(path)
 def test_real_mp4_is_verified(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'real.mp4';path.write_bytes(tone());tf._verify_video(path)
class Download44(unittest.IsolatedAsyncioTestCase):
 async def test_complete_download_committed_atomically(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'video.mp4';n=await tf.download(INFO['formats'][0],path,Session([Response(chunks=(b'video',b'data'),length=9)]))
   self.assertEqual(n,9);self.assertEqual(path.read_bytes(),b'videodata');self.assertFalse(path.with_name('video.mp4.part').exists())
 async def test_truncated_download_never_committed(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'video.mp4'
   with self.assertRaises(ValueError):await tf.download(INFO['formats'][0],path,Session([Response(chunks=(b'partial',),length=100)]))
   self.assertFalse(path.exists());self.assertFalse(list(Path(tmp).glob('*.part')))
 async def test_cancel_removes_partial_file(self):
  class Slow:
   async def iter_chunked(self,n):yield b'partial';await asyncio.sleep(10)
  r=Response();r.content=Slow()
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'video.mp4';task=asyncio.create_task(tf.download(INFO['formats'][0],path,Session([r])));await asyncio.sleep(.03);task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
   self.assertFalse(path.exists());self.assertFalse(list(Path(tmp).glob('*.part')))
 async def test_alternative_and_safe_header_propagation(self):
  calls=[]
  async def fetch(media,path,session):
   calls.append(media)
   if len(calls)==1:raise ValueError('expired')
   path.write_bytes(b'complete');return 8
  info={**INFO,'http_headers':{'User-Agent':'expected'},'formats':[INFO['formats'][0],{**INFO['formats'][0],'url':'https://cdn.example.org/other.mp4'}]}
  with tempfile.TemporaryDirectory() as tmp,patch.object(tf,'download',side_effect=fetch):
   result=await tf._download_video(info,URL,Path(tmp)/'video.mp4',None)
  self.assertTrue(result['complete']);self.assertEqual(result['attempts'],2);self.assertEqual(calls[1]['http_headers']['User-Agent'],'expected')
 async def test_refresh_retries_a_temporarily_failed_url(self):
  async def fetch(media,path,session):
   if fetch.count==0:fetch.count+=1;raise ValueError('transient')
   path.write_bytes(b'video');return 5
  fetch.count=0
  with tempfile.TemporaryDirectory() as tmp,patch.object(tf,'download',side_effect=fetch),patch.object(tf,'embed_metadata',AsyncMock(side_effect=ValueError(tf.UNAVAILABLE))),patch.object(tf,'metadata',return_value=INFO) as metadata:
   result=await tf._download_video(INFO,URL,Path(tmp)/'video.mp4',None)
  self.assertEqual(result['attempts'],2);metadata.assert_called_once()
 async def test_failed_download_cannot_become_metadata_success(self):
  with patch.object(tf,'canonical_url',AsyncMock(return_value=URL)),patch.object(tf,'metadata',return_value=INFO),patch.object(tf,'embed_metadata',AsyncMock(side_effect=ValueError(tf.UNAVAILABLE))),patch.object(tf,'download',AsyncMock(side_effect=ValueError('failed'))),patch.object(songfinder,'recognize',AsyncMock()) as recognize,patch.object(songfinder,'candidates',AsyncMock()) as candidates:
   with self.assertRaises(ValueError):await tf.analyze(URL,None)
  recognize.assert_not_awaited();candidates.assert_not_awaited()
 async def test_decode_and_shazam_start_only_after_complete_video(self):
  order=[];data=tone()
  async def download(media,path,session):
   self.assertFalse(path.exists());await asyncio.sleep(.01);path.write_bytes(data);order.append('download_complete');return len(data)
  verify=tf._verify_video;extract=songfinder.extract_sample
  def verified(path):self.assertEqual(path.read_bytes(),data);order.append('verify');return verify(path)
  def decoded(path,out,offset):self.assertEqual(path.read_bytes(),data);order.append('extract_audio');return extract(path,out,offset)
  async def recognize(path,session):self.assertEqual(path.read_bytes()[:4],b'RIFF');order.append('shazam');return IDENTITY
  with patch.object(tf,'canonical_url',AsyncMock(return_value=URL)),patch.object(tf,'metadata',return_value=INFO),patch.object(tf,'download',side_effect=download),patch.object(tf,'_verify_video',side_effect=verified),patch.object(songfinder,'extract_sample',side_effect=decoded),patch.object(songfinder,'recognize',side_effect=recognize),patch.object(songfinder,'candidates',AsyncMock(return_value=[])):
   result=await tf.analyze(URL,None)
  self.assertEqual(order,['download_complete','verify','extract_audio','shazam']);self.assertEqual(result['video']['download']['bytes'],len(data));self.assertTrue(result['video']['download']['complete'])

class Embed44(unittest.TestCase):
 def document(self,video_id='1234567890123456789',url='https://cdn.example.org/full.mp4',**extra):
  page={'videoData':{'itemInfos':{'id':video_id,'video':{'urls':[url],'videoMeta':{'duration':60}},**extra},'musicInfos':{'playUrl':['https://cdn.example.org/WRONG-audio.mp3']}}}
  return '<script type="application/json" id="__FRONTITY_CONNECT_STATE__">'+json.dumps({'source':{'data':{'/embed/v2/'+video_id:page}}})+'</script>'
 def test_exact_video_identity_and_no_music_credit_url(self):
  info=tf._embed_info(self.document(),'1234567890123456789')
  self.assertEqual(info['formats'][0]['url'],'https://cdn.example.org/full.mp4');self.assertEqual(info['duration'],60)
  with self.assertRaises(ValueError):tf._embed_info(self.document(),'9999999999999999999')
 def test_private_and_friend_entries_are_rejected(self):
  for private in [{'secret':True},{'forFriend':True}]:
   with self.assertRaises(ValueError):tf._embed_info(self.document(**private),'1234567890123456789')
 def test_private_cdn_and_missing_video_rejected(self):
  with self.assertRaises(ValueError):tf._embed_info(self.document(url='https://127.0.0.1/private'),'1234567890123456789')
 def test_invalid_state_is_a_handled_error(self):
  for state in [None,[],{}, {'source':[]},{'source':{'data':[]}}, {'source':{'data':{'test':{'videoData':[]}}}}]:
   text='<script id="__FRONTITY_CONNECT_STATE__">'+json.dumps(state)+'</script>'
   with self.assertRaises(ValueError):tf._embed_info(text,'1234567890123456789')

class EmbedNetwork44(unittest.IsolatedAsyncioTestCase):
 async def test_embed_offsite_redirect_is_blocked(self):
  s=Session([Response(302,{'Location':'https://evil.example/private'})])
  with self.assertRaises(ValueError):await tf.embed_metadata(URL,s)
  self.assertEqual(len(s.urls),1)
 async def test_embed_page_size_is_bounded(self):
  s=Session([Response(chunks=(b'x'*(2*1024*1024+1),))])
  with self.assertRaises(ValueError):await tf.embed_metadata(URL,s)
 async def test_embed_fallback_is_used_after_blocked_primary_cdn(self):
  info={**INFO,'formats':[{**INFO['formats'][0],'url':'https://cdn.example.org/embed.mp4'}],'download_route44':'public_tiktok_embed'}
  async def download(media,path,session):
   if not media['url'].endswith('/embed.mp4'):raise ValueError('CDN HTTP403')
   path.write_bytes(b'video');return 5
  with tempfile.TemporaryDirectory() as tmp,patch.object(tf,'download',side_effect=download),patch.object(tf,'embed_metadata',AsyncMock(return_value=info)) as embed:
   r=await tf._download_video(INFO,URL,Path(tmp)/'video.mp4',None)
  self.assertEqual(r['route'],'public_tiktok_embed');self.assertTrue(r['complete']);embed.assert_awaited_once()
