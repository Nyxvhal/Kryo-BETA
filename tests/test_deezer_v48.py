import unittest
from unittest.mock import patch,AsyncMock
from kryonyx import convert

class Deezer48(unittest.IsolatedAsyncioTestCase):
 def test_links(self):
  for kind in ('playlist','album','track'):
   x=convert.parse_link('https://www.deezer.com/en/'+kind+'/12345');self.assertEqual((x['service'],x['type'],x['id']),('deezer',kind,'12345'))
 def test_reject_hosts(self):
  for url in ['https://deezer.com.evil/playlist/1','https://evil.example/deezer.com/playlist/1','https://www.deezer.com/playlist/not-a-number','file://deezer.com/playlist/1']:
   self.assertIsNone(convert.parse_link(url))
 def test_youtube_music(self):self.assertEqual(convert.parse_link('https://music.youtube.com/playlist?list=PL1234567890123456789')['service'],'youtube')
 async def test_pages_use_fixed_host(self):
  class Response:
   status=200
   def __init__(self,data):self.data=data
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
   async def json(self,**kw):return self.data
  class Session:
   calls=[]
   def get(self,url,**kw):
    self.calls.append((url,kw));return Response({'title':'List','nb_tracks':2,'tracks':{'data':[{'title':'One','artist':{'name':'A'},'duration':100}],'next':'https://evil.example/steal'}} if len(self.calls)==1 else {'data':[{'title':'Two','artist':{'name':'B'},'duration':200}]})
  session=Session()
  with patch.object(convert.library,'http',new=AsyncMock(return_value=session)):
   x=await convert.fetch('https://www.deezer.com/playlist/12345')
  self.assertEqual([x['title'] for x in x['items']],['One','Two']);self.assertFalse(x['truncated']);self.assertEqual(session.calls[1][0],'https://api.deezer.com/playlist/12345/tracks?index=1&limit=100');self.assertTrue(all(c[1]['allow_redirects'] is False for c in session.calls))
 async def test_denied_is_actionable(self):
  class R:
   status=403
   async def __aenter__(self):return self
   async def __aexit__(self,*a):pass
  class S:
   def get(self,*a,**kw):return R()
  with patch.object(convert.library,'http',new=AsyncMock(return_value=S())):
   with self.assertRaisesRegex(ValueError,'metadata file'):await convert.fetch('https://www.deezer.com/playlist/12345')

if __name__=='__main__':unittest.main()
