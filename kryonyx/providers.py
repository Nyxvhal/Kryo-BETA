"""
providers.py — поиск и разрешение музыки из подключённых плагинов.

Формат id трека:
    yt:<video_id>      YouTube
    sc:<b64(url)>      SoundCloud
    sp:<b64(uri)>      Spotify metadata (audio is matched to an open source)

Что здесь есть:
  * быстрый параллельный поиск с пагинацией (много результатов);
  * жёсткий фильтр SoundCloud Go+ (обрезанные 30-секундные превью);
  * подсказки запросов и карточки авторов из обоих сервисов;
  * страницы авторов (канал YouTube / профиль SoundCloud);
  * «радио» (YouTube Mix) для рекомендаций и бесконечной очереди;
  * кэш в памяти с TTL, чтобы повторный поиск был мгновенным.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from urllib.parse import parse_qs, urlsplit
import urllib.parse
import urllib.request
from typing import Any, Iterable

from . import extplugins, library, plugins, spotify, youtube, ytcookies, ytdlp_bin, ytmusic
from .paths import app_dir

log = logging.getLogger(__name__)

# yt-dlp импортируется лениво: его загрузка занимает 1–2 секунды, а окно
# приложения должно открываться сразу.
yt_dlp: Any = None
YTDLP_OK = True          # уточняется при первом обращении


def _ytdlp():
    global yt_dlp, YTDLP_OK
    if yt_dlp is None:
        try:
            import yt_dlp as module
            yt_dlp = module
            YTDLP_OK = True
        except Exception:  # pragma: no cover
            YTDLP_OK = False
    return yt_dlp


def ytdlp_ready() -> bool:
    return _ytdlp() is not None

YOUTUBE = "youtube"
SOUNDCLOUD = "soundcloud"
SPOTIFY = "spotify"
# Дополнительные библиотеки живут в library.py (Audius, Bandcamp, Internet Archive).
ALL_SOURCES = (YOUTUBE, SOUNDCLOUD, SPOTIFY) + library.LIBRARY_SOURCES
DEFAULT_SOURCES = (SOUNDCLOUD, SPOTIFY)


# --------------------------------------------------------------------------- #
# кэш
# --------------------------------------------------------------------------- #
class TTLCache:
    """Минимальный кэш в памяти: ключ -> (истекает, значение)."""

    def __init__(self, ttl: float = 600.0, maxsize: int = 512) -> None:
        self.ttl = ttl
        self.maxsize = maxsize
        self._data: dict[str, tuple[float, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str):
        hit = self._data.get(key)
        if not hit:
            return None
        if hit[0] < time.monotonic():
            self._data.pop(key, None)
            return None
        return hit[1]

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        if len(self._data) >= self.maxsize:
            # выкидываем самые старые записи, а не весь кэш
            for k in sorted(self._data, key=lambda k: self._data[k][0])[: self.maxsize // 4]:
                self._data.pop(k, None)
        self._data[key] = (time.monotonic() + (ttl or self.ttl), value)

    def lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

    def drop(self, key: str) -> None:
        self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()


_search_cache = TTLCache(ttl=900.0)
_page_cache = TTLCache(ttl=1800.0)
_stream_cache = TTLCache(ttl=4500.0, maxsize=256)   # прямые ссылки живут ~2ч
_suggest_cache = TTLCache(ttl=3600.0)

# Сколько страница автора имеет право собираться, прежде чем мы покажем то,
# что уже готово. Остальное догружается в фоне и попадает в кэш.
AUTHOR_DEADLINE = 6.0
# Жёсткий предел: дольше этого страница не ждёт даже полностью пустая.
AUTHOR_TIMEOUT = 16.0


# --------------------------------------------------------------------------- #
# base64 для ссылок SoundCloud
# --------------------------------------------------------------------------- #
def b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()


# --------------------------------------------------------------------------- #
# настройки yt-dlp
# --------------------------------------------------------------------------- #
_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "ignoreerrors": True,
    "socket_timeout": 8,
    "retries": 0,
    "extractor_retries": 0,
    "nocheckcertificate": True,
    "cachedir": False,
    "noprogress": True,
}

# Для поиска не нужны ни описание страницы, ни JS-плеер, ни субтитры — без них
# yt-dlp делает один запрос к API вместо нескольких и отвечает в разы быстрее.
_FLAT_OPTS = {
    **_BASE_OPTS,
    "extract_flat": "in_playlist",
    "lazy_playlist": True,
    "extractor_args": {
        "youtube": {
            "player_skip": ["configs", "webpage", "js"],
            "skip": ["hls", "dash", "translated_subs"],
        },
        "youtubetab": {"skip": ["webpage"]},
    },
}

# Только прямой HTTP-аудиопоток: HLS/DASH-манифесты браузер не проиграет.
_STREAM_OPTS = {
    **_BASE_OPTS,
    "noplaylist": True,
    "socket_timeout": 20,
    "format": "bestaudio[protocol^=http][acodec!=none]/bestaudio/best",
}

# Если Piped/Invidious недоступны, yt-dlp перебирает клиенты плеера YouTube.
_YT_CLIENTS = ("plain", "tv_simply", "web_safari", "android_vr", "ios", "mweb", "default")
_COOKIE_NAMES = ("youtube_cookies.txt", "cookies.txt")


def cookie_file() -> str | None:
    """Файл cookies — один на всё приложение (см. kryonyx/ytcookies.py)."""
    try:
        target = ytcookies.path()
    except Exception:
        target = None
    if target:
        return target
    for folder in (app_dir(), os.getcwd()):
        for name in _COOKIE_NAMES:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return path
    return None


def _opts(base: dict, client: str | None = None) -> dict:
    opts = dict(base)
    if client == "plain":
        # «Голый» запуск: без cookies и без особых клиентов.
        return opts
    cookies = cookie_file()
    if cookies:
        opts["cookiefile"] = cookies
    else:
        try:
            browser = ytcookies.browser()
        except Exception:
            browser = ""
        if browser:
            # The embedded yt-dlp path must use the same browser choice as
            # the external binary; otherwise fallback lost authentication.
            opts["cookiesfrombrowser"] = (browser,)
    if client and client not in ("default", "plain"):
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    return opts


def _extract(expr: str, opts: dict, client: str | None = None) -> dict | None:
    module = _ytdlp()
    if module is None:
        raise StreamError("yt-dlp is not available in this build")
    with module.YoutubeDL(_opts(opts, client)) as ydl:
        return ydl.extract_info(expr, download=False)


async def _aextract(expr: str, opts: dict, client: str | None = None) -> dict | None:
    return await asyncio.to_thread(_extract, expr, opts, client)


# --------------------------------------------------------------------------- #
# фильтр SoundCloud Go+ / превью
# --------------------------------------------------------------------------- #
_GO_PLUS_TITLE_RE = re.compile(r"(?<![a-z0-9])(?:go\+|go\s?plus\b)", re.I)
_PREVIEW_MIN_DURATION = 45          # полноценных треков короче почти не бывает
_SNIPPET_DURATIONS = (30, 31, 90)   # типичные длины обрезка Go+


def is_go_plus(entry: dict) -> bool:
    """True, если это Go+ / обрезанное превью SoundCloud, а не полный трек.

    SoundCloud отдаёт подписочные треки как 30-секундный «snip». Признаки
    проверяем по всем полям, которые встречаются в разных версиях yt-dlp:
    monetization_model, policy, availability и расхождение duration
    с full_duration.
    """
    if not entry:
        return False

    monetization = str(entry.get("monetization_model") or "").upper()
    if "SUB_HIGH_TIER" in monetization or "TIER" in monetization:
        return True

    policy = str(entry.get("policy") or "").upper()
    if policy in ("SNIP", "BLOCK", "MONETIZE_SNIP"):
        return True

    availability = str(entry.get("availability") or "").lower()
    if availability in ("subscriber_only", "premium_only", "needs_auth", "not_public"):
        return True

    duration = entry.get("duration")
    full = entry.get("full_duration")
    if duration and full and (full - duration) > 5:
        return True

    title = str(entry.get("title") or "")
    if _GO_PLUS_TITLE_RE.search(title):
        return True

    # Обрезки всегда ровно 30 с (иногда 90 с) — в каталоге это превью, не трек.
    if duration and int(duration) in _SNIPPET_DURATIONS and not entry.get("full_duration"):
        return True
    if duration and duration < _PREVIEW_MIN_DURATION:
        return True

    return False


# --------------------------------------------------------------------------- #
# нормализация трека
# --------------------------------------------------------------------------- #
_JUNK_RE = re.compile(
    r"\s*[\(\[]\s*(?:official\s*(?:music\s*)?video|official\s*audio|lyrics?(?:\s*video)?|"
    r"audio|video|hd|hq|4k|mv|visualizer|clip|премьера(?:\s*клипа)?|клип)\s*[\)\]]",
    re.I,
)
_FEAT_RE = re.compile(r"\s*[-–—]\s*topic$", re.I)


def _thumb(entry: dict, track_id: str = "") -> str | None:
    thumb = entry.get("thumbnail")
    if thumb:
        return thumb
    thumbs = entry.get("thumbnails") or []
    for t in reversed(thumbs):
        if t.get("url"):
            return t["url"]
    # «Плоская» выдача YouTube картинку иногда не присылает вовсе, но она
    # всегда доступна по id видео — восстанавливаем, а не оставляем пустую
    # плитку.
    vid = entry.get("id") or (track_id[3:] if track_id.startswith("yt:") else "")
    if vid and (track_id.startswith("yt:") or not track_id):
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return None


def _clean_title(raw: str) -> str:
    title = _JUNK_RE.sub("", raw or "").strip(" -–—|")
    return title or (raw or "Без названия")


def _split_artist_title(title: str, uploader: str) -> tuple[str, str]:
    """«Артист - Трек» из заголовка YouTube; иначе автор канала."""
    uploader = _FEAT_RE.sub("", uploader or "").strip() or "Неизвестный"
    for sep in (" - ", " – ", " — ", " -- "):
        if sep in title:
            left, right = title.split(sep, 1)
            left, right = left.strip(), right.strip()
            if 1 < len(left) < 60 and right:
                return right, left
    return title, uploader


def normalize(entry: dict, source: str, *, split: bool = True) -> dict | None:
    if not entry:
        return None

    if source == YOUTUBE:
        vid = entry.get("id") or ""
        if not vid or len(vid) > 24:
            return None
        track_id = "yt:" + vid
        page = entry.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
        author_url = entry.get("channel_url") or entry.get("uploader_url")
        author_id = entry.get("channel_id") or entry.get("uploader_id")
    else:
        page = entry.get("url") or entry.get("webpage_url") or ""
        if not page or not page.startswith("http"):
            return None
        track_id = "sc:" + b64e(page)
        author_url = entry.get("uploader_url") or entry.get("channel_url")
        author_id = entry.get("uploader_id")

    raw_title = _clean_title(str(entry.get("title") or "").strip())
    uploader = str(
        entry.get("uploader") or entry.get("channel") or entry.get("artist") or ""
    ).strip()
    if split:
        title, artist = _split_artist_title(raw_title, uploader)
    else:
        title, artist = raw_title, uploader or "Неизвестный"

    # Настоящие метаданные (YouTube Music) точнее разбора заголовка.
    if entry.get("track"):
        title = str(entry["track"]).strip()
    if entry.get("artist"):
        artist = str(entry["artist"]).split(",")[0].strip()

    return {
        "id": track_id,
        "title": title,
        "artist": artist,
        "duration": int(entry["duration"]) if entry.get("duration") else None,
        "thumbnail": _thumb(entry, track_id),
        "source": source,
        "url": page,
        "author_url": author_url,
        "author_id": author_id,
        "views": entry.get("view_count") if source==YOUTUBE else entry.get("playback_count",entry.get("view_count")),
        "stats_kind": "views" if source == YOUTUBE else "listens",
    }


def _dedupe(tracks: Iterable[dict]) -> list[dict]:
    """Убирает дубли по id и по паре «артист + название»."""
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    out: list[dict] = []
    for track in tracks:
        if not track:
            continue
        if track["id"] in seen_ids:
            continue
        key = re.sub(r"[^a-zа-я0-9]", "", f"{track['artist']}{track['title']}".lower())
        if key and key in seen_keys:
            continue
        seen_ids.add(track["id"])
        seen_keys.add(key)
        out.append(track)
    return out


# --------------------------------------------------------------------------- #
# поиск
# --------------------------------------------------------------------------- #
_yt_ranked72 = TTLCache(ttl=900.0, maxsize=256)


async def _youtube_candidates(query: str, need: int) -> list[dict]:
    tracks: list[dict] = []
    try:
        tracks = await ytmusic.search(query, need)
    except Exception as exc:
        log.warning("[ytmusic] search %r: %s", query, exc)

    # Порядок добора: сначала официальный бинарник yt-dlp
    # (он всегда свежий), и только потом публичные узлы Piped/Invidious.
    if len(tracks) < max(4, need // 3) and ytdlp_bin.ready():
        try:
            extra = await ytdlp_bin.search(query, need)
        except Exception as exc:
            log.warning("[yt-dlp] search %r: %s", query, exc)
            extra = []
        seen = {t["id"] for t in tracks}
        tracks += [t for t in extra if t and t["id"] not in seen]

    if len(tracks) < max(4, need // 3):
        try:
            extra = await youtube.search(query, need)
        except Exception as exc:
            log.warning("[piped] search %r: %s", query, exc)
            extra = []
        seen = {t["id"] for t in tracks}
        tracks += [t for t in extra if t and t["id"] not in seen]
    return [t for t in tracks if t and (t["duration"] is None or 45 <= t["duration"] <= 3600)]


async def search_youtube(query: str, limit: int = 30, offset: int = 0) -> list[dict]:
    """YouTube: сначала музыкальный каталог YouTube Music (ytmusicapi) —
    там песни, а не случайные видео; если он молчит, идём в Piped/Invidious.

    v72: выдача ранжируется целиком (оригинал первым, копии одной записи
    схлопываются) и запоминается, поэтому следующая страница продолжает ту же
    очередь, а не пересортировывает уже показанное."""
    if not query.strip():
        return []
    from .trackmeta import clean_track
    from . import search_rank72
    need = limit + offset
    key = "yt72:" + query.strip().casefold()
    ranked, exhausted = _yt_ranked72.get(key) or ([], False)
    degraded = False
    if len(ranked) < need and not exhausted:
        async with _yt_ranked72.lock(key):
            ranked, exhausted = _yt_ranked72.get(key) or ([], False)
            if len(ranked) < need and not exhausted:
                fresh = await _youtube_candidates(query, need)
                # Never mutate a previously cached list while building a new page.
                ranked = list(ranked)
                scored = search_rank72.rank(query, [clean_track(t) for t in fresh])
                known = {t["id"] for t in ranked}
                groups = [search_rank72.identity(t) for t in ranked]
                for track in scored:
                    if track["id"] in known:
                        continue
                    title, names = search_rank72.identity(track)
                    if any(title and title == g[0] and set(names) & set(g[1]) for g in groups):
                        continue
                    ranked.append(track); known.add(track["id"]); groups.append((title, names))
                exhausted = len(fresh) < need
                # Incomplete data must remain retryable rather than becoming a
                # complete (or briefly cached) answer to the next request.
                degraded = not fresh or any((t.get("_rank72") or {}).get("degraded") for t in fresh)
                if not degraded:
                    _yt_ranked72.set(key, (ranked, exhausted))
    result = [dict(t) for t in ranked[offset: offset + limit]]
    return ytmusic.IncompleteSearchResults(result) if degraded else result


async def search_soundcloud(
    query: str, limit: int = 30, offset: int = 0, *, allow_go_plus: bool = False
) -> list[dict]:
    if not query.strip():
        return []
    # Go+ отбрасываем после выдачи, поэтому запрашиваем с запасом.
    need = min(int((limit + offset) * (1.0 if allow_go_plus else 1.3)) + 3, 40)
    try:
        info = await _aextract(f"scsearch{need}:{query}", _FLAT_OPTS)
    except Exception as exc:
        log.warning("[soundcloud] search %r failed: %s", query, exc)
        return []
    entries = (info or {}).get("entries") or []
    out: list[dict] = []
    dropped = 0
    for entry in entries:
        if not allow_go_plus and is_go_plus(entry):
            dropped += 1
            continue
        track = normalize(entry, SOUNDCLOUD, split=False)
        if track:
            out.append(track)
    if dropped:
        log.debug("[soundcloud] Go+/preview filtered out: %d", dropped)
    return out[offset : offset + limit]


# --------------------------------------------------------------------------- #
# альбомы и плейлисты
# --------------------------------------------------------------------------- #
_collection_cache = TTLCache(ttl=1800.0)

ALBUM_PREFIX = ytmusic.ALBUM_PREFIX
PLAYLIST_PREFIX = ytmusic.PLAYLIST_PREFIX


def is_collection(ident: str) -> bool:
    return str(ident or "").startswith((ALBUM_PREFIX, PLAYLIST_PREFIX))


def _by_match(items: list[dict], query: str) -> list[dict]:
    """Сначала то, что действительно про запрос.

    Каталог отдаёт альбомы в своём порядке, и чужой сингл со похожим словом в
    названии легко оказывается первым. Совпадение по автору весит больше, чем
    совпадение по названию: человек искал исполнителя.
    """
    words = {w for w in re.findall(r"[a-zа-я0-9]+", query.casefold()) if len(w) > 1}
    if not words:
        return items

    def score(item: dict) -> tuple[int, int]:
        artist = set(re.findall(r"[a-zа-я0-9]+", str(item.get("artist") or "").casefold()))
        title = set(re.findall(r"[a-zа-я0-9]+", str(item.get("title") or "").casefold()))
        return (len(words & artist) * 2 + len(words & title), item.get("count") or 0)

    return sorted(items, key=score, reverse=True)


async def search_collections(query: str, limit: int = 10) -> dict:
    """Альбомы и плейлисты по тому же запросу, что и треки.

    Источник — музыкальный каталог YouTube Music: там это настоящие релизы
    и готовые подборки, а не случайные видео. Молчание каталога ничего не
    ломает: выдача просто останется без этих полок.
    """
    query = " ".join((query or "").split())
    if not query:
        return {"albums": [], "playlists": []}
    key = f"c:{query.lower()}|{limit}"
    cached = _collection_cache.get(key)
    if cached is not None:
        return cached
    async with _collection_cache.lock(key):
        cached = _collection_cache.get(key)
        if cached is not None:
            return cached
        found = await asyncio.gather(
            asyncio.wait_for(ytmusic.albums(query, limit), 14.0),
            asyncio.wait_for(ytmusic.playlists(query, limit), 8.0),
            return_exceptions=True,
        )
        degraded = any(isinstance(part, BaseException) or getattr(part, "degraded", False)
                       for part in found)
        for part in found:
            if isinstance(part, BaseException):
                log.warning("[search] collection source failed: %s", part)
        albums, playlists = (part if isinstance(part, list) else [] for part in found)
        result = {"albums": _by_match(albums, query),
                  "playlists": _by_match(playlists, query)}
        if degraded:
            result["degraded"] = True
        else:
            _collection_cache.set(key, result)
        return result


async def collection(ident: str, limit: int | None = None) -> dict:
    """Содержимое альбома или плейлиста по его id."""
    ident = str(ident or "").strip()
    if ident.startswith(ALBUM_PREFIX):
        return await ytmusic.album(ident, limit)
    if ident.startswith(PLAYLIST_PREFIX):
        return await ytmusic.playlist(ident, limit)
    raise RuntimeError("This is not an album or a playlist")


async def search(
    query: str,
    *,
    sources: Iterable[str] = ALL_SOURCES,
    limit: int = 40,
    page: int = 0,
    allow_go_plus: bool = False,
    with_collections: bool = False,
) -> dict:
    """Параллельный поиск по выбранным источникам + карточки авторов."""
    query = (query or "").strip()
    if not query:
        return {"query": query, "tracks": [], "authors": [], "sources": list(sources)}

    # Источники своих плагинов (ext:<id>) участвуют в поиске на тех же правах,
    # что встроенные: плагин включён — источник доступен.
    custom = tuple(extplugins.sources())
    known = (*ALL_SOURCES, *custom)
    sources = [s for s in sources if s in known] or list(DEFAULT_SOURCES) + list(custom)
    allowed = set(plugins.enabled_sources())
    if allowed:
        sources = [s for s in sources if s in allowed] or [s for s in DEFAULT_SOURCES if s in allowed]
    if not sources:
        return {"query": query, "tracks": [], "authors": [], "sources": []}
    cache_key = (f"s:{query.lower()}|{','.join(sorted(sources))}|{limit}|{page}"
                 f"|{int(allow_go_plus)}|{int(with_collections)}")
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    async with _search_cache.lock(cache_key):
        cached = _search_cache.get(cache_key)
        if cached is not None:
            return cached

        offset = page * limit
        # Альбомы и плейлисты ищем параллельно с треками: раньше их запрашивали
        # уже после треков, и первая страница ждала каталог лишние секунды.
        collections_task = (asyncio.create_task(search_collections(query, 12))
                            if with_collections and page == 0 else None)
        # Если оба источника — делим лимит, но с перекрытием, чтобы выдача была
        # плотной даже когда один источник пустой.
        per = limit if len(sources) == 1 else max(12, int(limit * 0.7))
        tasks = []
        artist_tasks: list[Any] = []
        if YOUTUBE in sources:
            tasks.append(search_youtube(query, per, offset))
            if page == 0:
                artist_tasks.append(asyncio.create_task(
                    asyncio.wait_for(ytmusic.artists(query, 12), 6.0)))
        if SOUNDCLOUD in sources:
            tasks.append(search_soundcloud(query, per, offset, allow_go_plus=allow_go_plus))
        if SPOTIFY in sources and spotify.ready():
            tasks.append(spotify.search(query, per, offset))
            if page == 0:
                artist_tasks.append(asyncio.create_task(
                    asyncio.wait_for(spotify.artists(query, 12), 8.0)))
        if library.JAMENDO in sources:
            library.set_jamendo_client(plugins.config("jamendo").get("client_id"))
        for name in library.LIBRARY_SOURCES:
            if name in sources:
                tasks.append(library.search(name, query, max(8, per // 2), offset))
        for name in custom:
            if name in sources:
                tasks.append(extplugins.search(name, query, max(8, per // 2), offset))

        chunks = await asyncio.gather(*tasks, return_exceptions=True)
        buckets: list[list[dict]] = []
        for chunk in chunks:
            if isinstance(chunk, BaseException):
                log.warning("[search] source failed: %s", chunk)
                continue
            buckets.append(chunk)

        from .trackmeta import clean_track
        from . import search_rank72
        # v72: every source keeps its own order as a signal (YouTube also its
        # play counts and «Top result»), then one ranking collapses copies.
        merged: list[dict] = []
        for bucket in buckets:
            for index, track in enumerate(bucket):
                if not track:
                    continue
                row = clean_track(track)
                if "_rank72" not in row:
                    row["_rank72"] = {"pos": index, "kind": ""}
                merged.append(row)
        degraded = (any(isinstance(chunk, BaseException) or getattr(chunk, "degraded", False) for chunk in chunks)
                    or any((t.get("_rank72") or {}).get("degraded") for t in merged))
        tracks = [search_rank72.public(t) for t in
                  search_rank72.rank(query, _dedupe(merged))][:limit]
        authors = _authors_from(tracks) if page == 0 else []
        if artist_tasks:
            found_artists = await asyncio.gather(*artist_tasks, return_exceptions=True)
            if any(isinstance(part, BaseException) or getattr(part, "degraded", False) for part in found_artists):
                degraded = True
            official = [item for chunk in found_artists if isinstance(chunk, list)
                        for item in chunk]
            # Official YT Music matches go first and replace track-cover
            # fallbacks with the actual artist/channel avatar.
            merged: list[dict] = []
            seen_authors: set[str] = set()
            for item in list(official or []) + authors:
                name = str(item.get("name") or "").strip().lower()
                if not name or name in seen_authors:
                    continue
                seen_authors.add(name)
                merged.append(item)
            authors = merged[:12]
        result = {
            "query": query,
            "page": page,
            "tracks": tracks,
            "authors": authors,
            "sources": sources,
            "has_more": len(tracks) >= limit * 0.6,
        }
        if degraded:
            result["degraded"] = True
        # Альбомы и плейлисты идут только на первой странице: на второй
        # странице треков они были бы теми же самыми.
        if collections_task is not None:
            try:
                found = await collections_task
            except Exception as exc:
                log.warning("[search] collections failed: %s", exc)
                found = {"degraded": True}
            result["albums"] = found.get("albums") or []
            result["playlists"] = found.get("playlists") or []
            if found.get("degraded"):
                degraded = result["degraded"] = True
        if not degraded:
            _search_cache.set(cache_key, result)
        return result


def _interleave(buckets: list[list[dict]]) -> list[dict]:
    """Перемешивает источники по очереди, чтобы выдача не была «одним блоком»."""
    out: list[dict] = []
    for i in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if i < len(bucket):
                out.append(bucket[i])
    return out


def _authors_from(tracks: list[dict], limit: int = 12) -> list[dict]:
    """Варианты авторов по результатам поиска: кто чаще встречается — тот выше."""
    stats: dict[str, dict] = {}
    for track in tracks:
        name = (track.get("artist") or "").strip()
        if not name or name.lower() in ("неизвестный", "unknown", "various artists"):
            continue
        key = name.lower()
        item = stats.setdefault(
            key,
            {
                "id": track.get("author_id") or key,
                "name": name,
                "source": track["source"],
                "url": track.get("author_url"),
                "thumbnail": track.get("author_thumbnail"),
                "tracks": 0,
                "score": 0,
            },
        )
        item["tracks"] += 1
        views = track.get("views")
        if not isinstance(views, (int, float)) or views < 0:
            views = 0
        item["score"] += views ** 0.25 + 1
        if not item.get("url") and track.get("author_url"):
            item["url"] = track["author_url"]
    authors = sorted(stats.values(), key=lambda a: (-a["tracks"], -a["score"]))
    return authors[:limit]


# --------------------------------------------------------------------------- #
# подсказки поиска
# --------------------------------------------------------------------------- #
def _fetch_suggest(query: str) -> list[str]:
    url = (
        "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&hl=ru&q="
        + urllib.parse.quote(query)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    return [str(s) for s in (data[1] if len(data) > 1 else []) if s]


async def suggest(query: str, limit: int = 10) -> list[str]:
    """Подсказки запросов из YouTube (мгновенные, без yt-dlp)."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    cached = _suggest_cache.get(query.lower())
    if cached is not None:
        return cached[:limit]
    try:
        items = await asyncio.to_thread(_fetch_suggest, query)
    except Exception as exc:
        log.debug("[suggest] %r: %s", query, exc)
        items = []
    _suggest_cache.set(query.lower(), items)
    return items[:limit]


