"""
youtube.py — YouTube через публичные API открытых фронтендов Piped и Invidious.

Зачем: yt-dlp запускает парсер страницы и подпись плеера на каждый запрос —
это секунды на трек. Piped/Invidious отдают готовый JSON и прямые ссылки на
аудиодорожку, поэтому поиск и старт трека занимают десятки миллисекунд.

Формат id остаётся прежним: yt:<video_id>.
"""

from __future__ import annotations

import asyncio
import logging
import random
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

UA = "KryonyxMusic/2.6 (local player)"

# Публичные узлы. Список живой: если узел молчит или отдаёт ошибку, он временно
# уходит в конец очереди, а запрос повторяется на следующем.
PIPED = [
    "https://pipedapi.kavin.rocks",
    "https://api.piped.private.coffee",
    "https://pipedapi.adminforge.de",
    "https://piped-api.lunar.icu",
    "https://pipedapi.reallyaweso.me",
]
INVIDIOUS = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
    "https://invidious.f5.si",
]

_penalty: dict[str, float] = {}
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
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=6, sock_read=10),
            headers={"User-Agent": UA}, **netproxy.session_kwargs(),
        )
    return _session


async def close() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def _order(hosts: list[str]) -> list[str]:
    now = time.monotonic()
    live = [h for h in hosts if _penalty.get(h, 0) < now]
    dead = [h for h in hosts if _penalty.get(h, 0) >= now]
    random.shuffle(live)
    return live + dead


def _blame(host: str, seconds: float = 300.0) -> None:
    _penalty[host] = time.monotonic() + seconds


