"""Run v43 regression suites. UI requires an isolated local server on port 8779.
Use --browser for UI, --live for explicit external TikTok verification.
Do not point tests at a normal user profile: UI fixtures change settings/history.
"""
from pathlib import Path
import argparse,json,subprocess,sys,time
r=Path(__file__).resolve().parents[1];out=r/'verification/repair-v43'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--browser',action='store_true');p.add_argument('--live',action='store_true');a=p.parse_args();out.mkdir(parents=True,exist_ok=True)
suites=[('python',[sys.executable,'-m','unittest','discover','-s','tests'])]
suites += [(f.stem,['node',str(f.relative_to(r))]) for f in sorted((r/'tests').glob('test_*.cjs'))]
if a.browser:
 for f in ['browser_repair_v43.cjs','browser_audio_reactivity_v43.cjs','browser_scenes_v43.cjs','browser_scale_v41.cjs','browser_loading_v40.cjs','browser_performance_v43.cjs','browser_tiktok_v43.cjs']:
  suites.append((Path(f).stem,['node','tests/'+f]))
if a.live:suites.append(('tiktok-live',['node','tests/browser_tiktok_live_v43.cjs']))
results=[]
for name,cmd in suites:
 start=time.monotonic()
 try:
  res=subprocess.run(cmd,cwd=r,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=300)
  (out/(name+'-runner.log')).write_bytes(res.stdout);exitcode=res.returncode
 except subprocess.TimeoutExpired as e:
  (out/(name+'-runner.log')).write_bytes(e.stdout or b'');exitcode=124
 results.append({'suite':name,'exit':exitcode,'seconds':round(time.monotonic()-start,2)});print(name,exitcode,flush=True)
(out/'regression-runner.json').write_text(json.dumps(results,indent=2));raise SystemExit(any(x['exit'] for x in results))