async def suggest_authors(query: str, limit: int = 8) -> list[dict]:
    """Быстрые карточки авторов по короткому запросу (для выпадашки поиска)."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    key = f"a:{query.lower()}:{limit}"
    cached = _suggest_cache.get(key)
    if cached is not None:
        return cached
    official, yt, sc = await asyncio.gather(
        asyncio.wait_for(ytmusic.artists(query, limit), 6.0),
        search_youtube(query, 12),
        search_soundcloud(query, 10),
        return_exceptions=True,
    )
    tracks = [t for chunk in (yt, sc) if isinstance(chunk, list) for t in chunk]
    authors = []
    seen: set[str] = set()
    official_items = official if isinstance(official, list) else []
    for item in official_items + _authors_from(tracks, limit):
        name = str(item.get("name") or "").strip().lower()
        if name and name not in seen:
            seen.add(name)
            authors.append(item)
    authors = authors[:limit]
    _suggest_cache.set(key, authors)
    return authors


# --------------------------------------------------------------------------- #
# страница автора
# --------------------------------------------------------------------------- #
async def _try(coro, timeout: float, label: str) -> list[dict]:
    """Ждём корутину не дольше timeout; ошибки и таймаут — просто пустой список."""
    try:
        return await asyncio.wait_for(coro, timeout) or []
    except asyncio.TimeoutError:
        log.debug("[author] %s: таймаут %.1f с", label, timeout)
    except Exception as exc:
        log.debug("[author] %s: %s", label, exc)
    return []


async def _youtube_channel(url: str, limit: int) -> list[dict]:
    tracks = await _try(ytmusic.channel(url, limit), 6.0, "ytmusic")
    if len(tracks) >= 5:
        return tracks[:limit]
    # добор — только если основного источника не хватило
    seen = {t["id"] for t in tracks}
    tracks += [t for t in await _try(youtube.channel(url, limit), 6.0, "youtube")
               if t["id"] not in seen]
    if len(tracks) < 5 and ytdlp_bin.ready():
        seen = {t["id"] for t in tracks}
        tracks += [t for t in await _try(ytdlp_bin.playlist(url, limit), 10.0, "yt-dlp")
                   if t["id"] not in seen]
    return tracks[:limit]


async def _soundcloud_user(url: str, limit: int) -> list[dict]:
    target = url.rstrip("/")
    if not target.endswith("/tracks"):
        target += "/tracks"
    info = await _aextract(target, {**_FLAT_OPTS, "playlistend": limit})
    entries = (info or {}).get("entries") or []
    out = []
    for entry in entries:
        if is_go_plus(entry):
            continue
        track = normalize(entry, SOUNDCLOUD, split=False)
        if track:
            out.append(track)
    return out


async def _search_tracks(name: str, limit: int) -> list[dict]:
    """Поиск по имени автора — только треки, без падений наружу."""
    try:
        res = await asyncio.wait_for(search(name, limit=limit), 14.0)
        return res.get("tracks") or []
    except Exception as exc:
        log.debug("[author] поиск %s: %s", name, exc)
        return []


async def author(name: str, *, url: str | None = None, source: str | None = None,
                 limit: int = 40) -> dict:
    """Страница автора: только треки выбранного профиля и подтверждённые соавторства.

    Задачи идут параллельно, а страница отдаётся, как только появились первые
    треки: быстрый YouTube Music обычно отвечает за пару секунд, медленный
    yt-dlp догружается в фоне и заменяет ответ в кэше.
    """
    if source == SPOTIFY or (url and "open.spotify.com" in url):
        return await spotify.artist_page(name, url or "", limit)

    key = f"au:v20:{source or ''}:{url or name}:{limit}"
    cached = _page_cache.get(key)
    if cached is not None:
        return cached

    # Один и тот же автор, открытый дважды подряд (двойной клик, возврат
    # назад), раньше запускал два одинаковых набора запросов. Теперь второй
    # вызов просто ждёт первый и забирает готовый результат.
    async with _page_cache.lock(key):
        cached = _page_cache.get(key)
        if cached is not None:
            return cached

        jobs: list[tuple[str, Any]] = []      # (роль, задача)
        if url:
            if "soundcloud.com" in url:
                source = source or SOUNDCLOUD
                if ytdlp_ready():
                    jobs.append(("own", _try(_soundcloud_user(url, limit), 14.0,
                                             "soundcloud")))
            else:
                source = source or YOUTUBE
                jobs.append(("own", _try(_youtube_channel(url, limit), 14.0,
                                         "channel")))
        if name:
            # Быстрый источник: страница появляется, не дожидаясь yt-dlp.
            jobs.append(("extra", _try(ytmusic.search(name, max(20, limit)), 8.0,
                                       "ytmusic")))
            jobs.append(("extra", _try(_search_tracks(name, max(20, limit)), 14.0,
                                       "search")))

        tasks = [(role, asyncio.ensure_future(job)) for role, job in jobs]
        partial = False
        if tasks:
            # Ждём первые результаты, но пустую страницу вместо скелетонов не
            # отдаём: держимся до AUTHOR_TIMEOUT, пока хоть что-то не придёт.
            deadline = time.monotonic() + AUTHOR_TIMEOUT
            while True:
                await asyncio.wait([t for _, t in tasks], timeout=AUTHOR_DEADLINE,
                                   return_when=asyncio.FIRST_COMPLETED)
                done = all(t.done() for _, t in tasks)
                if _harvest(tasks)[0] or _harvest(tasks)[1] or done \
                        or time.monotonic() >= deadline:
                    break
            partial = not all(t.done() for _, t in tasks)

        own, extra = _harvest(tasks)
        result = _author_page(name, url, source, own, extra, limit, partial)
        from .artist_portraits import portrait
        try: official = await asyncio.wait_for(portrait(name,url,source),6.5)
        except Exception: official = {}
        if official: result.update(official)
        elif source in (None, 'youtube'): result['picture'] = None
        if partial:
            # Досчитываем молча: результат пригодится следующему открытию.
            asyncio.ensure_future(_warm_author(key, name, url, source, limit, tasks))
        # Пустой ответ не кэшируем вовсе: иначе страница автора «залипала»
        # пустой на весь TTL. Неполный живёт минуту — до фоновой догрузки.
        if result["tracks"]:
            _page_cache.set(key, result, ttl=60.0 if partial else None)
        return result


def _harvest(tasks: list[tuple[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Готовые результаты задач, разложенные по ролям."""
    own: list[dict] = []
    extra: list[dict] = []
    for role, task in tasks:
        if not task.done() or task.cancelled() or task.exception():
            continue
        value = task.result()
        if not isinstance(value, list):
            continue
        (own if role == "own" else extra).extend(value)
    return own, extra


