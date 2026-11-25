"""Offline wave ranking and bounded prefetch state contracts; no external services."""
import unittest
from unittest.mock import patch,AsyncMock
from contextlib import ExitStack
from kryonyx import recommend as r,server

def track(i,artist='Artist',title=None,source='youtube'):
 return dict(id='yt:'+str(i),title=title or 'Song '+str(i),artist=artist,source=source,duration=180)
class Wave61(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.stack=ExitStack();self.addCleanup(self.stack.close)
  for key,val in {'_user_sources':lambda:['youtube'],'_top_artists':lambda *a:[], '_external':lambda:{'artists':[],'played':set(),'liked':set(),'queries':[]}}.items():self.stack.enter_context(patch.object(r,key,val))
  for key,val in {'get_settings':lambda:{},'played_ids':lambda *a:set(),'list_likes':lambda *a:[],'disliked_artists':lambda:[]}.items():self.stack.enter_context(patch.object(r.storage,key,val))
  self.related=self.stack.enter_context(patch.object(r.providers,'related',AsyncMock(return_value=[track(i,chr(65+i%4)) for i in range(16)])))
  self.search=self.stack.enter_context(patch.object(r,'_search_many',AsyncMock(return_value=[])))
 async def test_seed_related_and_bounded(self):
  out=await r.wave_candidates(track('seed'),limit=100)
  self.assertEqual(len(out['items']),12);self.assertEqual(out['seed_id'],'yt:seed');self.assertEqual(self.related.call_args.kwargs['sources'],['youtube']);self.search.assert_not_called()
 async def test_seed_ids_and_cross_provider_identity_removed(self):
  seed=track('seed');self.related.return_value=[seed,track('duplicate',title=seed['title']),track('ok','Other')]
  out=await r.wave_candidates(seed);self.assertEqual([x['id'] for x in out['items']],['yt:ok'])
 async def test_exclusions_and_source_choice(self):
  self.related.return_value=[track('excluded'),track('off',source='soundcloud'),track('ok')]
  out=await r.wave_candidates(track('seed'),['yt:excluded']);self.assertEqual([x['id'] for x in out['items']],['yt:ok'])
 async def test_blocked_and_hidden(self):
  with patch.object(r.storage,'disliked_artists',return_value=['Blocked']),patch.object(r.storage,'get_settings',return_value={'search26Hidden':['yt:hide']}):
   self.related.return_value=[track('blocked','Blocked'),track('hide'),track('ok')];out=await r.wave_candidates(track('seed'));self.assertEqual([x['id'] for x in out['items']],['yt:ok'])
 async def test_modes_bias_familiarity(self):
  with patch.object(r.storage,'played_ids',return_value={'yt:4','yt:5'}):
   familiar=await r.wave_candidates(track('seed'),mode='familiar');fresh=await r.wave_candidates(track('seed'),mode='discover')
   self.assertTrue(familiar['items'][0]['is_familiar']);self.assertFalse(fresh['items'][0]['is_familiar'])
 async def test_same_artist_fallback_not_random_hits(self):
  self.related.return_value=[];await r.wave_candidates(track('seed','Seed artist'));self.search.assert_awaited_once_with(['Seed artist'],24)
 async def test_empty_is_honest(self):
  self.related.return_value=[];self.assertEqual((await r.wave_candidates(track('seed')))['items'],[])
 async def test_invalid_input(self):
  for seed,exclude,mode in [(None,None,'balanced'),({},None,'balanced'),(track('a'),['x']*201,'balanced'),(track('a'),None,'unknown')]:
   with self.assertRaises(ValueError):await r.wave_candidates(seed,exclude,mode)
 async def test_artist_diversity(self):
  self.related.return_value=[track(i,'Same' if i<10 else str(i)) for i in range(16)]
  out=await r.wave_candidates(track('seed'));self.assertLessEqual(sum(x['artist']=='Same' for x in out['items'][:6]),2)
 async def test_prefetch_download_and_stream_modes(self):
  with patch.object(server.audiovault,'enabled',return_value=True),patch.object(server,'_ensure_file',AsyncMock(return_value='cached')) as download,patch.object(server.audiocache,'find',return_value='cached'):
   await server._prefetch_one30('test61','Title','Artist',True);download.assert_awaited_once();self.assertEqual(server._prefetch_status61['test61']['state'],'downloaded')
  with patch.object(server.audiovault,'enabled',return_value=False),patch.object(server,'_media_for',AsyncMock()) as resolve,patch.object(server,'_ensure_file',AsyncMock()) as download:
   await server._prefetch_one30('stream61','Title','Artist',True);resolve.assert_awaited_once();download.assert_not_called();self.assertEqual(server._prefetch_status61['stream61']['state'],'resolved')
 async def test_prefetch_status_never_starts_a_download(self):
  import json
  from types import SimpleNamespace
  with patch.object(server.audiocache,'find',return_value=None),patch.object(server,'_prefetch_one30',AsyncMock()) as work:
   response=await server.api_prefetch(SimpleNamespace(query={'id':'missing61','status':'1'}))
   self.assertEqual(json.loads(response.body)['state'],'idle');work.assert_not_called()
 async def test_cleared_download_is_not_reported_ready(self):
  import json
  from types import SimpleNamespace
  server._prefetch_status61['evicted61']={'state':'downloaded','cached':True}
  with patch.object(server.audiocache,'find',return_value=None):
   response=await server.api_prefetch(SimpleNamespace(query={'id':'evicted61','status':'1'}))
   self.assertFalse(json.loads(response.body)['cached']);self.assertNotEqual(json.loads(response.body)['state'],'downloaded')
 async def test_prefetch_error_not_success(self):
  with patch.object(server.audiovault,'enabled',return_value=True),patch.object(server,'_ensure_file',AsyncMock(side_effect=RuntimeError('no network'))):
   await server._prefetch_one30('fail61','','',True);self.assertEqual(server._prefetch_status61['fail61']['state'],'error')
if __name__=='__main__':unittest.main()
