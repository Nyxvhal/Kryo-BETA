"""
streaming.py — разрешение потоков в две фазы.

Модель работы простая и держится на двух шагах:

  1. Поиск кандидатов  (resolve_candidates_for_track)
     Трек = «исполнитель + название». Каждый включённый стриминговый плагин
     возвращает своих кандидатов — потенциальные источники звука ещё без
     прямой ссылки.

  2. Разрешение потока (resolve_stream_for_candidate)
     У верхнего кандидата ссылка добывается «точно в момент нужды». Ссылки
     живут недолго (YouTube — часы), поэтому у каждого кандидата хранится
     время последнего разрешения, а истёкшие переразрешаются заново.

Поведение собрано в таблицу:

    failed: true                     -> возвращаем как есть, без повтора
    свежий stream                    -> возвращаем как есть (кэш)
    stream истёк или отсутствует     -> разрешаем заново
    разрешение не удалось N раз      -> failed: true
    нет включённых стриминг-плагинов -> None
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from . import library, plugins, providers, storage

log = logging.getLogger(__name__)

# Значения по умолчанию (срок жизни ссылки и
# playback.streamResolutionRetries).
DEFAULT_EXPIRY_MS = 60 * 60 * 1000
DEFAULT_RETRIES = 3

PROTOCOLS = ("file", "http", "https", "hls")

# Порядок опроса источников: сначала самые надёжные прямые ссылки.
PROVIDER_PRIORITY = (
    providers.YOUTUBE,
    library.AUDIUS,
    providers.SOUNDCLOUD,
    library.JAMENDO,
    library.ARCHIVE,
    library.BANDCAMP,
    library.MIXCLOUD,
    library.RADIO,
)

_candidates: dict[str, list[dict]] = {}
_locks: dict[str, asyncio.Lock] = {}


# --------------------------------------------------------------------------- #
# настройки
# --------------------------------------------------------------------------- #
def _setting(key: str, default: int) -> int:
    try:
        value = storage.get_settings().get(key)
        return int(value) if value else default
    except Exception:
        return default


def expiry_ms() -> int:
    return max(60_000, _setting("streamExpiryMs", DEFAULT_EXPIRY_MS))


def retries() -> int:
    return max(1, min(6, _setting("streamResolutionRetries", DEFAULT_RETRIES)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _expired(candidate: dict) -> bool:
    stamp = candidate.get("lastResolvedAtIso")
    if not stamp:
        return True
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    age_ms = (datetime.now(timezone.utc) - moment).total_seconds() * 1000
    return age_ms >= expiry_ms()


def _key(track: dict) -> str:
    raw = f"{track.get('artist') or ''} {track.get('title') or ''}".lower()
    return re.sub(r"[^a-zа-я0-9]+", "", raw) or (track.get("id") or "")


def _lock(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = _locks[key] = asyncio.Lock()
    return lock


# --------------------------------------------------------------------------- #
# кандидаты
# --------------------------------------------------------------------------- #
def _provider_ref(source: str) -> dict:
    """Ссылка на провайдера: плагин + вид провайдера."""
    return {
        "plugin": plugins.SOURCE_PLUGIN.get(source, source),
        "provider": source,
        "kind": "streaming",
        "name": (plugins.BY_ID.get(plugins.SOURCE_PLUGIN.get(source, ""), {})
                 .get("name") or source),
    }


def candidate_from_track(track: dict) -> dict:
    duration = track.get("duration")
    return {
        "id": track.get("id"),
        "title": track.get("title") or "",
        "artist": track.get("artist") or "",
        "durationMs": int(duration * 1000) if duration else None,
        "thumbnail": track.get("thumbnail"),
        "source": _provider_ref(track.get("source") or _source_of(track.get("id") or "")),
        "stream": None,
        "lastResolvedAtIso": None,
        "failed": False,
        "attempts": 0,
    }


def _source_of(track_id: str) -> str:
    for source, prefix in providers.prefixes().items():
        if track_id.startswith(prefix):
            return source
    return "unknown"


def _score(candidate: dict, track: dict) -> float:
    """Насколько кандидат похож на запрошенный трек и насколько надёжен источник."""
    want_title = re.sub(r"[^a-zа-я0-9]+", "", (track.get("title") or "").lower())
    want_artist = re.sub(r"[^a-zа-я0-9]+", "", (track.get("artist") or "").lower())
    got_title = re.sub(r"[^a-zа-я0-9]+", "", (candidate.get("title") or "").lower())
    got_artist = re.sub(r"[^a-zа-я0-9]+", "", (candidate.get("artist") or "").lower())

    score = 0.0
    if want_title and want_title in got_title:
        score += 3
    if want_artist and want_artist in got_artist:
        score += 2
    source = (candidate.get("source") or {}).get("provider")
    if source in PROVIDER_PRIORITY:
        score += (len(PROVIDER_PRIORITY) - PROVIDER_PRIORITY.index(source)) * 0.1
    want_ms = track.get("duration")
    got_ms = candidate.get("durationMs")
    if want_ms and got_ms and abs(got_ms / 1000 - want_ms) <= 8:
        score += 1
    return score


async def resolve_candidates_for_track(track: dict, *, limit: int = 8,
                                       refresh: bool = False) -> dict:
    """Первая фаза: ищем возможные источники звука для трека.

    Возвращает {"success": bool, "candidates": [...]} или {"success": False,
    "error": "..."} — результат разрешения потока.
    """
    title = (track.get("title") or "").strip()
    artist = (track.get("artist") or "").strip()
    # Spotify is a metadata provider.  It seeds artist/title/cover data, but
    # candidates must come from providers that can return playable audio.
    selected = storage.get_settings().get("sources") or []
    selected = {str(source) for source in selected if isinstance(source, str)}
    # Источники со звуком: Spotify и Deezer дают только метаданные.
    playable_sources = [source for source in plugins.enabled_sources()
                        if source not in (providers.SPOTIFY, library.DEEZER)]
    # Фильтр источников на экране поиска не должен запрещать подбор звука.
    # Раньше при наборе по умолчанию (SoundCloud + Spotify) у трека Spotify
    # оставался единственный кандидат — SoundCloud, а если выбран был только
    # Spotify, список кандидатов оказывался пустым и трек вообще не играл.
    # Теперь выбранные источники идут первыми, а остальные включённые
    # остаются запасными.
    sources = ([source for source in playable_sources if source in selected]
               + [source for source in playable_sources if source not in selected])
    if not sources:
        return {"success": False, "error": "no active streaming provider",
                "candidates": []}
    if not title and not track.get("id"):
        return {"success": False, "error": "track needs a title", "candidates": []}

    key = _key(track)
    async with _lock(key):
        if not refresh and key in _candidates:
            return {"success": True, "candidates": _candidates[key], "cached": True}

        found: list[dict] = []
        if track.get("id"):
            # Сам трек — всегда кандидат номер один.
            found.append(candidate_from_track(track))

        if title:
            query = f"{artist} {title}".strip()
            try:
                result = await providers.search(query, sources=sources,
                                                limit=max(12, limit * 2), page=0)
            except Exception as exc:
                log.warning("[streams] candidate lookup failed: %s", exc)
                result = {"tracks": []}
            for item in result.get("tracks") or []:
                if any(c["id"] == item.get("id") for c in found):
                    continue
                found.append(candidate_from_track(item))

        ranked = sorted(found, key=lambda c: -_score(c, track))[:limit]
        if not ranked:
            return {"success": False, "error": "no candidates found", "candidates": []}
        _candidates[key] = ranked
        if len(_candidates) > 300:
            for old in list(_candidates)[:100]:
                _candidates.pop(old, None)
        return {"success": True, "candidates": ranked}


# --------------------------------------------------------------------------- #
# разрешение потока
# --------------------------------------------------------------------------- #
def _protocol(url: str) -> str:
    low = (url or "").lower()
    if ".m3u8" in low:
        return "hls"
    if low.startswith("file://"):
        return "file"
    return "https" if low.startswith("https") else "http"


def _to_stream(media: dict) -> dict:
    mime = media.get("mime") or "audio/mpeg"
    codec = {"audio/mp4": "aac", "audio/mpeg": "mp3", "audio/webm": "opus",
             "audio/ogg": "opus", "audio/aac": "aac"}.get(mime)
    return {
        "url": media["url"],
        "protocol": _protocol(media["url"]),
        "mimeType": mime,
        "bitrateKbps": media.get("bitrate"),
        "codec": media.get("codec") or codec,
        "qualityLabel": media.get("quality"),
        "headers": media.get("headers") or {},
        "size": media.get("size"),
        "duration": media.get("duration"),
    }


async def resolve_stream_for_candidate(candidate: dict) -> dict | None:
    """Вторая фаза: добываем прямую ссылку. Кандидат не меняется — возвращается копия."""
    if not candidate or not candidate.get("id"):
        return None
    if candidate.get("failed"):
        return candidate
    if candidate.get("stream") and not _expired(candidate):
        return candidate

    limit = retries()
    updated = {**candidate}
    last_error: Exception | None = None
    for attempt in range(limit):
        try:
            media = await providers.resolve(candidate["id"])
            updated["stream"] = _to_stream(media)
            updated["lastResolvedAtIso"] = _now_iso()
            updated["failed"] = False
            updated["attempts"] = attempt + 1
            updated["error"] = None
            if media.get("duration") and not updated.get("durationMs"):
                updated["durationMs"] = int(media["duration"] * 1000)
            _remember(updated)
            return updated
        except Exception as exc:
            last_error = exc
            log.debug("[streams] %s: attempt %d/%d failed: %s",
                      candidate["id"], attempt + 1, limit, exc)
            await asyncio.sleep(0.25 * (attempt + 1))

    updated["failed"] = True
    updated["attempts"] = limit
    updated["error"] = str(last_error or "stream resolution failed")
    _remember(updated)
    return updated


def _remember(candidate: dict) -> None:
    """Обновляет кандидата во всех списках, где он встречается."""
    for items in _candidates.values():
        for index, item in enumerate(items):
            if item.get("id") == candidate.get("id"):
                items[index] = candidate


async def playable(track: dict, *, skip: Iterable[str] = ()) -> dict | None:
    """Первый кандидат, который реально отдал ссылку.

    Перебор идёт сверху вниз, провалившиеся помечаются failed и больше не
    трогаются — это и есть «автозамена источника».
    """
    skip = set(skip)
    result = await resolve_candidates_for_track(track)
    if not result.get("success"):
        return None
    for candidate in result["candidates"]:
        if candidate.get("failed") or candidate.get("id") in skip:
            continue
        resolved = await resolve_stream_for_candidate(candidate)
        if resolved and resolved.get("stream") and not resolved.get("failed"):
            return resolved
    return None


def forget(track: dict | None = None) -> None:
    if track is None:
        _candidates.clear()
        return
    _candidates.pop(_key(track), None)


def stats() -> dict:
    total = sum(len(v) for v in _candidates.values())
    failed = sum(1 for v in _candidates.values() for c in v if c.get("failed"))
    return {"tracks": len(_candidates), "candidates": total, "failed": failed,
            "expiryMs": expiry_ms(), "retries": retries()}
