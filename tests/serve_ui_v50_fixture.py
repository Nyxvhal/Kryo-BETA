"""Real v50 profile/SQLite/recommendation engine; deterministic demo catalogs, no accounts."""
import asyncio,hashlib,runpy,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
base=runpy.run_path(str(ROOT/'tests/serve_ui_v12_fixture.py'))
from aiohttp import web
from kryonyx import server,providers,storage,recommend,convert,plugins
STATE=tempfile.TemporaryDirectory(prefix='kryonyx50-qa-');storage._local.conn=None;storage.init(STATE.name+'/qa.db');storage.save_settings({'sources':['youtube']});recommend._rows_file=lambda:STATE.name+'/home.json'
ART=['kryonyx-vibe-08-winter-aurora.png','kryonyx-vibe-06-autumn-dusk.png','kryonyx-vibe-13-retrowave.png','kryonyx-vibe-12-vaporwave.png']
async def search(query,limit=48,**kwargs):
 await asyncio.sleep(.015);key=hashlib.sha256(query.encode()).hexdigest()[:8]
 names=['Northern Lights','Evening Walk','After Hours','Quiet City','New Horizons','Night Drive']
 artists=['Nightfall','Velvet Coast','Echo Studio','Northern Line','Nightfall','Demo Ensemble']
 return {'tracks':[{'id':f'yt:{key}-{i}','title':names[i%6]+f' · {i+1}', 'artist':artists[i%6],'source':'youtube','duration':180,'thumbnail':'/img/avatars/'+ART[i%4]} for i in range(min(limit,36))]}
async def related(id,artist='',title='',limit=48,**kw):return (await search(artist+' '+title,limit,**kw))['tracks']
async def collections(*a,**k):return {'albums':[],'playlists':[]}
async def match(item,sources):
 await asyncio.sleep(.015)
 return {**item,'match':{**item,'id':'yt:matched-'+hashlib.sha256((item['title']+item.get('artist','')).encode()).hexdigest()[:12],'source':'youtube','thumbnail':'/img/avatars/'+ART[0]},'state':'good','score':1}
providers.search=search;providers.related=related;providers.search_collections=collections;convert.match_one=match;plugins.enabled_sources=lambda:['youtube'];plugins.enabled=lambda pid:True
async def _no_catalog70(*a,**k):return []
recommend._curated=_no_catalog70;recommend._starter_playlists=_no_catalog70;recommend._starter_albums=_no_catalog70
@web.middleware
async def fixture(request,handler):
 if request.path.startswith(('/api/history','/api/account-profile','/api/recommend','/api/mix','/api/radio','/api/settings','/api/playlists','/api/convert','/api/transfer/')):return await handler(request)
 return await base['fixture'](request,handler)
if __name__=='__main__':
 app=server.build_app();app.middlewares.insert(0,fixture);web.run_app(app,host='127.0.0.1',port=8782,print=None)
