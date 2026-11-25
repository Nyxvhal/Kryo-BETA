"""Account login removal must leave public music metadata independent."""
import unittest,types,sys
from pathlib import Path
from unittest.mock import patch,MagicMock
from aiohttp.test_utils import TestClient,TestServer
from kryonyx import server,ytmusic
ROOT=Path(__file__).resolve().parents[1]
class RemovedAccountTests(unittest.TestCase):
 def test_removed_login_code_and_ui(self):
  self.assertFalse((ROOT/'kryonyx/ytaccount.py').exists())
  self.assertFalse((ROOT/'kryonyx/web/js/ytmusic.js').exists())
  html=(ROOT/'kryonyx/web/index.html').read_text()
  for name in ['id="mYtm"','id="ytmCard"','Sign in with Google','id="ytmIn"','/js/ytmusic.js']:
   self.assertNotIn(name,html)
  self.assertNotIn('ytaccount',(ROOT/'kryonyx/recommend.py').read_text())
 def test_public_client_has_no_account_credentials(self):
  factory=MagicMock();module=types.SimpleNamespace(YTMusic=factory)
  with patch.dict(sys.modules,{'ytmusicapi':module}),patch.object(ytmusic,'_client',None),patch.object(ytmusic,'_tried',False),patch('kryonyx.netproxy.requests_proxies',return_value=None):
   self.assertIs(ytmusic._api(),factory.return_value)
   factory.assert_called_once_with(proxies=None)
class RemovedAccountRoutes(unittest.IsolatedAsyncioTestCase):
 async def test_old_account_routes_are_unavailable(self):
  app=server.build_app();app.on_startup.clear()
  async with TestClient(TestServer(app)) as client:
   for method,path in [('get','account'),('post','login/headers'),('post','login/oauth/start'),('post','login/oauth/finish'),('get','playlists'),('post','sync'),('post','logout')]:
    response=await getattr(client,method)('/api/ytmusic/'+path)
    self.assertIn(response.status,(404,405),(method,path,response.status))
