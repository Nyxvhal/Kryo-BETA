import asyncio,json,tempfile
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from kryonyx import server,audiovault
async def run():
 out={'id':'yt:dQw4w9WgXcQ','scope':'real Kryo resolver, HTTP range, stream API and temporary cache; no resolver substitution or credentials'}
 with tempfile.TemporaryDirectory(prefix='kryo-live-') as tmp,patch.object(audiovault,'cache_dir',return_value=tmp):
  client=TestClient(TestServer(server.build_app()));await client.start_server()
  try:
   async def sample():
    r=await client.get('/api/stream?id=yt:dQw4w9WgXcQ',headers={'Range':'bytes=0-65535'});b=await r.read();return {'status':r.status,'bytes':len(b),'content_type':r.headers.get('Content-Type'),'range':r.headers.get('Content-Range')}
   r=await asyncio.wait_for(asyncio.gather(sample(),sample(),client.get('/api/cache/audio')),75)
   stats=await r[2].json();out.update(samples=r[:2],stats_status=r[2].status,cache_tracks=stats.get('tracks'))
  except Exception as e:out['error']=type(e).__name__+': '+str(e)[:240]
  finally:await client.close()
 print(json.dumps(out,ensure_ascii=False,indent=2),flush=True)
asyncio.run(run())
