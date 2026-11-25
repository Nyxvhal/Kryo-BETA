"""Allowlisted non-audio exports. Only a native Save As result can choose a path."""
import base64
import io
import json
import os
import re
import tempfile
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

MAX_BYTES = 160 * 1024 * 1024
KINDS = {'layout': '.json', 'theme': '.json', 'karaoke': '.json', 'playlist': '.kryx',
         'frame': '.png', 'cover': '.png', 'avatar': None, 'avatar-pack': '.zip', 'm3u': '.m3u8'}

def safe_name(value, extension):
    name = re.sub(r'[\x00-\x1f\\/:*?"<>|]', '_', str(value or 'export')).strip(' .')[:170]
    if not name: name = 'export'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'{p}{n}' for p in ('COM','LPT') for n in range(1,10)]}: name = '_' + name
    if not name.lower().endswith(extension): name += extension
    return name

def checked_spec(spec):
    if not isinstance(spec, dict) or spec.get('kind') not in KINDS:
        raise ValueError('This file type cannot be exported')
    kind = spec['kind']; extension = KINDS[kind]
    path = spec.get('url')
    if kind in {'avatar','avatar-pack','m3u'} or (kind == 'karaoke' and path is not None):
        if not isinstance(path,str): raise ValueError('Invalid export URL')
        u = urlsplit(path)
        if u.scheme or u.netloc or u.fragment or not path.startswith('/api/') or '\\' in path:
            raise ValueError('Invalid export URL')
        q=parse_qs(u.query,keep_blank_values=True)
        if kind=='avatar':
            if not re.fullmatch(r'/api/avatarshop/download/[A-Za-z0-9_-]{1,160}',u.path) or set(q)!={'format'} or q['format'] not in [['png'],['svg']]:raise ValueError('Invalid avatar export')
            extension='.'+q['format'][0]
        elif kind=='avatar-pack':
            if u.path!='/api/avatarshop/pack' or set(q)!={'collection'} or q['collection'] not in [[x] for x in ('all','original','redesigned','signature','portraits','custom')]:raise ValueError('Invalid avatar collection')
        elif kind=='m3u':
            if not re.fullmatch(r'/api/playlists/[0-9]+/export.m3u',u.path) or q:raise ValueError('Invalid playlist export')
        elif not re.fullmatch(r'/api/karaoke/jobs/[a-f0-9-]{8,64}/result',u.path) or q:raise ValueError('Invalid karaoke export')
    elif path is not None:
        raise ValueError('This file type cannot use an export URL')
    return kind, extension, safe_name(spec.get('name'),extension)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Export redirect is not permitted')

def fetch_local(base_url,path,body=None):
    u=urlsplit(base_url)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port or u.path or u.query or u.fragment or u.username:raise ValueError('Desktop export server is unavailable')
    request=Request(base_url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Origin':base_url})
    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=100) as response:
        data=response.read(MAX_BYTES+1)
    if not data or len(data)>MAX_BYTES:raise ValueError('Export is empty or too large')
    return data

def validate_data(kind,extension,data):
    if not data or len(data)>MAX_BYTES:raise ValueError('Export is empty or too large')
    if extension=='.json':
        document=json.loads(data)
        if not isinstance(document,dict):raise ValueError('Invalid JSON export')
    elif extension=='.kryx':
        from .extras import unpack_playlist
        unpack_playlist(data.decode('utf-8'))
    elif extension=='.png':
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            if image.format!='PNG':raise ValueError('Invalid PNG export')
            image.verify()
    elif extension=='.svg':
        from xml.etree import ElementTree
        if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('Invalid SVG export')
        if ElementTree.fromstring(data).tag.split('}')[-1]!='svg':raise ValueError('Invalid SVG export')
    elif extension=='.zip':
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if not archive.namelist() or any(not n.lower().endswith(('.png','.svg','.txt','.md','.json')) for n in archive.namelist()):raise ValueError('Invalid avatar archive')
    elif extension=='.m3u8' and not data.startswith(b'#EXTM3U'):raise ValueError('Invalid playlist export')
    return data

def prepare(spec,base_url):
    kind,extension,name=checked_spec(spec)
    if kind=='cover':
        urls=spec.get('urls')
        if not isinstance(urls,list) or not urls or len(urls)>12 or any(not isinstance(v,str) or len(v)>2000000 for v in urls):raise ValueError('Invalid cover request')
        data=fetch_local(base_url,'/api/image/export',{'urls':urls})
    elif spec.get('url'):
        data=fetch_local(base_url,spec['url'])
    elif kind=='frame':
        value=spec.get('data','')
        if not isinstance(value,str) or not value.startswith('data:image/png;base64,') or len(value)>MAX_BYTES*1.4:raise ValueError('Invalid frame export')
        data=base64.b64decode(value.split(',',1)[1],validate=True)
    elif kind in {'layout','theme','karaoke','playlist'}:
        value=spec.get('text')
        if not isinstance(value,str):raise ValueError('Invalid text export')
        data=value.encode('utf-8')
    else:raise ValueError('Invalid export request')
    return validate_data(kind,extension,data),name,extension

def write_atomic(destination,data):
    from pathlib import Path
    path=Path(destination)
    fd,temporary=tempfile.mkstemp(prefix='.kryonyx-save-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as output:
            output.write(data);output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
