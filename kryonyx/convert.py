"""
convert.py — перенос плейлистов из Spotify, YouTube и SoundCloud.

Ссылку читаем публично, без ключей и без входа в аккаунт:

  * Spotify    — страница embed (`open.spotify.com/embed/...`) отдаёт JSON
                 со списком треков: название, исполнитель, длительность;
  * YouTube    — yt-dlp в «плоском» режиме, запасной вариант Piped/Invidious;
  * SoundCloud — yt-dlp, запасной вариант — разбор `window.__sc_hydration`.

Дальше каждый трек ищется в подключённых библиотеках плеера (YouTube,
SoundCloud, Audius, Bandcamp, Jamendo, Internet Archive) и получает оценку
совпадения по названию, исполнителю и длительности. Совпавшие треки можно
сохранить в обычный плейлист Kryonyx.

Работа идёт задачами: интерфейс запускает задачу, опрашивает прогресс и в
конце сохраняет результат, поэтому длинные плейлисты не упираются в таймаут.
"""

from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import re
import time
import threading
import unicodedata
import urllib.parse
import uuid
from difflib import SequenceMatcher
from typing import Any, Iterable

from . import library, plugins, providers, storage

log = logging.getLogger(__name__)

MAX_ITEMS = None                # no application-level track count limit
# Параллельных поисков при сопоставлении. Каждый поиск сам расходится по
# нескольким библиотекам, поэтому число небольшое: восемь — это примерно
# три трека в секунду, и при этом сервисы не начинают отдавать 429.
MATCH_CONCURRENCY = 8
GOOD_SCORE = 0.62               # уверенное совпадение
WEAK_SCORE = 0.42               # показываем, но помечаем «проверьте»
JOB_TTL = 30 * 60

SERVICES: tuple[dict, ...] = (
    {"id": "spotify", "name": "Spotify", "example": "https://open.spotify.com/playlist/…"},
    {"id": "youtube", "name": "YouTube", "example": "https://youtube.com/playlist?list=…"},
    {"id": "soundcloud", "name": "SoundCloud", "example": "https://soundcloud.com/user/sets/…"},
    {"id": "deezer", "name": "Deezer", "example": "https://www.deezer.com/playlist/…"},
)

# Какой плагин отвечает за чтение ссылки этого сервиса.
SERVICE_PLUGIN = {
    "spotify": "spotify-import",
    "youtube": "youtube-import",
    "soundcloud": "soundcloud-import",
}


# --------------------------------------------------------------------------- #
# разбор ссылки
# --------------------------------------------------------------------------- #
_SPOTIFY_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?|spotify:)"
    r"(track|album|playlist)[:/]([A-Za-z0-9]{10,40})", re.I)
_YT_LIST_RE = re.compile(r"[?&]list=([A-Za-z0-9_-]{10,60})")
_YT_VIDEO_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/|embed/))([A-Za-z0-9_-]{11})")
_SC_SET_RE = re.compile(r"soundcloud\.com/([\w.-]+)/sets/([\w.-]+)", re.I)
_SC_TRACK_RE = re.compile(r"soundcloud\.com/([\w.-]+)/([\w.-]+)", re.I)


