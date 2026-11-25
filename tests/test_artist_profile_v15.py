"""Artist pages must not degrade into a broad search/recommendation feed."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import make_mocked_request
from kryonyx import providers, server, trackmeta

URL='https://music.youtube.com/channel/UCartist'
def track(ident, artist, **extra):
    return dict(id='yt:'+ident, title='Song '+ident, artist=artist, **extra)

class ArtistFilterTests(unittest.TestCase):
    def page(self, own=(), extra=(), name='CG5', url=None):
        return providers._author_page(name,url,'youtube',list(own),list(extra),40,False)
    def test_sparse_catalog_never_appends_other_artists(self):
        page=self.page([track('own','CG5')],[track('mine','CG5'),track('other','Other'),track('title','Someone',original_title='CG5 song')])
        self.assertEqual([t['id'] for t in page['tracks']],['yt:own','yt:mine'])
    def test_zero_matching_returns_empty_not_search_feed(self):
        self.assertEqual(self.page(extra=[track('other','Other')])['tracks'],[])
    def test_substrings_do_not_match(self):
        for artist in ['CG50','Not CG5','CG5 tribute','Alison']:
            self.assertFalse(trackmeta.artist_track_matches(track('a',artist),'CG5' if artist!='Alison' else 'Ali'))
    def test_structured_collaborator_is_included(self):
        t=track('collab','Guest, CG5',artists=[{'name':'Guest','url':'https://music.youtube.com/channel/UCguest'},{'name':'CG5','url':URL}])
        self.assertTrue(trackmeta.artist_track_matches(t,'CG5',URL))
        self.assertTrue(trackmeta.artist_track_matches(t,'Guest'))
    def test_same_name_with_different_stable_identity_is_rejected(self):
        t=track('wrong','CG5',artists=[{'name':'CG5','url':'https://youtube.com/channel/UCdifferent'}])
        self.assertFalse(trackmeta.artist_track_matches(t,'CG5',URL))
    def test_matching_profile_cross_domain_and_tab(self):
        t=track('own','Uploader',author_url='https://www.youtube.com/channel/UCartist/videos?x=1')
        self.assertTrue(trackmeta.artist_track_matches(t,'CG5',URL))
    def test_direct_profile_without_credits_is_trusted_not_search(self):
        t=track('empty','')
        self.assertTrue(trackmeta.artist_track_matches(t,'CG5',URL,from_profile=True))
        self.assertFalse(trackmeta.artist_track_matches(t,'CG5',URL))
    def test_conflicting_direct_profile_not_trusted(self):
        t=track('bad','Other',author_url='https://youtube.com/channel/UCother')
        self.assertFalse(trackmeta.artist_track_matches(t,'CG5',URL,from_profile=True))
    def test_legacy_collaborators_and_band_names(self):
        for artist,name in [('CG5, Ironmouse','Ironmouse'),('CG5 feat. Guest','Guest'),('Earth, Wind & Fire','Earth, Wind & Fire'),('Simon & Garfunkel','Simon & Garfunkel'),('AC/DC','AC/DC')]:
            self.assertTrue(trackmeta.artist_track_matches(track('a',artist),name))
        self.assertFalse(trackmeta.artist_track_matches(track('a','Other',artists=[{'name':'Simon & Garfunkel'}]),'Simon'))
    def test_unicode_and_topic_suffix(self):
        self.assertTrue(trackmeta.artist_track_matches(track('a','Björk - Topic'),'Björk'))
        self.assertTrue(trackmeta.artist_track_matches(track('a','Певец'),'певец'))
    def test_soundcloud_profile_and_lookalike_host(self):
        self.assertTrue(trackmeta.artist_track_matches(track('a','Other',author_url='https://soundcloud.com/artist/tracks'),'Name','https://soundcloud.com/artist'))
        self.assertIsNone(trackmeta.artist_profile_key('https://soundcloud.com.evil/artist'))
    def test_dedupe_and_limit_after_filter(self):
        mine=[track(str(i),'CG5') for i in range(55)]
        p=self.page(mine,mine+[track('bad','Other')])
        self.assertEqual(len(p['tracks']),40)
    def test_channel_id_is_case_sensitive(self):
        t=track('a','CG5',author_url='https://youtube.com/channel/UCArtist')
        self.assertFalse(trackmeta.artist_track_matches(t,'CG5',URL))

class ArtistAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        providers._page_cache.clear()
        self.portraits=patch('kryonyx.artist_portraits.portrait',AsyncMock(return_value={}))
        self.portraits.start();self.addAsyncCleanup(asyncio.to_thread,self.portraits.stop)
    async def test_actual_author_pipeline_filters_search_results(self):
        with patch.object(providers,'AUTHOR_DEADLINE',.01),patch.object(providers.ytmusic,'search',AsyncMock(return_value=[track('mine','CG5'),track('wrong','Other')])),patch.object(providers,'_search_tracks',AsyncMock(return_value=[track('other','Somebody')])):
            result=await providers.author('CG5')
            self.assertEqual([t['id'] for t in result['tracks']],['yt:mine'])
    async def test_warm_cache_does_not_reintroduce_strangers(self):
        async def slow(*args):
            await asyncio.sleep(.04)
            return [track('own','CG5',author_url=URL)]
        with patch.object(providers,'AUTHOR_DEADLINE',.005),patch.object(providers,'_youtube_channel',slow),patch.object(providers.ytmusic,'search',AsyncMock(return_value=[track('other','Other')])),patch.object(providers,'_search_tracks',AsyncMock(return_value=[])):
            first=await providers.author('CG5',url=URL)
            self.assertEqual(first['tracks'],[])
            await asyncio.sleep(.08)
            final=await providers.author('CG5',url=URL)
            self.assertEqual([t['id'] for t in final['tracks']],['yt:own'])
            self.assertFalse(final['partial'])
    async def test_api_returns_only_filtered_artist_tracks(self):
        with patch.object(providers.ytmusic,'search',AsyncMock(return_value=[track('mine','CG5'),track('wrong','Other')])),patch.object(providers,'_search_tracks',AsyncMock(return_value=[])),patch.object(server.extras,'fill_thumbnails',AsyncMock()):
            response=await server.api_author(make_mocked_request('GET','/api/author?name=CG5&catalog=v15'))
            result=json.loads(response.text)
            self.assertEqual([t['id'] for t in result['tracks']],['yt:mine'])

if __name__=='__main__': unittest.main()
