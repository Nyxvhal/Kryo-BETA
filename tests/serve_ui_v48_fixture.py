"""Isolated v48 fixture. No user accounts or production profile used."""
import runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
base=runpy.run_path(str(ROOT/'tests/serve_ui_v12_fixture.py'))
from aiohttp import web
from kryonyx import server,convert,plugins,storage
import tempfile
STATE=tempfile.TemporaryDirectory(prefix="kryonyx-transfer48-")
storage.init(STATE.name+"/test.db")
async def match(item,sources):
 return {**item,'match':{'id':'qa:'+item['title'],'title':item['title'],'artist':item['artist'],'source':'youtube'},'score':1,'state':'good'}
convert.match_one=match
plugins.enabled_sources=lambda:['youtube']
@web.middleware
async def route48(request,handler):
 if request.path.startswith(('/api/transfer/','/api/convert')):return await handler(request)
 return await base['fixture'](request,handler)
if __name__=='__main__':
 app=server.build_app();app.middlewares.insert(0,route48);web.run_app(app,host='127.0.0.1',port=8780,print=None)
