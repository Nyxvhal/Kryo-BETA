"""TikTok validation, bounded downloads, real local FFmpeg samples and opt-in API.
TikTok/Shazam/catalogue calls are mocked; no claim of live identification accuracy.
"""
import asyncio, io, math, tempfile, unittest, wave, subprocess, functools
from pathlib import Path
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
from kryonyx import tiktokfinder as tf, songfinder, providers, server

URL='https://www.tiktok.com/@demo/video/1234567890123456789'
TRACK={'id':'yt:original39','title':'Example song','artist':'Example artist','source':'youtube'}
IDENTITY={'title':TRACK['title'],'artist':TRACK['artist'],'source':'Shazam acoustic fingerprint'}
INFO={'duration':60,'track':'Credited title','artists':['Credited artist'],'title':'caption is not the song','uploader':'not the performer','formats':[{'url':'https://cdn.example.org/media.mp4','protocol':'https','acodec':'aac','vcodec':'h264'}]}

@functools.lru_cache(maxsize=2)
def tone(seconds=50):
    # A real progressive video, not a WAV disguised as a video; v44 verifies video first.
    from kryonyx import clipcache
    with tempfile.TemporaryDirectory() as tmp:
        out=Path(tmp)/'fixture.mp4'
        subprocess.run([clipcache.ffmpeg_exe(),'-nostdin','-v','error',
            '-f','lavfi','-i',f'color=c=black:s=32x32:r=1:d={seconds}',
            '-f','lavfi','-i',f'sine=frequency=220:sample_rate=16000:duration={seconds}',
            '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest','-y',str(out)],check=True,timeout=30)
        return out.read_bytes()

class UrlTests(unittest.TestCase):
    def test_canonical_removes_tracking(self):self.assertEqual(tf.normalize_url(URL+'?utm_source=x#fragment'),URL)
    def test_short_links(self):
        for u in ['https://vm.tiktok.com/ZMabc123/','https://vt.tiktok.com/ZMabc123/','https://www.tiktok.com/t/ZMabc123/']:
            self.assertEqual(tf.normalize_url(u+'?x=1'),u)
    def test_rejects_untrusted_inputs(self):
        for u in [None,{},'',[], 'http://www.tiktok.com/@demo/video/1234567890123456789','file:///tmp/private','https://127.0.0.1/','https://tiktok.com.evil.example/@a/video/12345678901','https://www.tiktok.com@evil.example/','https://user:password@www.tiktok.com/@demo/video/1234567890123456789','https://www.tiktok.com:444/@demo/video/1234567890123456789','https://www.tiktok.com/music/song-123','https://www.tiktok.com/@a/photo/12345678901','https://www.tiktok.com/@a/video/12345678901 --exec bad','https://www.tiktok.com/@a/video/../12345678901']:
            with self.subTest(u=u),self.assertRaises(ValueError):tf.normalize_url(u)
    def test_caption_and_uploader_are_not_music_attribution(self):
        self.assertIsNone(tf.sound_hint({'title':'Adele Skyfall','uploader':'Adele'}))
    def test_generic_original_sounds_are_not_original_tracks(self):
        for name in ['original sound','Original sound - Creator','оригинальный звук - пользователь','sonido original','som original','原声']:
            self.assertIsNone(tf.sound_hint({'track':name,'artist':'uploader'}))
    def test_hint_is_explicitly_unverified(self):
        hint=tf.sound_hint(INFO);self.assertFalse(hint['verified']);self.assertEqual(hint['artist'],'Credited artist')
    def test_format_selection_requires_video_with_audio(self):
        f={'url':'https://cdn.example.org/a.m4a','vcodec':'none','acodec':'aac','filesize':512}
        self.assertEqual(tf.media_format({'formats':INFO['formats']+[f]}),INFO['formats'][0])
        with self.assertRaises(ValueError):tf.media_format({'formats':[f]})
    def test_manifest_private_oversize_and_silent_formats_rejected(self):
        for f in [{'url':'https://127.0.0.1/track.mp4'},{'url':'https://cdn.example.org/a.m3u8'}, {'url':'https://cdn.example.org/a','protocol':'m3u8_native'}, {'url':'https://cdn.example.org/a','filesize':tf.MAX_BYTES+1},{'url':'https://cdn.example.org/a','acodec':'none'},{'url':'http://cdn.example.org/a'},{'url':'https://localhost/a'}]:
            with self.subTest(f=f),self.assertRaises(ValueError):tf.media_format({'formats':[f]})
    def test_metadata_uses_only_dedicated_extractor_and_no_download(self):
        with patch('yt_dlp.YoutubeDL') as cls:
            y=cls.return_value.__enter__.return_value;y.extract_info.return_value=INFO
            self.assertEqual(tf.metadata(URL),INFO)
            y.extract_info.assert_called_once_with(URL,download=False,ie_key='TikTok')
            opts=cls.call_args.args[0];self.assertTrue(opts['skip_download']);self.assertFalse(opts['cachedir']);self.assertNotIn('cookiefile',opts)
    def test_rejects_metadata_playlist_and_long_video(self):
        for info in [{'_type':'playlist'},dict(INFO,duration=601),dict(INFO,duration=float('nan'))]:
            with patch('yt_dlp.YoutubeDL') as cls:
                cls.return_value.__enter__.return_value.extract_info.return_value=info
                with self.assertRaises(ValueError):tf.metadata(URL)
    def test_dedup_excludes_original_from_related(self):
        other=dict(TRACK,id='sc:copy')
        self.assertEqual(tf._distinct([TRACK,other], [TRACK]),[])

