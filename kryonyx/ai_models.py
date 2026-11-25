"""Registry and verified download of the optional AI model weights.

Weights are never bundled. Each file is fetched over HTTPS from the upstream
release, size-limited, SHA-256 verified and only then moved into place, so a
truncated or substituted download can never be loaded by the worker.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
import zipfile
from pathlib import Path

from .paths import data_dir
from . import audiovault

MODELS = {
    'realesr-general-x4v3': {
        'file': 'realesr-general-x4v3.pth', 'kind': 'upscale', 'arch': 'compact', 'num_conv': 32,
        'title': 'Real-ESRGAN general v3', 'use': 'video', 'license': 'BSD-3-Clause',
        'url': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth',
        'size': 4885111, 'sha256': '8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292'},
    'realesr-animevideov3': {
        'file': 'realesr-animevideov3.pth', 'kind': 'upscale', 'arch': 'compact', 'num_conv': 16,
        'title': 'Real-ESRGAN anime video v3', 'use': 'video', 'license': 'BSD-3-Clause',
        'url': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth',
        'size': 2504012, 'sha256': 'b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d'},
    'RealESRGAN_x4plus': {
        'file': 'RealESRGAN_x4plus.pth', 'kind': 'upscale', 'arch': 'rrdb',
        'title': 'Real-ESRGAN x4plus', 'use': 'image', 'license': 'BSD-3-Clause',
        'url': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
        'size': 67040989, 'sha256': '4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1'},
    'rife': {
        'file': 'rife-flownet.pkl', 'kind': 'interpolate', 'arch': 'ifnet',
        'title': 'RIFE (ECCV 2022)', 'use': 'video', 'license': 'MIT',
        'url': 'https://huggingface.co/hzwer/RIFE/resolve/main/RIFE_train_log.zip',
        'size': 39801396, 'sha256': 'e17c7d98eddf985a75068b366fb3891b81ade394ca65618e1cbaae21f211f038',
        'member': 'RIFE_train_log/flownet.pkl', 'member_size': 42901317,
        'member_sha256': '2b48d6f7c7c09c109ad50372e9d9dc722a75859dc20e8832a62826ecede35ad3'},
}
# Which weights each feature needs; the UI downloads only what is missing.
NEEDS = {
    'wallpaper:photo': ['RealESRGAN_x4plus'], 'wallpaper:fast': ['realesr-general-x4v3'],
    'wallpaper:art': ['realesr-animevideov3'],
    'clip:general': ['realesr-general-x4v3'], 'clip:anime': ['realesr-animevideov3'], 'clip:smooth': ['rife'],
}
_verified = {}


def folder():
    path = Path(data_dir()) / 'ai' / 'models'
    path.mkdir(parents=True, exist_ok=True)
    return path


def path(model_id):
    return folder() / MODELS[model_id]['file']


def _expected(spec):
    return (spec.get('member_size') or spec['size'], spec.get('member_sha256') or spec['sha256'])


def sha256(file, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(file, 'rb') as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def present(model_id, verify=True):
    """True only for a complete file with the published digest (cached by stat)."""
    spec = MODELS[model_id]; target = path(model_id)
    try:
        stat = target.stat()
    except OSError:
        return False
    size, digest = _expected(spec)
    if stat.st_size != size:
        return False
    if not verify:
        return True
    key = (str(target), stat.st_size, stat.st_mtime_ns)
    if _verified.get(model_id) == key:
        return True
    if sha256(target) != digest:
        return False
    _verified[model_id] = key
    return True


def summary():
    out = {}
    for model_id, spec in MODELS.items():
        out[model_id] = {'title': spec['title'], 'kind': spec['kind'], 'use': spec['use'], 'license': spec['license'],
                         'size': spec['size'], 'present': present(model_id)}
    return out


def missing(feature):
    return [m for m in NEEDS.get(feature, []) if not present(m)]


class Downloads:
    """One verified download at a time; progress is polled by /api/ai/status."""

    def __init__(self):
        self.state = {}; self.task = None; self.queue = []

    def public(self):
        return {k: dict(v) for k, v in self.state.items()}

    def start(self, ids, http_factory):
        ids = [m for m in ids if m in MODELS]
        if not ids:
            raise ValueError('Unknown model')
        for model_id in ids:
            if present(model_id, verify=False) and present(model_id):
                self.state[model_id] = {'stage': 'done', 'done': MODELS[model_id]['size'], 'total': MODELS[model_id]['size']}
                continue
            if self.state.get(model_id, {}).get('stage') in ('queued', 'downloading', 'verifying'):
                continue
            self.state[model_id] = {'stage': 'queued', 'done': 0, 'total': MODELS[model_id]['size']}
            self.queue.append(model_id)
        if self.queue and (self.task is None or self.task.done()):
            self.task = asyncio.create_task(self._run(http_factory))
        return self.public()

    async def _run(self, http_factory):
        while self.queue:
            model_id = self.queue.pop(0)
            item = self.state[model_id]
            try:
                await self._fetch(model_id, item, http_factory)
                item['stage'] = 'done'
            except asyncio.CancelledError:
                item['stage'] = 'cancelled'; raise
            except Exception as exc:  # network, digest or disk errors are reported, never loaded
                item['stage'] = 'error'; item['error'] = str(exc)[:300] or 'Download failed'

    async def _fetch(self, model_id, item, http_factory):
        import aiohttp
        spec = MODELS[model_id]
        part = folder() / (spec['file'] + '.download')
        digest = hashlib.sha256(); size = 0; started = time.monotonic()
        item['stage'] = 'downloading'
        session = await http_factory()
        timeout = aiohttp.ClientTimeout(total=3600, sock_read=60)
        try:
            async with session.get(spec['url'], allow_redirects=True, timeout=timeout,
                                   headers={'User-Agent': 'KryonyxMusic/72 (model download)'}) as response:
                if response.status != 200:
                    raise ValueError('Model server returned HTTP %s' % response.status)
                if response.url.scheme != 'https':
                    raise ValueError('Refusing a non-HTTPS model redirect')
                with open(part, 'wb') as fh:
                    async for chunk in response.content.iter_chunked(1 << 18):
                        size += len(chunk)
                        if size > spec['size']:
                            raise ValueError('Model file is larger than the published size')
                        digest.update(chunk)
                        await audiovault.run_blocking_owned(fh.write, chunk)
                        elapsed = max(.001, time.monotonic() - started)
                        item.update(done=size, rate=round(size / elapsed))
            item['stage'] = 'verifying'
            if size != spec['size'] or digest.hexdigest() != spec['sha256']:
                raise ValueError('Model checksum mismatch; the file was discarded')
            if spec.get('member'):
                await audiovault.run_blocking_owned(_extract_member, part, spec, path(model_id))
            else:
                os.replace(part, path(model_id))
            _verified.pop(model_id, None)
            if not await audiovault.run_blocking_owned(present, model_id):
                raise ValueError('Installed model failed verification')
        finally:
            part.unlink(missing_ok=True)


def _extract_member(archive, spec, target):
    """Copy exactly one named member out of the verified zip (no path from the archive is used)."""
    tmp = target.with_name(target.name + '.part')
    digest = hashlib.sha256(); written = 0
    try:
        with zipfile.ZipFile(archive) as zf:
            try:
                info = zf.getinfo(spec['member'])
            except KeyError:
                raise ValueError('Unexpected model archive contents') from None
            if info.file_size != spec['member_size']:
                raise ValueError('Unexpected model archive contents')
            with zf.open(info) as src, open(tmp, 'wb') as dst:
                while block := src.read(1 << 20):
                    written += len(block)
                    if written > spec['member_size']:
                        raise ValueError('Model archive member is too large')
                    digest.update(block); dst.write(block)
        if written != spec['member_size'] or digest.hexdigest() != spec['member_sha256']:
            raise ValueError('Model archive checksum mismatch')
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
