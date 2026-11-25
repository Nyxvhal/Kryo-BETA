"""
extplugins.py — свои плагины и свои библиотеки.

Встроенный каталог (plugins.py) описывает возможности, код которых уже лежит
внутри приложения. Этот модуль добавляет второй слой: человек кладёт свой
файл в папку плагинов — и он появляется в каталоге рядом со встроенными,
с переключателем, настройками и живой проверкой.

Где лежат плагины
-----------------
    <данные>/plugins/            своя папка пользователя (основная)
    <рядом с программой>/plugins/ переносной запуск (флешка, распакованный архив)
    KRYONYX_PLUGINS_DIR          своя папка, если так удобнее

Плагином считается:
    myplugin.py                  один файл
    myplugin/plugin.py           папка (можно с __init__.py и своими модулями)

Свои библиотеки
---------------
    <данные>/lib/                добавляется в sys.path целиком,
                                 .whl/.zip внутри — тоже

Что должен объявить плагин
--------------------------
    PLUGIN = {
        "id": "myradio",            # необязательно: по умолчанию имя файла
        "name": "My Radio",
        "version": "1.0.0",
        "author": "Имя автора",
        "description": "Что он делает",
        "categories": ["streaming"],
        "settings": [{"key": "token", "label": "Token", "type": "password",
                      "required": False}],
    }

    def search(query, limit=20, offset=0, config=None): -> list[dict]
    def resolve(ref, config=None): -> {"url": "...", "mime": "audio/mpeg"}
    def dashboard(config=None): -> list[dict] | dict
    def selftest(config=None): -> {"state": "ok", "note": ""}
    def setup(api): ...            # вызывается один раз при загрузке

Любая из функций может быть обычной или async — вызов подстраивается сам.

Безопасность и устойчивость
---------------------------
Плагин — это код пользователя на его же устройстве, поэтому он выполняется в
том же процессе. Чтобы чужая ошибка не уронила плеер: импорт и каждый вызов
обёрнуты, у вызова есть предел по времени, а неудача плагина выключает только
его самого — остальные источники продолжают работать. Ошибка целиком видна в
карточке плагина и в журнале.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import logging
import os
import shutil
import sys
import threading
import time
import traceback
import zipfile
from typing import Any, Callable, Iterable

from . import plugins as catalog
from .paths import extra_lib_dirs, extra_plugin_dirs, libs_dir, plugins_dir

log = logging.getLogger(__name__)

PREFIX = "x:"                 # id трека: x:<plugin>:<свой id>
SOURCE_PREFIX = "ext:"        # имя источника поиска: ext:<plugin>
CALL_TIMEOUT = 25.0
HOOKS = ("search", "resolve", "dashboard", "selftest", "lyrics")

_lock = threading.Lock()
_entries: dict[str, dict] = {}     # pid -> запись о плагине
_errors: list[dict] = []           # что не загрузилось
_lib_paths: list[str] = []
_loaded_at: float = 0.0


# --------------------------------------------------------------------------- #
# вспомогательное
# --------------------------------------------------------------------------- #
def _slug(value: str) -> str:
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(value).lower())
    return out.strip("-_")[:48]


def source_name(pid: str) -> str:
    return SOURCE_PREFIX + pid


def track_prefix(pid: str) -> str:
    return f"{PREFIX}{pid}:"


def sources() -> list[str]:
    """Источники поиска, которые дают свои плагины (только включённые)."""
    return [source_name(pid) for pid, entry in _entries.items()
            if entry["hooks"].get("search") and catalog.enabled(pid)]


def prefixes() -> dict[str, str]:
    return {source_name(pid): track_prefix(pid) for pid in _entries}


def pid_of_source(source: str) -> str:
    return source[len(SOURCE_PREFIX):] if source.startswith(SOURCE_PREFIX) else ""


def pid_of_track(track_id: str) -> str:
    if not track_id.startswith(PREFIX):
        return ""
    return track_id[len(PREFIX):].split(":", 1)[0]


# --------------------------------------------------------------------------- #
# мостик, который получает сам плагин
# --------------------------------------------------------------------------- #
class PluginApi:
    """Небольшой набор готовых инструментов: чтобы плагин был коротким.

    Сеть здесь на urllib — плагину не нужно знать ни про aiohttp, ни про то,
    в каком потоке его вызвали.
    """

    def __init__(self, pid: str, folder: str) -> None:
        self.id = pid
        self.folder = folder
        self.log = logging.getLogger(f"kryonyx.plugin.{pid}")

    @property
    def config(self) -> dict:
        return catalog.config(self.id)

    def data_dir(self) -> str:
        path = os.path.join(plugins_dir(), "_data", self.id)
        os.makedirs(path, exist_ok=True)
        return path

    def get(self, url: str, *, params: dict | None = None,
            headers: dict | None = None, timeout: float = 15.0) -> bytes:
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen
        if params:
            url = url + ("&" if "?" in url else "?") + urlencode(params)
        request = Request(url, headers={"User-Agent": "KryonyxMusic/plugin",
                                        **(headers or {})})
        with urlopen(request, timeout=timeout) as answer:   # noqa: S310 (свой плагин)
            return answer.read()

    def get_json(self, url: str, **kwargs) -> Any:
        return json.loads(self.get(url, **kwargs).decode("utf-8", "replace"))

    def track(self, *, id: str, title: str, artist: str = "", **extra) -> dict:
        """Готовый трек в формате плеера: id сам получит нужную приставку."""
        return {"id": f"{track_prefix(self.id)}{id}", "title": title,
                "artist": artist, "source": source_name(self.id), **extra}


# --------------------------------------------------------------------------- #
# загрузка
# --------------------------------------------------------------------------- #
def _manifest(module: Any, pid: str, path: str) -> dict:
    raw = getattr(module, "PLUGIN", None)
    data = dict(raw) if isinstance(raw, dict) else {}
    side = os.path.join(os.path.dirname(path), "plugin.json")
    if os.path.isdir(path):
        side = os.path.join(path, "plugin.json")
    if os.path.isfile(side):
        try:
            with open(side, encoding="utf-8") as handle:
                extra = json.load(handle)
            if isinstance(extra, dict):
                data = {**extra, **data}
        except (OSError, ValueError) as exc:
            log.warning("[plugins] %s: plugin.json is broken: %s", pid, exc)
    data.setdefault("id", pid)
    data["id"] = _slug(data["id"]) or pid
    data.setdefault("name", pid)
    data.setdefault("version", "1.0.0")
    data.setdefault("author", "")
    data.setdefault("description", "")
    cats = data.get("categories")
    data["categories"] = [str(c) for c in cats] if isinstance(cats, list) else ["other"]
    settings = data.get("settings")
    data["settings"] = [s for s in settings if isinstance(s, dict)] \
        if isinstance(settings, list) else []
    return data


def _hooks(module: Any) -> dict[str, Callable]:
    out = {}
    for name in HOOKS:
        func = getattr(module, name, None)
        if callable(func):
            out[name] = func
    return out


def _candidates() -> list[str]:
    found: list[str] = []
    for base in extra_plugin_dirs():
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            if name.startswith((".", "_")):
                continue
            path = os.path.join(base, name)
            if os.path.isfile(path) and name.endswith(".py"):
                found.append(path)
            elif os.path.isdir(path):
                for inner in ("plugin.py", "__init__.py", "main.py"):
                    if os.path.isfile(os.path.join(path, inner)):
                        found.append(path)
                        break
    return found


def _import(path: str) -> tuple[Any, str]:
    """Импорт файла или папки как отдельного модуля (без засорения пакета)."""
    if os.path.isdir(path):
        name = os.path.basename(path.rstrip(os.sep))
        entry = next(os.path.join(path, inner) for inner in
                     ("plugin.py", "__init__.py", "main.py")
                     if os.path.isfile(os.path.join(path, inner)))
        locations = [path]
    else:
        name = os.path.splitext(os.path.basename(path))[0]
        entry = path
        locations = None
    pid = _slug(name) or "plugin"
    mod_name = f"kryonyx_plugin_{pid}"
    spec = importlib.util.spec_from_file_location(
        mod_name, entry, submodule_search_locations=locations)
    if spec is None or spec.loader is None:
        raise ImportError(f"{path}: Python did not accept this file")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(mod_name, None)
        raise
    return module, pid


def load_all(*, register: bool = True) -> dict:
    """Перечитывает папки плагинов и библиотек с нуля."""
    global _lib_paths, _loaded_at
    from . import bootstrap

    with _lock:
        bootstrap.add_lib_paths()
        # Что из своих библиотек реально видно импорту прямо сейчас.
        _lib_paths = [path for path in extra_lib_dirs() if path in sys.path]
        found: dict[str, dict] = {}
        broken: list[dict] = []
        for path in _candidates():
            try:
                module, pid = _import(path)
                data = _manifest(module, pid, path)
                pid = data["id"]
                if pid in catalog.BUILTIN_IDS:
                    raise ValueError(
                        f"id «{pid}» already belongs to a built-in plugin — rename it")
                if pid in found:
                    raise ValueError(f"id «{pid}» is already taken by {found[pid]['path']}")
                hooks = _hooks(module)
                api = PluginApi(pid, os.path.dirname(path) if os.path.isfile(path) else path)
                if callable(getattr(module, "setup", None)):
                    module.setup(api)
                found[pid] = {"id": pid, "manifest": data, "module": module,
                              "hooks": hooks, "path": path, "api": api,
                              "loaded_at": time.time()}
                log.info("[plugins] custom plugin is loaded: %s (%s) — %s",
                         data["name"], pid, ", ".join(sorted(hooks)) or "no hooks")
            except BaseException as exc:                    # плагин чужой: ловим всё
                tail = traceback.format_exc(limit=4).strip().splitlines()
                broken.append({"id": _slug(os.path.basename(path)), "path": path,
                               "error": f"{type(exc).__name__}: {exc}",
                               "trace": tail[-6:]})
                log.error("[plugins] custom plugin failed: %s — %s", path, exc)
        _entries.clear()
        _entries.update(found)
        _errors.clear()
        _errors.extend(broken)
        _loaded_at = time.time()

    if register:
        catalog.register_external(catalog_entries())
    return status()


def catalog_entries() -> list[dict]:
    """Свои плагины в том же виде, в каком каталог показывает встроенные."""
    out = []
    for pid, entry in _entries.items():
        data = entry["manifest"]
        hooks = sorted(entry["hooks"])
        out.append({
            "id": pid,
            "name": data["name"],
            "author": data["author"] or "custom plugin",
            "plugin_author": data.get("plugin_author") or data["author"] or "",
            "credits": data.get("credits") if isinstance(data.get("credits"), list) else [],
            "api": data.get("api") or ", ".join(hooks),
            "based_on": data.get("based_on") or "",
            "version": str(data["version"]),
            "categories": data["categories"] or ["other"],
            "description": data["description"] or "Custom plugin from your plugins folder",
            "core": False,
            "preinstalled": True,      # файл положили руками — значит он нужен
            "custom": True,
            "source": source_name(pid) if "search" in entry["hooks"] else None,
            "needs_ytdlp": bool(data.get("needs_ytdlp")),
            "settings": data["settings"],
            "homepage": data.get("homepage") or "",
            "path": entry["path"],
            "hooks": hooks,
        })
    return out


def status() -> dict:
    return {
        "plugins_dirs": extra_plugin_dirs(),
        "lib_dirs": extra_lib_dirs(),
        "lib_paths": list(_lib_paths),
        "loaded_at": _loaded_at,
        "items": [
            {**item,
             "enabled": catalog.enabled(item["id"]),
             "installed": catalog.installed(item["id"])}
            for item in catalog_entries()
        ],
        "errors": list(_errors),
        "libs": installed_libs(),
    }


def installed_libs() -> list[dict]:
    """Что лежит в папке своих библиотек: пакеты, модули и колёса."""
    from . import bootstrap

    core = bootstrap.core_libs()
    out: list[dict] = []
    seen: set[str] = set()
    for base in extra_lib_dirs():
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            if name.startswith(".") or name.endswith((".dist-info", ".egg-info", ".pth")):
                continue
            path = os.path.join(base, name)
            label = name[:-3] if name.endswith(".py") else name
            if label in seen or label == "__pycache__":
                continue
            seen.add(label)
            try:
                size = (sum(f.stat().st_size for f in os.scandir(path) if f.is_file())
                        if os.path.isdir(path) else os.path.getsize(path))
            except OSError:
                size = 0
            out.append({"name": label, "path": path, "dir": base,
                        "kind": "package" if os.path.isdir(path) else "file",
                        "size": size,
                        # Зависимости самого плеера удалять нельзя: без них
                        # приложение просто не запустится в следующий раз.
                        "protected": label in core})
    return out


# --------------------------------------------------------------------------- #
# вызов плагина
# --------------------------------------------------------------------------- #
async def _call(pid: str, hook: str, *args, **kwargs) -> Any:
    entry = _entries.get(pid)
    if not entry:
        raise KeyError(pid)
    func = entry["hooks"].get(hook)
    if func is None:
        raise LookupError(f"plugin «{pid}» has no {hook}()")
    kwargs.setdefault("config", catalog.config(pid))
    try:
        params = inspect.signature(func).parameters
        if "config" not in params and not any(
                p.kind == p.VAR_KEYWORD for p in params.values()):
            kwargs.pop("config", None)
    except (TypeError, ValueError):
        pass
    if inspect.iscoroutinefunction(func):
        return await asyncio.wait_for(func(*args, **kwargs), CALL_TIMEOUT)
    return await asyncio.wait_for(asyncio.to_thread(func, *args, **kwargs), CALL_TIMEOUT)


def _tracks(pid: str, raw: Any) -> list[dict]:
    """Приводим выдачу плагина к формату плеера. Мусор молча отбрасываем."""
    if isinstance(raw, dict):
        raw = raw.get("tracks") or raw.get("items") or []
    if not isinstance(raw, (list, tuple)):
        return []
    prefix = track_prefix(pid)
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        ident = str(item.get("id") or item.get("url") or "").strip()
        if not title or not ident:
            continue
        track = {**item}
        track["id"] = ident if ident.startswith(prefix) else prefix + ident
        track["title"] = title
        track["artist"] = str(item.get("artist") or item.get("uploader") or "").strip()
        track["source"] = source_name(pid)
        duration = item.get("duration")
        try:
            track["duration"] = int(float(duration)) if duration else None
        except (TypeError, ValueError):
            track["duration"] = None
        out.append(track)
    return out


async def search(source: str, query: str, limit: int = 20, offset: int = 0) -> list[dict]:
    """Поиск через свой плагин. Его падение не должно ломать общий поиск."""
    pid = pid_of_source(source) or source
    if pid not in _entries or not catalog.enabled(pid):
        return []
    try:
        raw = await _call(pid, "search", query, limit=limit, offset=offset)
    except (LookupError, KeyError):
        return []
    except asyncio.TimeoutError:
        log.warning("[plugins] %s: search() did not answer in %.0f s", pid, CALL_TIMEOUT)
        return []
    except BaseException as exc:
        log.warning("[plugins] %s: search() failed: %s", pid, exc)
        return []
    return _tracks(pid, raw)[:limit]


async def resolve(track_id: str) -> dict:
    """Ссылка на звук от своего плагина: {"url", "headers", "mime", "size"}."""
    pid = pid_of_track(track_id)
    entry = _entries.get(pid)
    if not entry:
        raise RuntimeError(f"plugin «{pid}» is not loaded — the track cannot be played")
    if not catalog.enabled(pid):
        raise RuntimeError(f"plugin «{pid}» is turned off")
    ref = track_id[len(track_prefix(pid)):]
    raw = await _call(pid, "resolve", ref)
    if isinstance(raw, str):
        raw = {"url": raw}
    if not isinstance(raw, dict) or not str(raw.get("url") or "").startswith(("http", "file")):
        raise RuntimeError(f"plugin «{pid}» returned no playable link")
    return {"url": str(raw["url"]),
            "headers": raw.get("headers") if isinstance(raw.get("headers"), dict) else {},
            "size": int(raw["size"]) if str(raw.get("size") or "").isdigit() else None,
            "mime": str(raw.get("mime") or "audio/mpeg")}


async def dashboard_rows(limit: int = 16) -> list[dict]:
    """Ряды для главной от своих плагинов."""
    rows: list[dict] = []
    for pid, entry in list(_entries.items()):
        if "dashboard" not in entry["hooks"] or not catalog.enabled(pid):
            continue
        try:
            raw = await _call(pid, "dashboard")
        except BaseException as exc:
            log.debug("[plugins] %s: dashboard() failed: %s", pid, exc)
            continue
        groups = raw if isinstance(raw, list) and raw and isinstance(raw[0], dict) \
            and ("tracks" in raw[0] or "items" in raw[0]) else [
                {"title": entry["manifest"]["name"], "tracks": raw}]
        for group in groups:
            tracks = _tracks(pid, group.get("tracks") or group.get("items"))[:limit]
            if tracks:
                rows.append({"id": f"ext-{pid}-{len(rows)}",
                             "title": str(group.get("title")
                                          or entry["manifest"]["name"]),
                             "plugin": pid, "items": tracks})
    return rows


async def selftest(pid: str) -> dict:
    """Живая проверка своего плагина: его же selftest() или один поиск."""
    entry = _entries.get(pid)
    if not entry:
        return {"id": pid, "state": "fail", "note": "the plugin is not loaded", "ms": 0}
    started = time.perf_counter()
    try:
        if "selftest" in entry["hooks"]:
            raw = await _call(pid, "selftest")
            if isinstance(raw, dict):
                state = str(raw.get("state") or "ok")
                note = str(raw.get("note") or "")
            else:
                state, note = ("ok" if raw else "fail"), ""
        elif "search" in entry["hooks"]:
            found = await search(source_name(pid), "music", 3)
            state = "ok" if found else "warn"
            note = f"{len(found)} tracks"
        else:
            state, note = "skip", "no search() and no selftest()"
    except BaseException as exc:
        state, note = "fail", f"{type(exc).__name__}: {exc}"
    return {"id": pid, "state": state, "note": note,
            "ms": int((time.perf_counter() - started) * 1000)}


# --------------------------------------------------------------------------- #
# управление файлами: установка и удаление
# --------------------------------------------------------------------------- #
MAX_FILE = 8 * 1024 * 1024


def install_file(name: str, payload: bytes) -> dict:
    """Кладёт в папку плагинов присланный .py или .zip и перечитывает каталог."""
    if len(payload) > MAX_FILE:
        raise ValueError("the file is larger than 8 MB")
    safe = _slug(os.path.splitext(os.path.basename(name))[0])
    if not safe:
        raise ValueError("the file name is not usable")
    base = plugins_dir()
    lower = name.lower()
    if lower.endswith(".py"):
        target = os.path.join(base, safe + ".py")
        with open(target, "wb") as handle:
            handle.write(payload)
    elif lower.endswith(".zip"):
        target = os.path.join(base, safe)
        tmp = target + ".part"
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        raw = os.path.join(base, safe + ".zip.tmp")
        with open(raw, "wb") as handle:
            handle.write(payload)
        try:
            with zipfile.ZipFile(raw) as archive:
                for member in archive.namelist():
                    # Архив чужой: ни «..», ни абсолютных путей наружу.
                    place = os.path.realpath(os.path.join(tmp, member))
                    if not place.startswith(os.path.realpath(tmp) + os.sep):
                        raise ValueError(f"the archive tries to write outside: {member}")
                archive.extractall(tmp)
        finally:
            try:
                os.remove(raw)
            except OSError:
                pass
        inner = [os.path.join(tmp, e) for e in os.listdir(tmp)]
        # Архив из одной папки распаковываем на уровень выше.
        if len(inner) == 1 and os.path.isdir(inner[0]):
            tmp_inner = inner[0]
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(tmp_inner, target)
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            shutil.rmtree(target, ignore_errors=True)
            shutil.move(tmp, target)
    else:
        raise ValueError("only .py files and .zip archives are accepted")
    load_all()
    return {"installed": safe, "path": target, **status()}


def remove(pid: str) -> dict:
    """Удаляет файл или папку своего плагина."""
    entry = _entries.get(pid)
    if not entry:
        raise KeyError(pid)
    path = entry["path"]
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except OSError as exc:
            raise ValueError(f"the file was not removed: {exc}") from exc
    try:
        catalog.uninstall(pid)
    except Exception:
        pass
    load_all()
    return status()


def remove_lib(name: str) -> dict:
    """Удаляет свою библиотеку. Встроенные зависимости не трогаем."""
    target = _slug(name)
    hit = next((item for item in installed_libs() if _slug(item["name"]) == target), None)
    if not hit:
        raise KeyError(name)
    if hit["protected"]:
        raise ValueError(f"«{hit['name']}» is a dependency of the player itself "
                         f"and cannot be removed here")
    path = hit["path"]
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except OSError as exc:
            raise ValueError(str(exc)) from exc
    # Сопутствующие метаданные pip (*.dist-info) тоже убираем.
    for extra in os.listdir(hit["dir"]):
        if extra.lower().startswith(hit["name"].lower().replace("-", "_")) \
                and extra.endswith((".dist-info", ".egg-info")):
            shutil.rmtree(os.path.join(hit["dir"], extra), ignore_errors=True)
    return status()


def install_lib(specs: Iterable[str]) -> dict:
    """Ставит библиотеку в папку своих библиотек (pip install --target)."""
    from . import bootstrap

    wanted = [str(s).strip() for s in specs if str(s).strip()][:10]
    if not wanted:
        raise ValueError("nothing to install")
    good, note = bootstrap.install(wanted)
    if not good:
        raise RuntimeError(note or "pip could not install it")
    return {"installed": wanted, "target": libs_dir(), **status()}


# --------------------------------------------------------------------------- #
# первый запуск: папки, подсказка и пример
# --------------------------------------------------------------------------- #
README = """# Свои плагины Kryo