class Content:
    def __init__(self,chunks):self.chunks=chunks
    async def iter_chunked(self,n):
        for x in self.chunks:yield x
class Response:
    def __init__(self,status=200,headers=None,chunks=(b'audio',),length=None):
        self.status=status;self.headers=headers or {};self.content=Content(chunks);self.content_length=length
    async def __aenter__(self):return self
    async def __aexit__(self,*a):pass
class Session:
    def __init__(self,responses):self.responses=iter(responses);self.urls=[]
    def get(self,url,**kw):self.urls.append((url,kw));return next(self.responses)

class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_link_is_resolved_without_following_arbitrary_redirects(self):
        s=Session([Response(302,{'Location':URL})]);self.assertEqual(await tf.canonical_url('https://vm.tiktok.com/ZMabc123/',s),URL)
        self.assertFalse(s.urls[0][1]['allow_redirects'])
    async def test_short_redirect_to_private_or_external_is_blocked(self):
        for u in ['http://127.0.0.1/private','https://attacker.example/path','https://www.tiktok.com.evil.example/']:
            s=Session([Response(302,{'Location':u})])
            with self.assertRaises(ValueError):await tf.canonical_url('https://vm.tiktok.com/ZMabc123/',s)
            self.assertEqual(len(s.urls),1)
    async def test_short_loop_bounded(self):
        s=Session([Response(302,{'Location':'https://vm.tiktok.com/ZMabc123/'})]*6)
        with self.assertRaises(ValueError):await tf.canonical_url('https://vm.tiktok.com/ZMabc123/',s)
        self.assertEqual(len(s.urls),6)
    async def test_streaming_size_limit_and_length_limit(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(tf,'MAX_BYTES',8):
            for response in [Response(chunks=(b'12345',b'67890')),Response(length=10)]:
                with self.assertRaisesRegex(ValueError,'100 MB'):await tf.download(INFO['formats'][0],Path(tmp)/'test',Session([response]))
    async def test_media_redirect_to_private_blocked_before_request(self):
        s=Session([Response(302,{'Location':'https://127.0.0.1/private'})])
        with self.assertRaises(ValueError):await tf.download(INFO['formats'][0],Path('/unused'),s)
        self.assertEqual(len(s.urls),1)
    async def test_html_error_is_not_decoded_as_media(self):
        with self.assertRaises(ValueError):await tf.download(INFO['formats'][0],Path('/unused'),Session([Response(headers={'Content-Type':'text/html'})]))
    async def test_public_resolver_rejects_private_and_mixed_dns(self):
        import socket
        from kryonyx.wallpaper import PublicResolver
        for rows in [[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))],[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))]]:
            with patch.object(asyncio.get_running_loop(),'getaddrinfo',AsyncMock(return_value=rows)):
                with self.assertRaises(OSError):await PublicResolver().resolve('cdn.example.org',443)

