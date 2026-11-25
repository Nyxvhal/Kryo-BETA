"""Public TikTok video -> fully downloaded local video -> opt-in acoustic fingerprint.
No accounts/cookies, no private-video bypass, no autoplay or permanent media cache.
Catalogue suggestions are NOT acoustic similarity scores or confirmed originals.
"""
from __future__ import annotations
import asyncio, math, re, tempfile, logging, time, uuid, subprocess, json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin
import aiohttp
from . import songfinder, providers
from .wallpaper import PublicResolver, public_url

log = logging.getLogger(__name__)

MAX_BYTES = 100 * 1024 * 1024
MAX_DURATION = 600
HOSTS = {'tiktok.com', 'www.tiktok.com', 'm.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com'}
BAD_URL = 'Use a public HTTPS TikTok video link, including vm.tiktok.com or vt.tiktok.com.'
UNAVAILABLE = 'TikTok video is unavailable or blocked. Upload the saved video instead.'
NETWORK = 'The TikTok video could not be fully downloaded. Try again or upload the saved video.'
GENERIC = re.compile(r'original\s*(sound|audio)|оригинальн\w*\s*(звук|аудио)|оригінальн\w*\s*звук|sonido\s+original|som\s+original|son\s+original|suono\s+originale|originalton|原声|オリジナル楽曲', re.I)


def normalize_url(value: str) -> str:
    if not isinstance(value, str) or len(value)>2048 or any(c.isspace() or ord(c)<32 for c in value.strip()):
        raise ValueError(BAD_URL)
    try:
        u=urlsplit(value.strip());host=(u.hostname or '').lower()
        if u.scheme!='https' or host not in HOSTS or u.username or u.password or u.port not in (None,443):raise ValueError(BAD_URL)
        video=re.fullmatch(r'/@([A-Za-z0-9_.-]{1,80})/video/(\d{10,25})/?',u.path)
        short=re.fullmatch(r'/(?:t/)?([A-Za-z0-9_-]{4,100})/?',u.path)
        if video:return f'https://www.tiktok.com/@{video[1]}/video/{video[2]}'
        if short and (host in {'vm.tiktok.com','vt.tiktok.com'} or u.path.startswith('/t/')):
            return urlunsplit(('https',host,u.path,'',''))
    except (ValueError,TypeError):pass
    raise ValueError(BAD_URL)


async def canonical_url(value: str, session) -> str:
    value=normalize_url(value)
    for _ in range(6):
        if '/video/' in urlsplit(value).path:return value
        async with session.get(value,allow_redirects=False) as response:
            if response.status in (301,302,303,307,308):
                value=normalize_url(urljoin(value,response.headers.get('Location','')))
            else:raise ValueError(UNAVAILABLE)
    raise ValueError('Too many redirects in the TikTok link.')


def metadata(url):
    """Only a canonical TikTok URL reaches the dedicated TikTok extractor."""
    import yt_dlp
    opts={'quiet':True,'no_warnings':True,'skip_download':True,'noplaylist':True,
          'socket_timeout':10,'retries':0,'extractor_retries':0,'cachedir':False,
          'proxy':'','logger':_Quiet()}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:info=ydl.extract_info(url,download=False,ie_key='TikTok')
    except Exception as exc:raise ValueError(UNAVAILABLE) from exc
    if not isinstance(info,dict) or info.get('_type') in ('playlist','multi_video','url','url_transparent'):raise ValueError(UNAVAILABLE)
    duration=info.get('duration')
    if duration is not None:
        try:duration=float(duration)
        except (ValueError,TypeError):raise ValueError(UNAVAILABLE)
        if not math.isfinite(duration) or duration<0 or duration>MAX_DURATION:
            raise ValueError('TikTok videos must be at most 10 minutes long.')
    return info

class _Quiet:
    def debug(self,*a):pass
    def warning(self,*a):pass
    def error(self,*a):pass


def sound_hint(info):
    """Music attribution is a hint; caption, filename and uploader never identify audio."""
    title=info.get('track');artist=info.get('artist')
    if not artist and isinstance(info.get('artists'),list):artist=', '.join(x for x in info['artists'] if isinstance(x,str))
    if not isinstance(title,str) or not title.strip() or GENERIC.search(title):return None
    return {'title':title.strip()[:300],'artist':str(artist or '').strip()[:200],'source':'TikTok sound metadata','verified':False}


