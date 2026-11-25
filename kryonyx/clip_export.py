"""Export only completed, known clip-cache files; never accept a source path from JS."""
from pathlib import Path
import json
import os
import re
import shutil
import tempfile


def completed_clip(cache_root, session_id):
    if not isinstance(session_id, str) or not re.fullmatch(r'[a-f0-9]{24}', session_id):
        raise ValueError('Invalid clip session')
    directory = Path(cache_root).resolve() / session_id
    if directory.is_symlink():
        raise ValueError('Invalid clip cache directory')
    data = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    container = data.get('container')
    if container not in ('mp4', 'webm'):
        raise ValueError('Unsupported clip container')
    sources = data.get('sources', {})
    if not sources or not all(s.get('complete') for s in sources.values()):
        raise ValueError('The complete clip is not ready yet')
    source = directory / ('clip.' + container)
    if not source.is_file() and 'audio' not in sources:
        source = directory / 'video.bin'
    if not source.is_file() or source.is_symlink() or source.resolve().parent != directory:
        raise ValueError('The complete clip is not ready yet')
    video_id = re.sub(r'[^\w-]', '', str(data.get('video_id', 'clip')))[:80]
    return source, f"clip-{video_id}-{int(data.get('height') or 0)}p.{container}"


def copy_atomic(source, destination):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('Choose a file outside the player cache')
    # An interrupted copy must not truncate an existing user file.
    fd, temporary = tempfile.mkstemp(prefix='.kryonyx-export-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as output, source.open('rb') as input_file:
            shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