def _author_page(name: str, url: str | None, source: str | None,
                 own: list[dict], extra: list[dict], limit: int,
                 partial: bool) -> dict:
    """Собирает ответ страницы автора из того, что уже есть."""
    from .trackmeta import artist_track_matches
    own = [track for track in own
           if artist_track_matches(track, name, url, from_profile=True)]
    extra = [track for track in extra if artist_track_matches(track, name, url)]
    tracks = _dedupe(own + extra)[:limit]
    return {
        "name": name or "Artist",
        "url": url,
        "source": source,
        "picture": (
            next((t["author_thumbnail"] for t in tracks
                  if t.get("author_thumbnail")), None)
        ),
        "tracks": tracks,
        "partial": partial,
    }


async def _warm_author(key: str, name: str, url: str | None, source: str | None,
                       limit: int, tasks: list[tuple[str, Any]]) -> None:
    """Догружает то, что не успело к дедлайну, и кладёт полный ответ в кэш."""
    try:
        await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)
    except Exception as exc:
        log.debug("[author] фоновая догрузка %s: %s", name, exc)
        return
    own, extra = _harvest(tasks)
    result = _author_page(name, url, source, own, extra, limit, False)
    previous = _page_cache.get(key)
    if previous and previous.get('picture_source'):
        result['picture']=previous['picture'];result['picture_source']=previous.get('picture_source')
    elif source in (None, 'youtube'): result['picture'] = None
    if result["tracks"]:
        _page_cache.set(key, result)


