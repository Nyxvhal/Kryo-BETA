"""Кнопки плеера в превью окна на панели задач Windows.

Наведите мышь на значок Kryonyx Music в панели задач: под миниатюрой окна
появятся «Предыдущий», «Играть/Пауза» и «Следующий» (как у Spotify и AIMP),
а сама кнопка на панели задач показывает ход трека полоской прогресса.

Работает через ITaskbarList3 на чистом ctypes. Нажатия на кнопки Windows
шлёт окну приложения как WM_COMMAND/THBN_CLICKED, поэтому окно
перехватывается (subclass) — все остальные сообщения уходят ему же.
Все вызовы COM делаются из потока значка в трее (tray.py).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Callable

log = logging.getLogger("kryonyx.taskbar")

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:                                          # pragma: no cover
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)
    ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class THUMBBUTTON(ctypes.Structure):
        _fields_ = [("dwMask", wintypes.DWORD), ("iId", wintypes.UINT),
                    ("iBitmap", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 260), ("dwFlags", wintypes.DWORD)]

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    user32.EnumWindows.argtypes = [ENUMPROC, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                       wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = LRESULT
    _set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _set_long.restype = ctypes.c_void_p
    _get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
    _get_long.restype = ctypes.c_void_p
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                  ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p,
                                       wintypes.DWORD, ctypes.POINTER(GUID),
                                       ctypes.POINTER(ctypes.c_void_p)]
    ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]

WM_COMMAND = 0x0111
WM_NCDESTROY = 0x0082
THBN_CLICKED = 0x1800
GWLP_WNDPROC = -4
GW_OWNER = 4
THB_ICON, THB_TOOLTIP, THB_FLAGS = 0x2, 0x4, 0x8
THBF_ENABLED = 0x0
TBPF_NOPROGRESS, TBPF_NORMAL, TBPF_PAUSED = 0x0, 0x2, 0x8
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10

BTN_PREV, BTN_TOGGLE, BTN_NEXT = 41, 42, 43
CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
IID_ITaskbarList3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"


def _media_dir() -> str:
    from .paths import resource_dir
    for base in (os.path.join(resource_dir(), "icons", "media"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "media")):
        if os.path.isdir(base):
            return base
    return ""


def find_main_window(exclude: int = 0) -> int:
    """Главное окно нашего процесса: видимое окно верхнего уровня WinForms.

    Хэндл берём через EnumWindows, а не через window.native.Handle: свойство
    .NET из чужого потока трогать нельзя."""
    if not IS_WINDOWS:
        return 0
    pid = kernel32.GetCurrentProcessId()
    found: list[tuple[int, int]] = []

    def _each(hwnd, _):
        try:
            if hwnd == exclude or not user32.IsWindowVisible(hwnd):
                return True
            # Auxiliary tool windows must never be restored as the main player.
            # In particular the strip can be larger than a minimized WinForms rect.
            if int(_get_long(hwnd, -20) or 0) & 0x80:  # WS_EX_TOOLWINDOW
                return True
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value != pid or user32.GetWindow(hwnd, GW_OWNER):
                return True
            name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, name, 256)
            box = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(box))
            area = max(0, box.right - box.left) * max(0, box.bottom - box.top)
            bonus = 10 ** 9 if name.value.startswith("WindowsForms") else 0
            if user32.IsIconic(hwnd): bonus += 10 ** 10
            found.append((area + bonus, int(hwnd)))
        except Exception:
            pass
        return True

    user32.EnumWindows(ENUMPROC(_each), 0)
    return max(found)[1] if found else 0


class Thumbbar:
    """Кнопки под миниатюрой окна и прогресс на кнопке панели задач."""

    def __init__(self, on_action: Callable[[str], None]) -> None:
        self.on_action = on_action
        self.hwnd = 0
        self._list = None
        self._old_proc = None
        self._new_proc = None
        self._added = False
        self._icons: dict[str, int] = {}
        self._playing = False
        self._labels = {"prev": "Previous", "play": "Play", "pause": "Pause",
                        "next": "Next"}
        self._button_created = 0
        self.need_readd = False

    # ------------------------------------------------------------ COM
    def _vcall(self, index: int, restype, argtypes, *args):
        vtbl = ctypes.cast(self._list, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return proto(vtbl[index])(self._list, *args)

    def _init_com(self) -> bool:
        if self._list:
            return True
        ole32.CoInitializeEx(None, 0x2)                 # COINIT_APARTMENTTHREADED
        clsid, iid = GUID(), GUID()
        ole32.CLSIDFromString(CLSID_TaskbarList, ctypes.byref(clsid))
        ole32.CLSIDFromString(IID_ITaskbarList3, ctypes.byref(iid))
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 0x1 | 0x4,
                                    ctypes.byref(iid), ctypes.byref(ptr))
        if hr != 0 or not ptr.value:
            log.info("taskbar: ITaskbarList3 is not available (hr=%#x)", hr & 0xFFFFFFFF)
            return False
        self._list = ptr
        self._vcall(3, ctypes.c_long, [])               # HrInit
        return True

    def _icon(self, name: str) -> int:
        if name not in self._icons:
            path = os.path.join(_media_dir(), name + ".ico")
            size = user32.GetSystemMetrics(49) or 16    # SM_CXSMICON
            handle = user32.LoadImageW(None, path, IMAGE_ICON, size, size,
                                       LR_LOADFROMFILE) if os.path.isfile(path) else 0
            self._icons[name] = handle or 0
        return self._icons[name]

    def _buttons(self):
        arr = (THUMBBUTTON * 3)()
        spec = [(BTN_PREV, "prev", self._labels["prev"]),
                (BTN_TOGGLE, "pause" if self._playing else "play",
                 self._labels["pause"] if self._playing else self._labels["play"]),
                (BTN_NEXT, "next", self._labels["next"])]
        for slot, (bid, icon, tip) in zip(arr, spec):
            slot.dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
            slot.iId = bid
            slot.hIcon = self._icon(icon)
            slot.szTip = tip[:259]
            slot.dwFlags = THBF_ENABLED
        return arr

    # ------------------------------------------------------------ окно
    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_COMMAND and (wparam >> 16) & 0xFFFF == THBN_CLICKED:
                action = {BTN_PREV: "prev", BTN_TOGGLE: "toggle",
                          BTN_NEXT: "next"}.get(wparam & 0xFFFF)
                if action:
                    threading.Thread(target=self._safe, args=(action,), daemon=True).start()
                    return 0
            elif self._button_created and msg == self._button_created:
                # Проводник перезапустился: кнопки надо поставить заново.
                self._added = False
                self.need_readd = True
            elif msg == WM_NCDESTROY:
                old = self._old_proc
                self._old_proc = None
                self.hwnd = 0
                self._added = False
                if old:
                    _set_long(hwnd, GWLP_WNDPROC, old)
                    return user32.CallWindowProcW(old, hwnd, msg, wparam, lparam)
        except Exception as exc:                        # pragma: no cover
            log.debug("taskbar proc: %s", exc)
        return user32.CallWindowProcW(self._old_proc, hwnd, msg, wparam, lparam)

    def _safe(self, action: str) -> None:
        try:
            self.on_action(action)
        except Exception as exc:                        # pragma: no cover
            log.debug("taskbar action %s failed: %s", action, exc)

    def attach(self, hwnd: int) -> bool:
        """Поставить кнопки на окно. Зовётся из потока трея, можно повторно."""
        if not IS_WINDOWS or not hwnd:
            return False
        try:
            if not self._init_com():
                return False
            if hwnd != self.hwnd:
                self.hwnd = hwnd
                self._added = False
                self._button_created = user32.RegisterWindowMessageW("TaskbarButtonCreated")
                self._new_proc = WNDPROC(self._proc)
                # Старую процедуру запоминаем до подмены: сообщения окну идут
                # из потока интерфейса, и первое может прийти сразу.
                self._old_proc = _get_long(hwnd, GWLP_WNDPROC)
                if not self._old_proc:
                    self.hwnd = 0
                    return False
                old = _set_long(hwnd, GWLP_WNDPROC,
                                ctypes.cast(self._new_proc, ctypes.c_void_p))
                if not old:
                    log.info("taskbar: the window could not be subclassed (%s)",
                             ctypes.get_last_error())
                    self.hwnd = 0
                    return False
                self._old_proc = old
            if not self._added:
                arr = self._buttons()
                hr = self._vcall(15, ctypes.c_long,
                                 [wintypes.HWND, wintypes.UINT, ctypes.POINTER(THUMBBUTTON)],
                                 hwnd, 3, arr)
                self._added = hr == 0
                log.info("taskbar: thumbnail buttons %s (hr=%#x)",
                         "added" if self._added else "NOT added", hr & 0xFFFFFFFF)
            self.need_readd = False
            return self._added
        except Exception as exc:
            log.warning("taskbar buttons are not available: %s", exc)
            return False

    def update(self, playing: bool, labels: dict | None = None,
               position: float = 0.0, duration: float = 0.0) -> None:
        if not IS_WINDOWS or not self.hwnd or not self._list:
            return
        if labels:
            for key in self._labels:
                if labels.get(key):
                    self._labels[key] = str(labels[key])
        self._playing = bool(playing)
        try:
            if self._added:
                arr = self._buttons()
                self._vcall(16, ctypes.c_long,
                            [wintypes.HWND, wintypes.UINT, ctypes.POINTER(THUMBBUTTON)],
                            self.hwnd, 3, arr)
            # Полоска хода трека на самой кнопке панели задач.
            if duration and duration > 0:
                done = max(0, min(int(position * 1000), int(duration * 1000)))
                self._vcall(10, ctypes.c_long, [wintypes.HWND, ctypes.c_int],
                            self.hwnd, TBPF_NORMAL if playing else TBPF_PAUSED)
                self._vcall(9, ctypes.c_long,
                            [wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong],
                            self.hwnd, done, int(duration * 1000))
            else:
                self._vcall(10, ctypes.c_long, [wintypes.HWND, ctypes.c_int],
                            self.hwnd, TBPF_NOPROGRESS)
        except Exception as exc:                        # pragma: no cover
            log.debug("taskbar update failed: %s", exc)
