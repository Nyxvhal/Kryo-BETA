"""Local UI v8 verification only. Demo metadata; real stream/vault/avatar APIs.
No real accounts, catalog results, or private user data. Port 18779.
"""
import asyncio,io,json,math,sys,tempfile,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from kryonyx import server,audiovault,avatars,avatarshop
ROOT=Path(__file__).resolve().parents[1]
TMP=tempfile.TemporaryDirectory(prefix='kryonyx-ui9-qa-')
audiovault.cache_dir=lambda:TMP.name
avatars.data_dir=lambda:TMP.name
avatarshop.cache_dir=lambda:TMP.name
TRACKS=[dict(id=f'local:qa{i}',title=title,artist='Демо · локальный тест',source='local',duration=10,thumbnail='/img/avatars/'+img) for i,(title,img) in enumerate([('Свет внутри','kryonyx-vibe-08-winter-aurora.png'),('Тёплый вечер','kryonyx-vibe-06-autumn-dusk.png'),('На своей волне','kryonyx-vibe-13-retrowave.png'),('Медленный город','kryonyx-vibe-12-vaporwave.png')])]
b=io.BytesIO()
with wave.open(b,'wb') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(b''.join(int(1600*math.sin(2*math.pi*220*i/22050)).to_bytes(2,'little',signed=True) for i in range(220500)))
TONE=b.getvalue();OFFLINE=False;UPSTREAM=0
SETTINGS=dict(lang='ru',theme='studio6',settingsRev=8,accent='#A995FF',accent2='#70C9BC',bg='#111216',flat=True,noAnim=True,workspace={'compactPlayer':True})
async def media(*args,**kw):return 'different-source-id',{'url':'http://127.0.0.1:18779/fixture-tone.wav','mime':'audio/wav'}
server._media_for=media
@web.middleware
async def fixture(req,handler):
 global SETTINGS,OFFLINE,UPSTREAM
 p=req.path
 if p=='/fixture/control':
  OFFLINE=req.query.get('offline')=='1';return web.json_response({'upstream':UPSTREAM,'offline':OFFLINE})
 if p=='/fixture-tone.wav':
  UPSTREAM+=1
  if OFFLINE:return web.Response(status=503)
  a,b,partial=server.clipstream.ranges(req.headers.get('Range',''),len(TONE));h={'Content-Type':'audio/wav'}
  if partial:h['Content-Range']=f'bytes {a}-{b}/{len(TONE)}'
  return web.Response(body=TONE[a:b+1],headers=h,status=206 if partial else 200)
 if p=='/':
  text=(ROOT/'kryonyx/web/index.html').read_text();inject="""<script>addEventListener('DOMContentLoaded',()=>{let timer=setInterval(()=>{if(!document.body.classList.contains('ui-v8'))return;clearInterval(timer);const state=new URLSearchParams(location.search).get('qa');if(state==='shop')ExperienceV8.openStore();if(state==='signature'){ExperienceV8.openStore().then(()=>{$('ui8Collection').value='signature';$('ui8Collection').dispatchEvent(new Event('change'));});}if(state==='cache'){Workspace.openSettings();App.openPane('sound');}if(state==='recommend'){setTimeout(()=>$('ui8RecTools').scrollIntoView({block:'start'}),700);}setTimeout(()=>{document.activeElement.blur();$('toast').classList.remove('on');},600);},50)});</script>"""
  return web.Response(text=text.replace('</body>',inject+'<script>'+ (ROOT/'tests/ui_v9_capture.js').read_text() +'</script></body>'),content_type='text/html')
 if not p.startswith('/api/') or p.startswith(('/api/stream','/api/prefetch','/api/cache/audio','/api/avatar')):return await handler(req)
 data={'ok':True,'items':[]}
 if p=='/api/settings':
  if req.method=='PUT':SETTINGS=await req.json()
  data=SETTINGS
 elif p=='/api/state':data={'value':None}
 elif p=='/api/likes':data={'items':[],'ids':[]}
 elif p=='/api/recommend':
  rows=int(req.query.get('rows',12));data={'rows':[dict(id=f'demo{i}',kind='tracks',title='Демо · '+['Новая волна','Знакомый ритм','Открытия рядом','Новые имена'][i%4],subtitle='Тестовая подборка · не реальные рекомендации',items=[dict(TRACKS[j%4],id=f'local:demo-{i}-{j}',title=TRACKS[j%4]['title']+' · '+str(j+1),artist='Демо · '+['Ночная волна','Северный ветер','Городской свет','Тихий берег','Новая глава'][j%5]) for j in range(60)]) for i in range(rows)]}
 elif p=='/api/history':data={'items':TRACKS}
 elif p=='/api/playlists':data={'items':[]}
 elif p=='/api/search':data={'tracks':[dict(TRACKS[0],artist='CG5, Ironmouse',artists=[{'name':'CG5','url':'https://music.youtube.com/channel/demoCG5','source':'youtube'},{'name':'Ironmouse','url':'https://music.youtube.com/channel/demoIron','source':'youtube'}]),*TRACKS[1:]],'has_more':False}
 elif p=='/api/searches':data={'items':['Ночная музыка','CG5']}
 elif p=='/api/suggest':
  if req.query.get('q')=='slow':await asyncio.sleep(.7)
  data={'queries':['CG5 new music'],'authors':[{'name':'CG5','source':'youtube','thumbnail':'/img/avatars/kryonyx-vibe-13-retrowave.png','url':'https://music.youtube.com/channel/demoCG5'},{'name':'Ironmouse','source':'youtube','thumbnail':'/img/avatars/kryonyx-vibe-12-vaporwave.png','url':'https://music.youtube.com/channel/demoIron'}],'tracks':TRACKS[:3],'history':[]}
 elif p=='/api/author':data={'name':req.query.get('name'),'picture':'/img/avatars/kryonyx-vibe-12-vaporwave.png','tracks':TRACKS,'partial':False}
 elif p=='/api/lyrics':data={'lines':[],'synced':False}

 elif p=='/api/search/extra':data={'authors':[],'albums':[],'playlists':[]}
 elif p=='/api/health':data={'ok':True,'stats':{},'sources':[]}
 elif p=='/api/youtube/cookies':data={'present':False,'signed_in':False,'browsers':[]}
 return web.json_response(data)
if __name__=='__main__':
 app=server.build_app();app.middlewares.insert(0,fixture);web.run_app(app,host='127.0.0.1',port=18779,print=None)