# --------------------------------------------------------------------------- #
# радио (YouTube Mix) — база для рекомендаций и бесконечной очереди
# --------------------------------------------------------------------------- #
async def youtube_mix(video_id: str, limit: int = 25) -> list[dict]:
    """Похожие треки по видео — из блока рекомендаций Piped/Invidious."""
    if not video_id:
        return []
    key = f"mix:{video_id}:{limit}"
    cached = _page_cache.get(key)
    if cached is not None:
        return cached
    tracks = await ytmusic.radio(video_id, limit)
    if len(tracks) < 5:
        tracks += await youtube.related(video_id, limit)
    tracks = _dedupe([t for t in tracks if t and t["id"] != f"yt:{video_id}"])[:limit]
    _page_cache.set(key, tracks)
    return tracks


def _song_key(text: str) -> str:
    text = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", str(text or ""))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


async def _youtube_twin(artist: str, title: str) -> str:
    """id той же песни в каталоге YouTube Music — для настоящего радио.

    У треков SoundCloud/Spotify нет своего «радио по треку», и раньше
    похожие для них искались просто по имени автора. Песню сопоставляем
    строго: автор указан в треке, название совпадает без пометок версии.
    """
    artist, title = (artist or "").strip(), (title or "").strip()
    if not artist or not title:
        return ""
    key = f"twin:{_song_key(artist)}|{_song_key(title)}"
    cached = _page_cache.get(key)
    if cached is not None:
        return cached
    from .trackmeta import artist_track_matches
    vid = ""
    try:
        found = await asyncio.wait_for(ytmusic.songs(f"{artist} {title}", 6), 8.0)
    except Exception:
        found = []
    want = _song_key(title)
    for track in found:
        got = _song_key(track.get("title"))
        if want and got and (got == want or (len(want) > 4 and (want in got or got in want))) \
                and artist_track_matches(track, artist):
            vid = str(track["id"])[3:]
            break
    _page_cache.set(key, vid)
    return vid