Положите сюда файл `.py` (или папку с `plugin.py`) и нажмите «Перечитать»
в Настройки → Плагины → Свои плагины. Перезапуск не нужен.

    PLUGIN = {"id": "myradio", "name": "My Radio", "version": "1.0.0",
              "author": "Я", "description": "Мой источник",
              "categories": ["streaming"]}

    def search(query, limit=20, offset=0, config=None):
        return [{"id": "1", "title": "Трек", "artist": "Автор",
                 "duration": 180, "thumbnail": "https://..."}]

    def resolve(ref, config=None):
        return {"url": "https://example.com/audio.mp3", "mime": "audio/mpeg"}

Необязательные функции: `dashboard()` — ряд на главной, `selftest()` — своя
проверка, `setup(api)` — разовая подготовка (у `api` есть `get_json`,
`config`, `track`, `data_dir`, `log`).

Свои библиотеки Python кладите в папку `lib` рядом с этой: она целиком
добавляется в `sys.path`, поэтому `import` в плагине работает как обычно.
Ставить библиотеки можно и кнопкой в том же разделе (pip, без прав
администратора).

Плагины живут у каждого пользователя свои, работают только на этом
устройстве и ничего никуда не отправляют сами.
"""

EXAMPLE = '''"""Пример своего плагина: один файл, без зависимостей.

