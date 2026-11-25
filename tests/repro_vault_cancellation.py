import asyncio,threading
from unittest.mock import patch
from aiohttp import web
from kryonyx import audiovault as v
entered=threading.Event();release=threading.Event();closed=threading.Event();used_closed=threading.Event()
class Blob:
 def __enter__(self):return self
 def __exit__(self,*a):closed.set()
 def seek(self,n):pass
 def read(self,n):
  entered.set();release.wait(4)
  if closed.is_set():used_closed.set()
  return b'x'
class Result:
 def fetchone(self):return (1,'audio/wav',1)
class Conn:
 def execute(self,*a):return Result()
 def blobopen(self,*a,**kw):return Blob()
 def close(self):pass
class Response:
 def __init__(self,**kw):pass
 async def prepare(self,r):pass
 async def write(self,c):pass
 async def write_eof(self):pass
class Request:headers={};method='GET'
async def main():
 with patch.object(v,'connect',return_value=Conn()),patch.object(web,'StreamResponse',Response):
  task=asyncio.create_task(v.serve(Request(),'vault:test'))
  assert await asyncio.to_thread(entered.wait,2)
  task.cancel();await asyncio.sleep(.05);print('closed_while_worker_active=',closed.is_set(),flush=True);release.set()
  try:await task
  except asyncio.CancelledError:pass
  await asyncio.sleep(.1);print('worker_observed_closed=',used_closed.is_set(),flush=True)
asyncio.run(main())
