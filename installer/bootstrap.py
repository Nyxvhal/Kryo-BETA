"""Plum Wizard frontend; Inno Setup remains the native transactional engine.

No network, analytics, account input or arbitrary command execution in the bridge.
The only programs it starts are the bundled engine, Windows' own tasklist/taskkill
(to find and politely close a running Kryonyx) and the installed Kryonyx itself.

v71: update detection (previous folder, version and options from the engine's
uninstall entry), a free-space check, closing a running Kryonyx before files are
replaced, real progress read from the engine log, specific error messages with
the log one click away, a single-instance guard and a WebView2 download prompt.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
APP_ID = '{8F3D2A61-6C4E-4C9B-9E2A-5B1C7D0A9E11}'
APP_EXE = 'Kryo.exe'
LEGACY_EXE = 'KryonyxMusic.exe'
UNINSTALL_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\' + APP_ID + '_is1'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
WINDOWS = os.name == 'nt'   # the engine and its helpers only exist on Windows
WEBVIEW2_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
SPACE_MARGIN = 64 * 1024 * 1024
# Inno Setup exit codes: https://jrsoftware.org/ishelp/topic_setupexitcodes.htm
EXIT_ERRORS = {1: 'init', 2: 'cancelled', 3: 'fatal', 4: 'fatal', 5: 'locked', 6: 'cancelled', 7: 'prepare', 8: 'reboot'}
# Engine log lines -> wizard phase. Unknown or missing log = indeterminate progress.
LOG_STEPS = (('Shutting down applications', 'close'), ('Starting the installation process', 'copy'),
             ('-- File entry --', 'copy'), ('-- Icon entry --', 'shortcuts'), ('-- Run entry --', 'finish'),
             ('Installation process succeeded', 'finish'))


def _payload() -> dict:
    """Version, file count and size of the packaged app, written by build_windows.ps1."""
    try:
        data = json.loads((ROOT / 'installer' / 'payload.json').read_text(encoding='utf-8-sig'))
        return {key: data[key] for key in ('version', 'files', 'bytes') if key in data}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _engine() -> Path:
    found = sorted((ROOT / 'dist').glob('Kryo-*-engine.exe'))
    return found[-1] if found else ROOT / 'dist' / 'Kryo-1.0.0-engine.exe'


def _same(a, b) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(a))).rstrip('\\/') == os.path.normcase(os.path.abspath(str(b))).rstrip('\\/')
    except (TypeError, ValueError):
        return False


def _existing(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def _folder_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _previous() -> dict | None:
    """The engine's own uninstall entry tells where and which version is installed."""
    if os.name != 'nt':
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            def value(name):
                try:
                    return str(winreg.QueryValueEx(key, name)[0])
                except OSError:
                    return None
            path = (value('InstallLocation') or value('Inno Setup: App Path') or '').strip().rstrip('\\/')
            if not path:
                return None
            return {'path': path, 'version': value('DisplayVersion') or '', 'tasks': value('Inno Setup: Selected Tasks')}
    except OSError:
        return None


def _running() -> bool:
    if os.name != 'nt':
        return False
    for name in (APP_EXE, LEGACY_EXE):
        if _running_name(name):
            return True
    return False


def _running_name(name: str) -> bool:
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq ' + name, '/FO', 'CSV', '/NH'],
                             capture_output=True, timeout=8, creationflags=NO_WINDOW).stdout or b''
    except (OSError, subprocess.SubprocessError):
        return False
    return ('"' + name.lower() + '"').encode() in out.lower()


def _close_running(timeout: float = 20.0) -> bool:
    """Ask Kryonyx to close like its window's close button would (no /F). True once it is gone."""
    if not _running():
        return True
    try:
        for name in (APP_EXE, LEGACY_EXE):
            if _running_name(name):
                subprocess.run(['taskkill', '/IM', name], capture_output=True, timeout=10, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.5)
        if not _running():
            return True
    return False