async def related(track_id: str, artist: str = "", title: str = "", limit: int = 20, sources: list[str] | None = None) -> list[dict]:
    """Похожие треки: сначала микс YouTube, потом поиск по автору."""
    tracks: list[dict] = []
    allowed = sources if sources is not None else DEFAULT_SOURCES
    if track_id.startswith("yt:") and "youtube" in allowed:
        tracks = await youtube_mix(track_id[3:], limit)
    elif "youtube" in allowed and artist and title:
        twin = await _youtube_twin(artist, title)
        if twin:
            tracks = await youtube_mix(twin, limit)
    if len(tracks) < limit // 2:
        seed = artist or title
        if seed:
            found = await search(seed, limit=limit, sources=allowed)
            tracks = _dedupe(tracks + found["tracks"])
    return tracks[:limit]


# --------------------------------------------------------------------------- #
# получение прямой ссылки на аудио
# --------------------------------------------------------------------------- #
def _pick_audio(info: dict | None) -> dict | None:
    if not info:
        return None
    formats = info.get("requested_formats") or info.get("formats") or []
    best = None
    candidates = []
    for fmt in formats:
        if fmt.get("acodec") in (None, "none"):
            continue
        if fmt.get("vcodec") not in (None, "none"):
            continue
        proto = str(fmt.get("protocol") or "")
        if not proto.startswith("http") or "m3u8" in proto or "dash" in proto:
            continue
        if not fmt.get("url"):
            continue
        candidates.append(fmt)
    from .audio_quality import pick
    best = pick(candidates,lambda f:(f.get("abr") or f.get("tbr") or 0)*1000)
    if best is None and info.get("url"):
        best = {
            "url": info["url"],
            "filesize": info.get("filesize"),
            "http_headers": info.get("http_headers"),
            "ext": info.get("ext"),
        }
    return best


