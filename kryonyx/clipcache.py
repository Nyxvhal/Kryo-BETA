"""
clipcache.py — клип скачивается на диск параллельно с просмотром.

Зачем. Раньше клип шёл прямо из CDN одним потоком: перемотка зависела от
того, как ответит googlevideo (он любит отдавать 200 вместо 206, обрывать
соединение и выдавать 403 на открытый диапазон), а повторный заход качал всё
заново. Теперь схема такая:

  1. ссылка на ролик берётся у любого из движков (innertube, yt-dlp,
     pytubefix, Piped, Invidious);
  2. фоновая задача (`Job`) качает файл на диск последовательно, окнами по
     2 МиБ — каждое окно честный Range-запрос, поэтому CDN не обрывает;
  3. плеер читает тот же файл: что уже скачано — отдаётся с диска мгновенно
     (перемотка назад бесплатна), что чуть впереди — ждёт скачивания, а
     далёкая перемотка вперёд идёт отдельным окном прямо из CDN;
  4. скачанный ролик остаётся в кэше: следующий запуск стартует мгновенно и
     перематывается как обычный локальный файл.

Задача стартует сама, как только известен клип играющего трека, — к моменту
нажатия «Клип» значительная часть файла уже на диске.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import time
from typing import Any, AsyncIterator, Awaitable, Callable

import aiohttp

from .paths import data_dir
from . import audiovault

log = logging.getLogger("kryonyx.clipcache")

CHUNK = 2 * 1024 * 1024         # окно одного Range-запроса
AHEAD = 6 * 1024 * 1024         # насколько вперёд от скачанного ещё ждём диск
MAX_SIZE = 400 * 1024 * 1024    # больше — это не клип
KEEP_BYTES = 3000 * 1024 * 1024
KEEP_FILES = 80
_HOP = {"host", "connection", "content-length", "transfer-encoding",
        "content-encoding", "accept-encoding", "range"}

GetMedia = Callable[[bool], Awaitable[dict]]


def folder() -> str:
    path = os.path.join(data_dir(), "video-cache")
    os.makedirs(path, exist_ok=True)
    return path


def _safe(video_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(video_id))[-40:]


def final_path(video_id: str, height: int) -> str:
    return os.path.join(folder(), f"{_safe(video_id)}-p{int(height or 0)}.mp4")


def ready_file(video_id: str, quality: int) -> tuple[str, int] | None:
    """Готовый файл ролика: самый высокий не выше нужного, иначе любой."""
    prefix = _safe(video_id) + "-"
    found: list[tuple[int, str]] = []
    try:
        names = os.listdir(folder())
    except OSError:
        return None
    for name in names:
        match = re.fullmatch(re.escape(prefix) + r"(?:p)?(\d+)\.mp4", name)
        if not match:
            continue
        path = os.path.join(folder(), name)
        try:
            if os.path.getsize(path) > 256 * 1024:
                found.append((int(match.group(1)), path))
        except OSError:
            continue
    if not found:
        return None
    fits = [row for row in found if row[0] <= max(144, quality)]
    height, path = max(fits or found)
    return path, height


def prune() -> None:
    """Держит кэш в разумных пределах: старое уходит первым."""
    try:
        rows = []
        for name in os.listdir(folder()):
            path = os.path.join(folder(), name)
            if not os.path.isfile(path):
                continue
            stat = os.stat(path)
            if ".part" in name and time.time() - stat.st_mtime > 3600 \
                    and not any(j.part == path and not j.finished for j in _jobs.values()):
                os.remove(path)
                continue
            if name.endswith((".mp4", ".webm")) and ".part" not in name:
                rows.append((stat.st_mtime, stat.st_size, path))
        rows.sort(reverse=True)
        total = 0
        for index, (_, size, path) in enumerate(rows):
            total += size
            if index >= KEEP_FILES or total > KEEP_BYTES:
                try:
                    os.remove(path)
                except OSError:
                    pass
    except OSError:
        pass


def total_of(resp: aiohttp.ClientResponse) -> int | None:
    match = re.search(r"/(\d+)\s*$", resp.headers.get("Content-Range", ""))
    if match:
        return int(match.group(1))
    if resp.status == 200:
        try:
            return int(resp.headers["Content-Length"])
        except (KeyError, ValueError):
            return None
    return None


class Window:
    """Один открытый Range-запрос к CDN, начиная с нужного байта."""

    def __init__(self, resp: aiohttp.ClientResponse, start: int, media: dict):
        self.resp = resp
        self.start = start
        self.media = media
        self.total = total_of(resp)
        # 200 вместо 206: CDN проигнорировал Range и шлёт файл с начала.
        self.skip = start if (resp.status == 200 and start > 0) else 0

    async def chunks(self) -> AsyncIterator[bytes]:
        skip = self.skip
        async for chunk in self.resp.content.iter_chunked(128 * 1024):
            if skip:
                if len(chunk) <= skip:
                    skip -= len(chunk)
                    continue
                chunk, skip = chunk[skip:], 0
            yield chunk

    def release(self) -> None:
        try:
            self.resp.release()
        except Exception:
            pass


async def open_window(session: aiohttp.ClientSession, get_media: GetMedia,
                      start: int, end: int | None, *, refresh: bool = False
                      ) -> Window:
    """Окно [start, end] с обновлением ссылки на 403/410 и разрывах."""
    last: Exception | None = None
    for attempt in range(3):
        media = await get_media(refresh or attempt > 0)
        headers = {k: v for k, v in (media.get("headers") or {}).items()
                   if k.lower() not in _HOP}
        headers["Range"] = f"bytes={start}-{'' if end is None else end}"
        try:
            resp = await session.get(media["url"], headers=headers)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last = exc
            continue
        if resp.status in (403, 410):
            resp.release()
            last = RuntimeError(f"the link expired (HTTP {resp.status})")
            continue
        if resp.status >= 400 and resp.status != 416:
            resp.release()
            raise RuntimeError(f"the source answered HTTP {resp.status}")
        return Window(resp, start, media)
    raise RuntimeError(str(last or "the source did not answer"))


# --------------------------------------------------------------------------- #
# фоновая загрузка
# --------------------------------------------------------------------------- #
class Job:
    def __init__(self, key: str, video_id: str, height: int):
        self.key = key
        self.video_id = video_id
        self.height = height
        self.final = final_path(video_id, height)
        self.part = self.final + ".part"
        self.total: int | None = None
        self.written = 0
        self.done = False
        self.error = ""
        self.finished = False
        self.failed_at = 0.0
        self.cond = asyncio.Condition()
        self.task: asyncio.Task | None = None

    def path(self) -> str:
        return self.final if self.done else self.part

    async def pulse(self) -> None:
        async with self.cond:
            self.cond.notify_all()

    async def wait(self, timeout: float) -> None:
        try:
            async with self.cond:
                await asyncio.wait_for(self.cond.wait(), timeout)
        except asyncio.TimeoutError:
            pass


_jobs: dict[str, Job] = {}
_gate = asyncio.Semaphore(2)


async def _run(job: Job, session: aiohttp.ClientSession, get_media: GetMedia) -> None:
    started = time.monotonic()
    try:
        async with _gate:
            if os.path.exists(job.part):
                os.remove(job.part)
            fh = open(job.part, "wb")
            try:
                breaks = 0
                while True:
                    if job.total is not None and job.written >= job.total:
                        break
                    end = job.written + CHUNK - 1
                    if job.total is not None:
                        end = min(end, job.total - 1)
                    try:
                        win = await open_window(session, get_media, job.written, end)
                    except RuntimeError:
                        breaks += 1
                        if breaks > 4:
                            raise
                        await asyncio.sleep(0.5 * breaks)
                        continue
                    if win.resp.status == 416:
                        win.release()
                        break           # дальше файла уже нет
                    if win.total is not None:
                        if win.total > MAX_SIZE:
                            win.release()
                            raise RuntimeError("the file is too large for a clip")
                        job.total = win.total
                    got = 0
                    try:
                        async for chunk in win.chunks():
                            fh.write(chunk)
                            fh.flush()
                            job.written += len(chunk)
                            got += len(chunk)
                            await job.pulse()
                            if job.total is None and job.written > MAX_SIZE:
                                raise RuntimeError("the file is too large for a clip")
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        breaks += 1
                        if breaks > 6:
                            raise RuntimeError("the connection kept dropping")
                    finally:
                        win.release()
                    if got == 0:
                        breaks += 1
                        if breaks > 6:
                            raise RuntimeError("the source returned no data")
                    elif win.resp.status == 200 and job.total is None:
                        break           # без размера и без Range: тело кончилось
                    await job.pulse()
            finally:
                fh.close()
            if job.written < 256 * 1024:
                raise RuntimeError("the clip download was incomplete")
            if job.total is not None and job.written < job.total:
                raise RuntimeError("the clip download was cut short")
            for attempt in range(8):
                try:
                    os.replace(job.part, job.final)
                    break
                except PermissionError:      # Windows: файл ещё читается
                    await asyncio.sleep(0.25)
            else:
                raise RuntimeError("cannot finalize the clip file")
            job.total = job.written
            job.done = True
            log.info("[clip] %s %sp saved: %.1f MB in %.1fs", job.video_id,
                     job.height, job.written / 1048576, time.monotonic() - started)
            await audiovault.run_blocking_owned(prune)
    except asyncio.CancelledError:
        try:
            os.remove(job.part)
        except FileNotFoundError:
            pass
        raise
    except Exception as exc:
        job.error = str(exc) or exc.__class__.__name__
        job.failed_at = time.monotonic()
        log.info("[clip] %s: download failed: %s", job.video_id, job.error)
        try:
            os.remove(job.part)
        except OSError:
            pass
    finally:
        job.finished = True
        await job.pulse()


def ensure(session: aiohttp.ClientSession, video_id: str, height: int,
           get_media: GetMedia) -> Job:
    """Запускает загрузку, если её ещё нет (или прошлая упала давно)."""
    key = f"{video_id}@{height}"
    job = _jobs.get(key)
    if job is not None:
        if not job.finished or (job.error and time.monotonic() - job.failed_at < 60):
            return job
        if job.done and os.path.isfile(job.final):
            return job
    job = Job(key, video_id, height)
    _jobs[key] = job
    if len(_jobs) > 60:
        for old in [k for k, j in _jobs.items() if j.finished and k != key][:30]:
            _jobs.pop(old, None)
    job.task = asyncio.create_task(_run(job, session, get_media))
    return job


def active(video_id: str) -> Job | None:
    for job in _jobs.values():
        if job.video_id == video_id and not job.finished:
            return job
    return None


def read_at(path: str, pos: int, size: int) -> bytes:
    with open(path, "rb") as fh:
        fh.seek(pos)
        return fh.read(size)


def status() -> dict[str, Any]:
    try:
        files = [n for n in os.listdir(folder()) if n.endswith((".mp4", ".webm"))
                 and ".part" not in n]
        size = sum(os.path.getsize(os.path.join(folder(), n)) for n in files)
    except OSError:
        files, size = [], 0
    return {"files": len(files), "bytes": size,
            "active": sum(1 for j in _jobs.values() if not j.finished)}


def clear() -> int:
    removed = 0
    for name in os.listdir(folder()):
        if name.endswith((".mp4", ".webm", ".part")) and not any(
                j.part.endswith(name) and not j.finished for j in _jobs.values()) \
                and not any(not h.finished and name.startswith(_safe(h.video_id))
                            for h in _hd_jobs.values()):
            try:
                os.remove(os.path.join(folder(), name))
                removed += 1
            except OSError:
                pass
    return removed


# --------------------------------------------------------------------------- #
# клипы в выбранном качестве: видео и звук отдельно, склейка в один файл
# --------------------------------------------------------------------------- #
# YouTube отдаёт готовый файл «видео+звук» только до 360p. Всё, что выше, лежит
# двумя дорожками. Их качают параллельными Range-окнами (быстро и без обрывов),
# склеивают без перекодирования (`-c copy`, секунды) и дальше работают с обычным
# локальным файлом: перемотка в любую точку мгновенная, повторный запуск без сети.
CHUNK_HD = 4 * 1024 * 1024
WORKERS = 4


def ffmpeg_exe() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ready_hd(video_id: str, quality: int) -> tuple[str, int] | None:
    """Склеенный клип запрошенного качества, если он уже на диске."""
    pattern = re.compile(re.escape(_safe(video_id)) + rf"-hd{int(quality)}-(\d+)\.(?:mp4|webm)")
    try:
        names = os.listdir(folder())
    except OSError:
        return None
    for name in names:
        match = pattern.fullmatch(name)
        if match:
            path = os.path.join(folder(), name)
            try:
                if os.path.getsize(path) > 256 * 1024:
                    return path, int(match.group(1))
            except OSError:
                pass
    return None


class HDJob:
    def __init__(self, key: str, video_id: str, quality: int):
        self.key, self.video_id, self.quality = key, video_id, quality
        self.state = "resolving"        # resolving | downloading | muxing | done | error
        self.progress = 0.0
        self.height = 0
        self.error = ""
        self.finished = False
        self.failed_at = 0.0
        self.path = ""
        self.task: asyncio.Task | None = None


_hd_jobs: dict[str, HDJob] = {}
_hd_gate = asyncio.Semaphore(2)


async def _download_parallel(session, get_media: GetMedia, dest: str, size_hint: int | None,
                             on_bytes: Callable[[int, int | None], None]) -> int:
    """Скачивает один файл параллельными окнами. Возвращает размер."""
    first = await open_window(session, get_media, 0, CHUNK_HD - 1)
    total = first.total or size_hint
    if not total:
        first.release()
        raise RuntimeError("the source did not tell the file size")
    if total > 3 * 1024 * 1024 * 1024:
        first.release()
        raise RuntimeError("the file is too large")
    with open(dest, "wb") as fh:
        fh.truncate(total)
    pending = list(range(CHUNK_HD, total, CHUNK_HD))[::-1]     # окно 0 уже открыто
    on_bytes(0, total)

    async def fetch(offset: int, win: Window | None) -> None:
        end = min(offset + CHUNK_HD, total) - 1
        for attempt in range(4):
            pos = offset
            try:
                if win is None:
                    win = await open_window(session, get_media, pos, end,
                                            refresh=attempt > 1)
                with open(dest, "r+b") as fh:
                    fh.seek(pos)
                    async for chunk in win.chunks():
                        chunk = chunk[:end - pos + 1]
                        if not chunk:
                            break
                        fh.write(chunk)
                        pos += len(chunk)
                        on_bytes(len(chunk), None)
                        if pos > end:
                            break
                if pos > end:
                    return
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
                pass
            finally:
                if win is not None:
                    win.release()
                    win = None
            on_bytes(-(pos - offset), None)        # окно придётся качать заново
            await asyncio.sleep(0.4 * (attempt + 1))
        raise RuntimeError("a part of the clip could not be downloaded")

    async def worker(first_win: Window | None) -> None:
        if first_win is not None:
            await fetch(0, first_win)
        while pending:
            await fetch(pending.pop(), None)

    await asyncio.gather(*(worker(first if i == 0 else None) for i in range(WORKERS)))
    return total


async def _mux(video: str, audio: str, dest: str, container: str) -> None:
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("FFmpeg is needed to join video and audio (install imageio-ffmpeg)")
    args = [exe, "-y", "-hide_banner", "-loglevel", "error", "-i", video, "-i", audio,
            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy"]
    if container == "mp4":
        args += ["-movflags", "+faststart"]
    args += ["-f", container, dest]
    kwargs: dict[str, Any] = {"stdout": asyncio.subprocess.PIPE,
                              "stderr": asyncio.subprocess.PIPE}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    proc = await asyncio.create_subprocess_exec(*args, **kwargs)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), 180)
    except asyncio.CancelledError:
        if proc.returncode is None:proc.kill()
        await proc.wait()
        raise
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError("joining video and audio took too long")
    if proc.returncode != 0:
        text = (err or b"").decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError("FFmpeg: " + (text[-1] if text else f"exit {proc.returncode}"))


async def _run_hd(job: HDJob, session, resolve: Callable[[bool], Awaitable[dict]]) -> None:
    started = time.monotonic()
    base = os.path.join(folder(), f"{_safe(job.video_id)}-hd{job.quality}")
    vpart, apart = base + ".v.part", base + ".a.part"
    try:
        async with _hd_gate:
            pair = await resolve(False)
            job.height = int(pair["video"].get("height") or job.quality)
            container = pair.get("container") or "mp4"
            final = f"{base}-{job.height}.{container}"
            job.state = "downloading"
            sizes = {"v": int(pair["video"].get("size") or 0), "a": int(pair["audio"].get("size") or 0)}
            done = {"v": 0, "a": 0}

            def tracker(key: str):
                def on(n: int, total: int | None) -> None:
                    if total:
                        sizes[key] = total
                    done[key] = max(0, done[key] + n)
                    whole = sum(sizes.values()) or 1
                    job.progress = min(0.99, sum(done.values()) / whole)
                return on

            def getter(kind: str) -> GetMedia:
                async def get(refresh: bool) -> dict:
                    nonlocal pair
                    if refresh:
                        pair = await resolve(True)
                    return pair[kind]
                return get

            await asyncio.gather(
                _download_parallel(session, getter("video"), vpart, sizes["v"], tracker("v")),
                _download_parallel(session, getter("audio"), apart, sizes["a"], tracker("a")))
            job.state = "muxing"
            tmp = final + ".part"
            await _mux(vpart, apart, tmp, container)
            for _ in range(8):
                try:
                    os.replace(tmp, final)
                    break
                except PermissionError:
                    await asyncio.sleep(0.25)
            job.path, job.progress, job.state = final, 1.0, "done"
            log.info("[clip] %s %sp saved (%s): %.1f MB in %.1fs", job.video_id, job.height,
                     container, os.path.getsize(final) / 1048576, time.monotonic() - started)
            await audiovault.run_blocking_owned(prune)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        job.state, job.error = "error", str(exc) or exc.__class__.__name__
        job.failed_at = time.monotonic()
        log.info("[clip] %s: %sp failed: %s", job.video_id, job.quality, job.error)
    finally:
        for path in (vpart, apart):
            try:
                os.remove(path)
            except OSError:
                pass
        job.finished = True


def ensure_hd(session, video_id: str, quality: int,
              resolve: Callable[[bool], Awaitable[dict]], *, force: bool = False) -> HDJob:
    key = f"{video_id}@{quality}"
    job = _hd_jobs.get(key)
    if job is not None and not force:
        if not job.finished or (job.error and time.monotonic() - job.failed_at < 20) \
                or job.state == "done":
            return job
    if job is not None and not job.finished:
        return job
    job = HDJob(key, video_id, quality)
    _hd_jobs[key] = job
    if len(_hd_jobs) > 60:
        for old in [k for k, j in _hd_jobs.items() if j.finished and k != key][:30]:
            _hd_jobs.pop(old, None)
    job.task = asyncio.create_task(_run_hd(job, session, resolve))
    return job


async def close_jobs() -> None:
    """Stop clip downloads before their shared HTTP session is closed."""
    tasks = [job.task for job in [*_jobs.values(), *_hd_jobs.values()]
             if job.task is not None and not job.task.done()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
