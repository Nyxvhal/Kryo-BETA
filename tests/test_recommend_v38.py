"""Taste/novelty/diversity and collection coverage; no live provider dependencies."""
import unittest
from unittest.mock import AsyncMock,patch
from kryonyx import recommend

class Ranking38Tests(unittest.TestCase):
 def tr(self,id,title,artist,**kw):return dict(id=id,title=title,artist=artist,source='youtube',**kw)
 def test_popularity_counters_do_not_determine_cross_source_ranking(self):
  a=self.tr('yt:a','A','A',views=1);b=self.tr('yt:b','B','B',views=999999999999)
  self.assertEqual([x['id'] for x in recommend._score([a,b],{},set(),set())],['yt:a','yt:b'])
 def test_taste_and_novelty_are_bounded_and_effective(self):
  a=self.tr('yt:a','A','Known');b=self.tr('yt:b','B','New')
  self.assertEqual(recommend._score([a,b],{}, {'yt:a'},set())[0]['id'],'yt:b')
  self.assertEqual(recommend._score([a,b],{'known':100},set(),set())[0]['id'],'yt:a')
 def test_disliked_artists_are_excluded(self):
  self.assertEqual(recommend._score([self.tr('yt:a','A','Blocked')],{},set(),{'blocked'}),[])
 def test_duplicates_cross_provider_are_removed(self):
  x=recommend._score([self.tr('yt:a','Song','Artist'),self.tr('sc:b','Song','Artist')],{},set(),set())
  self.assertEqual(len(x),1)
 def test_frequent_artist_does_not_fill_the_head(self):
  tracks=[self.tr(f'yt:{i}',f'Track {i}','A') for i in range(10)]+[self.tr('yt:z','Other','B')]
  self.assertEqual(recommend._score(tracks,{'a':100},set(),set())[2]['artist'],'B')

class Collections38Tests(unittest.IsolatedAsyncioTestCase):
 async def test_albums_cannot_crowd_out_playlists(self):
  found={'albums':[{'id':'yt:a','title':'Album','artist':'Artist','kind':'album'}], 'playlists':[{'id':'sc:p','title':'Playlist','kind':'playlist'}]}
  with patch.object(recommend.storage,'top_artists',return_value=[{'artist':'Artist','weight':10},{'artist':'Other','weight':3}]),patch.object(recommend.storage,'disliked_artists',return_value=[]),patch.object(recommend.providers,'search_collections',AsyncMock(return_value=found)):
   rows=await recommend._collection_rows(2)
  self.assertEqual([r['kind'] for r in rows],['albums','playlists'])
  self.assertEqual(rows[0]['items'][0]['kind'],'album');self.assertEqual(rows[1]['items'][0]['kind'],'playlist')
 async def test_invalid_wrong_kind_and_blocked_collections_are_removed(self):
  found={'albums':[None,{}, {'id':'a','title':'Bad type','kind':'playlist'},{'id':'b','title':'Blocked','artist':'B'},{'id':'c','title':'Valid','kind':'album'}]}
  with patch.object(recommend.storage,'top_artists',return_value=[]),patch.object(recommend.storage,'disliked_artists',return_value=['B']),patch.object(recommend.providers,'search_collections',AsyncMock(return_value=found)):
   rows=await recommend._collection_rows(2)
  self.assertEqual([x['id'] for r in rows for x in r['items']],['c'])
 async def test_provider_failure_does_not_invent_collections(self):
  with patch.object(recommend.storage,'top_artists',return_value=[]),patch.object(recommend.providers,'search_collections',AsyncMock(side_effect=OSError('offline'))):
   self.assertEqual(await recommend._collection_rows(2),[])
