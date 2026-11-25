"""UI v7 local visual QA fixtures only. Not a production server or a real catalogue.
Run: python tests/serve_ui_v7_fixture.py (127.0.0.1:8769).
Use ?qa=overview, ?qa=sound, ?theme=daylight6, or ?empty=1.
"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'kryonyx/web'
TRACKS=[dict(id=f'qa:{i}',title=title,artist='Демо-библиотека',source='local',duration=180,thumbnail='/img/avatars/'+img) for i,(title,img) in enumerate([
 ('Свет внутри','kryonyx-vibe-08-winter-aurora.png'),('Тёплый вечер','kryonyx-vibe-06-autumn-dusk.png'),('На своей волне','kryonyx-vibe-13-retrowave.png'),('Медленный город','kryonyx-vibe-12-vaporwave.png')])]
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**k):super().__init__(*a,directory=str(WEB),**k)
 def log_message(self,*args):pass
 def json(self,data):
  body=json.dumps(data,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  u=urlparse(self.path);q=parse_qs(urlparse(self.headers.get('Referer','')).query);theme=q.get('theme',['studio6'])[0];empty=q.get('empty',['0'])[0]=='1'
  if u.path.startswith('/api/'):
   p=u.path;data={'ok':True,'items':[]}
   if p=='/api/settings':data=dict(lang='ru',settingsRev=8,theme=theme,accent='#6246C4' if theme=='daylight6' else '#A995FF',accent2='#267F75' if theme=='daylight6' else '#70C9BC',bg='#F7F8FA' if theme=='daylight6' else '#111216',flat=True,light=theme=='daylight6',noAnim=True,workspace={'compactPlayer':True})
   elif p=='/api/state':data={'value':None}
   elif p=='/api/likes':data={'items':[],'ids':[]}
   elif p=='/api/recommend':data={'rows':[] if empty else [{'kind':'tracks','title':'Демо · вечерняя подборка','items':TRACKS}]}
   elif p=='/api/discovery':data={'rows':[]}
   elif p=='/api/history':data={'items':[] if empty else TRACKS}
   elif p=='/api/playlists':data={'items':[] if empty else [dict(id=i+1,name=name,count=4-i,cover=TRACKS[i]['thumbnail']) for i,name in enumerate(['Демо · После полуночи','Демо · Для прогулки','Демо · Новый ритм'])]}
   elif p.startswith('/api/playlists/') and p.endswith('/tracks'):data={'items':TRACKS}
   elif p=='/api/search':data={'tracks':TRACKS,'has_more':False}
   elif p=='/api/search/extra':data={'authors':[],'albums':[],'playlists':[]}
   elif p=='/api/listen-counts':data={'counts':{t['id']:0 for t in TRACKS}}
   elif p=='/api/health':data={'ok':True,'sources':[],'stats':{}}
   elif p=='/api/youtube/cookies':data={'present':False,'signed_in':False,'browsers':[]}
   return self.json(data)
  if u.path=='/':
   content=(WEB/'index.html').read_text();inject='''<script>addEventListener('DOMContentLoaded',()=>{const timer=setInterval(()=>{if(!document.body.classList.contains('ui-v7'))return;clearInterval(timer);const state=new URLSearchParams(location.search).get('qa');if(state==='overview'||state==='sound'||state==='favorites'){Workspace.openSettings();if(state==='sound'){App.openPane('sound');document.querySelector('[data-ui-eq="lounge"]').click();}if(state==='favorites'){S.ui7={favorites:['sound:sVolume','look:noAnim','look:sRadius']};InterfaceV7.paintFavorites();InterfaceV7.openSettingPane('favorites7');}}if(state==='library')App.go('lib');if(state==='search')App.search('Демо');if(state==='queue'||state==='now'){Player.queue=[{"id": "qa:0", "title": "Свет внутри", "artist": "Демо-библиотека", "source": "local", "duration": 180, "thumbnail": "/img/avatars/kryonyx-vibe-08-winter-aurora.png"}, {"id": "qa:1", "title": "Тёплый вечер", "artist": "Демо-библиотека", "source": "local", "duration": 180, "thumbnail": "/img/avatars/kryonyx-vibe-06-autumn-dusk.png"}, {"id": "qa:2", "title": "На своей волне", "artist": "Демо-библиотека", "source": "local", "duration": 180, "thumbnail": "/img/avatars/kryonyx-vibe-13-retrowave.png"}, {"id": "qa:3", "title": "Медленный город", "artist": "Демо-библиотека", "source": "local", "duration": 180, "thumbnail": "/img/avatars/kryonyx-vibe-12-vaporwave.png"}];Player.index=0;Player.current=Player.queue[0];Player.staged=true;Player.paintTrack();Player.paintTime();if(state==='queue')Workspace.openQueue();else App.openNow();}if(state==='sleep'){InterfaceV7.openSleep();InterfaceV7.setSleep(30);}setTimeout(()=>{$('toast').classList.remove('on');document.activeElement.blur();},250);},50)});</script>'''
   body=content.replace('</body>',inject+'</body>').encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  return super().do_GET()
 def do_POST(self):
  self.rfile.read(int(self.headers.get('Content-Length',0)));self.json({'ok':True})
 do_PUT=do_POST
 do_DELETE=do_POST
if __name__=='__main__':
 print('UI_V7_QA_READY: http://127.0.0.1:8769 (fixtures only)',flush=True)
 ThreadingHTTPServer(('127.0.0.1',8769),Handler).serve_forever()
