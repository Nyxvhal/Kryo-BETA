"""
ytlibs.py — запасные движки YouTube внутри процесса (без внешнего бинарника).

Бинарник yt-dlp скачивается отдельно и иногда недоступен (GitHub заблокирован,
идёт обновление, антивирус). Эти движки стоят в самом приложении и
подключаются как ещё один независимый путь к ссылке на клип:

  * yt_dlp   — та же библиотека, что и бинарник, но импортом: стартует сразу,
               ничего не качает, прокси и cookies берёт из настроек;
  * pytubefix — отдельная реализация плеера YouTube с набором клиентов
               (ANDROID_VR, TV, MWEB, IOS, WEB). Когда у одного клиента бот-
               проверка, другой часто отвечает.

Оба отдают совмещённую дорожку (видео+звук одним файлом) — её можно
перематывать и докачивать обычными Range-запросами. Каждый движок
необязателен: нет пакета — путь просто пропускается.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import netproxy, ytcookies

log = logging.getLogger("kryonyx.ytlibs")

_PYTUBE_CLIENTS = ("ANDROID_VR", "TV", "MWEB", "IOS")
_YTDLP_CLIENTS = (["android_vr"], ["tv_simply", "web_safari"], ["ios"], ["mweb"])
_AGENT = {
    "ANDROID_VR": "com.google.android.apps.youtube.vr.oculus/1.62.27 (Linux; U; Android 12; GB) gzip",
    "IOS": "com.google.ios.youtube/20.03.02 (iPhone16,2; U; CPU iOS 18_2_1 like Mac OS X)",
}
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def available() -> dict[str, bool]:
    out = {}
    for name in ("yt_dlp", "pytubefix"):
        try:
            __import__(name)
            out[name] = True
        except Exception:
            out[name] = False
    return out


def _watch(video_id: str) -> str:
    return video_id if str(video_id).startswith("http") else \
        f"https://www.youtube.com/watch?v={video_id}"


# --------------------------------------------------------------------------- #
# yt_dlp как библиотека
# --------------------------------------------------------------------------- #
def _ytdlp_sync(video_id: str, ceiling: int, clients: list[str]) -> dict:
    import yt_dlp
    opts: dict[str, Any] = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "skip_download": True, "socket_timeout": 12, "retries": 1,
        "extractor_retries": 1, "geo_bypass": True,
        "extractor_args": {"youtube": {"player_client": clients}},
        "format": (f"best[ext=mp4][height<={ceiling}][vcodec!=none][acodec!=none]"
                   f"/best[height<={ceiling}][vcodec!=none][acodec!=none]"),
    }
    proxy = netproxy.url()
    if proxy:
        opts["proxy"] = proxy
    cookies = ytcookies.path()
    if cookies:
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(_watch(video_id), download=False)
    picked = data if data.get("url") else None
    if picked is None:
        rows = [f for f in (data.get("requested_formats") or data.get("formats") or [])
                if isinstance(f, dict) and f.get("url")
                and f.get("vcodec") not in (None, "none")
                and f.get("acodec") not in (None, "none")
                and not str(f.get("protocol") or "").startswith(("m3u8", "http_dash"))
                and (f.get("height") or 0) <= ceiling]
        rows.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
        picked = rows[-1] if rows else None
    if not picked:
        raise RuntimeError("yt_dlp: no progressive video")
    return {
        "url": picked["url"],
        "headers": dict(picked.get("http_headers") or data.get("http_headers") or {}),
        "mime": "video/webm" if picked.get("ext") == "webm" else "video/mp4",
        "height": int(picked.get("height") or 0),
        "width": int(picked.get("width") or 0),
        "size": int(picked.get("filesize") or picked.get("filesize_approx") or 0) or None,
        "duration": int(data["duration"]) if data.get("duration") else None,
    }


async def ytdlp_video(video_id: str, quality: int = 720) -> dict:
    last: Exception | None = None
    for clients in _YTDLP_CLIENTS:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_ytdlp_sync, video_id, quality, clients), 25)
        except ImportError:
            raise RuntimeError("yt_dlp library is not installed") from None
        except Exception as exc:
            last = exc
            if "not a bot" in str(exc).lower() and not ytcookies.path():
                break           # другой клиент ту же стену не снимет
    raise RuntimeError(f"yt_dlp: {last}")


# --------------------------------------------------------------------------- #
# pytubefix
# --------------------------------------------------------------------------- #
def _pytube_sync(video_id: str, ceiling: int, client: str) -> dict:
    from pytubefix import YouTube
    kwargs: dict[str, Any] = {"client": client}
    proxies = netproxy.requests_proxies()
    if proxies:
        kwargs["proxies"] = proxies
    cookies = ytcookies.path()
    if cookies:
        kwargs["use_oauth"] = False
    yt = YouTube(_watch(video_id), **kwargs)
    streams = [s for s in yt.streams.filter(progressive=True)
               if s.url and (s.resolution or "").endswith("p")]
    streams = [s for s in streams if int((s.resolution or "0p")[:-1] or 0) <= ceiling] or streams
    if not streams:
        raise RuntimeError(f"pytubefix {client}: no progressive video")
    best = max(streams, key=lambda s: (int((s.resolution or "0p")[:-1] or 0), s.bitrate or 0))
    return {
        "url": best.url,
        "headers": {"User-Agent": _AGENT.get(client, _BROWSER_UA)},
        "mime": "video/mp4",
        "height": int((best.resolution or "0p")[:-1] or 0),
        "width": 0,
        "size": getattr(best, "filesize", None) or None,
        "duration": int(yt.length or 0) or None,
    }


async def pytube_video(video_id: str, quality: int = 720) -> dict:
    last: Exception | None = None
    for client in _PYTUBE_CLIENTS:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_pytube_sync, video_id, quality, client), 20)
        except ImportError:
            raise RuntimeError("pytubefix is not installed") from None
        except Exception as exc:
            last = exc
            if "bot" in str(exc).lower():
                break
    raise RuntimeError(f"pytubefix: {last}")


# --------------------------------------------------------------------------- #
# раздельные дорожки (видео и звук) — для клипов выше 360p
# --------------------------------------------------------------------------- #
def dash_from_formats(data: dict, ceiling: int) -> dict:
    """Пара дорожек из ответа yt-dlp (библиотеки или бинарника)."""
    from . import youtube
    rows = []
    heads: dict[str, dict] = {}
    for f in (data.get("formats") or []):
        if not isinstance(f, dict) or not f.get("url"):
            continue
        if not str(f.get("protocol") or "https").startswith("http") \
                or "m3u8" in str(f.get("protocol")) or "dash" in str(f.get("protocol")):
            continue
        vcodec, acodec = f.get("vcodec") or "none", f.get("acodec") or "none"
        ext = str(f.get("ext") or "")
        if vcodec != "none" and acodec == "none":
            mime = f'video/{"webm" if ext == "webm" else "mp4"}; codecs="{vcodec}"'
        elif acodec != "none" and vcodec == "none":
            mime = f'audio/{"webm" if ext in ("webm", "opus") else "mp4"}; codecs="{acodec}"'
        else:
            continue
        rows.append({"url": f["url"], "mimeType": mime, "height": f.get("height"),
                     "width": f.get("width"), "bitrate": int((f.get("tbr") or 0) * 1000),
                     "contentLength": f.get("filesize") or f.get("filesize_approx")})
        heads[f["url"]] = dict(f.get("http_headers") or data.get("http_headers") or {})
    pair = youtube.pick_dash(rows, ceiling)
    if not pair:
        raise RuntimeError("no separate video and audio tracks")
    for key in ("video", "audio"):
        pair[key]["headers"] = heads.get(pair[key]["url"]) or {}
    pair["duration"] = int(data["duration"]) if data.get("duration") else None
    return pair


def _dash_sync(video_id: str, ceiling: int, clients: list[str]) -> dict:
    import yt_dlp
    opts: dict[str, Any] = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "skip_download": True, "socket_timeout": 12, "retries": 1,
        "extractor_retries": 1, "geo_bypass": True, "format": "all",
        "extractor_args": {"youtube": {"player_client": clients}},
    }
    proxy = netproxy.url()
    if proxy:
        opts["proxy"] = proxy
    cookies = ytcookies.path()
    if cookies:
        opts["cookiefile"] = cookies
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(_watch(video_id), download=False)
    return dash_from_formats(data, ceiling)


async def dash(video_id: str, quality: int = 1080, check=None) -> dict:
    """Дорожки клипа через библиотеку yt_dlp (несколько клиентов плеера)."""
    last: Exception | None = None
    for clients in _YTDLP_CLIENTS:
        try:
            pair = await asyncio.wait_for(
                asyncio.to_thread(_dash_sync, video_id, quality, clients), 30)
            if check is not None:
                await check(pair)
            return pair
        except ImportError:
            raise RuntimeError("yt_dlp library is not installed") from None
        except Exception as exc:
            last = exc
            if "not a bot" in str(exc).lower() and not ytcookies.path():
                break
    raise RuntimeError(f"yt_dlp: {last}")


async def video(video_id: str, quality: int = 720) -> dict:
    """Первый ответивший из встроенных движков; недоступные пропускаются."""
    have = available()
    tasks = []
    if have["yt_dlp"]:
        tasks.append(asyncio.create_task(ytdlp_video(video_id, quality)))
    if have["pytubefix"]:
        tasks.append(asyncio.create_task(pytube_video(video_id, quality)))
    if not tasks:
        raise RuntimeError("no built-in YouTube engine is installed")
    pending = set(tasks)
    errors: list[str] = []
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    media = task.result()
                except Exception as exc:
                    errors.append(str(exc))
                    continue
                if media.get("url"):
                    return media
        raise RuntimeError(errors[-1] if errors else "no built-in engine answered")
    finally:
        for task in pending:
            task.cancel()
