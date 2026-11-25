"""YouTube Music через ytmusicapi.

Библиотека даёт музыкальный каталог YouTube без ключей и без аккаунта: поиск
только по песням (а не по случайным видео), нормальные названия, исполнители,
альбомы и длительности, радио по треку и страницы исполнителей.

Важно: ytmusicapi отдаёт ТОЛЬКО метаданные. Ссылки на аудио она не выдаёт,
их по-прежнему добывает kryonyx.youtube (Piped/Invidious) или yt-dlp.

Библиотека синхронная, поэтому все вызовы уходят в отдельный поток.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

log = logging.getLogger("kryonyx.ytmusic")

_client: Any = None
_tried = False


def _api() -> Any:
    """Ленивая инициализация: без сети и без задержки старта приложения."""
    global _client, _tried
    if _client is None and not _tried:
        _tried = True
        try:
            from ytmusicapi import YTMusic
            from . import netproxy
            _client = YTMusic(proxies=netproxy.requests_proxies())
        except Exception as exc:                     # pragma: no cover
            log.warning("[ytmusic] unavailable: %s", exc)
            _client = None
    return _client


def ready() -> bool:
    return _api() is not None


def reset() -> None:
    """Пересоздаёт клиент (после смены прокси)."""
    global _client, _tried
    _client, _tried = None, False


# Тип видео в YouTube Music: OMV — официальный клип, UGC — ролик пользователя,
# ATV — «авто-трек» из каталога с одной статичной обложкой вместо картинки.
_OMV, _UGC, _ATV = "OMV", "UGC", "ATV"


def _kind(item: dict) -> str:
    raw = str(item.get("videoType") or "").upper()
    for key in (_OMV, _UGC, _ATV):
        if raw.endswith(key):
            return key
    return ""


async def video_search(query: str, limit: int = 10) -> list[dict]:
    """Настоящие видео (а не авто-треки каталога) — кандидаты на клип."""
    query = (query or "").strip()
    if not query or not ready():
        return []
    try:
        items = await _call("search", query, filter="videos", limit=limit,
                            ignore_spelling=True)
    except Exception as exc:
        log.info("[ytmusic] video search %r: %s", query, exc)
        return []
    out = []
    for item in items or []:
        track = _track(item)
        if track:
            track["kind"] = _kind(item)
            track["views"] = item.get("views") or ""
            out.append(track)
    return out


async def counterpart(video_id: str) -> dict:
    """Что за трек у этого id: тип и официальный клип, если у песни он есть."""
    if not video_id or not ready():
        return {}
    try:
        data = await _call("get_watch_playlist", video_id, limit=1)
    except Exception as exc:
        log.info("[ytmusic] watch %s: %s", video_id, exc)
        return {}
    tracks = (data or {}).get("tracks") or []
    head = tracks[0] if tracks else {}
    twin = head.get("counterpart") or {}
    result = {"kind": _kind(head)}
    if isinstance(twin, dict) and twin.get("videoId"):
        found = _track(twin)
        if found:
            found["kind"] = _kind(twin) or _OMV
            result["video"] = found
    return result


def _seconds(value: str | None) -> int | None:
    if not value:
        return None
    parts = [p for p in re.split(r"[:]", str(value)) if p.isdigit()]
    if not parts:
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total or None


def _thumb(item: dict, vid: str = "") -> str:
    thumbs = item.get("thumbnails") or []
    if thumbs:
        best = max(thumbs, key=lambda t: (t.get("width") or 0))
        url = best.get("url")
        if url:
            # YouTube Music uses both =w60-h60-... and =s120-... forms.
            # Keep the CDN-specific suffix and only request a larger source.
            url = re.sub(r"=w\d+-h\d+", "=w720-h720", str(url))
            url = re.sub(r"=s\d+", "=s720", url)
            return url
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else ""


def _names(item: dict, key: str) -> str:
    values = item.get(key) or []
    if isinstance(values, dict):
        values = [values]
    names = [v.get("name") for v in values if isinstance(v, dict) and v.get("name")]
    return ", ".join(names)


def _artist_ref(item: dict) -> tuple[str, str]:
    """First artist name and browse/channel id from a YT Music item."""
    values = item.get("artists") or []
    if isinstance(values, dict):
        values = [values]
    for value in values:
        if not isinstance(value, dict):
            continue
        name = str(value.get("name") or "").strip()
        ident = str(value.get("id") or value.get("browseId") or "").strip()
        if name or ident:
            return name, ident
    return "", ""


def _track(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    vid = item.get("videoId")
    title = (item.get("title") or "").strip()
    if not vid or not title:
        return None
    if item.get("isAvailable") is False:
        return None
    duration = item.get("duration_seconds") or _seconds(
        item.get("duration") or item.get("length"))
    album = item.get("album")
    _artist_name, artist_id = _artist_ref(item)
    return {
        "id": "yt:" + vid,
        "title": title,
        "artist": _names(item, "artists") or "YouTube Music",
        "artists": [{"name": a.get("name"), "url": f"https://music.youtube.com/channel/{a.get('id') or a.get('browseId')}" if (a.get("id") or a.get("browseId")) else None, "source": "youtube"}
                    for a in (item.get("artists") or []) if isinstance(a, dict) and a.get("name")],
        "album": (album or {}).get("name") if isinstance(album, dict) else album,
        "duration": int(duration) if duration else None,
        "thumbnail": _thumb(item, vid),
        "source": "youtube",
        "url": f"https://www.youtube.com/watch?v={vid}",
        "views": item.get("views") if item.get("views") is not None else item.get("viewCount"),
        "stats_kind": "views",
        "author_id": artist_id or None,
        "author_url": (
            f"https://music.youtube.com/channel/{artist_id}" if artist_id else None
        ),
    }


async def _call(name: str, *args, **kwargs) -> Any:
    api = _api()
    if api is None:
        raise RuntimeError("ytmusicapi is unavailable")
    return await asyncio.to_thread(getattr(api, name), *args, **kwargs)


# --------------------------------------------------------------------------- #
# поиск
# --------------------------------------------------------------------------- #
def _kind72(item: dict) -> str:
    kind = _kind(item)
    if kind == _ATV or item.get("resultType") == "song":
        return "song"
    return {"OMV": "omv", "UGC": "ugc"}.get(kind, "")


async def search(query: str, limit: int = 25) -> list[dict]:
    """Песни по запросу: каталог, клипы и «лучший результат» вместе.

    v72: раньше видео запрашивались только если песен не хватило, поэтому
    треки, которые есть на YouTube лишь роликом, не находились вовсе, а
    автоисправление запроса подменяло редкие названия популярными. Теперь три
    запроса идут параллельно: песни (точно как введено), видео и общий поиск
    с «лучшим результатом» (он исправляет опечатки). Если точный поиск песен
    слабый, добираем песни с исправлением. У каждого трека остаются сигналы
    каталога (_rank72) — по ним search_rank72 ставит оригинал первым.
    """
    query = (query or "").strip()
    if not query or not ready():
        return []
    # One page (20) of songs answers the first screen; deeper pages ask more.
    want = 20 if limit <= 40 else limit - 10
    jobs = (
        _call("search", query, limit=20, ignore_spelling=False),
        _call("search", query, filter="songs", limit=want, ignore_spelling=True),
        _call("search", query, filter="videos", limit=min(40, max(20, want // 2)), ignore_spelling=True),
    )
    found = list(await asyncio.gather(*jobs, return_exceptions=True))
    # v73: one failed sub-query (a transient "blocked"/timeout) used to leave
    # the catalogue songs out — the original vanished from the first screen and
    # that partial list was cached for 15 minutes. Retry the failed ones once;
    # if songs still fail, the rows are marked degraded and cached briefly.
    failed = [i for i, chunk in enumerate(found) if isinstance(chunk, Exception)]
    if failed:
        await asyncio.sleep(0.35)
        again = (
            lambda: _call("search", query, limit=20, ignore_spelling=False),
            lambda: _call("search", query, filter="songs", limit=want, ignore_spelling=True),
            lambda: _call("search", query, filter="videos", limit=min(40, max(20, want // 2)), ignore_spelling=True),
        )
        retried = await asyncio.gather(*(again[i]() for i in failed), return_exceptions=True)
        for i, chunk in zip(failed, retried):
            found[i] = chunk
    for name, chunk in zip(("top", "songs", "videos"), found):
        if isinstance(chunk, Exception):
            log.warning("[ytmusic] search %s (%s): %s", query, name, chunk)
    degraded = isinstance(found[1], Exception)
    top, songs, videos = [c if isinstance(c, list) else [] for c in found]
    from .search_rank72 import relevance
    exact = [t for t in (_track(i) for i in songs[:8]) if t]
    if len(exact) < 5 or max((relevance(query, t) for t in exact), default=0) < 75:
        try:
            corrected = await _call("search", query, filter="songs", limit=want, ignore_spelling=False)
        except Exception as exc:
            log.info("[ytmusic] corrected songs %s: %s", query, exc)
            corrected = []
        seen_ids = {i.get("videoId") for i in songs}
        songs = songs + [i for i in corrected or [] if i.get("videoId") not in seen_ids]
    out: list[dict] = []
    feats: dict[str, dict] = {}
    rows: dict[str, dict] = {}
    top_artist = ""

    def add(item: dict, **signal) -> None:
        track = _track(item)
        if not track:
            return
        f = feats.get(track["id"])
        if f is None:
            f = feats[track["id"]] = {"kind": _kind72(item)}
            track["_rank72"] = f
            rows[track["id"]] = track
            out.append(track)
        else:
            # The mixed «Top result» list omits durations and albums; the
            # songs list has them — fill gaps from whichever list has them.
            known = rows[track["id"]]
            for key in ("duration", "album", "views", "author_id", "author_url"):
                if not known.get(key) and track.get(key):
                    known[key] = track[key]
            if not f.get("kind"):
                f["kind"] = _kind72(item)
        for key, value in signal.items():
            if key in ("pos", "vpos", "mixed"):
                f[key] = min(f.get(key, value), value)
            else:
                f[key] = f.get(key) or value
        from .search_rank72 import plays
        count = plays(item.get("views"))
        if count > (f.get("plays") or 0):
            f["plays"] = count

    for index, item in enumerate(top):
        kind = item.get("resultType")
        if item.get("category") == "Top result":
            if kind in ("song", "video"):
                add(item, top=True)
            elif kind == "artist" and not top_artist:
                top_artist = str(item.get("artist") or _names(item, "artists") or "").strip()
        elif kind in ("song", "video"):
            add(item, mixed=index)
    for index, item in enumerate(songs):
        add(item, pos=index)
    for index, item in enumerate(videos):
        add(item, vpos=index)
    if top_artist:
        for track in out:
            track["_rank72"]["top_artist_name"] = top_artist
    if degraded:
        for track in out:
            track["_rank72"]["degraded"] = True
    return out


class IncompleteSearchResults(list):
    """A usable partial list that must not be cached as a complete result."""
    degraded = True


async def artists(query: str, limit: int = 8) -> list[dict]:
    """Карточки исполнителей для страницы поиска."""
    query = (query or "").strip()
    if not query:
        return []
    if not ready():
        return IncompleteSearchResults()
    try:
        items = await _call("search", query, filter="artists", limit=limit)
    except Exception as exc:
        log.warning("[ytmusic] artists %s: %s", query, exc)
        return IncompleteSearchResults()
    out = []
    for item in items or []:
        name = (item.get("artist") or "").strip()
        browse = item.get("browseId")
        if not name or not browse:
            continue
        out.append({
            "id": browse,
            "name": name,
            "url": f"https://music.youtube.com/channel/{browse}",
            # The UI consumes `thumbnail`; keep `picture` for older callers.
            "thumbnail": _thumb(item),
            "picture": _thumb(item),
            "source": "youtube",
        })
    return out[:limit]


async def radio(video_id: str, limit: int = 25) -> list[dict]:
    """Официальное радио YouTube Music по треку — база для рекомендаций."""
    if not video_id or not ready():
        return []
    try:
        data = await _call("get_watch_playlist", videoId=video_id,
                           limit=max(limit + 5, 25), radio=True)
    except Exception as exc:
        log.warning("[ytmusic] radio %s: %s", video_id, exc)
        return []
    out = []
    for item in (data or {}).get("tracks") or []:
        track = _track(item)
        if track and track["id"] != "yt:" + video_id:
            out.append(track)
    return out[:limit]


async def channel(url_or_id: str, limit: int = 30) -> list[dict]:
    """Треки исполнителя по ссылке на канал или browseId."""
    ident = (url_or_id or "").rstrip("/").split("/")[-1]
    if not ident or not ready():
        return []
    try:
        data = await _call("get_artist", ident)
    except Exception as exc:
        log.warning("[ytmusic] artist %s: %s", ident, exc)
        return []
    picture = _thumb(data or {})
    out: list[dict] = []
    seen: set[str] = set()
    for key in ("songs", "videos"):
        block = (data or {}).get(key) or {}
        for item in block.get("results") or []:
            track = _track(item)
            if track and track["id"] not in seen:
                seen.add(track["id"])
                if picture:
                    track["author_thumbnail"] = picture
                out.append(track)
    return out[:limit]


async def suggestions(query: str, limit: int = 8) -> list[str]:
    query = (query or "").strip()
    if not query or not ready():
        return []
    try:
        items = await _call("get_search_suggestions", query)
    except Exception:
        return []
    return [str(i) for i in (items or []) if isinstance(i, str)][:limit]


# --------------------------------------------------------------------------- #
# альбомы и плейлисты
# --------------------------------------------------------------------------- #
ALBUM_PREFIX = "ytalbum:"
PLAYLIST_PREFIX = "ytplaylist:"


def _playlist_id(item: dict) -> str:
    """playlistId из элемента поиска: у плейлистов браузерный id идёт с VL."""
    value = str(item.get("playlistId") or "").strip()
    if value:
        return value
    browse = str(item.get("browseId") or "").strip()
    return browse[2:] if browse.startswith("VL") else browse


def _collection(item: dict, kind: str) -> dict | None:
    """Карточка альбома или плейлиста в том же виде, что карточка трека."""
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    if kind == "album":
        browse = str(item.get("browseId") or "").strip()
        if not browse:
            return None
        ident = ALBUM_PREFIX + browse
        artist = _names(item, "artists") or _names(item, "author") or "YouTube Music"
    else:
        plid = _playlist_id(item)
        if not plid:
            return None
        ident = PLAYLIST_PREFIX + plid
        artist = (_names(item, "author") or str(item.get("author") or "")
                  or "YouTube Music")
    count = item.get("itemCount") or item.get("trackCount") or item.get("views")
    try:
        count = int(str(count).split()[0].replace(",", "")) if count else None
    except (TypeError, ValueError):
        count = None
    card = {
        "id": ident,
        "kind": kind,
        "title": title,
        "artist": artist,
        "year": str(item.get("year") or "").strip() or None,
        "count": count,
        "thumbnail": _thumb(item),
        "source": "youtube",
    }
    if kind == "album":
        # «Album», «EP» или «Single» — по нему решаем, надо ли уточнять число треков.
        card["release"] = str(item.get("type") or item.get("resultType") or "").strip()
    return card


async def _search_collections(query: str, flt: str, kind: str,
                              limit: int) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    if not ready():
        return IncompleteSearchResults()
    try:
        items = await _call("search", query, filter=flt, limit=max(limit, 10))
    except Exception as exc:
        log.warning("[ytmusic] %s %s: %s", flt, query, exc)
        return IncompleteSearchResults()
    out: list[dict] = []
    seen: set[str] = set()
    for item in items or []:
        card = _collection(item, kind)
        if card and card["id"] not in seen:
            seen.add(card["id"])
            out.append(card)
    return out[:limit]


# Сколько треков в релизе: browseId -> число. Релизы не меняются, поэтому
# кэш живёт до перезапуска (и ограничен по размеру).
_album_sizes: dict[str, int] = {}
MIN_ALBUM_TRACKS = 2


async def _album_size(card: dict, gate: asyncio.Semaphore) -> int | None:
    ident = card["id"].removeprefix(ALBUM_PREFIX)
    if ident in _album_sizes:
        return _album_sizes[ident]
    async with gate:
        try:
            data = await asyncio.wait_for(_call("get_album", ident), 6.0)
        except Exception as exc:
            log.debug("[ytmusic] album size %s: %s", ident, exc)
            return None
    data = data or {}
    size = data.get("trackCount")
    try:
        size = int(size) if size is not None else len(data.get("tracks") or [])
    except (TypeError, ValueError):
        size = len(data.get("tracks") or [])
    if len(_album_sizes) > 2000:
        _album_sizes.clear()
    _album_sizes[ident] = size
    return size


async def albums(query: str, limit: int = 10) -> list[dict]:
    """Альбомы по запросу — только релизы хотя бы из двух треков.

    Поиск каталога по «albums» отдаёт и синглы из одной песни: на полке
    «Альбомы» они выглядели как альбомы, а внутри был один трек — тот же,
    что уже стоит в списке треков. Число треков в выдаче поиска не приходит,
    поэтому для синглов (и релизов неизвестного типа) уточняем его отдельным
    запросом. Полноформатные альбомы и EP пропускаем без проверки.
    """
    found = await _search_collections(query, "albums", "album", max(limit * 2, 20))
    if getattr(found, "degraded", False):
        return found
    gate = asyncio.Semaphore(6)

    async def size_of(card: dict) -> int | None:
        if card.get("count"):
            return card["count"]
        release = (card.get("release") or "").casefold()
        if release in ("album", "ep", "альбом", "мини-альбом"):
            return None                         # заведомо не один трек
        return await _album_size(card, gate)

    sizes = await asyncio.gather(*(size_of(card) for card in found))
    out: list[dict] = []
    for card, size in zip(found, sizes):
        release = (card.get("release") or "").casefold()
        if size is None:
            # Не узнали — синглу не верим, альбом/EP оставляем.
            if release in ("single", "сингл"):
                continue
        elif size < MIN_ALBUM_TRACKS:
            continue
        else:
            card["count"] = size
        out.append(card)
        if len(out) >= limit:
            break
    return out


async def playlists(query: str, limit: int = 10) -> list[dict]:
    """Готовые плейлисты сервиса и слушателей."""
    def big(items: list[dict]) -> list[dict]:
        # Плейлист из одного трека — тот же трек, что уже есть в выдаче.
        return [item for item in items
                if not item.get("count") or item["count"] >= MIN_ALBUM_TRACKS]

    primary = await _search_collections(query, "playlists", "playlist", limit)
    found = big(primary)
    if len(found) >= max(3, limit // 2):
        return IncompleteSearchResults(found) if getattr(primary, "degraded", False) else found
    secondary = await _search_collections(query, "community_playlists", "playlist", limit)
    extra = big(secondary)
    seen = {item["id"] for item in found}
    result = (found + [item for item in extra if item["id"] not in seen])[:limit]
    if getattr(primary, "degraded", False) or getattr(secondary, "degraded", False):
        return IncompleteSearchResults(result)
    return result


def _album_track(item: dict, album: str, artist: str, cover: str) -> dict | None:
    track = _track(item)
    if not track:
        return None
    if not track.get("album"):
        track["album"] = album
    if not track.get("thumbnail"):
        track["thumbnail"] = cover
    if artist and (not track.get("artist") or track["artist"] == "YouTube Music"):
        track["artist"] = artist
    return track


async def album(browse_id: str, limit: int | None = None) -> dict:
    """Содержимое альбома: обложка, исполнитель и список треков."""
    ident = str(browse_id or "").removeprefix(ALBUM_PREFIX).strip()
    if not ident or not ready():
        raise RuntimeError("YouTube Music is unavailable")
    data = await _call("get_album", ident)
    data = data or {}
    cover = _thumb(data)
    artist = _names(data, "artists") or "YouTube Music"
    name = str(data.get("title") or "").strip() or "Album"
    tracks = [t for t in (_album_track(item, name, artist, cover)
                          for item in (data.get("tracks") or [])) if t]
    return {
        "id": ALBUM_PREFIX + ident,
        "kind": "album",
        "title": name,
        "artist": artist,
        "year": str(data.get("year") or "").strip() or None,
        "thumbnail": cover,
        "source": "youtube",
        "tracks": tracks[:limit],
    }


async def playlist(playlist_id: str, limit: int | None = None) -> dict:
    """Содержимое плейлиста."""
    ident = str(playlist_id or "").removeprefix(PLAYLIST_PREFIX).strip()
    if ident.startswith("VL"):
        ident = ident[2:]
    if not ident or not ready():
        raise RuntimeError("YouTube Music is unavailable")
    data = await _call("get_playlist", ident, limit=None if limit is None else max(limit, 25))
    data = data or {}
    cover = _thumb(data)
    tracks = [t for t in (_track(item) for item in (data.get("tracks") or [])) if t]
    for track in tracks:
        if not track.get("thumbnail"):
            track["thumbnail"] = cover
    author = data.get("author")
    if isinstance(author, dict):
        author = author.get("name")
    return {
        "id": PLAYLIST_PREFIX + ident,
        "kind": "playlist",
        "title": str(data.get("title") or "").strip() or "Playlist",
        "artist": str(author or "YouTube Music"),
        "count": data.get("trackCount") or len(tracks),
        "thumbnail": cover,
        "source": "youtube",
        "tracks": tracks[:limit],
    }


# --------------------------------------------------------------------------- #
# официальные чарты и редакционные подборки (холодный старт главной)
# --------------------------------------------------------------------------- #
async def chart_playlists(country: str = "ZZ") -> dict[str, str]:
    """Плейлисты официальных чартов страны: daily, trending, top, live.

    get_charts отдаёт карточки «Daily Top Music Videos», «Trending 20» и
    «Top 100 Music Videos» — реальные чарты YouTube, а не поиск по слову «хиты».
    """
    if not ready():
        return {}
    country = (str(country or "ZZ").strip().upper() or "ZZ")[:2]
    try:
        data = await _call("get_charts", country)
    except Exception as exc:
        log.info("[ytmusic] charts %s: %s", country, exc)
        return {}
    out: dict[str, str] = {}
    for item in (data or {}).get("videos") or []:
        if not isinstance(item, dict):
            continue
        pid = _playlist_id(item)
        low = str(item.get("title") or "").casefold()
        if not pid or not low:
            continue
        if "live" in low:
            out.setdefault("live", pid)
        elif low.startswith("trending"):
            out.setdefault("trending", pid)
        elif "daily top" in low:
            out.setdefault("daily", pid)
        elif low.startswith("top 100"):
            out.setdefault("top", pid)
    return out


async def editorial_playlists(query: str, limit: int = 8) -> list[dict]:
    """Редакционные плейлисты YouTube Music («featured playlists»)."""
    query = (query or "").strip()
    if not query or not ready():
        return []
    try:
        items = await _call("search", query, filter="featured_playlists", limit=max(limit, 10))
    except Exception as exc:
        log.info("[ytmusic] featured %s: %s", query, exc)
        return []
    out = []
    for item in items or []:
        card = _collection(item, "playlist")
        if card:
            out.append(card)
    return out[:limit]


async def new_albums(limit: int = 16) -> list[dict]:
    """Новые альбомы и EP из раздела «Обзор» (синглы на полку альбомов не идут)."""
    if not ready():
        return []
    try:
        data = await _call("get_explore")
    except Exception as exc:
        log.info("[ytmusic] explore: %s", exc)
        return []
    items = (data or {}).get("new_releases") or []
    if isinstance(items, dict):
        items = items.get("items") or []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").casefold() not in ("album", "ep"):
            continue
        card = _collection(item, "album")
        if card:
            out.append(card)
    return out[:limit]


async def songs(query: str, limit: int = 30) -> list[dict]:
    """Только каталожные песни (без роликов): чистая выдача для подборок."""
    query = (query or "").strip()
    if not query or not ready():
        return []
    try:
        items = await _call("search", query, filter="songs", limit=max(limit, 20),
                            ignore_spelling=True)
    except Exception as exc:
        log.info("[ytmusic] songs %s: %s", query, exc)
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in items or []:
        track = _track(item)
        if track and track["id"] not in seen:
            seen.add(track["id"])
            out.append(track)
    return out[:limit]


def status() -> dict:
    return {"ready": ready()}