_PREFIX = {
    YOUTUBE: "yt:", SOUNDCLOUD: "sc:", SPOTIFY: "sp:",
    library.AUDIUS: "au:", library.BANDCAMP: "bc:", library.ARCHIVE: "ia:",
    library.MIXCLOUD: "mx:", library.JAMENDO: "jm:", library.RADIO: "rb:",
    library.DEEZER: "dz:",
}


def prefixes() -> dict[str, str]:
    """Приставки id по источникам, включая источники своих плагинов."""
    return {**_PREFIX, **extplugins.prefixes()}


class StreamError(RuntimeError):
    pass


# Поток CDN сам говорит, до какой секунды он живой: googlevideo кладёт это
# либо в query (?expire=...), либо прямо в путь (/expire/1700000000/).
_EXPIRE_IN_PATH = re.compile(r"/expire/(\d{9,12})")
_LINK_MARGIN = 150.0


def _link_deadline(url: str) -> float | None:
    """Unix-время, после которого ссылка точно мёртвая. None — неизвестно."""
    try:
        query = parse_qs(urlsplit(url).query)
    except Exception:
        return None
    for key in ("expire", "expires", "exp"):
        value = (query.get(key) or [""])[0]
        if value.isdigit():
            return float(value)
    found = _EXPIRE_IN_PATH.search(url)
    return float(found.group(1)) if found else None


