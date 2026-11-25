import unittest
from unittest.mock import AsyncMock,patch
from kryonyx import trackmeta,recommend,ytmusic

class MetadataTests(unittest.TestCase):
 def test_promotional_suffixes_and_artist_prefix(self):
  t=trackmeta.clean_track({'id':'yt:abc','title':'CG5 - Night Song (Official Music Video)','artist':'CG5'})
  self.assertEqual(t['title'],'Night Song');self.assertEqual(t['id'],'yt:abc');self.assertEqual(t['original_title'],'CG5 - Night Song (Official Music Video)')
 def test_versions_not_removed(self):
  for label in ['Live','Remix','Acoustic','Sped Up','Remastered 2024']:
   t=trackmeta.clean_track({'title':f'Song ({label})','artist':'Band'});self.assertEqual(t['title'],f'Song ({label})')
 def test_unicode_and_entities(self):
  self.assertEqual(trackmeta.clean_track({'title':'  Night &amp; Day\n  ','artist':'Björk'})['title'],'Night & Day')
 def test_not_guessing_artist_from_title(self):
  self.assertEqual(trackmeta.clean_track({'title':'Band - Song','artist':'Uploader'})['title'],'Band - Song')
 def test_structured_collaborators_have_distinct_urls(self):
  t=ytmusic._track({'videoId':'a','title':'Song','artists':[{'name':'A','id':'UCa'},{'name':'B','id':'UCb'}]})
  self.assertEqual(len(t['artists']),2);self.assertNotEqual(t['artists'][0]['url'],t['artists'][1]['url'])
 def test_no_false_empty_title(self):
  self.assertTrue(trackmeta.clean_track({'title':'(Official Audio)','artist':''})['title'])

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
 async def test_sixty_candidates_retained(self):
  candidates=[{'id':str(i),'title':'Song '+str(i),'artist':'Artist '+str(i%10)} for i in range(100)]
  row=await recommend._row('Mix','For you',candidates);self.assertEqual(len(row['items']),60)
 async def test_provider_fetches_more_without_collections(self):
  with patch.object(recommend.providers,'search',AsyncMock(return_value={'tracks':[]})) as search,patch.object(recommend,'_user_sources',return_value=['archive']):
   await recommend._search_many(['test']);kw=search.call_args.kwargs;self.assertEqual(kw['limit'],48);self.assertFalse(kw['with_collections']);self.assertEqual(kw['sources'],['archive'])
 def test_dedupe_after_title_cleanup(self):
  items=[{'id':'1','title':'Artist - Song (Official Audio)','artist':'Artist'},{'id':'2','title':'Song','artist':'Artist'}]
  self.assertEqual(len(recommend._score(items,{},set(),set())),1)

class SuggestTests(unittest.IsolatedAsyncioTestCase):
 async def test_rich_suggest_keeps_search_history_separate(self):
  import json
  from aiohttp.test_utils import make_mocked_request
  from kryonyx import server
  with patch.object(server.storage,'recent_searches',return_value=['old query']),patch.object(server.providers,'suggest',AsyncMock(return_value=['query'])),patch.object(server.providers,'suggest_authors',AsyncMock(return_value=[{'name':'Artist'}])),patch.object(server.providers,'search',AsyncMock(return_value={'tracks':[{'id':'1','title':'Song'}]})) as search,patch.object(server.extras,'fill_thumbnails',AsyncMock()):
   data=json.loads((await server.api_suggest(make_mocked_request('GET','/api/suggest?q=music&rich=1&sources=archive'))).text)
   self.assertEqual(data['tracks'][0]['title'],'Song');self.assertEqual(data['history'],['old query']);self.assertFalse(search.call_args.kwargs['with_collections']);self.assertEqual(search.call_args.kwargs['sources'],['archive'])
 async def test_legacy_suggest_does_not_fetch_tracks(self):
  import json
  from aiohttp.test_utils import make_mocked_request
  from kryonyx import server
  with patch.object(server.storage,'recent_searches',return_value=[]),patch.object(server.providers,'suggest',AsyncMock(return_value=[])),patch.object(server.providers,'suggest_authors',AsyncMock(return_value=[])),patch.object(server.providers,'search',AsyncMock()) as search:
   data=json.loads((await server.api_suggest(make_mocked_request('GET','/api/suggest?q=music'))).text);search.assert_not_called();self.assertEqual(data['tracks'],[])

class SpotifyCollaboratorsTests(unittest.TestCase):
 def test_official_collaborators_use_distinct_profiles(self):
  from kryonyx import spotify
  t=spotify._official_track({'id':'track','name':'Song','artists':[{'id':'first','name':'First'},{'id':'second','name':'Second'}]})
  self.assertEqual([a['name'] for a in t['artists']],['First','Second'])
  self.assertEqual(t['artists'][0]['url'],'https://open.spotify.com/artist/first')
  self.assertEqual(t['artists'][1]['url'],'https://open.spotify.com/artist/second')
 def test_catalog_band_name_is_not_split(self):
  from kryonyx import spotify
  t=spotify._track({'uri':'spotify:track:abc','name':'Song','artists':{'items':[{'uri':'spotify:artist:band','profile':{'name':'Earth, Wind & Fire'}},{'uri':'spotify:artist:guest','profile':{'name':'Guest'}}]}})
  self.assertEqual(t['artists'][0]['name'],'Earth, Wind & Fire');self.assertEqual(t['artists'][1]['url'],'https://open.spotify.com/artist/guest')
