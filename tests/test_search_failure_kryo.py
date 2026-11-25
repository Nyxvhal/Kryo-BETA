"""Do not turn provider failures into sticky, complete empty search results."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import make_mocked_request
from kryonyx import providers, server, ytmusic


class SearchFailureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        providers._collection_cache.clear()
        providers._search_cache.clear()

    async def test_ytmusic_distinguishes_failure_from_successful_empty(self):
        with patch.object(ytmusic, 'ready', return_value=True), patch.object(
            ytmusic, '_call', new=AsyncMock(side_effect=[OSError('offline'), [], OSError('offline'), []])
        ):
            bad_artist = await ytmusic.artists('Artist')
            good_artist = await ytmusic.artists('Artist')
            bad_album = await ytmusic.albums('Album')
            good_album = await ytmusic.albums('Album')
        self.assertTrue(bad_artist.degraded)
        self.assertEqual(good_artist, [])
        self.assertFalse(hasattr(good_artist, 'degraded'))
        self.assertTrue(bad_album.degraded)
        self.assertEqual(good_album, [])
        self.assertFalse(hasattr(good_album, 'degraded'))

    async def test_playlist_preserves_partial_results_and_failure(self):
        complete = [{'id':'pl:1', 'count':2}]
        with patch.object(ytmusic, '_search_collections', new=AsyncMock(
            side_effect=[complete, ytmusic.IncompleteSearchResults()]
        )):
            result = await ytmusic.playlists('Artist', 10)
        self.assertTrue(result.degraded)
        self.assertEqual(result, complete)

    async def test_collections_failure_is_retryable_and_success_is_cached(self):
        album = {'id':'album:1', 'title':'Artist album', 'artist':'Artist'}
        albums = AsyncMock(side_effect=[ytmusic.IncompleteSearchResults([album]), [album]])
        playlists = AsyncMock(return_value=[])
        with patch.object(ytmusic, 'albums', albums), patch.object(ytmusic, 'playlists', playlists):
            first = await providers.search_collections('Artist')
            second = await providers.search_collections('Artist')
            third = await providers.search_collections('Artist')
        self.assertTrue(first['degraded'])
        self.assertEqual(first['albums'], [album])
        self.assertNotIn('degraded', second)
        self.assertEqual(second, third)
        self.assertEqual(albums.await_count, 2)
        self.assertEqual(playlists.await_count, 2)

    async def test_collection_exception_does_not_cache_empty(self):
        albums = AsyncMock(side_effect=[OSError('offline'), []])
        with patch.object(ytmusic, 'albums', albums), patch.object(ytmusic, 'playlists', AsyncMock(return_value=[])):
            self.assertTrue((await providers.search_collections('Artist'))['degraded'])
            self.assertNotIn('degraded', await providers.search_collections('Artist'))
        self.assertEqual(albums.await_count, 2)

    async def test_extra_endpoint_marks_artist_and_collection_failures(self):
        request = make_mocked_request('GET', '/api/search/extra?q=Artist')
        with patch.object(providers, 'search_collections', AsyncMock(return_value={'albums':[], 'playlists':[], 'degraded':True})), patch.object(
            ytmusic, 'artists', AsyncMock(return_value=[])
        ):
            response = await server.api_search_extra(request)
        self.assertTrue(json.loads(response.text)['degraded'])
        with patch.object(providers, 'search_collections', AsyncMock(return_value={'albums':[], 'playlists':[]})), patch.object(
            ytmusic, 'artists', AsyncMock(side_effect=OSError('offline'))
        ):
            response = await server.api_search_extra(request)
        self.assertTrue(json.loads(response.text)['degraded'])

    async def test_track_source_failure_not_cached_as_success(self):
        youtube = AsyncMock(side_effect=[OSError('offline'), []])
        with patch.object(providers.plugins, 'enabled_sources', return_value=['youtube']), patch.object(
            providers, 'search_youtube', youtube
        ), patch.object(ytmusic, 'artists', AsyncMock(return_value=[])):
            first = await providers.search('SearchfailureUnique', sources=['youtube'], with_collections=False)
            second = await providers.search('SearchfailureUnique', sources=['youtube'], with_collections=False)
            third = await providers.search('SearchfailureUnique', sources=['youtube'], with_collections=False)
        self.assertTrue(first['degraded'])
        self.assertNotIn('degraded', second)
        self.assertEqual(second, third)
        self.assertEqual(youtube.await_count, 2)
