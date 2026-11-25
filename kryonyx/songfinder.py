"""Text/lyric candidate search and opt-in acoustic fingerprint recognition.
Only a short fingerprint leaves the device; uploads are temporary, never indexed.
The public recognition endpoint is unofficial and can be unavailable.
"""
from __future__ import annotations
import asyncio, math, re, subprocess, time, uuid
from pathlib import Path
from difflib import SequenceMatcher
from . import providers, clipcache

MAX_UPLOAD=100*1024*1024
EXTENSIONS={'.mp3','.wav','.flac','.m4a','.aac','.ogg','.opus','.mp4','.mkv','.webm','.mov'}
_slots=asyncio.Semaphore(2)
_STOP=set('песня трек музыка найди найти похожая похожий похожее где поет поёт про это the song music find track sounds like and with of a is в и на из как'.split())

def tokens(text):return re.findall(r'[\w]+',str(text).casefold(),re.UNICODE)
def queries(text):
    text=re.sub(r'\s+',' ',str(text)).strip()[:600]
    short=' '.join(t for t in tokens(text) if t not in _STOP)[:180]
    return list(dict.fromkeys(q for q in [text,short] if q))

def rank(tracks, query, identity=None, limit=20):
    target=identity or {};q=set(tokens(' '.join([target.get('artist',''),target.get('title','')]) or query))-_STOP
    rows=[];seen=set()
    for i,t in enumerate(tracks):
        if not isinstance(t,dict) or not t.get('id') or not t.get('title'):continue
        key=(str(t.get('artist','')).casefold(),str(t['title']).casefold(),t.get('duration'))
        if t['id'] in seen or key in seen:continue
        seen.update((t['id'],key));have=set(tokens(str(t.get('artist',''))+' '+t['title']))
        overlap=len(q&have)/max(1,len(q));fuzzy=SequenceMatcher(None,' '.join(sorted(q)),' '.join(sorted(have))).ratio()
        value=overlap*4+fuzzy+1/(i+5)
        if target and str(t.get('title','')).casefold()==target.get('title','').casefold():value+=3
        rows.append((value,t))
    rows.sort(key=lambda p:-p[0])
    return [{**t,'match_rank':i+1} for i,(_,t) in enumerate(rows[:limit])]

async def candidates(query,identity=None):
    pieces=queries(query)
    if identity:pieces=list(dict.fromkeys([' '.join([identity.get('artist',''),identity.get('title','')]).strip(),identity.get('title',''),*pieces]))[:3]
    from .recommend import _user_sources
    sources=_user_sources()
    async def search(q):
        try:
            result=await asyncio.wait_for(providers.search(q,limit=60,sources=sources,with_collections=False),25)
            return result.get('tracks',[])
        except Exception:return None
    found=await asyncio.gather(*(search(q) for q in pieces if q))
    if found and all(chunk is None for chunk in found):
        raise ValueError('Music catalogues are unavailable. Check the connection and selected sources.')
    return rank([t for chunk in found if chunk for t in chunk],query,identity)

def extract_sample(path:Path,output:Path,offset:float):
    exe=clipcache.ffmpeg_exe()
    if not exe:raise ValueError('FFmpeg is unavailable; reinstall the player with bundled media tools')
    command=[exe,'-nostdin','-hide_banner','-loglevel','error','-protocol_whitelist','file,pipe','-ss',str(offset),'-i',str(path),'-t','20','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','-y',str(output)]
    try:result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:raise ValueError('The media sample took too long to decode') from exc
    if result.returncode or not output.is_file() or output.stat().st_size<32000:
        raise ValueError('Could not read audio at this position. Choose another file or time offset.')

async def recognize(path,session):
    try:from shazamio_core import Recognizer
    except ImportError as exc:raise ValueError('The acoustic recognition module is missing from this build') from exc
    try:signature=await asyncio.wait_for(Recognizer(segment_duration_seconds=10).recognize_path(value=str(path)),20)
    except (RuntimeError,ValueError) as exc:raise ValueError('Could not create a fingerprint. Try an excerpt with clearly audible music.') from exc
    data={'timezone':'UTC','signature':{'uri':signature.signature.uri,'samplems':signature.signature.samples},'timestamp':signature.timestamp,'context':{},'geolocation':{}}
    url=f'https://amp.shazam.com/discovery/v5/en-US/GB/iphone/-/tag/{str(uuid.uuid4()).upper()}/{str(uuid.uuid4()).upper()}?sync=true&webv3=true&sampling=true&shazamapiversion=v3&sharehub=true&hubv5minorversion=v5.1&hidelb=true&video=v3'
    import aiohttp
    async with session.post(url,json=data,headers={'User-Agent':'Shazam/14.1.0','X-Shazam-Platform':'IPHONE','X-Shazam-AppVersion':'14.1.0'},timeout=aiohttp.ClientTimeout(total=25)) as response:
        if response.status!=200:raise ValueError('The recognition service is unavailable. Try again later or search by description.')
        result=await response.json(content_type=None)
    if not isinstance(result,dict):raise ValueError('Invalid response from the recognition service')
    track=result.get('track') or {}
    if not isinstance(track,dict):raise ValueError('Invalid track response from the recognition service')
    if not track.get('title'):return None
    return {'title':str(track['title'])[:300],'artist':str(track.get('subtitle') or '')[:200],'source':'Shazam acoustic fingerprint','url':track.get('url')}