def _child_env() -> dict:
    """The onefile setup leaks PyInstaller variables; the installed app must start fresh."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('_PYI_', '_MEIPASS'))}
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return env


class Installer:
    # pywebview exposes every public attribute of the js_api object to the page
    # (recursively for objects), so the window, paths and caches stay private.
    def __init__(self):
        self._window = None
        self.state = {'phase': 'ready', 'error': '', 'code': None}
        self.destination = str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Programs' / 'Kryo')
        self._lock = threading.Lock()
        self._pack = _payload()
        self.version = str(self._pack.get('version') or '1.0.0')
        self._prev = _previous()
        if self._prev:
            self.destination = self._prev['path']
        self._previous_size = None
        self._log_path = Path(tempfile.gettempdir()) / ('KryonyxMusic-setup-%d.log' % os.getpid())

    # ---------- read-only information for the wizard
    def info(self):
        legal = {name: (ROOT / name).read_text(encoding='utf-8-sig') for name in ('LICENSE', 'TERMS.md', 'PRIVACY.md', 'THIRD_PARTY_NOTICES.md')}
        previous = tasks = None
        if self._prev:
            previous = {'path': self._prev['path'], 'version': self._prev['version']}
            if self._prev.get('tasks') is not None:
                chosen = {t.strip().lower() for t in self._prev['tasks'].split(',')}
                tasks = {'desktop': 'desktopicon' in chosen, 'autostart': 'autostart' in chosen}
        return {'path': self.destination, 'legal': legal, 'version': self.version,
                'previous': previous, 'tasks': tasks, 'space': self.space(self.destination),
                'running': _running(), 'windows': os.name == 'nt'}

    def space(self, destination=None):
        """Free space on the target drive versus the size of the packaged app."""
        need = self._pack.get('bytes')
        need = int(need) if isinstance(need, (int, float)) and need > 0 else None
        free = None
        try:
            base = _existing(Path(str(destination or self.destination)))
            if base is not None:
                free = int(shutil.disk_usage(str(base)).free)
        except (OSError, ValueError):
            free = None
        if need is not None and self._prev and _same(destination or self.destination, self._prev['path']):
            if self._previous_size is None:
                self._previous_size = _folder_size(self._prev['path'])
            need = max(0, need - self._previous_size)   # an update replaces files in place
        ok = not (need is not None and free is not None and free < need + SPACE_MARGIN)
        return {'need': need, 'free': free, 'ok': ok}

    def running(self):
        return _running()

    def browse(self):
        import webview
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG, directory=self.destination)
        if not result:
            return None
        chosen = Path(str(result[0] if isinstance(result, (list, tuple)) else result))
        return str(self._suggest(chosen))

    def _suggest(self, chosen: Path) -> Path:
        """A picked folder that already holds other files gets its own 'Kryonyx Music' subfolder."""
        try:
            if chosen.name.lower() in ('kryo', 'kryonyx music') or (chosen / APP_EXE).is_file() or (chosen / LEGACY_EXE).is_file() or not any(chosen.iterdir()):
                return chosen
            if self._prev and _same(chosen, self._prev['path']):
                return chosen
        except OSError:
            return chosen
        return chosen / 'Kryo'

    # ---------- installation
    def install(self, destination, desktop, autostart, accepted):
        with self._lock:
            if self.state['phase'] == 'installing':
                return {'ok': False, 'error': 'busy'}
            if accepted is not True:
                return {'ok': False, 'error': 'acceptance'}
            if not WINDOWS:
                return {'ok': False, 'error': 'windows'}
            path = Path(str(destination))
            if not path.is_absolute() or any(c in str(path) for c in '\r\n"') or len(str(path)) > 220:
                return {'ok': False, 'error': 'path'}
            if path.parent == path:
                return {'ok': False, 'error': 'root'}
            try:
                path.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=path):
                    pass
            except OSError:
                return {'ok': False, 'error': 'permission'}
            space = self.space(str(path))
            if not space['ok']:
                return {'ok': False, 'error': 'space', 'need': space['need'], 'free': space['free']}
            self.destination = str(path)
            self.state = {'phase': 'installing', 'error': '', 'code': None, 'step': 'prepare', 'progress': None,
                          'files': 0, 'total': self._total()}
            threading.Thread(target=self._run, args=(bool(desktop), bool(autostart)), daemon=False).start()
            return {'ok': True}

    def _update(self, **values):
        self.state = {**self.state, **values}

    def _total(self) -> int:
        total = self._pack.get('files')
        return int(total) if isinstance(total, (int, float)) and total > 0 else 0

    def _watch(self, stop: threading.Event) -> None:
        """Follow the engine log: file entries give real progress, markers give the phase."""
        total = self._total()
        offset, carry, done = 0, '', 0
        while not stop.wait(0.3):
            try:
                with open(self._log_path, 'rb') as fh:
                    fh.seek(offset)
                    chunk = fh.read()
            except OSError:
                continue
            if not chunk:
                continue
            offset += len(chunk)
            lines = (carry + chunk.decode('utf-8', 'replace')).split('\n')
            carry = lines.pop()
            step = None
            for line in lines:
                for marker, name in LOG_STEPS:
                    if marker in line:
                        step = name
                        done += marker == '-- File entry --'
                        break
            update = {'files': min(done, total) if total else done}
            if step:
                update['step'] = step
            if total:
                update['progress'] = round(min(done / total, 0.99), 4)
            self._update(**update)

    def _run(self, desktop, autostart):
        tasks = ','.join(name for name, enabled in [('desktopicon', desktop), ('autostart', autostart)] if enabled)
        stop, watcher = threading.Event(), None
        try:
            if WINDOWS:
                self._update(step='close')
                if not _close_running():
                    self.state = {'phase': 'error', 'error': 'running', 'code': None}
                    return
                self._update(step='prepare')
                try:
                    self._log_path.unlink()
                except OSError:
                    pass
                watcher = threading.Thread(target=self._watch, args=(stop,), daemon=True)
                watcher.start()
            try:
                result = subprocess.run([str(_engine()), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER',
                                         '/CLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/LOG=' + str(self._log_path),
                                         '/DIR=' + self.destination, '/TASKS=' + tasks], check=False, creationflags=NO_WINDOW)
            finally:
                stop.set()
                if watcher is not None:
                    watcher.join(2)
            code = result.returncode
            log = self._log_path.is_file()
            if code == 0:
                self.state = {'phase': 'done', 'error': '', 'code': 0, 'step': 'finish', 'progress': 1.0,
                              'files': self._total() or self.state.get('files', 0), 'total': self._total(), 'log': log}
            else:
                self.state = {'phase': 'error', 'error': EXIT_ERRORS.get(code, 'engine'), 'code': code, 'log': log}
        except OSError:
            self.state = {'phase': 'error', 'error': 'missing', 'code': None}

    def status(self):
        return dict(self.state)

    def open_log(self):
        """Open this run's engine log (fixed path, no input from the page)."""
        if os.name != 'nt' or not self._log_path.is_file():
            return False
        try:
            os.startfile(str(self._log_path))
            return True
        except OSError:
            return False

    def finish(self, launch=False):
        if self.state['phase'] != 'done':
            return False
        if launch:
            try:
                subprocess.Popen([str(Path(self.destination) / APP_EXE)], cwd=self.destination, env=_child_env())
            except OSError:
                return False
        self._window.destroy()
        return True

    def close(self):
        if self.state['phase'] == 'installing':
            return False
        self._window.destroy()
        return True