def parse_link(url: str) -> dict | None:
    """Определяет сервис и тип ссылки. None — ссылку не понимаем."""
    url = (url or "").strip()
    if not url:
        return None

    if not url.lower().startswith("spotify:"):
        checked = urllib.parse.urlparse(url)
        hosts = {"open.spotify.com", "youtube.com", "www.youtube.com", "music.youtube.com",
                 "m.youtube.com", "youtu.be", "soundcloud.com", "www.soundcloud.com",
                 "deezer.com", "www.deezer.com"}
        if checked.scheme not in {"https", "http"} or checked.hostname not in hosts:
            return None
        if checked.username or checked.password:
            return None
        try:
            if checked.port not in {None, 80, 443}:
                return None
        except ValueError:
            return None

    # Strict host/path parsing: no arbitrary endpoints or redirect-following.
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in {"https", "http"} and parsed.hostname in {"deezer.com", "www.deezer.com"}:
        found = re.fullmatch(r"/(?:[a-z]{2}/)?(playlist|album|track)/(\d+)/?", parsed.path)
        if found:
            return {"service": "deezer", "type": found[1], "id": found[2],
                    "url": f"https://www.deezer.com/{found[1]}/{found[2]}"}
        return None

    found = _SPOTIFY_RE.search(url)
    if found:
        kind = found.group(1).lower()
        return {"service": "spotify", "type": kind, "id": found.group(2),
                "url": f"https://open.spotify.com/{kind}/{found.group(2)}"}

    if "youtube.com" in url or "youtu.be" in url:
        found = _YT_LIST_RE.search(url)
        if found and not found.group(1).startswith("RD"):
            return {"service": "youtube", "type": "playlist", "id": found.group(1),
                    "url": f"https://www.youtube.com/playlist?list={found.group(1)}"}
        found = _YT_VIDEO_RE.search(url)
        if found:
            return {"service": "youtube", "type": "track", "id": found.group(1),
                    "url": f"https://www.youtube.com/watch?v={found.group(1)}"}
        return None

    if "soundcloud.com" in url:
        found = _SC_SET_RE.search(url)
        if found:
            return {"service": "soundcloud", "type": "playlist",
                    "id": f"{found.group(1)}/sets/{found.group(2)}",
                    "url": f"https://soundcloud.com/{found.group(1)}/sets/{found.group(2)}"}
        found = _SC_TRACK_RE.search(url)
        if found and found.group(2) not in {"sets", "tracks", "likes", "reposts"}:
            return {"service": "soundcloud", "type": "track",
                    "id": f"{found.group(1)}/{found.group(2)}",
                    "url": f"https://soundcloud.com/{found.group(1)}/{found.group(2)}"}
        return None

    return None


# --------------------------------------------------------------------------- #
# чтение исходного плейлиста
# --------------------------------------------------------------------------- #
def _plain(text: str) -> str:
    """Убирает неразрывные пробелы и лишние отступы: Spotify отдаёт список
    исполнителей через «,\xa0», и такой запрос ломает поиск в Internet Archive."""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _item(title: str, artist: str = "", duration_ms: int | None = None,
          album: str = "", url: str = "", thumbnail: str = "") -> dict | None:
    title = _plain(title)
    if not title:
        return None
    return {
        "title": title,
        "artist": _plain(artist),
        "album": _plain(album),
        "duration": round(duration_ms / 1000) if duration_ms else None,
        "url": url,
        "thumbnail": thumbnail,
    }


async def _text(url: str, timeout: float = 20.0) -> str:
    session = await library.http()
    import aiohttp
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) KryonyxMusic",
               "Accept-Language": "en"}
    async with session.get(url, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return await resp.text()


# ------------------------------------------------------------------ Spotify --
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.S)
_OG_DESC_RE = re.compile(
    r'<meta\s+property="og:description"\s+content="([^"]*)"', re.I)

# Публичная embed-страница отдаёт максимум 50 треков плейлиста и trackCount
# больше не присылает, поэтому настоящий размер из неё не узнать: ровно
# пятьдесят строк считаем признаком обрезанного списка.
SPOTIFY_EMBED_LIMIT = 50


def _spotify_payload(html: str) -> dict:
    """__NEXT_DATA__ embed-страницы. Ошибку страницы превращаем в понятный текст."""
    found = _NEXT_DATA_RE.search(html)
    if not found:
        raise RuntimeError("Spotify did not return page data — "
                           "the link may be wrong or Spotify changed the page")
    try:
        payload = json.loads(found.group(1))
    except Exception as exc:
        raise RuntimeError(f"could not read the Spotify page data: {exc}") from exc
    props = ((payload.get("props") or {}).get("pageProps") or {})
    status = props.get("status")
    if status and int(status) >= 400:
        # 404 приходит и на закрытый плейлист, и на удалённый — текст один.
        raise RuntimeError(
            "Spotify does not open this link: the playlist or album is private, "
            "region-locked or deleted. Only public links can be imported.")
    return payload


def _spotify_entity(payload: dict) -> dict:
    """Сущность ссылки: сначала обычное место, потом поиск по дереву.

    Структура embed-страницы уже менялась несколько раз, поэтому кладём оба
    пути: прямой (props.pageProps.state.data.entity) и обход дерева.
    """
    direct = (((payload.get("props") or {}).get("pageProps") or {})
              .get("state") or {}).get("data") or {}
    entity = direct.get("entity")
    if isinstance(entity, dict) and (entity.get("trackList") or entity.get("name")
                                     or entity.get("title")):
        return entity

    stack: list[Any] = [payload]
    best: dict = {}
    single: dict = {}
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if isinstance(node.get("trackList"), list) and node["trackList"]:
                if len(node["trackList"]) > len(best.get("trackList") or []):
                    best = node
            elif not single and node.get("uri") and (node.get("title") or node.get("name")) \
                    and node.get("duration"):
                single = node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return best or single


