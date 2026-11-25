"""
main.py — точка входа десктопного приложения.

Сервер (aiohttp) поднимается в фоновом потоке, окно pywebview открывается
в главном потоке — это жёсткое требование самой библиотеки.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time

from . import APP_NAME, VERSION_LABEL, __version__
from .paths import app_dir, data_dir, libs_dir, plugins_dir, resource_dir

log = logging.getLogger("kryonyx")


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.FileHandler(
        os.path.join(data_dir(), "kryonyx.log"), encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    # Живая лента для экрана «Логи» в настройках.
    from . import logs
    logs.install()
    log.info("%s %s is starting", APP_NAME, __version__)


def _icon_path() -> str | None:
    """Файл иконки.

    Первой идёт аватарка, выбранная в настройках: она лежит в папке данных
    и переживает обновление приложения. Дальше — иконка рядом с .exe и
    упакованные ресурсы.
    """
    try:
        from . import avatars
        avatars.refresh_active_icon()
    except Exception as exc:
        log.debug("bundled icon refresh skipped: %s", exc)
    for candidate in (os.path.join(data_dir(), "icon.ico"),
                      os.path.join(app_dir(), "icon.ico"),
                      os.path.join(resource_dir(), "web", "favicon.ico"),
                      os.path.join(resource_dir(), "web", "icon.png")):
        if os.path.isfile(candidate):
            return candidate
    return None


def _windows_identity() -> None:
    """Своя запись в панели задач: Windows берёт для неё иконку приложения,
    а не иконку хост-процесса Python/WebView2."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Kryonyx.Music.Player.2")
    except Exception as exc:                            # pragma: no cover
        log.debug("AppUserModelID not set: %s", exc)


_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}


def _loopback(host: str) -> str:
    """Любой внешний адрес молча превращаем в локальный."""
    value = (host or "").strip().lower()
    if value in _LOOPBACK:
        return "::1" if value in ("::1", "0:0:0:0:0:0:0:1") else "127.0.0.1"
    if value not in ("", "127.0.0.1"):
        log.warning("адрес %r недоступен: плеер слушает только этот компьютер", host)
    return "127.0.0.1"


def _serve(ready: threading.Event, state: dict, host: str, port: int) -> None:
    from . import server

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    state["loop"] = loop

    async def _boot() -> None:
        state["runner"], state["port"] = await server.start(host, port)
        ready.set()

    try:
        loop.run_until_complete(_boot())
        loop.run_forever()
    except Exception as exc:  # pragma: no cover
        state["error"] = exc
        ready.set()
    finally:
        runner = state.get("runner")
        if runner is not None:
            loop.run_until_complete(runner.cleanup())
        loop.close()


# Меньше окно делать нельзя: ниже этого интерфейс начинает ломаться.
MIN_WIDTH = 400
MIN_HEIGHT = 560
DEF_WIDTH = 1360
DEF_HEIGHT = 860


def _win_state_path() -> str:
    return os.path.join(data_dir(), "window.json")


