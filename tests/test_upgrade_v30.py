import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
import unittest
from kryonyx import server
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer30',ROOT/'installer/bootstrap.py');inst=importlib.util.module_from_spec(spec);spec.loader.exec_module(inst)
class InstallerTests(unittest.TestCase):
 def test_legal_documents_available(self):
  info=inst.Installer().info();self.assertEqual(set(info['legal']),{'LICENSE','TERMS.md','PRIVACY.md','THIRD_PARTY_NOTICES.md'});self.assertIn('MIT License',info['legal']['LICENSE'])
 def test_acceptance_required(self):
  self.assertEqual(inst.Installer().install('C:\\Temp',True,False,False)['error'],'acceptance')
 def test_busy_cannot_restart(self):
  api=inst.Installer();api.state['phase']='installing';self.assertEqual(api.install('C:\\Temp',True,False,True)['error'],'busy')
 def test_install_no_shell_and_explicit_tasks(self):
  api=inst.Installer();api.destination='C:\\Kryonyx';
  with patch.object(inst.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
   api._run(False,True);args=run.call_args.args[0];self.assertIn('/TASKS=autostart',args);self.assertIn('/DIR=C:\\Kryonyx',args);self.assertNotIn('shell',run.call_args.kwargs);self.assertEqual(api.state['phase'],'done')
 def test_failed_engine_not_success(self):
  api=inst.Installer()
  with patch.object(inst.subprocess,'run',return_value=SimpleNamespace(returncode=5)):api._run(True,False)
  self.assertEqual(api.status()['phase'],'error');self.assertFalse(api.finish(True))
 def test_during_install_close_is_blocked(self):
  api=inst.Installer();api.state['phase']='installing';self.assertFalse(api.close())
class PrefetchServerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  server._prefetch_task30=None;server._prefetch_id30='';self.started=[];self.cancelled=[]
  async def work(track,*args):
   self.started.append(track)
   try:await asyncio.Event().wait()
   except asyncio.CancelledError:self.cancelled.append(track);raise
  self.patch=patch.object(server,'_prefetch_one30',side_effect=work);self.patch.start();self.cache=patch.object(server.audiocache,'find',return_value=None);self.cache.start()
 async def asyncTearDown(self):
  tasks=list(server._prefetch_tasks30)
  for t in tasks:t.cancel()
  await asyncio.gather(*tasks,return_exceptions=True);self.patch.stop();self.cache.stop()
 async def test_duplicate_request_does_not_spawn(self):
  req=SimpleNamespace(query={'id':'a'});await server.api_prefetch(req);await asyncio.sleep(0);await server.api_prefetch(req);await asyncio.sleep(0);self.assertEqual(self.started,['a'])
 async def test_obsolete_successor_is_cancelled(self):
  await server.api_prefetch(SimpleNamespace(query={'id':'a'}));await asyncio.sleep(0);await server.api_prefetch(SimpleNamespace(query={'id':'b','current':'c'}));await asyncio.sleep(0);self.assertEqual(self.started,['a','b']);self.assertEqual(self.cancelled,['a'])
 async def test_now_playing_warmup_is_not_cancelled(self):
  await server.api_prefetch(SimpleNamespace(query={'id':'a'}));await asyncio.sleep(0);await server.api_prefetch(SimpleNamespace(query={'id':'b','current':'a'}));await asyncio.sleep(0);self.assertEqual(self.started,['a','b']);self.assertEqual(self.cancelled,[])
if __name__=='__main__':unittest.main()
