from pathlib import Path
import subprocess,json,time,urllib.request
r=Path(__file__).resolve().parents[1];out=r/'verification/repair-v38'
for kind,source,key in [('javascript','javascript-regression.json','file'),('browser','browser-regression.json','file')]:
 rows=[]
 for x in json.loads((r/'verification/repair-v37'/source).read_text()):
  file=x[key];t=time.monotonic()
  if kind=='browser':
   data=json.dumps({'uiScale':100,'panelOpacity33':75,'studio':{'searchLayout':'list','cards':180},'playerControls':True,'albumFlowRev23':True,'albumReferenceRev24':True,'repair33':True,'settingsRev':8}).encode()
   urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8779/api/settings',data=data,method='PUT',headers={'Content-Type':'application/json'})).read()
  try:
   p=subprocess.run(['node',file],cwd=r,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120);code=p.returncode;log=p.stdout
  except subprocess.TimeoutExpired as e:code=124;log=(e.stdout or b'').decode() if isinstance(e.stdout,bytes) else e.stdout or ''
  (out/(Path(file).name+'.log')).write_text(log);row={'file':file,'exit':code,'seconds':round(time.monotonic()-t,1),'checks':sum(l.startswith('PASS') for l in log.splitlines())};rows.append(row);print(kind,row,flush=True)
 (out/(kind+'-regression.json')).write_text(json.dumps(rows,indent=2))
