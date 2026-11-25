"""
storage.py — локальная база (SQLite) рядом с профилем пользователя.

Хранит плейлисты, лайки, историю прослушиваний, «вкус» (веса авторов),
историю поиска и настройки. PostgreSQL и Telegram-аккаунты больше не нужны:
приложение полностью локальное и работает сразу после установки.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Iterable

from .paths import all_data_dirs, data_dir

log = logging.getLogger(__name__)

_local = threading.local()
_db_path: str | None = None

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS playlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at REAL NOT NULL,
    cover      TEXT
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id    TEXT NOT NULL,
    payload     TEXT NOT NULL,
    position    REAL NOT NULL,
    added_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pt_playlist ON playlist_tracks(playlist_id, position);

CREATE TABLE IF NOT EXISTS likes (
    track_id TEXT PRIMARY KEY,
    payload  TEXT NOT NULL,
    liked_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id  TEXT NOT NULL,
    payload   TEXT NOT NULL,
    played_at REAL NOT NULL,
    seconds   REAL NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    skipped   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_history_time ON history(played_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_track ON history(track_id);

CREATE TABLE IF NOT EXISTS artist_taste (
    artist     TEXT PRIMARY KEY,
    weight     REAL NOT NULL DEFAULT 0,
    plays      INTEGER NOT NULL DEFAULT 0,
    skips      INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS search_history (
    query    TEXT PRIMARY KEY,
    hits     INTEGER NOT NULL DEFAULT 1,
    last_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL DEFAULT 0
);

-- Состояние приложения: очередь, текущий трек и позиция, размер окна и любые
-- другие «мелочи», которые должны пережить перезапуск и чистку WebView.
CREATE TABLE IF NOT EXISTS app_state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

# Колонки, добавленные после первых версий базы: старые файлы обновляем на месте.
MIGRATIONS = (
    ("settings", "updated_at", "REAL NOT NULL DEFAULT 0"),
    ("history", "session_id", "TEXT"),
)


def _migrate(conn: sqlite3.Connection) -> None:
    """Догоняем схему в базах, созданных прошлыми версиями приложения."""
    for table, column, decl in MIGRATIONS:
        names = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if names and column not in names:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            log.info("[db] %s.%s added", table, column)


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(_db_path or db_path(), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def db_path() -> str:
    global _db_path
    if _db_path is None:
        _db_path = os.path.join(data_dir(), "kryonyx.db")
    return _db_path


def _rescue(path: str) -> None:
    """Переносим базу из прежнего места, если в текущем её ещё нет.

    Плейлисты, лайки и настройки лежат в одном файле, поэтому переезд папки
    данных (или временная папка в прошлом запуске) не должен стоить
    пользователю библиотеки.
    """
    if os.path.exists(path):
        return
    target = os.path.dirname(path)
    for folder in all_data_dirs():
        if os.path.abspath(folder) == os.path.abspath(target):
            continue
        old = os.path.join(folder, "kryonyx.db")
        if not os.path.isfile(old) or os.path.getsize(old) < 1024:
            continue
        try:
            os.makedirs(target, exist_ok=True)
            source = sqlite3.connect(old)
            copy = sqlite3.connect(path)
            with copy:
                source.backup(copy)      # переносит и незакрытый WAL
            source.close()
            copy.close()
            log.info("[db] rescued from %s", old)
            return
        except (OSError, sqlite3.Error) as exc:
            log.warning("[db] could not rescue %s: %s", old, exc)


def init(path: str | None = None) -> str:
    global _db_path
    _db_path = path or db_path()
    _rescue(_db_path)
    conn = _conn()
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    _activity_cache.clear()
    if not list_playlists():
        create_playlist("Мне нравится")
    log.info("[db] %s", _db_path)
    return _db_path


# --------------------------------------------------------------------------- #
# вспомогательное
# --------------------------------------------------------------------------- #
_TRACK_FIELDS = ("id", "title", "artist", "duration", "thumbnail", "source", "url",
                 "author_url", "author_id", "author_thumbnail", "artists", "album", "views", "play_count", "stats_kind")


def clean_track(track: dict) -> dict:
    out = {k: track.get(k) for k in _TRACK_FIELDS}
    out["id"] = str(out["id"] or "")[:512]
    out["title"] = str(out["title"] or "Без названия")[:300]
    out["artist"] = str(out["artist"] or "Неизвестный")[:200]
    if out["duration"] is not None:
        try:
            out["duration"] = int(out["duration"])
        except (TypeError, ValueError):
            out["duration"] = None
    for key in ("thumbnail", "url", "author_url"):
        if out[key]:
            out[key] = str(out[key])[:1024]
    return out


def _load(row: sqlite3.Row, extra: dict | None = None) -> dict:
    track = json.loads(row["payload"])
    if extra:
        track.update(extra)
    return track


# --------------------------------------------------------------------------- #
# плейлисты
# --------------------------------------------------------------------------- #
def list_playlists() -> list[dict]:
    rows = _conn().execute(
        """
        SELECT p.id, p.name, p.created_at, p.cover,
               (SELECT COUNT(*) FROM playlist_tracks t WHERE t.playlist_id = p.id) AS count,
               (SELECT payload FROM playlist_tracks t WHERE t.playlist_id = p.id
                 ORDER BY t.position LIMIT 1) AS first_track
        FROM playlists p ORDER BY p.created_at
        """
    ).fetchall()
    out = []
    for row in rows:
        cover = row["cover"]
        if not cover and row["first_track"]:
            cover = (json.loads(row["first_track"]) or {}).get("thumbnail")
        out.append({"id": row["id"], "name": row["name"], "count": row["count"], "cover": cover})
    return out


def create_playlist(name: str, tracks: list[dict] | None = None) -> dict:
    """Create a complete collection atomically; never silently truncate tracks."""
    name = (name or "New playlist").strip()[:80]
    conn = _conn()
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT INTO playlists(name, created_at) VALUES(?, ?)",
            (name, time.time()),
        )
        pid = cur.lastrowid
        items, seen = [], set()
        for raw in tracks or []:
            track = clean_track(raw)
            if not track["id"] or track["id"] in seen:
                continue
            seen.add(track["id"])
            items.append((pid, track["id"], json.dumps(track, ensure_ascii=False),
                          len(items) + 1, time.time()))
        conn.executemany(
            "INSERT INTO playlist_tracks(playlist_id, track_id, payload, position, added_at)"
            " VALUES(?, ?, ?, ?, ?)", items,
        )
    return {"id": pid, "name": name, "count": len(items), "cover": None}


def rename_playlist(playlist_id: int, name: str) -> bool:
    conn = _conn()
    cur = conn.execute(
        "UPDATE playlists SET name = ? WHERE id = ?", ((name or "").strip()[:80], playlist_id)
    )
    conn.commit()
    return cur.rowcount > 0


def delete_playlist(playlist_id: int) -> bool:
    conn = _conn()
    conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
    cur = conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    conn.commit()
    return cur.rowcount > 0


def playlist_tracks(playlist_id: int) -> list[dict] | None:
    conn = _conn()
    if not conn.execute("SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)).fetchone():
        return None
    rows = conn.execute(
        "SELECT id, payload FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
        (playlist_id,),
    ).fetchall()
    return [_load(row, {"row_id": row["id"]}) for row in rows]


def add_many_to_playlist(playlist_id: int, tracks: list[dict]) -> int | None:
    """Batch addition under one write lock: preserve order and prevent repeats."""
    conn = _conn()
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM playlists WHERE id = ?", (playlist_id,)).fetchone():
            return None
        seen = {row[0] for row in conn.execute(
            "SELECT track_id FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))}
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()[0]
        items = []
        for raw in tracks:
            track = clean_track(raw)
            if not track["id"] or track["id"] in seen:
                continue
            seen.add(track["id"])
            pos += 1
            items.append((playlist_id, track["id"], json.dumps(track, ensure_ascii=False),
                          pos, time.time()))
        conn.executemany(
            "INSERT INTO playlist_tracks(playlist_id, track_id, payload, position, added_at)"
            " VALUES(?, ?, ?, ?, ?)", items,
        )
    return len(items)


def add_to_playlist(playlist_id: int, track: dict) -> bool:
    return add_many_to_playlist(playlist_id, [track]) is not None


def remove_from_playlist(playlist_id: int, row_id: int) -> bool:
    conn = _conn()
    cur = conn.execute(
        "DELETE FROM playlist_tracks WHERE playlist_id = ? AND id = ?", (playlist_id, row_id)
    )
    conn.commit()
    return cur.rowcount > 0


def reorder_playlist(playlist_id: int, row_ids: Iterable[int]) -> bool:
    conn = _conn()
    for index, row_id in enumerate(row_ids):
        conn.execute(
            "UPDATE playlist_tracks SET position = ? WHERE playlist_id = ? AND id = ?",
            (index, playlist_id, row_id),
        )
    conn.commit()
    return True


# --------------------------------------------------------------------------- #
# лайки
# --------------------------------------------------------------------------- #
def list_likes(limit: int = 500) -> list[dict]:
    rows = _conn().execute(
        "SELECT payload FROM likes ORDER BY liked_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_load(row) for row in rows]


def liked_ids() -> list[str]:
    return [row["track_id"] for row in _conn().execute("SELECT track_id FROM likes").fetchall()]


def toggle_like(track: dict) -> bool:
    """Возвращает новое состояние: True — трек в любимых."""
    track = clean_track(track)
    conn = _conn()
    exists = conn.execute("SELECT 1 FROM likes WHERE track_id = ?", (track["id"],)).fetchone()
    if exists:
        conn.execute("DELETE FROM likes WHERE track_id = ?", (track["id"],))
        conn.commit()
        _bump_taste(track["artist"], -1.5)
        return False
    conn.execute(
        "INSERT OR REPLACE INTO likes(track_id, payload, liked_at) VALUES(?, ?, ?)",
        (track["id"], json.dumps(track, ensure_ascii=False), time.time()),
    )
    conn.commit()
    _bump_taste(track["artist"], 4.0)
    return True


# --------------------------------------------------------------------------- #
# история и вкус
# --------------------------------------------------------------------------- #
def log_play(track: dict, seconds: float = 0.0, completed: bool = False,
             skipped: bool = False, session_id: str | None = None) -> None:
    track = clean_track(track)
    conn = _conn()
    conn.execute(
        "INSERT INTO history(track_id, payload, played_at, seconds, completed, skipped, session_id)"
        " VALUES(?, ?, ?, ?, ?, ?, ?)",
        (track["id"], json.dumps(track, ensure_ascii=False), time.time(),
         float(seconds or 0), int(bool(completed)), int(bool(skipped)),
         str(session_id)[:100] if session_id else None),
    )
    conn.commit()

    try:
        duration = float(track.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    seconds = max(0.0, float(seconds or 0))
    # Без длительности долю прослушанного не узнать: раньше такой пропуск
    # всегда считался «быстрым», даже после трёх минут музыки.
    if duration > 0:
        ratio = seconds / duration
        fast_skip = skipped and ratio < 0.2 and seconds < 90
    else:
        ratio = 0.0
        fast_skip = skipped and seconds < 30
    if fast_skip:
        _bump_taste(track["artist"], -1.0, skip=True)
    elif completed or ratio > 0.6:
        _bump_taste(track["artist"], 2.0, play=True)
    elif seconds > 30:
        _bump_taste(track["artist"], 0.7, play=True)
    _activity_cache.clear()


def _bump_taste(artist: str, delta: float, play: bool = False, skip: bool = False) -> None:
    artist = (artist or "").strip()
    if not artist or artist.lower() in ("неизвестный", "unknown"):
        return
    conn = _conn()
    row = conn.execute("SELECT weight, updated_at FROM artist_taste WHERE artist = ?", (artist,)).fetchone()
    now = time.time()
    # Вкус «стареет»: сохраняется вес на момент updated_at, поэтому перед
    # добавлением нового сигнала старый вес приводим к текущему моменту.
    weight = (_decayed(row["weight"], row["updated_at"], now) if row else 0.0) + delta
    conn.execute(
        """
        INSERT INTO artist_taste(artist, weight, plays, skips, updated_at)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(artist) DO UPDATE SET
            weight = ?,
            plays = plays + ?,
            skips = skips + ?,
            updated_at = ?
        """,
        (artist, weight, int(play), int(skip), now,
         weight, int(play), int(skip), now),
    )
    conn.commit()


def history(limit: int = 100) -> list[dict]:
    rows = _conn().execute(
        """
        SELECT payload, MAX(played_at) AS played_at FROM history
        GROUP BY track_id ORDER BY played_at DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_load(row, {"played_at": row["played_at"]}) for row in rows]


