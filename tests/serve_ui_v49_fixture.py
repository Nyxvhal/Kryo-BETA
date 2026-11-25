"""Isolated UI QA. Real parser, jobs, SQLite; demo catalog and matching only."""
import runpy,sys,tempfile,asyncio
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
base=runpy.run_path(str(ROOT/'tests/serve_ui_v12_fixture.py'))
from aiohttp import web
from kryonyx import server,convert,plugins,storage
STATE=tempfile.TemporaryDirectory(prefix='kryonyx49-qa-');storage._local.conn=None;storage.init(STATE.name+'/qa.db')
async def match(item,sources):
 await asyncio.sleep(.03)
 return {**item,'match':{'id':'qa:'+item['title'],'title':item['title'],'artist':item.get('artist',''),'source':'local','duration':item.get('duration') or 180,'thumbnail':'/img/avatars/kryonyx-vibe-08-winter-aurora.png'},'state':'good','score':1}
async def fetch(url):
 return {'type':'playlist','name':'Вечерняя коллекция','service':'spotify','items':[{'title':t,'artist':a,'duration':180} for t,a in [('Northern Lights','Example Artist'),('Evening Walk','Demo Ensemble'),('After Hours','Studio Session')]]}
convert.match_one=match;convert.fetch=fetch;plugins.enabled_sources=lambda:['youtube'];plugins.enabled=lambda pid:True
@web.middleware
async def fixture49(request,handler):
 if request.path.startswith(('/api/transfer/','/api/convert','/api/playlists')):return await handler(request)
 return await base['fixture'](request,handler)
if __name__=='__main__':
 app=server.build_app();app.middlewares.insert(0,fixture49);web.run_app(app,host='127.0.0.1',port=8781,print=None)
