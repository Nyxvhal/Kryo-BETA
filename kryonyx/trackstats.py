"""Source counts for exact recording IDs, separate from local history listens."""
from __future__ import annotations
import asyncio, re, time
from . import storage, ytmusic, providers
_cache = {}
_slots = asyncio.Semaphore(3)
_inflight = {}

def source_url(ident):
    if re.fullmatch(r'yt:[A-Za-z0-9_-]{11}',ident):return 'https://www.youtube.com/watch?v='+ident[3:]
    if ident.startswith('sc:'):
        try:
            from urllib.parse import urlparse
            url=providers.b64d(ident[3:]);parsed=urlparse(url)
            if parsed.scheme=='https' and parsed.hostname in ('soundcloud.com','www.soundcloud.com') and not parsed.username and not parsed.password and parsed.port in (None,443):return url
        except Exception:pass
    return None

def valid_id(ident):return source_url(ident) is not None

def persist(ident, value):
    conn=storage._conn()
    with conn:
        for table in ('likes','playlist_tracks','history'):
            for row in conn.execute(f'SELECT rowid AS rid,payload FROM {table} WHERE track_id=?',(ident,)).fetchall():
                import json
                data=json.loads(row['payload']);data.update(value)
                conn.execute(f'UPDATE {table} SET payload=? WHERE rowid=?',(json.dumps(data,ensure_ascii=False),row['rid']))

async def _lookup(ident):
    async with _slots:
        value=None
        try:
            if not ident.startswith('yt:'):raise ValueError('not YouTube')
            data=await asyncio.wait_for(ytmusic._call('get_song',ident[3:]),10)
            raw=(data or {}).get('videoDetails',{}).get('viewCount')
            if raw is not None and str(raw).isdigit():value={'views':int(raw),'stats_kind':'views'}
        except Exception:pass
        # Metadata-only fallback, never playback/search of another recording.
        if value is None:
            try:
                data=await asyncio.wait_for(providers._aextract(source_url(ident),{'quiet':True,'no_warnings':True,'skip_download':True,'ignore_no_formats_error':True,'noplaylist':True,'socket_timeout':6,'retries':0}),12)
                raw=(data or {}).get('playback_count',(data or {}).get('view_count')) if ident.startswith('sc:') else (data or {}).get('view_count')
                if isinstance(raw,(int,float)) and raw>=0:value={'views':int(raw),'stats_kind':'listens' if ident.startswith('sc:') else 'views'}
            except Exception:pass
        if value is not None:await asyncio.to_thread(persist,ident,value)
        _cache[ident]=(time.monotonic()+(3600 if value else 300),value)
        return value

async def lookup(ident):
    if not valid_id(ident):return None
    hit=_cache.get(ident)
    if hit and hit[0]>time.monotonic():return hit[1]
    job=_inflight.get(ident)
    if job is None:
        job=asyncio.create_task(_lookup(ident));_inflight[ident]=job
        job.add_done_callback(lambda _: _inflight.pop(ident,None))
    return await asyncio.shield(job)

async def batch(ids):
    values=await asyncio.gather(*(lookup(i) for i in dict.fromkeys(ids)))
    return {i:v for i,v in zip(dict.fromkeys(ids),values)}
