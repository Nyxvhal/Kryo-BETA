"""Deterministic resolver races, subprocess cleanup and quality preservation."""
import asyncio,json,unittest
from unittest.mock import patch,AsyncMock
from kryonyx import ytdlp_bin as y
GOOD=json.dumps({'url':'https://example.test/audio','ext':'m4a','acodec':'aac','vcodec':'none','abr':256})
class ResolverTests(unittest.IsolatedAsyncioTestCase):
 async def test_fast_plain_uses_no_alternates(self):
  alt=AsyncMock(return_value=GOOD)
  with patch.object(y,'run_plain',AsyncMock(return_value=GOOD)),patch.object(y,'run',alt):
   result=await y._fast_audio_link([], [['a']], 'url')
  self.assertEqual(result[0],GOOD);alt.assert_not_awaited()
 async def test_slow_plain_is_cancelled_and_reaped(self):
  cancelled=[]
  async def slow(*a,**k):
   try:await asyncio.sleep(10)
   finally:cancelled.append(True)
  with patch.object(y,'_PLAIN_HEDGE_SECONDS',.01),patch.object(y,'run_plain',slow),patch.object(y,'run',AsyncMock(return_value=GOOD)):
   result=await asyncio.wait_for(y._fast_audio_link([], [['a']], 'url'),.5)
  self.assertEqual(result[0],GOOD);self.assertEqual(cancelled,[True])
 async def test_invalid_alternate_does_not_hide_next_valid(self):
  async def run(args,**kw):return '{}' if 'bad' in args else GOOD
  with patch.object(y,'run',run):
   result=await y._fast_audio_link([], [['bad'],['good']], 'url',plain=False)
  self.assertEqual(result[0],GOOD)
 async def test_invalid_plain_uses_alternates(self):
  with patch.object(y,'run_plain',AsyncMock(return_value='{}')),patch.object(y,'run',AsyncMock(return_value=GOOD)):
   result=await y._fast_audio_link([], [['good']], 'url')
  self.assertEqual(result[0],GOOD)
 async def test_alternate_concurrency_is_bounded(self):
  active=0;peak=0
  async def run(*a,**k):
   nonlocal active,peak
   active+=1;peak=max(peak,active)
   try:await asyncio.sleep(.05);raise RuntimeError('fail')
   finally:active-=1
  with patch.object(y,'_STAGGER',.005),patch.object(y,'run',run):
   result=await y._first_success([],[[str(i)] for i in range(7)],'url')
  self.assertEqual(result[0],'');self.assertEqual(active,0);self.assertLessEqual(peak,2)
 async def test_cancel_cleans_both_branches(self):
  active=[]
  async def run(*a,**k):
   active.append(1)
   try:await asyncio.sleep(10)
   finally:active.pop()
  with patch.object(y,'_PLAIN_HEDGE_SECONDS',.005),patch.object(y,'run_plain',run),patch.object(y,'run',run):
   task=asyncio.create_task(y._fast_audio_link([], [['a']], 'url'));await asyncio.sleep(.03);task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
  self.assertEqual(active,[])
 async def test_resolver_retains_user_quality_selector(self):
  from kryonyx import audio_quality
  with patch.object(y,'ready',return_value=True),patch.object(audio_quality,'format_selector',return_value='quality-exact'),patch.object(y,'_fast_audio_link',AsyncMock(return_value=(GOOD,None,False))) as f:
   result=await y.stream('test')
  self.assertEqual(f.call_args.args[0][1],'quality-exact');self.assertEqual(result['bitrate'],256)
 async def test_native_process_reaped_on_cancel_and_timeout(self):
  for runner in (y.run,y.run_plain):
   for cancel in (True,False):
    killed=[]
    class Process:
     returncode=None
     async def communicate(self):
      if not killed:await asyncio.sleep(20)
      return b'',b''
     def kill(self):killed.append(True);self.returncode=-9
    with patch.object(y,'path',return_value='binary'),patch.object(y.asyncio,'create_subprocess_exec',AsyncMock(return_value=Process())):
     task=asyncio.create_task(runner([],timeout=.01 if not cancel else 20))
     if cancel:await asyncio.sleep(.005);task.cancel()
     with self.assertRaises(asyncio.CancelledError if cancel else RuntimeError):await task
    self.assertEqual(killed,[True])
