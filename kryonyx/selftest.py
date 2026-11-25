"""
selftest.py — живая проверка плагинов: «а он вообще работает?».

Каждый плагин умеет один маленький настоящий запрос к своему сервису:
поиск из трёх результатов, один ответ метаданных, один текст песни, один
пинг скробблера. Проверка возвращает состояние, время ответа и короткий
комментарий, поэтому в настройках видно не «включён», а «работает».

Ничего не сохраняется и не отправляется: скробблеры и Rich Presence
проверяются их же тестовыми вызовами из integrations.py.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from . import convert, extras, integrations, library, plugins, providers, spotify

log = logging.getLogger(__name__)

TIMEOUT = 25.0

# Эти проверки идут через общие сборщики, которые сами пропускают выключенные
# плагины, поэтому «принудительно» их не проверить — честно говорим об этом.
ENABLED_ONLY = {"audius-trending", "deezer-charts", "radio-top"}

# ---------------------------------------------------------------- проверки --
PROBE_QUERY = "daft punk around the world"
# У каталогов Creative Commons и радиостанций своя специфика: там популярной
# поп-музыки нет, поэтому пробуем нейтральное слово.
SOURCE_QUERY = {"jamendo": "piano", "radio": "jazz", "archive": "live concert"}


def _note(state: str, text: str, **args) -> dict:
    """Ответ проверки: английский шаблон (ключ словаря интерфейса) + данные.

    Клиент переводит шаблон и только потом подставляет данные. Раньше
    заметки были русскими и на остальных языках так и показывались.
    """
    out = text
    for key, value in args.items():
        out = out.replace("{" + key + "}", str(value))
    result = {"state": state, "note": out}
    if args:
        result["note_key"], result["note_args"] = text, {k: str(v) for k, v in args.items()}
    else:
        result["note_key"] = text
    return result


async def _search_source(source: str) -> dict:
    query = SOURCE_QUERY.get(source, PROBE_QUERY)
    if source == providers.YOUTUBE:
        tracks = await providers.search_youtube(query, 3)
    elif source == providers.SOUNDCLOUD:
        tracks = await providers.search_soundcloud(query, 3)
    elif source == providers.SPOTIFY:
        # library.search() ничего не знает про Spotify и молча отдавал
        # пустой список за 0 мс — проверка врала «ничего не нашёл».
        tracks = await spotify.search(query, 3)
    else:
        tracks = await library.search(source, query, 3)
    count = len([t for t in tracks if t])
    if not count:
        return _note("warn", "the service answered, but found nothing for “{query}”",
                     query=query)
    example = tracks[0]
    return _note("ok", "found {count}: {track}", count=count,
                 track=f"{example.get('artist')} — {example.get('title')}")


def _source_probe(source: str) -> Callable[[], Awaitable[dict]]:
    async def probe() -> dict:
        result = await _search_source(source)
        # У Jamendo бесплатный демо-ключ отдаёт пустой каталог: честно говорим,
        # что нужен свой Client ID, а не «сервис сломался».
        if source == "jamendo" and result.get("state") != "ok" \
                and not plugins.config("jamendo").get("client_id"):
            return _note("off", "needs your own Client ID from developer.jamendo.com — "
                                "the shared demo key returns an empty catalogue")
        return result
    return probe


# Каждый источник метаданных проверяем его же запросом, без общего кэша.
_META_PROBES = {
    "deezer": lambda: extras._deezer("Daft Punk", "Around the World"),
    "musicbrainz": lambda: extras._musicbrainz("Daft Punk", "Around the World"),
    "discogs": lambda: extras._discogs("Daft Punk", "Around the World"),
    "wikipedia": lambda: extras._wikipedia("Daft Punk"),
}


async def _probe_metadata(provider: str) -> dict:
    data = await _META_PROBES[provider]()
    if not data:
        if provider == "discogs" and not plugins.config("discogs").get("token"):
            return _note("off", "needs a personal Discogs token")
        return _note("warn", "the service gave no data for the test track")
    got = data.get("album") or data.get("title") or data.get("summary") or ""
    if got:
        return _note("ok", "metadata received: {value}", value=str(got)[:60])
    return _note("ok", "metadata received")


async def _probe_lrclib() -> dict:
    data = await extras._json("https://lrclib.net/api/search",
                              {"q": PROBE_QUERY}, headers={"User-Agent": extras.UA})
    rows = data if isinstance(data, list) else []
    if not rows:
        return _note("warn", "no lyrics for the test query")
    synced = sum(1 for r in rows if r.get("syncedLyrics"))
    return _note("ok", "found {count} lyrics, {synced} with timing",
                 count=len(rows), synced=synced)


async def _probe_lyricsovh() -> dict:
    lines = await extras.plain_lyrics("Daft Punk", "Around the World")
    if not lines:
        return _note("warn", "lyrics not found")
    return _note("ok", "lyrics received, {count} lines", count=len(lines))


async def _probe_discovery(row_id: str) -> dict:
    rows = await extras.discovery_rows(8)
    for row in rows:
        if row.get("id") == row_id or row.get("plugin") == row_id:
            count = len(row.get("tracks") or row.get("items") or [])
            if count:
                return _note("ok", "the row is built, {count} tracks", count=count)
            return _note("warn", "the row is empty")
    return _note("warn", "the row did not arrive — the service is down or the plugin is off")


async def _probe_integration(pid: str) -> dict:
    data = await integrations.test(pid)
    if data.get("ok"):
        if data.get("message"):
            return {"state": "ok", "note": data["message"]}
        return _note("ok", "connected")
    message = data.get("message") or data.get("error") or "not set up"
    # Раньше «не настроено» узнавали по русскому «настро», а интеграции
    # отвечают по-английски («A token is required»), и пустые поля
    # показывались красной ошибкой вместо «не настроено».
    lowered = message.lower()
    off = any(word in lowered for word in ("required", "not set", "not configured", "настро"))
    return {"state": "off" if off else "fail", "note": message}


async def _probe_convert(service: str, url: str) -> dict:
    data = await convert.fetch(url)
    count = len(data.get("items") or [])
    if not count:
        return _note("warn", "the link was read, but there are no tracks")
    return _note("ok", "read “{name}”, {count} tracks", name=data.get("name"), count=count)


async def _probe_m3u() -> dict:
    text = extras.playlist_m3u("Selftest", [
        {"title": "Around the World", "artist": "Daft Punk", "duration": 428,
         "id": "yt:test"}])
    if text.startswith("#EXTM3U") and "Around the World" in text:
        return _note("ok", "the file is built locally, no network needed")
    return _note("fail", "the export returned an empty file")


def _probe_map() -> dict[str, Callable[[], Awaitable[dict]]]:
    probes: dict[str, Callable[[], Awaitable[dict]]] = {}
    for plugin in plugins.catalog():
        if plugin.get("source") and not plugin.get("custom"):
            probes[plugin["id"]] = _source_probe(plugin["source"])
    probes.update({
        "deezer": lambda: _probe_metadata("deezer"),
        "musicbrainz": lambda: _probe_metadata("musicbrainz"),
        "discogs": lambda: _probe_metadata("discogs"),
        "wikipedia": lambda: _probe_metadata("wikipedia"),
        "lrclib": _probe_lrclib,
        "lyricsovh": _probe_lyricsovh,
        "audius-trending": lambda: _probe_discovery("audius-trending"),
        "deezer-charts": lambda: _probe_discovery("deezer-charts"),
        "radio-top": lambda: _probe_discovery("radio-top"),
        "listenbrainz": lambda: _probe_integration("listenbrainz"),
        "maloja": lambda: _probe_integration("maloja"),
        "lastfm": lambda: _probe_integration("lastfm"),
        "discord": lambda: _probe_integration("discord"),
        "mastodon": lambda: _probe_integration("mastodon"),
        "spotify-import": lambda: _probe_convert(
            "spotify", "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"),
        "youtube-import": lambda: _probe_convert(
            "youtube", "https://www.youtube.com/playlist?list=PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI"),
        "soundcloud-import": lambda: _probe_convert(
            "soundcloud", "https://soundcloud.com/jazzhopcafe/sets/anime-tributes-mix-series"),
        "m3u": _probe_m3u,
    })
    return probes


# ---------------------------------------------------------------- запуск --
async def check(pid: str, *, force: bool = False) -> dict:
    """Проверяет один плагин. Исключения превращаются в понятный ответ."""
    plugin = plugins.BY_ID.get(pid)
    if not plugin:
        raise ValueError("unknown plugin")
    base = {"id": pid, "name": plugin["name"],
            "installed": plugins.installed(pid), "enabled": plugins.enabled(pid)}
    # Свой плагин проверяет сам себя: его selftest() или один живой поиск.
    if plugin.get("custom"):
        from . import extplugins
        return {**base, **await extplugins.selftest(pid)}
    probe = _probe_map().get(pid)
    if probe is None:
        return {**base, **_note("skip", "nothing to check: the plugin works locally"), "ms": 0}
    off = not plugins.enabled(pid)
    if off and (not force or pid in ENABLED_ONLY):
        note = ("the plugin is off — it can be checked only when it is on"
                if pid in ENABLED_ONLY
                else "the plugin is off — turn it on to check it")
        return {**base, **_note("off", note), "ms": 0}
    if plugin.get("needs_ytdlp") and not providers.ytdlp_ready():
        return {**base, **_note("fail", "this build has no yt-dlp"), "ms": 0}

    started = time.monotonic()
    try:
        result = await asyncio.wait_for(probe(), TIMEOUT)
    except asyncio.TimeoutError:
        result = _note("fail", "no answer within {seconds} s", seconds=int(TIMEOUT))
    except Exception as exc:
        result = {"state": "fail", "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
    took = int((time.monotonic() - started) * 1000)
    if off:
        # Сервис ответил, но в самом приложении плагин сейчас не участвует.
        result = {**result,
                  "note": f"{result.get('note', '')} "
                          "(the plugin is off: checked directly, not used in the app)",
                  "off_note": "(the plugin is off: checked directly, not used in the app)"}
    log.info("[selftest] %s -> %s (%d ms) %s", pid, result.get("state"), took,
             result.get("note", ""))
    return {**base, **result, "ms": took}


async def check_all(ids: list[str] | None = None, *,
                    only_enabled: bool = True, force: bool = False) -> dict:
    """Проверяет все плагины (по умолчанию только включённые) параллельно.

    `force` — проверять и выключенные: запрос к сервису идёт напрямую, а в
    заметке видно, что в самом приложении плагин сейчас не работает.
    """
    if force:
        only_enabled = False
    wanted = [p["id"] for p in plugins.catalog()
              if (not ids or p["id"] in ids)
              and (not only_enabled or plugins.enabled(p["id"]))]
    semaphore = asyncio.Semaphore(5)

    async def one(pid: str) -> dict:
        async with semaphore:
            try:
                return await check(pid, force=force)
            except Exception as exc:
                return {"id": pid, "state": "fail", "ms": 0, "note": str(exc)[:160]}

    results = await asyncio.gather(*(one(pid) for pid in wanted))
    summary: dict[str, int] = {}
    for row in results:
        summary[row["state"]] = summary.get(row["state"], 0) + 1
    return {"items": list(results), "summary": summary,
            "checked": len(results), "at": time.time()}
