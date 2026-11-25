"""
avatars.py — каталог аватарок приложения.

Аватарка — это не только картинка в интерфейсе: выбранный вариант
становится иконкой окна, панели задач и ярлыков (меню «Пуск», рабочий
стол). Поэтому рядом с PNG для каталога лежит готовый .ico на все
размеры — пережимать картинки в рантайме не нужно, а значит не нужен и
Pillow для встроенных аватарок. Пользовательские изображения нормализует custom_avatars.

Где что лежит:
    kryonyx/avatars.json      — каталог (id, имя, группа, файл, цвет)
    kryonyx/web/img/avatars/  — PNG 256×256 для интерфейса
    kryonyx/icons/<id>.ico    — многоразмерная иконка для Windows
    <данные>/icon.ico         — выбранная иконка (её берёт main._icon_path)
    <данные>/avatar.json      — что именно выбрано
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import uuid

from .paths import app_dir, data_dir, resource_dir
from . import custom_avatars

log = logging.getLogger("kryonyx.avatars")

DEFAULT_AVATAR = "kryonyx-core"

# Старое имя файла несло служебный тег персонажа в названии. Тег убран,
# но у тех, кто уже выбрал эту аватарку, в avatar.json лежит прежний id.
RENAMED = {"kryonyx-02-black-violet": DEFAULT_AVATAR,
           "kryonyx-01-saba-sky": "kryonyx-01-sky",
           "portrait-v12-ironmouse-season-0": DEFAULT_AVATAR,
           "portrait-v12-ironmouse": DEFAULT_AVATAR,
           "portrait-v12-ironmouse-season-1": DEFAULT_AVATAR,
           "portrait-v12-ironmouse-season-2": DEFAULT_AVATAR,
           "portrait-v12-ironmouse-season-3": DEFAULT_AVATAR,
           "portrait-v12-ironmouse-season-4": DEFAULT_AVATAR,
           }

_catalog: list[dict] | None = None


def _catalog_path() -> str:
    return os.path.join(resource_dir(), "avatars.json")


def catalog() -> list[dict]:
    """Список аватарок. Читается один раз и кэшируется."""
    global _catalog
    if _catalog is None:
        try:
            with open(_catalog_path(), encoding="utf-8") as handle:
                data = json.load(handle)
            _catalog = [item for item in data if isinstance(item, dict) and item.get("id")]
        except (OSError, ValueError) as exc:
            log.warning("the avatar catalog was not read: %s", exc)
            _catalog = []
    return _catalog + custom_avatars.catalog(data_dir())


def by_id(aid: str) -> dict | None:
    aid = RENAMED.get(aid, aid)
    for item in catalog():
        if item["id"] == aid:
            return item
    return None


def _state_path() -> str:
    return os.path.join(data_dir(), "avatar.json")


def current() -> str:
    try:
        with open(_state_path(), encoding="utf-8") as handle:
            aid = (json.load(handle) or {}).get("id")
        aid = RENAMED.get(aid, aid)
        if aid and by_id(aid):
            return aid
    except (OSError, ValueError):
        pass
    return DEFAULT_AVATAR


def ico_path(aid: str) -> str:
    if str(aid).startswith("custom-"):
        return str(custom_avatars.asset(data_dir(), aid, "icon.ico"))
    if by_id(aid) is None:
        raise ValueError('Unknown built-in avatar')
    bundled=os.path.join(resource_dir(), "icons", f"{aid}.ico")
    if os.path.isfile(bundled):return bundled
    # Slim builds omit hundreds of duplicate ICOs. Only the picked one is made.
    from PIL import Image
    import io
    image=os.path.join(resource_dir(),'web','img','avatars',f'{aid}.png')
    with open(image,'rb') as handle:content=handle.read()
    folder=os.path.join(data_dir(),'avatar-icons');os.makedirs(folder,exist_ok=True)
    target=os.path.join(folder,hashlib.sha256(content).hexdigest()+'-generated.ico')
    if not os.path.isfile(target):
        with Image.open(io.BytesIO(content)) as source:
            output=io.BytesIO();source.convert('RGBA').save(output,format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
        _atomic_bytes(target,output.getvalue())
    return target


def refresh_active_icon() -> bool:
    """Refresh a previously selected built-in icon after a bundled pack update."""
    import hashlib
    aid = current()
    if aid.startswith("custom-"):
        return False
    source = ico_path(aid)
    target = os.path.join(data_dir(), "icon.ico")
    try:
        with open(source, "rb") as handle:
            content = handle.read()
        if os.path.isfile(target):
            with open(target, "rb") as handle:
                if hashlib.sha256(handle.read()).digest() == hashlib.sha256(content).digest():
                    return False
        # Copy only our selected icon. Never switch avatar or overwrite user artwork.
        temporary = target + ".updating"
        with open(temporary, "wb") as handle:
            handle.write(content)
        os.replace(temporary, target)
        return True
    except OSError as exc:
        log.debug("active icon refresh skipped: %s", exc)
        return False


def active_icon() -> str | None:
    """Готовая иконка выбранной аватарки, если она уже выложена в данные."""
    path = os.path.join(data_dir(), "icon.ico")
    return path if os.path.isfile(path) else None


def state() -> dict:
    aid = current()
    return {"id": aid, "default": DEFAULT_AVATAR, "items": catalog(),
            "shortcuts": os.name == "nt"}


# --------------------------------------------------------------------- выбор
def _windows_supported() -> bool:
    return os.name == "nt"


_selection_lock = threading.RLock()
_live_icon_callback = None
_window_icons: dict[int, dict[int, int]] = {}


def set_live_icon_callback(callback) -> None:
    """Attach the native tray updater without coupling the HTTP server to WebView."""
    global _live_icon_callback
    _live_icon_callback = callback


def _atomic_bytes(path: str, content: bytes) -> None:
    temporary = path + ".tmp-" + uuid.uuid4().hex
    try:
        with open(temporary, "wb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.isfile(temporary):
            os.unlink(temporary)


def choose(aid: str) -> dict:
    """Commit one selection atomically; apply live icons before updating shortcuts.

    Content-addressed ICO paths bypass Explorer's same-filename icon cache.
    Serialized selections prevent background PowerShell jobs from winning late.
    """
    with _selection_lock:
        aid = RENAMED.get(aid, aid)
        item = by_id(aid)
        if item is None:
            raise ValueError(f"unknown avatar: {aid}")
        try:source = ico_path(aid)
        except OSError as exc:raise ValueError('The avatar icon could not be prepared') from exc
        target = os.path.join(data_dir(), "icon.ico")
        previous = None
        try:
            with open(source, "rb") as handle:
                content = handle.read()
            if not content:
                raise OSError("Empty avatar icon")
            os.makedirs(data_dir(), exist_ok=True)
            cache = os.path.join(data_dir(), "avatar-icons")
            os.makedirs(cache, exist_ok=True)
            immutable = os.path.join(cache, hashlib.sha256(content).hexdigest() + ".ico")
            if not os.path.isfile(immutable):
                _atomic_bytes(immutable, content)
            if os.path.isfile(target):
                with open(target, "rb") as handle:
                    previous = handle.read()
            _atomic_bytes(target, content)
            try:
                _atomic_bytes(_state_path(), json.dumps({"id": aid}).encode("utf-8"))
            except OSError:
                if previous is not None:
                    _atomic_bytes(target, previous)
                else:
                    os.unlink(target)
                raise
        except OSError as exc:
            raise ValueError("The avatar icon could not be saved") from exc

        window = set_window_icon("Kryo", immutable)
        if _live_icon_callback is not None:
            try:
                _live_icon_callback(immutable)
            except Exception as exc:
                log.warning("tray icon update failed: %s", exc)
        shortcuts = _apply_shortcuts(immutable) if _windows_supported() else {"updated":0,"failed":0,"skipped":0}
        log.info("[avatar] %s selected; live window=%s, shortcuts=%s", aid, window, shortcuts)
        return {"ok":True,"id":aid,"icon":immutable,"window":window,
                "shortcuts":bool(shortcuts.get("updated")) and not shortcuts.get("failed"),
                "shortcut_result":shortcuts,"item":item}


# ------------------------------------------------------------------ Windows
def _shortcut_candidates() -> list[str]:
    roots = []
    for env, subs in (
        ("APPDATA", [os.path.join("Microsoft", "Windows", "Start Menu", "Programs"),
                     os.path.join("Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar"),
                     os.path.join("Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "ImplicitAppShortcuts")]),
        ("ProgramData", [os.path.join("Microsoft", "Windows", "Start Menu", "Programs")]),
        ("USERPROFILE", ["Desktop", os.path.join("OneDrive", "Desktop")]),
        ("PUBLIC", ["Desktop"]), ("OneDrive", ["Desktop"]),
        ("OneDriveCommercial", ["Desktop"]), ("OneDriveConsumer", ["Desktop"]),
    ):
        root = os.getenv(env)
        if root:
            roots.extend(os.path.join(root, sub) for sub in subs)
    return list(dict.fromkeys(p for p in roots if os.path.isdir(p)))


def _find_shortcuts() -> list[str]:
    found = set()
    for root in _shortcut_candidates():
        for base, dirs, files in os.walk(root):
            if base[len(root):].count(os.sep) >= 3:
                dirs[:] = []
            for name in files:
                lower = name.lower()
                if lower.endswith(".lnk") and ("kryo" in lower or "крионикс" in lower):
                    found.add(os.path.join(base, name))
    return sorted(found)


def _shortcut_script(icon: str, links: list[str]) -> str:
    import sys
    payload = {"icon":icon,"links":links,
               "targets":[os.path.join(app_dir(),"Kryo.exe"),os.path.join(app_dir(),"start.bat")],
               "python":sys.executable,"entry":os.path.join(app_dir(),"run.py")}
    if getattr(sys,"frozen",False):
        payload["targets"].append(sys.executable)
    data = base64.b64encode(json.dumps(payload,ensure_ascii=False).encode("utf-8")).decode("ascii")
    # No paths are interpolated as PowerShell syntax (apostrophes, Cyrillic, spaces).
    return "$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + data + "')) | ConvertFrom-Json; " + r"""