def _spotify_cover(entity: dict) -> str:
    """Обложка: coverArt (плейлисты) или visualIdentity (треки и альбомы)."""
    art = entity.get("coverArt") or {}
    best, area = "", -1
    for source in (art.get("sources") or []):
        url = source.get("url") or ""
        size = (source.get("width") or 0) * (source.get("height") or 0)
        if url and size >= area:
            best, area = url, size
    if best:
        return best
    for image in ((entity.get("visualIdentity") or {}).get("image") or []):
        url = image.get("url") or ""
        size = (image.get("maxWidth") or 0) * (image.get("maxHeight") or 0)
        if url and size >= area:
            best, area = url, size
    return best


def _spotify_artists(node: dict) -> str:
    """Исполнители: список artists (страница трека) или строка subtitle."""
    artists = node.get("artists")
    if isinstance(artists, list) and artists:
        names = [str(a.get("name") or "") for a in artists if isinstance(a, dict)]
        names = [n for n in names if n]
        if names:
            return ", ".join(names)
    return str(node.get("subtitle") or "")


def _spotify_track_url(node: dict) -> str:
    uri = str(node.get("uri") or "")
    ident = str(node.get("id") or "") or (uri.split(":")[-1] if uri else "")
    return f"https://open.spotify.com/track/{ident}" if ident else ""


async def _spotify_album_name(link: dict) -> str:
    """Название альбома для одиночного трека.

    В embed-данных трека альбома нет, а он нужен и для подбора, и для карточки
    Discord. Берём его из og:description обычной страницы: там формат
    «Исполнитель · Альбом · Song · Год».
    """
    try:
        html = await _text(f"https://open.spotify.com/track/{link['id']}", timeout=15)
    except Exception as exc:
        log.debug("[convert] spotify album lookup failed: %s", exc)
        return ""
    found = _OG_DESC_RE.search(html)
    if not found:
        return ""
    parts = [p.strip() for p in found.group(1).split("·")]
    return parts[1] if len(parts) >= 3 else ""


async def _spotify_playlist_pages(link: dict, fallback: dict) -> dict:
    from . import spotify
    items, offset, signatures = [], 0, set()
    total = fallback.get("total", 0)
    partial = False
    try:
        while True:
            response = await spotify._query("fetchPlaylistContents", {
                "uri": "spotify:playlist:" + link["id"], "offset": offset, "limit": 100})
            playlist = (response.get("data") or {}).get("playlistV2") or {}
            content = playlist.get("content") or {}
            rows = content.get("items") or []
            expected = content.get("totalCount")
            if isinstance(expected, int): total = expected
            signature = json.dumps(rows, sort_keys=True)
            if not rows or signature in signatures:
                partial = bool(rows) or bool(total and offset < total)
                break
            signatures.add(signature)
            for row in rows:
                wrapper = row.get("itemV2") or row.get("item") or {}
                track = spotify._track(wrapper.get("data") or wrapper)
                if not track: continue
                made = _item(track["title"], track["artist"],
                             (track.get("duration") or 0) * 1000,
                             album=track.get("album") or "", url=track.get("url") or "",
                             thumbnail=track.get("thumbnail") or "")
                if made: items.append(made)
            offset += len(rows)
            if (isinstance(expected, int) and offset >= expected) or len(rows) < 100: break
    except Exception as exc:
        log.warning("[convert] Spotify full playlist unavailable: %s", exc)
        partial = True
    if len(items) < len(fallback["items"]): return fallback
    return {**fallback, "items": items, "total": max(int(total or 0), len(items)),
            "truncated": partial or len(items) < (total or offset)}


