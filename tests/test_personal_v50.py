"""Account export privacy, bounded archives, replacement and recommendation signals."""
import asyncio,io,json,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch,AsyncMock
from kryonyx import account_import as imp,storage,recommend

def data(doc):return json.dumps(doc,ensure_ascii=False).encode()
def archive(files):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  for name,value in files.items():z.writestr(name,value)
 return b.getvalue()
class Parse50(unittest.TestCase):
 def parse(self,doc,name='music.json',service='spotify'):return imp.parse(data(doc),name,service)
 def test_spotify_history(self):
  x=self.parse([{'trackName':'Song','artistName':'Artist','msPlayed':180000,'endTime':'2024','ip_addr_decrypted':'PRIVATE'}]);self.assertEqual(len(x['history']),1);self.assertNotIn('PRIVATE',json.dumps(x))
 def test_extended_and_podcast_skips(self):
  x=self.parse([{'master_metadata_track_name':'Song','master_metadata_album_artist_name':'Artist','ms_played':90000},{'master_metadata_track_name':None,'episode_name':'Podcast','ms_played':60000},{'master_metadata_track_name':'Skip','ms_played':1000}]);self.assertEqual(len(x['history']),1);self.assertEqual(x['skipped'],2)
 def test_non_numeric_history_skips(self):
  x=self.parse({'favorites':[{'title':'A'}],'history':[{'title':'B','count':'NaN'}]});self.assertEqual(x['history'][0]['count'],1)
 def test_privacy_allowlist(self):
  x=self.parse({'email':'SECRET','password':'SECRET','favorites':[{'title':'Song','artist':'A','token':'SECRET','url':'file:///SECRET'}],'artists':[{'name':'B','address':'SECRET'}]});self.assertNotIn('SECRET',json.dumps(x));self.assertEqual(x['favorites'][0],{'title':'Song','artist':'A'})
 def test_library(self):self.assertEqual(len(self.parse({'tracks':[{'track':'Song','artist':'A'}]})['favorites']),1)
 def test_spotify_library_track_wrapper(self):self.assertEqual(self.parse({'tracks':[{'track':{'name':'Song','artists':[{'name':'A'}]}}]})['favorites'][0]['artist'],'A')
 def test_history_counts_deduplicate(self):
  x=self.parse({'history':[{'title':'Song','artist':'A','count':2},{'title':'Song','artist':'A','count':8}]});self.assertEqual(x['history'][0]['count'],10)
 def test_counts_bounded(self):self.assertEqual(self.parse({'history':[{'title':'A','count':1e20}]})['history'][0]['count'],100)
 def test_takeout_music_only(self):
  rows=[{'header':'YouTube Music','title':'Watched Artist - Song','subtitles':[{'name':'Artist - Topic'}]},{'header':'YouTube','title':'Watched NonMusic','subtitles':[]}];x=self.parse(rows,service='youtube-music');self.assertEqual(x['history'][0]['title'],'Song');self.assertEqual(x['history'][0]['artist'],'Artist');self.assertEqual(x['skipped'],1)
 def test_malformed_takeout_fields(self):
  for value in [12,{},True,'bad']:
   x=self.parse([{'header':'YouTube Music','title':'Song','subtitles':value,'products':value}],service='youtube-music');self.assertEqual(len(x['history']),1)
  x=self.parse([{'header':'YouTube Music','title':'Song','subtitles':[{'name':17}]}],service='youtube-music');self.assertEqual(x['history'][0]['artist'],'')
 def test_vk(self):self.assertEqual(len(self.parse({'response':{'items':[{'title':'Song','artist':'Artist'}]}},service='vk')['favorites']),1)
 def test_playlist_categories(self):self.assertEqual(len(self.parse({'playlists':[{'name':'List','items':[{'track':{'trackName':'A','artistName':'B'}}]}]})['playlists']),1)
 def test_csv_play_count(self):
  x=imp.parse(b'Track Name,Artist Name,Play Count\nSong,Artist,10','Music.csv','apple-music');self.assertEqual(x['history'][0]['count'],10)
 def test_archive_unknown_ignored(self):
  x=imp.parse(archive({'Music/library.json':data({'favorites':[{'title':'Song'}]}),'Account.json':data({'email':'PRIVATE'}),'picture.jpg':b'xxx'}),'account.zip','spotify');self.assertEqual(len(x['favorites']),1);self.assertGreaterEqual(x['ignored_files'],2)
 def test_no_music_error(self):
  with self.assertRaisesRegex(ValueError,'No supported'):self.parse({'email':'PRIVATE','password':'PRIVATE'})
 def test_zip_traversal(self):
  with self.assertRaisesRegex(ValueError,'Unsafe'):imp.parse(archive({'../test.json':b'[]'}),'bad.zip','spotify')
 def test_archive_ratio(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('music.json',' '*1000000)
  with self.assertRaisesRegex(ValueError,'compression'):imp.parse(b.getvalue(),'bad.zip','spotify')
 def test_corrupt_compressed_archive(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('music.json',data({'favorites':[{'title':'Song'}]}))
  raw=bytearray(b.getvalue());offset=30+len('music.json');raw[offset:offset+3]=b'\xff\xff\xff'
  with self.assertRaises(ValueError):imp.parse(bytes(raw),'broken.zip','spotify')
 def test_many_entries(self):
  with self.assertRaisesRegex(ValueError,'128'):imp.parse(archive({str(i)+'.json':b'[]' for i in range(129)}),'bad.zip','spotify')
 def test_bad_zip(self):
  with self.assertRaises(ValueError):imp.parse(b'PKbroken','bad.zip','spotify')
 def test_empty_file(self):
  with self.assertRaises(ValueError):imp.parse(b'','x.json','spotify')
 def test_invalid_service(self):
  with self.assertRaises(ValueError):self.parse([],service='bad')
 def test_over_limit(self):
  with self.assertRaises(ValueError):imp.parse(b'x'*(imp.MAX_UPLOAD+1),'x.json','spotify')
 def test_invalid_utf8(self):
  with self.assertRaises(ValueError):imp.parse(b'\xff\xfe','x.json','spotify')
 def test_unique_limit(self):
  with self.assertRaisesRegex(ValueError,'5000'):self.parse({'favorites':[{'title':str(i),'artist':'A'} for i in range(5001)]})
 def test_record_limit(self):
  with self.assertRaisesRegex(ValueError,'25000'):self.parse({'history':[{'title':'A'}]*25001})
class StorageBase:
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.oldpath=storage._db_path;self.oldconn=getattr(storage._local,'conn',None);storage._local.conn=None;storage.init(self.tmp.name+'/qa.db');imp._staged.clear();imp._context_cache=None;recommend.invalidate()
 def tearDown(self):
  storage._local.conn.close();storage._local.conn=self.oldconn;storage._db_path=self.oldpath;self.tmp.cleanup();imp._context_cache=None;recommend.invalidate()
 def stage(self,service='spotify',title='Song'):
  return imp.stage(data({'favorites':[{'title':title,'artist':'Artist'}],'history':[{'title':'Past','artist':'Other','count':100}],'artists':['Artist']}),'profile.json',service)
class Profile50(StorageBase,unittest.TestCase):
 def test_apply_idempotent(self):
  p=self.stage();self.assertFalse(imp.apply(p['token'],['favorites'])['unchanged']);self.assertTrue(imp.apply(p['token'],['favorites'])['unchanged']);self.assertEqual(len(imp.profiles()),1)
 def test_selected_categories_only(self):
  p=self.stage();imp.apply(p['token'],['history']);x=imp.profiles()[0];self.assertEqual(x['favorites'],[]);self.assertEqual(len(x['history']),1)
 def test_reimport_replaces_not_accumulates(self):
  p=self.stage();imp.apply(p['token'],['favorites']);q=self.stage(title='Different');imp.apply(q['token'],['favorites']);self.assertEqual(imp.profiles()[0]['favorites'][0]['title'],'Different')
 def test_local_counts_untouched(self):
  p=self.stage();imp.apply(p['token'],['favorites','history','artists']);self.assertEqual(storage.history(),[]);self.assertEqual(storage.top_artists(),[]);self.assertEqual(storage.list_likes(),[])
 def test_service_deletion_is_scoped(self):
  for service in ['spotify','vk']:imp.apply(self.stage(service)['token'],['favorites'])
  imp.remove('spotify');self.assertEqual([x['service'] for x in imp.summary()],['vk'])
 def test_expired_token(self):
  p=self.stage();imp._staged[p['token']]=(time.monotonic()-1,{})
  with self.assertRaisesRegex(ValueError,'expired'):imp.apply(p['token'],['favorites'])
 def test_none_selected(self):
  p=self.stage()
  with self.assertRaises(ValueError):imp.apply(p['token'],[])
 def test_stage_cache_bounded(self):
  for _ in range(12):self.stage()
  self.assertEqual(len(imp._staged),8)
 def test_context_weight_capped(self):
  p=self.stage();imp.apply(p['token'],['favorites','history']);self.assertTrue(all(x['weight']<=30 for x in imp.context()['artists']))
 def test_import_used_for_top_artists(self):
  imp.apply(self.stage()['token'],['favorites']);self.assertEqual(recommend._top_artists()[0]['artist'],'Artist')
 def test_zero_influence_ignores_import(self):
  imp.apply(self.stage()['token'],['favorites']);storage.save_settings({'recommend50':{'importInfluence':0}});self.assertEqual(recommend._top_artists(),[])
 def test_cached_context_removed(self):
  imp.apply(self.stage()['token'],['favorites']);self.assertTrue(imp.context()['liked']);imp.remove('spotify');self.assertFalse(imp.context()['liked'])
 def test_hidden_recording_cross_source(self):
  storage.save_settings({'search26Hidden':['meta:artist|song']});self.assertEqual(recommend._score([{'id':'yt:s','title':'Song','artist':'Artist'}],{},set(),set()),[])
 def test_imported_history_is_familiar(self):
  imp.apply(self.stage()['token'],['history']);r=recommend._score([{'id':'yt:s','title':'Past','artist':'Other'}],{},set(),set());self.assertTrue(r[0]['recommend_familiar'])
 def test_discovery_control_changes_order(self):
  tracks=[{'id':'known','title':'Known','artist':'A'},{'id':'new','title':'New','artist':'B'}];storage.save_settings({'recommend50':{'discovery':0}});self.assertEqual(recommend._score(tracks,{}, {'known'},set())[0]['id'],'known');storage.save_settings({'recommend50':{'discovery':100}});self.assertEqual(recommend._score(tracks,{}, {'known'},set())[0]['id'],'new')
 def test_scope_changes_with_profile(self):
  before=recommend._scope();imp.apply(self.stage()['token'],['favorites']);self.assertNotEqual(before,recommend._scope())
 def test_invalid_preferences_safe(self):
  storage.save_settings({'recommend50':{'discovery':'oops','importInfluence':{}}});self.assertEqual(recommend.preferences(),{'discovery':50,'importInfluence':65})
class Generation50(StorageBase,unittest.IsolatedAsyncioTestCase):
 async def test_cancelled_build_cleans_up_provider_jobs(self):
  started=asyncio.Event();tasks=[]
  async def find(*a,**k):
   tasks.append(asyncio.current_task());started.set();await asyncio.Event().wait()
  with patch.object(recommend,'_search_many',find),patch.object(recommend,'_collection_rows',AsyncMock(return_value=[])),patch.object(recommend.extras,'fill_thumbnails',AsyncMock()):
   build=asyncio.create_task(recommend.build_rows(2));await started.wait();build.cancel()
   with self.assertRaises(asyncio.CancelledError):await build
   self.assertTrue(all(t.done() for t in tasks))
 async def test_obsolete_build_cannot_repopulate_cache(self):
  started=asyncio.Event();release=asyncio.Event()
  async def find(*a,**k):
   started.set();await release.wait();return [{'id':str(i),'title':str(i),'artist':'A','source':'youtube'} for i in range(6)]
  with patch.object(recommend,'_search_many',find),patch.object(recommend,'_collection_rows',AsyncMock(return_value=[])),patch.object(recommend.extras,'fill_thumbnails',AsyncMock()):
   task=asyncio.create_task(recommend.build_rows(2));await started.wait();recommend.invalidate();release.set();await task;self.assertEqual(recommend._cache,{})
if __name__=='__main__':unittest.main()
