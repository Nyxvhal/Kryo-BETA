"""Private, update-safe avatars. Never uses an uploaded filename as a path."""
from __future__ import annotations
import io, json, os, re, shutil, tempfile, threading, uuid, warnings
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 3 * 1024 * 1024
MAX_ITEMS = 100
LOCK = threading.RLock()
_ID = re.compile(r'custom-[0-9a-f]{32}\Z')

def folder(root):
    p = Path(root) / 'custom-avatars'
    if p.is_symlink():
        raise ValueError('Avatar storage is unavailable')
    return p

def directory(root, aid):
    if not isinstance(aid, str) or not _ID.fullmatch(aid):
        raise ValueError('Custom avatar not found')
    p = folder(root) / aid
    if p.is_symlink() or not p.is_dir():
        raise ValueError('Custom avatar not found')
    return p

def asset(root, aid, kind='image.png'):
    if kind not in ('image.png', 'thumb.png', 'icon.ico'):
        raise ValueError('Custom avatar not found')
    p = directory(root, aid) / kind
    if p.is_symlink() or not p.is_file():
        raise ValueError('Custom avatar not found')
    return p

def catalog(root):
    with LOCK:
        base = folder(root)
        if not base.exists():
            return []
        items = []
        for p in sorted(base.iterdir()):
            if not _ID.fullmatch(p.name) or p.is_symlink() or not p.is_dir():
                continue
            try:
                meta = p / 'metadata.json'
                if meta.is_symlink():
                    continue
                data = json.loads(meta.read_text(encoding='utf-8'))
                asset(root, p.name)
                items.append({'id': p.name, 'name': str(data['name'])[:80],
                              'collection': 'custom', 'category': 'Custom avatars',
                              'custom': True, 'formats': ['png'],
                              'file': f'/api/avatars/custom/{p.name}/image.png',
                              'preview': f'/api/avatars/custom/{p.name}/thumb.png'})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return items

def create(root, content, name):
    if not content or len(content) > MAX_BYTES:
        raise ValueError('Avatar upload is too large')
    name = ' '.join(str(name).split()).strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Enter an avatar name (1–80 characters)')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or getattr(source, 'is_animated', False):
                    raise ValueError('Choose a still PNG, JPEG or WebP image')
                w, h = source.size
                if max(w, h) > 8192 or w * h > 32000000 or min(w, h) < 16:
                    raise ValueError('Image dimensions must be between 16 and 8192 pixels (maximum 32 MP)')
                source.load()
                image = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGBA'), (512, 512), method=Image.Resampling.LANCZOS)
                # Fresh pixel image: no original EXIF, comments or embedded profiles.
                clean = Image.new('RGBA', image.size)
                clean.paste(image)
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('This image could not be read') from None
    with LOCK:
        if len(catalog(root)) >= MAX_ITEMS:
            raise ValueError('You can save up to 100 custom avatars')
        base = folder(root)
        base.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix='.upload-', dir=base))
        aid = 'custom-' + uuid.uuid4().hex
        try:
            clean.save(temp / 'image.png', format='PNG')
            clean.resize((128, 128), Image.Resampling.LANCZOS).save(temp / 'thumb.png', format='PNG')
            clean.save(temp / 'icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
            (temp / 'metadata.json').write_text(json.dumps({'name':name}, ensure_ascii=False), encoding='utf-8')
            os.replace(temp, base / aid)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        return next(i for i in catalog(root) if i['id'] == aid)

def remove(root, aid):
    with LOCK:
        shutil.rmtree(directory(root, aid))