async def _fetch_spotify(link: dict) -> dict:
    html = await _text(f"https://open.spotify.com/embed/{link['type']}/{link['id']}")
    entity = _spotify_entity(_spotify_payload(html))
    if not entity:
        raise RuntimeError("Spotify returned no track data for this link")

    rows = entity.get("trackList")
    album_name = entity.get("name") or entity.get("title") or ""
    single = not isinstance(rows, list) or not rows
    if single:
        # Ссылка на один трек: трек-лист на такой странице больше не приходит,
        # все данные лежат прямо в сущности.
        rows = [entity]
        album_name = await _spotify_album_name(link) if link["type"] == "track" else album_name

    cover = _spotify_cover(entity)
    items: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        made = _item(row.get("title") or row.get("name") or "",
                     _spotify_artists(row),
                     row.get("duration"),
                     album=album_name if link["type"] in ("album", "track") else "",
                     url=_spotify_track_url(row),
                     thumbnail=cover)
        if made:
            items.append(made)
    if not items:
        raise RuntimeError("Spotify returned no tracks for this link "
                           "(is the playlist private?)")

    name = entity.get("name") or entity.get("title") or "Spotify playlist"
    total = entity.get("trackCount") or entity.get("totalCount") or len(items)
    result = {
        "name": name,
        "author": (_spotify_artists(entity) or "") if link["type"] != "track" else "",
        "cover": cover,
        "items": items[:MAX_ITEMS],
        "total": int(total) if isinstance(total, (int, float)) else len(items),
        "truncated": link["type"] == "playlist" and len(items) >= SPOTIFY_EMBED_LIMIT,
    }
    if link["type"] == "playlist" and result["truncated"]:
        return await _spotify_playlist_pages(link, result)
    return result



# ------------------------------------------------------------------ YouTube --
async def _fetch_youtube_flat(link: dict) -> dict:
    opts = {**providers._FLAT_OPTS, "noplaylist": False}
    opts.pop("playlistend", None)
    info = await providers._aextract(link["url"], opts)
    entries = [e for e in ((info or {}).get("entries") or []) if e]
    if not entries and info and info.get("title"):
        entries = [info]
    items: list[dict] = []
    for entry in entries:
        duration = entry.get("duration")
        made = _item(entry.get("title") or "",
                     entry.get("artist") or entry.get("uploader")
                     or entry.get("channel") or "",
                     int(duration * 1000) if duration else None,
                     album=entry.get("album") or "",
                     url=entry.get("url") or entry.get("webpage_url") or "",
                     thumbnail=(entry.get("thumbnails") or [{}])[-1].get("url", ""))
        if made:
            items.append(made)
    if not items:
        raise RuntimeError("the playlist is empty or private")
    return {
        "name": (info or {}).get("title") or "YouTube playlist",
        "author": (info or {}).get("uploader") or (info or {}).get("channel") or "",
        "cover": "",
        "items": items,
        "total": (info or {}).get("playlist_count") or len(items),
    }


async def _fetch_youtube_api(link: dict) -> dict:
    """Read all public pages; repeated cursors and failed pages are partial, not success."""
    from . import youtube as yt
    last = None
    for piped in (True, False):
        items, seen, partial = [], set(), False
        data = {}
        first = {}
        try:
            path = f"/playlists/{link['id']}" if piped else f"/api/v1/playlists/{link['id']}"
            data = await yt._get(yt.PIPED if piped else yt.INVIDIOUS, path)
            first = data or {}
            page = 1
            while True:
                rows = (data or {}).get("relatedStreams" if piped else "videos") or []
                signature = json.dumps(rows, sort_keys=True)
                if signature in seen:
                    partial = bool(rows)
                    break
                seen.add(signature)
                for r in rows:
                    if piped:
                        url = str(r.get("url") or "")
                        if url.startswith("/"): url = "https://www.youtube.com" + url
                        made = _item(r.get("title") or "", r.get("uploaderName") or "",
                                     int((r.get("duration") or 0) * 1000) or None,
                                     url=url, thumbnail=r.get("thumbnail") or "")
                    else:
                        made = _item(r.get("title") or "", r.get("author") or "",
                                     int((r.get("lengthSeconds") or 0) * 1000) or None,
                                     url="https://www.youtube.com/watch?v=" + str(r.get("videoId") or ""),
                                     thumbnail=(r.get("videoThumbnails") or [{}])[0].get("url", ""))
                    if made: items.append(made)
                if piped:
                    cursor = (data or {}).get("nextpage")
                    if not cursor: break
                    key = "cursor:" + str(cursor)
                    if key in seen:
                        partial = True
                        break
                    seen.add(key)
                    data = await yt._get(yt.PIPED, f"/nextpage/playlists/{link['id']}", {"nextpage": cursor})
                else:
                    total = first.get("videoCount")
                    if not rows or (isinstance(total, int) and len(items) >= total): break
                    page += 1
                    data = await yt._get(yt.INVIDIOUS, path, {"page": page})
        except Exception as exc:
            last, partial = exc, True
            first = first if isinstance(first, dict) else {}
        if items:
            total = first.get("videos" if piped else "videoCount")
            if not isinstance(total, int): total = len(items)
            return {"name": first.get("name" if piped else "title") or "YouTube playlist",
                    "author": first.get("uploader" if piped else "author") or "", "cover": "",
                    "items": items, "total": total, "truncated": partial or len(items) < total}
    raise last or RuntimeError("YouTube nodes are unavailable")


