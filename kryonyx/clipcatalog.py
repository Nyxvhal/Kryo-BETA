"""Bounded metadata-only video catalog. No stream resolution or prefetch here."""
from __future__ import annotations
import asyncio
import re
import time
from collections import OrderedDict

class Catalog:
    def __init__(self, search, ttl=120, max_entries=24):
        self.search=search;self.ttl=ttl;self.max_entries=max_entries
        self.cache=OrderedDict();self.pending={}
    async def get(self, query, limit, identity):
        key=(query.casefold(),limit,identity);now=time.monotonic()
        hit=self.cache.get(key)
        if hit and now-hit[0]<self.ttl:
            self.cache.move_to_end(key);return hit[1]
        if key in self.pending:return await asyncio.shield(self.pending[key])
        if len(self.pending)>=8:raise RuntimeError('Video search is busy; try again shortly')
        async def fetch():
            try:
                rows=await asyncio.wait_for(self.search(query,limit),18)
                out=[];seen=set()
                for row in rows or []:
                    ident=str(row.get('id') or '').removeprefix('ytvideo:').removeprefix('yt:')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',ident) or ident in seen:continue
                    seen.add(ident)
                    out.append({'id':'ytvideo:'+ident,'title':str(row.get('title') or 'YouTube video')[:500],
                        'artist':str(row.get('artist') or 'YouTube')[:300],
                        'thumbnail':str(row.get('thumbnail') or row.get('cover') or '')[:2048],
                        'duration':row.get('duration') or 0,'views':str(row.get('views') or '')[:80],
                        'source':'youtube','kind':'video'})
                    if len(out)>=limit:break
                self.cache[key]=(time.monotonic(),out)
                while len(self.cache)>self.max_entries:self.cache.popitem(last=False)
                return out
            finally:self.pending.pop(key,None)
        task=asyncio.create_task(fetch());self.pending[key]=task
        return await asyncio.shield(task)
