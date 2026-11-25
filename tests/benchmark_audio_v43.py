"""Local per-connection-limited Range source; pass the original v42 source ZIP."""
import asyncio,hashlib,importlib.util,json,sys,tempfile,time,zipfile
from pathlib import Path
from unittest.mock import patch
import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
from kryonyx import audiocache as current,audiovault,clipstream
async def main():
 data=bytes(range(256))*(14336);rows=[]
 async def source(req):
  a,b,partial=clipstream.ranges(req.headers.get('Range',''),len(data));h={'Content-Type':'audio/mpeg'}
  if partial:h['Content-Range']=f'bytes {a}-{b}/{len(data)}'
  response=web.StreamResponse(status=206 if partial else 200,headers=h);response.content_length=b-a+1;await response.prepare(req);await asyncio.sleep(.015)
  try:
   for off in range(a,b+1,32768):
    chunk=data[off:min(off+32768,b+1)];await response.write(chunk);await asyncio.sleep(len(chunk)/(2*1024*1024))
   await response.write_eof()
  except (ConnectionResetError,asyncio.CancelledError):pass
  return response
 with tempfile.TemporaryDirectory() as tmp:
  with zipfile.ZipFile(sys.argv[1]) as z:old=z.read('kryonyx-music/kryonyx/audiocache.py')
  path=Path(tmp)/'baseline.py';path.write_bytes(old);spec=importlib.util.spec_from_file_location('kryonyx._baseline43',path);baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
  app=web.Application();app.router.add_get('/audio',source);up=TestServer(app);await up.start_server()
  try:
   with patch.object(audiovault,'cache_dir',return_value=tmp):
    async with aiohttp.ClientSession() as session:
     for version,module in [('v42',baseline),('v43',current)]:
      for mode in ['stream','prefetch']:
       for rep in range(3):
        key=f'{version}-{mode}-{rep}';chunks=[];times=[];start=time.perf_counter();media={'url':str(up.make_url('/audio')),'mime':'audio/mpeg'}
        async def consume(chunk):chunks.append(chunk);times.append(time.perf_counter()-start)
        if mode=='stream':await module.tee(session,key,media,on_chunk=consume)
        else:await module.download(session,key,media)
        elapsed=time.perf_counter()-start;token=audiovault.find(key);stored=audiovault.materialize(token);actual=Path(stored).read_bytes();Path(stored).unlink();assert actual==data
        if mode=='stream':assert b''.join(chunks)==data
        rows.append({'version':version,'mode':mode,'seconds':round(elapsed,3),'first_byte':round(times[0],3) if times else None,'max_delivery_gap':round(max([b-a for a,b in zip(times,times[1:])] or [0]),3),'sha256':hashlib.sha256(actual).hexdigest()})
  finally:await up.close()
 out={'setup':'3.5 MiB, 2 MiB/s per connection, 15 ms request latency, real local HTTP ranges. Not a promise for all Internet sources. Both revisions use current vault storage.','runs':rows}
 Path('verification/repair-v43/audio-benchmark.json').write_text(json.dumps(out,indent=2))
 from statistics import median
 for version in ['v42','v43']:
  for mode in ['stream','prefetch']:
   selected=[x for x in rows if x['version']==version and x['mode']==mode];print(version,mode,'median',median(x['seconds'] for x in selected),'firstbyte',selected[0]['first_byte'])
asyncio.run(main())