def _message(text: str, title: str, flags: int) -> int:
    try:
        import ctypes
        return int(ctypes.windll.user32.MessageBoxW(None, text, title, flags))
    except Exception:
        return 0


def _single_instance() -> bool:
    """Two wizards must never drive the engine at once."""
    if os.name != 'nt':
        return True
    try:
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, 'Local\\KryonyxMusicSetup')
        if not handle:
            return True
        _single_instance.handle = handle          # kept for the life of the process
        return ctypes.get_last_error() != 183      # ERROR_ALREADY_EXISTS
    except Exception:
        return True


def main():
    if not _single_instance():
        _message('Kryo setup is already running.', 'Kryo — Setup', 0x40)
        return 0
    import webview
    api = Installer()
    html = (ROOT / 'installer' / 'wizard.html').read_text(encoding='utf-8')
    api._window = webview.create_window('Kryo — Setup', html=html, js_api=api,
        width=990, height=700, min_size=(850, 620), frameless=True, easy_drag=False,
        background_color='#111111', text_select=True)
    api._window.events.closing += lambda: api.state['phase'] != 'installing'
    try:
        webview.start(gui='edgechromium', private_mode=True)
    except Exception:
        if os.name != 'nt':
            raise
        answer = _message('Setup needs the Microsoft Edge WebView2 Runtime. Open the download page?',
                          'Kryo — WebView2', 0x04 | 0x30)
        if answer == 6:
            try:
                os.startfile(WEBVIEW2_URL)
            except OSError:
                pass
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
