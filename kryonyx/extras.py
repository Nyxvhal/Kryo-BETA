"""
extras.py — то, что дают плагины поверх воспроизведения:

  * метаданные   — Deezer, MusicBrainz + Cover Art Archive, Discogs, Wikipedia;
  * тексты       — lyrics.ovh как запасной вариант к LRCLIB;
  * скробблинг   — ListenBrainz, Maloja, Last.fm;
  * подборки     — Audius Trending, Deezer Charts, топ радиостанций.

Каждый источник включается своим плагином в каталоге и молча пропускается,
если он выключен или не настроен.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
import urllib.parse
import zlib
from typing import Any

from . import library, plugins

log = logging.getLogger(__name__)

UA = library.UA
_cache: dict[str, tuple[float, Any]] = {}


def _cached(key: str):
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def _store(key: str, value: Any, ttl: float = 3600.0):
    if len(_cache) > 1200:
        _cache.clear()
    _cache[key] = (time.monotonic() + ttl, value)
    return value


async def _json(url: str, params: dict | None = None, headers: dict | None = None,
                timeout: float = 8.0) -> Any:
    session = await library.http()
    import aiohttp
    async with session.get(url, params=params, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return await resp.json(content_type=None)


# --------------------------------------------------------------------------- #
# метаданные
# --------------------------------------------------------------------------- #
async def _deezer(artist: str, title: str) -> dict:
    # Строгий синтаксис (artist:"…" track:"…") Deezer часто отдаёт пустым,
    # поэтому после него пробуем обычную строку.
    queries = [f'artist:"{artist}" track:"{title}"', f"{artist} {title}".strip()] \
        if artist else [title]
    items: list[dict] = []
    for query in queries:
        data = await _json("https://api.deezer.com/search", {"q": query, "limit": 1})
        items = (data or {}).get("data") or []
        if items:
            break
    if not items:
        return {}
    item = items[0]
    album = item.get("album") or {}
    return {
        "source": "deezer",
        "title": item.get("title"),
        "artist": (item.get("artist") or {}).get("name"),
        "album": album.get("title"),
        "cover": album.get("cover_xl") or album.get("cover_big"),
        "duration": item.get("duration"),
        "link": item.get("link"),
    }


async def _musicbrainz(artist: str, title: str) -> dict:
    query = f'recording:"{title}"' + (f' AND artist:"{artist}"' if artist else "")
    data = await _json("https://musicbrainz.org/ws/2/recording",
                       {"query": query, "fmt": "json", "limit": 1},
                       headers={"User-Agent": UA})
    items = (data or {}).get("recordings") or []
    if not items:
        return {}
    rec = items[0]
    releases = rec.get("releases") or []
    release = releases[0] if releases else {}
    out = {
        "source": "musicbrainz",
        "mbid": rec.get("id"),
        "title": rec.get("title"),
        "album": release.get("title"),
        "year": (rec.get("first-release-date") or "")[:4] or None,
    }
    if release.get("id"):
        out["cover"] = f"https://coverartarchive.org/release/{release['id']}/front-500"
    return out


async def _discogs(artist: str, title: str) -> dict:
    token = (plugins.config("discogs").get("token") or "").strip()
    if not token:
        return {}
    data = await _json("https://api.discogs.com/database/search",
                       {"q": f"{artist} {title}".strip(), "type": "release",
                        "per_page": 1, "token": token},
                       headers={"User-Agent": UA})
    items = (data or {}).get("results") or []
    if not items:
        return {}
    item = items[0]
    return {
        "source": "discogs",
        "album": item.get("title"),
        "year": str(item.get("year") or "") or None,
        "label": (item.get("label") or [None])[0],
        "genres": item.get("genre") or [],
        "styles": item.get("style") or [],
        "cover": item.get("cover_image"),
    }


async def _wikipedia(artist: str) -> dict:
    if not artist:
        return {}
    slug = urllib.parse.quote(artist.replace(" ", "_"))
    data = await _json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
                       headers={"User-Agent": UA})
    extract = (data or {}).get("extract")
    if not extract:
        return {}
    return {
        "source": "wikipedia",
        "bio": extract,
        "link": ((data.get("content_urls") or {}).get("desktop") or {}).get("page"),
        "image": ((data.get("thumbnail") or {}).get("source")),
    }


async def metadata(artist: str, title: str) -> dict:
    """Собирает метаданные всеми включёнными плагинами категории metadata."""
    key = f"meta:{artist}|{title}".lower()
    hit = _cached(key)
    if hit is not None:
        return hit

    jobs: list[tuple[str, Any]] = []
    if plugins.enabled("deezer"):
        jobs.append(("deezer", _deezer(artist, title)))
    if plugins.enabled("musicbrainz"):
        jobs.append(("musicbrainz", _musicbrainz(artist, title)))
    if plugins.enabled("discogs"):
        jobs.append(("discogs", _discogs(artist, title)))
    if plugins.enabled("wikipedia"):
        jobs.append(("wikipedia", _wikipedia(artist)))
    if not jobs:
        return {"providers": [], "fields": {}}

    results = await asyncio.gather(*[j[1] for j in jobs], return_exceptions=True)
    fields: dict[str, Any] = {}
    used: list[str] = []
    detail: dict[str, dict] = {}
    for (name, _), result in zip(jobs, results):
        if isinstance(result, Exception) or not result:
            if isinstance(result, Exception):
                log.debug("[meta] %s: %s", name, result)
            continue
        used.append(name)
        detail[name] = result
        for field, value in result.items():
            if field != "source" and value and field not in fields:
                fields[field] = value
    return _store(key, {"providers": used, "fields": fields, "detail": detail})


# --------------------------------------------------------------------------- #
# тексты (запасной путь к LRCLIB)
# --------------------------------------------------------------------------- #
async def plain_lyrics(artist: str, title: str) -> list[dict]:
    if not plugins.enabled("lyricsovh") or not artist:
        return []
    try:
        data = await _json(
            f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}",
            timeout=8)
    except Exception:
        return []
    text = (data or {}).get("lyrics") or ""
    return [{"time": None, "text": line} for line in text.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# скробблинг
# --------------------------------------------------------------------------- #
async def _listenbrainz(track: dict, seconds: float) -> bool:
    token = (plugins.config("listenbrainz").get("token") or "").strip()
    if not token:
        return False
    payload = {
        "listen_type": "single",
        "payload": [{
            "listened_at": int(time.time()),
            "track_metadata": {
                "artist_name": track.get("artist") or "Unknown",
                "track_name": track.get("title") or "Unknown",
                "additional_info": {"media_player": "Kryo",
                                    "duration_ms": int((track.get("duration") or seconds) * 1000)},
            },
        }],
    }
    session = await library.http()
    async with session.post("https://api.listenbrainz.org/1/submit-listens",
                            json=payload,
                            headers={"Authorization": f"Token {token}"}) as resp:
        return resp.status < 300


async def _maloja(track: dict, seconds: float) -> bool:
    conf = plugins.config("maloja")
    url = (conf.get("url") or "").strip().rstrip("/")
    key = (conf.get("key") or "").strip()
    if not url or not key:
        return False
    session = await library.http()
    async with session.post(f"{url}/apis/mlj_1/newscrobble", json={
        "artist": track.get("artist") or "Unknown",
        "title": track.get("title") or "Unknown",
        "key": key,
        "length": int(track.get("duration") or seconds or 0),
    }) as resp:
        return resp.status < 300


def _lastfm_sign(params: dict, secret: str) -> dict:
    signature = "".join(f"{k}{params[k]}" for k in sorted(params)) + secret
    return {**params, "api_sig": hashlib.md5(signature.encode()).hexdigest(),
            "format": "json"}


async def lastfm_now_playing(track: dict) -> bool:
    """track.updateNowPlaying — «сейчас играет» в профиле Last.fm."""
    conf = plugins.config("lastfm")
    api_key = (conf.get("api_key") or "").strip()
    secret = (conf.get("secret") or "").strip()
    session_key = (conf.get("session") or "").strip()
    if not (api_key and secret and session_key):
        return False
    params = _lastfm_sign({
        "method": "track.updateNowPlaying", "api_key": api_key, "sk": session_key,
        "artist": track.get("artist") or "Unknown",
        "track": track.get("title") or "Unknown",
    }, secret)
    session = await library.http()
    async with session.post("https://ws.audioscrobbler.com/2.0/", data=params) as resp:
        return resp.status < 300


async def _lastfm(track: dict, seconds: float) -> bool:
    conf = plugins.config("lastfm")
    api_key = (conf.get("api_key") or "").strip()
    secret = (conf.get("secret") or "").strip()
    session_key = (conf.get("session") or "").strip()
    if not (api_key and secret and session_key):
        return False
    params = {
        "method": "track.scrobble",
        "api_key": api_key,
        "sk": session_key,
        "artist": track.get("artist") or "Unknown",
        "track": track.get("title") or "Unknown",
        "timestamp": str(int(time.time() - (seconds or 0))),
    }
    params = _lastfm_sign(params, secret)
    session = await library.http()
    async with session.post("https://ws.audioscrobbler.com/2.0/", data=params) as resp:
        return resp.status < 300


async def scrobble(track: dict, seconds: float = 0.0) -> list[str]:
    """Отправляет прослушивание во все включённые скробблеры."""
    jobs = []
    if plugins.enabled("listenbrainz"):
        jobs.append(("listenbrainz", _listenbrainz(track, seconds)))
    if plugins.enabled("maloja"):
        jobs.append(("maloja", _maloja(track, seconds)))
    if plugins.enabled("lastfm"):
        jobs.append(("lastfm", _lastfm(track, seconds)))
    if not jobs:
        return []
    results = await asyncio.gather(*[j[1] for j in jobs], return_exceptions=True)
    done = []
    for (name, _), result in zip(jobs, results):
        if isinstance(result, Exception):
            log.warning("[scrobble] %s: %s", name, result)
        elif result:
            done.append(name)
    return done


# --------------------------------------------------------------------------- #
# подборки для главной
# --------------------------------------------------------------------------- #
async def _deezer_chart(limit: int) -> list[dict]:
    data = await _json("https://api.deezer.com/chart/0/tracks", {"limit": limit})
    out = []
    for item in (data or {}).get("data") or []:
        out.append({
            "title": item.get("title"),
            "artist": (item.get("artist") or {}).get("name"),
            "thumbnail": (item.get("album") or {}).get("cover_big"),
            "duration": item.get("duration"),
            "match": True,          # звук подбирается в открытых библиотеках
        })
    return out


async def _listenbrainz_top(limit: int) -> list[dict]:
    data = await _json("https://api.listenbrainz.org/1/stats/sitewide/recordings",
                       {"count": min(limit, 100), "range": "week"}, timeout=10)
    out = []
    for item in ((data or {}).get("payload") or {}).get("recordings") or []:
        mbid = item.get("caa_release_mbid")
        out.append({
            "title": item.get("track_name"),
            "artist": item.get("artist_name"),
            "thumbnail": f"https://coverartarchive.org/release/{mbid}/front-500" if mbid else None,
            "match": True,
        })
    return out


async def _bandcamp_notable(limit: int) -> list[dict]:
    session = await library.http()
    import aiohttp
    async with session.post(
        "https://bandcamp.com/api/homepage_api/1/notable_tralbums_data",
        json={"page_size": min(limit, 40)},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    out = []
    for item in ((data or {}).get("items") or (data or {}).get("results") or []):
        image = item.get("image_id") or item.get("imageId")
        out.append({
            "title": item.get("title"),
            "artist": item.get("artist_name") or item.get("artistName") or (item.get("attribution") or {}).get("name"),
            "thumbnail": f"https://f4.bcbits.com/img/a{image}_16.jpg" if image else None,
            "match": True,
        })
    return out


async def discovery_rows(limit: int = 16) -> list[dict]:
    """Ряды главной, которые добавляют плагины категории discovery."""
    rows: list[dict] = []

    if plugins.enabled("audius-trending"):
        try:
            items = await library.audius_trending(limit)
            if items:
                rows.append({"id": "audius-trending", "title": "Trending on Audius",
                             "plugin": "audius-trending", "items": items})
        except Exception as exc:
            log.debug("[discovery] audius: %s", exc)

    if plugins.enabled("radio-top"):
        try:
            items = await library.radio_top(limit)
            if items:
                rows.append({"id": "radio-top", "title": "Top radio stations",
                             "plugin": "radio-top", "items": items})
        except Exception as exc:
            log.debug("[discovery] radio: %s", exc)

    if plugins.enabled("deezer-charts"):
        try:
            items = await _deezer_chart(limit)
            if items:
                rows.append({"id": "deezer-charts", "title": "Global charts",
                             "plugin": "deezer-charts", "unresolved": True,
                             "items": items})
        except Exception as exc:
            log.debug("[discovery] deezer: %s", exc)

    if plugins.enabled("listenbrainz-dashboard"):
        try:
            items = await _listenbrainz_top(limit)
            if items:
                rows.append({"id": "listenbrainz-dashboard", "title": "Popular on ListenBrainz",
                             "plugin": "listenbrainz-dashboard", "unresolved": True, "items": items})
        except Exception as exc:
            log.debug("[discovery] listenbrainz: %s", exc)

    if plugins.enabled("bandcamp-dashboard"):
        try:
            items = await _bandcamp_notable(limit)
            if items:
                rows.append({"id": "bandcamp-dashboard", "title": "Notable on Bandcamp",
                             "plugin": "bandcamp-dashboard", "unresolved": True, "items": items})
        except Exception as exc:
            log.debug("[discovery] bandcamp: %s", exc)

    # Ряды от своих плагинов пользователя: у них тот же вид, что у встроенных.
    try:
        from . import extplugins
        rows.extend(await extplugins.dashboard_rows(limit))
    except Exception as exc:
        log.debug("[discovery] custom plugins: %s", exc)

    return rows


# --------------------------------------------------------------------------- #
# обмен плейлистами: короткий код «KRX1:…»
# --------------------------------------------------------------------------- #
PLAYLIST_CODE_PREFIX = "KRX1:"
# Второй формат кода — короткий. Старый «KRX1:» умел только полный JSON с
# обложками: тридцать треков давали простыню на 8–10 тысяч знаков, которую
# не принимал ни один мессенджер.
PLAYLIST_CODE_V2 = "KRX2:"

# Поля, которых хватает, чтобы трек заиграл у друга; остальное раздувает код.
_SHARE_FIELDS = ("id", "title", "artist", "album", "duration",
                 "thumbnail", "source", "url", "author_url")


def _thumb_for(track_id: str) -> str:
    """Обложку YouTube можно восстановить из id — в коде её не несём."""
    if track_id.startswith("yt:") and len(track_id) > 3:
        return f"https://i.ytimg.com/vi/{track_id[3:]}/hqdefault.jpg"
    return ""


# --------------------------------------------------------------------------- #
# дозаполнение обложек
# --------------------------------------------------------------------------- #
# Обложку хранит далеко не каждый источник: Bandcamp и Mixcloud отдают её не
# во всех ответах, Audius — только для части треков, а у YouTube она иногда
# теряется в «плоской» выдаче (flat-playlist). Пустая плитка в этом случае
# означала лишь «источник не прислал картинку», хотя обложка существует.
_ART_TTL = 86400.0            # найденная картинка живёт сутки
_ART_MISS_TTL = 1800.0        # ненайденная — полчаса, чтобы не долбить API
_ART_LOOKUPS = 16             # сколько треков ищем по сети за один ответ
_ART_PARALLEL = 6


def _art_key(artist: str, title: str) -> str:
    return f"art:{artist.strip()}|{title.strip()}".lower()


async def cover_for(artist: str, title: str) -> str:
    """Обложка по исполнителю и названию. Пусто — значит не нашлась."""
    title = (title or "").strip()
    if not title:
        return ""
    artist = (artist or "").strip()
    key = _art_key(artist, title)
    hit = _cached(key)
    if hit is not None:
        return hit
    cover = ""
    try:
        info = await _deezer(artist, title)
        cover = str(info.get("cover") or "")
    except Exception as exc:
        log.debug("[art] %s — %s: %s", artist, title, exc)
    _store(key, cover, _ART_TTL if cover else _ART_MISS_TTL)
    return cover


async def fill_thumbnails(tracks: Any, *, lookup: bool = True,
                          limit: int = _ART_LOOKUPS) -> Any:
    """Дописывает обложки тем трекам, которым источник их не дал.

    Сначала бесплатные способы: обложка YouTube восстанавливается из id, а
    уже найденные картинки берутся из кэша. Только остаток ищется по сети, и
    то не больше `limit` штук за ответ — ряды главной не должны ждать сеть.
    """
    if not isinstance(tracks, list):
        return tracks
    pending: list[dict] = []
    for track in tracks:
        if not isinstance(track, dict) or track.get("thumbnail"):
            continue
        derived = _thumb_for(str(track.get("id") or ""))
        if derived:
            track["thumbnail"] = derived
            continue
        pending.append(track)
    if not pending:
        return tracks

    remote: list[dict] = []
    for track in pending:
        key = _art_key(str(track.get("artist") or ""), str(track.get("title") or ""))
        hit = _cached(key)
        if hit is None:
            remote.append(track)
        elif hit:
            track["thumbnail"] = hit
    if not lookup or not remote:
        return tracks

    gate = asyncio.Semaphore(_ART_PARALLEL)

    async def one(track: dict) -> None:
        async with gate:
            cover = await cover_for(str(track.get("artist") or ""),
                                    str(track.get("title") or ""))
            if cover:
                track["thumbnail"] = cover

    await asyncio.gather(*[one(t) for t in remote[:limit]], return_exceptions=True)
    return tracks


def pack_playlist(name: str, tracks: list[dict]) -> str:
    """Плейлист -> короткая строка «KRX2:…».

    Формат нарочно текстовый и плотный: строки «id|название|исполнитель|сек»,
    сжатые zlib и закодированные base64url. Обложки и ссылки в код не идут:
    у YouTube обложка восстанавливается из id, остальное подтянется при
    первом воспроизведении. Так код стал короче прежнего в 8–12 раз.
    """
    rows = [str(name or "Playlist")[:120]]
    for track in tracks:
        if not isinstance(track, dict) or not track.get("id"):
            continue
        def field(key: str) -> str:
            return str(track.get(key) or "").replace("|", "/").replace("\n", " ")[:120]
        rows.append("|".join((str(track["id"])[:60], field("title"), field("artist"),
                              str(int(track.get("duration") or 0)))))
    raw = "\n".join(rows).encode("utf-8")
    packed = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")
    return PLAYLIST_CODE_V2 + packed


def unpack_playlist(code: str) -> tuple[str, list[dict]]:
    """Код (или содержимое файла .kryx) -> название и треки. Понимает оба формата."""
    text = (code or "").strip()
    # Из мессенджеров код часто приезжает с переносами строк и пробелами.
    text = "".join(text.split())
    short = text.startswith(PLAYLIST_CODE_V2)
    for prefix in (PLAYLIST_CODE_V2, PLAYLIST_CODE_PREFIX):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    try:
        if text.startswith("{"):                  # файл с обычным JSON
            payload = json.loads(text)
        else:
            padded = text + "=" * (-len(text) % 4)
            raw = zlib.decompress(base64.urlsafe_b64decode(padded.encode("ascii")))
            if short or not raw.lstrip().startswith(b"{"):
                return _unpack_rows(raw.decode("utf-8", "replace"))
            payload = json.loads(raw.decode("utf-8"))
    except Exception:
        # Внутренние ошибки base64/zlib пользователю ничего не говорят.
        raise ValueError("This share code is not valid") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("tracks"), list):
        raise ValueError("This share code is not valid")
    tracks = [{key: item.get(key) for key in _SHARE_FIELDS if item.get(key) is not None}
              for item in payload["tracks"] if isinstance(item, dict) and item.get("id")]
    for track in tracks:
        if not track.get("thumbnail"):
            thumb = _thumb_for(str(track.get("id") or ""))
            if thumb:
                track["thumbnail"] = thumb
    return str(payload.get("name") or "Playlist")[:120], tracks


def _unpack_rows(text: str) -> tuple[str, list[dict]]:
    """Короткий формат: первая строка — название, дальше по треку на строку."""
    lines = [row for row in text.split("\n") if row.strip()]
    if not lines:
        raise ValueError("This share code is not valid")
    name = lines[0][:120]
    tracks: list[dict] = []
    for row in lines[1:]:
        parts = row.split("|")
        track_id = parts[0].strip()
        if not track_id:
            continue
        track = {
            "id": track_id,
            "title": (parts[1] if len(parts) > 1 else "") or track_id,
            "artist": parts[2] if len(parts) > 2 else "",
            "duration": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
            "source": track_id.split(":", 1)[0] if ":" in track_id else "",
        }
        thumb = _thumb_for(track_id)
        if thumb:
            track["thumbnail"] = thumb
        tracks.append(track)
    if not tracks:
        raise ValueError("The share code has no tracks")
    return name, tracks


# --------------------------------------------------------------------------- #
# экспорт плейлиста в m3u
# --------------------------------------------------------------------------- #
def playlist_m3u(name: str, tracks: list[dict], base: str = "") -> str:
    lines = ["#EXTM3U", f"#PLAYLIST:{name}"]
    for track in tracks:
        duration = int(track.get("duration") or -1)
        lines.append(f"#EXTINF:{duration},{track.get('artist','')} - {track.get('title','')}")
        tid = urllib.parse.quote(str(track.get("id") or ""))
        lines.append(f"{base}/api/stream?id={tid}")
    return "\n".join(lines) + "\n"