def video_formats(info):
    """Whole progressive video+audio files only, never the separate music credit URL."""
    formats=info.get('formats') or ([info] if info.get('url') else [])
    usable=[];seen=set()
    for f in formats:
        if not isinstance(f,dict):continue
        url=f.get('url') or '';proto=str(f.get('protocol') or '')
        if not isinstance(url,str) or not url.startswith('https://') or not public_url(url):continue
        if proto not in ('','http','https') or any(x in urlsplit(url).path.lower() for x in ('.m3u8','.mpd')):continue
        if f.get('vcodec')=='none' or f.get('acodec')=='none':continue
        ext=str(f.get('ext') or '').lower()
        if ext in ('m4a','mp3','aac','opus','ogg','wav','flac'):continue
        size=f.get('filesize') or f.get('filesize_approx') or 0
        try:size=float(size)
        except (TypeError,ValueError):continue
        if not math.isfinite(size) or size<0 or size>MAX_BYTES or url in seen:continue
        seen.add(url);usable.append((size or MAX_BYTES,len(usable),f))
    if not usable:raise ValueError('No supported TikTok video with audio. Upload the video instead.')
    return [f for _,_,f in sorted(usable,key=lambda x:(x[0],x[1]))]


def media_format(info):
    return video_formats(info)[0]


def _download_headers(media):
    # Signed CDN links may require the extractor's UA/referer, but never forward
    # arbitrary cookies, authorization or attacker-supplied header names.
    raw=media.get('http_headers') or {};headers={}
    for key in ('User-Agent','Accept','Accept-Language'):
        value=next((v for k,v in raw.items() if str(k).lower()==key.lower()),None)
        if isinstance(value,str) and len(value)<=1024 and not any(ord(c)<32 for c in value):headers[key]=value
    ref=next((v for k,v in raw.items() if str(k).lower()=='referer'),None)
    if isinstance(ref,str):
        try:
            u=urlsplit(ref)
            if u.scheme=='https' and u.hostname in HOSTS and not u.username and not u.password and not any(ord(c)<32 for c in ref):headers['Referer']=ref
        except ValueError:pass
    return headers


async def download(media, target:Path, session):
    """Commit a COMPLETE local video before decoding can begin. Remove partials."""
    url=media['url'];partial=target.with_name(target.name+'.part');headers=_download_headers(media)
    target.unlink(missing_ok=True)
    try:
        for _ in range(6):
            if not url.startswith('https://') or not public_url(url):raise ValueError(NETWORK)
            async with session.get(url,allow_redirects=False,headers=headers) as response:
                if response.status in (301,302,303,307,308):
                    url=urljoin(url,response.headers.get('Location',''));continue
                if response.status!=200:
                    log.warning('[tiktok] video CDN HTTP %d',response.status)
                    raise ValueError(NETWORK)
                kind=response.headers.get('Content-Type','').lower()
                if 'text/html' in kind or 'application/json' in kind:raise ValueError(NETWORK)
                length=response.content_length
                if length is not None and length>MAX_BYTES:raise ValueError('TikTok download exceeds 100 MB. Upload a shorter excerpt.')
                import aiofiles
                total=0
                async with aiofiles.open(partial,'wb') as handle:
                    async for chunk in response.content.iter_chunked(65536):
                        total+=len(chunk)
                        if total>MAX_BYTES:raise ValueError('TikTok download exceeds 100 MB. Upload a shorter excerpt.')
                        await handle.write(chunk)
                if not total or (length is not None and total!=length):raise ValueError(NETWORK)
                partial.replace(target)
                return total
        raise ValueError('Too many redirects in the TikTok media.')
    finally:
        partial.unlink(missing_ok=True)


class _EmbedState(HTMLParser):
    def __init__(self):super().__init__();self.capture=False;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('id')=='__FRONTITY_CONNECT_STATE__':self.capture=True
    def handle_data(self,text):
        if self.capture:self.parts.append(text)
    def handle_endtag(self,tag):
        if tag=='script':self.capture=False


def _embed_info(text,video_id):
    """Only this exact public video's video.urls. Never musicInfos.playUrl."""
    parser=_EmbedState();parser.feed(text)
    try:state=json.loads(''.join(parser.parts))
    except (ValueError,TypeError):raise ValueError(UNAVAILABLE) from None
    if not isinstance(state,dict) or not isinstance(state.get('source'),dict):raise ValueError(UNAVAILABLE)
    pages=state['source'].get('data') or {}
    if not isinstance(pages,dict):raise ValueError(UNAVAILABLE)
    for page in pages.values():
        if not isinstance(page,dict) or page.get('customErrorCode',0):continue
        data=page.get('videoData') or {}
        if not isinstance(data,dict):continue
        item=data.get('itemInfos') or {}
        if not isinstance(item,dict):continue
        if str(item.get('id') or '')!=video_id:continue
        if item.get('secret') or item.get('forFriend'):raise ValueError(UNAVAILABLE)
        video=item.get('video') or {}
        if not isinstance(video,dict):raise ValueError(UNAVAILABLE)
        meta=video.get('videoMeta') or {}
        if not isinstance(meta,dict):raise ValueError(UNAVAILABLE)
        duration=meta.get('duration')
        if duration is not None:
            try:duration=float(duration)
            except (ValueError,TypeError):raise ValueError(UNAVAILABLE) from None
            if not math.isfinite(duration) or not 0<duration<=MAX_DURATION:raise ValueError('TikTok videos must be at most 10 minutes long.')
        urls=video.get('urls') or []
        if not isinstance(urls,list):raise ValueError(UNAVAILABLE)
        formats=[{'url':u,'format_id':'public_embed','ext':'mp4','acodec':'aac','vcodec':'h264','protocol':'https'} for u in urls if isinstance(u,str)]
        info={'id':video_id,'duration':duration,'formats':formats,'download_route44':'public_tiktok_embed'}
        video_formats(info)  # Every candidate still goes through the public-address guards.
        return info
    raise ValueError(UNAVAILABLE)


