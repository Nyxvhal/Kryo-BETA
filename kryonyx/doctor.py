"""
doctor.py — проверка «запустится ли плеер на этом устройстве».

Kryo — локальное приложение: сервер слушает только loopback, база,
кэш и настройки лежат в папке этого пользователя и этого компьютера, чужих
хостов нет. Этот модуль отвечает на простой вопрос: всё ли на месте именно
здесь — и если нет, что человеку сделать.

Отчёт виден в трёх местах: `KryonyxMusic --doctor` в консоли, `/api/doctor`
в интерфейсе и короткая сводка в `/api/health`.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import sqlite3
import sys

from . import APP_NAME, __version__
from .bootstrap import OPTIONAL, REQUIRED, have, python_for_pip
from .paths import (app_dir, cache_dir, data_dir, device_tag, libs_dir,
                    plugins_dir, resource_dir, web_dir)

OK, WARN, FAIL = "ok", "warn", "fail"


def _fill(text: str, args: dict | None) -> str:
    for key, value in (args or {}).items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _check(name: str, state: str, note: str, fix: str = "", *,
           note_args: dict | None = None, fix_args: dict | None = None) -> dict:
    """Одна строка проверки.

    Тексты — английские ключи словаря интерфейса (web/js/i18n.js); данные
    (пути, версии, порты) подставляются в шаблон отдельно, через *_args.
    Раньше строки были русскими, и «Проверку на этом устройстве» на любом
    другом языке показывали по-русски.
    """
    out = {"name": name, "state": state, "note": _fill(note, note_args),
           "fix": _fill(fix, fix_args)}
    if note_args:
        out["note_key"], out["note_args"] = note, note_args
    if fix_args:
        out["fix_key"], out["fix_args"] = fix, fix_args
    return out


def _writable(path: str) -> bool:
    probe = os.path.join(path, ".doctor-test")
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _free_port(host: str = "127.0.0.1", port: int = 8765) -> tuple[bool, int]:
    """Есть ли свободный порт в том же диапазоне, что берёт сервер."""
    for candidate in range(port, port + 12):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, candidate))
                return True, candidate
            except OSError:
                continue
    return False, 0


def checks() -> list[dict]:
    out: list[dict] = []

    version = sys.version_info
    out.append(_check(
        "Python", OK if version >= (3, 10) else FAIL,
        f"{platform.python_version()} ({sys.executable})",
        "" if version >= (3, 10) else "Python 3.10 or newer is needed"))

    folder = data_dir()
    out.append(_check(
        "Data folder", OK if _writable(folder) else FAIL, folder,
        "" if _writable(folder) else
        "the folder is not writable — set your own in KRYONYX_DATA_DIR"))

    out.append(_check("This device", OK, "{host} · tag {tag}", "",
                      note_args={"host": platform.node() or "?", "tag": device_tag()}))

    try:
        connection = sqlite3.connect(os.path.join(folder, "doctor.db"))
        connection.execute("create table if not exists t(x)")
        connection.close()
        os.remove(os.path.join(folder, "doctor.db"))
        out.append(_check("SQLite database", OK, "created and writable", ""))
    except Exception as exc:
        out.append(_check("SQLite database", FAIL, str(exc)[:160],
                          "the disk is write-protected or busy with another program"))

    out.append(_check("Cache", OK if _writable(cache_dir()) else WARN, cache_dir(),
                      "" if _writable(cache_dir()) else
                      "the cache turns off, audio is fetched again every time"))

    index = os.path.join(web_dir(), "index.html")
    out.append(_check(
        "Interface", OK if os.path.isfile(index) else FAIL,
        web_dir(),
        "" if os.path.isfile(index) else
        "interface files are missing — unpack the whole archive"))

    free, port = _free_port()
    out.append(_check(
        "Local port", OK if free else FAIL,
        f"127.0.0.1:{port}" if free else "8765–8776 are all busy",
        "" if free else "close extra copies of the player or set --port"))

    missing = [spec for module, spec in REQUIRED if not have(module)]
    out.append(_check(
        "Required libraries", OK if not missing else FAIL,
        "in place" if not missing else ", ".join(missing),
        "" if not missing else
        f'{python_for_pip() or sys.executable} -m pip install --target '
        f'"{libs_dir()}" ' + " ".join(missing)))

    absent = [(module, spec, why) for module, spec, why in OPTIONAL if not have(module)]
    out.append(_check(
        "Optional libraries", OK if not absent else WARN,
        "in place" if not absent else
        "; ".join(f"{spec} — {why}" for _, spec, why in absent),
        "" if not absent else
        f'{python_for_pip() or sys.executable} -m pip install --target '
        f'"{libs_dir()}" ' + " ".join(spec for _, spec, _ in absent)))

    binary = os.path.join(data_dir(), "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    near = os.path.join(app_dir(), "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
    found = next((p for p in (binary, near) if os.path.isfile(p)), "") or shutil.which("yt-dlp")
    out.append(_check(
        "yt-dlp", OK if found else WARN, found or "missing — it downloads itself on the first start",
        "" if found else "needs the internet once; without it Audius, "
                         "Internet Archive, Jamendo and radio still work"))

    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    out.append(_check("ffmpeg", OK if ffmpeg else WARN,
                      ffmpeg or "missing",
                      "" if ffmpeg else
                      "only needed to save a track to a file: put ffmpeg next to the program ({path})",
                      fix_args=None if ffmpeg else {"path": app_dir()}))

    out.append(_check("Your plugins", OK if _writable(plugins_dir()) else WARN,
                      plugins_dir(),
                      "" if _writable(plugins_dir()) else
                      "the folder is not writable — your plugins will not load"))
    out.append(_check("Your libraries", OK if _writable(libs_dir()) else WARN,
                      libs_dir(),
                      "" if _writable(libs_dir()) else
                      "the folder is not writable — pip cannot install there"))

    try:
        import webview  # noqa: F401
        window = "own window (pywebview)"
    except Exception:
        window = "no window — the interface opens in the browser (--browser)"
    out.append(_check("App window", OK, window, ""))

    return out


def report() -> dict:
    items = checks()
    worst = FAIL if any(i["state"] == FAIL for i in items) else (
        WARN if any(i["state"] == WARN for i in items) else OK)
    return {
        "app": APP_NAME, "version": __version__,
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "state": worst,
        "local_only": True,
        "device": device_tag(),
        "paths": {"data": data_dir(), "cache": cache_dir(), "app": app_dir(),
                  "resources": resource_dir(), "plugins": plugins_dir(),
                  "libs": libs_dir()},
        "checks": items,
    }


def summary() -> dict:
    """Короткая сводка для /api/health."""
    items = checks()
    return {
        "state": (FAIL if any(i["state"] == FAIL for i in items)
                  else WARN if any(i["state"] == WARN for i in items) else OK),
        "device": device_tag(),
        "data_dir": data_dir(),
        "local_only": True,
        "problems": [{"name": i["name"], "note": i["note"], "fix": i["fix"]}
                     for i in items if i["state"] != OK],
    }


def text() -> str:
    data = report()
    mark = {OK: "+", WARN: "!", FAIL: "x"}
    # Пункты проверки написаны по-английски (их же переводит интерфейс),
    # поэтому и шапка с итогом в консоли — на том же языке, без смеси.
    lines = [f"{data['app']} {data['version']} — local player",
             f"system: {data['platform']}",
             f"device: {data['device']}",
             f"data: {data['paths']['data']}",
             f"plugins: {data['paths']['plugins']}",
             f"libraries: {data['paths']['libs']}",
             ""]
    for item in data["checks"]:
        lines.append(f" [{mark[item['state']]}] {item['name']}: {item['note']}")
        if item["fix"]:
            lines.append(f"      → {item['fix']}")
    lines.append("")
    lines.append({OK: "Ready: the player will start on this device.",
                  WARN: "It will start, but some features stay off (see “!”).",
                  FAIL: "Something blocks the start: fix the “x” lines first."}[data["state"]])
    return "\n".join(lines)
