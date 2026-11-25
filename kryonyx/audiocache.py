"""Streaming audio with a private SQLite vault.
First bytes play immediately while a temporary .part is filled. Only a
complete transfer is committed to the bounded vault; no loose music export.
Legacy audio caches migrate on startup. This is storage, not encryption.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time

from .paths import cache_dir
from . import audiovault

log = logging.getLogger(__name__)

MAX_BYTES = 6 * 1024 ** 3      # держим до 6 ГБ скачанной музыки
# 32 КБ: первый кусок уходит браузеру ещё быстрее — звук начинается раньше.
_CHUNK = 32 * 1024
# Дальше читаем крупнее: на длинном треке мелкие куски только жгут процессор.
_CHUNK_BIG = 512 * 1024
# Сколько кусков трека тянем одновременно, когда источник умеет Range.
_LANES = 4
# Меньше этого размера делить на части бессмысленно.
_SPLIT_MIN = 3 * 1024 ** 2
# Сколько байт отдаём из первого же потока: этого хватает, чтобы звук пошёл,
# а дальше трек догоняем упреждающей подкачкой сегментов.
_HEAD = 64 * 1024
# Размер сегмента упреждающей подкачки при живом воспроизведении.
_SEG = 512 * 1024
_locks: dict[str, asyncio.Lock] = {}
_committing: set[str] = set()
def committing(track_id): return track_id in _committing


class _NoRange(Exception):
    """Источник не принял Range: упреждающая подкачка невозможна."""


class SourceError(RuntimeError):
    """Источник отказал по HTTP. Код нужен наверху, чтобы отличить
    протухшую ссылку (403/401/410 — можно получить новую) от настоящей
    поломки (404/5xx — новая ссылка не поможет)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"the source answered {status}")
        self.status = status

    @property
    def stale(self) -> bool:
        return self.status in (401, 403, 410)

MIME_BY_EXT = {
    ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".mp3": "audio/mpeg",
    ".opus": "audio/ogg", ".ogg": "audio/ogg", ".webm": "audio/webm",
    ".flac": "audio/flac", ".wav": "audio/wav",
}


def folder() -> str:
    path = os.path.join(cache_dir(), "audio")
    os.makedirs(path, exist_ok=True)
    return path


def _key(track_id: str) -> str:
    return hashlib.sha1(track_id.encode()).hexdigest()


def _ext_for(mime: str, url: str) -> str:
    for ext, value in MIME_BY_EXT.items():
        if value == mime:
            return ext
    low = url.split("?")[0].lower()
    for ext in MIME_BY_EXT:
        if low.endswith(ext):
            return ext
    return ".m4a"


# Указатель «ключ трека -> файл». Раньше каждый find() перебирал весь каталог
# кэша: на тысяче треков это сотни системных вызовов на КАЖДЫЙ запрос — и
# именно отсюда брались заметные паузы перед стартом. Теперь каталог читается
# редко, а обычная проверка стоит один словарный поиск.
_index: dict[str, str] = {}
_index_at = 0.0
_INDEX_TTL = 30.0
_touched: dict[str, float] = {}


def _rebuild_index() -> None:
    global _index_at
    found: dict[str, str] = {}
    try:
        for name in os.listdir(folder()):
            if name.endswith(".part"):
                continue
            found[name.split(".", 1)[0]] = os.path.join(folder(), name)
    except OSError:
        pass
    _index.clear()
    _index.update(found)
    _index_at = time.time()


def _remember_file(key: str, path: str) -> None:
    _index[key] = path


def find(track_id: str) -> str | None:
    """Готовый файл трека, если он уже скачан."""
    key = _key(track_id)
    path = _index.get(key)
    if path is None and time.time() - _index_at > _INDEX_TTL:
        _rebuild_index()
        path = _index.get(key)
    if not path:
        return None
    try:
        if os.path.getsize(path) <= 0:
            raise OSError
    except OSError:
        _index.pop(key, None)
        return None
    # «Последнее использование» обновляем не чаще раза в пять минут: на запись
    # времени доступа тоже уходит обращение к диску.
    now = time.time()
    if now - _touched.get(key, 0.0) > 300:
        _touched[key] = now
        try:
            os.utime(path, None)
        except OSError:
            pass
    return path


