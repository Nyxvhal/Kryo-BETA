"""Local deterministic regression; service responses are mocked, media decoding is real."""
import asyncio,io,json,math,tempfile,unittest,wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock,MagicMock
from aiohttp import FormData
from aiohttp.test_utils import TestClient,TestServer,make_mocked_request
from kryonyx import songfinder,trackstats,storage,server,avatars,providers

def tone():
    b=io.BytesIO()
    with wave.open(b,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        w.writeframes(b''.join(int(6000*math.sin(2*math.pi*(220+i/16000*5)*i/16000)).to_bytes(2,'little',signed=True) for i in range(16000*12)))
    return b.getvalue()
TRACKS=[{'id':f'yt:abcdefgh{i:03}','title':f'Song {i}','artist':'Artist','source':'youtube','duration':200} for i in range(15)]

class FinderPureTests(unittest.TestCase):
    def test_rank_prefers_exact_identity_not_service_order(self):
        rows=songfinder.rank([{'id':'1','title':'Else','artist':'Other'},{'id':'2','title':'Skyfall','artist':'Adele'}],'song',{'title':'Skyfall','artist':'Adele'})
        self.assertEqual(rows[0]['id'],'2');self.assertNotIn('confidence',rows[0])
    def test_rank_deduplicates_and_does_not_pad(self):
        row={'id':'1','title':'One','artist':'A'}
        self.assertEqual(len(songfinder.rank([row,row,{**row,'id':'2'}],'One')),1)
    def test_descriptions_form_bounded_distinct_queries(self):
        self.assertEqual(songfinder.queries('найди песня synth midnight')[1],'synth midnight')
        self.assertLessEqual(len(songfinder.queries('X'*1000)[0]),600)
    def test_media_decode_and_missing_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'source.wav').write_bytes(tone());songfinder.extract_sample(p/'source.wav',p/'sample.wav',0)
            with wave.open(str(p/'sample.wav')) as w:self.assertEqual((w.getframerate(),w.getnchannels()),(16000,1))
            (p/'bad.mp4').write_bytes(b'not video')
            with self.assertRaises(ValueError):songfinder.extract_sample(p/'bad.mp4',p/'bad.wav',0)
    def test_stats_never_follow_arbitrary_urls(self):
        self.assertFalse(trackstats.valid_id('yt:../../bad'))
        for url in ['http://127.0.0.1/a','https://soundcloud.com.evil/a','https://soundcloud.com@127.0.0.1/a','file:///etc/passwd']:
            self.assertFalse(trackstats.valid_id('sc:'+providers.b64e(url)))
        self.assertTrue(trackstats.valid_id('sc:'+providers.b64e('https://soundcloud.com/artist/song')))
    def test_artist_cover_is_never_portrait(self):
        t={'id':'yt:12345678901','artist':'Adele','title':'Skyfall','thumbnail':'album.png','source':'youtube'}
        self.assertIsNone(providers._authors_from([t])[0]['thumbnail'])
        self.assertIsNone(providers._author_page('Adele',None,'youtube',[],[t],20,False)['picture'])
        t['author_thumbnail']='original-artist.jpg'
        self.assertEqual(providers._authors_from([t])[0]['thumbnail'],'original-artist.jpg')
    def test_lazily_generated_ico_from_slim_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            from PIL import Image
            p=Path(folder);(p/'web/img/avatars').mkdir(parents=True)
            import shutil
            shutil.copy2(Path(avatars.resource_dir())/'avatars.json',p/'avatars.json')
            Image.new('RGB',(512,512),'purple').save(p/'web/img/avatars/collection-001-ironmouse.png')
            with patch.object(avatars,'resource_dir',return_value=folder),patch.object(avatars,'data_dir',return_value=folder):
                first=avatars.ico_path('collection-001-ironmouse');self.assertEqual(first,avatars.ico_path('collection-001-ironmouse'))
                chosen=avatars.choose('collection-001-ironmouse');self.assertTrue(Path(chosen['icon']).is_file());self.assertEqual(avatars.current(),'collection-001-ironmouse')
                with Image.open(first) as im:self.assertEqual(im.format,'ICO');self.assertIn((256,256),im.ico.sizes());self.assertIn((16,16),im.ico.sizes())
            self.assertFalse((p/'icons').exists())

class FinderAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_artist_photo_is_read_from_exact_profile(self):
        from kryonyx.artist_portraits import portrait
        with patch.object(providers.ytmusic,'_call',AsyncMock(return_value={'thumbnails':[{'url':'https://yt3.googleusercontent.com/original','width':800}]})) as read:
            result=await portrait('Adele','https://music.youtube.com/channel/UCexact','youtube')
            read.assert_awaited_once_with('get_artist','UCexact');self.assertIn('original',result['picture'])
    async def test_ambiguous_artist_search_does_not_choose_wrong_photo(self):
        from kryonyx.artist_portraits import portrait
        with patch.object(providers.ytmusic,'artists',AsyncMock(return_value=[{'name':'Another Artist','thumbnail':'wrong.jpg'}])):
            self.assertEqual(await portrait('Artist',None,'youtube'),{})
    async def test_candidates_have_at_least_ten_when_catalogue_returns_them(self):
        with patch.object(providers,'search',AsyncMock(return_value={'tracks':TRACKS})),patch('kryonyx.recommend._user_sources',return_value=['youtube']):
            found=await songfinder.candidates('Artist Song');self.assertEqual(len(found),15);self.assertEqual(found[0]['match_rank'],1)
    async def test_local_native_fingerprint_produces_signature(self):
        from shazamio_core import Recognizer
        sig=await Recognizer(segment_duration_seconds=10).recognize_bytes(value=tone())
        self.assertTrue(sig.signature.uri.startswith('data:audio/'));self.assertGreater(sig.signature.samples,0)
    async def test_recognition_sends_signature_not_original_file(self):
        context=MagicMock();context.__aenter__=AsyncMock(return_value=SimpleNamespace(status=200,json=AsyncMock(return_value={'track':{'title':'Skyfall','subtitle':'Adele'}})));context.__aexit__=AsyncMock()
        http=MagicMock();http.post.return_value=context
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'sample.wav';p.write_bytes(tone());identity=await songfinder.recognize(p,http)
        payload=http.post.call_args.kwargs['json'];self.assertEqual(identity['title'],'Skyfall');self.assertIn('signature',payload);self.assertNotIn('file',payload);self.assertEqual(payload['timezone'],'UTC')
    async def test_exact_source_count_backfills_old_liked_and_saved_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            conn=getattr(storage._local,'conn',None)
            if conn:conn.close();del storage._local.conn
            old=storage._db_path;storage.init(str(Path(folder)/'test.db'))
            t={'id':'yt:abcdefghijk','title':'Old','artist':'Artist','source':'youtube'}
            storage.toggle_like(t);pid=storage.create_playlist('Saved',[t])['id']
            with patch.object(trackstats.ytmusic,'_call',AsyncMock(return_value={'videoDetails':{'viewCount':'12345'}})):
                trackstats._cache.clear();trackstats._inflight.clear();value=await trackstats.lookup(t['id'])
            self.assertEqual(value['views'],12345);self.assertEqual(storage.list_likes()[0]['views'],12345);self.assertEqual(storage.playlist_tracks(pid)[0]['views'],12345)
            storage._local.conn.close();del storage._local.conn;storage._db_path=old
    async def test_unknown_source_count_is_not_zero(self):
        with patch.object(trackstats.ytmusic,'_call',AsyncMock(return_value={})),patch.object(providers,'_aextract',AsyncMock(return_value={})):
            trackstats._cache.clear();self.assertIsNone(await trackstats.lookup('yt:abcdefghijk'))
    async def test_source_zero_remains_valid(self):
        with patch.object(trackstats.ytmusic,'_call',AsyncMock(return_value={'videoDetails':{'viewCount':'0'}})),patch.object(trackstats,'persist'):
            trackstats._cache.clear();self.assertEqual((await trackstats.lookup('yt:abcdefghijk'))['views'],0)

class FinderApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
    async def asyncTearDown(self):await self.client.close()
    async def test_text_endpoint_validates_and_returns_real_number(self):
        bad=await self.client.post('/api/song-finder/text',json={'query':'x'});self.assertEqual(bad.status,400)
        with patch.object(songfinder,'candidates',AsyncMock(return_value=TRACKS)):
            response=await self.client.post('/api/song-finder/text',json={'query':'Skyfall'});body=await response.json();self.assertEqual(response.status,200);self.assertEqual(body['found'],15)
    async def test_cross_origin_search_rejected(self):
        res=await self.client.post('/api/song-finder/text',json={'query':'track'},headers={'Origin':'https://foreign.example'});self.assertEqual(res.status,403)
    async def test_file_consent_and_offset_required(self):
        self.assertEqual((await self.client.post('/api/song-finder/file')).status,400)
        self.assertEqual((await self.client.post('/api/song-finder/file?consent=1&offset=nan')).status,400)
    async def test_media_upload_recognition_and_temp_cleanup(self):
        called=[]
        async def recognize(path,session):called.append(path);self.assertTrue(path.is_file());return {'title':'Skyfall','artist':'Adele'}
        form=FormData();form.add_field('file',tone(),filename='arbitrary-name.wav',content_type='audio/wav')
        with patch.object(songfinder,'recognize',side_effect=recognize),patch.object(songfinder,'candidates',AsyncMock(return_value=TRACKS)):
            response=await self.client.post('/api/song-finder/file?consent=1',data=form);body=await response.json()
        self.assertEqual(response.status,200,body);self.assertEqual(body['found'],15);self.assertFalse(called[0].exists());self.assertEqual(body['recognition']['artist'],'Adele')
    async def test_no_audio_match_does_not_search_uploaded_filename(self):
        form=FormData();form.add_field('file',tone(),filename='Adele-Skyfall.wav')
        with patch.object(songfinder,'recognize',AsyncMock(return_value=None)),patch.object(songfinder,'candidates',AsyncMock()) as search:
            response=await self.client.post('/api/song-finder/file?consent=1',data=form);body=await response.json()
        self.assertEqual(body['items'],[]);search.assert_not_called()
    async def test_invalid_extension_and_bad_media_rejected(self):
        for name in ['file.exe','broken.mp4']:
            form=FormData();form.add_field('file',b'bad media',filename=name)
            response=await self.client.post('/api/song-finder/file?consent=1',data=form);self.assertIn(response.status,[400,422])
    async def test_streamed_upload_has_independent_size_limit(self):
        form=FormData();form.add_field('file',b'x'*40,filename='sample.wav')
        with patch.object(songfinder,'MAX_UPLOAD',16):
            response=await self.client.post('/api/song-finder/file?consent=1',data=form)
        self.assertEqual(response.status,413)
    async def test_track_stats_batch_rejects_oversize(self):
        response=await self.client.post('/api/track-stats',json={'ids':['yt:abcdefghijk']*25});self.assertEqual(response.status,400)

if __name__=='__main__':unittest.main()