$ws = New-Object -ComObject WScript.Shell
$updated = 0; $failed = 0; $skipped = 0
foreach ($path in $p.links) {
  try {
    $l = $ws.CreateShortcut($path)
    $target = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($l.TargetPath))
    $ours = $p.targets -contains $target
    if (!$ours -and $target -ieq $p.python) {
      $ours = $l.Arguments.IndexOf($p.entry, [StringComparison]::OrdinalIgnoreCase) -ge 0
    }
    if (!$ours) { $skipped++; continue }
    $l.IconLocation = $p.icon + ',0'; $l.Save()
    $updated++
  } catch { $failed++ }
}
@{updated=$updated;failed=$failed;skipped=$skipped} | ConvertTo-Json -Compress
"""


def _apply_shortcuts(icon: str) -> dict:
    links = _find_shortcuts()
    if not links:
        return {"updated":0,"failed":0,"skipped":0}
    command = base64.b64encode(_shortcut_script(icon,links).encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(["powershell","-NoProfile","-NonInteractive",
                                 "-ExecutionPolicy","Bypass","-EncodedCommand",command],
                                timeout=20,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),
                                capture_output=True,text=True,check=True)
        report = json.loads(result.stdout.strip().lstrip("\ufeff"))
        report = {k:max(0,int(report.get(k,0))) for k in ("updated","failed","skipped")}
        if report["updated"]:
            _refresh_shell(links)
        return report
    except (OSError,subprocess.SubprocessError,ValueError,TypeError) as exc:
        log.warning("shortcuts were not updated: %s",exc)
        return {"updated":0,"failed":len(links),"skipped":0}


def _refresh_shell(links=()) -> None:
    if not _windows_supported():
        return
    try:
        import ctypes
        from ctypes import wintypes
        shell = ctypes.WinDLL("shell32",use_last_error=True)
        shell.SHChangeNotify.argtypes=[wintypes.LONG,wintypes.UINT,wintypes.LPCVOID,wintypes.LPCVOID]
        shell.SHChangeNotify.restype=None
        for link in links:
            shell.SHChangeNotify(0x2000,0x0005,ctypes.c_wchar_p(link),None)  # UPDATEITEM / PATHW
        shell.SHChangeNotify(0x08000000,0,None,None)  # invalidate association icon cache
    except Exception as exc:                            # pragma: no cover
        log.debug("shell refresh failed: %s",exc)


def _win_icon_api():
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL("user32",use_last_error=True)
    user.LoadImageW.argtypes=[wintypes.HINSTANCE,wintypes.LPCWSTR,wintypes.UINT,ctypes.c_int,ctypes.c_int,wintypes.UINT]
    user.LoadImageW.restype=wintypes.HANDLE
    user.SendMessageTimeoutW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM,
                                      wintypes.UINT,wintypes.UINT,ctypes.POINTER(ctypes.c_size_t)]
    user.SendMessageTimeoutW.restype=wintypes.LPARAM
    user.DestroyIcon.argtypes=[wintypes.HICON];user.DestroyIcon.restype=wintypes.BOOL
    user.IsWindow.argtypes=[wintypes.HWND];user.IsWindow.restype=wintypes.BOOL
    return user


def set_window_icon(title: str = "Kryo", icon: str | None = None) -> bool:
    with _selection_lock:
        return _set_window_icon(title, icon)


def _set_window_icon(title: str, icon: str | None) -> bool:
    """Use this process's HWND, never the changing track title. Pointer-safe on x64."""
    if not _windows_supported():
        return False
    icon = icon or active_icon()
    if not icon:
        return False
    try:
        import ctypes
        from .taskbar import find_main_window
        hwnd = find_main_window()
        if not hwnd:
            return False
        user = _win_icon_api()
        # We only destroy handles allocated by this module, not OS/WebView icons.
        for old_hwnd in list(_window_icons):
            if not user.IsWindow(old_hwnd):
                for handle in _window_icons.pop(old_hwnd).values():
                    user.DestroyIcon(handle)
        owned = _window_icons.setdefault(hwnd,{})
        changed = False
        for kind,size in ((1,32),(0,16)):
            handle = user.LoadImageW(None,icon,1,size,size,0x0010)
            if not handle:
                continue
            result = ctypes.c_size_t()
            if user.SendMessageTimeoutW(hwnd,0x0080,kind,handle,0x0002,500,ctypes.byref(result)):
                previous = owned.get(kind)
                owned[kind] = handle
                if previous:
                    user.DestroyIcon(previous)
                changed = True
            else:
                user.DestroyIcon(handle)
        return changed
    except Exception as exc:                            # pragma: no cover
        log.warning("live window icon not replaced: %s",exc)
        return False


def web_icon() -> str:
    """PNG выбранной аватарки — его отдаёт /icon.png и favicon интерфейса."""
    aid = current()
    if aid.startswith("custom-"):
        return str(custom_avatars.asset(data_dir(), aid))
    path = os.path.join(resource_dir(), "web", "img", "avatars", f"{aid}.png")
    if os.path.isfile(path):
        return path
    return os.path.join(resource_dir(), "web", "icon.png")
