import asyncio, json, aiohttp
from kryonyx import lyric_translate, server
async def main():
 results={}
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=6)) as session:
  async def translate():
   try:
    value=await asyncio.wait_for(lyric_translate._request(session,'Hello world','ru'),8)
    return {'status':'ok','nonempty':bool(value.strip()),'differs_from_source':value.strip().lower()!='hello world'}
   except Exception as e:return {'status':'failed','error':type(e).__name__,'detail':str(e)[:160]}
  async def lyrics():
   try:
    async with session.get('https://lrclib.net/api/search',params={'track_name':'Beauty And A Beat','artist_name':'Justin Bieber'}) as response:
     if response.status!=200:return {'status':'http_error','http':response.status}
     data=await response.json(content_type=None);items=[x for x in data if isinstance(x,dict)] if isinstance(data,list) else []
     scored=sorted([(server._lyrics_score(x,'Beauty And A Beat','Justin Bieber',227),x) for x in items],key=lambda t:t[0],reverse=True)
     picked=scored[0] if scored and scored[0][0]>-1000 else None
     return {'status':'ok','candidates':len(items),'accepted':bool(picked),'artist':picked[1].get('artistName') if picked else None,'title':picked[1].get('trackName') if picked else None}
   except Exception as e:return {'status':'failed','error':type(e).__name__,'detail':str(e)[:160]}
  results['translation'],results['lrclib']=await asyncio.gather(translate(),lyrics())
 print(json.dumps(results,ensure_ascii=False,indent=2))
asyncio.run(main())
