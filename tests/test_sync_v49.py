"""Real SQLite regression tests for additive refresh, counts and retry safety."""
import concurrent.futures,tempfile,unittest
from kryonyx import convert,storage
class Saves49(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.oldpath=storage._db_path;self.oldconn=getattr(storage._local,'conn',None);storage._local.conn=None;storage.init(self.temp.name+'/qa.db')
  self.tracks=[{'id':'qa:1','title':'First','artist':'Artist','source':'local'},{'id':'qa:2','title':'Second','artist':'Artist','source':'local'}]
  convert._jobs['qa49']={'stage':'ready','name':'Collection','items':[{'match':t,'state':'good'} for t in self.tracks]}
 def tearDown(self):
  convert._jobs.pop('qa49',None);storage._local.conn.close();storage._local.conn=self.oldconn;storage._db_path=self.oldpath;self.temp.cleanup()
 def test_atomic_new_playlist(self):
  r=convert.save('qa49');self.assertEqual(r['added'],2);self.assertEqual(storage.playlist_tracks(r['playlist']['id'])[1]['title'],'Second')
 def test_new_retry_creates_once(self):
  a=convert.save('qa49');b=convert.save('qa49');self.assertEqual(a['playlist']['id'],b['playlist']['id']);self.assertEqual(b['added'],0);self.assertEqual(len(storage.list_playlists()),2)
 def test_additive_count_and_order(self):
  p=storage.create_playlist('Existing',[self.tracks[0]]);r=convert.save('qa49',playlist_id=p['id']);self.assertEqual(r['added'],1);self.assertEqual(r['duplicates'],1);self.assertEqual(r['playlist']['name'],'Existing');self.assertEqual([x['id'] for x in storage.playlist_tracks(p['id'])],['qa:1','qa:2'])
 def test_all_duplicates_are_zero(self):
  p=storage.create_playlist('Existing',self.tracks);self.assertEqual(convert.save('qa49',playlist_id=p['id'])['added'],0)
 def test_missing_destination_is_error(self):
  with self.assertRaisesRegex(ValueError,'no longer exists'):convert.save('qa49',playlist_id=999)
  self.assertEqual(len(storage.list_playlists()),1)
 def test_no_private_cache_in_api(self):
  convert.save('qa49');self.assertNotIn('_saves',convert._public(convert._jobs['qa49']))
 def test_parallel_duplicate_post(self):
  with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:convert.save('qa49'),range(2)))
  self.assertEqual(len(storage.list_playlists()),2);self.assertEqual(sum(r['added'] for r in results),2)
 def test_new_selection_after_save(self):
  convert.save('qa49',skip=[1]);r=convert.save('qa49',name='Other',skip=[0]);self.assertEqual(r['added'],1)
class Links49(unittest.TestCase):
 def test_spoofed_hosts(self):
  for u in ['https://evil.test/open.spotify.com/playlist/123456789012345','https://youtube.com.evil.test/playlist?list=PL1234567890123','https://evil.test/?url=https://soundcloud.com/artist/song','https://open.spotify.com@evil.test/playlist/1234567890123','file:///youtube.com/playlist?list=PL1234567890123','https://youtube.com:9999/playlist?list=PL1234567890123','https://a:b@youtube.com/playlist?list=PL1234567890123']:
   self.assertIsNone(convert.parse_link(u),u)
 def test_real_hosts(self):
  for u in ['https://open.spotify.com/playlist/123456789012345','https://music.youtube.com/playlist?list=PL1234567890123','https://soundcloud.com/artist/sets/list','https://www.deezer.com/en/playlist/123']:
   self.assertIsNotNone(convert.parse_link(u),u)
if __name__=='__main__':unittest.main()