def listen_counts(ids: list[str]) -> dict[str, int]:
    """One local listen per playback session: >=30s in total or completed.

    Legacy reports have no session id; each qualified row is counted separately.
    Counts are based on local history and disappear when history is cleared.
    """
    ids = list(dict.fromkeys(str(i)[:512] for i in ids if i))[:500]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    rows = _conn().execute(f"""
        SELECT track_id, COUNT(*) AS listens FROM (
            SELECT track_id FROM history WHERE track_id IN ({marks})
            GROUP BY track_id, COALESCE(session_id, 'legacy:' || id)
            HAVING SUM(seconds) >= 30 OR MAX(completed) = 1
        ) GROUP BY track_id
    """, ids).fetchall()
    counts = {i: 0 for i in ids}
    counts.update({r["track_id"]: r["listens"] for r in rows})
    return counts


# Период полураспада вкуса: исполнитель, которого не слушали четыре месяца,
# весит вдвое меньше. Так рекомендации идут за тем, что нравится сейчас,
# а не за тем, что крутилось год назад.
TASTE_HALF_LIFE = 120 * 24 * 3600.0


def _decayed(weight: float, updated_at: float | None, now: float | None = None) -> float:
    try:
        weight = float(weight or 0)
        age = max(0.0, (now or time.time()) - float(updated_at or 0))
    except (TypeError, ValueError):
        return 0.0
    if not updated_at:
        return weight
    return weight * 0.5 ** (age / TASTE_HALF_LIFE)


