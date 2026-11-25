"""
recommend.py — система рекомендаций.

Никаких «для сна» и «в дорогу»: подборки строятся только из реального
поведения — что слушали до конца, что лайкнули, что пропустили, кого
слушают чаще всего. Похожесть берём из официальных миксов YouTube
(RD-плейлисты), а не из поиска по слову «похожее».

Оценка трека:
    score = похожесть источника (позиция в радио/чарте)
          + вес автора (вкус, со временем «стареет»)
          + бонус за новизну (не слушали)
          - штраф за автора и трек, которые часто пропускают
          - штраф за «мусор»: сборники на час, подкасты, sped up/nightcore,
            SEO-заливы вида «новинки музыки 2026»

v70: холодный старт берётся из официальных чартов и редакционных подборок
YouTube Music, а не из поиска по ключевым словам; версии одной песни
(клип, lyric video, sped up) считаются одним треком; один исполнитель не
идёт подряд в радио и волне.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import math
import os
import random
import re
import time

from . import extras, providers, storage, account_import, ytmusic
from .trackmeta import clean_track, artist_track_matches
from .paths import cache_dir

log = logging.getLogger(__name__)

_cache: dict[str, tuple[float, list[dict]]] = {}
_generation = 0
_disk_invalidated = False
_cache_scope = None


def current_generation() -> int:
    return _generation

def preferences():
    try: raw=storage.get_settings().get("recommend50",{})
    except Exception: raw={}
    if not isinstance(raw,dict):raw={}
    def number(key,default):
        try: return max(0,min(100,float(raw.get(key,default))))
        except (ValueError,TypeError): return default
    return {"discovery":number("discovery",50),"importInfluence":number("importInfluence",65)}

def _scope():
    try: signatures=account_import.signatures()
    except Exception: signatures=[]
    try: hidden=storage.get_settings().get('search26Hidden',[])
    except Exception: hidden=[]
    return hashlib.sha256(json.dumps([sorted(_user_sources()),preferences(),signatures,hidden,_country()],sort_keys=True).encode()).hexdigest()

def _external():
    if preferences()['importInfluence']<=0:return {'artists':[],'played':set(),'liked':set(),'queries':[]}
    try:return account_import.context()
    except Exception:return {'artists':[],'played':set(),'liked':set(),'queries':[]}

def _top_artists(limit=8):
    local=storage.top_artists(max(limit,12));external=_external();factor=preferences()['importInfluence']/100
    merged={_norm(x['artist']):dict(x) for x in local}
    for row in external['artists']:
        key=_norm(row['artist']);current=merged.setdefault(key,{'artist':row['artist'],'weight':0,'plays':0,'skips':0})
        current['weight']+=row['weight']*factor
    try:blocked={_norm(a) for a in storage.disliked_artists()}
    except Exception:blocked=set()
    return sorted([x for k,x in merged.items() if k not in blocked],key=lambda x:-x['weight'])[:limit]



# v70: полки холодного старта собираются иначе — старый кэш (с SEO-сборниками)
# не показываем даже один запуск.
_ROWS_VERSION = 70


def _rows_file() -> str:
    return os.path.join(cache_dir(), "home_rows.json")


def _load_rows() -> list[dict] | None:
    """Подборки с прошлого запуска: главный экран рисуется мгновенно."""
    try:
        path = _rows_file()
        if not os.path.isfile(path):
            return None
        if time.time() - os.path.getmtime(path) > 7 * 24 * 3600:
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data,dict) or data.get("version")!=_ROWS_VERSION or data.get("scope")!=_scope():return None
        rows=data.get("rows")
        return rows if isinstance(rows, list) and rows else None
    except Exception:
        return None


def _save_rows(rows: list[dict]) -> None:
    global _disk_invalidated
    try:
        temp=_rows_file()+".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump({"version":_ROWS_VERSION,"scope":_scope(),"rows":rows}, fh, ensure_ascii=False)
        os.replace(temp,_rows_file())
        _disk_invalidated = False
    except Exception:
        pass


def cached_rows() -> list[dict] | None:
    global _cache_scope
    scope=_scope()
    if _cache_scope!=scope:_cache.clear();_cache_scope=scope
    hit = _cache.get("rows")
    if hit and hit[0] > time.monotonic():
        return hit[1]
    if _disk_invalidated:
        return None
    return _load_rows()
_CACHE_TTL = 600.0
_network_slots = asyncio.Semaphore(4)


async def _bounded(coro, timeout: float = 18):
    """Сетевой вызов с общим лимитом параллельности и тайм-аутом.

    Если задачу отменили, пока она ждала слот, корутина так и не стартует:
    её нужно закрыть, иначе Python пишет «coroutine was never awaited».
    """
    started = False
    try:
        async with _network_slots:
            started = True
            try:
                return await asyncio.wait_for(coro, timeout=timeout)
            except asyncio.CancelledError:
                raise
            except Exception:
                return []
    finally:
        if not started and inspect.iscoroutine(coro):
            coro.close()
_lock = asyncio.Lock()

# Стартовые подборки, когда истории ещё нет. Это жанры и «что слушают сейчас»,
# а не настроения.
# Заголовки — английские ключи словаря интерфейса: их переводит клиент
# (web/js/i18n.js). Раньше здесь стояли русские строки, и на главной
# любого языка, кроме русского, полки оставались по-русски.
#
# v70: источник — официальные чарты страны и редакционные плейлисты YouTube
# Music. Поиск по словам остаётся только запасным путём (когда YouTube
# выключен в источниках или каталог недоступен) и проходит строгий фильтр.
_YEAR = time.gmtime().tm_year
_CHART = "Official chart"
_EDITORIAL = "Curated playlist"
_START = "To get started"
_COLD_START = [
    # (заголовок, подпись, спецификация каталога, запасные запросы)
    ("Popular now", _CHART, {"chart": "daily"}, ["popular songs", "chart music"]),
    ("Trending now", _CHART, {"chart": "trending"}, ["trending songs"]),
    ("Russian rap and pop", _START, {"songs": ["русский рэп хиты", "русская поп музыка хиты"], "langs": ("ru", "uk")},
     ["русский рэп", "русская поп музыка"]),
    ("New releases", "Fresh releases", {"editorial": "released", "prefer": ("released",), "keys": ("released",)}, ["new songs"]),
    ("Hip-hop and rap", _EDITORIAL, {"editorial": "hip hop hits", "prefer": ("hip hop hits", "on everything: today's hip-hop hits"), "keys": ("hip hop", "hip-hop", "rap")},
     ["hip hop songs", "rap songs"]),
    ("Electronic music", _EDITORIAL, {"editorial": "electronic hits", "prefer": ("electronic hits", "chill house", "edm hits"), "keys": ("electronic", "edm", "house", "techno")},
     ["electronic music", "house music"]),
    ("Rock music", _EDITORIAL, {"editorial": "rock hits", "prefer": ("rock hits",), "keys": ("rock",)}, ["rock songs"]),
    ("Indie discoveries", _EDITORIAL, {"editorial": "indie anthems", "prefer": ("indie anthems", "indie heatwave", "ultimate indie anthems"), "keys": ("indie",)}, ["indie songs"]),
    ("R&B and soul", _EDITORIAL, {"editorial": "r&b hits", "prefer": ("biggest r&b hits", "r&b hits", "feel-good hip hop and r&b"), "keys": ("r&b", "rnb", "soul")}, ["rnb soul"]),
    ("Dance discoveries", _EDITORIAL, {"editorial": "dance hits", "prefer": ("dance hits",), "keys": ("dance", "club")}, ["dance music"]),
    ("Alternative sounds", _EDITORIAL, {"editorial": "alternative hits", "prefer": ("alternative current: hits", "alternative hits"), "keys": ("alternative", "alt")},
     ["alternative rock"]),
    ("Jazz and soul", _EDITORIAL, {"editorial": "jazz classics", "prefer": ("jazz classics", "essential jazz"), "keys": ("jazz",)}, ["jazz", "soul jazz"]),
    ("Acoustic sessions", _EDITORIAL, {"editorial": "acoustic hits", "prefer": ("acoustic hits",), "keys": ("acoustic", "unplugged")},
     ["acoustic songs"]),
    ("Ambient and instrumental", _EDITORIAL, {"editorial": "ambient focus", "prefer": ("ambient focus", "lofi loft", "deep chill"), "keys": ("ambient", "chill", "lofi", "focus")},
     ["ambient music", "instrumental chill"]),
    ("Classical essentials", _EDITORIAL, {"editorial": "classical essentials", "prefer": ("essential classical",), "keys": ("classical",)},
     ["classical piano", "orchestra classical"]),
    ("Soundtracks", _EDITORIAL, {"editorial": "soundtrack hits", "prefer": ("soundtrack hits",), "keys": ("soundtrack", "score", "film", "movie")},
     ["original soundtrack"]),
    ("World music", _EDITORIAL, {"editorial": "afrobeats now", "prefer": ("afrobeats now", "afrobeats party"), "keys": ("afro",)},
     ["world music", "afrobeats"]),
    ("Global top", _CHART, {"chart": "daily", "country": "ZZ", "not_country": "ZZ"}, []),
]

# Язык интерфейса -> страна официального чарта. Английский — мировой чарт.
_LANG_COUNTRY = {"ru": "RU", "uk": "UA", "de": "DE", "fr": "FR", "es": "ES", "pt": "BR",
                 "it": "IT", "tr": "TR", "pl": "PL", "ja": "JP", "zh": "TW", "en": "ZZ"}


def _lang() -> str:
    try:
        lang = str(storage.get_settings().get("lang") or "en")
    except Exception:
        lang = "en"
    return lang.split("-")[0].casefold()[:5] or "en"


def _country() -> str:
    try:
        region = str(storage.get_settings().get("region70") or "").strip().upper()
    except Exception:
        region = ""
    if re.fullmatch(r"[A-Z]{2}", region):
        return region
    return _LANG_COUNTRY.get(_lang(), "ZZ")


def _cold_plan() -> list[tuple[str, str, dict, list[str]]]:
    lang, country = _lang(), _country()
    out = []
    for title, subtitle, spec, queries in _COLD_START:
        if spec.get("langs") and lang not in spec["langs"]:
            continue
        if spec.get("not_country") and country == spec["not_country"]:
            continue
        out.append((title, subtitle, spec, queries))
    return out


# --- кэш каталога: чарты меняются раз в день, подборки — ещё реже ----------- #
_curated_mem: dict[str, tuple[float, list[dict]]] = {}


def _curated_file() -> str:
    return os.path.join(cache_dir(), "curated70.json")


def _spec_key(spec: dict, country: str) -> str:
    return json.dumps({k: v for k, v in spec.items() if k not in ("langs", "not_country")},
                      sort_keys=True, ensure_ascii=False) + "@" + (spec.get("country") or country)


def _curated_load(key: str) -> list[dict] | None:
    now = time.time()
    hit = _curated_mem.get(key)
    if hit and hit[0] > now:
        return hit[1]
    try:
        with open(_curated_file(), encoding="utf-8") as fh:
            data = json.load(fh)
        entry = data.get(key) if isinstance(data, dict) else None
        if isinstance(entry, dict) and float(entry.get("until") or 0) > now and isinstance(entry.get("tracks"), list):
            _curated_mem[key] = (float(entry["until"]), entry["tracks"])
            return entry["tracks"]
    except Exception:
        pass
    return None


def _curated_save(key: str, tracks: list[dict], ttl: float) -> None:
    until = time.time() + ttl
    _curated_mem[key] = (until, tracks)
    try:
        path = _curated_file()
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        now = time.time()
        data = {k: v for k, v in data.items() if isinstance(v, dict) and float(v.get("until") or 0) > now}
        data[key] = {"until": until, "tracks": tracks}
        temp = path + ".tmp"
        with open(temp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(temp, path)
    except Exception:
        pass


# Поиск редакционных плейлистов нечёткий и региональный: на «indie hits»
# приходят «Indian Indie Hits», на «r&b hits» — «Korean R&B Hits». Берём
# предпочтительные названия, затем совпадения по ключам без чужого региона.
_REGIONAL = re.compile(
    r"\b(?:indian|indonesian|korean|k-|j-|turkish|hindi|bollywood|tollywood|punjabi|tamil|telugu|"
    r"kannada|haryanvi|malayalam|bhojpuri|arabic|naija|mandopop|cantopop|french|japan\w*|i-pop|"
    r"éxitos|latino|latin|samba|sertanejo|mexican\w*|presenting|hindustani|thai|vietnam\w*|"
    r"filipino|opm|african|gospel|christmas|halloween|kids|toddler|pakistani|desi|urdu|bangla|bengali|"
    r"nepali|sinhala|persian|kurdish|greek|italian|german|spanish|dutch|polish|brazil\w*|"
    r"portuguese|chinese|taiwan\w*|malay\w*|egypt\w*|maghreb|carnatic|marathi|gujarati|odia|"
    r"pagode|forr[oó]|cumbia|corridos|banda|grupero|norteñ\w*|bachata|vallenato|dangdut|enka|"
    r"c-pop|t-pop|axé|funk\s+carioca|reggaeton|musica|música)\b",
    re.I,
)


def _pick_editorial(cards: list[dict], spec: dict) -> list[dict]:
    official = [c for c in cards if isinstance(c, dict)
                and str(c.get("artist") or "").casefold() in ("youtube music", "")]
    prefer = [str(x).casefold() for x in spec.get("prefer") or ()]
    keys = tuple(spec.get("keys") or ())
    exact = [c for c in official if str(c.get("title") or "").strip().casefold() in prefer]
    exact.sort(key=lambda c: prefer.index(str(c.get("title") or "").strip().casefold()))
    neutral = [c for c in official if not _REGIONAL.search(str(c.get("title") or ""))]
    keyed = [c for c in neutral if any(k in str(c.get("title") or "").casefold() for k in keys)]
    out, seen = [], set()
    for card in exact + keyed + neutral[:1]:
        if card["id"] not in seen:
            seen.add(card["id"])
            out.append(card)
    return out


# Готовые плейлисты для нового пользователя: эпохи и жанры, без «для сна».
_STARTER_PLAYLISTS = [
    ("the hits 80s", ("the hits: '80s", "'80s hits")),
    ("90s hits", ("the hits: '90s", "'90s hits", "90s hits")),
    ("00s hits", ("the hits: '00s", "'00s hits")),
    ("the hits 10s", ("the hits: '10s", "'10s hits")),
    ("rap classics", ("rap classics", "hip hop classics", "'00s hip hop party")),
    ("indie anthems", ("indie anthems", "ultimate indie anthems")),
    ("rock classics", ("rock classics", "classic rock", "rock anthems")),
    ("chill house", ("chill house",)),
    ("lofi loft", ("lofi loft", "lofi")),
    ("essential motown hits", ("essential motown hits",)),
    ("heavy metal", ("heavy metal workout", "metal essentials", "heavy metal")),
    ("dance hits", ("dance hits",)),
]


async def _starter_playlists(limit: int = 12) -> list[dict]:
    key = "starter-playlists@" + _country()
    cached = _curated_load(key)
    if cached is not None:
        return cached[:limit]

    async def one(query, prefer):
        cards = await ytmusic.editorial_playlists(query, 8)
        picks = _pick_editorial(cards, {"prefer": prefer, "keys": tuple(query.split()[:1])})
        return picks[0] if picks else None

    found = await asyncio.gather(*(one(q, prefer) for q, prefer in _STARTER_PLAYLISTS), return_exceptions=True)
    cards, seen = [], set()
    for card in found:
        if isinstance(card, dict) and card.get("id") not in seen:
            seen.add(card["id"])
            cards.append({**card, "kind": "playlist"})
    if len(cards) >= 4:
        _curated_save(key, cards, 24 * 3600)
    return cards[:limit]


async def _starter_albums(limit: int = 12) -> list[dict]:
    key = "new-albums@" + _country()
    cached = _curated_load(key)
    if cached is not None:
        return cached[:limit]
    cards = [{**c, "kind": "album"} for c in await ytmusic.new_albums(limit * 2)]
    if len(cards) >= 4:
        _curated_save(key, cards, 12 * 3600)
    return cards[:limit]


async def _curated(spec: dict, country: str) -> list[dict]:
    """Треки официального чарта, редакционного плейлиста или каталога песен."""
    if spec.get("chart"):
        charts = await ytmusic.chart_playlists(spec.get("country") or country)
        pid = charts.get(spec["chart"]) or charts.get("daily") or charts.get("top")
        if not pid:
            return []
        data = await ytmusic.playlist(pid, 80)
        return list((data or {}).get("tracks") or [])
    if spec.get("editorial"):
        cards = await ytmusic.editorial_playlists(spec["editorial"], 10)
        picks = _pick_editorial(cards, spec)[:2]
        chunks = await asyncio.gather(*(ytmusic.playlist(c["id"], 60) for c in picks), return_exceptions=True)
        return [t for chunk in chunks if isinstance(chunk, dict) for t in (chunk.get("tracks") or [])]
    if spec.get("songs"):
        chunks = await asyncio.gather(*(ytmusic.songs(q, 30) for q in spec["songs"]), return_exceptions=True)
        return [t for chunk in chunks if isinstance(chunk, list) for t in chunk]
    return []


async def _cold_tracks(spec: dict, queries: list[str]) -> list[dict]:
    """Стартовая полка: сначала каталог YouTube Music, потом запасной поиск."""
    tracks: list[dict] = []
    if spec and "youtube" in _user_sources():
        country = _country()
        key = _spec_key(spec, country)
        cached = _curated_load(key)
        if cached is None:
            found = await _bounded(_curated(spec, country), timeout=20)
            found = [t for t in (found if isinstance(found, list) else []) if isinstance(t, dict)]
            basis = "chart" if spec.get("chart") else "editorial" if spec.get("editorial") else "catalog"
            found = [{**t, "recommend_basis": basis} for t in found]
            if len(found) >= 8:
                _curated_save(key, found, 6 * 3600 if spec.get("chart") else 24 * 3600)
            cached = found
        tracks = list(cached)
    if len(tracks) < 12 and queries:
        tracks += await _search_many(queries, 48)
    return tracks


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").casefold() if ch.isalnum())


def _user_sources() -> list[str]:
    """Библиотеки, выбранные пользователем в настройках."""
    try:
        chosen = storage.get_settings().get("sources")
    except Exception:
        chosen = None
    if isinstance(chosen, list):
        allowed = [s for s in chosen if s in providers.ALL_SOURCES]
        if allowed:
            return allowed
    return list(providers.DEFAULT_SOURCES)


async def _search_many(queries: list[str], per: int = 48) -> list[dict]:
    sources = _user_sources()
    chunks = await asyncio.gather(
        *[_bounded(providers.search(q, limit=per, sources=sources, with_collections=False)) for q in queries],
        return_exceptions=True,
    )
    out: list[dict] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            out.extend(chunk.get("tracks") or [])
    return out


# --------------------------------------------------------------------------- #
# качество и «одна песня — одна запись»
# --------------------------------------------------------------------------- #
# Не песни: сборники на час, подкасты, SEO-заливы «новинки музыки 2026».
_NON_SONG = re.compile(
    r"(?:\b(?:podcast|подкаст|episode|эпизод|interview|интервью|audiobook|аудиокниг\w*|"
    r"full\s+album|полный\s+альбом|playlist|плейлист|сборник|подборка|compilation|"
    r"non[\s-]?stop|megamix|mega\s+mix|dj\s+set|live\s+stream|стрим|reaction|реакция|"
    r"tutorial|unboxing|trailer|трейлер|asmr|ringtone|рингтон\w*|jingle|джингл\w*|"
    r"новинки\s+(?:музыки|недели|\d{4})|лучшие\s+песни|best\s+songs\s+of|"
    r"(?:хиты|hits|музыка|music|mix|микс|top)\s+(?:19|20)\d\d|"
    r"top\s*\d{2,3}|топ\s*\d{1,3}|\d+\s*(?:hours?|hrs|час(?:а|ов)?|минут)|24\s*/\s*7)\b)",
    re.I,
)
# Производные версии: в стартовых и новых подборках их не берём, в радио —
# только если сам сид такой же версии.
_DERIVED = re.compile(
    r"\b(?:sped\s*up|speed\s*up|slowed|reverb|nightcore|daycore|8d(?:\s*audio)?|"
    r"bass\s*boost(?:ed)?|tik\s*tok\s+(?:version|remix)|cover|кавер|караоке|karaoke|минус|"
    r"perfectly\s+slowed|super\s+slowed|ultra\s+slowed)\b",
    re.I,
)
_BAD_ARTISTS = {"youtube music", "various artists", "various", "va", "unknown", "unknown artist",
                "неизвестный", "неизвестен", "сборник", "topic", "music", "музыка", "hits", "top hits",
                "new music", "radio", "радио"}
_VERSION_PART = re.compile(
    r"(?:official|video|audio|lyric|visuali[sz]er|clip|клип|премьер|mv\b|hd\b|4k|8k|remaster|remix|"
    r"ремикс|mix\b|edit\b|version|версия|sped|speed|slowed|reverb|nightcore|8d|bass|live|концерт|"
    r"acoustic|instrumental|karaoke|cover|кавер|extended|radio|explicit|clean|mono|stereo|demo|"
    r"prod\.?|session|tiktok|ver\.|(?:19|20)\d\d)",
    re.I,
)
_BRACKETS = re.compile(r"\s*[\(\[]([^\)\]]*)[\)\]]")
_FEAT = re.compile(r"\s*[\(\[]?\s*(?:feat\.?|ft\.?|featuring|при\s+уч\.?)\s[^\)\]]*[\)\]]?", re.I)
_ARTIST_SPLIT = re.compile(r"\s*(?:,|;|/|&|\+|\s(?:feat\.?|ft\.?|featuring|x|х|и|with|vs\.?)\s)\s*", re.I)


def _main_artist(name) -> str:
    """Первый исполнитель из «A, B & C feat. D» — ключ для разнообразия."""
    text = str(name or "").strip()
    head = _ARTIST_SPLIT.split(text, maxsplit=1)[0] if text else ""
    return _norm(head) or _norm(text)


def _core_title(title) -> str:
    """Название без пометок версии: клип, lyric video, sped up, remaster, feat."""
    raw = str(title or "")
    text = _FEAT.sub("", raw)
    text = _BRACKETS.sub(lambda m: "" if _VERSION_PART.search(m.group(1)) else m.group(0), text)
    for sep in (" | ", " - ", " – ", " — "):
        if sep in text:
            left, right = text.split(sep, 1)
            if left.strip() and _VERSION_PART.search(right):
                text = left
    return _norm(text) or _norm(raw)


def _identity2(track: dict) -> tuple[str, str]:
    return (_main_artist(track.get("artist")), _core_title(track.get("title")))


def _quality(track: dict, *, strict: bool = False, allow_derived: bool = False) -> tuple[float, bool]:
    """(штраф, отбросить). strict — для стартовых полок из обычного поиска."""
    title = str(track.get("title") or "")
    artist = str(track.get("artist") or "").strip()
    try:
        duration = float(track.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 1800:
        return 0.0, True   # 30+ минут — это микс или стрим, а не песня
    penalty = 0.0
    checks = (
        # Короткое (интро, шортс) опускаем вниз, но не выбрасываем: в радио
        # от трека бывают настоящие короткие песни и интерлюдии.
        (0 < duration < 40, 2.0),
        (bool(_NON_SONG.search(title)), 2.5),
        (duration > 900, 1.0),
        (artist.casefold() in _BAD_ARTISTS or not artist, 1.0),
        (len(artist) > 60 or artist.count(",") >= 3, 0.8),
        (not allow_derived and bool(_DERIVED.search(title)), 1.4),
        (title.count("|") >= 2 or "#" in title or len(title) > 90, 0.6),
    )
    for bad, cost in checks:
        if bad:
            if strict:
                return 0.0, True
            penalty += cost
    return penalty, False


_EMPTY_ACTIVITY = {"played": {}, "skips": {}, "keys": {}, "skip_keys": {}, "artists": set(), "now": 0.0}
_activity_view: dict = {}


def _activity() -> dict:
    """Локальная история для штрафов: недавно слушали, часто пропускают."""
    if not getattr(storage, "_db_path", None):
        return _EMPTY_ACTIVITY
    try:
        raw = storage.recent_activity()
    except Exception:
        return _EMPTY_ACTIVITY
    if _activity_view.get("raw") is raw:
        return _activity_view["view"]
    keys: dict = {}
    skip_keys: dict = {}
    artists: set = set()
    for tid, meta in (raw.get("tracks") or {}).items():
        key = _identity2(meta)
        keys.setdefault(key, raw["played"].get(tid, 0))
        if raw["skips"].get(tid):
            skip_keys[key] = skip_keys.get(key, 0) + raw["skips"][tid]
        if key[0]:
            artists.add(key[0])
    view = {"played": raw.get("played") or {}, "skips": raw.get("skips") or {}, "keys": keys,
            "skip_keys": skip_keys, "artists": artists, "now": raw.get("now") or time.time()}
    _activity_view.clear()
    _activity_view.update(raw=raw, view=view)
    return view


def _score(tracks: list[dict], taste: dict[str, float], played: set[str],
           blocked: set[str], base: float = 1.0, *, strict: bool = False,
           seed: dict | None = None) -> list[dict]:
    scored = []
    seen = set()
    prefs=preferences();discovery=prefs['discovery']/100
    external=_external();liked=external['liked'];external_artists={_norm(x['artist']) for x in external['artists']}
    try:hidden=set(v for v in storage.get_settings().get('search26Hidden',[]) if isinstance(v,str))
    except Exception:hidden=set()
    activity=_activity()
    allow_derived=bool(seed and _DERIVED.search(str(seed.get('title') or '')))
    total=len(tracks)

    for index, track in enumerate(tracks):
        if not isinstance(track, dict) or not track.get("id") or not track.get("title"): continue
        track = clean_track(track)
        identity = (_norm(track.get("artist")), _norm(track.get("title")))
        version = _identity2(track)
        if track["id"] in seen or identity in seen or version in seen: continue
        seen.update((track["id"], identity, version))
        artist = _norm(track.get("artist"))
        if artist in blocked or version[0] in blocked or track["id"] in hidden or "meta:"+"|".join(identity) in hidden:
            continue
        penalty, reject = _quality(track, strict=strict and not track.get("recommend_basis"), allow_derived=allow_derived)
        if reject: continue
        skips = max(activity["skips"].get(track["id"], 0), activity["skip_keys"].get(version, 0))
        if skips >= 3: continue
        value = base * (1.0 - index / (total * 2 + 1))
        familiar=track['id'] in played or identity in external['played'] or version in activity["keys"]
        weight=taste.get(artist, taste.get(version[0], 0.0))
        value += math.log1p(max(0, weight)) * (1-discovery*.6)
        value += (0.2+1.2*discovery) if not familiar else (.3-3*discovery)
        if identity in liked:value+=1.2*(1-discovery)
        value -= penalty + 1.1 * skips
        last = activity["played"].get(track["id"]) or activity["keys"].get(version)
        if last and activity["now"] - last < 3 * 3600: value -= 1.5   # только что звучал
        track['recommend_reason']='imported_favorite' if identity in liked else 'imported_artist' if artist in external_artists else 'favorite_artist' if weight>0 else 'familiar' if familiar else 'discovery'
        track['recommend_familiar']=familiar

        # Popularity counters from unrelated providers are not comparable.
        # Related-source position, taste, novelty and diversity drive ranking.
        scored.append((value, track))
    scored.sort(key=lambda pair: -pair[0])
    # Round-robin artist cap in the head, then keep the remaining candidates.
    head, tail, counts = [], [], {}
    for _, track in scored:
        artist=_main_artist(track.get("artist")) or track["id"]
        if counts.get(artist,0)>=2: tail.append(track)
        else: head.append(track);counts[artist]=counts.get(artist,0)+1
    return head + tail


def _spaced(tracks: list[dict], gap: int = 1) -> list[dict]:
    """Один исполнитель не звучит подряд, если есть из чего выбрать."""
    out: list[dict] = []
    pending = list(tracks)
    while pending:
        recent = {_main_artist(t.get("artist")) for t in out[-gap:]} if gap > 0 else set()
        for i, track in enumerate(pending):
            if _main_artist(track.get("artist")) not in recent:
                out.append(pending.pop(i))
                break
        else:
            out.append(pending.pop(0))
    return out


def _label(text: str, args: dict | None = None) -> dict:
    """Подпись полки: английский шаблон + данные для подстановки."""
    return {"text": text, "args": args or {}}


def _fill(label) -> str:
    if isinstance(label, dict):
        out = label.get("text") or ""
        for name, value in (label.get("args") or {}).items():
            out = out.replace("{" + name + "}", str(value))
        return out
    return str(label or "")


def _row_meta(title, subtitle) -> dict:
    """Поля полки для клиента.

    title/subtitle — готовый английский текст (так полка читается и без
    перевода), title_key/title_args — шаблон для перевода на клиенте.
    Подпись, которая на самом деле имя исполнителя, шаблоном не считается:
    имена переводить нельзя.
    """
    meta = {"title": _fill(title), "subtitle": _fill(subtitle)}
    if isinstance(title, dict):
        meta["title_key"] = title["text"]
        meta["title_args"] = title.get("args") or {}
    if isinstance(subtitle, dict):
        meta["subtitle_key"] = subtitle["text"]
        meta["subtitle_args"] = subtitle.get("args") or {}
    return meta


async def _row(title, subtitle, tracks: list[dict], limit: int = 60,
               kind: str = "tracks") -> dict | None:
    tracks = tracks[:limit]
    if len(tracks) < 4:
        return None
    meta = _row_meta(title, subtitle)
    return {"id": _norm(meta["title"]) or str(random.random()), **meta,
            "kind": kind, "items": tracks}


async def _wrap_cards(job, kind: str, fallback: str = "") -> dict:
    try:
        cards = await job
    except Exception:
        cards = []
    if len(cards or []) < 4 and fallback:
        return await providers.search_collections(fallback, 12)
    return {kind: cards or []}


async def _collection_rows(limit_rows: int) -> list[dict]:
    """Полки с альбомами и плейлистами, а не только с отдельными треками.

    Запросы берутся из того же вкуса, что и остальные подборки: частые
    авторы дают свои релизы, а общий жанровый запрос — готовые плейлисты.
    Если музыкальный каталог молчит, полок просто не будет.
    """
    if limit_rows <= 0:
        return []
    top = [a["artist"] for a in _top_artists(4)]
    jobs: list[asyncio.Future] = []
    plan: list[tuple] = []

    for artist in top[:2]:
        jobs.append(asyncio.ensure_future(providers.search_collections(artist, 12)))
        plan.append((_label("Albums by {artist}", {"artist": artist}),
                     _label("Releases of your artist"), "albums"))
    starter = not top and "youtube" in _user_sources()
    if starter:
        # Нового пользователя встречают редакционные плейлисты и свежие
        # альбомы каталога, а не поиск по фразе «новинки музыки 2026».
        jobs.append(asyncio.ensure_future(_wrap_cards(_starter_playlists(12), "playlists")))
    else:
        seed = top[0] if top else "hits"
        jobs.append(asyncio.ensure_future(providers.search_collections(seed, 12)))
    plan.append((_label("Playlists for you"), _label("Ready-made selections"), "playlists"))
    if len(plan) < limit_rows + 1:
        if starter:
            jobs.append(asyncio.ensure_future(_wrap_cards(_starter_albums(12), "albums",
                                                          fallback=f"new album {_YEAR}")))
        else:
            jobs.append(asyncio.ensure_future(
                providers.search_collections(f"new album {_YEAR}", 12)))
        plan.append((_label("New albums"), _label("Fresh releases"), "albums"))

    results = await asyncio.gather(*jobs, return_exceptions=True)
    rows: list[dict] = []
    seen: set[str] = set()
    for (title, subtitle, kind), found in zip(plan, results):
        if isinstance(found, Exception) or not isinstance(found, dict):
            continue
        blocked = {_norm(a) for a in storage.disliked_artists()}
        taste = {_norm(a["artist"]): a["weight"] for a in _top_artists(12)}
        items = []
        for item in (found.get(kind) or []):
            if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
                continue
            if item["id"] in seen or _norm(item.get("artist", "")) in blocked:
                continue
            if item.get("kind") not in (None, "album" if kind == "albums" else "playlist"):
                continue
            identity = (kind, _norm(item.get("artist", "")), _norm(item["title"]))
            if identity in seen:
                continue
            seen.add(identity)
            items.append({**item, "kind": "album" if kind == "albums" else "playlist"})
        items.sort(key=lambda x: -taste.get(_norm(x.get("artist", "")), 0))
        if not items:
            continue
        for item in items:
            seen.add(item["id"])
        meta = _row_meta(title, subtitle)
        rows.append({"id": "col-" + (_norm(meta["title"]) or str(random.random())),
                     **meta, "kind": kind, "items": items[:16]})
    # Reserve one shelf per collection type; frequent artists must not crowd out playlists.
    diverse = []
    for kind in ("albums", "playlists"):
        candidate = next((r for r in rows if r["kind"] == kind), None)
        if candidate:
            diverse.append(candidate)
    return (diverse + [r for r in rows if r not in diverse])[:limit_rows]


async def _artist_tracks(artist: str) -> list[dict]:
    """«Ещё от исполнителя»: только треки, где он действительно указан автором."""
    found = await _search_many([artist], 48)
    return [t for t in found if isinstance(t, dict) and artist_track_matches(t, artist)]


def _known_artists(top: list[dict], likes: list[dict]) -> set[str]:
    known = {_main_artist(a.get("artist")) for a in top}
    known.update(_main_artist(t.get("artist")) for t in likes)
    known.update(_activity()["artists"])
    try:
        known.update(_main_artist(t.get("artist")) for t in storage.history(200))
    except Exception:
        pass
    known.update(_main_artist(a.get("artist")) for a in _external().get("artists", []))
    known.discard("")
    return known


def _one_per_artist(tracks: list[dict], limit: int = 30) -> list[dict]:
    out, seen = [], set()
    for track in tracks:
        key = _main_artist(track.get("artist")) or track.get("id")
        if key in seen:
            continue
        seen.add(key)
        out.append(track)
        if len(out) >= limit:
            break
    return out


async def build_rows(limit_rows: int = 12, exclude_ids: set[str] | list[str] | None = None) -> list[dict]:
    """Главный экран: несколько персональных подборок."""
    global _cache_scope
    scope=_scope()
    if _cache_scope!=scope:_cache.clear();_cache_scope=scope
    generation=_generation
    limit_rows=max(2,min(16,int(limit_rows)))
    key = f"rows:{limit_rows}"
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]

    async with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]

        top = _top_artists(8)
        seeds = storage.recent_seed_tracks(6)
        played = storage.played_ids()
        blocked = {_norm(a) for a in storage.disliked_artists()}
        taste = {_norm(a["artist"]): a["weight"] for a in top}
        likes = storage.list_likes(60)

        rows: list[dict] = []
        jobs: list[asyncio.Future] = []
        # (заголовок, подпись, роль): роль решает строгость фильтра и порядок.
        plan: list[tuple] = []

        # 1. Продолжить слушать — сразу, без сети.
        recent = storage.history(60)
        if len(recent) >= 4:
            rows.append({
                "id": "continue",
                **_row_meta(_label("Continue listening"), _label("Recent tracks")),
                "kind": "tracks", "items": [clean_track(t) for t in recent[:60]],
                "_role": "continue",
            })

        # 1b. «На повторе» — то, что слушаешь чаще всего в последние недели.
        try:
            repeat = storage.top_tracks(30, 40)
        except Exception:
            repeat = []
        if len(repeat) >= 4:
            rows.append({
                "id": "repeat70",
                **_row_meta(_label("On repeat"), _label("Your most played lately")),
                "kind": "tracks", "items": [clean_track(t) for t in repeat],
                "_role": "repeat",
            })

        # 2. Микс на основе того, что слушали последним (реальная похожесть).
        for seed in seeds[:4]:
            jobs.append(asyncio.ensure_future(
                _bounded(providers.related(seed["id"], seed.get("artist", ""), seed.get("title", ""), 90, sources=_user_sources()))
            ))
            plan.append((_label("Similar to “{title}”", {"title": seed.get("title", "")}),
                         seed.get("artist") or _label("Personal mix"), "seed", seed))

        # 3. Liked mix (rotates across generations on manual refresh).
        if likes:
            liked = likes[_generation % len(likes)]
            jobs.append(asyncio.ensure_future(
                _bounded(providers.related(liked["id"], liked.get("artist", ""), liked.get("title", ""), 90, sources=_user_sources()))
            ))
            plan.append((_label("Because you like it"),
                         liked.get("artist") or _label("From your favourites"), "liked", liked))

        # Imported IDs belong to another service: search by musical metadata,
        # never fabricate playable IDs or related-track responses.
        imported_queries=_external().get('queries',[])[:2]
        if imported_queries:
            jobs.append(asyncio.ensure_future(_search_many(imported_queries,48)))
            plan.append((_label("From your imported music"),_label("From your music profile"), "import", None))

        # 4. Новое от авторов, которых слушаешь (строго их треки).
        for artist in [a["artist"] for a in top[:4]]:
            jobs.append(asyncio.ensure_future(_artist_tracks(artist)))
            plan.append((_label("More from {artist}", {"artist": artist}),
                         _label("An artist from your taste"), "artist", None))

        # 5. «Новые для тебя исполнители» собираются из радио сидов ниже,
        # а не из поиска по фразе «похожие исполнители».
        discovery_slot = 1 if (seeds or likes) else 0

        # 6. Холодный старт / добор, если истории мало: официальные чарты и
        # редакционные подборки, запасной путь — строгий поиск.
        need = limit_rows - len(plan) - len(rows) - discovery_slot
        if need > 0:
            for title, subtitle, spec, queries in _cold_plan()[: need + 2]:
                jobs.append(asyncio.ensure_future(_cold_tracks(spec, queries)))
                plan.append((_label(title), _label(subtitle), "cold", None))

        try:
            done,pending=await asyncio.wait(jobs,timeout=35) if jobs else (set(),set())
        except asyncio.CancelledError:
            for job in jobs:job.cancel()
            if jobs:await asyncio.gather(*jobs,return_exceptions=True)
            raise
        for job in pending:job.cancel()
        if pending:await asyncio.gather(*pending,return_exceptions=True)
        results=[job.result() if job in done and not job.cancelled() and job.exception() is None else [] for job in jobs]
        pool: list[dict] = []
        for (title, subtitle, role, seed), result in zip(plan, results):
            if isinstance(result, Exception) or not result:
                continue
            if role in ("seed", "liked"):
                pool.extend(t for t in result if isinstance(t, dict))
            ranked = _score(result, taste, played, blocked, strict=(role == "cold"), seed=seed)
            row = await _row(title, subtitle, ranked)
            if row:
                row["_role"] = role
                rows.append(row)

        if pool:
            known = _known_artists(top, likes)
            fresh = [t for t in pool if _main_artist(t.get("artist")) not in known]
            ranked = _one_per_artist(_score(fresh, taste, played, blocked), 30)
            row = await _row(_label("Artists new to you"), _label("Picked for your taste"), ranked)
            if row:
                row["_role"] = "new_artists"
                # Сразу после первой «похожей» полки: открытие нового — главное.
                at = next((i + 1 for i, r in enumerate(rows) if r.get("_role") in ("seed", "liked")), len(rows))
                rows.insert(at, row)

        # Prevent the same track/recording from filling every shelf. Уникальные
        # полки (новые исполнители, на повторе) забирают свои треки первыми.
        priority = {"continue": 0, "repeat": 1, "new_artists": 2}
        order = sorted(range(len(rows)), key=lambda i: (priority.get(rows[i].get("_role"), 5), i))
        seen_global=set();clean: dict[int, dict]={}
        excluded_set = {str(x) for x in (exclude_ids or []) if x}
        for index in order:
            row=rows[index];items=[]
            deferred=[]
            for track in row.get("items",[]):
                track=clean_track(track)
                identity=(_norm(track.get("artist")),_norm(track.get("title")))
                version=_identity2(track)
                if track.get("id") in seen_global or identity in seen_global or version in seen_global:continue
                if row.get("_role") not in ("continue", "repeat"):
                    seen_global.update((track.get("id"),identity,version))
                if excluded_set and row.get("_role") not in ("continue", "repeat") and track.get("id") in excluded_set:
                    deferred.append(track)
                else:
                    items.append(track)
            if deferred and len(items) < 8:
                items.extend(deferred)
            if len(items)>=4:clean[index]={k:v for k,v in row.items() if k!="_role"} | {"items":items[:60]}
        rows=[clean[i] for i in sorted(clean)]
        # Две полки экрана отдаём альбомам и плейлистам: раньше главная
        # состояла только из отдельных треков.
        collections = await _bounded(_collection_rows(2))
        if collections:
            head = rows[:2]
            rows = head + collections + rows[2:]
        rows=rows[:limit_rows]
        # Обложки дописываем до сохранения: тогда главная, открытая из кэша,
        # уже показывает картинки и не ждёт сеть.
        for row in rows:
            await extras.fill_thumbnails(row.get("items"))
        if generation!=_generation or scope!=_scope():return rows
        _cache[key] = (time.monotonic() + _CACHE_TTL, rows)
        _cache["rows"] = _cache[key]
        if len(rows) > 1:
            _save_rows(rows)
        return rows


async def radio(seed_track: dict | None = None, limit: int = 20) -> list[dict]:
    """Бесконечная очередь: продолжение под текущий трек и вкус."""
    played = storage.played_ids(150)
    blocked = {_norm(a) for a in storage.disliked_artists()}
    taste = {_norm(a["artist"]): a["weight"] for a in _top_artists(12)}

    tracks: list[dict] = []
    if seed_track and seed_track.get("id"):
        tracks = await providers.related(
            seed_track["id"], seed_track.get("artist", ""), seed_track.get("title", ""), limit * 2, sources=_user_sources()
        )
    if len(tracks) < limit:
        seed_artist = str((seed_track or {}).get("artist") or "").strip()
        top = [a["artist"] for a in _top_artists(4)] or _external().get("queries",[])[:2] or ([seed_artist] if seed_artist else [])
        if top:
            tracks += await _search_many([random.choice(top)], limit)

    ranked = _score(tracks, taste, played, blocked, seed=seed_track)
    return _spaced(_next_visible(ranked, seed_track))[:limit]


def _day_seed() -> str:
    return time.strftime("%Y-%m-%d") + ":" + _scope()


async def daily_mix(limit: int = 40) -> dict:
    """«Твой микс» — один длинный плейлист по вкусу на каждый день."""
    top = _top_artists(6)
    likes = storage.list_likes(20)
    seeds = [t for t in storage.recent_seed_tracks(4)]
    jobs = []
    for seed in (seeds + likes)[:4]:
        jobs.append(_bounded(providers.related(seed["id"], seed.get("artist", ""), seed.get("title", ""), 20, sources=_user_sources())))
    if top:
        jobs.append(_search_many([a["artist"] for a in top[:3]], 10))
    if _external().get("queries"):
        jobs.append(_search_many(_external()["queries"][:2],20))
    strict = not jobs
    if not jobs:
        # Истории нет: официальный чарт, а не SEO-сборники «хиты года».
        title, _subtitle, spec, queries = _cold_plan()[0]
        jobs.append(_cold_tracks(spec, queries))

    chunks = await asyncio.gather(*jobs, return_exceptions=True)
    tracks = [t for chunk in chunks if isinstance(chunk, list) for t in chunk]
    ranked = _score(
        tracks,
        {_norm(a["artist"]): a["weight"] for a in top},
        storage.played_ids(100),
        {_norm(a) for a in storage.disliked_artists()},
        strict=strict,
    )
    # Микс одного дня стабилен: обновление страницы не перетасовывает его
    # заново, а завтра порядок и состав будут другими.
    pool = ranked[:max(1, int(limit * 1.5))]
    rng = random.Random(_day_seed())
    rng.shuffle(pool)
    return {"title": "Your mix", "items": _spaced(pool[:limit])}


def invalidate() -> None:
    global _generation, _disk_invalidated
    _generation+=1
    _disk_invalidated = True
    _cache.clear()


def _next_visible(tracks: list[dict], seed: dict | None, excluded: list[str] | None = None) -> list[dict]:
    """Apply source choice, explicit dismissals and seed/dedup protection."""
    settings = storage.get_settings()
    saved = settings.get('search26Hidden', [])
    hidden = {v for v in (saved if isinstance(saved, list) else []) if isinstance(v, str)}
    hidden.update(excluded or [])
    allowed = set(_user_sources())
    seed = seed or {}
    seed_identity = (_norm(seed.get('artist')), _norm(seed.get('title')))
    seed_version = _identity2(seed) if seed.get('title') else None
    seen: set = set()
    out = []
    for track in tracks:
        if not isinstance(track, dict) or not track.get('id') or not track.get('title'):
            continue
        identity = (_norm(track.get('artist')), _norm(track.get('title')))
        version = _identity2(track)
        identity_key = 'meta:' + '|'.join(identity)
        if track['id'] == seed.get('id') or (seed.get('title') and (identity == seed_identity or version == seed_version)):
            continue
        if track['id'] in hidden or identity_key in hidden or track.get('source') not in allowed:
            continue
        if track['id'] in seen or identity in seen or version in seen:
            continue
        seen.update((track['id'], identity, version))
        out.append(track)
    return out


async def next_picks(seed: dict, excluded: list[str] | None = None, limit: int = 24) -> dict:
    """YouTube-related/taste-ranked candidates, never synthetic recommendations."""
    if not isinstance(seed, dict) or not isinstance(seed.get('id'), str) or not seed['id'].strip() or len(seed['id']) > 500:
        raise ValueError('A valid seed track is required')
    for key in ('title', 'artist'):
        if not isinstance(seed.get(key, ''), str) or len(seed.get(key, '')) > 1000:
            raise ValueError('Invalid track metadata')
    if excluded is not None and (not isinstance(excluded, list) or len(excluded) > 200 or any(not isinstance(v, str) or len(v) > 2000 for v in excluded)):
        raise ValueError('Invalid exclusions')
    tracks = await asyncio.wait_for(radio(seed, 50), timeout=22)
    familiar = storage.played_ids(1000) | {t['id'] for t in storage.list_likes(500) if t.get('id')}
    external=_external()
    items = [{**track, 'is_familiar': track['id'] in familiar or (_norm(track.get('artist')),_norm(track.get('title'))) in external['played']} for track in _next_visible(tracks, seed, excluded)[:max(1, min(40, limit))]]
    return {'items': items, 'basis': 'related_track', 'seed_id': seed['id']}

async def wave_candidates(seed: dict, excluded=None, mode='balanced', limit=8) -> dict:
    """A rolling, seed-related radio. No invented acoustic features or hit fallback."""
    if not isinstance(seed, dict) or not isinstance(seed.get('id'), str) or not seed['id'].strip() or len(seed['id']) > 500:
        raise ValueError('A valid seed track is required')
    if any(not isinstance(seed.get(k, ''), str) or len(seed.get(k, '')) > 1000 for k in ('artist','title')):
        raise ValueError('Invalid track metadata')
    if mode not in ('balanced','familiar','discover'):
        raise ValueError('Invalid wave mode')
    if excluded is not None and (not isinstance(excluded,list) or len(excluded)>200 or any(not isinstance(x,str) or len(x)>2000 for x in excluded)):
        raise ValueError('Invalid exclusions')
    sources=_user_sources()
    # Source-related order is the similarity signal; no unrelated global hits.
    candidates=await _bounded(providers.related(seed['id'],seed.get('artist',''),seed.get('title',''),48,sources=sources))
    candidates=candidates if isinstance(candidates,list) else []
    if len(candidates)<12 and seed.get('artist','').strip():
        candidates += await _search_many([seed['artist'].strip()],24)
    played=storage.played_ids(1000)
    liked={x['id'] for x in storage.list_likes(500) if x.get('id')}
    taste={_norm(x['artist']):x['weight'] for x in _top_artists(12)}
    blocked={_norm(x) for x in storage.disliked_artists()}
    ranked=_score(candidates,taste,played,blocked,seed=seed)
    visible=_next_visible(ranked,seed,excluded)
    external=_external()['played']
    for item in visible:
        item['is_familiar']=item['id'] in played|liked or (_norm(item.get('artist')),_norm(item.get('title'))) in external
        item['wave_reason']='related_track' if _norm(item.get('artist'))!=_norm(seed.get('artist')) else 'same_artist'
    # Modes bias the ranking without removing the related-source safety boundary.
    if mode!='balanced':
        visible.sort(key=lambda x: x['is_familiar'] != (mode=='familiar'))
    head,tail,counts=[],[],{}
    for item in visible:
        key=_main_artist(item.get('artist')) or item['id']
        if counts.get(key,0)>=2:tail.append(item)
        else:head.append(item);counts[key]=counts.get(key,0)+1
    return {'items':_spaced(head+tail)[:max(1,min(12,limit))], 'seed_id':seed['id'], 'mode':mode, 'basis':'source_related_and_taste'}