def _link_ttl(url: str, default: float) -> float:
    """Сколько держать ссылку в кэше.

    Раньше TTL был фиксированным, и ссылка со сроком жизни в двадцать минут
    всё равно лежала час — отсюда 403 на ровном месте: плеер брал из кэша
    заведомо мёртвый адрес. Теперь срок берём из самой ссылки и выкидываем её
    чуть раньше, чем CDN перестанет её принимать.
    """
    deadline = _link_deadline(url)
    if deadline is None:
        return default
    left = deadline - time.time() - _LINK_MARGIN
    if left <= 0:
        return 5.0
    return min(default, left)


def invalidate_stream(track_id: str) -> None:
    """Забыть прямую ссылку на трек.

    Нужно, когда ссылка внешне живая, но источник отвечает на неё 403: пока
    она лежала в кэше, все повторные попытки получали ровно её же.
    """
    _stream_cache.drop(track_id)


def link_expired(media: dict | None, margin: float = 30.0) -> bool:
    """Ссылка уже мертва по своему же сроку: качать по ней нечего."""
    if not media or not media.get("url"):
        return False
    deadline = _link_deadline(str(media["url"]))
    return deadline is not None and deadline - time.time() <= margin


async def resolve(track_id: str, *, refresh: bool = False, attempt: int = 0) -> dict:
    """(url, headers, size, mime) для трека.

    refresh — не брать готовую ссылку из кэша и получить новую;
    attempt  — номер попытки: сдвигает клиента плеера YouTube, чтобы повтор
               после 403 шёл другим путём, а не за той же мёртвой ссылкой.
    """
    if refresh:
        _stream_cache.drop(track_id)
    if track_id.startswith(("sp:", "dz:")):
        source = "Spotify" if track_id.startswith("sp:") else "Deezer"
        raise StreamError(f"{source} supplies metadata only; matching an open audio source")
    cached = None if refresh else _stream_cache.get(track_id)
    if cached is not None:
        return cached

    # Свой плагин пользователя: ссылку отдаёт он сам.
    if track_id.startswith(extplugins.PREFIX):
        try:
            result = await extplugins.resolve(track_id)
        except Exception as exc:
            raise StreamError(str(exc)) from exc
        _stream_cache.set(track_id, result, ttl=600)
        return result

    # Библиотеки с прямыми ссылками не требуют yt-dlp.
    if track_id.startswith("au:"):
        result = await library.resolve_audius(track_id[3:])
        _stream_cache.set(track_id, result, ttl=900)
        return result
    if track_id.startswith("ia:"):
        result = await library.resolve_archive(track_id[3:])
        _stream_cache.set(track_id, result)
        return result
    if track_id.startswith("jm:"):
        library.set_jamendo_client(plugins.config("jamendo").get("client_id"))
        result = await library.resolve_jamendo(track_id[3:])
        _stream_cache.set(track_id, result, ttl=1800)
        return result
    if track_id.startswith("rb:"):
        # Радио — живой поток, кэшировать на диск нечего.
        return await library.resolve_radio(track_id[3:])

    # YouTube. Главный источник ссылок — свежий
    # бинарник yt-dlp, он же умеет обходить бот-проверки с cookies. Публичные
    # узлы Piped/Invidious остаются быстрым запасным путём, а вкомпилированный
    # модуль yt-dlp — последним рубежом.
    if track_id.startswith("yt:"):
        async with _stream_cache.lock(track_id):
            cached = None if refresh else _stream_cache.get(track_id)
            if cached is not None:
                return cached
            errors: list[str] = []
            if ytdlp_bin.ready():
                try:
                    info = await ytdlp_bin.stream(track_id[3:], attempt)
                    result = {
                        "url": info["url"],
                        "headers": dict(info.get("headers") or {}),
                        "size": info.get("size"),
                        "mime": info.get("mime") or "audio/mp4",
                        "bitrate": info.get("bitrate"),
                        "codec": info.get("codec"),
                        "duration": info.get("duration"),
                    }
                    # Формально ссылка живёт около шести часов, но она привязана
                    # к сессии и адресу, и умереть может гораздо раньше. Держим
                    # двадцать минут: за это время трек успевает лечь в кэш
                    # целиком, а протухшая ссылка не переживает переключение
                    # трека туда и обратно.
                    _stream_cache.set(track_id, result, ttl=_link_ttl(result["url"], 1200))
                    return result
                except Exception as exc:
                    errors.append(f"yt-dlp: {exc}")
                    log.warning("[youtube] yt-dlp binary failed (%s)", exc)
            try:
                info = await youtube.stream(track_id[3:])
                result = {
                    "url": info["url"],
                    "headers": dict(info.get("headers") or {}),
                    "size": info.get("size"),
                    "mime": info.get("mime") or "audio/mp4",
                    "duration": info.get("duration"),
                }
                _stream_cache.set(track_id, result, ttl=_link_ttl(result["url"], 1800))
                return result
            except Exception as exc:
                errors.append(f"piped/invidious: {exc}")
                if not ytdlp_ready():
                    raise StreamError("; ".join(errors))
                log.warning("[youtube] nodes unavailable (%s), trying the yt-dlp module", exc)

    if not ytdlp_ready():
        raise StreamError("yt-dlp is not available in this build")

    async with _stream_cache.lock(track_id):
        cached = None if refresh else _stream_cache.get(track_id)
        if cached is not None:
            return cached

        if track_id.startswith("yt:"):
            page = f"https://www.youtube.com/watch?v={track_id[3:]}"
            clients = _YT_CLIENTS
        elif track_id.startswith("sc:"):
            page = b64d(track_id[3:])
            clients = (None,)
        elif track_id.startswith("bc:") or track_id.startswith("mx:"):
            page = b64d(track_id[3:])
            clients = (None,)
        else:
            raise StreamError("unknown source: " + track_id)

        fmt = None
        info: dict | None = None
        last_error: Exception | None = None
        for client in clients:
            try:
                info = await _aextract(page, _STREAM_OPTS, client)
                fmt = _pick_audio(info)
                if fmt and fmt.get("url"):
                    break
                fmt = None
            except Exception as exc:
                last_error = exc

        if not fmt:
            message = str(last_error or "no direct audio stream found")
            if "not a bot" in message or "Sign in to confirm" in message:
                message = ytdlp_bin.BOT_HINT
            raise StreamError(message)

        if track_id.startswith("sc:") and info and is_go_plus(info):
            raise StreamError("This track needs a SoundCloud Go+ subscription")

        ext = str(fmt.get("ext") or "").lower()
        mime = {
            "m4a": "audio/mp4", "mp4": "audio/mp4", "mp3": "audio/mpeg",
            "opus": "audio/ogg", "webm": "audio/webm", "ogg": "audio/ogg",
        }.get(ext, "audio/mpeg" if track_id.startswith("sc:") else "audio/mp4")

        size = fmt.get("filesize") or fmt.get("filesize_approx")
        result = {
            "url": fmt["url"],
            "headers": dict(fmt.get("http_headers") or {}),
            "size": int(size) if size else None,
            "mime": mime,
            "duration": int(info.get("duration")) if (info or {}).get("duration") else None,
            "bitrate": int(fmt["abr"]) if fmt.get("abr") else (int(fmt["tbr"]) if fmt.get("tbr") else None),
            "codec": fmt.get("acodec") if fmt.get("acodec") not in (None, "none") else None,
        }
        _stream_cache.set(track_id, result, ttl=_link_ttl(result["url"], 1800))
        return result


