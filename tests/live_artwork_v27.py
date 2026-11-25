"""Actual provider artwork through the non-writing export endpoint."""
import asyncio,io,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from aiohttp.test_utils import TestClient,TestServer
from kryonyx import server
async def main():
 app=server.build_app();app.on_startup.clear();client=TestClient(TestServer(app));await client.start_server();at=time.monotonic()
 try:
  response=await client.post('/api/image/export',json={'urls':['https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg','https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg']});data=await response.read();result={'status':response.status,'ok':False,'seconds':round(time.monotonic()-at,2),'scope':'Actual provider network request through application endpoint; no user-file export and no native Windows dialog.'}
  if response.status==200:
   with Image.open(io.BytesIO(data)) as image:result.update(ok=image.format=='PNG',format=image.format,width=image.width,height=image.height,bytes=len(data));image.verify()
  else:result['error']=data.decode(errors='replace')[:300]
  (Path(__file__).resolve().parents[1]/'verification/repair-v27/live-artwork.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 finally:await client.close()
asyncio.run(main())
