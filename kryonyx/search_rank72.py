"""v72/v73 search ranking: the original recording first, full versions, fewer copies.

Text relevance alone made every cover called "Believer" tie with the original
and pushed "Get Lucky (feat. ...)" below covers titled exactly "Get Lucky".
Here relevance is computed on the *core* title (credits, promo and remaster
tags removed) and combined with the catalogue's own signals: YouTube Music
position, play counts, the "Top result" and the result type (catalogue song >
official video > upload). Copies of one recording collapse into one row,
preferring the catalogue audio. Version words (sped up, cover, live, ...) are
penalised only when the query does not ask for them.
"""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher

from .search_rank34 import normal

# Bracketed tags that never change which recording it is (matching only).
_TAGS = re.compile(
    r"\s*[\[(](?=[^\])]*\b(?:official|lyrics?|lyric|audio|video|visuali[sz]er|hd|hq|4k|8k|mv|m/v|clip|клип|текст|"
    r"премьера|explicit|clean|remaster(?:ed)?|mono|stereo|color\s*coded|subtitulado|legendado|перевод)\b)[^\])]*[\])]",
    re.I)
_FEAT_BRACKET = re.compile(r"\s*[\[(]\s*(?:feat\.?|ft\.?|featuring|with|при\s+уч\w*|prod\.?|produced)\b[^\])]*[\])]", re.I)
_FEAT_BARE = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s.+$", re.I)
_DASH_TAG = re.compile(r"\s+[-–—|]\s+(?:(?:\d{4}\s+)?remaster(?:ed)?(?:\s+\d{4})?(?:\s+version)?|official\s+(?:music\s+)?(?:video|audio)|lyrics?)\s*$", re.I)
_SPLIT = re.compile(r"\s+[-–—]\s+")

# Version groups: (penalty when unwanted, words). Words match at word starts,
# so "live" never fires inside "oliver".
VERSION_GROUPS = {
    'slowed': (18, ('slowed', 'замедл')),
    'sped': (18, ('sped', 'speed up', 'speedup', 'ускор', 'nightcore')),
    'remix': (16, ('remix', 'ремикс', 'rmx', 'bootleg', 'flip', 'vip mix', 'mashup', 'мэшап', 'мешап')),
    'live': (14, ('live', 'концерт', 'вживую', 'лайв', 'unplugged', 'арена', 'arena', 'лужники', 'стадион',
                  'stadium', 'фестивал', 'festival', 'олимпийск', 'rock am ring', 'glastonbury', 'coachella')),
    'cover': (22, ('cover', 'кавер', 'covered by', 'tribute', 'в исполнении', 'ai cover', 'kidz bop')),
    'instrumental': (18, ('instrumental', 'минус', 'инструментал', 'backing track', 'karaoke', 'караоке', 'acapella', 'a cappella')),
    'reverb': (14, ('reverb', 'реверб')),
    'acoustic': (10, ('acoustic', 'акустик')),
    'arrangement': (16, ('piano', 'пианино', 'фортепиано', 'violin', 'скрипк', 'guitar', 'гитар', 'orchestra', 'оркестр', 'symphon', 'симфон', 'string quartet', 'музыкальная шкатулка', 'music box', 'lullaby', 'колыбельн', '8 bit', '8bit')),
    'lofi': (12, ('lofi', 'lo fi')),
    'effects': (20, ('8d', '16d', 'bass boosted', 'bassboosted', 'бас буст')),
    'extended': (14, ('extended', '1 hour', '10 hours', '1 час', '10 часов', 'loop')),
    'tiktok': (16, ('tiktok', 'tik tok', 'тикток', 'тик ток')),
    'fan': (26, ('amv', 'gmv', 'smv', 'fan made', 'fanmade', 'animation', 'анимация', 'fnaf', 'minecraft', 'sfm', 'mmd', 'reaction', 'реакция', 'parody', 'пародия', 'tutorial', 'lesson', 'урок', 'разбор', 'аккорды', 'chords', 'sheet music', 'ноты', 'flashmob')),
    'preview': (40, ('preview', 'snippet', 'teaser', 'trailer', 'превью', 'сниппет', 'тизер', 'shorts')),
}
_LONG_WORDS = {'mix', 'playlist', 'album', 'hour', 'hours', 'compilation', 'час', 'сборник', 'альбом', 'full'}