async def _get(hosts: list[str], path: str, params: dict | None = None,
               timeout: float = 9.0) -> Any:
    """Запрос по очереди узлов: первый ответивший выигрывает."""
    session = await http()
    last: Exception | None = None
    for host in _order(hosts)[:4]:
        try:
            async with session.get(host + path, params=params,
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                data = await resp.json(content_type=None)
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(str(data["error"])[:120])
            return data
        except Exception as exc:
            last = exc
            _blame(host)
            continue
    raise RuntimeError(f"all instances failed: {last}")


# --------------------------------------------------------------------------- #
# нормализация
# --------------------------------------------------------------------------- #
def _video_id(value: str) -> str:
    if not value:
        return ""
    if "watch?v=" in value:
        return value.split("watch?v=")[1].split("&")[0]
    return value.strip("/").split("/")[-1]


def _piped_track(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    if (item.get("type") or "stream") != "stream":
        return None
    vid = _video_id(item.get("url") or item.get("id") or "")
    if not vid:
        return None
    duration = item.get("duration")
    thumb = item.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return {
        "id": "yt:" + vid,
        "title": (item.get("title") or "").strip() or vid,
        "artist": (item.get("uploaderName") or item.get("uploader") or "YouTube").strip(),
        "duration": int(duration) if isinstance(duration, (int, float)) and duration > 0 else None,
        "views": item.get("views"),
        "stats_kind": "views",
        "thumbnail": thumb,
        "source": "youtube",
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


def _invidious_track(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    vid = item.get("videoId")
    if not vid:
        return None
    duration = item.get("lengthSeconds")
    return {
        "id": "yt:" + vid,
        "title": (item.get("title") or "").strip() or vid,
        "artist": (item.get("author") or "YouTube").strip(),
        "duration": int(duration) if duration else None,
        "views": item.get("viewCount"),
        "stats_kind": "views",
        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "source": "youtube",
        "url": f"https://www.youtube.com/watch?v={vid}",
    }


# --------------------------------------------------------------------------- #
# поиск
# --------------------------------------------------------------------------- #
async def search(query: str, limit: int = 25, *, videos: bool = False) -> list[dict]:
    """Поиск на Piped/Invidious.

    videos=True — только обычные видео. Для клипов это обязательно: фильтр
    music_songs отдаёт авто-треки каталога («- Topic») со статичной обложкой.
    """
    query = (query or "").strip()
    if not query or not AIOHTTP_OK:
        return []

    try:
        if videos:
            data = await _get(PIPED, "/search", {"q": query, "filter": "videos"})
            tracks = [t for t in (_piped_track(i) for i in ((data or {}).get("items") or [])) if t]
            if tracks:
                return _dedupe(tracks)[:limit]
            raise RuntimeError("Piped returned no videos")
        data = await _get(PIPED, "/search", {"q": query, "filter": "music_songs"})
        items = (data or {}).get("items") or []
        tracks = [t for t in (_piped_track(i) for i in items) if t]
        if len(tracks) < max(6, limit // 3):
            # на некоторых узлах фильтр music_songs пустой — берём обычные видео
            data = await _get(PIPED, "/search", {"q": query, "filter": "videos"})
            tracks += [t for t in (_piped_track(i) for i in ((data or {}).get("items") or [])) if t]
        if tracks:
            return _dedupe(tracks)[:limit]
    except Exception as exc:
        log.warning("[piped] search %r: %s", query, exc)

    try:
        data = await _get(INVIDIOUS, "/api/v1/search", {"q": query, "type": "video"})
        tracks = [t for t in (_invidious_track(i) for i in (data or [])) if t]
        return _dedupe(tracks)[:limit]
    except Exception as exc:
        log.warning("[invidious] search %r: %s", query, exc)
    return []


def _dedupe(tracks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for track in tracks:
        if track["id"] in seen:
            continue
        seen.add(track["id"])
        out.append(track)
    return out


# --------------------------------------------------------------------------- #
# stream
# --------------------------------------------------------------------------- #
def _pick(streams: list[dict], key_url="url", key_mime="mimeType") -> dict | None:
    from .audio_quality import pick
    candidates=[]
    for item in streams or []:
        if not isinstance(item,dict) or not item.get(key_url):continue
        mime=str(item.get(key_mime) or '')
        if (mime and not mime.startswith('audio')) or 'm3u8' in str(item[key_url]):continue
        candidates.append(item)
    def rate(item):
        try:
            value=float(item.get('bitrate') or item.get('audioBitrate') or 0)
            return value*1000 if 0<value<1000 else value
        except (ValueError,TypeError):return 0
    return pick(candidates,rate)


async def stream(video_id: str) -> dict:
    """Прямая ссылка на аудиодорожку + длительность и название."""
    if not AIOHTTP_OK:
        raise RuntimeError("aiohttp is unavailable")

    try:
        data = await _get(PIPED, f"/streams/{video_id}")
        chosen = _pick((data or {}).get("audioStreams") or [])
        if chosen:
            return {
                "url": chosen["url"],
                "headers": {"User-Agent": UA},
                "size": int(chosen.get("contentLength") or 0) or None,
                "mime": (chosen.get("mimeType") or "audio/mp4").split(";")[0],
                "duration": int((data or {}).get("duration") or 0) or None,
                "title": (data or {}).get("title"),
                "artist": (data or {}).get("uploader"),
                "related": [t for t in (_piped_track(i) for i in
                                        ((data or {}).get("relatedStreams") or [])) if t],
            }
    except Exception as exc:
        log.warning("[piped] stream %s: %s", video_id, exc)

    data = await _get(INVIDIOUS, f"/api/v1/videos/{video_id}")
    formats = [f for f in ((data or {}).get("adaptiveFormats") or [])
               if str(f.get("type") or "").startswith("audio")]
    chosen = _pick(formats, key_mime="type")
    if not chosen:
        raise RuntimeError("no audio track")
    return {
        "url": chosen["url"],
        "headers": {"User-Agent": UA},
        "size": int(chosen.get("clen") or 0) or None,
        "mime": str(chosen.get("type") or "audio/mp4").split(";")[0],
        "duration": int((data or {}).get("lengthSeconds") or 0) or None,
        "title": (data or {}).get("title"),
        "artist": (data or {}).get("author"),
        "related": [t for t in (_invidious_track(i) for i in
                                ((data or {}).get("recommendedVideos") or [])) if t],
    }


def _height(item: dict) -> int:
    value = item.get("height") or item.get("quality") or item.get("qualityLabel") or 0
    found = __import__("re").search(r"(\d{3,4})", str(value))
    return int(found.group(1)) if found else 0


def _progressive(items: list[dict], ceiling: int, *, invidious: bool = False) -> dict | None:
    choices = []
    for item in items or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        mime = str(item.get("type") if invidious else item.get("mimeType") or "")
        if mime and not mime.startswith("video/"):
            continue
        if not invidious and item.get("videoOnly") is True:
            continue
        if "m3u8" in str(item.get("url") or ""):
            continue
        height = _height(item)
        if height and height <= ceiling:
            choices.append((height, int(item.get("bitrate") or 0), item))
    if not choices:
        return None
    choices.sort(key=lambda row: (row[0], row[1]))
    return choices[-1][2]


async def _one_json(host: str, path: str, timeout: float = 8.0) -> Any:
    session = await http()
    async with session.get(host + path, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"])[:120])
    return data


async def _race_json(hosts: list[str], path: str) -> Any:
    """First healthy public node wins; blocked nodes no longer add their timeouts."""
    tasks = {asyncio.create_task(_one_json(host, path)): host for host in _order(hosts)[:4]}
    errors = []
    try:
        while tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                host = tasks.pop(task)
                try:
                    data = task.result()
                except Exception as exc:
                    _blame(host)
                    errors.append(str(exc))
                    continue
                for other in pending:
                    other.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                return data
        raise RuntimeError("all instances failed: " + (errors[-1] if errors else "no nodes"))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


# --------------------------------------------------------------------------- #
# прямой запрос к плееру YouTube (Innertube)
# --------------------------------------------------------------------------- #
# Публичные узлы Piped и Invidious давно отвечают 403 через один раз, а запуск
# yt-dlp — это отдельный процесс и секунды ожидания. Тот же ответ плеера можно
# спросить у YouTube напрямую: клиенты ниже отдают совмещённую дорожку готовой
# ссылкой, без расшифровки подписи. Это самый быстрый путь к клипу: один
# POST-запрос, ответ за десятые доли секунды.
INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"

_INNERTUBE_CLIENTS = (
    {
        "name": "ANDROID_VR", "number": "28", "version": "1.62.27",
        "context": {"clientName": "ANDROID_VR", "clientVersion": "1.62.27",
                    "androidSdkVersion": 32, "osName": "Android",
                    "osVersion": "12", "deviceMake": "Oculus",
                    "deviceModel": "Quest 3"},
        "agent": ("com.google.android.apps.youtube.vr.oculus/1.62.27 "
                  "(Linux; U; Android 12; GB) gzip"),
    },
    {
        "name": "IOS", "number": "5", "version": "20.03.02",
        "context": {"clientName": "IOS", "clientVersion": "20.03.02",
                    "deviceMake": "Apple", "deviceModel": "iPhone16,2",
                    "osName": "iPhone", "osVersion": "18.2.1.22C161"},
        "agent": ("com.google.ios.youtube/20.03.02 "
                  "(iPhone16,2; U; CPU iOS 18_2_1 like Mac OS X)"),
    },
)


async def _innertube(video_id: str, client: dict, timeout: float = 10.0) -> dict:
    session = await http()
    body = {
        "context": {"client": {**client["context"], "hl": "en", "gl": "US"}},
        "videoId": video_id, "contentCheckOk": True, "racyCheckOk": True,
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": client["agent"],
        "X-YouTube-Client-Name": client["number"],
        "X-YouTube-Client-Version": client["version"],
        "Origin": "https://www.youtube.com",
    }
    async with session.post(INNERTUBE_URL, json=body, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    status = (data or {}).get("playabilityStatus") or {}
    if str(status.get("status") or "OK") not in ("OK", "LIVE_STREAM_OFFLINE"):
        raise RuntimeError(str(status.get("reason") or status.get("status") or "unplayable"))
    return data or {}


def _innertube_progressive(data: dict, ceiling: int) -> dict | None:
    """Совмещённая дорожка с готовой ссылкой (подпись не требуется)."""
    choices = []
    for item in ((data.get("streamingData") or {}).get("formats") or []):
        if not isinstance(item, dict) or not item.get("url"):
            continue
        mime = str(item.get("mimeType") or "")
        if mime and not mime.startswith("video/"):
            continue
        height = int(item.get("height") or 0)
        if height and height <= ceiling:
            choices.append((height, int(item.get("bitrate") or 0), item))
    if not choices:
        return None
    choices.sort(key=lambda row: (row[0], row[1]))
    return choices[-1][2]


async def innertube_video(video_id: str, quality: int = 720) -> dict:
    """Клип напрямую от плеера YouTube: ссылка, размер кадра и длительность."""
    if not AIOHTTP_OK:
        raise RuntimeError("aiohttp is unavailable")
    ceiling = max(144, min(int(quality or 720), 2160))
    errors = []
    for client in _INNERTUBE_CLIENTS:
        try:
            data = await _innertube(video_id, client)
        except Exception as exc:
            errors.append(f"{client['name']}: {exc}")
            continue
        item = _innertube_progressive(data, ceiling)
        if not item:
            errors.append(f"{client['name']}: no progressive video")
            continue
        details = data.get("videoDetails") or {}
        return {
            "url": item["url"],
            "headers": {"User-Agent": client["agent"]},
            "mime": str(item.get("mimeType") or "video/mp4").split(";")[0],
            "height": int(item.get("height") or 0),
            "width": int(item.get("width") or 0),
            "size": int(item.get("contentLength") or 0) or None,
            "duration": int(details.get("lengthSeconds") or 0) or None,
        }
    raise RuntimeError(errors[-1] if errors else "no progressive video")


def pick_dash(items: list[dict], ceiling: int, agent: str = "") -> dict | None:
    """Лучшая пара «видео без звука + звук» не выше нужной высоты.

    Берётся именно запрошенная высота (или ближайшая ниже, если ролик в ней
    не выложен). Кодек: VP9 в WebM — вдвое легче H.264 при той же картинке,
    его играют и Chrome, и Edge WebView2; на macOS берём H.264.
    """
    import sys
    vids = [f for f in items if isinstance(f, dict) and f.get("url")
            and str(f.get("mimeType") or "").startswith("video/")
            and 0 < int(f.get("height") or 0) <= ceiling]
    if not vids:
        return None
    top = max(int(f["height"]) for f in vids)

    def rank(f: dict) -> tuple:
        mime = str(f.get("mimeType") or "")
        vp9 = "vp9" in mime or "vp09" in mime
        avc = "avc1" in mime
        if sys.platform == "darwin":
            kind = 0 if avc else 1 if vp9 else 2
        else:
            kind = 0 if vp9 else 1 if avc else 2
        return (kind, -int(f.get("bitrate") or 0))
    video = sorted((f for f in vids if int(f["height"]) == top), key=rank)[0]
    webm = "webm" in str(video.get("mimeType") or "")
    audios = [f for f in items if isinstance(f, dict) and f.get("url")
              and str(f.get("mimeType") or "").startswith("audio/")]
    if not audios:
        return None
    want = "audio/webm" if webm else "audio/mp4"
    pool = [f for f in audios if str(f["mimeType"]).startswith(want)] or audios
    pool = [f for f in pool if (f.get("audioTrack") or {}).get("audioIsDefault", True)] or pool
    audio = max(pool, key=lambda f: int(f.get("bitrate") or 0))
    both_webm = webm and "webm" in str(audio.get("mimeType") or "")

    def part(f: dict) -> dict:
        return {"url": f["url"], "headers": {"User-Agent": agent} if agent else {},
                "mime": str(f.get("mimeType") or "").split(";")[0],
                "height": int(f.get("height") or 0), "width": int(f.get("width") or 0),
                "size": int(f.get("contentLength") or 0) or None}
    return {"video": part(video), "audio": part(audio),
            "container": "webm" if both_webm else "mp4"}


async def innertube_dash(video_id: str, quality: int = 1080, check=None) -> dict:
    """Раздельные дорожки прямо от плеера YouTube (ANDROID_VR / IOS)."""
    if not AIOHTTP_OK:
        raise RuntimeError("aiohttp is unavailable")
    ceiling = max(144, min(int(quality or 1080), 4320))
    errors = []
    for client in _INNERTUBE_CLIENTS:
        try:
            data = await _innertube(video_id, client)
        except Exception as exc:
            errors.append(f"{client['name']}: {exc}")
            continue
        pair = pick_dash((data.get("streamingData") or {}).get("adaptiveFormats") or [],
                         ceiling, client["agent"])
        if pair:
            pair["duration"] = int((data.get("videoDetails") or {}).get("lengthSeconds") or 0) or None
            if check is not None:
                try:
                    await check(pair)
                except Exception as exc:
                    errors.append(f"{client['name']}: {exc}")
                    continue
            return pair
        errors.append(f"{client['name']}: no separate tracks with links")
    raise RuntimeError(errors[-1] if errors else "no separate tracks")


async def mirror_dash(video_id: str, quality: int = 1080, check=None) -> dict:
    """Раздельные дорожки через Piped / Invidious — запасной путь, когда сам
    YouTube просит подтвердить, что вы не бот."""
    ceiling = max(144, min(int(quality or 1080), 4320))

    async def piped():
        data = await _race_json(PIPED, f"/streams/{video_id}") or {}
        rows = [dict(i, bitrate=int(i.get("bitrate") or 0)) for i in (data.get("videoStreams") or [])
                if isinstance(i, dict) and i.get("videoOnly") is True and i.get("url")
                and "m3u8" not in str(i["url"])]
        rows += [dict(i, bitrate=int(i.get("bitrate") or 0)) for i in (data.get("audioStreams") or [])
                 if isinstance(i, dict) and i.get("url") and "m3u8" not in str(i["url"])]
        pair = pick_dash(rows, ceiling, UA)
        if not pair:
            raise RuntimeError("Piped: no separate tracks")
        pair["duration"] = int(data.get("duration") or 0) or None
        return pair

    async def invidious():
        data = await _race_json(INVIDIOUS, f"/api/v1/videos/{video_id}") or {}
        rows = []
        for i in (data.get("adaptiveFormats") or []):
            if not isinstance(i, dict) or not i.get("url"):
                continue
            rows.append({"url": i["url"], "mimeType": i.get("type") or "",
                         "height": _height({"quality": i.get("qualityLabel") or i.get("resolution")})
                                   if str(i.get("type") or "").startswith("video/") else 0,
                         "width": 0, "bitrate": int(i.get("bitrate") or 0),
                         "contentLength": i.get("clen")})
        pair = pick_dash(rows, ceiling, UA)
        if not pair:
            raise RuntimeError("Invidious: no separate tracks")
        pair["duration"] = int(data.get("lengthSeconds") or 0) or None
        return pair

    async def run(fn):
        pair = await fn()
        if check is not None:
            await check(pair)
        return pair

    tasks = {asyncio.create_task(run(piped)), asyncio.create_task(run(invidious))}
    errors = []
    try:
        while tasks:
            done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    return task.result()
                except Exception as exc:
                    errors.append(str(exc))
        raise RuntimeError(errors[-1] if errors else "no mirror answered")
    finally:
        for task in tasks:
            task.cancel()


async def video(video_id: str, quality: int = 480) -> dict:
    """Fast progressive video+audio URL from Piped or Invidious."""
    ceiling = max(144, min(int(quality or 480), 2160))

    async def piped():
        data = await _race_json(PIPED, f"/streams/{video_id}")
        item = _progressive((data or {}).get("videoStreams") or [], ceiling)
        if not item:
            raise RuntimeError("Piped returned no progressive video")
        return {
            "url": item["url"], "headers": {"User-Agent": UA},
            "mime": str(item.get("mimeType") or "video/mp4").split(";")[0],
            "height": _height(item), "width": int(item.get("width") or 0),
            "duration": int((data or {}).get("duration") or 0) or None,
        }

    async def invidious():
        data = await _race_json(INVIDIOUS, f"/api/v1/videos/{video_id}")
        item = _progressive((data or {}).get("formatStreams") or [], ceiling, invidious=True)
        if not item:
            raise RuntimeError("Invidious returned no progressive video")
        return {
            "url": item["url"], "headers": {"User-Agent": UA},
            "mime": str(item.get("type") or "video/mp4").split(";")[0],
            "height": _height(item), "width": int(item.get("width") or 0),
            "duration": int((data or {}).get("lengthSeconds") or 0) or None,
        }

    # Три независимых пути идут вместе: прямой плеер YouTube, Piped и
    # Invidious. Побеждает первый ответивший, остальные снимаются.
    tasks = {asyncio.create_task(innertube_video(video_id, ceiling)),
             asyncio.create_task(piped()), asyncio.create_task(invidious())}
    errors = []
    try:
        while tasks:
            done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    result = task.result()
                except Exception as exc:
                    errors.append(str(exc))
                    continue
                for other in tasks:
                    other.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                return result
        raise RuntimeError(errors[-1] if errors else "no progressive video")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def related(video_id: str, limit: int = 25) -> list[dict]:
    try:
        info = await stream(video_id)
        return (info.get("related") or [])[:limit]
    except Exception:
        return []


async def channel(channel_url: str, limit: int = 30) -> list[dict]:
    """Треки канала по ссылке вида https://www.youtube.com/channel/UC..."""
    ident = channel_url.rstrip("/").split("/")[-1]
    try:
        data = await _get(PIPED, f"/channel/{ident}")
        items = (data or {}).get("relatedStreams") or []
        return [t for t in (_piped_track(i) for i in items) if t][:limit]
    except Exception:
        pass
    try:
        data = await _get(INVIDIOUS, f"/api/v1/channels/{ident}/videos")
        items = (data or {}).get("videos") or data or []
        return [t for t in (_invidious_track(i) for i in items) if t][:limit]
    except Exception:
        return []


async def health() -> dict:
    """Какие узлы отвечают прямо сейчас."""
    live = 0
    for host in PIPED + INVIDIOUS:
        if _penalty.get(host, 0) < time.monotonic():
            live += 1
    return {"instances": len(PIPED) + len(INVIDIOUS), "ready": live}
