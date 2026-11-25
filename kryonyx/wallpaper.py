"""Resolve public image/share links to a validated, locally cached wallpaper.
No arbitrary HTML execution. DNS and each redirect reject private addresses.
"""
import asyncio, hashlib, html, io, ipaddress, re, socket
from pathlib import Path
from urllib.parse import urlparse, urljoin, parse_qs
import aiohttp
from aiohttp.abc import AbstractResolver
from PIL import Image, ImageOps
from .paths import cache_dir

MAX_BYTES = 25 * 1024 * 1024

def public_url(value):
    try:
        u=urlparse(value)
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.port not in (None,80,443): return False
        h=u.hostname.lower().rstrip('.')
        if h=='localhost' or h.endswith(('.local','.localhost','.internal')):return False
        try:return ipaddress.ip_address(h).is_global
        except ValueError:return '.' in h
    except ValueError:return False

def unwrap(value):
    if not public_url(value):raise ValueError('Use a public HTTPS image or share link')
    u=urlparse(value);h=u.hostname.lower();q=parse_qs(u.query)
    trusted=h in ('google.com','www.google.com','yandex.ru','yandex.com','www.yandex.ru') or h.endswith('.google.com')
    if trusted:
        for key in ('imgurl','img_url','mediaurl'):
            candidate=(q.get(key) or [''])[0]
            if candidate:
                if not public_url(candidate):raise ValueError('This image URL is not public')
                return candidate
    return value

class PublicResolver(AbstractResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        records=await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM,family=family)
        out=[]
        for fam,_,proto,_,address in records:
            ip=address[0]
            if not ipaddress.ip_address(ip).is_global:raise OSError('Private network address blocked')
            out.append(dict(hostname=host,host=ip,port=port,family=fam,proto=proto,flags=socket.AI_NUMERICHOST))
        if not out:raise OSError('No public image address')
        return out
    async def close(self):pass

def page_image(text, base):
    # Attribute order is immaterial; no page script is evaluated.
    for tag in re.findall(r'<meta\b[^>]*>',text,re.I):
        attrs={k.lower():html.unescape(v) for k,_,v in re.findall(r'([\w:-]+)\s*=\s*([\"\'])(.*?)\2',tag,re.S)}
        if attrs.get('property',attrs.get('name','')).lower() in ('og:image','og:image:secure_url','twitter:image'):
            candidate=urljoin(base,attrs.get('content',''))
            if public_url(candidate):return candidate
    raise ValueError('No image in this page. Open an image and copy its direct image address, or upload a file.')

def directory():
    p=Path(cache_dir())/'wallpapers';p.mkdir(parents=True,exist_ok=True);return p

def store(body):
    if not body or len(body)>MAX_BYTES:raise ValueError('Image is too large (25 MB maximum)')
    with Image.open(io.BytesIO(body)) as im:
        if im.width*im.height>40_000_000:raise ValueError('Image exceeds 40 megapixels')
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((3840,3840),Image.Resampling.LANCZOS)
        out=io.BytesIO();im.save(out,'JPEG',quality=93,optimize=True)
    encoded=out.getvalue();name=hashlib.sha256(encoded).hexdigest()+'.jpg';target=directory()/name
    target.write_bytes(encoded)
    for old in sorted(directory().glob('*.jpg'),key=lambda p:p.stat().st_mtime,reverse=True)[20:]:old.unlink(missing_ok=True)
    return name

async def resolve(value):
    value=unwrap(str(value).strip());image_hops=0
    connector=aiohttp.TCPConnector(resolver=PublicResolver(),use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector,timeout=aiohttp.ClientTimeout(total=18),headers={'User-Agent':'Mozilla/5.0','Accept':'image/*,text/html;q=0.8'}) as session:
        for _ in range(7):
            if not public_url(value):raise ValueError('Non-public image address blocked')
            async with session.get(value,allow_redirects=False) as response:
                if response.status in (301,302,303,307,308):
                    value=urljoin(value,response.headers.get('Location',''));continue
                if response.status!=200:raise ValueError('Image service returned HTTP '+str(response.status))
                kind=response.headers.get('Content-Type','').lower();limit=MAX_BYTES if kind.startswith('image/') else 2*1024*1024
                parts=[];size=0
                async for chunk in response.content.iter_chunked(65536):
                    size+=len(chunk)
                    if size>limit:raise ValueError('Image or page exceeds the size limit')
                    parts.append(chunk)
                body=b''.join(parts)
                if kind.startswith('image/'):
                    try:return await asyncio.to_thread(store,body)
                    except Image.DecompressionBombError as exc:raise ValueError('Image dimensions exceed the safety limit') from exc
                if 'text/html' not in kind or image_hops>=2:raise ValueError('Link did not return an image')
                image_hops+=1;value=page_image(body.decode('utf-8','replace'),value)
    raise ValueError('Too many redirects in the image link')
