"""Local visual QA fixtures only. Not a production server or a real catalogue.
Run: python tests/serve_ui_v6_fixture.py (127.0.0.1:8769).
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
   elif p=='/api/health':data={'ok':True,'sources':[],'stats':{}}
   elif p=='/api/youtube/cookies':data={'present':False,'signed_in':False,'browsers':[]}
   return self.json(data)
  if u.path=='/':
   content=(WEB/'index.html').read_text();inject='''<script>addEventListener('DOMContentLoaded',()=>{const timer=setInterval(()=>{if(!document.body.classList.contains('ui-v6'))return;clearInterval(timer);const state=new URLSearchParams(location.search).get('qa');if(state==='overview'||state==='sound'){Workspace.openSettings();if(state==='sound'){App.openPane('sound');document.querySelector('[data-ui-eq="lounge"]').click();}}$('toast').classList.remove('on');document.activeElement.blur();},50)});</script>'''
   body=content.replace('</body>',inject+'</body>').encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  return super().do_GET()
 def do_POST(self):
  self.rfile.read(int(self.headers.get('Content-Length',0)));self.json({'ok':True})
 do_PUT=do_POST
 do_DELETE=do_POST
if __name__=='__main__':
 print('UI_V6_QA_READY: http://127.0.0.1:8769 (fixtures only)',flush=True)
 ThreadingHTTPServer(('127.0.0.1',8769),Handler).serve_forever()
