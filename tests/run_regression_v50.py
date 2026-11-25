"""v50 offline regression. --profile: isolated serve_ui_v50_fixture.py :8782.
--transfer: isolated serve_ui_v49_fixture.py :8781. Never use a real user profile.
No live providers, real accounts or native Windows verification.
"""
import argparse,json,subprocess,sys,time
from pathlib import Path

def main():
 root=Path(__file__).resolve().parents[1];out=root/'verification/repair-v50';out.mkdir(parents=True,exist_ok=True)
 args=argparse.ArgumentParser(description=__doc__);args.add_argument('--profile',action='store_true');args.add_argument('--transfer',action='store_true');opts=args.parse_args()
 jobs=[('python',[sys.executable,'-m','unittest','discover','-s','tests'])]
 jobs += [(p.stem,['node',str(p.relative_to(root))]) for p in sorted((root/'tests').glob('test_*.cjs'))]
 if opts.profile:jobs.append(('browser-personal',['node','tests/browser_personal_v50.cjs']))
 if opts.transfer:
  (root/'verification/repair-v49').mkdir(parents=True,exist_ok=True)
  jobs += [(name,['node','tests/'+name+'.cjs']) for name in ['browser_connections_v49','browser_races_v49']]
 report=[]
 for name,cmd in jobs:
  started=time.monotonic()
  try:
   proc=subprocess.run(cmd,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300);code=proc.returncode;data=proc.stdout
  except subprocess.TimeoutExpired as exc:code=124;data=exc.stdout or b''
  (out/(name+'-runner.log')).write_bytes(data);report.append({'suite':name,'exit':code,'seconds':round(time.monotonic()-started,2)});print(name,code,flush=True)
 (out/'regression-runner.json').write_text(json.dumps(report,indent=2));raise SystemExit(any(r['exit'] for r in report))
if __name__=='__main__':main()
