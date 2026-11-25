import asyncio,json,tempfile,unittest
from unittest.mock import patch,AsyncMock
from aiohttp.test_utils import TestClient,TestServer
from kryonyx import server,storage,account_import,convert
class API50(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.oldpath=storage._db_path;self.oldconn=getattr(storage._local,'conn',None);storage._local.conn=None;storage.init(self.tmp.name+'/qa.db');account_import._staged.clear()
  self.client=TestClient(TestServer(server.build_app()));await self.client.start_server()
 async def asyncTearDown(self):
  await self.client.close();storage._local.conn.close();storage._local.conn=self.oldconn;storage._db_path=self.oldpath;self.tmp.cleanup();account_import._context_cache=None
 async def preview(self):
  res=await self.client.post('/api/account-profile/preview?service=spotify',data=json.dumps({'favorites':[{'track':'Song','artist':'A','email':'PRIVATE'}]}).encode(),headers={'X-File-Name':'library.json'});self.assertEqual(res.status,200);return await res.json()
 async def test_preview_apply_get(self):
  data=await self.preview();self.assertEqual(data['counts']['favorites'],1)
  res=await self.client.post('/api/account-profile/apply',json={'token':data['token'],'selected':['favorites']});self.assertEqual(res.status,200)
  res=await self.client.get('/api/account-profile');out=await res.json();self.assertEqual(out['profiles'][0]['counts']['favorites'],1);self.assertNotIn('PRIVATE',json.dumps(out));self.assertNotIn('Song',json.dumps(out))
 async def test_expired_or_unknown_token(self):
  res=await self.client.post('/api/account-profile/apply',json={'token':'bogus','selected':['history']});self.assertEqual(res.status,400)
 async def test_cross_origin_blocked(self):
  res=await self.client.post('/api/account-profile/preview',data=b'{}',headers={'Origin':'https://evil.example'});self.assertEqual(res.status,403)
 async def test_bad_data_fails_cleanly(self):
  for value in [b'{oops',b'PKbad',b'\xff']:
   res=await self.client.post('/api/account-profile/preview',data=value);self.assertEqual(res.status,400)
 async def test_invalid_selection(self):
  data=await self.preview()
  for selected in [[],{},['passwords'],[{}]]:
   res=await self.client.post('/api/account-profile/apply',json={'token':data['token'],'selected':selected});self.assertEqual(res.status,400)
 async def test_delete_does_not_touch_local(self):
  data=await self.preview();await self.client.post('/api/account-profile/apply',json={'token':data['token'],'selected':['favorites']})
  playlist=storage.create_playlist('Local',[{'id':'yt:a','title':'A','artist':'B'}]);res=await self.client.delete('/api/account-profile/spotify');self.assertEqual(res.status,200);self.assertEqual(len(storage.playlist_tracks(playlist['id'])),1)
 async def test_matching_uses_real_import_pipeline(self):
  async def match(item,sources):return {**item,'match':{'id':'yt:test','title':item['title'],'artist':item['artist'],'source':'youtube'},'score':1,'state':'good'}
  data=await self.preview();await self.client.post('/api/account-profile/apply',json={'token':data['token'],'selected':['favorites']});storage.save_settings({'sources':['youtube']})
  with patch.object(convert.plugins,'enabled_sources',return_value=['youtube']),patch.object(convert,'match_one',side_effect=match):
   res=await self.client.post('/api/account-profile/spotify/match',json={});self.assertEqual(res.status,200,await res.text());job=await res.json();await convert.job(job['id'])['task'];self.assertEqual(convert.job(job['id'])['stage'],'ready')
 async def test_profile_change_replaces_obsolete_refresh(self):
  started=asyncio.Event();cancelled=asyncio.Event()
  async def obsolete():
   started.set()
   try:await asyncio.Event().wait()
   finally:cancelled.set()
  task=asyncio.create_task(obsolete());await started.wait();self.client.server.app['recommend_refresh33']=task;self.client.server.app['recommend_scope50']='obsolete'
  with patch.object(server.recommend,'build_rows',AsyncMock(return_value=[])),patch.object(server.recommend,'cached_rows',return_value=None),patch.object(server.recommend,'_scope',return_value='current'):
   res=await self.client.get('/api/recommend?rows=2&poll=1');self.assertEqual(res.status,200);self.assertTrue(cancelled.is_set());self.assertIsNot(self.client.server.app['recommend_refresh33'],task)
 async def test_file_limit(self):
  res=await self.client.post('/api/account-profile/preview',data=b'x'*(8*1024*1024+1));self.assertEqual(res.status,400)
if __name__=='__main__':unittest.main()
