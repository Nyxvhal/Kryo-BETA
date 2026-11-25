"""Opt-in public network smoke test. Uses a temporary cache, never user data."""
import asyncio,json,tempfile,hashlib
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from kryonyx import server,audiovault

async def run():
 result={'id':'yt:dQw4w9WgXcQ','scope':'live provider resolution and real Kryo streams; temporary cache, no credentials'}
 with tempfile.TemporaryDirectory(prefix='kryo-live-') as temp,patch.object(audiovault,'cache_dir',return_value=temp):
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  try:
   async def whole():
    r=await client.get('/api/stream?id=yt:dQw4w9WgXcQ');b=await r.read();return r.status,b
   x,y=await asyncio.wait_for(asyncio.gather(whole(),whole()),90)
   result.update(statuses=[x[0],y[0]],sizes=[len(x[1]),len(y[1])],identical=x[1]==y[1] and bool(x[1]))
   for _ in range(100):
    if await asyncio.to_thread(audiovault.find,'yt:dQw4w9WgXcQ'):break
    await asyncio.sleep(.1)
   found=bool(await asyncio.to_thread(audiovault.find,'yt:dQw4w9WgXcQ'));result['cache_entry']=found
   r=await client.get('/api/stream?id=yt:dQw4w9WgXcQ',headers={'Range':'bytes=0-65535'});b=await r.read();result['cached_range']={'status':r.status,'bytes':len(b),'matches_first_stream':b==x[1][:65536]}
   r=await client.get('/api/cache/audio');result['stats_status']=r.status;result['stats']=await r.json()
  except Exception as e:result['error']=type(e).__name__+': '+str(e)[:240]
  finally:await client.close()
 print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
 if 'error' in result or result.get('statuses')!=[200,200] or not result.get('identical') or not result.get('cache_entry') or not result.get('cached_range',{}).get('matches_first_stream'):raise SystemExit(1)
asyncio.run(run())
