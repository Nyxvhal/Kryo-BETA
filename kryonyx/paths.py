"""Пути приложения: работают одинаково из исходников и из собранного .exe."""

from __future__ import annotations

import getpass
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys


def app_dir() -> str:
    """Папка, рядом с которой лежит приложение (а не _MEIPASS PyInstaller-а)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """Папка с упакованными ресурсами (web/, иконки)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "kryonyx")
    return os.path.dirname(os.path.abspath(__file__))


def web_dir() -> str:
    return os.path.join(resource_dir(), "web")


def _writable(path: str) -> bool:
    """Папку берём только если в неё правда можно писать.

    Бинарник yt-dlp обновляется именно здесь, поэтому политика или
    перенаправленный профиль не должны оставлять приложение без данных.
    """
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _candidates() -> list[str]:
    if os.name == "nt":
        # LOCALAPPDATA — основное место, APPDATA (роуминг) и TEMP — подстраховка
        # на случай урезанных прав или перенаправленной папки профиля.
        roots = [os.getenv("LOCALAPPDATA"), os.getenv("APPDATA"),
                 os.path.join(os.path.expanduser("~"), "AppData", "Local"),
                 os.getenv("TEMP"), os.getenv("TMP")]
        return [os.path.join(r, "Kryo") for r in roots if r]
    if sys.platform == "darwin":
        return [os.path.expanduser("~/Library/Application Support/KryonyxMusic"),
                "/tmp/KryonyxMusic"]
    base = os.getenv("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return [os.path.join(base, "kryonyx-music"),
            os.path.join(os.path.expanduser("~"), ".kryonyx-music"),
            "/tmp/kryonyx-music"]


def _is_linklike(path: str) -> bool:
    """Reject symlinks and Windows reparse points, including on Python 3.11."""
    info = os.lstat(path)
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _snapshot_tree(root: str) -> dict[str, tuple]:
    """Hash files and enumerate directories; reject links and active SQLite journals."""
    if _is_linklike(root):
        raise OSError(f'Linked data root cannot be migrated: {root}')
    result = {}
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=lambda e: (_ for _ in ()).throw(e)):
        for name in sorted(dirs + files):
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, root)
            if _is_linklike(path):
                raise OSError(f'Linked item cannot be migrated: {path}')
            if name in dirs:
                result[rel] = ('directory',)
                continue
            if name.endswith(('-wal', '-journal')) and os.path.getsize(path):
                raise OSError(f'SQLite journal exists: {path}. Close the old player and retry.')
            digest = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    digest.update(chunk)
            result[rel] = ('file', os.path.getsize(path), digest.hexdigest())
    return result


def _migrate_brand_data(legacy: str, destination: str) -> bool:
    """Copy a stable tree to an adjacent temporary dir and publish after verification.

    No overwrite or merge. An error leaves the original and destination untouched.
    Call with every old instance closed; copying is not a cross-process snapshot.
    """
    if not os.path.isdir(legacy) or os.path.exists(destination):
        return False
    import tempfile
    parent = os.path.dirname(destination)
    os.makedirs(parent, exist_ok=True)
    lock = destination + '.migration-lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    stage = None
    try:
        if os.path.exists(destination):
            return False
        before = _snapshot_tree(legacy)
        stage = tempfile.mkdtemp(prefix='.kryo-migration-', dir=parent)
        shutil.copytree(legacy, stage, dirs_exist_ok=True)
        if before != _snapshot_tree(stage) or before != _snapshot_tree(legacy):
            raise OSError('Source changed or verification failed; close the old player and retry.')
        os.rename(stage, destination)
        stage = None
        return True
    finally:
        os.close(fd)
        if stage:
            shutil.rmtree(stage, ignore_errors=True)
        os.unlink(lock)



_data_dir: str | None = None
_device_tag: str | None = None