async def _fetch_youtube(link: dict) -> dict:
    try:
        return await _fetch_youtube_flat(link)
    except Exception as exc:
        log.warning("[convert] yt-dlp could not read the playlist: %s", exc)
        return await _fetch_youtube_api(link)


# --------------------------------------------------------------- SoundCloud --
_HYDRATION_RE = re.compile(r"window\.__sc_hydration\s*=\s*(\[.*?\]);", re.S)


async def _fetch_soundcloud_page(link: dict) -> dict:
    html = await _text(link["url"])
    found = _HYDRATION_RE.search(html)
    if not found:
        raise RuntimeError("the SoundCloud page returned no track list")
    playlist: dict = {}
    for node in json.loads(found.group(1)):
        if isinstance(node, dict) and node.get("hydratable") in {"playlist", "sound"}:
            playlist = node.get("data") or {}
            break
    rows = playlist.get("tracks") or ([playlist] if playlist.get("title") else [])
    items = [x for x in (
        _item(r.get("title") or "",
              ((r.get("user") or {}).get("username") or ""),
              r.get("duration"),
              url=r.get("permalink_url") or "",
              thumbnail=r.get("artwork_url") or "") for r in rows) if x]
    if not items:
        raise RuntimeError("the SoundCloud set has no tracks")
    return {
        "name": playlist.get("title") or "SoundCloud playlist",
        "author": (playlist.get("user") or {}).get("username") or "",
        "cover": playlist.get("artwork_url") or "",
        "items": items[:MAX_ITEMS],
        "total": playlist.get("track_count") or len(items),
    }


async def _fetch_soundcloud(link: dict) -> dict:
    try:
        return await _fetch_youtube_flat(link)      # yt-dlp понимает и SoundCloud
    except Exception as exc:
        log.warning("[convert] yt-dlp could not read the set: %s", exc)
        return await _fetch_soundcloud_page(link)


