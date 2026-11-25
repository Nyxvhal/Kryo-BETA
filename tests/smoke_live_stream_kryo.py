import asyncio, json, tempfile
from unittest.mock import patch, AsyncMock
import aiohttp
from aiohttp.test_utils import TestClient,TestServer
from kryonyx import audiovault,server
async def main():
 result={'source':'public CC0 test audio from MDN','resolver':'test URL injected; real HTTP, Kryo stream and SQLite cache'}
 with tempfile.TemporaryDirectory() as temp, patch.object(audiovault,'cache_dir',return_value=temp):
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  try:
   url='https://interactive-examples.mdn.mozilla.net/media/cc0-audio/t-rex-roar.mp3'
   async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
    async with session.get(url) as r:
     expected=await r.read();result['upstream_status']=r.status;result['bytes']=len(expected)
     if r.status!=200 or not expected:raise RuntimeError('test source unavailable')
   resolver=AsyncMock(return_value=('test:live-audio',{'url':url,'mime':'audio/mpeg'}))
   with patch.object(server,'_media_for',resolver):
    responses=await asyncio.wait_for(asyncio.gather(*(client.get('/api/stream?id=test:live-audio&q=any') for _ in range(4))),35)
    bodies=await asyncio.gather(*(r.read() for r in responses));result['parallel_statuses']=[r.status for r in responses];result['same_as_upstream']=all(x==expected for x in bodies)
    for _ in range(100):
     if await asyncio.to_thread(audiovault.find,'test:live-audio'):break
     await asyncio.sleep(.05)
    cached=await client.get('/api/stream?id=test:live-audio&q=any');body=await cached.read();result['cached_status']=cached.status;result['cached_identical']=body==expected
    r=await client.get('/api/stream?id=test:live-audio&q=any',headers={'Range':'bytes=0-99'});partial=await r.read();result['range_status']=r.status;result['range_identical']=partial==expected[:100]
    stat=await client.get('/api/cache/audio');stats=await stat.json();result['stats_status']=stat.status;result['tracks']=stats.get('tracks');result['resolver_calls']=resolver.await_count
  except Exception as e:result['error']=type(e).__name__+': '+str(e)[:200]
  finally:await client.close()
 print(json.dumps(result,ensure_ascii=False,indent=2))
asyncio.run(main())
