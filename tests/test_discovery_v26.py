import asyncio, unittest
from unittest.mock import AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer
from kryonyx import recommend as r, server

SEED={'id':'yt:seed','title':'Source song','artist':'Seed artist','source':'youtube'}
def track(i, title=None, artist='Artist', source='youtube'):
 return {'id':i,'title':title or i,'artist':artist,'source':source}

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.patches=[patch.object(r,'_user_sources',return_value=['youtube']),patch.object(r.storage,'get_settings',return_value={}),patch.object(r.storage,'played_ids',return_value={'yt:known'}),patch.object(r.storage,'list_likes',return_value=[track('yt:liked')])]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def test_textual_or_invalid_view_counts_never_break_ranking(self):
  counts=['1,234,567','1.2M','unknown',None,True,float('nan'),-5,8000]
  tracks=[{**track('yt:'+str(i)), 'views':v} for i,v in enumerate(counts)]
  ranked=r._score(tracks,{},set(),set())
  self.assertEqual(len(ranked),len(counts));self.assertEqual({x['id'] for x in ranked},{x['id'] for x in tracks})
 async def test_filters_seed_duplicate_hidden_and_disabled_source(self):
  items=[SEED,track('yt:copy',title=SEED['title'],artist=SEED['artist']),track('yt:a','A'),track('yt:dup','A'),track('yt:hidden'),track('sc:x',source='soundcloud')]
  with patch.object(r,'radio',AsyncMock(return_value=items)):
   d=await r.next_picks(SEED,['yt:hidden'])
  self.assertEqual([x['id'] for x in d['items']],['yt:a']);self.assertEqual(d['basis'],'related_track')
 async def test_history_and_likes_are_labeled_without_mutating_candidates(self):
  original=[track('yt:new'),track('yt:known'),track('yt:liked')]
  with patch.object(r,'radio',AsyncMock(return_value=original)):
   d=await r.next_picks(SEED)
  self.assertEqual([x['is_familiar'] for x in d['items']],[False,True,True]);self.assertNotIn('is_familiar',original[0])
 async def test_persistent_dismissal_and_identity(self):
  with patch.object(r.storage,'get_settings',return_value={'search26Hidden':['yt:a','meta:artist|same']}),patch.object(r,'radio',AsyncMock(return_value=[track('yt:a'),track('yt:b','Same'),track('yt:c')])):
   d=await r.next_picks(SEED)
  self.assertEqual([x['id'] for x in d['items']],['yt:c'])
 async def test_no_fabricated_tracks_when_provider_is_empty(self):
  with patch.object(r,'radio',AsyncMock(return_value=[])):
   self.assertEqual((await r.next_picks(SEED))['items'],[])
 async def test_bad_inputs_do_not_call_provider(self):
  with patch.object(r,'radio',AsyncMock()) as radio:
   for seed,excluded in [(None,None),({},None),({'id':[]},None),({**SEED,'title':{}},None),(SEED,{}),(SEED,[1]),(SEED,['x']*201)]:
    with self.subTest(seed=seed,excluded=str(excluded)[:20]):
     with self.assertRaises(ValueError):await r.next_picks(seed,excluded)
   radio.assert_not_awaited()
 async def test_network_failure_propagates_without_fake_items(self):
  with patch.object(r,'radio',AsyncMock(side_effect=OSError('offline'))):
   with self.assertRaises(OSError):await r.next_picks(SEED)
 async def test_radio_autoplay_also_respects_hidden_tracks_and_current_seed(self):
  with patch.object(r.storage,'disliked_artists',return_value=[]),patch.object(r.storage,'top_artists',return_value=[]),patch.object(r.providers,'related',AsyncMock(return_value=[SEED,track('yt:a'),track('yt:hidden')])),patch.object(r,'_search_many',AsyncMock(return_value=[])),patch.object(r.storage,'get_settings',return_value={'search26Hidden':['yt:hidden']}):
   out=await r.radio(SEED,5)
  self.assertEqual([x['id'] for x in out],['yt:a'])

class DiscoveryApiTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close()
 async def test_success(self):
  with patch.object(r,'next_picks',AsyncMock(return_value={'items':[track('yt:a')],'seed_id':SEED['id']})),patch.object(server.extras,'fill_thumbnails',AsyncMock()):
   response=await self.client.post('/api/recommend/next',json={'track':SEED,'exclude':[]})
   self.assertEqual(response.status,200);self.assertEqual((await response.json())['items'][0]['id'],'yt:a')
 async def test_invalid_seed(self):
  response=await self.client.post('/api/recommend/next',json={'track':None});self.assertEqual(response.status,400)
 async def test_timeout_returns_retryable_error(self):
  with patch.object(r,'next_picks',AsyncMock(side_effect=asyncio.TimeoutError())):
   response=await self.client.post('/api/recommend/next',json={'track':SEED});self.assertEqual(response.status,504)
 async def test_outage_returns_503(self):
  with patch.object(r,'next_picks',AsyncMock(side_effect=OSError('offline'))):
   response=await self.client.post('/api/recommend/next',json={'track':SEED});self.assertEqual(response.status,503)
 async def test_foreign_origin_rejected(self):
  response=await self.client.post('/api/recommend/next',json={'track':SEED},headers={'Origin':'https://foreign.example'});self.assertEqual(response.status,403)

class ProviderSourceTests(unittest.IsolatedAsyncioTestCase):
 async def test_disabled_youtube_is_not_queried_for_related_tracks(self):
  with patch.object(r.providers,'youtube_mix',AsyncMock()) as mix,patch.object(r.providers,'search',AsyncMock(return_value={'tracks':[]})) as search:
   await r.providers.related('yt:seed','Artist','Song',20,sources=['soundcloud'])
  mix.assert_not_awaited();self.assertEqual(search.call_args.kwargs['sources'],['soundcloud'])
 async def test_enabled_youtube_uses_actual_related_provider(self):
  with patch.object(r.providers,'youtube_mix',AsyncMock(return_value=[track('yt:'+str(i)) for i in range(20)])) as mix,patch.object(r.providers,'search',AsyncMock()) as search:
   data=await r.providers.related('yt:seed','Artist','Song',20,sources=['youtube'])
  mix.assert_awaited_once_with('seed',20);search.assert_not_awaited();self.assertEqual(len(data),20)