def _taste_rows() -> list[dict]:
    now = time.time()
    rows = _conn().execute(
        "SELECT artist, weight, plays, skips, updated_at FROM artist_taste"
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["weight"] = round(_decayed(item["weight"], item.pop("updated_at"), now), 4)
        out.append(item)
    return out


def top_artists(limit: int = 8, *, min_weight: float = 0.5) -> list[dict]:
    rows = [row for row in _taste_rows() if row["weight"] >= min_weight]
    rows.sort(key=lambda row: -row["weight"])
    return rows[:max(0, int(limit))]


def recent_seed_tracks(limit: int = 8) -> list[dict]:
    """Недавние треки, которые реально слушали — сиды для рекомендаций."""
    rows = _conn().execute(
        """
        SELECT payload, MAX(played_at) AS t FROM history
        WHERE skipped = 0 AND seconds > 25
        GROUP BY track_id ORDER BY t DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_load(row) for row in rows]


def top_tracks(days: float = 30, limit: int = 40) -> list[dict]:
    """«На повторе»: треки, которые за последние дни слушали чаще всего.

    Считается одно прослушивание на сессию (как в listen_counts) и только
    настоящие — от 30 секунд или до конца; быстрые пропуски не в счёт.
    """
    since = time.time() - days * 86400
    rows = _conn().execute(
        """
        SELECT track_id, COUNT(*) AS listens, MAX(last_at) AS last_at FROM (
            SELECT track_id, MAX(played_at) AS last_at FROM history
            WHERE played_at >= ?
            GROUP BY track_id, COALESCE(session_id, 'legacy:' || id)
            HAVING SUM(seconds) >= 30 OR MAX(completed) = 1
        ) GROUP BY track_id HAVING listens >= 2
        ORDER BY listens DESC, last_at DESC LIMIT ?
        """,
        (since, max(1, int(limit))),
    ).fetchall()
    if not rows:
        return []
    ids = [row["track_id"] for row in rows]
    marks = ",".join("?" for _ in ids)
    payloads = {
        row["track_id"]: row for row in _conn().execute(
            f"""
            SELECT track_id, payload, MAX(played_at) AS played_at FROM history
            WHERE track_id IN ({marks}) GROUP BY track_id
            """,
            ids,
        ).fetchall()
    }
    out = []
    for row in rows:
        found = payloads.get(row["track_id"])
        if found is not None:
            out.append(_load(found, {"listens": row["listens"]}))
    return out


def disliked_artists(limit: int = 20) -> list[str]:
    rows = [row for row in _taste_rows() if row["weight"] < -2]
    rows.sort(key=lambda row: row["weight"])
    return [row["artist"] for row in rows[:max(0, int(limit))]]


def played_ids(limit: int = 400) -> set[str]:
    # DISTINCT + ORDER BY по невыбранной колонке в SQLite не определён:
    # «последние N» могли оказаться случайными N треками.
    rows = _conn().execute(
        "SELECT track_id FROM history GROUP BY track_id ORDER BY MAX(played_at) DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {row["track_id"] for row in rows}


_activity_cache: dict[str, tuple[float, dict]] = {}


def recent_activity(days: float = 45, limit: int = 3000) -> dict:
    """Сигналы для рекомендаций из локальной истории за последние дни.

    played  — {track_id: время последнего прослушивания};
    skips   — {track_id: число быстрых пропусков};
    keys    — payload последних треков (для сравнения по исполнителю и названию);
    artists — исполнители из истории (кого пользователь уже знает).
    """
    key = f"{days}:{limit}:{_db_path}"
    hit = _activity_cache.get(key)
    now = time.time()
    if hit and hit[0] > now:
        return hit[1]
    rows = _conn().execute(
        """
        SELECT track_id, payload, played_at, seconds, completed, skipped FROM history
        WHERE played_at >= ? ORDER BY played_at DESC LIMIT ?
        """,
        (now - days * 86400, limit),
    ).fetchall()
    played: dict[str, float] = {}
    skips: dict[str, int] = {}
    tracks: dict[str, dict] = {}
    for row in rows:
        tid = row["track_id"]
        played.setdefault(tid, row["played_at"])
        if row["skipped"] and not row["completed"] and (row["seconds"] or 0) < 30:
            skips[tid] = skips.get(tid, 0) + 1
        if tid not in tracks:
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                payload = {}
            tracks[tid] = {"artist": payload.get("artist") or "", "title": payload.get("title") or ""}
    result = {"played": played, "skips": skips, "tracks": tracks, "now": now}
    _activity_cache[key] = (now + 60, result)
    return result


def clear_history() -> None:
    conn = _conn()
    conn.execute("DELETE FROM history")
    conn.execute("DELETE FROM artist_taste")
    conn.commit()
    _activity_cache.clear()


# --------------------------------------------------------------------------- #
# история поиска
# --------------------------------------------------------------------------- #
def log_search(query: str) -> None:
    query = (query or "").strip()
    if len(query) < 2:
        return
    conn = _conn()
    conn.execute(
        """
        INSERT INTO search_history(query, hits, last_at) VALUES(?, 1, ?)
        ON CONFLICT(query) DO UPDATE SET hits = hits + 1, last_at = ?
        """,
        (query[:120], time.time(), time.time()),
    )
    conn.commit()


def recent_searches(limit: int = 8, prefix: str = "") -> list[str]:
    conn = _conn()
    if prefix:
        rows = conn.execute(
            "SELECT query FROM search_history WHERE query LIKE ? ORDER BY hits DESC, last_at DESC"
            " LIMIT ?",
            (prefix + "%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT query FROM search_history ORDER BY last_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [row["query"] for row in rows]


def forget_search(query: str) -> None:
    """Убирает один запрос из истории: подсказка исчезает насовсем."""
    query = (query or "").strip()
    if not query:
        return
    conn = _conn()
    conn.execute("DELETE FROM search_history WHERE query = ?", (query[:120],))
    conn.commit()


def clear_searches() -> None:
    conn = _conn()
    conn.execute("DELETE FROM search_history")
    conn.commit()


# --------------------------------------------------------------------------- #
# настройки
# --------------------------------------------------------------------------- #
def get_settings() -> dict[str, Any]:
    rows = _conn().execute("SELECT key, value FROM settings").fetchall()
    out = {}
    for row in rows:
        try:
            out[row["key"]] = json.loads(row["value"])
        except json.JSONDecodeError:
            out[row["key"]] = row["value"]
    return out


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    conn = _conn()
    for key, value in (values or {}).items():
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES(?, ?, ?)",
            (str(key)[:80], json.dumps(value, ensure_ascii=False), time.time()),
        )
    conn.commit()
    return get_settings()


def reset_settings() -> None:
    conn = _conn()
    conn.execute("DELETE FROM settings")
    conn.commit()


def stats() -> dict:
    conn = _conn()
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "plays": one("SELECT COUNT(*) FROM history"),
        "tracks": one("SELECT COUNT(DISTINCT track_id) FROM history"),
        "likes": one("SELECT COUNT(*) FROM likes"),
        "playlists": one("SELECT COUNT(*) FROM playlists"),
        "artists": one("SELECT COUNT(*) FROM artist_taste"),
        "hours": round((one("SELECT COALESCE(SUM(seconds),0) FROM history") or 0) / 3600, 1),
        "db": db_path(),
    }


# --------------------------------------------------------------------------- #
# состояние приложения (очередь, текущий трек, позиция)
# --------------------------------------------------------------------------- #
def get_state(key: str) -> Any:
    row = _conn().execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return None


def set_state(key: str, value: Any) -> None:
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO app_state(key, value, updated_at) VALUES(?, ?, ?)",
        (str(key)[:80], json.dumps(value, ensure_ascii=False), time.time()),
    )
    conn.commit()


def clear_state(key: str | None = None) -> None:
    conn = _conn()
    if key:
        conn.execute("DELETE FROM app_state WHERE key = ?", (key,))
    else:
        conn.execute("DELETE FROM app_state")
    conn.commit()
