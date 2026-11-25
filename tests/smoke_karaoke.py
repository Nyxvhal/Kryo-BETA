"""Opt-in REAL model integration smoke test (downloads weights on first run).

python tests/smoke_karaoke.py --python .karaoke-venv/Scripts/python.exe --audio song.wav --language en
Add --reference lyrics.txt to exercise forced alignment instead of recognition.
"""
import argparse,json,subprocess,tempfile,os
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--python',required=True);p.add_argument('--audio',required=True);p.add_argument('--reference');p.add_argument('--language',default='en');p.add_argument('--model',default='tiny');a=p.parse_args()
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
 request={'audio':str(Path(a.audio).resolve()),'reference':Path(a.reference).read_text(encoding='utf-8-sig') if a.reference else '',
          'language':a.language,'model':a.model,'device':'cpu','cache':temp}
 results=[]
 for _ in range(2):
  process=subprocess.run([str(Path(a.python).absolute()),'-m','kryonyx.karaoke_worker'],input=json.dumps(request)+'\n',cwd=root,
          text=True,encoding='utf-8',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=3600,
          env={**os.environ,'PYTHONPATH':str(root),'PYTHONUTF8':'1'})
  events=[json.loads(row) for row in process.stdout.splitlines() if row.startswith('{')]
  assert process.returncode==0,events[-1] if events else process.stderr[-500:]
  done=next(e for e in events if e['stage']=='done');results.append(done)
 doc=json.loads(Path(results[0]['result']).read_text(encoding='utf-8'))
 assert doc['version']==2 and any(line.get('words') for line in doc['lines'])
 assert results[1]['cached'] is True
 print(json.dumps({'engine':doc['alignment']['engine'],'device':doc['alignment']['device'],
   'lines':len(doc['lines']),'words':sum(len(l['words']) for l in doc['lines']),'cache_reused':True},ensure_ascii=False))