def _machine_id() -> str:
    """Идентификатор железа. Пусто — не беда, метку соберём из остального."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography",
                 "/v", "MachineGuid"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in out.stdout.splitlines():
                if "MachineGuid" in line:
                    return line.split()[-1]
            return ""
        if sys.platform == "darwin":
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                 capture_output=True, text=True, timeout=5)
            for line in out.stdout.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
            return ""
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    return fh.read().strip()
    except Exception:
        pass
    return ""


def device_tag() -> str:
    """Короткая метка «этот компьютер + этот пользователь».

    Данные каждого запуска лежат в своей папке с такой меткой. Если профиль
    пользователя роуминговый или лежит на сетевом диске, два компьютера всё
    равно не делят одну базу, кэш и настройки: ни один из них не становится
    хостом для другого.
    """
    global _device_tag
    if _device_tag:
        return _device_tag
    env = (os.getenv("KRYONYX_DEVICE_TAG") or "").strip()
    if env:
        _device_tag = "".join(c for c in env if c.isalnum() or c in "-_")[:24] or "local"
        return _device_tag
    try:
        user = getpass.getuser()
    except Exception:
        user = os.getenv("USERNAME") or os.getenv("USER") or "user"
    parts = [platform.node() or "", user or "", _machine_id()]
    _device_tag = hashlib.sha1("|".join(parts).encode("utf-8", "ignore")).hexdigest()[:10]
    return _device_tag


_LEGACY_KEEP = {"devices"}


def _migrate_into_device(base: str, target: str) -> None:
    """Переносит данные прошлых версий из общей папки в папку устройства."""
    try:
        entries = [e for e in os.listdir(base) if e not in _LEGACY_KEEP]
    except OSError:
        return
    if not entries or not any(e == "kryonyx.db" for e in entries):
        return
    for name in entries:
        src = os.path.join(base, name)
        dst = os.path.join(target, name)
        if os.path.exists(dst):
            continue
        try:
            shutil.move(src, dst)
        except Exception:
            pass


def data_dir() -> str:
    """Пользовательские данные: база, кэш, настройки, бинарник yt-dlp.

    В установленной версии программа может лежать в Program Files, куда писать
    нельзя, поэтому данные всегда уходят в профиль пользователя.
    """
    global _data_dir
    if _data_dir:
        return _data_dir

    env = os.getenv("KRYONYX_DATA_DIR")
    if env:
        os.makedirs(env, exist_ok=True)
        _data_dir = env
        return _data_dir

    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        root = os.getenv("LOCALAPPDATA")
        _migrate_brand_data(os.path.join(root, "KryonyxMusic"), os.path.join(root, "Kryo"))

    picked = ""
    for candidate in _candidates():
        if _writable(candidate):
            picked = candidate
            break
    if not picked:
        picked = _candidates()[0]
        os.makedirs(picked, exist_ok=True)

    # Своя папка на каждое устройство и каждого пользователя.
    device = os.path.join(picked, "devices", device_tag())
    if _writable(device):
        _migrate_into_device(picked, device)
        _data_dir = device
    else:
        _data_dir = picked
    return _data_dir


def all_data_dirs() -> list[str]:
    """Все места, где данные могли оказаться в прошлых запусках.

    Нужно для переезда базы: если раньше писать можно было только во
    временную папку, плейлисты не должны пропасть, когда появилось
    нормальное место в профиле.
    """
    seen: list[str] = []
    for base in [os.getenv("KRYONYX_DATA_DIR"), *_candidates()]:
        if not base:
            continue
        for path in (os.path.join(base, "devices", device_tag()), base):
            if path not in seen:
                seen.append(path)
    return seen


def cache_dir() -> str:
    path = os.path.join(data_dir(), "cache")
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------- #
# свои плагины и свои библиотеки
# --------------------------------------------------------------------------- #
def _ensure(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def plugins_dir() -> str:
    """Папка со своими плагинами. Её открывает кнопка в настройках.

    Переопределяется переменной KRYONYX_PLUGINS_DIR: удобно, когда плагины
    лежат в репозитории или на флешке, а не в профиле пользователя.
    """
    env = (os.getenv("KRYONYX_PLUGINS_DIR") or "").strip()
    return _ensure(env or os.path.join(data_dir(), "plugins"))


def libs_dir() -> str:
    """Папка со своими библиотеками Python: её добавляем в sys.path.

    Сюда же ставятся зависимости, если в системе их не оказалось: писать в
    системный Python нельзя (а иногда и некуда), а эта папка своя у каждого
    пользователя и у каждого устройства.
    """
    env = (os.getenv("KRYONYX_LIB_DIR") or "").strip()
    return _ensure(env or os.path.join(data_dir(), "lib"))


def extra_plugin_dirs() -> list[str]:
    """Все места, откуда берём плагины: папка данных и папка рядом с программой.

    Папка рядом с .exe нужна переносному запуску: распаковал архив, положил
    плагин в `plugins/` — и он работает, без лазания по профилю.
    """
    out = [plugins_dir()]
    portable = os.path.join(app_dir(), "plugins")
    if os.path.isdir(portable) and portable not in out:
        out.append(portable)
    return out


def extra_lib_dirs() -> list[str]:
    out = [libs_dir()]
    portable = os.path.join(app_dir(), "lib")
    if os.path.isdir(portable) and portable not in out:
        out.append(portable)
    return out
