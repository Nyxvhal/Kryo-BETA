"""
library.py — дополнительные музыкальные библиотеки (без ключей и аккаунтов).

  * Audius          — open-source стриминг, прямой mp3, без ограничений;
  * Bandcamp        — инди-релизы, поток через yt-dlp;
  * Internet Archive — живые записи, архивы, netlabel-релизы, прямые mp3;
  * Mixcloud        — диджей-сеты и радиошоу, поток через yt-dlp;
  * Jamendo         — Creative Commons, прямой mp3;
  * Internet Radio  — каталог Radio-Browser, прямые потоки станций.

Формат id:
    au:<track_id>                 Audius
    bc:<b64(url)>                 Bandcamp
    ia:<b64(identifier/file)>     Internet Archive
    mx:<b64(url)>                 Mixcloud
    jm:<track_id>                 Jamendo
    rb:<b64(stream_url)>          Internet Radio
    dz:<track_id>                 Deezer metadata (audio matched elsewhere)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any

from . import netproxy

log = logging.getLogger(__name__)

try:
    import aiohttp
    AIOHTTP_OK = True
except Exception:  # pragma: no cover
    aiohttp = None  # type: ignore
    AIOHTTP_OK = False

AUDIUS = "audius"
BANDCAMP = "bandcamp"
ARCHIVE = "archive"
MIXCLOUD = "mixcloud"
JAMENDO = "jamendo"
RADIO = "radio"
DEEZER = "deezer"
LIBRARY_SOURCES = (AUDIUS, BANDCAMP, ARCHIVE, MIXCLOUD, JAMENDO, RADIO, DEEZER)

# Публичный ключ из документации Jamendo; в настройках плагина можно указать свой.
JAMENDO_CLIENT_ID = "2b4b80b5"
RADIO_HOSTS = (
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
)

APP_NAME = "KryonyxMusic"
UA = "KryonyxMusic/2.2 (local player)"

_session: Any = None
_session_gen = -1


async def http() -> Any:
    global _session, _session_gen
    if not AIOHTTP_OK:
        raise RuntimeError("aiohttp is unavailable")
    if _session is not None and not _session.closed and _session_gen != netproxy.generation:
        await _session.close()
        _session = None
    if _session is None or _session.closed:
        _session_gen = netproxy.generation
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=8, sock_read=15),
            headers={"User-Agent": UA}, **netproxy.session_kwargs(),
        )
    return _session


async def close() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()


async def _json(url: str, params: dict | None = None, timeout: float = 10.0) -> Any:
    session = await http()
    async with session.get(url, params=params,
                           timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return await resp.json(content_type=None)


# --------------------------------------------------------------------------- #
# Audius
# --------------------------------------------------------------------------- #
_audius_host: tuple[float, str] | None = None
_audius_lock: Any = None
_audius_cooldown = 0.0

# Запасные узлы на случай, если список недоступен. Старый
# discoveryprovider.audius.co отсюда убран намеренно: у него просрочен
# сертификат, и каждый запрос к нему заканчивался CERTIFICATE_VERIFY_FAILED.
_AUDIUS_FALLBACKS = (
    "https://api.audius.co",
    "https://audius-discovery-1.altego.net",
    "https://audius-metadata-1.figment.io",
)
# Узел считается мёртвым на это время, если ответил ошибкой или битым TLS.
_AUDIUS_PENALTY = 900.0
_AUDIUS_DEAD_UNTIL: dict[str, float] = {}
_AUDIUS_FAILS: dict[str, int] = {}
# Одна осечка бывает от сети, а не от узла: снимаем с ротации со второй.
_AUDIUS_MAX_FAILS = 2


class AudiusDown(RuntimeError):
    """Audius сейчас недоступен — молча пропускаем его в поиске и подборках."""


def _audius_alive(host: str) -> bool:
    return _AUDIUS_DEAD_UNTIL.get(host, 0.0) <= time.monotonic()


def audius_mark_dead(host: str) -> None:
    """Осечка узла. Со второй подряд — снимаем его с ротации."""
    global _audius_host
    _AUDIUS_FAILS[host] = _AUDIUS_FAILS.get(host, 0) + 1
    if _AUDIUS_FAILS[host] < _AUDIUS_MAX_FAILS:
        return
    _AUDIUS_DEAD_UNTIL[host] = time.monotonic() + _AUDIUS_PENALTY
    if _audius_host and _audius_host[1] == host:
        _audius_host = None


def audius_mark_ok(host: str) -> None:
    _AUDIUS_FAILS.pop(host, None)


async def audius_host() -> str:
    """Рабочий узел Audius.

    Раньше эта функция не имела замка, и шесть параллельных подборок делали
    шесть одинаковых запросов к api.audius.co — тот отвечал 403 на серию, а
    дальше всё валилось на запасной узел с просроченным сертификатом. Теперь
    список узлов запрашивается один раз, результат (в том числе неудача)
    держится в кэше, а мёртвые узлы на время выпадают из ротации.
    """
    global _audius_host, _audius_lock, _audius_cooldown
    if _audius_host and _audius_host[0] > time.monotonic() and _audius_alive(_audius_host[1]):
        return _audius_host[1]
    if _audius_lock is None:
        _audius_lock = asyncio.Lock()
    async with _audius_lock:
        if _audius_host and _audius_host[0] > time.monotonic() and _audius_alive(_audius_host[1]):
            return _audius_host[1]
        if _audius_cooldown > time.monotonic():
            raise AudiusDown("Audius is unavailable, trying again later")

        hosts: list[str] = []
        try:
            data = await _json("https://api.audius.co", {"app_name": APP_NAME})
            hosts = [h.rstrip("/") for h in (data.get("data") or []) if isinstance(h, str)]
        except Exception as exc:
            log.info("[audius] список узлов недоступен (%s), беру запасные", exc)
        for candidate in list(hosts) + list(_AUDIUS_FALLBACKS):
            host = candidate.rstrip("/")
            if host and _audius_alive(host):
                _audius_host = (time.monotonic() + 1800, host)
                return host
        # Живых узлов нет: уходим в тишину на четверть часа, чтобы не
        # засыпать журнал одинаковыми предупреждениями на каждый запрос.
        _audius_cooldown = time.monotonic() + _AUDIUS_PENALTY
        log.warning("[audius] нет доступных узлов, источник отключён на %d мин",
                    int(_AUDIUS_PENALTY // 60))
        raise AudiusDown("Audius is unavailable")


def _audius_track(item: dict) -> dict | None:
    if not isinstance(item, dict) or not item.get("id"):
        return None
    if item.get("is_delete") or item.get("is_unlisted"):
        return None
    art = item.get("artwork") or {}
    thumb = art.get("480x480") or art.get("1000x1000") or art.get("150x150")
    user = item.get("user") or {}
    return {
        "id": "au:" + str(item["id"]),
        "title": (item.get("title") or "").strip() or "Без названия",
        "artist": (user.get("name") or user.get("handle") or "Audius").strip(),
        "duration": int(item.get("duration") or 0) or None,
        "thumbnail": thumb,
        "play_count": item.get("play_count"),
        "stats_kind": "listens",
        "source": AUDIUS,
        "url": "https://audius.co" + (item.get("permalink") or ""),
    }


async def search_audius(query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    try:
        host = await audius_host()
    except AudiusDown:
        return []
    try:
        data = await _json(f"{host}/v1/tracks/search", {
            "query": query, "limit": min(limit + offset, 50),
            "offset": offset, "app_name": APP_NAME,
        })
    except Exception as exc:
        audius_mark_dead(host)
        log.info("[audius] поиск %r не удался (%s), узел снят с ротации", query, exc)
        return []
    audius_mark_ok(host)
    items = data.get("data") or []
    out = [t for t in (_audius_track(i) for i in items) if t]
    return out[:limit]


async def audius_trending(limit: int = 20) -> list[dict]:
    try:
        host = await audius_host()
    except AudiusDown:
        return []
    try:
        data = await _json(f"{host}/v1/tracks/trending",
                           {"limit": limit, "app_name": APP_NAME})
    except Exception as exc:
        audius_mark_dead(host)
        log.info("[audius] популярное недоступно (%s)", exc)
        return []
    return [t for t in (_audius_track(i) for i in (data.get("data") or [])) if t][:limit]


async def resolve_audius(track_id: str) -> dict:
    try:
        host = await audius_host()
    except AudiusDown as exc:
        raise RuntimeError("Audius is unavailable right now") from exc
    return {
        "url": f"{host}/v1/tracks/{track_id}/stream?app_name={APP_NAME}",
        "headers": {"User-Agent": UA},
        "size": None,
        "mime": "audio/mpeg",
        "duration": None,
    }


# --------------------------------------------------------------------------- #
# Bandcamp
# --------------------------------------------------------------------------- #
async def search_bandcamp(query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    if not AIOHTTP_OK:
        return []
    session = await http()
    payload = {
        "search_text": query,
        "search_filter": "t",       # только треки
        "full_page": False,
        "fan_id": None,
    }
    try:
        async with session.post(
            "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic",
            json=payload, timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            data = await resp.json(content_type=None)
    except Exception as exc:
        log.warning("[bandcamp] search %r failed: %s", query, exc)
        return []

    results = ((data or {}).get("auto") or {}).get("results") or []
    out: list[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = item.get("item_url_path") or item.get("url")
        name = (item.get("name") or "").strip()
        if not url or not name:
            continue
        out.append({
            "id": "bc:" + b64e(url),
            "title": name,
            "artist": (item.get("band_name") or "Bandcamp").strip(),
            "duration": None,
            "thumbnail": item.get("img") or None,
            "source": BANDCAMP,
            "url": url,
        })
    return out[offset: offset + limit]


# --------------------------------------------------------------------------- #
# Internet Archive
# --------------------------------------------------------------------------- #
_AUDIO_EXT = (".mp3", ".ogg", ".m4a", ".flac")


async def _archive_files(identifier: str) -> list[dict]:
    try:
        data = await _json(f"https://archive.org/metadata/{identifier}")
    except Exception:
        return []
    return [f for f in (data.get("files") or []) if isinstance(f, dict)]


async def _archive_item(doc: dict) -> dict | None:
    identifier = doc.get("identifier")
    if not identifier:
        return None
    files = await _archive_files(identifier)
    best = None
    for item in files:
        name = str(item.get("name") or "")
        low = name.lower()
        if not low.endswith(_AUDIO_EXT):
            continue
        # предпочитаем mp3: браузер играет его всегда
        rank = 0 if low.endswith(".mp3") else 1
        if best is None or rank < best[0]:
            best = (rank, item, name)
    if not best:
        return None
    meta = best[1]
    name = best[2]
    length = meta.get("length")
    duration = None
    if isinstance(length, str) and ":" in length:
        parts = [float(p) for p in length.split(":") if p.replace(".", "").isdigit()]
        for part in parts:
            duration = (duration or 0) * 60 + part
        duration = int(duration) if duration else None
    elif length:
        try:
            duration = int(float(length))
        except Exception:
            duration = None
    creator = doc.get("creator")
    if isinstance(creator, list):
        creator = creator[0] if creator else None
    return {
        "id": "ia:" + b64e(f"{identifier}/{name}"),
        "title": (meta.get("title") or doc.get("title") or name).strip(),
        "artist": (creator or "Internet Archive").strip(),
        "duration": duration,
        "thumbnail": f"https://archive.org/services/img/{identifier}",
        "source": ARCHIVE,
        "url": f"https://archive.org/details/{identifier}",
    }


async def search_archive(query: str, limit: int = 12, offset: int = 0) -> list[dict]:
    rows = min(limit + offset, 20)
    params = [
        ("q", f'({query}) AND mediatype:(audio)'),
        ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "creator"),
        ("rows", str(rows)), ("page", "1"), ("output", "json"),
        ("sort[]", "downloads desc"),
    ]
    try:
        data = await _json("https://archive.org/advancedsearch.php", params)  # type: ignore[arg-type]
    except Exception as exc:
        log.warning("[archive] search %r failed: %s", query, exc)
        return []
    docs = (((data or {}).get("response") or {}).get("docs") or [])[offset: offset + limit]
    results = await asyncio.gather(*[_archive_item(d) for d in docs], return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


async def resolve_archive(track_id: str) -> dict:
    path = b64d(track_id)
    return {
        "url": "https://archive.org/download/" + path,
        "headers": {"User-Agent": UA},
        "size": None,
        "mime": "audio/mpeg" if path.lower().endswith(".mp3") else "audio/mp4",
        "duration": None,
    }


# --------------------------------------------------------------------------- #
# Mixcloud
# --------------------------------------------------------------------------- #
async def search_mixcloud(query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    try:
        data = await _json("https://api.mixcloud.com/search/", {
            "q": query, "type": "cloudcast", "limit": min(limit + offset, 40),
        })
    except Exception as exc:
        log.warning("[mixcloud] search %r failed: %s", query, exc)
        return []
    out: list[dict] = []
    for item in (data or {}).get("data") or []:
        url = item.get("url")
        if not url:
            continue
        user = item.get("user") or {}
        pictures = item.get("pictures") or {}
        out.append({
            "id": "mx:" + b64e(url),
            "title": (item.get("name") or "").strip() or "Mixcloud",
            "artist": (user.get("name") or "Mixcloud").strip(),
            "duration": int(item.get("audio_length") or 0) or None,
            "thumbnail": pictures.get("large") or pictures.get("medium"),
            "source": MIXCLOUD,
            "url": url,
        })
    return out[offset: offset + limit]


# --------------------------------------------------------------------------- #
# Jamendo
# --------------------------------------------------------------------------- #
_jamendo_client_id = JAMENDO_CLIENT_ID


def set_jamendo_client(client_id: str | None) -> None:
    global _jamendo_client_id
    _jamendo_client_id = (client_id or "").strip() or JAMENDO_CLIENT_ID


def _jamendo_track(item: dict) -> dict | None:
    if not isinstance(item, dict) or not item.get("id"):
        return None
    return {
        "id": "jm:" + str(item["id"]),
        "title": (item.get("name") or "").strip() or "Jamendo",
        "artist": (item.get("artist_name") or "Jamendo").strip(),
        "duration": int(item.get("duration") or 0) or None,
        "thumbnail": item.get("album_image") or item.get("image"),
        "source": JAMENDO,
        "url": item.get("shareurl") or item.get("shorturl"),
        "stream": item.get("audio") or item.get("audiodownload"),
    }


async def search_jamendo(query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    try:
        data = await _json("https://api.jamendo.com/v3.0/tracks/", {
            "client_id": _jamendo_client_id, "format": "json",
            "limit": min(limit, 50), "offset": offset,
            "search": query, "audioformat": "mp32",
        })
    except Exception as exc:
        log.warning("[jamendo] search %r failed: %s", query, exc)
        return []
    return [t for t in (_jamendo_track(i) for i in (data.get("results") or [])) if t][:limit]


async def resolve_jamendo(track_id: str) -> dict:
    data = await _json("https://api.jamendo.com/v3.0/tracks/", {
        "client_id": _jamendo_client_id, "format": "json",
        "id": track_id, "audioformat": "mp32",
    })
    results = (data or {}).get("results") or []
    url = (results[0].get("audio") if results else None)
    if not url:
        raise RuntimeError("Jamendo: stream unavailable")
    return {"url": url, "headers": {"User-Agent": UA}, "size": None,
            "mime": "audio/mpeg",
            "duration": int(results[0].get("duration") or 0) or None}


# --------------------------------------------------------------------------- #
# Internet Radio (Radio-Browser)
# --------------------------------------------------------------------------- #
_radio_host: tuple[float, str] | None = None


async def radio_host() -> str:
    global _radio_host
    if _radio_host and _radio_host[0] > time.monotonic():
        return _radio_host[1]
    for host in RADIO_HOSTS:
        try:
            await _json(f"{host}/json/stats", timeout=5)
            _radio_host = (time.monotonic() + 1800, host)
            return host
        except Exception:
            continue
    _radio_host = (time.monotonic() + 300, RADIO_HOSTS[0])
    return RADIO_HOSTS[0]


def _radio_station(item: dict) -> dict | None:
    url = item.get("url_resolved") or item.get("url")
    if not url or not isinstance(url, str):
        return None
    tags = (item.get("tags") or "").split(",")[0].strip()
    country = (item.get("country") or "").strip()
    subtitle = " · ".join(x for x in (tags.title() if tags else "", country) if x)
    return {
        "id": "rb:" + b64e(url),
        "title": (item.get("name") or "").strip()[:120] or "Radio",
        "artist": subtitle or "Internet Radio",
        "duration": None,
        "thumbnail": item.get("favicon") or None,
        "source": RADIO,
        "url": item.get("homepage") or url,
        "live": True,
    }


async def search_radio(query: str, limit: int = 12, offset: int = 0) -> list[dict]:
    host = await radio_host()
    try:
        data = await _json(f"{host}/json/stations/search", {
            "name": query, "limit": min(limit + offset, 40),
            "hidebroken": "true", "order": "clickcount", "reverse": "true",
        })
    except Exception as exc:
        log.warning("[radio] search %r failed: %s", query, exc)
        return []
    out = [s for s in (_radio_station(i) for i in (data or [])) if s]
    return out[offset: offset + limit]


async def radio_top(limit: int = 20) -> list[dict]:
    host = await radio_host()
    try:
        data = await _json(f"{host}/json/stations/topclick/{min(limit, 40)}")
    except Exception:
        return []
    return [s for s in (_radio_station(i) for i in (data or [])) if s][:limit]


async def resolve_radio(track_id: str) -> dict:
    url = b64d(track_id)
    mime = "audio/aac" if url.lower().rstrip("/").endswith(".aac") else "audio/mpeg"
    return {"url": url, "headers": {"User-Agent": UA}, "size": None,
            "mime": mime, "duration": None, "live": True}


# --------------------------------------------------------------------------- #
# Deezer — полноценный поиск метаданных. Полные потоки Deezer требуют
# авторизации, поэтому звук прозрачно подбирается из открытых источников.
# --------------------------------------------------------------------------- #
def _deezer_track(item: dict) -> dict | None:
    if not isinstance(item, dict) or not item.get("id"):
        return None
    artist = item.get("artist") or {}
    album = item.get("album") or {}
    return {
        "id": "dz:" + str(item["id"]),
        "title": (item.get("title") or item.get("title_short") or "Без названия").strip(),
        "artist": (artist.get("name") or "Deezer").strip(),
        "album": (album.get("title") or "").strip() or None,
        "duration": int(item.get("duration") or 0) or None,
        "thumbnail": album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium"),
        "source": DEEZER,
        "url": item.get("link") or f"https://www.deezer.com/track/{item['id']}",
        "author_url": artist.get("link"),
    }


async def search_deezer(query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    try:
        data = await _json("https://api.deezer.com/search", {
            "q": query, "limit": min(limit, 50), "index": max(0, offset),
        }, timeout=8.0)
    except Exception as exc:
        log.info("[deezer] search %r failed: %s", query, exc)
        return []
    return [track for track in (_deezer_track(item) for item in (data or {}).get("data") or [])
            if track][:limit]

# --------------------------------------------------------------------------- #
# общий вход
# --------------------------------------------------------------------------- #
async def search(source: str, query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    query = (query or "").strip()
    if not query or not AIOHTTP_OK:
        return []
    if source == AUDIUS:
        return await search_audius(query, limit, offset)
    if source == BANDCAMP:
        return await search_bandcamp(query, limit, offset)
    if source == ARCHIVE:
        return await search_archive(query, min(limit, 12), offset)
    if source == MIXCLOUD:
        return await search_mixcloud(query, limit, offset)
    if source == JAMENDO:
        return await search_jamendo(query, limit, offset)
    if source == RADIO:
        return await search_radio(query, min(limit, 12), offset)
    if source == DEEZER:
        return await search_deezer(query, limit, offset)
    return []


def status() -> list[dict]:
    return [
        {"id": AUDIUS, "name": "Audius", "available": AIOHTTP_OK,
         "note": "Open streaming: electronic, hip-hop and independent artists"},
        {"id": BANDCAMP, "name": "Bandcamp", "available": AIOHTTP_OK,
         "note": "Indie and small labels; full tracks published by the artists"},
        {"id": ARCHIVE, "name": "Internet Archive", "available": AIOHTTP_OK,
         "note": "Live sets, archival recordings and netlabel releases"},
        {"id": MIXCLOUD, "name": "Mixcloud", "available": AIOHTTP_OK,
         "note": "DJ sets, radio shows and long mixes"},
        {"id": JAMENDO, "name": "Jamendo", "available": AIOHTTP_OK,
         "note": "Creative Commons catalogue with direct mp3 streams"},
        {"id": RADIO, "name": "Internet Radio", "available": AIOHTTP_OK,
         "note": "Live stations from the Radio-Browser directory"},
        {"id": DEEZER, "name": "Deezer", "available": AIOHTTP_OK,
         "note": "Deezer catalogue metadata; audio is matched to open providers"},
    ]