class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.paths=[];self.audio=tone()
        async def fetch(media,target,session):self.paths.append(target);target.write_bytes(self.audio);return len(self.audio)
        self.fetch=fetch
    def deps(self,info=None):
        from contextlib import ExitStack
        s=ExitStack();s.enter_context(patch.object(tf,'embed_metadata',AsyncMock(side_effect=ValueError(tf.UNAVAILABLE))));s.enter_context(patch.object(tf,'canonical_url',AsyncMock(return_value=URL)));s.enter_context(patch.object(tf,'metadata',return_value=info or INFO));s.enter_context(patch.object(tf,'download',side_effect=self.fetch));return s
    async def test_real_ffmpeg_two_samples_then_fingerprint_identity(self):
        samples=[]
        async def identify(path,session):
            self.assertTrue(path.is_file());samples.append(path.read_bytes());return None if len(samples)==1 else IDENTITY
        with self.deps(),patch.object(songfinder,'recognize',side_effect=identify),patch.object(songfinder,'candidates',AsyncMock(return_value=[TRACK,TRACK])),patch.object(providers,'related',AsyncMock(return_value=[TRACK,dict(TRACK,id='yt:other',title='Another song')])):
            d=await tf.analyze(URL,None)
        self.assertEqual(d['sample_count'],2);self.assertEqual(d['basis'],'acoustic_fingerprint');self.assertEqual(d['recognition']['title'],'Example song');self.assertEqual(len(d['items']),1);self.assertEqual(len(d['similar']),1)
        self.assertTrue(all(x[:4]==b'RIFF' for x in samples));self.assertTrue(all(not p.parent.exists() for p in self.paths))
    async def test_generic_no_match_does_not_search_caption_or_uploader(self):
        with self.deps(dict(INFO,track='original sound',title='Adele Skyfall')),patch.object(songfinder,'recognize',AsyncMock(return_value=None)),patch.object(songfinder,'candidates',AsyncMock()) as search:
            d=await tf.analyze(URL,None)
        self.assertEqual(d['basis'],'no_match');self.assertEqual(d['items'],[]);search.assert_not_called()
    async def test_metadata_fallback_is_not_confirmed_original_or_similarity(self):
        with self.deps(),patch.object(songfinder,'recognize',AsyncMock(return_value=None)),patch.object(songfinder,'candidates',AsyncMock(return_value=[TRACK])):
            d=await tf.analyze(URL,None)
        self.assertIsNone(d['recognition']);self.assertEqual(d['basis'],'sound_metadata');self.assertFalse(d['sound_hint']['verified']);self.assertEqual(d['similar'],[])
    async def test_recognition_outage_preserves_only_unverified_hint(self):
        with self.deps(),patch.object(songfinder,'recognize',AsyncMock(side_effect=ValueError('service offline'))),patch.object(songfinder,'candidates',AsyncMock(return_value=[])):
            d=await tf.analyze(URL,None)
        self.assertIsNone(d['recognition']);self.assertTrue(d['warnings']);self.assertTrue(all(not p.parent.exists() for p in self.paths))
    async def test_catalogue_outage_keeps_recognized_name(self):
        with self.deps(),patch.object(songfinder,'recognize',AsyncMock(return_value=IDENTITY)),patch.object(songfinder,'candidates',AsyncMock(side_effect=ValueError('catalogue offline'))):
            d=await tf.analyze(URL,None)
        self.assertEqual(d['recognition'],IDENTITY);self.assertEqual(d['items'],[]);self.assertEqual(d['catalogue_error'],'catalogue offline')
    async def test_download_failure_cleans_temp_files_without_fake_recognition(self):
        async def fail(media,target,session):self.paths.append(target);target.write_bytes(b'partial');raise ValueError('download failed')
        with self.deps(dict(INFO,track='original sound')),patch.object(tf,'download',side_effect=fail),self.assertRaises(ValueError):await tf.analyze(URL,None)
        self.assertTrue(all(not p.parent.exists() for p in self.paths))
    async def test_stage_logs_are_actionable_without_urls_or_song_titles(self):
        with self.deps(),patch.object(songfinder,'recognize',AsyncMock(return_value=IDENTITY)),patch.object(songfinder,'candidates',AsyncMock(return_value=[])),self.assertLogs('kryonyx.tiktokfinder',level='INFO') as logs:
            await tf.analyze(URL,None)
        text='\n'.join(logs.output)
        for stage in ['resolve_link','extract_metadata','download_video','verify_video','decode_sample','fingerprint','catalogue']:
            self.assertIn(stage+' started',text)
            self.assertIn(stage+' completed',text)
        self.assertNotIn(URL,text)
        self.assertNotIn(IDENTITY['title'],text)
        self.assertNotIn('kryonyx-tiktok-',text)

    async def test_stage_log_identifies_metadata_failure_without_raw_exception(self):
        with self.deps(),patch.object(tf,'metadata',side_effect=ValueError('private signed URL must not be logged')),self.assertLogs('kryonyx.tiktokfinder',level='INFO') as logs:
            with self.assertRaises(ValueError):await tf.analyze(URL,None)
        text='\n'.join(logs.output)
        self.assertIn('extract_metadata failed (ValueError)',text)
        self.assertNotIn('private signed URL',text)

    async def test_invalid_offset_and_offset_outside_video(self):
        for offset in [float('nan'),-1,601,True]:
            with self.assertRaises(ValueError):await tf.analyze(URL,None,offset)
        with self.deps(),self.assertRaisesRegex(ValueError,'outside'):await tf.analyze(URL,None,61)

class DisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_disconnect_cancels_analysis_and_runs_cleanup(self):
        from types import SimpleNamespace
        closed=asyncio.Event()
        async def work(*args):
            try:await asyncio.sleep(10)
            finally:closed.set()
        with patch.object(tf,'analyze',side_effect=work):
            with self.assertRaises(asyncio.CancelledError):
                await tf.for_request(SimpleNamespace(transport=None),URL,None)
        self.assertTrue(closed.is_set())
    async def test_connected_client_gets_result(self):
        from types import SimpleNamespace
        request=SimpleNamespace(transport=SimpleNamespace(is_closing=lambda:False))
        with patch.object(tf,'analyze',AsyncMock(return_value={'basis':'no_match'})):
            self.assertEqual(await tf.for_request(request,URL,None),{'basis':'no_match'})

class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
    async def asyncTearDown(self):await self.client.close()
    async def test_missing_consent_does_not_make_network_requests(self):
        with patch.object(tf,'analyze',AsyncMock()) as call:
            r=await self.client.post('/api/song-finder/tiktok',json={'url':URL});self.assertEqual(r.status,400);call.assert_not_called()
    async def test_malformed_url_body_and_offset_rejected(self):
        for data in [[],{}, {'url':'https://127.0.0.1','consent':True},{'url':URL,'consent':True,'offset':'nan'},{'url':URL,'consent':True,'offset':True}]:
            with self.subTest(data=data):self.assertEqual((await self.client.post('/api/song-finder/tiktok',json=data)).status,400)
    async def test_cross_origin_blocked(self):
        r=await self.client.post('/api/song-finder/tiktok',json={'url':URL,'consent':True},headers={'Origin':'https://evil.example'});self.assertEqual(r.status,403)
    async def test_result_keeps_identity_and_suggestions_separate(self):
        value={'recognition':IDENTITY,'items':[TRACK],'similar':[],'mode':'tiktok'}
        with patch.object(tf,'analyze',AsyncMock(return_value=value)) as call:
            r=await self.client.post('/api/song-finder/tiktok',json={'url':URL,'consent':True,'offset':3});self.assertEqual(r.status,200);self.assertEqual((await r.json())['recognition'],IDENTITY);self.assertEqual(call.call_args.args[2],3)
    async def test_upstream_error_and_timeout_are_actionable(self):
        for exc,status in [(ValueError(tf.UNAVAILABLE),422),(asyncio.TimeoutError(),504),(OSError('network'),502)]:
            with patch.object(tf,'analyze',AsyncMock(side_effect=exc)):
                r=await self.client.post('/api/song-finder/tiktok',json={'url':URL,'consent':True});self.assertEqual(r.status,status);self.assertIn('video',(await r.json())['error'])
    async def test_concurrency_limit_shared_with_file_search(self):
        await songfinder._slots.acquire();await songfinder._slots.acquire()
        try:
            r=await self.client.post('/api/song-finder/tiktok',json={'url':URL,'consent':True});self.assertEqual(r.status,429)
        finally:songfinder._slots.release();songfinder._slots.release()

if __name__=='__main__':unittest.main()