def _load_win_state() -> dict:
    """Размер и положение окна с прошлого запуска.

    `remember` по умолчанию включён — так же, как в настройках интерфейса
    (`winRemember`). Если значения расходятся, страница на каждом запуске
    шлёт в окно лишний запрос; лишние запросы на старте нам не нужны.
    """
    try:
        with open(_win_state_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {"remember": True}
        data.setdefault("remember", True)
        return data
    except (OSError, ValueError):
        return {"remember": True}


def _save_win_state(data: dict) -> None:
    try:
        with open(_win_state_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle)
    except OSError as exc:                              # pragma: no cover
        log.debug("the window state was not saved: %s", exc)


# Свёрнутое окно Windows «стоит» в точке (-32000, -32000). Если приложение
# закрыли из панели задач, в window.json уезжали именно эти координаты —
# и в следующий раз окно открывалось за пределами всех экранов: значок в
# панели есть, окна нет, нажатия никуда не приходят.
OFFSCREEN = -30000


def _sane_place(saved: dict) -> tuple[int | None, int | None]:
    """Координаты из прошлого запуска — только если они правдоподобны."""
    try:
        x, y = int(saved.get("x")), int(saved.get("y"))
    except (TypeError, ValueError):
        return None, None
    if x <= OFFSCREEN or y <= OFFSCREEN:
        log.warning("the saved window position %s,%s is off-screen and is ignored", x, y)
        return None, None
    return x, y


def _boot_flag() -> str:
    return os.path.join(data_dir(), "boot.flag")


def _boot_failed_before() -> bool:
    """Прошлый запуск не доложил, что интерфейс поднялся.

    Маркер ставится перед открытием окна и снимается, когда страница
    сообщает «я загрузилась». Если он остался — приложение в прошлый раз
    повисло или его закрыли принудительно, и следующий запуск идёт в
    облегчённом режиме.
    """
    return os.path.isfile(_boot_flag())


def _boot_mark() -> None:
    try:
        with open(_boot_flag(), "w", encoding="utf-8") as handle:
            handle.write(str(int(time.time())))
    except OSError:                                     # pragma: no cover
        pass


def _boot_clear() -> None:
    try:
        os.remove(_boot_flag())
    except OSError:
        pass


def _num(value) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number and 0 <= number < 10 ** 7 else 0.0


def _drag_delta(value) -> float:
    """A pointer delta in CSS pixels: finite, bounded, fractions kept.

    WebView2 reports pointer positions in fractions of a pixel on scaled
    displays (0.67 px per device pixel at 150 %). Truncating them to int
    turned a slow drag into a stream of zeros — the mini player stood still.
    """
    try:
        number = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return max(-4096.0, min(4096.0, number))


def _carry(rest: float, delta: float, scale: float) -> tuple[int, float]:
    """Whole device pixels to move now and the fraction kept for the next step."""
    total = rest + delta * scale
    whole = int(round(total))
    return whole, total - whole


class DesktopApi:
    """Мостик из JS в окно приложения.

    Окно у нас без системной рамки, поэтому заголовок, кнопки и растягивание
    за края живут в самом интерфейсе и ходят сюда.
    """

    def __init__(self) -> None:
        self._window = None
        self._fullscreen = False
        self._maximized = False
        self._on_top = False
        self._state = _load_win_state()
        # Последние известные границы окна. Их присылают сами события
        # `moved` и `resized`, поэтому спрашивать окно (а это обращение в
        # поток интерфейса) при каждом движении мыши не нужно.
        self._box = {"x": int(self._state.get("x") or 0),
                     "y": int(self._state.get("y") or 0),
                     "width": int(self._state.get("width") or DEF_WIDTH),
                     "height": int(self._state.get("height") or DEF_HEIGHT)}
        self._box_live = False
        self._export_lock = threading.Lock()
        self._lock = threading.Lock()
        self._flush: threading.Timer | None = None

    def bind(self, window) -> None:
        self._window = window

    def save_export(self, spec):
        """Non-audio exports always use the native Save As dialog. Never fall back."""
        if self._window is None:
            return {"error": "Desktop window is unavailable"}
        if not self._export_lock.acquire(blocking=False):
            return {"error": "Another save dialog is already open"}
        try:
            import webview
            from . import file_exports
            data, suggested, extension = file_exports.prepare(spec, self._base_url)
            selected = self._window.create_file_dialog(
                (webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG),
                save_filename=suggested, file_types=(f'Export (*{extension})',))
            if not selected:
                return {"cancelled": True}
            destination = str(selected[0] if isinstance(selected, (list, tuple)) else selected)
            if not destination.lower().endswith(extension):
                destination += extension
            file_exports.write_atomic(destination, data)
            return {"saved": True, "path": destination}
        except Exception as exc:
            log.warning("File export failed: %s", exc)
            return {"error": "Could not save the file. Check the source and destination."}
        finally:
            self._export_lock.release()

    def save_shared_audio(self, token):
        """Only an already prepared, unexpired capability; native Save As only."""
        if self._window is None:return {"error":"Desktop window is unavailable"}
        if not self._export_lock.acquire(blocking=False):return {"error":"Another save dialog is already open"}
        try:
            import webview
            from .audio_share import completed
            from .clip_export import copy_atomic
            source,name=completed(token)
            selected=self._window.create_file_dialog((webview.FileDialog.SAVE if hasattr(webview,'FileDialog') else webview.SAVE_DIALOG),save_filename=name,file_types=('Audio (*.mp3)',))
            if not selected:return {"cancelled":True}
            destination=str(selected[0] if isinstance(selected,(list,tuple)) else selected)
            if not destination.lower().endswith('.mp3'):destination+='.mp3'
            copy_atomic(source,destination)
            return {"saved":True,"path":destination}
        except Exception:
            return {"error":"Could not save the audio file"}
        finally:self._export_lock.release()

    def save_clip(self, session_id):
        """Show the native Save As dialog, then copy a complete original losslessly."""
        if self._window is None:
            return {"error": "Desktop window is unavailable"}
        try:
            from . import clipstream
            from .clip_export import completed_clip, copy_atomic
            import webview
            source, suggested = completed_clip(clipstream.root(), session_id)
            selected = self._window.create_file_dialog(
                (webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG), save_filename=suggested,
                file_types=('Video (*.mp4;*.webm)', 'All files (*.*)'))
            if not selected:
                return {"cancelled": True}
            destination = selected[0] if isinstance(selected, (list, tuple)) else selected
            copy_atomic(source, destination)
            return {"saved": True}
        except Exception as exc:
            log.warning("Clip export failed: %s", exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------ трей
    _tray = None
    _minimized = False

    def attach_tray(self, tray) -> None:
        self._tray = tray
        from . import avatars
        avatars.set_live_icon_callback(tray.set_icon)

    def now_playing(self, info=None) -> bool:
        """Что играет — для значка в трее и заголовка окна.

        JS присылает {title, artist, playing, labels}. Обновляем трей
        без всплывающих уведомлений о смене трека.
        """
        info = info if isinstance(info, dict) else {}
        title = str(info.get("title") or "")[:200]
        artist = str(info.get("artist") or "")[:200]
        playing = bool(info.get("playing"))
        if self._tray is not None:
            self._tray.update(title, artist, playing,
                              labels=info.get("labels") if isinstance(info.get("labels"), dict) else None,
                              notify=False,
                              position=_num(info.get("position")),
                              duration=_num(info.get("duration")))
        # Заголовок окна виден в превью на панели задач и в Alt+Tab.
        if self._window is not None:
            label = f"{title} — {artist}" if title and artist else title
            caption = f"{label} · {APP_NAME}" if label else f"{APP_NAME} {VERSION_LABEL}"
            if caption != getattr(self, "_caption", None):
                self._caption = caption
                try:
                    self._window.set_title(caption)
                except Exception as exc:                # pragma: no cover
                    log.debug("set_title failed: %s", exc)
        return True

    def note_minimized(self, state: bool) -> None:
        self._minimized = bool(state)

    def show_window(self) -> None:
        """Развернуть и вывести окно наверх (из трея)."""
        hwnd = 0
        try:
            from .taskbar import find_main_window
            tray_hwnd = getattr(self._tray, "_hwnd", 0) or 0
            hwnd = find_main_window(exclude=tray_hwnd)
        except Exception:                               # pragma: no cover
            hwnd = 0
        hwnd = hwnd or self._hwnd()
        if hwnd:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                if user32.IsIconic(ctypes.c_void_p(hwnd)):
                    user32.ShowWindow(ctypes.c_void_p(hwnd), 9)     # SW_RESTORE
                else:
                    user32.ShowWindow(ctypes.c_void_p(hwnd), 5)     # SW_SHOW
                user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
                self._minimized = False
                return
            except Exception as exc:                    # pragma: no cover
                log.debug("native restore failed: %s", exc)
        if self._window is not None:
            try:
                self._window.show()
                self._window.restore()
            except Exception as exc:                    # pragma: no cover
                log.debug("restore failed: %s", exc)
        self._minimized = False

    def tray_action(self, action: str) -> None:
        """Команда из меню значка в трее."""
        if action == "show":
            self.show_window()
            return
        if action == "quit":
            self.close()
            return
        if action in ("prev", "next", "toggle") and self._window is not None:
            self._window.evaluate_js(
                "window.KTray && window.KTray.act(%r)" % action)

    def toggle_fullscreen(self) -> bool:
        if self._window is not None:
            self._window.toggle_fullscreen()
            self._fullscreen = not self._fullscreen
        return self._fullscreen

    def minimize(self) -> bool:
        if self._window is not None:
            self._window.minimize()
        return True

    def toggle_maximize(self) -> bool:
        """Разворот на весь экран и обратно. Возвращает новое состояние."""
        if self._window is None:
            return self._maximized
        try:
            if self._maximized:
                self._window.restore()
            else:
                self._window.maximize()
        except Exception as exc:                        # pragma: no cover
            log.debug("the window did not change its state: %s", exc)
            return self._maximized
        self._maximized = not self._maximized
        self._remember()
        return self._maximized

    def maximized(self) -> bool:
        return self._maximized

    def close(self) -> bool:
        """Своя кнопка закрытия вместо системной."""
        self.mini_close()
        if self._window is not None:
            self._window.destroy()
        return True

    def bounds(self) -> dict:
        """Где окно стоит и какого размера — нужно для растягивания за края.

        Обращение к окну обслуживает поток интерфейса, поэтому любая
        осечка здесь не должна лететь наружу: вызывающий код в JS получит
        последние известные границы и продолжит работать.
        """
        if self._window is None:
            return dict(self._box)
        try:
            box = {"x": int(self._window.x), "y": int(self._window.y),
                   "width": int(self._window.width), "height": int(self._window.height)}
        except Exception as exc:                        # pragma: no cover
            log.debug("the window did not report its bounds: %s", exc)
            return dict(self._box)
        self._box = box
        self._box_live = True
        return dict(box)

    # ------------------------------------------------- события окна
    # Их шлёт сам pywebview при каждом движении и растягивании — десятки раз
    # в секунду. Раньше на каждое такое событие мы опрашивали окно (четыре
    # обращения в поток интерфейса) и писали файл. Во время перетаскивания
    # очередь этих обращений росла быстрее, чем поток интерфейса успевал её
    # разбирать, — окно переставало отвечать, и Windows показывал
    # «Kryo не отвечает». Теперь координаты берём прямо из события,
    # а запись на диск откладываем.
    def note_move(self, x=None, y=None) -> None:
        if x is None or y is None:
            return
        try:
            self._box["x"], self._box["y"] = int(x), int(y)
            self._box_live = True
        except (TypeError, ValueError):
            return
        self._remember()

    def note_resize(self, width=None, height=None) -> None:
        if width is None or height is None:
            return
        try:
            self._box["width"], self._box["height"] = int(width), int(height)
            self._box_live = True
        except (TypeError, ValueError):
            return
        self._remember()

    def set_bounds(self, x: int, y: int, width: int, height: int) -> dict:
        """Ставит окно в заданные границы. Меньше минимума не пускаем —
        иначе край, за который тянут, «перепрыгивает» противоположный."""
        if self._window is None:
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        width = max(MIN_WIDTH, int(width))
        height = max(MIN_HEIGHT, int(height))
        try:
            self._window.resize(width, height)
            self._window.move(int(x), int(y))
        except Exception as exc:                            # pragma: no cover
            log.debug("the window did not accept the new bounds: %s", exc)
        self._maximized = False
        self._remember()
        return {"x": int(x), "y": int(y), "width": width, "height": height}

    # ----------------------------------------------------------------- экран
    def screen(self) -> dict:
        """Рабочая область экрана: по ней интерфейс раскладывает окно по
        половинам и четвертям. Если pywebview про экраны не знает, отдаём
        размеры самого окна — привязка тогда просто не предлагается."""
        try:
            import webview
            screens = list(getattr(webview, "screens", []) or [])
        except Exception:                               # pragma: no cover
            screens = []
        if screens:
            best = screens[0]
            if self._window is not None and len(screens) > 1:
                # Окно могло уехать на второй монитор — берём тот, в котором
                # находится его середина.
                box = self.bounds()
                cx = box["x"] + box["width"] // 2
                cy = box["y"] + box["height"] // 2
                for item in screens:
                    sx, sy = int(getattr(item, "x", 0)), int(getattr(item, "y", 0))
                    sw, sh = int(item.width), int(item.height)
                    if sx <= cx < sx + sw and sy <= cy < sy + sh:
                        best = item
                        break
            return {"x": int(getattr(best, "x", 0)), "y": int(getattr(best, "y", 0)),
                    "width": int(best.width), "height": int(best.height), "real": True}
        box = self.bounds()
        return {"x": 0, "y": 0, "width": box["width"] or DEF_WIDTH,
                "height": box["height"] or DEF_HEIGHT, "real": False}

    def set_on_top(self, state: bool) -> bool:
        """«Поверх всех окон»: удобно, когда плеер стоит рядом с работой.

        Напрямую через pywebview это делать нельзя. Его winforms-бэкенд
        выполняет `set_on_top` как `form.TopMost = ...`, без `Invoke`, —
        а вызовы из JS идут в отдельном потоке (`js_bridge_call`). Свойство
        формы, выставленное не из потока интерфейса, трогает стиль окна и
        может пересоздать его хэндл: окно перестаёт разбирать сообщения, и
        Windows показывает «Kryo не отвечает».

        Поэтому тот же эффект делаем сами — `SetWindowPos` с
        HWND_TOPMOST/HWND_NOTOPMOST. Эта функция потокобезопасна: она
        отправляет сообщение в поток окна, а не правит его объект мимо него.
        """
        self._on_top = bool(state)
        if self._window is None:
            return self._on_top
        if self._native_on_top(self._on_top):
            return self._on_top
        try:
            self._window.on_top = self._on_top
        except Exception as exc:                        # pragma: no cover
            log.debug("on_top is not supported: %s", exc)
        return self._on_top

    def _hwnd(self) -> int:
        """Хэндл окна: нужен для вызовов Win32 в обход pywebview."""
        if os.name != "nt" or self._window is None:
            return 0
        try:
            native = getattr(self._window, "native", None)
            handle = getattr(native, "Handle", None)
            if handle is not None:
                return int(handle.ToInt64())
        except Exception as exc:                        # pragma: no cover
            log.debug("the window handle is not available: %s", exc)
        return 0

    def _native_on_top(self, state: bool) -> bool:
        hwnd = self._hwnd()
        if not hwnd:
            return False
        try:
            import ctypes
            HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
            SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
            return bool(ctypes.windll.user32.SetWindowPos(
                ctypes.c_void_p(hwnd),
                ctypes.c_void_p(HWND_TOPMOST if state else HWND_NOTOPMOST),
                0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE))
        except Exception as exc:                        # pragma: no cover
            log.debug("SetWindowPos did not work: %s", exc)
            return False

    def set_remember(self, state: bool) -> bool:
        """Запоминать размер и положение окна между запусками."""
        self._state["remember"] = bool(state)
        if state:
            box = self.bounds()
            if box["width"]:
                self._state.update(box)
        _save_win_state(self._state)
        return bool(state)

    def _remember(self) -> None:
        """Откладывает запись окна на диск: не чаще раза в секунду и всегда
        в стороннем потоке, чтобы интерфейс не ждал файловую систему."""
        if not self._state.get("remember"):
            return
        with self._lock:
            if self._flush is not None:
                return
            self._flush = threading.Timer(1.0, self._write_state)
            self._flush.daemon = True
            self._flush.start()

    def _write_state(self) -> None:
        with self._lock:
            self._flush = None
        box = dict(self._box) if self._box_live else self.bounds()
        if not box.get("width"):
            return
        # Свёрнутое окно отдаёт (-32000, -32000) — такое запоминать нельзя.
        if box.get("x", 0) <= OFFSCREEN or box.get("y", 0) <= OFFSCREEN:
            return
        self._state.update(box)
        self._state["maximized"] = self._maximized
        _save_win_state(self._state)

    def flush_state(self) -> None:
        """Последняя запись перед закрытием окна."""
        with self._lock:
            timer, self._flush = self._flush, None
        if timer is not None:
            timer.cancel()
        if self._state.get("remember"):
            self._write_state()

    # ------------------------------------------------------- мини-плеер
    # Маленькое окно поверх всех окон: обложка, название и кнопки
    # «назад / играть-пауза / дальше». Отдельное окно pywebview со своим
    # мостиком (MiniApi), чтобы его JS не мог закрыть или двигать главное.
    _mini = None
    _mini_state: dict = {}
    _base_url = ""
    # Перетаскивание мини-плеера: когда пришёл прошлый шаг, дробный остаток
    # в пикселях устройства и (не Windows) точная позиция на время жеста.
    _mini_drag_at = 0.0
    _mini_rest = (0.0, 0.0)
    _mini_pos = None
    MINI_W, MINI_H = 420, 180

    def _mini_hwnd(self) -> int:
        """Support pywebview Handle wrappers and integer handles without mutating a Form."""
        mini = self._mini
        if os.name != "nt" or mini is None:
            return 0
        native = getattr(mini, "native", None)
        for target in (native, mini):
            for key in ("Handle", "handle", "hwnd", "window_handle"):
                try:
                    handle = getattr(target, key, None)
                    value = int(handle.ToInt64()) if hasattr(handle, "ToInt64") else int(handle or 0)
                    if value:
                        return value
                except (TypeError, ValueError, AttributeError):
                    pass
        # Some backends expose their native handle only after WebView initialization.
        # Only use a title match owned by this process; never pin another app's window.
        try:
            import ctypes
            from ctypes import wintypes
            user = ctypes.windll.user32
            user.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
            user.FindWindowW.restype = wintypes.HWND
            user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
            hwnd = user.FindWindowW(None, f"{APP_NAME} · mini")
            pid = wintypes.DWORD()
            if hwnd:
                user.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
                if pid.value == os.getpid():
                    return int(hwnd)
        except Exception as exc:                         # pragma: no cover
            log.debug("mini handle unavailable: %s", exc)
        return 0

    def _mini_toolwindow(self, hwnd: int) -> bool:
        """Hide only the mini window from Windows Alt+Tab and the taskbar.

        Preserve all other extended styles. Return True only when the style
        changed; pinning remains functional if a backend rejects the change.
        """
        try:
            import ctypes
            from ctypes import wintypes
            user = ctypes.windll.user32
            get_style, set_style = user.GetWindowLongW, user.SetWindowLongW
            get_style.argtypes = (wintypes.HWND, ctypes.c_int)
            get_style.restype = ctypes.c_long
            set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
            set_style.restype = ctypes.c_long
            handle = ctypes.c_void_p(hwnd)
            style = get_style(handle, -20) & 0xffffffff  # GWL_EXSTYLE
            if not style:  # a topmost window has WS_EX_TOPMOST; do not overwrite on read failure
                return False
            desired = (style | 0x00000080) & ~0x00040000  # TOOLWINDOW, not APPWINDOW
            if desired == style:
                return False
            set_style(handle, -20, ctypes.c_int32(desired).value)
            actual = get_style(handle, -20) & 0xffffffff
            return actual == desired
        except Exception as exc:
            log.debug("mini tool-window style unavailable: %s", exc)
            return False

    def _pin_mini(self, force: bool = False) -> bool:
        """Reassert native topmost after shown/loaded/resize and state heartbeats.

        Windows may recreate a frameless WebView handle. on_top=True at creation
        alone does not protect the replacement. No WinForms property writes from
        the JS bridge thread; SetWindowPos is the only native mutation here.
        """
        if os.name != "nt" or self._mini is None:
            return False
        now = time.monotonic()
        if not force and now - getattr(self, "_mini_pin_at", 0) < 1:
            return True
        hwnd = self._mini_hwnd()
        if not hwnd:
            return False
        try:
            import ctypes
            from ctypes import wintypes
            user = ctypes.windll.user32
            user.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_uint)
            user.SetWindowPos.restype = wintypes.BOOL
            # ASYNCWINDOWPOS avoids waiting on an active resize's UI message loop.
            flags = 0x0001 | 0x0002 | 0x0010 | 0x4000
            if self._mini_toolwindow(hwnd):
                flags |= 0x0020  # SWP_FRAMECHANGED applies the extended style
            ok = bool(user.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(-1),
                                        0, 0, 0, 0, flags))
            if ok:
                self._mini_pin_at = now
            else:
                log.debug("mini topmost SetWindowPos failed")
            return ok
        except Exception as exc:                         # pragma: no cover
            log.debug("mini topmost failed: %s", exc)
            return False

    def _native_move_mini(self, dx: float, dy: float) -> bool:
        """Windows: move the mini window in device pixels.

        pywebview's `x`/`move()` pair can't do relative moves: 5.x reads `x`
        in physical pixels but scales the argument of `move()` once more (the
        window jumped away on 125–150 % displays), 6.x truncates both ways.
        GetWindowRect/SetWindowPos work in the window's own coordinates, the
        DPI scale comes from the window and the sub-pixel rest is carried to
        the next step. SetWindowPos is thread-safe; no WinForms property is
        touched from the bridge thread.
        """
        if os.name != "nt" or self._mini is None:
            return False
        hwnd = self._mini_hwnd()
        if not hwnd:
            return False
        try:
            import ctypes
            from ctypes import wintypes
            user = ctypes.windll.user32
            user.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
            user.GetWindowRect.restype = wintypes.BOOL
            rect = wintypes.RECT()
            if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False
            scale = 1.0
            try:
                user.GetDpiForWindow.argtypes = (wintypes.HWND,)
                user.GetDpiForWindow.restype = wintypes.UINT
                dpi = int(user.GetDpiForWindow(hwnd))
                if 48 <= dpi <= 960:
                    scale = dpi / 96.0
            except (AttributeError, OSError):            # Windows 8.1 and older
                pass
            step_x, rest_x = _carry(self._mini_rest[0], dx, scale)
            step_y, rest_y = _carry(self._mini_rest[1], dy, scale)
            self._mini_rest = (rest_x, rest_y)
            if not step_x and not step_y:
                return True
            user.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_uint)
            user.SetWindowPos.restype = wintypes.BOOL
            # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE: topmost stays as it is.
            return bool(user.SetWindowPos(hwnd, None, rect.left + step_x, rect.top + step_y,
                                          0, 0, 0x0001 | 0x0004 | 0x0010))
        except Exception as exc:                         # pragma: no cover
            log.debug("native mini move failed: %s", exc)
            return False

    def mini_open(self) -> bool:
        if self._mini is not None:
            self._pin_mini(force=True)
            return True
        try:
            import webview
        except ImportError:                             # pragma: no cover
            return False
        x, y = self._state.get("mini_x"), self._state.get("mini_y")
        if x is None or y is None:
            scr = self.screen()
            x = scr["x"] + scr["width"] - self.MINI_W - 24
            y = scr["y"] + scr["height"] - self.MINI_H - 72
        try:
            mini = webview.create_window(
                title=f"{APP_NAME} · mini",
                url=f"{self._base_url}/mini.html",
                width=max(360,int(self._state.get("mini_w") or self.MINI_W)),
                height=max(128,int(self._state.get("mini_h") or self.MINI_H)),
                x=int(x), y=int(y),
                # Окошко растягивается за края: мелким — для угла экрана,
                # крупным — с большой обложкой.
                resizable=True, min_size=(360, 128), frameless=True, easy_drag=False,
                on_top=True, focus=False,
                background_color="#000000",
                js_api=MiniApi(self),
            )
        except Exception as exc:                        # pragma: no cover
            log.warning("the mini player did not open: %s", exc)
            return False
        self._mini = mini

        def closed(*_):
            if self._mini is mini:
                self._mini = None
                # Окошко закрыли его же крестиком — выключаем настройку.
                self._eval_main("window.MiniPlayer && MiniPlayer.closed()")

        def moved(*args):
            if len(args) >= 2:
                try:
                    self._state["mini_x"], self._state["mini_y"] = int(args[0]), int(args[1])
                except (TypeError, ValueError):
                    return
                if self._state["mini_x"] > OFFSCREEN and self._state["mini_y"] > OFFSCREEN:
                    _save_win_state(self._state)

        def resized(*args):
            if len(args) >= 2:
                try:
                    w, h = int(args[0]), int(args[1])
                except (TypeError, ValueError):
                    return
                if w >= 300 and h >= 110:
                    self._state["mini_w"], self._state["mini_h"] = w, h
                    _save_win_state(self._state)

        def shown(*_):
            self._pin_mini(force=True)

        try:
            mini.events.closed += closed
            mini.events.moved += moved
            mini.events.resized += resized
            mini.events.shown += shown
            mini.events.loaded += shown
        except Exception as exc:                        # pragma: no cover
            log.debug("mini window events are not available: %s", exc)
        return True

    def mini_close(self) -> bool:
        mini, self._mini = self._mini, None
        self._mini_pin_at = 0
        if mini is not None:
            try:
                mini.destroy()
            except Exception as exc:                    # pragma: no cover
                log.debug("the mini player did not close: %s", exc)
        return True

    def mini_update(self, state=None) -> bool:
        """Главное окно присылает, что играет; передаём в мини-плеер."""
        if not isinstance(state, dict):
            return False
        self._mini_state = state
        self._pin_mini()
        mini = self._mini
        if mini is None:
            return True
        payload = json.dumps(state, ensure_ascii=False)

        def push() -> None:
            try:
                mini.evaluate_js(f"window.Mini && Mini.update({payload})")
            except Exception as exc:                    # pragma: no cover
                log.debug("mini update failed: %s", exc)
        # Не держим поток мостика главного окна, пока ответит второе окно.
        threading.Thread(target=push, name="kryonyx-mini", daemon=True).start()
        return True

    def _eval_main(self, code: str) -> None:
        window = self._window
        if window is None:
            return

        def run() -> None:
            try:
                window.evaluate_js(code)
            except Exception as exc:                    # pragma: no cover
                log.debug("main window eval failed: %s", exc)
        threading.Thread(target=run, name="kryonyx-mini-cmd", daemon=True).start()

    def info(self) -> dict:
        return {"version": __version__, "version_label": VERSION_LABEL, "platform": sys.platform,
                "data_dir": data_dir(), "app_dir": app_dir(), "desktop": True,
                "frameless": True, "maximized": self._maximized,
                "on_top": self._on_top,
                "remember": bool(self._state.get("remember")),
                "min_width": MIN_WIDTH, "min_height": MIN_HEIGHT}


