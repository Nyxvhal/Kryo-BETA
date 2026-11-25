"""
ytdlp_bin.py — официальный бинарник yt-dlp как внешний процесс.

Схема простая («голый» запуск официального бинарника yt-dlp и
ytdlp_setup.rs): приложение не полагается на вкомпилированную библиотеку, а
держит рядом свежий бинарник yt-dlp, сам его скачивает и раз в час проверяет
обновление. Именно поэтому YouTube продолжает работать, когда
Piped/Invidious лежат, а вшитая в сборку версия yt-dlp уже устарела.

Что делает модуль:
  * start_auto()      — фоновая установка при старте и автопроверка раз в час;
  * ensure()          — скачать бинарник (если его нет) и обновить раз в час;
  * search()          — ytsearchN:<запрос> через --dump-json --flat-playlist;
  * stream()          — прямая ссылка на аудиодорожку для видео;
  * playlist()        — список треков плейлиста/микса.

Всё общение — NDJSON на stdout. На Windows процесс стартует с
CREATE_NO_WINDOW, чтобы не мигало консольное окно.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import shutil
import stat
import sys
import time
import zipfile
from typing import Any

from . import netproxy, ytcookies
from .paths import app_dir, data_dir

log = logging.getLogger("kryonyx.ytdlp")

# Nightly-сборки обновляются каждый день и первыми получают заплатки к
# очередной поломке YouTube.
RELEASE_BASE = "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download"
RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
UPDATE_INTERVAL = 3600.0          # как часто проверять версию бинарника

# Повтор при обрыве сети: ждём всё дольше, но не больше четверти часа, чтобы
# при появлении интернета бинарник подтянулся сам, без перезапуска программы.
RETRY_DELAYS = (15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 900.0)
# Чужое обновление считаем брошенным, если файл-замок не обновлялся столько.
LOCK_STALE = 900.0

_path: str | None = None
_ready = False
_lock = asyncio.Lock()
_last_error: str = ""

# Состояние автообновления — его показывает /api/youtube/status.
_auto: dict[str, Any] = {
    "stage": "idle",          # idle | downloading | checking | ready | error | offline
    "auto": False,            # фоновая задача поднята
    "busy": False,            # прямо сейчас качаем/меняем бинарник
    "checked_at": 0.0,        # время последней успешной проверки версии
    "next_check": 0.0,        # когда запланирована следующая
    "attempts": 0,            # неудачных подряд
    "updated_at": 0.0,        # время последней успешной замены
    "rolled_back": False,     # последняя замена откатилась
}
_task: asyncio.Task | None = None
_session_factory = None
# Внеочередное обновление после бот-проверки: не чаще раза в десять минут,
# иначе серия неудачных треков устроила бы шквал запросов к GitHub.
_NUDGE_INTERVAL = 600.0
_nudged_at = 0.0
_nudge_task: asyncio.Task | None = None


# --------------------------------------------------------------------------- #
# имена файлов под текущую систему
# --------------------------------------------------------------------------- #
def _arch() -> str:
    machine = (platform.machine() or "").lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine in ("i386", "i686", "x86"):
        return "x86"
    return "x64"


def _asset_name() -> str:
    """Готовый однофайловый бинарник (без zip) — он есть для всех платформ."""
    arch = _arch()
    if os.name == "nt":
        if arch == "arm64":
            return "yt-dlp_arm64.exe"
        if arch == "x86":
            return "yt-dlp_x86.exe"
        return "yt-dlp.exe"
    if sys.platform == "darwin":
        return "yt-dlp_macos"
    return "yt-dlp_linux_aarch64" if arch == "arm64" else "yt-dlp_linux"


def _binary_name() -> str:
    return "yt-dlp.exe" if os.name == "nt" else "yt-dlp"


def folder() -> str:
    path = os.path.join(data_dir(), "ytdlp")
    os.makedirs(path, exist_ok=True)
    return path


def binary_path() -> str:
    return os.path.join(folder(), _binary_name())


def _stamp_path() -> str:
    return os.path.join(folder(), ".update_check")


def _read_stamp() -> dict:
    try:
        with open(_stamp_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_stamp(tag: str) -> None:
    try:
        tmp = _stamp_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"tag": tag, "checked_at": int(time.time())}, fh)
        os.replace(tmp, _stamp_path())
    except Exception as exc:
        log.debug("[yt-dlp] could not write the update stamp: %s", exc)


def _bundled() -> str | None:
    """Бинарник рядом с приложением или в PATH.

    Свой, автообновляемый файл всегда в приоритете: системный yt-dlp может
    быть старым, а именно свежесть и решает, работает ли YouTube.
    """
    # PyInstaller 6 puts collected binaries in `_internal` (`sys._MEIPASS`);
    # source/portable layouts keep them next to the main executable.
    roots = [app_dir()]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(str(meipass))
    for root in roots:
        for name in (_binary_name(), _asset_name()):
            candidate = os.path.join(root, name)
            if os.path.isfile(candidate):
                return candidate
    found = shutil.which("yt-dlp")
    return found or None


def _version_key(value: str) -> tuple[int, ...]:
    """Comparable key for stable and nightly date-based yt-dlp versions."""
    nums = [int(part) for part in re.findall(r"\d+", value or "")]
    return tuple(nums[:6])


# --------------------------------------------------------------------------- #
# установка и обновление
# --------------------------------------------------------------------------- #
def _backup_path() -> str:
    return binary_path() + ".bak"


def _lock_path() -> str:
    return os.path.join(folder(), ".update.lock")


def _acquire_file_lock() -> bool:
    """Не даём двум копиям программы менять бинарник одновременно.

    Замок — обычный файл: атомарное создание O_EXCL работает и на Windows, а
    брошенный после падения замок снимается по времени (LOCK_STALE).
    """
    path = _lock_path()
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"pid": os.getpid(), "at": int(time.time())}))
        return True
    except FileExistsError:
        try:
            age = time.time() - os.path.getmtime(path)
        except OSError:
            age = LOCK_STALE + 1
        if age < LOCK_STALE:
            log.debug("[yt-dlp] another instance is updating, skipping")
            return False
        log.info("[yt-dlp] removing a stale update lock (%.0f s old)", age)
        try:
            os.remove(path)
        except OSError:
            return False
        return _acquire_file_lock()
    except OSError as exc:
        # Папка данных недоступна для записи — обновляться всё равно некуда.
        log.warning("[yt-dlp] could not take the update lock: %s", exc)
        return False


def _release_file_lock() -> None:
    try:
        os.remove(_lock_path())
    except OSError:
        pass


async def _download(session, url: str, dest: str) -> None:
    async with session.get(url, allow_redirects=True) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status}")
        tmp = dest + ".part"
        with open(tmp, "wb") as fh:
            async for chunk in resp.content.iter_chunked(256 * 1024):
                fh.write(chunk)
    if os.path.getsize(tmp) < 1024 * 1024:       # бинарник весит десятки МБ
        os.remove(tmp)
        raise RuntimeError("the downloaded file was truncated")
    os.replace(tmp, dest)
    _make_executable(dest)


def _make_executable(path: str) -> None:
    if os.name == "nt":
        return
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as exc:
        log.debug("[yt-dlp] chmod failed: %s", exc)


async def _fetch_binary(session, dest: str) -> str:
    """Качает однофайловый бинарник в dest; если его нет — берёт zip."""
    try:
        await _download(session, f"{RELEASE_BASE}/{_asset_name()}", dest)
        return dest
    except Exception as exc:
        log.warning("[yt-dlp] direct file download failed (%s), trying zip", exc)

    zip_name = {"nt": "yt-dlp_win.zip"}.get(os.name) or (
        "yt-dlp_macos.zip" if sys.platform == "darwin" else "yt-dlp_linux.zip")
    archive = os.path.join(folder(), ".download.zip")
    unpacked = os.path.join(folder(), ".unpacked")
    try:
        await _download(session, f"{RELEASE_BASE}/{zip_name}", archive)
        await asyncio.to_thread(_extract, archive, unpacked)
        inner = os.path.join(unpacked, _binary_name())
        if not os.path.isfile(inner):
            raise RuntimeError("the archive has no binary")
        os.replace(inner, dest)
        _make_executable(dest)
    finally:
        for junk in (archive,):
            try:
                os.remove(junk)
            except OSError:
                pass
        shutil.rmtree(unpacked, ignore_errors=True)
    return dest


def _extract(archive: str, dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            name = os.path.basename(member)
            if not name:
                continue
            with zf.open(member) as src, open(os.path.join(dest, name), "wb") as out:
                shutil.copyfileobj(src, out)
    path = os.path.join(dest, _binary_name())
    if os.path.isfile(path) and os.name != "nt":
        os.chmod(path, 0o755)


async def _probe(program: str) -> str:
    """Свежескачанный файл обязан отвечать на --version, иначе он битый."""
    kwargs: dict[str, Any] = {"stdout": asyncio.subprocess.PIPE,
                              "stderr": asyncio.subprocess.PIPE}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    proc = await asyncio.create_subprocess_exec(program, "--version", **kwargs)
    try:
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=40)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("the new binary does not answer --version")
    if proc.returncode != 0:
        raise RuntimeError(f"the new binary exits with {proc.returncode}")
    return (out or b"").decode("utf-8", "replace").strip()


async def _install(session) -> str:
    """Ставит бинарник «в сторонке», проверяет и только потом подменяет.

    Так неудачная замена ничего не ломает: старый файл возвращается на место
    (на Windows его вообще нельзя переписать, пока он запущен) и YouTube
    продолжает работать на прежней версии.
    """
    target = binary_path()
    # На Windows временный файл тоже обязан оканчиваться на .exe. С именем
    # `yt-dlp.exe.new` свежий PyInstaller-бинарник у части систем завершался
    # с 0xFFFFFFFF ещё до проверки версии.
    staged = target + (".new.exe" if os.name == "nt" else ".new")
    backup = _backup_path()
    had_old = os.path.isfile(target)

    await _fetch_binary(session, staged)
    try:
        version_text = await _probe(staged)
    except Exception as exc:
        _safe_remove(staged)
        raise RuntimeError(f"the downloaded binary is broken: {exc}") from exc

    try:
        if had_old:
            _safe_remove(backup)
            os.replace(target, backup)
        os.replace(staged, target)
        _make_executable(target)
    except OSError as exc:
        # Тихий откат: возвращаем прежний файл и живём на нём дальше.
        _safe_remove(staged)
        if had_old and not os.path.isfile(target) and os.path.isfile(backup):
            try:
                os.replace(backup, target)
            except OSError as back_exc:
                log.error("[yt-dlp] rollback failed: %s", back_exc)
        _auto["rolled_back"] = True
        raise RuntimeError(f"could not replace the binary: {exc}") from exc

    _auto["rolled_back"] = False
    _auto["updated_at"] = time.time()
    log.info("[yt-dlp] binary in place: %s", version_text or "unknown version")
    return target


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _restore_backup() -> bool:
    """Если рабочего файла нет, а резервная копия есть — поднимаем её."""
    target, backup = binary_path(), _backup_path()
    if os.path.isfile(target) or not os.path.isfile(backup):
        return False
    try:
        shutil.copy2(backup, target)
        _make_executable(target)
        log.info("[yt-dlp] restored the previous binary from the backup")
        return True
    except OSError as exc:
        log.warning("[yt-dlp] could not restore the backup: %s", exc)
        return False


async def _latest_tag(session) -> str:
    async with session.get(RELEASE_API, headers={"User-Agent": "KryonyxMusic"}) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    return str((data or {}).get("tag_name") or "")


async def ensure(session=None, *, force: bool = False) -> bool:
    """Гарантирует рабочий бинарник. Возвращает True, если он готов.

    Безопасно вызывать при каждом старте и из кнопки в настройках: скачивание
    идёт один раз, дальше только часовая проверка версии.
    """
    global _path, _ready, _last_error
    async with _lock:
        target = binary_path()
        _restore_backup()
        have = os.path.isfile(target)
        local = _bundled()
        if not have:
            # Пока своего файла нет, играем на том, что нашлось рядом или в
            # PATH — но всё равно качаем свою копию: только её мы обновляем.
            if local:
                _path, _ready, _last_error = local, True, ""
                _auto["stage"] = "downloading"

        if have:
            # Файл на месте — YouTube уже работает, даже если проверка версии
            # или загрузка новой сборки сейчас не удастся.
            _path, _ready = target, True
            _auto["stage"] = "ready"
            # Установщик несёт проверенный свежий yt-dlp. Старая копия в
            # профиле пользователя раньше всегда перекрывала его, а обновить
            # её без доступа к GitHub было невозможно. На первом запуске
            # выбираем более новую из двух, ничего не удаляя.
            if (local and os.path.abspath(local) != os.path.abspath(target)
                    and (_path is None or _path == target)):
                try:
                    target_ver, local_ver = await asyncio.gather(
                        _probe(target), _probe(local))
                    if _version_key(local_ver) >= _version_key(target_ver):
                        _path = local
                        log.info("[yt-dlp] packaged %s supersedes profile %s",
                                 local_ver, target_ver)
                except Exception as exc:
                    # Если профильная копия битая, рабочая комплектная важнее.
                    try:
                        await _probe(local)
                        _path = local
                        log.warning("[yt-dlp] using packaged binary; profile copy "
                                    "failed validation: %s", exc)
                    except Exception:
                        pass

        own_session = False
        if session is None:
            import aiohttp
            session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=600, sock_connect=20),
                **netproxy.session_kwargs())
            own_session = True
        locked = False
        try:
            if not have or force:
                locked = await asyncio.to_thread(_acquire_file_lock)
                if not locked:
                    # Обновляет другая копия программы: ждать нечего.
                    return _ready
            _auto["busy"] = True
            if not have:
                _auto["stage"] = "downloading"
                log.info("[yt-dlp] binary missing, downloading %s", _asset_name())
                try:
                    _path = await _install(session)
                    _ready = True
                    _last_error = ""
                    _auto["stage"] = "ready"
                    _auto["attempts"] = 0
                    try:
                        _write_stamp(await _latest_tag(session))
                    except Exception:
                        _write_stamp("unknown")
                    _auto["checked_at"] = time.time()
                    log.info("[yt-dlp] installed: %s", _path)
                except Exception as exc:
                    _last_error = str(exc)
                    _auto["stage"] = "offline" if _looks_offline(exc) else "error"
                    _auto["attempts"] += 1
                    log.error("[yt-dlp] install failed: %s", exc)
                    _restore_backup()
                    if (not (_path and os.path.isfile(_path))
                            and os.path.isfile(binary_path())):
                        _path, _ready = binary_path(), True
                    return _ready
            else:
                await _maybe_update(session, target, force)
            return _ready
        finally:
            _auto["busy"] = False
            if locked:
                _release_file_lock()
            if own_session:
                await session.close()


def _looks_offline(exc: Exception) -> bool:
    """Нет интернета — это не ошибка приложения: не шумим в журнале."""
    import socket
    if isinstance(exc, (OSError, socket.gaierror, asyncio.TimeoutError)):
        return True
    text = str(exc).lower()
    return any(hint in text for hint in (
        "temporary failure in name resolution", "name or service not known",
        "cannot connect", "connection reset", "network is unreachable",
        "timed out", "timeout", "ssl", "getaddrinfo"))


async def _maybe_update(session, target: str, force: bool) -> None:
    """Часовая проверка версии и, если нужно, замена бинарника.

    Неудача здесь безопасна: рабочий файл остаётся прежним, а ошибка попадёт
    только в журнал — пользователь продолжает слушать музыку.
    """
    global _path, _ready, _last_error
    stamp = _read_stamp()
    age = time.time() - float(stamp.get("checked_at") or 0)
    if not force and age < UPDATE_INTERVAL:
        return

    _auto["stage"] = "checking"
    tag = ""
    try:
        tag = await _latest_tag(session)
        _auto["checked_at"] = time.time()
        _auto["attempts"] = 0
    except Exception as exc:
        log.debug("[yt-dlp] version check failed: %s", exc)
        _auto["stage"] = "offline" if _looks_offline(exc) else "error"
        _auto["attempts"] += 1
        _write_stamp(str(stamp.get("tag") or "unknown"))
        if not force:
            return

    if tag and tag == stamp.get("tag") and not force:
        _write_stamp(tag)
        _auto["stage"] = "ready"
        return

    log.info("[yt-dlp] updating to %s", tag or "latest")
    _auto["stage"] = "downloading"
    try:
        _path = await _install(session)
        _ready = True
        _last_error = ""
        _write_stamp(tag or str(stamp.get("tag") or "unknown"))
        _auto["stage"] = "ready"
    except Exception as exc:
        # Обновление не удалось — остаёмся на прежнем бинарнике, он рабочий.
        log.warning("[yt-dlp] update failed, keeping the current binary: %s", exc)
        _last_error = str(exc)
        _restore_backup()
        if not (_path and os.path.isfile(_path)) and os.path.isfile(target):
            _path, _ready = target, True
        _auto["stage"] = "ready" if os.path.isfile(target) else (
            "offline" if _looks_offline(exc) else "error")
        _write_stamp(str(stamp.get("tag") or "unknown"))


# --------------------------------------------------------------------------- #
# фоновая автоустановка и автопроверка
# --------------------------------------------------------------------------- #
async def _auto_loop(session_factory) -> None:
    """Ставит бинарник при первом запуске и раз в час проверяет обновление.

    Окно при этом не ждёт: задача живёт в фоне. Нет сети — повторяем с
    растущей паузой, пока не получится, и не мешаем пользователю.
    """
    attempt = 0
    while True:
        try:
            session = await session_factory() if callable(session_factory) else session_factory
            good = await ensure(session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            good = False
            log.debug("[yt-dlp] auto check failed: %s", exc)
        # Час до следующей проверки — только когда своя копия на месте.
        # Иначе (нет сети, битая загрузка) повторяем с растущей паузой.
        settled = good and os.path.isfile(binary_path())
        if settled:
            attempt = 0
            delay = UPDATE_INTERVAL
        else:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            attempt += 1
            log.info("[yt-dlp] binary is not in place yet, retrying in %.0f s", delay)
        _auto["next_check"] = time.time() + delay
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise


def start_auto(session_factory=None) -> asyncio.Task:
    """Поднимает фоновую задачу автоустановки/автообновления (идемпотентно)."""
    global _task, _session_factory
    _session_factory = session_factory or _session_factory
    if _task is not None and not _task.done():
        return _task
    _auto["auto"] = True
    _task = asyncio.create_task(_auto_loop(session_factory))
    return _task


def nudge_update(reason: str = "") -> None:
    """Проверить обновление прямо сейчас — после отказа YouTube.

    Чаще всего «не отдаёт поток» означает, что YouTube опять поменял плеер, а
    заплатка в nightly-сборке yt-dlp уже вышла. Ждать планового часа в этот
    момент бессмысленно: запускаем проверку в фоне, трек тем временем
    доигрывает свои попытки.
    """
    global _nudged_at, _nudge_task
    now = time.monotonic()
    if _auto["busy"] or (_nudge_task is not None and not _nudge_task.done()):
        return
    if now - _nudged_at < _NUDGE_INTERVAL:
        return
    _nudged_at = now

    async def work() -> None:
        try:
            factory = _session_factory
            session = await factory() if callable(factory) else factory
            log.info("[yt-dlp] checking for an update right away (%s)", reason or "failure")
            await ensure(session, force=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("[yt-dlp] out-of-schedule update failed: %s", exc)

    try:
        _nudge_task = asyncio.create_task(work())
    except RuntimeError:                   # нет работающего цикла — не беда
        _nudge_task = None


async def stop_auto() -> None:
    global _task
    task, _task = _task, None
    _auto["auto"] = False
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


def ready() -> bool:
    if _ready and _path and (os.path.isfile(_path) or shutil.which(_path)):
        return True
    return bool(_bundled()) or os.path.isfile(binary_path())


def path() -> str | None:
    if _path and (os.path.isfile(_path) or shutil.which(_path)):
        return _path
    target = binary_path()
    if os.path.isfile(target):
        return target
    return _bundled()


# --------------------------------------------------------------------------- #
# запуск процесса
# --------------------------------------------------------------------------- #
_COMMON = ("--no-warnings", "--no-progress", "--no-color", "--ignore-config",
           "--no-check-certificates", "--socket-timeout", "15", "--retries", "2",
           # Бесплатные подсказки против блокировок: региональные замки
           # снимаются заголовком, а разовый сбой извлечения — повтором.
           "--geo-bypass", "--extractor-retries", "3")


def _cookie_args() -> tuple[str, ...]:
    """Cookies для любого запуска yt-dlp.

    Сначала файл, которым управляют настройки (Настройки → YouTube → Cookies),
    затем файл, положенный рядом с программой руками, и только потом —
    браузер, выбранный в настройках. Браузерный путь последний: он читает
    профиль с диска и на закрытом браузере иногда подвисает.
    """
    try:
        target = ytcookies.path()
    except Exception:
        target = None
    if target:
        return ("--cookies", target)
    try:
        chosen = ytcookies.browser()
    except Exception:
        chosen = ""
    if chosen:
        return ("--cookies-from-browser", chosen)
    return ()


def cookies_ready() -> bool:
    return bool(_cookie_args())


async def run(args: list[str], timeout: float = 45.0) -> str:
    """Запускает yt-dlp и возвращает stdout. Ошибки — RuntimeError со stderr."""
    program = path()
    if not program:
        raise RuntimeError("yt-dlp binary is not installed yet")

    kwargs: dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000        # CREATE_NO_WINDOW
    proc = await asyncio.create_subprocess_exec(
        program, *_COMMON, *netproxy.ytdlp_args(), *_cookie_args(), *args, **kwargs)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        if proc.returncode is None:
            try: proc.kill()
            except ProcessLookupError: pass
        await proc.communicate()
        if isinstance(exc, asyncio.CancelledError): raise
        raise RuntimeError("yt-dlp timed out") from exc
    if proc.returncode != 0:
        message = (err or b"").decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(message[-1] if message else f"yt-dlp exit {proc.returncode}")
    return (out or b"").decode("utf-8", "replace")


async def pipe_format(video_id_or_url: str, fmt: str) -> asyncio.subprocess.Process:
    """Качает выбранную дорожку в stdout сразу, без ожидания всего файла."""
    program = path()
    if not program:
        raise RuntimeError("yt-dlp binary is not installed yet")
    url = str(video_id_or_url or "")
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={url}"
    kwargs: dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    return await asyncio.create_subprocess_exec(
        program, *_COMMON, *netproxy.ytdlp_args(), *_cookie_args(), "--no-playlist",
        "-f", fmt, "-o", "-", url, **kwargs)


def _ndjson(text: str) -> list[dict]:
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items


# --------------------------------------------------------------------------- #
# нормализация в формат Kryonyx
# --------------------------------------------------------------------------- #
def _thumb(entry: dict) -> str | None:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = [t for t in (entry.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]
    if thumbs:
        thumbs.sort(key=lambda t: (t.get("width") or 0))
        return thumbs[-1]["url"]
    vid = entry.get("id")
    return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg" if vid else None


def _artist(entry: dict) -> str:
    artists = entry.get("artists")
    if isinstance(artists, list) and artists:
        return str(artists[0])
    for key in ("artist", "creator", "channel", "uploader"):
        value = entry.get(key)
        if value:
            return str(value).split(",")[0].replace(" - Topic", "").strip()
    return "YouTube"


def _track(entry: dict) -> dict | None:
    vid = entry.get("id")
    title = (entry.get("title") or "").strip()
    if not vid or not title or title in ("[Private video]", "[Deleted video]"):
        return None
    duration = entry.get("duration")
    return {
        "id": "yt:" + str(vid),
        "title": str(entry.get("track") or title).strip(),
        "artist": _artist(entry),
        "album": entry.get("album"),
        "duration": int(duration) if isinstance(duration, (int, float)) and duration > 0 else None,
        "thumbnail": _thumb(entry),
        "source": "youtube",
        "url": f"https://www.youtube.com/watch?v={vid}",
        # Сырое имя канала: по «- Topic» видно авто-трек со статичной обложкой.
        "channel": str(entry.get("channel") or entry.get("uploader") or ""),
    }


# --------------------------------------------------------------------------- #
# публичные операции
# --------------------------------------------------------------------------- #
async def search(query: str, limit: int = 25) -> list[dict]:
    query = (query or "").strip()
    if not query or not ready():
        return []
    text = await run(["--dump-json", "--flat-playlist",
                      f"ytsearch{max(1, min(limit, 50))}:{query}"], timeout=40)
    out = []
    for entry in _ndjson(text):
        track = _track(entry)
        if track:
            out.append(track)
    return out[:limit]


# Аудио без видеодорожки и без HLS: браузер играет такой поток напрямую.
_FORMAT = ("bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio[acodec!=none][vcodec=none]"
           "/bestaudio/best")


# YouTube по-разному отдаёт поток разным клиентам плеера, и «Sign in to confirm
# you are not a bot» приходит далеко не всем. Перебираем наборы по очереди —
# это тот же приём, что был в providers, но теперь на свежем бинарнике.
_CLIENT_SETS = (
    (),
    ("--extractor-args", "youtube:player_client=tv_simply,web_safari"),
    ("--extractor-args", "youtube:player_client=android_vr,mweb"),
    ("--extractor-args", "youtube:player_client=ios,web_embedded"),
    # Набор для залогиненной сессии: с cookies именно web/tv отдают поток,
    # когда остальные клиенты упираются в бот-проверку.
    ("--extractor-args", "youtube:player_client=web,tv"),
)
# Сколько ждём молчащий набор, прежде чем подключить следующий параллельно.
# Смысл в двух вещах сразу: когда клиент работает (это большинство треков),
# второго процесса yt-dlp не появляется вообще; когда клиент упёрся в
# бот-проверку и висит, ждать его полный таймаут уже не нужно.
_STAGGER = 2.5
_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi", "chromium")

BOT_HINT = ("YouTube asks to confirm you are not a bot from this network. "
            "Open Settings → Libraries → YouTube and paste your YouTube cookies "
            "(or pick the browser you are signed in with) — after that the "
            "player asks YouTube as a signed-in listener and the wall goes away.")


def _is_bot_wall(message: str) -> bool:
    low = message.lower()
    return "not a bot" in low or "sign in to confirm" in low


def _may_need_cookies(message: str) -> bool:
    """Old yt-dlp often reports the bot wall as a false Video unavailable."""
    low = message.lower()
    return _is_bot_wall(message) or any(hint in low for hint in (
        "video unavailable", "login required", "authentication required",
        "confirm your age", "members-only",
    ))


async def _first_success(base: list[str], order, url: str, *, validate=None
                         ) -> tuple[str, Exception | None, bool]:
    """Перебирает наборы клиентов и возвращает первый удачный ответ.

    Наборы идут по порядку, но следующий не ждёт, пока предыдущий доживёт до
    своего таймаута: упавший освобождает очередь сразу, а молчащий через
    _STAGGER секунд получает себе конкурента и дальше они работают вместе.
    """
    all_tasks = set()
    def launch(extra) -> asyncio.Task:
        task = asyncio.create_task(run(base + list(extra) + [url], timeout=30))
        all_tasks.add(task)
        return task

    queue = list(order)
    running: set[asyncio.Task] = set()
    text = ""
    last: Exception | None = None
    bot_wall = False
    try:
        while queue or running:
            if queue and not running:
                running.add(launch(queue.pop(0)))
            done, running = await asyncio.wait(
                running, timeout=_STAGGER, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    got = task.result()
                    if got and got.strip() and validate:
                        validate(got)
                except asyncio.CancelledError:
                    continue
                except Exception as exc:
                    last = exc
                    bot_wall = bot_wall or _may_need_cookies(str(exc))
                    continue
                if got and got.strip():
                    text = got
                    break
            if text:
                break
            if queue and len(running) < 2:
                # Bound alternate clients; advance immediately after failures.
                running.add(launch(queue.pop(0)))
    finally:
        for task in running:
            if not task.done():
                task.cancel()
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
    return text, last, bot_wall


# «Голый» запуск yt-dlp: без cookies, без особых клиентов,
# только формат «лучший звук». Для большинства сетей этого достаточно, а
# cookies, наоборот, часто мешают: YouTube отзывает сессию, выгруженную из
# открытой вкладки, и отвечает «The page needs to be reloaded» или «Requested
# format is not available». Поэтому сначала идём этим путём, и только если
# он упёрся в бот-проверку — переходим к cookies и наборам клиентов.
_PLAIN_FORMAT = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio"
_plain_skip_until = 0.0


async def run_plain(args: list[str], timeout: float = 35.0) -> str:
    program = path()
    if not program:
        raise RuntimeError("yt-dlp binary is not installed yet")
    kwargs: dict[str, Any] = {"stdout": asyncio.subprocess.PIPE,
                              "stderr": asyncio.subprocess.PIPE}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000
    proc = await asyncio.create_subprocess_exec(
        program, "--no-warnings", "--no-progress", "--no-color", "--ignore-config",
        *netproxy.ytdlp_args(), *args, **kwargs)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        if proc.returncode is None:
            try: proc.kill()
            except ProcessLookupError: pass
        await proc.communicate()
        if isinstance(exc, asyncio.CancelledError): raise
        raise RuntimeError("yt-dlp timed out") from exc
    if proc.returncode != 0:
        message = (err or b"").decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(message[-1] if message else f"yt-dlp exit {proc.returncode}")
    return (out or b"").decode("utf-8", "replace")


def _stream_result(data: dict) -> dict:
    picked = _pick_format(data)
    if not picked or not picked.get("url"):
        raise RuntimeError("yt-dlp returned no audio link")

    ext = str(picked.get("ext") or data.get("ext") or "").lower()
    mime = {"m4a": "audio/mp4", "mp4": "audio/mp4", "mp3": "audio/mpeg",
            "webm": "audio/webm", "opus": "audio/ogg", "ogg": "audio/ogg",
            "aac": "audio/aac"}.get(ext, "audio/mp4")
    size = picked.get("filesize") or picked.get("filesize_approx")
    return {
        "url": picked["url"],
        "headers": dict(picked.get("http_headers") or data.get("http_headers") or {}),
        "size": int(size) if size else None,
        "mime": mime,
        "bitrate": int(picked["abr"]) if picked.get("abr") else None,
        "codec": picked.get("acodec"),
        "duration": int(data["duration"]) if data.get("duration") else None,
        "title": data.get("track") or data.get("title"),
        "artist": _artist(data),
        "album": data.get("album"),
    }


_PLAIN_HEDGE_SECONDS = 1.75

async def _fast_audio_link(base, order, url, *, plain=True):
    """Healthy plain lookup stays single; hedge only slow lookups, reap all losers."""
    last, bot_wall = None, False
    running, all_tasks = set(), set()
    async def plain_link():
        global _plain_skip_until
        try:
            text = await run_plain(base + [url])
            _stream_result(json.loads(text.strip().splitlines()[-1]))
            return text, None, False
        except asyncio.CancelledError: raise
        except Exception as exc:
            wall = _may_need_cookies(str(exc))
            if wall: _plain_skip_until = time.monotonic() + 600
            return "", exc, wall
    try:
        if plain:
            task = asyncio.create_task(plain_link());running.add(task);all_tasks.add(task)
            done, _ = await asyncio.wait(running, timeout=_PLAIN_HEDGE_SECONDS)
            if done:
                running.remove(task)
                text, last, bot_wall = task.result()
                if text: return text, last, bot_wall
        task = asyncio.create_task(_first_success(base, order, url,
            validate=lambda text: _stream_result(json.loads(text.strip().splitlines()[-1]))))
        running.add(task);all_tasks.add(task)
        while running:
            done, running = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    text, error, wall = task.result();bot_wall = bot_wall or wall
                    if error: last = error
                    if text:
                        _stream_result(json.loads(text.strip().splitlines()[-1]))
                        return text, last, bot_wall
                except Exception as exc: last = exc
    finally:
        for task in all_tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)
    return "", last, bot_wall


async def stream(video_id_or_url: str, attempt: int = 0) -> dict:
    """Свежая прямая ссылка на аудио.

    `attempt` сдвигает порядок клиентов плеера. Это нужно, когда ссылка уже
    была получена, но CDN ответил на неё 403: повторять тот же клиент
    бессмысленно, ответ будет ровно таким же.
    """
    if not ready():
        raise RuntimeError("yt-dlp binary is not installed yet")
    url = video_id_or_url
    if not str(url).startswith("http"):
        url = f"https://www.youtube.com/watch?v={video_id_or_url}"

    from .audio_quality import format_selector
    global _plain_skip_until
    if attempt > 0: _plain_skip_until = time.monotonic() + 300
    base = ["-f", format_selector(), "--dump-single-json", "--no-playlist"]
    count = len(_CLIENT_SETS)
    order = [_CLIENT_SETS[(attempt + i) % count] for i in range(count)]
    text, last, bot_wall = await _fast_audio_link(base, order, url,
        plain=attempt == 0 and time.monotonic() >= _plain_skip_until)

    # Cookies браузера пробуем только против бот-проверки: это единственное,
    # что она принимает, а лишние попытки затянули бы старт трека.
    # На телефоне никаких браузеров с cookies нет, и каждый такой запуск —
    # это впустую потраченные секунды перед сообщением об ошибке.
    if (not text.strip() and bot_wall and not _cookie_args()
            and not os.getenv("KRYONYX_ANDROID")):
        for browser in _BROWSERS:
            try:
                text = await run(base + ["--cookies-from-browser", browser, url],
                                 timeout=30)
                if text.strip():
                    log.info("[yt-dlp] cookies from %s helped", browser)
                    break
            except Exception as exc:
                last = exc
                continue

    if not text.strip():
        message = str(last or "yt-dlp returned no data")
        # YouTube отказал всем клиентам — возможно, сборка устарела.
        nudge_update("stream failed")
        raise RuntimeError(BOT_HINT if bot_wall or _is_bot_wall(message) else message)
    return _stream_result(json.loads(text.strip().splitlines()[-1]))


async def dash_plain(video_id_or_url: str, quality: int = 1080) -> dict:
    """Раздельные дорожки тем же «голым» запуском (без cookies)."""
    from . import ytlibs
    if not ready():
        raise RuntimeError("yt-dlp binary is not installed yet")
    url = str(video_id_or_url or "")
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={url}"
    text = await run_plain(["-f", "all", "--dump-single-json", "--no-playlist", url], 40)
    return ytlibs.dash_from_formats(json.loads(text.strip().splitlines()[-1]),
                                    max(144, min(int(quality or 1080), 4320)))


async def video(video_id_or_url: str, quality: int = 720, attempt: int = 0) -> dict:
    """Прямая совмещённая видео+аудио дорожка для встроенного клипа.

    Раздельные DASH-дорожки здесь намеренно не берём: обычный HTML5 video
    умеет надёжно перематывать один progressive-файл без MSE и ffmpeg.
    Поэтому 1080p мягко откатывается к лучшему доступному совмещённому
    формату (у YouTube это чаще всего 720p).
    """
    if not ready():
        raise RuntimeError("yt-dlp binary is not installed yet")
    url = str(video_id_or_url or "")
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={url}"
    ceiling = max(144, min(int(quality or 720), 2160))
    fmt = (
        f"best[ext=mp4][vcodec^=avc1][height<={ceiling}][acodec!=none]"
        f"/best[ext=mp4][height<={ceiling}][vcodec!=none][acodec!=none]"
        f"/best[height<={ceiling}][vcodec!=none][acodec!=none]"
        f"/best[height<={ceiling}]/best"
    )
    base = ["-f", fmt, "--dump-single-json", "--no-playlist"]
    count = len(_CLIENT_SETS)
    order = [_CLIENT_SETS[(attempt + i) % count] for i in range(count)]
    text, last, bot_wall = await _first_success(base, order, url)
    if not text.strip() and bot_wall and not _cookie_args() \
            and not os.getenv("KRYONYX_ANDROID"):
        for browser in _BROWSERS:
            try:
                text = await run(base + ["--cookies-from-browser", browser, url],
                                 timeout=35)
                if text.strip():
                    break
            except Exception as exc:
                last = exc
    if not text.strip():
        message = str(last or "yt-dlp returned no clip")
        nudge_update("video failed")
        raise RuntimeError(BOT_HINT if bot_wall or _is_bot_wall(message) else message)
    data = json.loads(text.strip().splitlines()[-1])
    picked = data
    if not picked.get("url"):
        combined = [
            f for f in (data.get("requested_formats") or data.get("formats") or [])
            if isinstance(f, dict) and f.get("url")
            and f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
            and not str(f.get("protocol") or "").startswith(("m3u8", "http_dash"))
        ]
        combined.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
        # Сначала то, что влезает в запрошенное качество; если совмещённых
        # дорожек такого размера нет вовсе — берём любую совмещённую, пусть
        # и меньше. Клип, который играет в 360p, лучше пустого экрана.
        fits = [f for f in combined if (f.get("height") or 0) <= ceiling]
        picked = (fits or combined)[-1] if combined else {}
    if not picked.get("url"):
        raise RuntimeError("yt-dlp returned no playable video link")
    ext = str(picked.get("ext") or data.get("ext") or "mp4").lower()
    mime = {"webm": "video/webm", "mkv": "video/x-matroska"}.get(ext, "video/mp4")
    return {
        "url": picked["url"],
        "headers": dict(picked.get("http_headers") or data.get("http_headers") or {}),
        "mime": mime,
        "height": int(picked.get("height") or data.get("height") or 0),
        "width": int(picked.get("width") or data.get("width") or 0),
        "duration": int(data["duration"]) if data.get("duration") else None,
        "title": data.get("track") or data.get("title"),
    }


async def dash(video_id_or_url: str, quality: int = 1080, attempt: int = 0) -> dict:
    """Раздельные дорожки (видео и звук) выбранной высоты через бинарник."""
    from . import ytlibs
    if not ready():
        raise RuntimeError("yt-dlp binary is not installed yet")
    url = str(video_id_or_url or "")
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={url}"
    base = ["-f", "all", "--dump-single-json", "--no-playlist"]
    count = len(_CLIENT_SETS)
    order = [_CLIENT_SETS[(attempt + i) % count] for i in range(count)]
    text, last, bot_wall = await _first_success(base, order, url)
    if not text.strip():
        message = str(last or "yt-dlp returned nothing")
        raise RuntimeError(BOT_HINT if bot_wall or _is_bot_wall(message) else message)
    return ytlibs.dash_from_formats(json.loads(text.strip().splitlines()[-1]),
                                    max(144, min(int(quality or 1080), 4320)))


async def download_video(video_id_or_url: str, quality: int = 1080) -> dict:
    """Скачивает и объединяет DASH-видео и звук в совместимый MP4."""
    if not ready():
        raise RuntimeError("yt-dlp binary is not installed yet")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for HD music videos")
    url = str(video_id_or_url or "")
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={url}"
    ceiling = max(144, min(int(quality or 1080), 2160))
    cache = os.path.join(data_dir(), "video-cache")
    os.makedirs(cache, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", video_id_or_url)[-80:]
    target = os.path.join(cache, f"{safe_id}-{ceiling}.mp4")
    if os.path.isfile(target) and os.path.getsize(target) > 1024 * 1024:
        return {"file": target, "height": ceiling, "mime": "video/mp4"}
    part = target + ".part.mp4"
    _safe_remove(part)
    fmt = (
        f"bestvideo[ext=mp4][vcodec^=avc1][height<={ceiling}]"
        f"+bestaudio[ext=m4a]/bestvideo[ext=mp4][height<={ceiling}]"
        f"+bestaudio/best[height<={ceiling}]"
    )
    await run([
        "-f", fmt, "--no-playlist", "--merge-output-format", "mp4",
        "--force-overwrites", "--no-progress", "-o", part, url,
    ], timeout=900)
    if not os.path.isfile(part) or os.path.getsize(part) < 1024 * 1024:
        _safe_remove(part)
        raise RuntimeError("The HD video download was incomplete")
    os.replace(part, target)
    return {"file": target, "height": ceiling, "mime": "video/mp4"}


def _pick_format(data: dict) -> dict | None:
    """Лучшее аудио по HTTP: без видео, без m3u8/DASH-манифеста."""
    candidates = []
    for fmt in (data.get("requested_formats") or data.get("formats") or []):
        if not isinstance(fmt, dict) or not fmt.get("url"):
            continue
        if fmt.get("acodec") in (None, "none"):
            continue
        if fmt.get("vcodec") not in (None, "none"):
            continue
        proto = str(fmt.get("protocol") or "")
        if "m3u8" in proto or "dash" in proto or "m3u8" in str(fmt["url"]):
            continue
        if not proto.startswith("http"):
            continue
        candidates.append(fmt)
    if candidates:
        from .audio_quality import pick
        return pick(candidates,lambda f: (f.get("abr") or f.get("tbr") or 0)*1000)
    if data.get("url") and "m3u8" not in str(data["url"]):
        return data
    return None


async def playlist(url: str, limit: int = 100) -> list[dict]:
    if not ready():
        return []
    text = await run(["--dump-json", "--flat-playlist",
                      "--playlist-end", str(max(1, min(limit, 400))), url], timeout=90)
    out = []
    for entry in _ndjson(text):
        track = _track(entry)
        if track:
            out.append(track)
    return out[:limit]


async def version() -> str:
    try:
        return (await run(["--version"], timeout=15)).strip()
    except Exception:
        return ""


def status() -> dict:
    stamp = _read_stamp()
    return {
        "ready": ready(),
        "path": path(),
        "tag": stamp.get("tag"),
        "error": _last_error,
        "asset": _asset_name(),
        "folder": folder(),
        "stage": _auto["stage"],
        "auto": _auto["auto"],
        "busy": _auto["busy"],
        "checked_at": int(_auto["checked_at"] or stamp.get("checked_at") or 0),
        "next_check": int(_auto["next_check"] or 0),
        "updated_at": int(_auto["updated_at"] or 0),
        "attempts": _auto["attempts"],
        "rolled_back": _auto["rolled_back"],
        "has_backup": os.path.isfile(_backup_path()),
        "interval": int(UPDATE_INTERVAL),
    }
