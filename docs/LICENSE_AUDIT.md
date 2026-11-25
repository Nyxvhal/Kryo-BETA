# License & Rights Audit

This document audits the licensing and redistribution status of Kryo (Kryonyx Music) across source code, runtime dependencies, build-only tools, binaries, media assets, and optional AI/translation models.

> **Scope note:** The root `LICENSE` (MIT) applies **only** to Kryo's own original source code. It does not grant redistribution rights to third-party libraries, binaries, fonts, artwork, avatars, music streams, lyrics, or AI/translation models.

## 1. Source Code

| Component | Path | License | Status |
| --- | --- | --- | --- |
| Kryo Python/JS/CSS/HTML source | `kryonyx/`, `run.py`, `installer/`, `build/` | MIT (`LICENSE`) | Cleared |
| Brand UI SVG paths (49 icons) | `assets/brand-v60/icons.json` | MIT (`LICENSE`) | Cleared (drawn for v60) |
| App logo (`Kryo.png`) | `assets/brand-v60/Kryo.png` | User-supplied | **Review required** (ownership/trademark not independently verified) |

## 2. Python Dependencies (Runtime vs Build-Only)

Declared in `requirements.txt`, `requirements-build.txt`, `requirements-ai.txt`, and `requirements-karaoke*.txt`.
Because `tools/collect_licenses.py` inventories the live build environment (`licenses/build-environment/MANIFEST.json`) and separates `scope: "runtime"` from `scope: "build-only"`, it must be run inside the actual Windows release build environment before distribution.

- **Runtime (`requirements.txt`):** `aiohttp`, `aiohttp-socks`, `yt-dlp`, `ytmusicapi`, `pytubefix`, `imageio-ffmpeg`, `pywebview`, `Pillow`, `shazamio-core` (see `licenses/shazamio-core-LICENSE.txt`), `aiofiles`.
- **Build / QA only (not shipped at runtime):** `pyinstaller`, `pyinstaller-hooks-contrib`, `pefile`, `altgraph`, `pytest`, `playwright`.
- **Optional (not bundled in base installer):** `requirements-ai.txt` (PyTorch/Real-ESRGAN/RIFE), `requirements-karaoke*.txt`, `argostranslate` (user-installed on demand).

## 3. Native Binaries & Runtime Components

| Binary / Runtime | Origin | License / Terms | Status / Action |
| --- | --- | --- | --- |
| `FFmpeg` (via `imageio-ffmpeg`) | `imageio-ffmpeg` wheel (not present in current source-only env) | LGPL-2.1 / GPL-2 / GPL-3 depending on actual `-buildconf` | **Release blocker for binary redistribution** until `tools/collect_licenses.py` captures `-buildconf` from the shipped binary and corresponding-source obligations are fulfilled (or FFmpeg is excluded/user-provided). |
| `yt-dlp.exe` | `build/vendor/yt-dlp.exe` (downloaded during Windows build) | Unlicense + embedded third-party notices | **Review required** on build (verify SHA-256 and `yt-dlp-THIRD-PARTY-NOTICES.txt`). |
| Microsoft Edge WebView2 Runtime | System runtime / Microsoft Evergreen installer | Microsoft proprietary redistribution terms | Not bundled inside Kryo; uses system WebView2 or user download from Microsoft. |

## 4. Fonts, Artwork & Avatars

| Asset Group | Path | Count | Status |
| --- | --- | ---: | --- |
| Bundled fonts | `licenses/fonts/` | See `licenses/fonts/` | Covered by respective font license files in `licenses/fonts/`. |
| Removed avatars | `docs/REMOVED_ASSETS_MANIFEST.md` | 257 removed | Removed from `kryonyx/avatars.json`, `kryonyx/web/img/avatars/`, and `kryonyx/avatar-notices/`. |
| Remaining built-in avatars | `kryonyx/avatars.json` | 233 kept | **Release blocker** for public redistribution of third-party likenesses/brands (`Games`, `Social networks and communities`, etc.): `ARTWORK_RIGHTS.md` explicitly records that redistribution permissions are `not_cleared`. |
| Custom user avatars | `%LOCALAPPDATA%\Kryo\custom-avatars\` | User-provided | Local only; never redistributed by the repo. |

## 5. Offline Translation & AI Models

- **Argos Translate & language packs:** Not bundled in the repository or base installer. Users install them separately; each language model carries its own upstream license/attribution.
- **AI upscaling/interpolation weights:** Not bundled; downloaded on demand with SHA-256 verification.

## 6. Release Blockers Summary

1. **Third-party avatar artwork (`kryonyx/avatars.json` remaining 233 entries):** Rights for third-party game/platform/brand imagery are not cleared for public redistribution (`ARTWORK_RIGHTS.md`).
2. **FFmpeg binary (`imageio-ffmpeg`):** Must run `tools/collect_licenses.py` in the actual Windows build environment to inspect `-buildconf` and satisfy GPL/LGPL corresponding-source obligations if bundled.
3. **Windows build environment verification:** `build/vendor/yt-dlp.exe` and `imageio-ffmpeg` are not present in this source-only workspace; full manifest generation is **NOT VERIFIED** until executed on the Windows build machine.