def lock(track_id: str) -> asyncio.Lock:
    key = _key(track_id)
    got = _locks.get(key)
    if got is None:
        got = _locks[key] = asyncio.Lock()
    return got


def paths_for(track_id: str, media: dict) -> tuple[str, str]:
    """(файл .part, итоговый файл) для трека."""
    ext = _ext_for(media.get("mime") or "", media.get("url") or "")
    base = os.path.join(folder(), _key(track_id))
    return base + ".part", base + ext


def downloading(track_id: str) -> bool:
    """Идёт ли прямо сейчас запись этого трека в кэш."""
    return lock(track_id).locked()


async def _probe(session, media: dict) -> tuple[int | None, bool]:
    """(размер трека, умеет ли источник Range) — один дешёвый запрос."""
    headers = dict(media.get("headers") or {})
    headers.pop("Range", None)
    headers["Range"] = "bytes=0-1"
    try:
        async with session.get(media["url"], headers=headers) as resp:
            if resp.status >= 400:
                return None, False
            rng = resp.headers.get("Content-Range") or ""
            if resp.status == 206 and "/" in rng:
                tail = rng.rsplit("/", 1)[-1].strip()
                if tail.isdigit():
                    return int(tail), True
            total = resp.headers.get("Content-Length")
            return (int(total) if total and total.isdigit() else None), False
    except Exception:
        return None, False