# v73: a concert date in the title ("15.05.2021") marks a live recording.
_LIVE_DATE = re.compile(r'(?<!\d)\d{1,2}[./]\d{1,2}[./](?:19|20)\d{2}(?!\d)')
# v73: channels that only make covers ("Pianella Piano", "KIDZ BOP Kids", "... Karaoke").
_COVER_ARTIST = ('piano', 'karaoke', 'kidz bop', 'kids', 'lullab', 'tribute', 'cover', 'music box', 'instrumental',
                 '8 bit', '8bit', 'nightcore', 'sped up', 'slowed', 'acapella', 'караоке', 'кавер', 'колыбельн',
                 'для детей', 'минус')
# v73: the right side of "X - Y" that is a version tag, not a song ("Song - Live at Wembley").
_VERSIONISH = re.compile(r'^\s*(?:live|acoustic|radio\s+edit|remix|remaster|extended|instrumental|demo|version|edit|'
                         r'mix|mono|stereo|sped|slowed|reverb|cover|кавер|ремикс|минус|живое|концерт)\b', re.I)
# v73: per-source trust so rows ranked by different sources compare fairly.
# YouTube rows carry the catalogue signals (plays, «Top result»); Spotify is an
# official catalogue without them; SoundCloud is mostly uploads and edits.
SOURCE_TRUST = {'youtube': 0.0, 'spotify': -4.0, 'soundcloud': -12.0}
OTHER_SOURCE_TRUST = -16.0


def core_title(title):
    text = str(title or '')
    for _ in range(3):
        before = text
        text = _TAGS.sub('', text); text = _FEAT_BRACKET.sub('', text)
        text = _FEAT_BARE.sub('', text); text = _DASH_TAG.sub('', text)
        if text == before:
            break
    return normal(text) or normal(title)


def _has(haystack, word):
    return (' ' + word) in haystack


def versions(text):
    hay = ' ' + normal(text) + ' '
    hay_raw = ' ' + str(text or '').casefold() + ' '
    found = set()
    for name, (_, words) in VERSION_GROUPS.items():
        if any(_has(hay, w) or _has(hay_raw, w) for w in words):
            found.add(name)
    if _LIVE_DATE.search(str(text or '')):
        found.add('live')
    return found


def artist_names(track):
    names = []
    for item in track.get('artists') or []:
        if isinstance(item, dict) and item.get('name'):
            names.append(normal(item['name']))
    for part in re.split(r'\s*(?:,|&|\bx\b|\bfeat\.?|\bft\.?|\band\b|\bи\b)\s*', str(track.get('artist') or ''), flags=re.I):
        if normal(part):
            names.append(normal(part))
    joined = normal(track.get('artist'))
    if joined:
        names.append(joined)
    out = []
    for name in names:
        name = re.sub(r'\s*(?:topic|vevo|official)$', '', name).strip()
        if name and name not in out:
            out.append(name)
    return out


def identity(track):
    """(core title, artist names) for collapsing copies of one recording.

    Uploads titled "Artist - Song" by a different channel are matched by the
    artist named in the title, so a re-upload joins the original's group.
    """
    title = str(track.get('title') or '')
    names = artist_names(track)
    raw = str(track.get('original_title') or title)
    parts = _SPLIT.split(raw, 1)
    if len(parts) == 2 and (track.get('_rank72') or {}).get('kind') != 'song':
        left, right = parts
        if 0 < len(left) <= 60 and core_title(right) and not _VERSIONISH.match(right):
            names = names + [n for n in artist_names({'artist': left}) if n not in names]
            title = right
    return core_title(title), names


