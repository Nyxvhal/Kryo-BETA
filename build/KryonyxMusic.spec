# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: onedir build (fast start-up, convenient for the installer)."""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(SPEC)), ".."))
sys.path.insert(0,ROOT)
from tools.prepare_assets_v20 import prepare
ASSETS, ASSET_REPORT = prepare()
ICON = os.path.join(ROOT, "build", "icon.ico")
VERSION_FILE = os.path.join(ROOT, "build", "version_info.txt")
YTDLP_EXE = os.path.join(ROOT, "build", "vendor", "yt-dlp.exe")
if not os.path.isfile(YTDLP_EXE):
    raise RuntimeError("build/vendor/yt-dlp.exe is missing; run build_windows.ps1")

hidden = (
    # YouTube goes through ytmusicapi + Piped/Invidious, but yt-dlp stays
    # the fallback path for stream URLs.
    collect_submodules("yt_dlp.extractor.youtube")
    + collect_submodules("yt_dlp.extractor.soundcloud")
    + collect_submodules("yt_dlp.extractor.bandcamp")
    + collect_submodules("yt_dlp.extractor.mixcloud")
    + ["yt_dlp.extractor.common", "yt_dlp.extractor.lazy_extractors",
       "ytmusicapi", "requests", "pytubefix", "aiohttp_socks", "python_socks", "imageio_ffmpeg", "aiofiles", "shazamio_core"]
    + collect_submodules("shazamio_core")
    + ["PIL.PngImagePlugin", "PIL.JpegImagePlugin", "PIL.WebPImagePlugin", "PIL.IcoImagePlugin"]
    + collect_submodules("ytmusicapi")
    + collect_submodules("pytubefix")
    + collect_submodules("aiohttp_socks")
    + collect_submodules("python_socks")
    + ["webview.platforms.edgechromium", "webview.platforms.winforms",
       "aiohttp", "sqlite3", "kryonyx.tray", "kryonyx.taskbar"]
)

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    # A fresh standalone binary ships next to the app, so YouTube works
    # right away on the user's PC even if GitHub is unreachable.
    binaries=[(YTDLP_EXE, ".")] + collect_dynamic_libs("shazamio_core"),
    datas=collect_data_files("imageio_ffmpeg") + [
           (os.path.join(ROOT, "licenses"), "licenses"),
           *[(os.path.join(ROOT, name), ".") for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "PRIVACY.md", "TERMS.md", "ARTWORK_RIGHTS.md")],
           (str(ASSETS / "web"), os.path.join("kryonyx", "web")),
           # Minimal startup/media icons; other avatar ICOs are generated locally.
           (str(ASSETS / "icons"), os.path.join("kryonyx", "icons")),
           (os.path.join(ROOT, "kryonyx", "avatars.json"), "kryonyx"),
           (os.path.join(ROOT, "kryonyx", "argos_worker.py"), "kryonyx"),
           (os.path.join(ROOT, "kryonyx", "avatar-notices"), "kryonyx/avatar-notices"),
           # v72: the optional AI worker runs in its own Python (.ai-venv), so it ships
           # as plain source files that that interpreter can import.
           *[(os.path.join(ROOT, "kryonyx", name), os.path.join("ai_worker", "kryonyx"))
             for name in ("__init__.py", "ai_worker.py", "ai_arch.py")]]
    + collect_data_files("ytmusicapi"),
    hiddenimports=hidden,
    # Heavy packages the player does not need.
    excludes=["tkinter", "matplotlib", "numpy", "pytest", "setuptools",
              "pandas", "scipy", "test", "unittest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Kryo",
    console=False,
    # The icon is required: without it Windows shows the default one.
    icon=ICON,
    # File properties (name, version, publisher) also hint Explorer to re-read
    # the .exe resources instead of using a cached icon.
    version=VERSION_FILE if os.path.exists(VERSION_FILE) else None,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    # UPX compresses the resource section and Explorer stops finding the icon
    # (that is why the .exe used to keep an old icon). The installer compresses
    # everything anyway (lzma2/max), so the size does not suffer.
    upx=False,
    name="Kryo",
)
