import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from kryonyx import convert, ytmusic, server, extras
from kryonyx.search_rank34 import rank_tracks, relevance

class Rank34(unittest.TestCase):
 def test_exact_before_edits_and_long_mix(self):
  rows=[dict(id='remix',title='Addiction remix',artist='LONOWN',duration=200),dict(id='mix',title='Addiction',artist='LONOWN',duration=3600),dict(id='original',title='Addiction',artist='LONOWN',duration=200)]
  self.assertEqual(rank_tracks('LONOWN Addiction',rows)[0]['id'],'original')
  self.assertEqual(rank_tracks('LONOWN Addiction remix',rows)[0]['id'],'remix')
 def test_accents_and_typo(self):
  self.assertGreater(relevance('beyonce halo',dict(title='Halo',artist='Beyoncé')),100)
  self.assertGreater(relevance('lonnown addiction',dict(title='Addiction',artist='LONOWN')),relevance('lonnown addiction',dict(title='Other track',artist='Other')))
 def test_count_validation_no_cap(self):
  self.assertTrue(server._valid_track_batch([dict(id=str(i)) for i in range(1250)]))
  self.assertFalse(server._valid_track_batch([dict(id='')]))
 def test_share_roundtrip_1250(self):
  tracks=[dict(id=f'yt:{i}',title=f'Track {i}',artist='A') for i in range(1250)]
  name,decoded=extras.unpack_playlist(extras.pack_playlist('Large',tracks))
  self.assertEqual(name,'Large');self.assertEqual(len(decoded),1250)

class Async34(unittest.IsolatedAsyncioTestCase):
 async def test_catalogue_loads_all(self):
  tracks=[dict(videoId=f'v{i}',title=f'Track {i}',artists=[dict(name='A')]) for i in range(1205)]
  with patch.object(ytmusic,'ready',return_value=True),patch.object(ytmusic,'_call',new=AsyncMock(return_value=dict(tracks=tracks,trackCount=1205))) as call:
   result=await ytmusic.playlist('PLtest');self.assertEqual(len(result['tracks']),1205);self.assertIsNone(call.call_args.kwargs['limit'])
 async def test_api_collection_has_no_default_limit(self):
  with patch('kryonyx.providers.is_collection',return_value=True),patch('kryonyx.providers.collection',new=AsyncMock(return_value={'tracks':[]})) as call,patch('kryonyx.extras.fill_thumbnails',new=AsyncMock()):
   response=await server.api_collection(SimpleNamespace(query={'id':'test'}));self.assertEqual(response.status,200);call.assert_awaited_once_with('test',None)
 async def test_ytdlp_no_cap(self):
  entries=[dict(title=f'Track {i}',url=f'https://youtube.com/watch?v={i}',artist='A') for i in range(1205)]
  with patch('kryonyx.providers._aextract',new=AsyncMock(return_value={'entries':entries})) as extract:
   result=await convert._fetch_youtube_flat({'url':'https://youtube.com/playlist?list=test'})
   self.assertEqual(len(result['items']),1205);self.assertNotIn('playlistend',extract.call_args.args[1])
 async def test_piped_pagination(self):
  def rows(start):return [dict(title=f'Track {i}',url=f'/watch?v={i}',duration=200) for i in range(start,start+100)]
  pages=[dict(name='Large',relatedStreams=rows(0),nextpage='page2',videos=205),dict(relatedStreams=rows(100),nextpage='page3'),dict(relatedStreams=rows(200)[:5])]
  with patch('kryonyx.youtube._get',new=AsyncMock(side_effect=pages)) as get:
   result=await convert._fetch_youtube_api({'id':'PLtest'})
   self.assertEqual(len(result['items']),205);self.assertFalse(result['truncated']);self.assertEqual(get.await_count,3)
 async def test_piped_repeated_cursor_partial(self):
  page=dict(name='Large',relatedStreams=[dict(title='One',url='/watch?v=a')],nextpage='same',videos=100)
  with patch('kryonyx.youtube._get',new=AsyncMock(side_effect=[page,page])):
   result=await convert._fetch_youtube_api({'id':'PLtest'});self.assertTrue(result['truncated']);self.assertEqual(len(result['items']),1)
 async def test_spotify_pagination(self):
  def page(start,count,total=250):
   return {'data':{'playlistV2':{'content':{'totalCount':total,'items':[{'itemV2':{'data':{'uri':f'spotify:track:{i}','name':f'Track {i}'}}} for i in range(start,start+count)]}}}}
  with patch('kryonyx.spotify._query',new=AsyncMock(side_effect=[page(0,100),page(100,100),page(200,50)])) as get:
   result=await convert._spotify_playlist_pages({'id':'test'},{'items':[],'total':250})
   self.assertEqual(len(result['items']),250);self.assertFalse(result['truncated']);self.assertEqual([c.args[1]['offset'] for c in get.call_args_list],[0,100,200])
 async def test_matching_worker_count_and_order(self):
  source=dict(items=[dict(title=str(i)) for i in range(1205)],name='Large',service='youtube',type='playlist')
  active=peak=0
  async def match(item,sources):
   nonlocal active,peak
   active+=1;peak=max(peak,active);await asyncio.sleep(0);active-=1
   return dict(item,state='good')
  convert._jobs['v34test']={'updated':0,'items':[]}
  with patch.object(convert,'fetch',new=AsyncMock(return_value=source)),patch.object(convert,'match_one',side_effect=match):
   await convert._run('v34test','url',[])
  result=convert._jobs.pop('v34test');self.assertEqual(result['done'],1205);self.assertEqual([x['title'] for x in result['items']],[str(i) for i in range(1205)]);self.assertLessEqual(peak,8)