Чтобы он заработал, переименуйте этот файл в example.py
(без .txt) и нажмите «Перечитать».
"""

PLUGIN = {
    "id": "example",
    "name": "Example source",
    "version": "1.0.0",
    "author": "Ваше имя",
    "description": "Пример: показывает, как устроен свой плагин",
    "categories": ["streaming"],
    "settings": [
        {"key": "limit", "label": "How many tracks", "type": "text",
         "required": False, "placeholder": "5",
         "hint": "Демонстрация настроек плагина"},
    ],
}

# Свободно звучащие записи Internet Archive: ссылка прямая, ключи не нужны.
TRACKS = [
    {"id": "jamendo-1", "title": "Example track", "artist": "Example artist",
     "duration": 180,
     "url": "https://archive.org/download/testmp3testfile/mpthreetest.mp3"},
]


def search(query, limit=20, offset=0, config=None):
    """Возвращает треки. id — свой, приставку плеер добавит сам."""
    want = (query or "").strip().lower()
    found = [t for t in TRACKS if want in (t["title"] + t["artist"]).lower()]
    return (found or TRACKS)[offset:offset + limit]


def resolve(ref, config=None):
    """ref — это тот самый id из search(). Отдаём прямую ссылку на звук."""
    for track in TRACKS:
        if track["id"] == ref:
            return {"url": track["url"], "mime": "audio/mpeg"}
    raise LookupError(ref)


def selftest(config=None):
    return {"state": "ok", "note": f"{len(TRACKS)} track(s) in the example"}
'''


def bootstrap_dirs() -> None:
    """Создаёт папки и кладёт подсказку с примером — один раз."""
    base = plugins_dir()
    libs_dir()
    for name, text in (("README.md", README), ("example.py.txt", EXAMPLE)):
        path = os.path.join(base, name)
        if not os.path.exists(path):
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
            except OSError as exc:
                log.debug("[plugins] %s was not written: %s", path, exc)


def example_text() -> str:
    return EXAMPLE


def init() -> dict:
    """Полная подготовка: папки, sys.path, импорт плагинов, запись в каталог."""
    bootstrap_dirs()
    try:
        return load_all()
    except Exception as exc:                                # pragma: no cover
        log.error("[plugins] custom plugins were not loaded: %s", exc)
        return {"items": [], "errors": [{"id": "", "path": "", "error": str(exc)}]}


def loaded_ids() -> list[str]:
    return list(_entries)


def has(pid: str) -> bool:
    return pid in _entries
