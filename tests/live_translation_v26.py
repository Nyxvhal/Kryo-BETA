import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import aiohttp
from kryonyx import lyric_translate
async def main():
 rows=[];source=['The morning light is warm.','','We walk beside the quiet sea.'];original=list(source)
 async with aiohttp.ClientSession() as session:
  for target in ['en','ru','es','pt','de','fr','it','tr','pl','uk','zh-CN','ja','ko']:
   at=time.monotonic()
   try:
    value=await lyric_translate.translate(source,target,session)
    rows.append({'target':target,'ok':len(value)==3 and value[1]=='' and all(value[i].strip() for i in [0,2]) and source==original,'translations':value,'seconds':round(time.monotonic()-at,2)})
   except Exception as e:rows.append({'target':target,'ok':False,'error':str(e),'seconds':round(time.monotonic()-at,2)})
 result={'source':'Own test sentences, not copyrighted song lyrics. Actual Google Translate endpoint through application backend module, explicit audit request.','rows':rows,'passed':sum(x['ok'] for x in rows),'total':len(rows)}
 (ROOT/'verification/repair-v26/live-translation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'passed':result['passed'],'total':result['total'],'failures':[x for x in rows if not x['ok']]},ensure_ascii=False))
asyncio.run(main())
