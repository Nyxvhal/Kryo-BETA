"""Loopback bridge for the optional native shell (desktop-rs, v73).

The Rust shell starts this server with ``--server-only`` and a random
per-launch token in ``KRYONYX_SHELL_TOKEN``. It shows the native Save As
dialog itself and then asks the endpoints below to write the file, exactly
like ``main.DesktopApi.save_*`` does inside the pywebview window. When the
shell closes it asks ``/api/shell/quit`` for a clean stop (jobs and the
database are closed) before it would end the process.

The token never reaches web pages: the shell adds the header to its own
loopback requests. Without a matching token every endpoint answers 403, so a
page opened in a browser on the same computer cannot use them to write files,
and a server started without the shell does not expose them at all.
"""
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path

TOKEN_ENV = 'KRYONYX_SHELL_TOKEN'
HEADER = 'X-Kryonyx-Shell'
KINDS = ('export', 'clip', 'shared_audio')


class BridgeError(ValueError):
    """A request the shell should show as a plain error message."""


def token() -> str:
    value = os.environ.get(TOKEN_ENV, '')
    return value if 32 <= len(value) <= 256 and value.isalnum() else ''


def allowed(header) -> bool:
    expected = token()
    if not expected or not isinstance(header, str):
        return False
    return hmac.compare_digest(header.encode('utf-8', 'ignore'), expected.encode())


def hello() -> dict:
    from . import APP_NAME, VERSION_LABEL, __version__
    from .paths import app_dir, data_dir
    return {'app': APP_NAME, 'version': __version__, 'version_label': VERSION_LABEL,
            'platform': sys.platform, 'data_dir': data_dir(), 'app_dir': app_dir()}


def _payload(kind, body):
    if kind not in KINDS:
        raise BridgeError('Unknown save request')
    if not isinstance(body, dict):
        raise BridgeError('Bad save request')
    return body


def plan(kind, body, base_url):
    """Suggested file name and dialog filters. Nothing is written here."""
    body = _payload(kind, body)
    if kind == 'export':
        from . import file_exports
        _data, suggested, extension = file_exports.prepare(body.get('spec'), base_url)
        return {'name': suggested, 'extension': extension,
                'filters': [['Export', [extension.lstrip('.')]]]}
    if kind == 'clip':
        from . import clipstream
        from .clip_export import completed_clip
        _source, suggested = completed_clip(clipstream.root(), body.get('session'))
        return {'name': suggested, 'extension': '',
                'filters': [['Video', ['mp4', 'webm']], ['All files', ['*']]]}
    from .audio_share import completed
    _source, name = completed(body.get('token'))
    return {'name': name, 'extension': '.mp3', 'filters': [['Audio', ['mp3']]]}


def _destination(path, extension):
    if not isinstance(path, str) or not path.strip() or '\x00' in path:
        raise BridgeError('Choose where to save the file')
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise BridgeError('Choose where to save the file')
    if extension and not target.name.lower().endswith(extension.lower()):
        target = target.with_name(target.name + extension)
    if not target.parent.is_dir():
        raise BridgeError('The folder does not exist')
    if target.is_dir():
        raise BridgeError('Choose a file name, not a folder')
    return target


def write(kind, body, path, base_url):
    """Write the prepared export / copy the finished clip or shared MP3."""
    body = _payload(kind, body)
    if kind == 'export':
        from . import file_exports
        data, _suggested, extension = file_exports.prepare(body.get('spec'), base_url)
        target = _destination(path, extension)
        file_exports.write_atomic(str(target), data)
        return {'saved': True, 'path': str(target)}
    from .clip_export import copy_atomic
    if kind == 'clip':
        from . import clipstream
        from .clip_export import completed_clip
        source, _suggested = completed_clip(clipstream.root(), body.get('session'))
        target = _destination(path, '')
    else:
        from .audio_share import completed
        source, _name = completed(body.get('token'))
        target = _destination(path, '.mp3')
    copy_atomic(source, target)
    return {'saved': True, 'path': str(target)}