def plays(value):
    """'7B' / '1.9M' / '56K' / '1,234' / 1234 -> int."""
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else 0
    text = str(value or '').strip().replace(',', '').replace('\u00a0', '').upper()
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMB])?', text)
    if not match:
        return 0
    number = float(match.group(1)) * {'K': 1e3, 'M': 1e6, 'B': 1e9}.get(match.group(2) or '', 1)
    return int(number)


def relevance(query, track):
    q = normal(query)
    words = q.split()
    if not words:
        return 0.0
    # v73: "Земфира — Бесконечность (Official Video)" from the channel
    # "Zemfira" is the song «Бесконечность» by Земфира — the artist prefix of an
    # upload title is not part of the song name (identity() strips it).
    title, artists = identity(track)
    full_title = normal(track.get('original_title') or track.get('title'))
    artist = artists[-1] if artists else ''
    joined = f'{artist} {title}'.strip()
    tokens = set((joined + ' ' + full_title + ' ' + ' '.join(artists)).split())
    if not tokens:
        return 0.0
    coverage = sum(max(SequenceMatcher(None, w, x).ratio() for x in tokens) for w in words) / len(words)
    shape = max(SequenceMatcher(None, q, title).ratio(), SequenceMatcher(None, q, joined).ratio(),
                SequenceMatcher(None, q, f'{title} {artist}').ratio())
    score = coverage * 60 + shape * 25
    if q == title: score += 35
    if q in (joined, f'{title} {artist}') or any(q in (f'{a} {title}', f'{title} {a}') for a in artists): score += 50
    if q in artists: score += 12
    if q in joined or q in full_title: score += 8
    if title and len(title) >= 3 and f' {title} ' in f' {q} ' and q != title: score += 10
    wanted = versions(query); got = versions(track.get('original_title') or track.get('title'))
    got |= versions(track.get('album') or '') & {'live', 'instrumental', 'cover'}
    penalty = 0
    for name in got - wanted:
        penalty += VERSION_GROUPS[name][0]
    score -= min(penalty, 48)
    score += 12 * len(wanted & got)
    score -= 20 * len(wanted - got)
    duration = track.get('duration') or 0
    if isinstance(duration, (int, float)) and duration > 1200 and not set(words) & _LONG_WORDS:
        score -= 25
    # v73: cover channels ("Pianella Piano", "KIDZ BOP Kids") title their
    # uploads exactly like the original; their name gives them away.
    padded_q, padded_a = ' ' + q + ' ', ' ' + ' '.join(artists) + ' '
    if any(_has(padded_a, w) for w in _COVER_ARTIST) and not any(_has(padded_q, w) for w in _COVER_ARTIST):
        score -= 14
    # v73: a title without letters ("∞" is Земфира's «Бесконечность») cannot be
    # matched as text; when the catalogue put it among its first songs, trust it.
    pos = (track.get('_rank72') or {}).get('pos')
    if not title and isinstance(pos, int) and pos <= 2:
        score = max(score, 110.0 - 12 * pos)
    return score


def prior(track):
    """Catalogue signals; bounded so a strong text match always wins."""
    f = track.get('_rank72') or {}
    score = 0.0
    if f.get('pos') is not None: score += 18 * math.exp(-f['pos'] / 5)
    if f.get('vpos') is not None: score += 7 * math.exp(-f['vpos'] / 4)
    if f.get('mixed') is not None: score += 6 * math.exp(-f['mixed'] / 4)
    # v73: YouTube Music's «Top result» and play counts weigh more: among many
    # songs with the same name the famous one is what people look for.
    if f.get('top'): score += 34
    if f.get('top_artist'): score += 45 if f['top_artist'] == 2 else 10
    count = f.get('plays') or plays(track.get('views'))
    if count: score += 7 * min(6.5, max(0.0, math.log10(count) - 3))
    kind = f.get('kind')
    score += {'song': 8, 'omv': 3, 'ugc': -5}.get(kind, 0)
    duration = track.get('duration') or 0
    if kind != 'song' and isinstance(duration, (int, float)) and 0 < duration < 75:
        score -= 20  # short uploads are usually snippets, not the full track
    source = track.get('source')
    if source:
        score += SOURCE_TRUST.get(source, OTHER_SOURCE_TRUST)
    return score