async def _download_parallel(session, media: dict, part: str, size: int) -> int:
    """Качает трек в несколько потоков по диапазонам байт.

    Источники отдают один поток заметно медленнее, чем канал позволяет.
    Четыре параллельных куска обычно ускоряют предзагрузку в 2–3 раза, а
    файл при этом собирается сразу на своём месте — склейка не нужна.
    """
    lanes = max(1, min(_LANES, -(-size // (1024 * 1024))))
    span = size // lanes
    base = {k: v for k, v in (media.get("headers") or {}).items()
            if k.lower() != "range"}

    with open(part, "wb") as fh:          # заранее растягиваем файл до нужной длины
        fh.truncate(size)

    written = 0

    async def lane(index: int) -> None:
        # У каждой дорожки свой диапазон и свой дескриптор: куски не
        # пересекаются, поэтому замок не нужен.
        nonlocal written
        start = index * span
        stop = size - 1 if index == lanes - 1 else (index + 1) * span - 1
        headers = dict(base)
        headers["Range"] = f"bytes={start}-{stop}"
        async with session.get(media["url"], headers=headers) as resp:
            if resp.status >= 400:
                raise SourceError(resp.status)
            if resp.status != 206 or resp.headers.get("Content-Range", "") != f"bytes {start}-{stop}/{size}":
                raise _NoRange()
            with open(part, "r+b") as fh:
                fh.seek(start)
                lane_bytes = 0
                async for chunk in resp.content.iter_chunked(_CHUNK_BIG):
                    lane_bytes += len(chunk)
                    if lane_bytes > stop - start + 1: raise RuntimeError("Oversized upstream audio range")
                    fh.write(chunk)
                    written += len(chunk)
                    if written > audiovault.MAX_TRACK:
                        raise RuntimeError("Audio exceeds 256 MiB")
                if lane_bytes != stop - start + 1: raise RuntimeError("Incomplete upstream audio range")

    tasks=[asyncio.create_task(lane(i)) for i in range(lanes)]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        raise
    return written


async def download(session, track_id: str, media: dict) -> str:
    """Качает трек целиком и возвращает путь к файлу. Вызывать под lock()."""
    ready = find(track_id)
    if ready:
        return ready

    part, final = paths_for(track_id, media)
    cache_generation = audiovault.generation()

    size_hint, ranged = await _probe(session, media)
    expected = str(size_hint) if size_hint else None
    if size_hint and size_hint > audiovault.MAX_TRACK:
        raise RuntimeError("Audio exceeds internal cache limit per track")
    if ranged and size_hint and size_hint >= _SPLIT_MIN:
        try:
            await _download_parallel(session, media, part, size_hint)
        except SourceError:
            raise
        except Exception as exc:          # сеть подвела — спокойно качаем в один поток
            log.debug("[cache] parallel download failed (%s), falling back", exc)
            try:
                os.remove(part)
            except OSError:
                pass
            await _download_single(session, media, part)
    else:
        expected = await _download_single(session, media, part) or expected
    size = os.path.getsize(part)
    if expected and size != int(expected):
        os.remove(part)
        raise RuntimeError("the download was interrupted")
    if size < 16 * 1024:
        os.remove(part)
        raise RuntimeError("the source returned an empty file")

    _committing.add(track_id)
    try:
        final = await audiovault.run_blocking_owned(audiovault.store, track_id, part, media.get("mime") or _ext_mime(media), expected_generation=cache_generation, tier=media.get("tier"), meta=_quality_meta(media))
    finally:
        _committing.discard(track_id)
    if not final: raise RuntimeError("Audio was not retained by the cache policy")
    log.info("[cache] %s -> %s (%.1f MB)", track_id, os.path.basename(final) if final else "not retained", size / 1048576)
    trim()
    return final


async def _download_single(session, media: dict, part: str) -> str | None:
    """Обычная загрузка одним потоком. Возвращает заявленный размер."""
    headers = dict(media.get("headers") or {})
    headers.pop("Range", None)
    async with session.get(media["url"], headers=headers) as resp:
        if resp.status >= 400:
            raise SourceError(resp.status)
        expected = resp.headers.get("Content-Length")
        with open(part, "wb") as fh:
            count=0
            async for chunk in resp.content.iter_chunked(_CHUNK_BIG):
                count+=len(chunk)
                if count>audiovault.MAX_TRACK: raise RuntimeError("Audio exceeds 256 MiB")
                fh.write(chunk)
    return expected


async def _tee_ahead(session, media: dict, size: int, start: int,
                     on_chunk, fh) -> int:
    """Доигрывает остаток трека сегментами в несколько запросов вперёд.

    Главный тормоз живого воспроизведения — не канал, а сам источник:
    googlevideo отдаёт один поток раз в несколько медленнее, чем позволяет
    линия, и кэш «догонял» трек почти в реальном времени. Поэтому остаток
    файла тянем сегментами по 2 МБ сразу в несколько запросов, а наружу
    выдаём строго по порядку — браузер видит обычный непрерывный ответ.
    """
    base = {k: v for k, v in (media.get("headers") or {}).items()
            if k.lower() != "range"}
    written = 0        # сколько ушло в файл кэша (его может и не быть)
    sent = 0           # сколько байт трека уже отдано наружу

    async def fetch(index: int) -> bytes:
        begin = start + index * _SEG
        stop = min(size, begin + _SEG) - 1
        headers = dict(base)
        headers["Range"] = f"bytes={begin}-{stop}"
        async with session.get(media["url"], headers=headers) as resp:
            if resp.status >= 400:
                raise SourceError(resp.status)
            # 200 вместо 206 значит «Range не понят»: пришёл бы файл с начала,
            # и мы склеили бы кашу. Тогда честно уходим в один поток.
            if resp.status != 206:
                raise _NoRange()
            expected = stop - begin + 1
            pieces, count = [], 0
            async for piece in resp.content.iter_chunked(_CHUNK_BIG):
                count += len(piece)
                if count > expected: raise RuntimeError("Oversized upstream audio range")
                pieces.append(piece)
            data = b"".join(pieces)
            if len(data) != expected or resp.headers.get("Content-Range", "") != f"bytes {begin}-{stop}/{size}":
                raise RuntimeError("Invalid upstream audio range")
            return data

    segments = -(-(size - start) // _SEG)
    tasks: dict[int, asyncio.Task] = {}
    index = 0
    try:
        while index < segments:
            # Держим несколько запросов в воздухе: пока отдаём текущий
            # сегмент, следующие уже качаются.
            while len(tasks) < _LANES and index + len(tasks) < segments:
                ahead_index = index + len(tasks)
                tasks[ahead_index] = asyncio.create_task(fetch(ahead_index))
            data = await tasks.pop(index)
            for off in range(0, len(data), _CHUNK_BIG):
                piece = data[off:off + _CHUNK_BIG]
                if on_chunk is not None:
                    await on_chunk(piece)
                sent += len(piece)
                if fh is not None:
                    fh.write(piece)
                    written += len(piece)
            index += 1
    except _NoRange:
        log.debug("[cache] the source ignores Range, falling back to one stream")
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        written += await _tee_rest(session, media, start + sent, on_chunk, fh)
    except BaseException:
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        raise
    return written


async def _tee_rest(session, media: dict, start: int, on_chunk, fh) -> int:
    """Откат: остаток трека одним потоком. Источник без Range отдаёт файл
    с начала, поэтому уже отданные байты просто пропускаем."""
    headers = {k: v for k, v in (media.get("headers") or {}).items()
               if k.lower() != "range"}
    headers["Range"] = f"bytes={start}-"
    written = 0
    async with session.get(media["url"], headers=headers) as resp:
        if resp.status >= 400:
            raise SourceError(resp.status)
        skip = 0 if resp.status == 206 else start
        async for chunk in resp.content.iter_chunked(_CHUNK_BIG):
            if skip:
                drop = min(skip, len(chunk))
                skip -= drop
                chunk = chunk[drop:]
                if not chunk:
                    continue
            if on_chunk is not None:
                await on_chunk(chunk)
            if fh is not None:
                fh.write(chunk)
                written += len(chunk)
    return written


async def tee(session, track_id: str, media: dict, *, range_header: str = "",
              cache: bool = True, on_start=None, on_chunk=None) -> dict:
    """Качает поток и одновременно отдаёт его наружу.

    on_start(info)   — вызывается один раз, когда источник ответил заголовками;
    on_chunk(bytes)  — каждый пришедший кусок (его и пишем в браузер).

    Файл кэша пишется только когда запрошен трек целиком (без Range или с
    Range: bytes=0-): иначе на диск попал бы обрезок.
    """
    headers = {k: v for k, v in (media.get("headers") or {}).items()
               if k.lower() != "range"}
    whole = not range_header or range_header.replace(" ", "") == "bytes=0-"
    if whole: range_header = ""
    cache = cache and audiovault.enabled()
    if range_header:
        headers["Range"] = range_header

    part, final = paths_for(track_id, media)
    cache_generation = audiovault.generation()
    fh = None
    written = 0
    tail_from = 0
    completed = False
    info: dict = {}
    try:
        async with session.get(media["url"], headers=headers) as resp:
            if resp.status >= 400:
                raise SourceError(resp.status)
            total = resp.headers.get("Content-Length")
            info = {
                "status": resp.status,
                "mime": (media.get("mime")
                         or resp.headers.get("Content-Type") or "audio/mpeg").split(";")[0],
                "length": int(total) if total and total.isdigit() else None,
                "content_range": resp.headers.get("Content-Range"),
            }
            if on_start is not None:
                await on_start(info)

            # Пишем в кэш только если качаем трек целиком и этот же файл не
            # пишет кто-то ещё (иначе два потока испортят один .part).
            if cache and whole and resp.status == 200 and not os.path.exists(final) and (not info.get("length") or info["length"] <= audiovault.MAX_TRACK):
                try:
                    fh = open(part, "wb")
                except OSError:
                    fh = None

            # Первые полмегабайта читаем мелко (звук начинается раньше), потом
            # переходим на крупные куски — так меньше накладных расходов.
            length = info.get("length") or 0
            # Один поток источника медленный, но первые килобайты из него
            # приходят сразу — их и отдаём, а остаток забираем сегментами.
            ahead = bool(whole and resp.status == 200 and not range_header
                         and length >= _SPLIT_MIN)
            seen = 0
            reader = resp.content
            while True:
                size = _CHUNK if seen < _HEAD else _CHUNK_BIG
                chunk = await reader.read(size)
                if not chunk:
                    break
                seen += len(chunk)
                if on_chunk is not None:
                    await on_chunk(chunk)
                if fh is not None:
                    fh.write(chunk)
                    written += len(chunk)
                    if written > audiovault.MAX_TRACK:
                        fh.close(); fh = None
                        os.remove(part)
                if ahead and seen >= _HEAD:
                    break
            if ahead and 0 < seen < length:
                tail_from = seen
                resp.close()              # этот поток дальше не нужен
        if tail_from:
            written += await _tee_ahead(session, media, int(info["length"]),
                                        tail_from, on_chunk, fh)
        completed = True
    finally:
        if fh is not None:
            fh.close()
            expected = info.get("length")
            good = completed and written > 16 * 1024 and (not expected or written == expected)
            if good:
                try:
                    _committing.add(track_id)
                    try:
                        await audiovault.run_blocking_owned(audiovault.store, track_id, part, info.get("mime") or "audio/mpeg", expected_generation=cache_generation, tier=media.get("tier"), meta=_quality_meta(media))
                    finally:
                        _committing.discard(track_id)
                    log.info("[cache] %s finished and saved (%.1f MB)",
                             track_id, written / 1048576)
                    trim()
                except Exception as exc:
                    log.warning("[cache] audio played but was not retained: %s", exc)
                    try: os.remove(part)
                    except OSError: pass
            else:
                # Пользователь переключил трек или сеть оборвалась — обрезок не нужен.
                try:
                    os.remove(part)
                except OSError:
                    pass
    return info


def trim(max_bytes: int = MAX_BYTES) -> None:
    """Чистим самые давно не игравшие файлы, когда кэш перерос лимит."""
    base = folder()
    try:
        files = []
        total = 0
        for name in os.listdir(base):
            path = os.path.join(base, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            files.append((stat.st_mtime, stat.st_size, path))
            total += stat.st_size
        if total <= max_bytes:
            return
        for _, size, path in sorted(files):
            try:
                os.remove(path)
                total -= size
            except OSError:
                pass
            if total <= max_bytes * 0.9:
                break
        _rebuild_index()
    except OSError:
        pass


def stats() -> dict:
    base = folder()
    count = 0
    total = 0
    try:
        for name in os.listdir(base):
            if name.endswith(".part"):
                continue
            try:
                total += os.path.getsize(os.path.join(base, name))
                count += 1
            except OSError:
                pass
    except OSError:
        pass
    return {"tracks": count, "bytes": total, "mb": round(total / 1048576, 1)}


def clear() -> int:
    base = folder()
    removed = 0
    try:
        for name in os.listdir(base):
            try:
                os.remove(os.path.join(base, name))
                removed += 1
            except OSError:
                pass
    except OSError:
        pass
    _index.clear()
    _touched.clear()
    return removed


def mime_for(path: str) -> str:
    return MIME_BY_EXT.get(os.path.splitext(path)[1].lower(), "audio/mpeg")


_last_touch = 0.0
_touch_lock = threading.Lock()


def touch_periodic() -> None:
    global _last_touch
    now = time.monotonic()
    with _touch_lock:
        if now - _last_touch <= 300:
            return
        _last_touch = now
    trim()

def _quality_meta(media: dict) -> dict:
    """Codec/bitrate reported by the source, kept with the cached object (v72)."""
    kbps = media.get("bitrate")
    try:
        kbps = int(round(float(kbps))) if kbps else None
        if kbps and kbps > 4000:  # some sources report bit/s
            kbps = int(round(kbps / 1000))
    except (TypeError, ValueError):
        kbps = None
    return {"codec": media.get("codec"), "kbps": kbps, "source": media.get("source_id")}


# UI v8 stores complete objects inside one private SQLite cache, never loose MP3s.
def _ext_mime(media):
    return MIME_BY_EXT.get(_ext_for("",media.get("url", "")), "audio/mpeg")
find = audiovault.find
stats = audiovault.stats
clear = audiovault.clear
trim = audiovault.trim
mime_for = audiovault.mime_for

folder = audiovault.folder

# Prefetch failures must not accumulate complete-looking temporary payloads.
_download_impl = download
async def download(session, track_id: str, media: dict) -> str:
    try:
        return await _download_impl(session, track_id, media)
    except BaseException:
        part, _ = paths_for(track_id, media)
        try: os.remove(part)
        except OSError: pass
        raise
