"""
bootstrap.py — подготовка окружения до запуска плеера.

Задача одна: приложение должно подниматься у любого человека на его же
устройстве, без правки системного Python и без прав администратора.

  * свои библиотеки (`<данные>/lib`) добавляются в sys.path;
  * если обязательной зависимости нет, она ставится в эту же папку
    (`pip install --target`), а не в систему;
  * ничего не делаем молча: каждый шаг виден в выводе и в журнале.

Автоустановку можно выключить переменной KRYONYX_AUTO_DEPS=0.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys

from .paths import extra_lib_dirs, libs_dir

log = logging.getLogger(__name__)

# Без этого приложение не поднимется вообще.
REQUIRED: tuple[tuple[str, str], ...] = (
    ("aiohttp", "aiohttp>=3.9,<4"),
)

# Без этого оно поднимется, но часть возможностей отключится.
# Пояснения — английские ключи словаря интерфейса: они видны в «Проверке
# на этом устройстве» и переводятся там на язык интерфейса.
OPTIONAL: tuple[tuple[str, str, str], ...] = (
    ("webview", "pywebview>=5.1", "own window (without it the interface opens in the browser)"),
    ("yt_dlp", "yt-dlp>=2025.1.15", "backup way to YouTube and SoundCloud links"),
    ("ytmusicapi", "ytmusicapi>=1.10", "search in the YouTube Music catalogue"),
    ("pytubefix", "pytubefix>=8.0", "one more built-in YouTube engine for clips"),
    ("imageio_ffmpeg", "imageio-ffmpeg>=0.5", "joining video and audio for HD clips"),
    ("aiohttp_socks", "aiohttp-socks>=0.9", "SOCKS proxy in the network settings"),
)


def add_lib_paths() -> list[str]:
    """Папки со своими библиотеками (и колёса внутри них) — в начало sys.path."""
    added: list[str] = []
    for base in extra_lib_dirs():
        entries = [base]
        try:
            for name in sorted(os.listdir(base)):
                if name.lower().endswith((".whl", ".zip", ".egg")):
                    entries.append(os.path.join(base, name))
        except OSError:
            pass
        for entry in entries:
            if entry not in sys.path:
                sys.path.insert(0, entry)
                added.append(entry)
    if added:
        importlib.invalidate_caches()
    return added


def have(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def python_for_pip() -> str:
    """Чем звать pip.

    В собранном приложении sys.executable — это сам KryonyxMusic.exe, и
    `sys.executable -m pip` запустил бы второй плеер вместо установки.
    Поэтому во frozen-сборке ищем настоящий Python в системе, а если его нет,
    честно об этом говорим: библиотеку тогда кладут в папку `lib` руками.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable
    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def _pip_install(specs: list[str]) -> tuple[bool, str]:
    """Ставит пакеты в папку своих библиотек. Интернета может и не быть."""
    if not specs:
        return True, ""
    target = libs_dir()
    runner = python_for_pip()
    if not runner:
        return False, ("в системе нет Python, а собранное приложение не умеет "
                       f"ставить пакеты само — распакуйте библиотеку в {target}")
    cmd = [runner, "-m", "pip", "install", "--no-input",
           "--disable-pip-version-check", "--target", target, *specs]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError:
        return False, "в этом Python нет pip"
    except subprocess.TimeoutExpired:
        return False, "установка не уложилась в 10 минут"
    except Exception as exc:                                # pragma: no cover
        return False, str(exc)
    if done.returncode != 0:
        tail = (done.stderr or done.stdout or "").strip().splitlines()
        return False, tail[-1] if tail else f"pip вернул код {done.returncode}"
    add_lib_paths()
    importlib.invalidate_caches()
    return True, target


def install(specs: list[str]) -> tuple[bool, str]:
    """Публичная установка пакетов: ею пользуется и экран «Свои библиотеки»."""
    return _pip_install([s for s in specs if s.strip()])


CORE_MARK = ".kryonyx-core.json"


def _listing(path: str) -> list[str]:
    try:
        return sorted(name for name in os.listdir(path) if not name.startswith("."))
    except OSError:
        return []


def core_libs() -> set[str]:
    """Что в папке библиотек поставило само приложение.

    Эти пакеты не предлагаем удалять: без них плеер не поднимется, а отличить
    их от своих библиотек пользователя иначе нельзя — лежат они рядом.
    """
    try:
        with open(os.path.join(libs_dir(), CORE_MARK), encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(name) for name in data.get("names", [])}
    except (OSError, ValueError):
        return set()


def _mark_core(before: list[str]) -> None:
    names = sorted(set(_listing(libs_dir())) - set(before)) or []
    if not names:
        return
    keep = sorted(core_libs() | {n[:-3] if n.endswith(".py") else n for n in names})
    try:
        with open(os.path.join(libs_dir(), CORE_MARK), "w", encoding="utf-8") as handle:
            json.dump({"names": keep}, handle, ensure_ascii=False)
    except OSError as exc:
        log.debug("[bootstrap] the marker was not written: %s", exc)


def ensure(*, auto: bool | None = None, quiet: bool = False) -> dict:
    """Проверяет зависимости и при необходимости ставит их в свою папку."""
    add_lib_paths()
    if auto is None:
        auto = (os.getenv("KRYONYX_AUTO_DEPS") or "1").strip().lower() not in ("0", "no", "off")

    missing = [spec for module, spec in REQUIRED if not have(module)]
    report: dict = {"installed": [], "missing": [], "optional_missing": [],
                    "lib_dir": libs_dir(), "note": ""}

    if missing and auto:
        if not quiet:
            print(f"[kryonyx] не хватает: {', '.join(missing)} — ставлю в {libs_dir()}")
        snapshot = _listing(libs_dir())
        good, note = _pip_install(missing)
        if good:
            _mark_core(snapshot)
        report["note"] = note
        if good:
            report["installed"] = missing
        missing = [spec for module, spec in REQUIRED if not have(module)]

    report["missing"] = missing
    report["optional_missing"] = [
        {"module": module, "spec": spec, "why": why}
        for module, spec, why in OPTIONAL if not have(module)
    ]
    if missing and not quiet:
        runner = python_for_pip() or sys.executable
        print("[kryonyx] не удалось подготовить зависимости: "
              + ", ".join(missing)
              + (f"\n[kryonyx] {report['note']}" if report["note"] else "")
              + f"\n[kryonyx] поставьте их руками: "
                f"{runner} -m pip install --target \"{libs_dir()}\" "
              + " ".join(missing))
    return report