def score(query, track):
    return round(relevance(query, track) + prior(track), 4)


def _share_alias_signals(rows):
    """v73: a catalogue song titled only with symbols ("∞") and an upload of
    the same artist and length whose title matches the query ("Земфира —
    Бесконечность") are one recording under two names. The readable row gets
    the catalogue's position and plays, so the famous song is not outranked by
    unknown songs that merely share the name. Both rows stay in the list."""
    symbols = [r for r in rows if not core_title(r.get('title'))]
    if not symbols:
        return
    for sym in symbols:
        fs = sym.get('_rank72') or {}
        names = set(artist_names(sym))
        length = sym.get('duration') or 0
        if not names or not isinstance(length, (int, float)) or length <= 0:
            continue
        for other in rows:
            if other is sym or not core_title(other.get('title')):
                continue
            span = other.get('duration') or 0
            if not isinstance(span, (int, float)) or abs(span - length) > 20:
                continue
            if not names & set(identity(other)[1]):
                continue
            fo = other.setdefault('_rank72', {})
            for key in ('pos', 'mixed', 'vpos'):
                if fs.get(key) is not None:
                    fo[key] = min(fo.get(key, fs[key]), fs[key])
            if fs.get('top'):
                fo['top'] = True
            if (fs.get('plays') or 0) > (fo.get('plays') or 0):
                fo['plays'] = fs['plays']


def rank(query, tracks, top_artist=''):
    """Score, collapse copies (catalogue audio represents the group), sort."""
    rows = []
    tracks = [dict(t, _rank72=dict(t.get('_rank72') or {})) for t in tracks if t]
    _share_alias_signals(tracks)
    for track in tracks:
        if not track or not track.get('id'):
            continue
        f = dict(track.get('_rank72') or {})
        want_artist = normal(f.get('top_artist_name') or top_artist)
        if want_artist and want_artist in artist_names(track):
            # A query that *is* the artist's name wants that artist's songs,
            # not other artists' songs that merely share the word as a title.
            f['top_artist'] = 2 if want_artist == normal(query) else 1
        row = {**track, '_rank72': f}
        row['search_score'] = score(query, row)
        rows.append(row)
    rows.sort(key=lambda r: -r['search_score'])
    groups = []
    by_id = set()
    for row in rows:
        if row['id'] in by_id:
            continue
        by_id.add(row['id'])
        title, names = identity(row)
        home = None
        for group in groups:
            if group['title'] == title and title and set(group['names']) & set(names) \
                    and versions(group['rep'].get('original_title') or group['rep'].get('title')) == versions(row.get('original_title') or row.get('title')):
                home = group; break
        if home is None:
            groups.append({'title': title, 'names': list(names), 'rep': row, 'score': row['search_score']}); continue
        home['names'] += [n for n in names if n not in home['names']]
        rep = home['rep']
        if (row.get('_rank72') or {}).get('kind') == 'song' and (rep.get('_rank72') or {}).get('kind') != 'song' \
                and rep.get('source') == row.get('source'):
            home['rep'] = row  # catalogue audio: full length, best quality
    out = []
    for group in sorted(groups, key=lambda g: -g['score']):
        out.append({**group['rep'], 'search_score': group['score']})
    return out


def public(track):
    """Row for the UI: signals hidden; v73 adds `m73` (core title, artist
    names, version tags) so the UI can fold the same recording found by
    different sources, and `plays_n` (approximate plays) for «popular» sort."""
    out = {k: v for k, v in track.items() if k != '_rank72'}
    f = track.get('_rank72') or {}
    if f.get('plays') and 'plays_n' not in out:
        out['plays_n'] = int(f['plays'])
    title, names = identity(track)
    if title:
        out['m73'] = [title, names[:6], sorted(versions(track.get('original_title') or track.get('title')))]
    return out
