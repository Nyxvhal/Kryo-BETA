import asyncio,json,plistlib,unittest
from unittest.mock import patch
from kryonyx import playlist_transfer as t, convert

class TransferParsing48(unittest.TestCase):
 def parse(self,s,name='list.csv',service='spotify'):return t.parse(s,name,service)
 def test_spotify_csv(self):
  x=self.parse('Track Name,Artist Name(s),Album Name,Track Duration (ms)\nHello,"A, B",Album,215000');self.assertEqual(x['items'][0]['artist'],'A, B');self.assertEqual(x['items'][0]['duration'],215)
 def test_cyrillic(self):self.assertEqual(self.parse('Название;Исполнитель;Длительность\nПесня;Автор;3:12')['items'][0]['duration'],192)
 def test_tsv(self):self.assertEqual(self.parse('title\tartist\nSong\tArtist')['total'],1)
 def test_utf8_bom(self):self.assertEqual(self.parse('\ufefftitle,artist\nSong,Artist')['total'],1)
 def test_json_wrappers(self):
  for data in [[{'title':'Song','artist':'A'}],{'tracks':{'items':[{'track':{'name':'Song','artists':[{'name':'A'}]}}]}},{'items':[{'attributes':{'name':'Song','artistName':'A','durationInMillis':230000}}]}]:self.assertEqual(self.parse(json.dumps(data))['items'][0]['artist'],'A')
 def test_vk_response(self):
  self.assertEqual(self.parse(json.dumps({'response':{'items':[{'title':'Song','artist':'A'}]}}),service='vk')['total'],1)
 def test_duration(self):
  for v,expected in [('3:20',200),('1:01:01',3661),('bad',None),('-1',None),('NaN',None)]:self.assertEqual(self.parse('title,duration\nSong,'+v)['items'][0]['duration'],expected)
 def test_m3u_metadata_only(self):
  x=self.parse('#EXTM3U\n#EXTINF:200,Artist - Song\nC:\\private\\music.mp3\nhttps://evil.example/file','list.m3u');self.assertEqual(x['total'],1);self.assertEqual(x['items'][0]['url'],'')
 def test_apple_xml_order(self):
  doc={'Tracks':{'1':{'Name':'One','Artist':'A','Total Time':100000},'2':{'Name':'Two','Artist':'B'}},'Playlists':[{'Name':'My list','Playlist Items':[{'Track ID':2},{'Track ID':1}]}]};x=self.parse(plistlib.dumps(doc).decode(),'apple.xml','apple-music');self.assertEqual(x['name'],'My list');self.assertEqual([i['title'] for i in x['items']],['Two','One']);self.assertEqual(x['items'][1]['duration'],100)
 def test_dedup(self):
  x=self.parse('title,artist,duration\nSong,A,100\nSong,A,100\nSong,B,100\nSong,A,200\n,A,');self.assertEqual((x['total'],x['duplicates'],x['skipped']),(3,1,1))
 def test_services(self):
  for svc in t.SERVICES:self.assertEqual(self.parse('title,artist\nSong,A',service=svc)['service'],svc)
 def test_reject_empty(self):
  for value in ['', '{}','[]','id,path\n1,/etc/passwd','{invalid']:
   with self.assertRaises(ValueError):self.parse(value)
 def test_size(self):
  with self.assertRaises(ValueError):self.parse('я'*(t.MAX_BYTES//2+1))
 def test_limit(self):
  with self.assertRaises(ValueError):self.parse('title,artist\n'+'Song,A\n'*5001)
 def test_wrong_service(self):
  with self.assertRaises(ValueError):self.parse('title\nSong',service='evil')
 def test_xml_entity(self):
  with self.assertRaises(ValueError):self.parse('<?xml version="1.0"?><!DOCTYPE plist [<!ENTITY x SYSTEM "file:///etc/passwd">]><plist/>','test.xml')
 def test_malformed_xml(self):
  with self.assertRaises(ValueError):self.parse('<?xml version="1.0"?><plist><dict><key>X</key>','broken.xml')
 def test_filename_is_not_path(self):self.assertEqual(self.parse('title\nSong','C:\\private\\name.csv')['name'],'name')
 def test_field_lengths(self):self.assertEqual(len(self.parse(json.dumps([{'title':'a'*1000}]))['items'][0]['title']),500)

class Matching48(unittest.IsolatedAsyncioTestCase):
 async def test_import_job_and_save(self):
  async def match(item,sources):return {'original':item,'match':{'id':'qa:song','title':item['title'],'artist':item['artist'],'source':'local'},'state':'good','score':1}
  source=t.parse('title,artist\nSong,A','list.csv','vk')
  with patch.object(convert.plugins,'enabled_sources',return_value=['youtube']),patch.object(convert,'match_one',side_effect=match):
   state=convert.start_import(source,['youtube']);self.assertNotIn('task',state);await convert.job(state['id'])['task'];done=convert.job(state['id']);self.assertEqual(done['stage'],'ready');self.assertEqual(done['matched'],1)
   with patch.object(convert.storage,'create_playlist',return_value={'id':123,'count':1}):
    result=convert.save(state['id']);self.assertEqual(result['added'],1)
 async def test_cancellation(self):
  async def slow(*a):await asyncio.sleep(60)
  with patch.object(convert.plugins,'enabled_sources',return_value=['youtube']),patch.object(convert,'match_one',side_effect=slow):
   state=convert.start_import(t.parse('title\nSong'),['youtube']);await asyncio.sleep(.01);result=await convert.cancel(state['id']);self.assertEqual(result['stage'],'cancelled')
 async def test_no_sources(self):
  with patch.object(convert.plugins,'enabled_sources',return_value=[]):
   with self.assertRaises(ValueError):convert.start_import(t.parse('title\nSong'))

if __name__=='__main__':unittest.main()
