"""Offline regressions: counter migration, session deduplication and metadata."""
import unittest
import tempfile
import sqlite3
from pathlib import Path
from kryonyx import storage, ytmusic, youtube, library, providers

class StudioTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.oldpath=storage._db_path
  self.oldconn=getattr(storage._local,'conn',None)
  storage._local.conn=None
  self.path=str(Path(self.tmp.name)/'music.sqlite')
  storage.init(self.path)
  self.track={'id':'yt:example','title':'Test','artist':'Artist','duration':180,'source':'youtube','views':123456,'stats_kind':'views'}
 def tearDown(self):
  conn=getattr(storage._local,'conn',None)
  if conn:conn.close()
  storage._local.conn=self.oldconn;storage._db_path=self.oldpath;self.tmp.cleanup()
 def test_metadata_survives_like_and_playlist(self):
  storage.toggle_like(self.track)
  self.assertEqual(storage.list_likes()[0]['views'],123456)
  pid=storage.create_playlist('Test')['id']
  storage.add_to_playlist(pid,self.track)
  self.assertEqual(storage.playlist_tracks(pid)[0]['stats_kind'],'views')
 def test_no_listens_is_zero(self):
  self.assertEqual(storage.listen_counts([self.track['id']]),{self.track['id']:0})
 def test_short_skip_does_not_count(self):
  storage.log_play(self.track,4,False,True,'one')
  self.assertEqual(storage.listen_counts([self.track['id']])[self.track['id']],0)
 def test_session_segments_count_once(self):
  storage.log_play(self.track,26,False,False,'one')
  self.assertEqual(storage.listen_counts([self.track['id']])[self.track['id']],0)
  storage.log_play(self.track,10,False,False,'one')
  storage.log_play(self.track,100,True,False,'one')
  self.assertEqual(storage.listen_counts([self.track['id']])[self.track['id']],1)
 def test_second_session_counts_twice(self):
  storage.log_play(self.track,35,False,False,'one')
  storage.log_play(self.track,35,False,False,'two')
  self.assertEqual(storage.listen_counts([self.track['id']])[self.track['id']],2)
 def test_completed_short_song_counts(self):
  storage.log_play(self.track,12,True,False,'one')
  self.assertEqual(storage.listen_counts([self.track['id']])[self.track['id']],1)
 def test_clearing_history_resets(self):
  storage.log_play(self.track,35,False,False,'one');storage.clear_history()
  self.assertEqual(storage.listen_counts([self.track['id']])[self.track['id']],0)
 def test_bound_parameters_and_legacy(self):
  weird={**self.track,'id':"yt:' OR 1=1 --"}
  storage.log_play(weird,40)
  self.assertEqual(storage.listen_counts([weird['id'],self.track['id']]),{weird['id']:1,self.track['id']:0})
 def test_ytmusic_formatted_stat_not_guessed(self):
  track=ytmusic._track({'videoId':'abc','title':'Song','views':'1.2M'})
  self.assertEqual(track['views'],'1.2M')
  self.assertEqual(len(providers._authors_from([track])),1)
 def test_provider_zero_and_missing(self):
  self.assertEqual(youtube._piped_track({'url':'/watch?v=abc','views':0})['views'],0)
  self.assertEqual(youtube._invidious_track({'videoId':'abc','viewCount':0})['views'],0)
  self.assertEqual(library._audius_track({'id':'abc','play_count':0})['play_count'],0)
  self.assertIsNone(library._audius_track({'id':'abc'})['play_count'])
 def test_old_database_migration(self):
  conn=storage._local.conn;conn.execute('ALTER TABLE history DROP COLUMN session_id');conn.commit()
  storage.init(self.path)
  self.assertIn('session_id',[r['name'] for r in conn.execute('PRAGMA table_info(history)')])
  storage.log_play(self.track,31,False,False,'new')
  self.assertEqual(storage.listen_counts([self.track['id']])[self.track['id']],1)


 def test_create_more_than_200_tracks_preserves_every_track(self):
  tracks=[{**self.track,'id':f'yt:bulk-{i}'} for i in range(350)]
  made=storage.create_playlist('Bulk',tracks)
  result=storage.playlist_tracks(made['id'])
  self.assertEqual(len(result),350)
  self.assertEqual([t['id'] for t in result],[t['id'] for t in tracks])
  self.assertEqual(result[-1]['views'],123456)
 def test_batch_add_deduplicates_and_preserves_order(self):
  made=storage.create_playlist('Batch',[self.track])
  b={**self.track,'id':'yt:b'};c={**self.track,'id':'yt:c'}
  self.assertEqual(storage.add_many_to_playlist(made['id'],[self.track,b,b,c]),2)
  self.assertEqual([t['id'] for t in storage.playlist_tracks(made['id'])],[self.track['id'],'yt:b','yt:c'])
  self.assertEqual(storage.add_many_to_playlist(999999,[b]),None)
 def test_failed_create_rolls_back_playlist(self):
  before=len(storage.list_playlists())
  with self.assertRaises(TypeError):storage.create_playlist('Broken',[{**self.track,'views':object()}])
  self.assertEqual(len(storage.list_playlists()),before)