_ALT_ORDER = (YOUTUBE, library.AUDIUS, SOUNDCLOUD, library.ARCHIVE)


async def find_alternative(title: str, artist: str, exclude: str = "") -> dict | None:
    """Ищет тот же трек в другом источнике — запасной путь, когда поток не открылся."""
    query = f"{artist} {title}".strip()
    if not query:
        return None
    key = re.sub(r"[^a-zа-я0-9]", "", query.lower())
    for source in _ALT_ORDER:
        if exclude.startswith(_PREFIX.get(source, "\x00")):
            continue
        try:
            if source == YOUTUBE:
                found = await search_youtube(query, 4)
            elif source == SOUNDCLOUD:
                found = await search_soundcloud(query, 4)
            else:
                found = await library.search(source, query, 4)
        except Exception:
            continue
        for track in found:
            if track["id"] == exclude:
                continue
            other = re.sub(r"[^a-zа-я0-9]", "", f"{track['artist']}{track['title']}".lower())
            # грубая проверка совпадения: название должно пересекаться с запросом
            if key and other and (key[:12] in other or other[:12] in key
                                  or _clean_title(title).lower()[:10] in track["title"].lower()):
                return track
        if found:
            return found[0]
    return None


async def prefetch(track_id: str) -> bool:
    """Заранее получить ссылку на следующий трек — переход играет без паузы."""
    try:
        await resolve(track_id)
        return True
    except Exception:
        return False


def status() -> dict:
    return {
        "sources": [
            {
                "id": YOUTUBE,
                "name": "YouTube",
                "available": True,
                "note": "YouTube Music catalogue: official releases, albums and radio",
            },
            {
                "id": SOUNDCLOUD,
                "name": "SoundCloud",
                "available": True,
                "note": "Indie, remixes and rare uploads; Go+ previews hidden",
            },
            {
                "id": SPOTIFY,
                "name": "Spotify",
                "available": spotify.ready(),
                "note": "Metadata source only (search, artists, covers); audio and clips come from open providers",
            },
            *library.status(),
            # Свои плагины показываем там же, где встроенные библиотеки:
            # в «Где искать» они включаются тем же переключателем.
            *[{"id": item["source"], "name": item["name"], "available": True,
               "custom": True,
               "note": item["description"]}
              for item in extplugins.catalog_entries() if item.get("source")],
        ],
        "ytdlp": ytdlp_ready() or ytdlp_bin.ready(),
        "ytdlp_binary": ytdlp_bin.status(),
        "youtube_cookies": ytcookies.state(),
        "youtube_api": "yt-dlp binary + ytmusicapi + piped/invidious",
        "cookies": bool(cookie_file()),
        "plugin_sources": plugins.enabled_sources(),
        "custom_sources": extplugins.sources(),
        "default_sources": list(DEFAULT_SOURCES),
    }


def clear_caches() -> None:
    for cache in (_search_cache, _page_cache, _stream_cache, _suggest_cache):
        cache.clear()