async def embed_metadata(canonical,session):
    video_id=urlsplit(normalize_url(canonical)).path.rsplit('/',1)[-1]
    url='https://www.tiktok.com/embed/v2/'+video_id
    for _ in range(4):
        u=urlsplit(url)
        if u.scheme!='https' or u.hostname not in HOSTS or u.username or u.password or u.port not in (None,443):raise ValueError(UNAVAILABLE)
        async with session.get(url,allow_redirects=False) as response:
            if response.status in (301,302,303,307,308):
                url=urljoin(url,response.headers.get('Location',''));continue
            if response.status!=200:raise ValueError(UNAVAILABLE)
            chunks=[];size=0
            async for chunk in response.content.iter_chunked(65536):
                size+=len(chunk)
                if size>2*1024*1024:raise ValueError(UNAVAILABLE)
                chunks.append(chunk)
            return _embed_info(b''.join(chunks).decode('utf-8','replace'),video_id)
    raise ValueError(UNAVAILABLE)


async def _download_video(info, canonical, target, session):
    # Real public embed often serves a different VIDEO CDN than webapp-prime,
    # which can return 403. This is TikTok itself, not a third-party downloader.
    last=None;attempts=0
    for route in ('extractor','embed','refresh'):
        try:
            if route=='embed':info=await embed_metadata(canonical,session)
            elif route=='refresh':info=await asyncio.wait_for(asyncio.to_thread(metadata,canonical),40)
            formats=video_formats(info)
        except (ValueError,aiohttp.ClientError,asyncio.TimeoutError,OSError) as exc:
            last=exc;continue
        for media in formats[:3]:
            if attempts>=5:break
            attempts+=1
            media={**media,'http_headers':{**(info.get('http_headers') or {}),**(media.get('http_headers') or {})}}
            try:
                size=await asyncio.wait_for(download(media,target,session),35)
                return {'complete':True,'kind':'video','bytes':size,'attempts':attempts,
                        'route':info.get('download_route44') or route}
            except (ValueError,aiohttp.ClientError,asyncio.TimeoutError,OSError) as exc:
                last=exc
    raise ValueError(NETWORK) from last


def _verify_video(path):
    from . import clipcache
    exe=clipcache.ffmpeg_exe()
    if not exe:raise ValueError('FFmpeg is unavailable; reinstall the player with bundled media tools')
    command=[exe,'-nostdin','-hide_banner','-loglevel','info','-protocol_whitelist','file,pipe',
             '-i',str(path),'-map','0:v:0','-frames:v','1','-an','-f','null','-']
    try:r=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:raise ValueError('Downloaded file is not a readable video with audio. Upload the saved video.') from exc
    if r.returncode:raise ValueError('Downloaded file is not a readable video with audio. Upload the saved video.')
    match=re.search(rb'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',r.stderr or b'')
    if not match:raise ValueError('Downloaded file is not a readable video with audio. Upload the saved video.')
    hours,minutes,seconds=map(float,match.groups());duration=hours*3600+minutes*60+seconds
    if duration>MAX_DURATION:raise ValueError('TikTok videos must be at most 10 minutes long.')
    return duration


async def _verify(source):
    # Wait for local ffmpeg to close its handles before deleting a Windows temp dir.
    task=asyncio.create_task(asyncio.to_thread(_verify_video,source))
    try:return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:await task
        finally:raise


async def _decode(source,sample,offset):
    # A decoder must release its file handle before TemporaryDirectory cleans up on Windows.
    task=asyncio.create_task(asyncio.to_thread(songfinder.extract_sample,source,sample,offset))
    try:return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:await task
        finally:raise


def _distinct(tracks, excluded=()):
    ids={x['id'] for x in excluded if isinstance(x,dict) and x.get('id')}
    names={(str(x.get('artist','')).casefold(),str(x.get('title','')).casefold()) for x in excluded if isinstance(x,dict)}
    out=[]
    for t in tracks:
        if not isinstance(t,dict) or not t.get('id') or not t.get('title'):continue
        key=(str(t.get('artist','')).casefold(),str(t['title']).casefold())
        if t['id'] in ids or key in names:continue
        ids.add(t['id']);names.add(key);out.append(t)
    return out