class StudioAPITests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from aiohttp.test_utils import TestClient,TestServer
  from kryonyx import server
  self.tmp=tempfile.TemporaryDirectory();self.oldpath=storage._db_path
  self.oldconn=getattr(storage._local,'conn',None);storage._local.conn=None
  storage.init(str(Path(self.tmp.name)/'api.sqlite'))
  self.client=TestClient(TestServer(server.build_app()));await self.client.start_server()
 async def asyncTearDown(self):
  await self.client.close()
  # Close the main thread connection; worker connections end with executor.
  storage._local.conn.close();storage._local.conn=self.oldconn;storage._db_path=self.oldpath;self.tmp.cleanup()
 async def test_endpoint_validation_and_empty(self):
  for payload in [{'ids':'bad'},{'ids':[None]},{'ids':['x']*501}]:
   response=await self.client.post('/api/listen-counts',json=payload)
   self.assertEqual(response.status,400)
  response=await self.client.post('/api/listen-counts',json={'ids':['yt:new']})
  self.assertEqual(await response.json(),{'counts':{'yt:new':0}})
 async def test_real_play_endpoint_and_counts(self):
  track={'id':'yt:api','title':'Test','artist':'Artist','duration':180}
  for seconds in [26,8]:
   response=await self.client.post('/api/play',json={'track':track,'seconds':seconds,'session_id':'session-api'})
   self.assertEqual(response.status,200)
  response=await self.client.post('/api/listen-counts',json={'ids':['yt:api']})
  self.assertEqual(await response.json(),{'counts':{'yt:api':1}})
  await self.client.delete('/api/history')
  response=await self.client.post('/api/listen-counts',json={'ids':['yt:api']})
  self.assertEqual(await response.json(),{'counts':{'yt:api':0}})


 async def test_bulk_create_and_validation(self):
  import asyncio
  tracks=[{'id':f'yt:{i}','title':'Test','artist':'A','thumbnail':'/icon.png','views':i} for i in range(350)]
  response=await self.client.post('/api/playlists',json={'name':'Bulk','tracks':tracks})
  self.assertEqual(response.status,200)
  made=await response.json()
  self.assertEqual(made['count'],350)
  stored=await asyncio.to_thread(storage.playlist_tracks,made['id'])
  self.assertEqual(len(stored),350)
  self.assertEqual(stored[-1]['views'],349)
  before=await asyncio.to_thread(storage.list_playlists)
  for invalid in [[{}],[{'id':' '}]]:
   response=await self.client.post('/api/playlists',json={'name':'Invalid','tracks':invalid})
   self.assertEqual(response.status,400)
  after=await asyncio.to_thread(storage.list_playlists)
  self.assertEqual(len(before),len(after))
 async def test_batch_add_endpoint_and_single_compatibility(self):
  import asyncio
  response=await self.client.post('/api/playlists',json={'name':'Batch'})
  made=await response.json();pid=made['id']
  a={'id':'yt:a','title':'A'};b={'id':'yt:b','title':'B'}
  response=await self.client.post(f'/api/playlists/{pid}/tracks',json={'track':a})
  self.assertEqual((await response.json())['ok'],True)
  response=await self.client.post(f'/api/playlists/{pid}/tracks',json={'tracks':[a,b,b]})
  self.assertEqual((await response.json())['added'],1)
  stored=await asyncio.to_thread(storage.playlist_tracks,pid)
  self.assertEqual([t['id'] for t in stored],['yt:a','yt:b'])
  response=await self.client.post('/api/playlists/999999/tracks',json={'tracks':[a]})
  self.assertEqual(response.status,404)
  response=await self.client.post(f'/api/playlists/{pid}/tracks',json={'tracks':['invalid']})
  self.assertEqual(response.status,400)

 async def test_unlimited_import_roundtrip_v34(self):
  import asyncio
  tracks=[{'id':f'yt:large34_{i}','title':f'Track {i}','artist':'A'} for i in range(1250)]
  response=await self.client.post('/api/playlists',json={'name':'Large 34','tracks':tracks})
  self.assertEqual(response.status,200);made=await response.json();self.assertEqual(made['count'],1250)
  response=await self.client.post('/api/playlists/share-list',json={'name':'Shared 34','tracks':tracks})
  shared=await response.json();self.assertEqual(shared['count'],1250)
  response=await self.client.post('/api/playlists/decode',json={'code':shared['code']})
  decoded=await response.json();self.assertEqual(len(decoded['tracks']),1250)
  response=await self.client.post('/api/playlists/import',json={'code':shared['code'],'name':'Imported 34'})
  imported=await response.json();self.assertEqual(imported['added'],1250)
  stored=await asyncio.to_thread(storage.playlist_tracks,imported['id']);self.assertEqual(len(stored),1250)

if __name__=='__main__':unittest.main()
