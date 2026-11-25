"""Stable, Unicode-aware relevance scoring; never merges different editions/sources."""
import re
import unicodedata
from difflib import SequenceMatcher


def normal(text):
    text = unicodedata.normalize('NFKD', str(text or '').casefold())
    return ' '.join(re.sub(r'[^\w\s]', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


VERSIONS = ('slowed', 'sped', 'remix', 'live', 'cover', 'instrumental', 'karaoke', 'nightcore', 'reverb')


def relevance(query, track):
    q = normal(query)
    title, artist = normal(track.get('title')), normal(track.get('artist'))
    joined = f'{artist} {title}'.strip()
    words = q.split()
    tokens = joined.split()
    if not words or not tokens:
        return 0.0
    coverage = sum(max(SequenceMatcher(None, w, x).ratio() for x in tokens) for w in words) / len(words)
    score = coverage * 60 + max(SequenceMatcher(None, q, title).ratio(), SequenceMatcher(None, q, joined).ratio()) * 25
    if q == title: score += 35
    if q == joined or q == f'{title} {artist}': score += 50
    if q == artist: score += 12
    if q in joined: score += 8
    for version in VERSIONS:
        want, got = version in words, version in tokens
        if got and not want: score -= 17
        if want and got: score += 12
        if want and not got: score -= 20
    duration = track.get('duration') or 0
    if isinstance(duration, (float, int)) and duration > 1200 and not set(words) & {'mix', 'playlist', 'album', 'hour', 'compilation'}:
        score -= 25
    return round(score, 4)


def rank_tracks(query, tracks):
    return sorted(({**t, 'search_score': relevance(query, t)} for t in tracks), key=lambda t: -t['search_score'])
