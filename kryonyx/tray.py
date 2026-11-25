"""Значок в области уведомлений Windows (трей).

Показывает, что сейчас играет (подсказка при наведении и короткое
уведомление при смене трека, если окно свёрнуто), и даёт управлять
плеером из меню по правому щелчку: назад, пауза/играть, дальше,
показать окно, выйти. Левый щелчок разворачивает окно.

Написано на чистом ctypes, без pywin32: у значка свой поток со своим
циклом сообщений, поэтому поток интерфейса pywebview он не трогает.
На других системах модуль ничего не делает.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Callable

log = logging.getLogger("kryonyx.tray")

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:                                          # pragma: no cover
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                    ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                    ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
                    ("hBalloonIcon", wintypes.HICON)]

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt", POINT)]

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR,
                                       wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                   ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      wintypes.LPVOID]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
    user32.LoadIconW.restype = wintypes.HICON
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
    user32.SetTimer.restype = ctypes.c_size_t
    user32.IsWindow.argtypes = [wintypes.HWND]
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.ExtractIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT]
    shell32.ExtractIconW.restype = wintypes.HICON
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_USER = 0x0400
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_TRAY = WM_USER + 20
WM_REFRESH = WM_USER + 21
WM_TIMER = 0x0113
TIMER_WATCH = 7

NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 0x1, 0x2, 0x4, 0x10, 0x80
NIIF_USER, NIIF_NOSOUND, NIIF_LARGE_ICON = 0x4, 0x10, 0x20
MF_STRING, MF_GRAYED, MF_SEPARATOR = 0x0, 0x1, 0x800
TPM_RIGHTBUTTON, TPM_BOTTOMALIGN = 0x2, 0x20
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
SW_RESTORE, SW_SHOW = 9, 5

CMD_PREV, CMD_TOGGLE, CMD_NEXT, CMD_SHOW, CMD_QUIT = 1001, 1002, 1003, 1004, 1005

DEFAULT_LABELS = {"prev": "Previous", "play": "Play", "pause": "Pause",
                  "next": "Next", "show": "Show window", "quit": "Quit",
                  "idle": "Nothing is playing"}


def _clip(text: str, size: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) < size else text[:size - 2] + "…"


def promote_icon() -> tuple[bool, bool]:
    """Windows 11 прячет новые значки за стрелку «^». Один раз выводим наш
    значок на панель рядом с часами: ставим IsPromoted=1 в его записи
    HKCU\\Control Panel\\NotifyIconSettings. Если человек уже решил сам
    (значение есть), его выбор не трогаем. Возвращает True, если запись
    найдена, и второе True, если её поменяли сейчас."""
    if not IS_WINDOWS:
        return False, False
    try:
        import winreg
    except ImportError:                                 # pragma: no cover
        return False, False
    exe = os.path.normcase(os.path.abspath(sys.executable))
    root = r"Control Panel\NotifyIconSettings"
    try:
        base = winreg.OpenKey(winreg.HKEY_CURRENT_USER, root)
    except OSError:
        return False, False                             # Windows 10: такого ключа нет
    changed = found = False
    try:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(base, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(base, name, 0,
                                    winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                    path, _ = winreg.QueryValueEx(key, "ExecutablePath")
                    path = os.path.normcase(os.path.abspath(os.path.expandvars(str(path))))
                    if path != exe:
                        continue
                    found = True
                    try:
                        winreg.QueryValueEx(key, "IsPromoted")
                    except OSError:
                        winreg.SetValueEx(key, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        changed = True
            except OSError:
                continue
    finally:
        winreg.CloseKey(base)
    if changed:
        log.info("tray: the icon is moved next to the clock")
    return found, changed


class Tray:
    """Значок в трее. Все методы можно звать из любого потока."""

    def __init__(self, app_name: str, icon_path: str | None,
                 on_action: Callable[[str], None]) -> None:
        self.app_name = app_name
        self.icon_path = icon_path
        self.on_action = on_action
        self.title = ""
        self.artist = ""
        self.playing = False
        self.labels = dict(DEFAULT_LABELS)
        self.notify_wanted = False
        self._hwnd = None
        self._hicon = None
        self._own_icon = False
        self._icon_dirty = False
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._added = False
        self._balloon: tuple[str, str] | None = None
        self._wndproc = None        # держим ссылку, иначе её съест сборщик мусора
        self._taskbar_created = 0
        self.position = 0.0
        self.duration = 0.0
        self._ticks = 0
        self._promoted = False
        self.thumbbar = None
        try:
            from .taskbar import Thumbbar
            self.thumbbar = Thumbbar(on_action) if IS_WINDOWS else None
        except Exception as exc:                        # pragma: no cover
            log.debug("taskbar buttons are off: %s", exc)

    # ------------------------------------------------------------ снаружи
    @property
    def supported(self) -> bool:
        return IS_WINDOWS

    def start(self) -> bool:
        if not IS_WINDOWS or self._thread is not None:
            return False
        self._thread = threading.Thread(target=self._run, name="kryonyx-tray",
                                        daemon=True)
        self._thread.start()
        self._ready.wait(3.0)
        return self._hwnd is not None

    def stop(self) -> None:
        if IS_WINDOWS and self._hwnd:
            try:
                user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            except Exception:                           # pragma: no cover
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def update(self, title: str = "", artist: str = "", playing: bool = False,
               labels: dict | None = None, notify: bool = False,
               position: float = 0.0, duration: float = 0.0) -> None:
        with self._lock:
            self.position = float(position or 0)
            self.duration = float(duration or 0)
            changed = (title or "", artist or "") != (self.title, self.artist)
            self.title = title or ""
            self.artist = artist or ""
            self.playing = bool(playing)
            if labels:
                for key in DEFAULT_LABELS:
                    if labels.get(key):
                        self.labels[key] = str(labels[key])
            # Legacy notify keyword is accepted, but track toasts are disabled.
            self._balloon = None
        if IS_WINDOWS and self._hwnd:
            user32.PostMessageW(self._hwnd, WM_REFRESH, 0, 0)

    def set_icon(self, path: str) -> None:
        """Request a replacement on the tray message thread, not the HTTP thread."""
        with self._lock:
            self.icon_path = path
            self._icon_dirty = True
        if IS_WINDOWS and self._hwnd:
            user32.PostMessageW(self._hwnd, WM_REFRESH, 0, 0)

    def tooltip(self) -> str:
        with self._lock:
            if not self.title:
                return _clip(self.app_name, 128)
            mark = "▶ " if self.playing else "❚❚ "
            line = self.title + (" — " + self.artist if self.artist else "")
            return _clip(mark + line, 128)

    # ------------------------------------------------------------ поток значка
    def _load_icon(self):
        path = self.icon_path
        if path and os.path.isfile(path) and path.lower().endswith(".ico"):
            handle = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0,
                                       LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if handle:
                self._own_icon = True
                return handle
        # Иконка, вшитая в KryonyxMusic.exe (в сборке PyInstaller).
        try:
            handle = shell32.ExtractIconW(None, sys.executable, 0)
            if handle and handle > 1:
                self._own_icon = True
                return handle
        except Exception:
            pass
        return user32.LoadIconW(None, ctypes.c_void_p(32512))   # IDI_APPLICATION

    def _data(self, flags: int) -> "NOTIFYICONDATAW":
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip()
        return nid

    def _add(self) -> None:
        nid = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        self._added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)))
        if self._added:
            nid.uVersion = 4                            # NOTIFYICON_VERSION_4
            shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))

    def _refresh(self) -> None:
        with self._lock:
            dirty, self._icon_dirty = self._icon_dirty, False
        previous, own = None, False
        if dirty:
            previous, own = self._hicon, self._own_icon
            self._own_icon = False
            self._hicon = self._load_icon()
            if not self._hicon:
                self._hicon, self._own_icon = previous, own
                previous = None
        try:
            self._refresh_data()
        finally:
            if previous and own and previous != self._hicon:
                user32.DestroyIcon(previous)

    def _refresh_data(self) -> None:
        if self.thumbbar is not None:
            with self._lock:
                args = (self.playing, dict(self.labels), self.position, self.duration)
            self.thumbbar.update(*args)
        if not self._added:
            self._add()
            return
        nid = self._data(NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        with self._lock:
            balloon, self._balloon = self._balloon, None
        if not shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid)):
            self._added = False
            self._add()

    def _menu(self) -> None:
        with self._lock:
            labels = dict(self.labels)
            title = self.title
            artist = self.artist
            playing = self.playing
        menu = user32.CreatePopupMenu()
        try:
            head = title + (" — " + artist if artist else "") if title else labels["idle"]
            user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, _clip(head, 64))
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_PREV, "⏮  " + labels["prev"])
            user32.AppendMenuW(menu, MF_STRING, CMD_TOGGLE,
                               ("⏸  " + labels["pause"]) if playing
                               else ("▶  " + labels["play"]))
            user32.AppendMenuW(menu, MF_STRING, CMD_NEXT, "⏭  " + labels["next"])
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_SHOW, labels["show"])
            user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, labels["quit"])
            user32.SetMenuDefaultItem(menu, CMD_SHOW, 0)
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            # Без этого меню не закрывается щелчком мимо него.
            user32.SetForegroundWindow(self._hwnd)
            user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
                                  pt.x, pt.y, 0, self._hwnd, None)
            user32.PostMessageW(self._hwnd, 0, 0, 0)     # WM_NULL
        finally:
            user32.DestroyMenu(menu)

    def _fire(self, action: str) -> None:
        # Действие уходит в отдельный поток: evaluate_js ждёт ответа окна,
        # а цикл сообщений значка стоять не должен.
        threading.Thread(target=self._safe_action, args=(action,),
                         daemon=True).start()

    def _safe_action(self, action: str) -> None:
        try:
            self.on_action(action)
        except Exception as exc:                        # pragma: no cover
            log.debug("tray action %s failed: %s", action, exc)

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                event = lparam & 0xFFFF                 # VERSION_4: младшее слово
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._fire("show")
                elif event == WM_CONTEXTMENU:
                    # С NOTIFYICON_VERSION_4 правый щелчок приходит и как
                    # WM_RBUTTONUP, и как WM_CONTEXTMENU — меню открываем раз.
                    self._menu()
                return 0
            if msg == WM_COMMAND:
                cmd = wparam & 0xFFFF
                action = {CMD_PREV: "prev", CMD_TOGGLE: "toggle", CMD_NEXT: "next",
                          CMD_SHOW: "show", CMD_QUIT: "quit"}.get(cmd)
                if action:
                    self._fire(action)
                return 0
            if msg == WM_REFRESH:
                self._refresh()
                return 0
            if msg == WM_TIMER and wparam == TIMER_WATCH:
                self._watch()
                return 0
            if self._taskbar_created and msg == self._taskbar_created:
                # Проводник перезапустился — значок надо добавить заново.
                self._added = False
                self._add()
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                if self._added:
                    nid = self._data(0)
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                    self._added = False
                user32.PostQuitMessage(0)
                return 0
        except Exception as exc:                        # pragma: no cover
            log.debug("tray window proc: %s", exc)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _watch(self) -> None:
        self._ticks += 1
        tb = self.thumbbar
        if tb is not None:
            alive = tb.hwnd and user32.IsWindow(tb.hwnd)
            if not alive or tb.need_readd or not tb._added:
                from .taskbar import find_main_window
                hwnd = find_main_window(exclude=self._hwnd or 0)
                if hwnd and tb.attach(hwnd):
                    self._refresh()
        if not self._promoted and self._ticks in (2, 4, 8, 15, 30):
            self._promoted, changed = promote_icon()
            if changed:
                # Проводник читает настройку при добавлении значка.
                nid = self._data(0)
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                self._added = False
                self._add()

    def _run(self) -> None:                             # pragma: no cover
        try:
            hinst = kernel32.GetModuleHandleW(None)
            self._wndproc = WNDPROC(self._proc)
            cls = WNDCLASSEXW()
            cls.cbSize = ctypes.sizeof(WNDCLASSEXW)
            cls.lpfnWndProc = self._wndproc
            cls.hInstance = hinst
            cls.lpszClassName = "KryonyxMusicTray"
            user32.RegisterClassExW(ctypes.byref(cls))   # повторная регистрация не страшна
            # Обычное (не message-only) скрытое окно: только такие получают
            # широковещательное TaskbarCreated.
            self._hwnd = user32.CreateWindowExW(0, "KryonyxMusicTray", self.app_name,
                                                0, 0, 0, 0, 0, None, None, hinst, None)
            if not self._hwnd:
                log.warning("tray: the helper window was not created (%s)",
                            ctypes.get_last_error())
                return
            self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
            self._hicon = self._load_icon()
            self._add()
            log.info("tray: the icon is %s", "added" if self._added else "NOT added")
            # Раз в 2 с: кнопки на превью окна (окно появляется позже значка
            # и может пересоздаться) и показ значка рядом с часами.
            user32.SetTimer(self._hwnd, TIMER_WATCH, 2000, None)
        except Exception as exc:
            log.warning("tray is not available: %s", exc)
            self._hwnd = None
            return
        finally:
            self._ready.set()
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if self._own_icon and self._hicon:
            user32.DestroyIcon(self._hicon)
        self._hwnd = None
