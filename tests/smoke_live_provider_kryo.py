import asyncio,json
from kryonyx import ytmusic,providers
async def main():
 out={'provider':'YouTube Music / yt-dlp','query':'Rick Astley Never Gonna Give You Up','scope':'public catalog and provider resolver, no credentials'}
 try:
  rows=await asyncio.wait_for(ytmusic.search(out['query'],10),25);out['results']=len(rows);out['sample']=[{k:r.get(k) for k in ('id','title','artist','duration')} for r in rows[:3]]
  if rows:
   try:
    media=await asyncio.wait_for(providers.resolve(rows[0]['id']),40);out['resolver_ok']=bool(media.get('url'));out['resolver_fields']=[k for k in media if k!='url']
   except Exception as e:out['resolver_error']=type(e).__name__+': '+str(e)[:220]
 except Exception as e:out['search_error']=type(e).__name__+': '+str(e)[:220]
 print(json.dumps(out,ensure_ascii=False,indent=2),flush=True)
asyncio.run(main())