class MiniApi:
    """Мостик окна мини-плеера: только управление воспроизведением."""

    def __init__(self, desk: DesktopApi) -> None:
        self._desk = desk

    def state(self) -> dict:
        self._desk._pin_mini()
        return dict(self._desk._mini_state or {})

    def action(self, name: str) -> bool:
        if name in ("prev", "next", "toggle"):
            self._desk._eval_main("window.KTray && window.KTray.act(%s)" % json.dumps(name))
            return True
        if name in ("lyrics", "queue"):
            self._desk.show_window()
            self._desk._eval_main("window.MiniPlayer && MiniPlayer.action(%s)" % json.dumps(name))
            return True
        if name == "show":
            self._desk.show_window()
            self._desk._eval_main("window.MiniPlayer && MiniPlayer.closed()")
            self._desk.mini_close()
            return True
        return False

    def seek(self, fraction) -> bool:
        value = _num(fraction)
        value = min(1.0, max(0.0, value))
        self._desk._eval_main("window.MiniPlayer && MiniPlayer.seek(%r)" % value)
        return True

    def volume(self, value) -> bool:
        value = min(100.0, max(0.0, _num(value)))
        self._desk._eval_main("window.MiniPlayer && MiniPlayer.volume(%r)" % value)
        return True

    def move_by(self, dx, dy) -> bool:
        """Move only this mini window by a pointer delta (CSS pixels).

        v73: `mini.move(int(mini.x) + dx, ...)` did not survive display
        scaling — see `_drag_delta` and `DesktopApi._native_move_mini`.
        Windows moves the window itself in device pixels; elsewhere an exact
        float position is kept for the duration of one drag gesture.
        """
        desk = self._desk
        mini = desk._mini
        if mini is None:
            return False
        dx, dy = _drag_delta(dx), _drag_delta(dy)
        now = time.monotonic()
        if now - float(getattr(desk, "_mini_drag_at", 0.0) or 0.0) > 1.0:
            # A new gesture: forget the rest of the previous one.
            desk._mini_rest = (0.0, 0.0)
            desk._mini_pos = None
        desk._mini_drag_at = now
        if not dx and not dy:
            return True
        native = getattr(desk, "_native_move_mini", None)
        if callable(native) and native(dx, dy):
            pin = getattr(desk, "_pin_mini", None)
            if callable(pin):
                pin()                                    # throttled to once a second
            return True
        try:
            if getattr(desk, "_mini_pos", None) is None:
                desk._mini_pos = [float(mini.x), float(mini.y)]
            desk._mini_pos[0] += dx
            desk._mini_pos[1] += dy
            mini.move(int(round(desk._mini_pos[0])), int(round(desk._mini_pos[1])))
            desk._pin_mini(force=True)
            return True
        except Exception as exc:
            log.debug("mini move failed: %s", exc)
            return False

    def resize(self, width, height) -> dict:
        """Растягивание окошка за свой уголок: у окна без рамки системных краёв нет."""
        mini = self._desk._mini
        w = max(360, min(1400, int(_num(width) or 0)))
        h = max(128, min(900, int(_num(height) or 0)))
        if mini is not None:
            try:
                mini.resize(w, h)
                self._desk._pin_mini(force=True)
            except Exception as exc:                    # pragma: no cover
                log.debug("mini resize failed: %s", exc)
        return {"width": w, "height": h}

    def size(self) -> dict:
        mini = self._desk._mini
        try:
            return {"width": int(mini.width), "height": int(mini.height)}
        except Exception:                               # pragma: no cover
            return {"width": 0, "height": 0}

    def close(self) -> bool:
        self._desk.mini_close()
        self._desk._eval_main("window.MiniPlayer && MiniPlayer.closed()")
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kryonyx", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--port", type=int, default=int(os.getenv("KRYONYX_PORT", "8765")))
    parser.add_argument("--host", default="127.0.0.1",
                        help="только адрес этого компьютера (127.0.0.1 / ::1)")
    parser.add_argument("--browser", action="store_true", help="открыть в браузере, без окна")
    parser.add_argument("--server-only", action="store_true",
                        help="только сервер, без окна (интерфейс в браузере этого же ПК)")
    parser.add_argument("--lan", action="store_true",
                        help="устарело: раздача по сети убрана, плеер всегда локальный")
    parser.add_argument("--safe", action="store_true",
                        help="облегчённый режим: без атмосферы, обоев, рисовки и анимаций")
    parser.add_argument("--doctor", action="store_true",
                        help="проверить, всё ли готово на этом устройстве, и выйти")
    parser.add_argument("--no-deps", action="store_true",
                        help="не доустанавливать зависимости в свою папку библиотек")
    args = parser.parse_args(argv)

    # Сначала окружение: свои библиотеки в sys.path, недостающие зависимости —
    # в папку пользователя. Без этого шага плеер поднимался только там, где
    # зависимости уже стояли в системном Python.
    from . import bootstrap
    env = bootstrap.ensure(auto=not args.no_deps)

    if args.doctor:
        from . import doctor
        print(doctor.text())
        return 0 if doctor.report()["state"] != "fail" else 1

    if env["missing"]:
        print("Kryo не может запуститься без этих библиотек: "
              + ", ".join(env["missing"]))
        print("Подробности и способ исправить: Kryo.exe --doctor")
        return 1

    _setup_logging()
    _windows_identity()
    # ffmpeg можно просто положить рядом с приложением.
    os.environ["PATH"] = app_dir() + os.pathsep + os.environ.get("PATH", "")

    # Плеер работает только для того устройства, которое его запустило:
    # слушаем исключительно loopback. Один компьютер больше не может стать
    # хостом для остальных — на каждом свой экземпляр и свои данные.
    host = _loopback(args.host)
    if args.lan:
        log.warning("--lan больше не поддерживается: плеер слушает только %s. "
                    "Запустите Kryo на том устройстве, где слушаете.", host)
    ready = threading.Event()
    state: dict = {}
    thread = threading.Thread(target=_serve, args=(ready, state, host, args.port), daemon=True)
    thread.start()

    if not ready.wait(timeout=30):
        log.warning("the server did not answer within 30 s, continuing")
    if state.get("error"):
        log.error("the server did not start: %s", state["error"])
        return 1

    port = state.get("port", args.port)
    # Прошлый запуск не доложил, что интерфейс поднялся: значит, окно
    # повисло и его закрыли силой. Второй раз наступать на те же грабли
    # незачем — поднимаемся в облегчённом режиме.
    recovered = _boot_failed_before()
    safe = bool(args.safe or recovered)
    if recovered:
        log.warning("the previous run did not finish loading — starting in safe mode")
    url = f"http://127.0.0.1:{port}" + ("/?safe=1" if safe else "")
    log.info("%s %s — %s", APP_NAME, __version__, url)
    log.info("[local] данные: %s", data_dir())
    log.info("[local] свои плагины: %s", plugins_dir())
    log.info("[local] свои библиотеки: %s", libs_dir())
    for absent in env.get("optional_missing", []):
        log.warning("[local] нет %s — %s", absent["spec"], absent["why"])

    if args.server_only:
        print(f"{APP_NAME} доступен по адресу {url}")
        print("Это адрес только для этого компьютера: с других устройств "
              "плеер намеренно недоступен.")
        try:
            # 0.2 s: the native shell's /api/shell/quit ends the server
            # thread, and the process should follow without a pause.
            while thread.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        return 0

    if not args.browser:
        try:
            import webview
        except ImportError:
            webview = None
        if webview is not None:
            api = DesktopApi()
            api._base_url = f"http://127.0.0.1:{port}"
            # Размер с прошлого запуска, если человек попросил его запоминать.
            saved = _load_win_state()
            win_w, win_h = DEF_WIDTH, DEF_HEIGHT
            win_x = win_y = None
            if saved.get("remember") and int(saved.get("width") or 0) >= MIN_WIDTH:
                win_w = max(MIN_WIDTH, int(saved["width"]))
                win_h = max(MIN_HEIGHT, int(saved.get("height") or DEF_HEIGHT))
                win_x, win_y = _sane_place(saved)
            window = webview.create_window(
                title=f"{APP_NAME} {VERSION_LABEL}",
                url=url,
                width=win_w,
                height=win_h,
                x=win_x,
                y=win_y,
                min_size=(MIN_WIDTH, MIN_HEIGHT),
                resizable=True,
                # Системный заголовок убран: своя полоса с названием и
                # кнопками рисуется в интерфейсе и живёт в одной теме с ним.
                frameless=True,
                # Таскать окно можно только за эту полосу. Со включённым
                # easy_drag окно уезжало от любого движения мышью по списку.
                easy_drag=False,
                background_color="#000000",
                js_api=api,
            )
            api.bind(window)
            # Значок в трее: что играет и управление плеером (только Windows).
            tray = None
            try:
                from .tray import Tray
                tray = Tray(APP_NAME, _icon_path(), api.tray_action)
                if tray.supported:
                    api.attach_tray(tray)
                    # Свой поток с циклом сообщений: окну он не мешает.
                    threading.Thread(target=tray.start, name="kryonyx-tray-boot",
                                     daemon=True).start()
                else:
                    tray = None
            except Exception as exc:                    # pragma: no cover
                log.warning("tray is not available: %s", exc)
                tray = None
            # Маркер снимает сама страница запросом POST /api/boot/ok.
            _boot_mark()
            log.info("[boot] the window is created: %dx%d at %s,%s, frameless, safe=%s",
                     win_w, win_h, win_x, win_y, safe)
            # Сторож запуска: если страница за 20 с не доложила о загрузке,
            # это видно в журнале (Настройки → Логи и kryonyx.log).
            def _watchdog() -> None:
                if _boot_failed_before():
                    log.error("[boot] the interface did not report within 20 s — "
                              "the window is probably frozen; try "
                              "Kryo.exe --browser or --safe")
                else:
                    log.info("[boot] the interface is up")
            timer = threading.Timer(20.0, _watchdog)
            timer.daemon = True
            timer.start()
            if saved.get("remember") and saved.get("maximized"):
                api._state["maximized"] = True
            # Положение запоминаем в момент закрытия: во время перетаскивания
            # окна JS об этом не знает, а сюда события приходят всегда.
            try:
                window.events.closing += lambda *_: api.flush_state()
                # Мини-плеер не должен держать приложение живым без главного окна.
                window.events.closing += lambda *_: api.mini_close()
                window.events.resized += lambda *args: api.note_resize(*args[:2])
                window.events.moved += lambda *args: api.note_move(*args[:2])
                if hasattr(window.events, "minimized"):
                    window.events.minimized += lambda *_: api.note_minimized(True)
                if hasattr(window.events, "restored"):
                    window.events.restored += lambda *_: api.note_minimized(False)
            except Exception as exc:                    # pragma: no cover
                log.debug("window events are not available: %s", exc)
            icon = _icon_path()
            log.info("[boot] the window icon: %s", icon)
            log.info("[boot] handing control to pywebview")
            try:
                webview.start(debug=bool(os.getenv("KRYONYX_DEBUG")),
                              icon=icon) if icon else webview.start(
                                  debug=bool(os.getenv("KRYONYX_DEBUG")))
            except TypeError:
                # Старые сборки pywebview про icon= не знают.
                webview.start(debug=bool(os.getenv("KRYONYX_DEBUG")))
            _boot_clear()
            if tray is not None:
                tray.stop()
            _shutdown(state, thread)
            return 0

    import webbrowser

    # Браузер живёт сам по себе: если окно pywebview не открывается или
    # висит, этот путь остаётся рабочим (Kryo.exe --browser).
    _boot_clear()
    webbrowser.open(url)
    try:
        while thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    _shutdown(state, thread)
    return 0


def _shutdown(state: dict, thread: threading.Thread) -> None:
    loop = state.get("loop")
    if loop is not None:
        loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