async def analyze(url, session, offset=0):
    url=normalize_url(url)
    if isinstance(offset,bool) or not isinstance(offset,(int,float)) or not math.isfinite(offset) or not 0<=offset<=MAX_DURATION:raise ValueError('TikTok sample start must be between 0 and 600 seconds.')
    request_id=uuid.uuid4().hex[:8]
    async def step(name, operation):
        started=time.monotonic()
        log.info('[tiktok:%s] %s started',request_id,name)
        try:
            result=await operation
        except asyncio.CancelledError:
            log.info('[tiktok:%s] %s cancelled',request_id,name)
            raise
        except Exception as exc:
            # No shared URL, signed CDN query, audio, cookies or titles in logs.
            log.warning('[tiktok:%s] %s failed (%s)',request_id,name,type(exc).__name__)
            raise
        log.info('[tiktok:%s] %s completed in %.2fs',request_id,name,time.monotonic()-started)
        return result
    warnings=[];recognition=None;hint=None;items=[];similar=[];catalogue_error=None;sample_count=0
    connector=aiohttp.TCPConnector(resolver=PublicResolver(),use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector,trust_env=False,
        timeout=aiohttp.ClientTimeout(total=45,connect=12),headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.tiktok.com/'}) as remote:
        canonical=await step('resolve_link',canonical_url(url,remote))
        try:info=await step('extract_metadata',asyncio.wait_for(asyncio.to_thread(metadata,canonical),40))
        except (ValueError,aiohttp.ClientError,asyncio.TimeoutError,OSError):
            info=await step('read_public_embed',embed_metadata(canonical,remote))
        hint=sound_hint(info)
        duration=float(info.get('duration') or 0)
        if duration and offset>=duration:raise ValueError('Sample start is outside the TikTok video.')
        with tempfile.TemporaryDirectory(prefix='kryonyx-tiktok-') as tmp:
            source=Path(tmp)/'video.mp4';sample=Path(tmp)/'sample.wav'
            # Never downgrade a failed download to a successful metadata-only result.
            video=await step('download_video',_download_video(info,canonical,source,remote))
            duration=await step('verify_video',_verify(source))
            if offset>=duration:raise ValueError('Sample start is outside the TikTok video.')
            offsets=[offset]
            if duration>offset+25:offsets.append(min(offset+20,max(offset,duration-20)))
            for start in dict.fromkeys(offsets):
                # A decoding failure is not a successful metadata analysis.
                await step('decode_sample',_decode(source,sample,start));sample_count+=1
                try:
                    recognition=await step('fingerprint',songfinder.recognize(sample,session))
                except (ValueError,aiohttp.ClientError,asyncio.TimeoutError,OSError) as exc:
                    if not hint:raise ValueError(str(exc) if isinstance(exc,ValueError) else NETWORK) from exc
                    warnings.append(str(exc) if isinstance(exc,ValueError) else NETWORK)
                    break
                if recognition:break

    identity=recognition or hint
    if identity:
        try:items=_distinct(await step('catalogue',songfinder.candidates(' '.join([identity['artist'],identity['title']]),identity)))
        except ValueError as exc:catalogue_error=str(exc)
        # Related catalogue tracks, not waveform embeddings or extra fingerprint matches.
        if recognition and items:
            from .recommend import _user_sources
            try:similar=_distinct(await asyncio.wait_for(providers.related(items[0]['id'],recognition['artist'],recognition['title'],limit=12,sources=_user_sources()),20),items)[:12]
            except Exception:warnings.append('Related tracks are unavailable right now.')
    log.info('[tiktok:%s] complete: acoustic_match=%s sound_hint=%s candidates=%d warnings=%d',request_id,bool(recognition),bool(hint),len(items),len(warnings))
    return {'mode':'tiktok','recognition':recognition,'sound_hint':hint,'items':items,'similar':similar,
            'found':len(items),'catalogue_error':catalogue_error,'warnings':warnings,
            'sample_count':sample_count,'video':{'url':canonical,'duration':duration,'download':video},
            'basis':'acoustic_fingerprint' if recognition else 'sound_metadata' if hint else 'no_match',
            'similar_basis':'catalogue_related' if similar else None}

async def for_request(request, url, session, offset=0):
    """Stop remote download/recognition work when its initiating client goes away."""
    task=asyncio.create_task(analyze(url,session,offset))
    async def watch():
        while not task.done():
            await asyncio.sleep(.2)
            transport=request.transport
            if transport is None or transport.is_closing():
                task.cancel();return
    monitor=asyncio.create_task(watch())
    try:return await task
    finally:
        monitor.cancel()
        try:await monitor
        except asyncio.CancelledError:pass
