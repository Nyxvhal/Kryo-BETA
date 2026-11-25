"""Portable playlist metadata only. No credentials, audio, DRM or local paths are read."""
from __future__ import annotations
import csv, io, json, plistlib, re
from xml.parsers.expat import ExpatError
from pathlib import PurePath
from typing import Any

MAX_BYTES = 2 * 1024 * 1024
MAX_TRACKS = 5000
SERVICES = ('youtube-music', 'vk', 'spotify', 'apple-music', 'deezer', 'soundcloud', 'generic')

def _norm(value):
    return re.sub(r'[^\w]', '', str(value).casefold())

def _value(row, *keys):
    data = {_norm(k): v for k, v in row.items()}
    return next((data[_norm(k)] for k in keys if _norm(k) in data and data[_norm(k)] not in (None, '')), '')

def _names(value):
    if isinstance(value, list): return ', '.join(filter(None, (_names(x) for x in value)))
    if isinstance(value, dict): return str(value.get('name') or value.get('title') or '')
    return str(value or '').strip()

def _duration(value, milliseconds=False):
    if value in ('', None): return None
    try:
        if isinstance(value, str) and ':' in value:
            parts = [float(x) for x in value.split(':')]
            seconds = sum(n * 60 ** i for i, n in enumerate(reversed(parts)))
        else: seconds = float(value) / (1000 if milliseconds else 1)
        return round(seconds) if 0 < seconds < 86400 else None
    except (TypeError, ValueError, OverflowError): return None

def _track(row):
    if not isinstance(row, dict): return None
    if isinstance(row.get('track'), dict): row = row['track']
    if isinstance(row.get('attributes'), dict): row = row['attributes']
    title = _value(row, 'title', 'Track Name', 'Track name', 'name', 'song', 'название', 'трек', 'Название трека')
    if not isinstance(title, str) or not title.strip(): return None
    artist = _value(row, 'artist', 'artists', 'Artist Name', 'Artist Name(s)', 'artistName', 'исполнитель', 'автор')
    album = _value(row, 'album', 'Album Name', 'albumName', 'альбом')
    ms = _value(row, 'duration_ms', 'durationMs', 'durationInMillis', 'Track Duration (ms)', 'Total Time')
    seconds = _value(row, 'duration', 'duration_seconds', 'Duration (s)', 'time', 'длительность')
    return {'title': title.strip()[:500], 'artist': _names(artist)[:500], 'album': _names(album)[:500],
            'duration': _duration(ms, True) if ms != '' else _duration(seconds), 'url': '', 'thumbnail': ''}

def parse(content: str, filename: str = '', service: str = 'generic') -> dict:
    if service not in SERVICES: raise ValueError('Unknown music service')
    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_BYTES: raise ValueError('Playlist file exceeds 2 MB')
    content = content.lstrip('\ufeff').strip()
    if not content: raise ValueError('Playlist file is empty')
    name = PurePath(str(filename).replace('\\', '/')).stem[:120] or 'Imported playlist'
    rows: Any = []
    try:
        if content.startswith(('{', '[')):
            data = json.loads(content)
            if isinstance(data, list): rows = data
            elif isinstance(data, dict):
                if isinstance(data.get('response'), dict): data = data['response']
                name = str(data.get('name') or data.get('title') or name)[:120]
                rows = data.get('tracks', data.get('items', data.get('songs', data.get('data', []))))
                if isinstance(rows, dict): rows = rows.get('items', rows.get('data', []))
            if not isinstance(rows, list): raise ValueError('Expected an array of tracks')
        elif content.startswith(('<?xml', '<plist')):
            if '<!ENTITY' in content.upper(): raise ValueError('XML entities are not allowed')
            data = plistlib.loads(content.encode('utf-8'))
            tracks = data.get('Tracks', {})
            playlists = data.get('Playlists', [])
            # Follow exported playlist order, not dictionary order, when available.
            if playlists and playlists[0].get('Playlist Items'):
                name = str(playlists[0].get('Name') or name)[:120]
                rows = [tracks.get(str(x.get('Track ID')), {}) for x in playlists[0]['Playlist Items']]
            else: rows = list(tracks.values())
        elif content.startswith('#EXTM3U') or PurePath(filename).suffix.lower() in ('.m3u', '.m3u8'):
            for line in content.splitlines():
                if line.startswith('#EXTINF:') and ',' in line:
                    metadata, label = line.split(',', 1)
                    artist, sep, title = label.partition(' - ')
                    rows.append({'title': title if sep else artist, 'artist': artist if sep else '', 'duration': metadata.split(':', 1)[1]})
        else:
            try: dialect = csv.Sniffer().sniff(content[:8192], delimiters=',;\t')
            except csv.Error: dialect = csv.excel_tab if '\t' in content.splitlines()[0] else csv.excel
            rows = list(csv.DictReader(io.StringIO(content), dialect=dialect))
    except (json.JSONDecodeError, plistlib.InvalidFileException, ExpatError, csv.Error, TypeError, AttributeError, KeyError) as exc:
        raise ValueError('Cannot read playlist. Use CSV, JSON, M3U or Apple Music XML') from exc
    if len(rows) > MAX_TRACKS: raise ValueError('Maximum 5000 rows per import; split the file')
    items, seen, duplicates, skipped = [], set(), 0, 0
    for row in rows:
        item = _track(row)
        if not item: skipped += 1; continue
        key = (_norm(item['artist']), _norm(item['title']), item['duration'])
        if key in seen: duplicates += 1; continue
        seen.add(key); items.append(item)
    if not items: raise ValueError('No tracks found. Required columns: title / Track Name and artist / Artist Name')
    return {'name': name, 'service': service, 'type': 'playlist', 'items': items, 'total': len(items),
            'duplicates': duplicates, 'skipped': skipped, 'truncated': False, 'source_url': ''}
