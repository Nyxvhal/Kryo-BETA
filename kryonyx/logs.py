"""
logs.py — журнал приложения, который видно прямо в настройках.

Последние записи держим в памяти кольцевым буфером, интерфейс
забирает их по HTTP и показывает с фильтром по уровню. Файл журнала при этом
пишется как и раньше — здесь только «живая» лента.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime

MAX_RECORDS = 1000

_buffer: deque[dict] = deque(maxlen=MAX_RECORDS)
_lock = threading.Lock()
_counter = 0
_installed = False


class BufferHandler(logging.Handler):
    """Складывает записи в память, ничего не форматируя заранее."""

    def emit(self, record: logging.LogRecord) -> None:
        global _counter
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        if record.exc_info:
            try:
                message += "\n" + self.format(record).split("\n", 1)[-1]
            except Exception:
                pass
        with _lock:
            _counter += 1
            _buffer.append({
                "seq": _counter,
                "time": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                "ts": record.created,
                "level": record.levelname.lower(),
                "logger": record.name,
                "message": message[:2000],
            })


def install(level: int = logging.INFO) -> None:
    global _installed
    if _installed:
        return
    handler = BufferHandler(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    # Без этого корневой логгер остаётся на WARNING и записи уровня INFO
    # вообще не рождаются — экран «Логи» тогда пустой всегда.
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    _installed = True


LEVELS = ("debug", "info", "warning", "error", "critical")


def records(level: str = "", limit: int = 300, after: int = 0,
            query: str = "") -> list[dict]:
    level = (level or "").lower()
    keep = LEVELS[LEVELS.index(level):] if level in LEVELS else LEVELS
    query = query.lower().strip()
    with _lock:
        items = list(_buffer)
    out = [
        item for item in items
        if item["level"] in keep
        and item["seq"] > after
        and (not query or query in item["message"].lower() or query in item["logger"].lower())
    ]
    return out[-limit:]


def counts() -> dict:
    with _lock:
        items = list(_buffer)
    result = {level: 0 for level in LEVELS}
    for item in items:
        result[item["level"]] = result.get(item["level"], 0) + 1
    result["total"] = len(items)
    result["since"] = items[0]["time"] if items else None
    return result


def clear() -> int:
    with _lock:
        size = len(_buffer)
        _buffer.clear()
    logging.getLogger("kryonyx").info("log cleared by the user")
    return size


def text(level: str = "", limit: int = 1000) -> str:
    return "\n".join(
        f"{item['time']} {item['level'].upper():8} {item['logger']}: {item['message']}"
        for item in records(level, limit)
    )