async def _fetch_deezer(link: dict) -> dict:
    """Public metadata only; fixed API host, no preview audio or credentials."""
    import aiohttp
    session = await library.http()
    async def get(path):
        async with session.get("https://api.deezer.com/" + path,
                               timeout=aiohttp.ClientTimeout(total=20), allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError("Deezer public list is unavailable; import a metadata file instead")
            data = await response.json(content_type=None)
            if data.get("error"):
                raise ValueError("Deezer denied access to this list; use a metadata export")
            return data
    entity = await get(link["type"] + "/" + link["id"])
    rows = []
    if link["type"] == "track":
        rows = [entity]
    else:
        page = entity.get("tracks") or {}
        rows = list(page.get("data") or [])
        # Construct our own bounded path; never request an upstream 'next' URL.
        while page.get("next") and len(rows) < 5000:
            page = await get(f"{link['type']}/{link['id']}/tracks?index={len(rows)}&limit=100")
            more = page.get("data") or []
            if not more: break
            rows.extend(more)
    items = []
    for row in rows[:5000]:
        item = _item(row.get("title", ""), (row.get("artist") or {}).get("name", ""),
                     int(row.get("duration") or 0) * 1000,
                     (row.get("album") or {}).get("title", ""))
        if item: items.append(item)
    if not items:
        raise ValueError("No readable tracks in this Deezer list")
    total = entity.get("nb_tracks") or len(rows)
    return {"name": entity.get("title") or "Deezer playlist", "items": items,
            "total": total, "truncated": bool(page.get("next")) if link["type"] != "track" else False,
            "author": (entity.get("creator") or entity.get("artist") or {}).get("name", ""),
            "cover": entity.get("picture_medium") or entity.get("cover_medium") or ""}


FETCHERS = {
    "deezer": _fetch_deezer,
    "spotify": _fetch_spotify,
    "youtube": _fetch_youtube,
    "soundcloud": _fetch_soundcloud,
}


async def fetch(url: str) -> dict:
    """Читает исходный плейлист по ссылке."""
    link = parse_link(url)
    if not link:
        raise ValueError("link not recognised: need a playlist, album or track from "
                         "Spotify, YouTube, SoundCloud or Deezer")
    data = await FETCHERS[link["service"]](link)
    data["service"] = link["service"]
    data["type"] = link["type"]
    data["source_url"] = link["url"]
    data["truncated"] = bool(data.get("truncated")) or \
        bool(data.get("total") and data["total"] > len(data["items"]))
    return data


# --------------------------------------------------------------------------- #
# сопоставление с библиотеками плеера
# --------------------------------------------------------------------------- #
_NOISE_RE = re.compile(
    r"\((?:official|official\s+\w+|lyrics?|lyric\s+video|audio|video|visualizer|"
    r"remaster(?:ed)?(?:\s+\d{4})?|hd|hq|4k|mv|m/v)[^)]*\)"
    r"|\[(?:official|lyrics?|audio|video|remaster(?:ed)?[^\]]*|free\s+dl[^\]]*)\]"
    r"|\b(?:official\s+(?:video|audio|music\s+video)|lyric\s+video|"
    r"full\s+album|hq|hd)\b", re.I)
_FEAT_RE = re.compile(r"\s*(?:\(|\[)?\b(?:feat|ft|featuring|with)\b\.?\s[^)\]]*(?:\)|\])?",
                      re.I)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _NOISE_RE.sub(" ", text)
    text = _FEAT_RE.sub(" ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sim(a: str, b: str) -> float:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.92
    return SequenceMatcher(None, a, b).ratio()


def score(item: dict, track: dict) -> float:
    """0..1 — насколько найденный трек похож на строку исходного плейлиста."""
    title = _sim(item["title"], track.get("title") or "")
    # В названии с YouTube часто «Артист - Трек», поэтому сверяем и пару целиком.
    joined = _sim(f"{item['artist']} {item['title']}",
                  f"{track.get('artist') or ''} {track.get('title') or ''}")
    artist = _sim(item["artist"], track.get("artist") or "") if item["artist"] else 0.5
    value = 0.55 * max(title, joined) + 0.3 * artist
    want, got = item.get("duration"), track.get("duration")
    if want and got:
        delta = abs(want - got)
        value += 0.15 if delta <= 3 else 0.11 if delta <= 8 else 0.05 if delta <= 20 else -0.12
    else:
        value += 0.05
    return max(0.0, min(1.0, value))


async def match_one(item: dict, sources: Iterable[str]) -> dict:
    """Ищет трек в библиотеках и возвращает лучшее совпадение."""
    query = " ".join(x for x in (item["artist"], item["title"]) if x).strip()
    try:
        found = await providers.search(query, sources=list(sources), limit=10)
    except Exception as exc:
        log.warning("[convert] search %r failed: %s", query, exc)
        return {**item, "match": None, "score": 0.0, "state": "error",
                "error": str(exc)[:160]}

    best, best_score = None, 0.0
    for track in found.get("tracks") or []:
        value = score(item, track)
        if value > best_score:
            best, best_score = track, value
    state = "good" if best_score >= GOOD_SCORE else \
            "weak" if best_score >= WEAK_SCORE else "missing"
    return {**item, "match": best if state != "missing" else None,
            "score": round(best_score, 3), "state": state,
            "candidates": len(found.get("tracks") or [])}


# --------------------------------------------------------------------------- #
# задачи: запуск, прогресс, сохранение
# --------------------------------------------------------------------------- #
_jobs: dict[str, dict] = {}


def _cleanup() -> None:
    dead = [k for k, v in _jobs.items() if time.time() - v["updated"] > JOB_TTL and v.get("stage") not in {"loading", "matching", "fetching"}]
    for key in dead:
        _jobs.pop(key, None)


def job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def _public(data: dict) -> dict:
    return {k: v for k, v in data.items() if k != "task" and not k.startswith("_")}


async def _run(job_id: str, url: str, sources: list[str], imported: dict | None = None) -> None:
    state = _jobs[job_id]
    try:
        source = imported if imported is not None else await fetch(url)
        state.update(stage="matching", name=source["name"], service=source["service"],
                     kind=source["type"], cover=source.get("cover", ""),
                     author=source.get("author", ""), total=len(source["items"]),
                     truncated=source.get("truncated", False),
                     source_url=source.get("source_url", ""), updated=time.time())

        results: list[dict | None] = [None] * len(source["items"])
        pending = iter(enumerate(source["items"]))
        done = 0
        published = 0.0

        async def worker() -> None:
            nonlocal done, published
            for index, item in pending:
                results[index] = await match_one(item, sources)
                done += 1
                state["done"] = done
                state["updated"] = time.time()
                if time.monotonic() - published > .2:
                    state["items"] = [r for r in results if r]
                    published = time.monotonic()

        workers = [asyncio.create_task(worker()) for _ in range(min(MATCH_CONCURRENCY, len(results)))]
        try:
            await asyncio.gather(*workers)
        finally:
            for task in workers:
                if not task.done(): task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            state["items"] = [r for r in results if r]
        ready = [r for r in results if r]
        state.update(stage="ready", items=ready, done=len(ready),
                     matched=sum(1 for r in ready if r["state"] == "good"),
                     weak=sum(1 for r in ready if r["state"] == "weak"),
                     missing=sum(1 for r in ready if r["state"] == "missing"),
                     updated=time.time())
        log.info("[convert] %s '%s': matched %d of %d",
                 source["service"], source["name"], state["matched"], state["total"])
    except asyncio.CancelledError:
        # Отмена — не ошибка: оставляем то, что уже успели подобрать.
        ready = [r for r in state.get("items") or [] if r]
        state.update(stage="cancelled", items=ready, done=len(ready),
                     matched=sum(1 for r in ready if r["state"] == "good"),
                     weak=sum(1 for r in ready if r["state"] == "weak"),
                     missing=sum(1 for r in ready if r["state"] == "missing"),
                     updated=time.time())
        log.info("[convert] job %s cancelled, matched %d", job_id, len(ready))
        raise
    except Exception as exc:
        log.warning("[convert] job %s failed: %s", job_id, exc)
        state.update(stage="error", error=str(exc)[:300], updated=time.time())


def start(url: str, sources: list[str] | None = None) -> dict:
    """Создаёт задачу переноса и сразу возвращает её состояние."""
    _cleanup()
    link = parse_link(url)
    if not link:
        raise ValueError("link not recognised: need a playlist, album or track from "
                         "Spotify, YouTube, SoundCloud or Deezer")
    # Ссылку читает свой плагин: выключен — значит переносить нечем.
    pid = SERVICE_PLUGIN.get(link["service"])
    if pid and not plugins.enabled(pid):
        name = plugins.BY_ID.get(pid, {}).get("name", pid)
        raise ValueError(
            f"the plugin '{name}' is off — turn it on in Settings "
            f"(Plugins -> Playlists) to transfer {link['service']} links")
    if pid and plugins.BY_ID.get(pid, {}).get("needs_ytdlp") \
            and not providers.ytdlp_ready():
        raise ValueError("this build has no yt-dlp — such links cannot be read")

    allowed = plugins.enabled_sources()
    picked = [s for s in (sources or providers.ALL_SOURCES) if s in allowed]
    if not picked:
        raise ValueError("no enabled library to search in")

    job_id = uuid.uuid4().hex[:12]
    state = {
        "id": job_id, "stage": "fetching", "service": link["service"],
        "kind": link["type"], "source_url": link["url"], "name": "",
        "author": "", "cover": "", "items": [], "total": 0, "done": 0,
        "matched": 0, "weak": 0, "missing": 0, "sources": picked,
        "created": time.time(), "updated": time.time(),
    }
    _jobs[job_id] = state
    state["task"] = asyncio.create_task(_run(job_id, url, picked))
    return _public(state)


def start_import(source: dict, sources: list[str] | None = None) -> dict:
    """Start the existing cancellable matcher with already validated metadata."""
    _cleanup()
    allowed = plugins.enabled_sources()
    picked = [s for s in (sources or providers.ALL_SOURCES) if s in allowed]
    if not picked:
        raise ValueError("no enabled library to search in")
    job_id = uuid.uuid4().hex[:12]
    state = {"id": job_id, "stage": "matching", "service": source["service"],
             "kind": "playlist", "name": source["name"], "author": "", "cover": "",
             "items": [], "total": len(source["items"]), "done": 0,
             "matched": 0, "weak": 0, "missing": 0, "sources": picked,
             "duplicates": source.get("duplicates", 0), "skipped": source.get("skipped", 0),
             "created": time.time(), "updated": time.time()}
    _jobs[job_id] = state
    state["task"] = asyncio.create_task(_run(job_id, "", picked, source))
    return _public(state)


async def cancel(job_id: str) -> dict:
    """Останавливает задачу: то, что уже подобрано, остаётся доступным."""
    state = _jobs.get(job_id)
    if not state:
        raise ValueError("job not found")
    task = state.get("task")
    if task and not task.done():
        task.cancel()
        # Ждём, пока задача свернётся: иначе интерфейс прочитает ещё не
        # обновлённое состояние и не покажет кнопку сохранения.
        await asyncio.wait({task}, timeout=5)
    if state["stage"] not in {"ready", "error", "cancelled"}:
        state.update(stage="cancelled", updated=time.time())
    return _public(state)


def _clean_override(track: Any) -> dict | None:
    """Ручной выбор из окна «Источники»: берём только понятные поля."""
    if not isinstance(track, dict) or not track.get("id") or not track.get("title"):
        return None
    duration = track.get("duration")
    return {
        "id": str(track["id"]),
        "title": str(track.get("title") or ""),
        "artist": str(track.get("artist") or ""),
        "duration": int(duration) if isinstance(duration, (int, float)) else None,
        "thumbnail": str(track.get("thumbnail") or ""),
        "source": str(track.get("source") or ""),
        "url": str(track.get("url") or ""),
    }


_save_lock = threading.RLock()

def save(job_id: str, name: str | None = None, **kwargs) -> dict:
    """Serialize retryable saves, including concurrent double-clicks."""
    with _save_lock:
        return _save_locked(job_id, name, **kwargs)

def _save_locked(job_id: str, name: str | None = None, *,
         include_weak: bool = True, playlist_id: int | None = None,
         skip: Iterable[int] = (), overrides: dict | None = None) -> dict:
    """Складывает найденные треки в плейлист Kryonyx.

    `overrides` — строки, для которых источник выбран руками в окне
    «Источники»: номер строки → трек. Такие строки сохраняются всегда, даже
    если поиск считал их слабыми или вовсе ничего не нашёл.
    """
    state = _jobs.get(job_id)
    if not state:
        raise ValueError("job not found — start the transfer again")
    if state["stage"] not in {"ready", "cancelled"}:
        raise ValueError("the transfer is not finished yet")

    manual: dict[int, dict] = {}
    for key, value in (overrides or {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        track = _clean_override(value)
        if track:
            manual[index] = track

    skipped = set(skip or ())
    chosen: list[dict] = []
    for index, row in enumerate(state["items"]):
        if index in skipped:
            continue
        if index in manual:
            chosen.append(manual[index])
            continue
        if not row.get("match"):
            continue
        if row["state"] == "weak" and not include_weak:
            continue
        chosen.append(row["match"])
    if not chosen:
        raise ValueError("nothing to save: no matches")

    # Cache successful identical saves: a retried POST must not create a second list.
    fingerprint = hashlib.sha256(json.dumps([playlist_id, name, chosen], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = state.get("_saves", {}).get(fingerprint)
    if previous:
        return {**previous, "added": 0, "already_saved": True}
    if playlist_id:
        playlist = next((p for p in storage.list_playlists() if p["id"] == playlist_id), None)
        if not playlist:
            raise ValueError("Destination playlist no longer exists")
        added = storage.add_many_to_playlist(playlist_id, chosen)
        if added is None:
            raise ValueError("Destination playlist no longer exists")
        playlist = {**playlist, "count": playlist["count"] + added}
    else:
        title = (name or state["name"] or "Imported playlist").strip()[:80]
        playlist = storage.create_playlist(title, chosen)
        added = playlist["count"]
    result = {"playlist": playlist, "added": added, "requested": len(chosen),
              "duplicates": len(chosen) - added}
    cache = state.setdefault("_saves", {})
    if len(cache) >= 32:
        cache.pop(next(iter(cache)))
    cache[fingerprint] = result
    log.info("[convert] %d tracks added to playlist #%s", playlist["id"], added)
    return result
