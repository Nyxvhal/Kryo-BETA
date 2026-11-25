# Build Kryo on Windows

This source package does not contain a ready-made EXE. Native build/install testing requires Windows; Linux Chromium tests do not prove that a Windows installer works.

## Build

Double-click `Build-Windows.cmd`, or run this in the extracted project directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build_windows.ps1
```

Use Windows 10/11 x64, internet access, Python 3.11–3.13 x64 (prefer 3.12), Inno Setup 6 and Microsoft Edge WebView2 Runtime. When possible, `winget` installs missing Python 3.12 and Inno Setup; installation may require Windows consent. Without winget, install them from their official distributors first. Do not disable TLS or Windows security requirements.

The build checks critical command exit codes, prepares runtime assets, downloads yt-dlp, collects license information, runs PyInstaller, builds the native Inno engine, then packages the custom setup wizard. The installer wizard is English-only. Install scope is the current user.

The version comes from `kryonyx/__init__.py` and is passed to Inno (`/DAppVersion=…`), so the app, the engine and the setup file names always agree. The build also writes `build/payload.json` (file count and size of the packaged app); the wizard uses it for real installation progress and a free-space check. Without it (for example when the wizard is opened from sources) progress stays indeterminate and only free space is shown.

Setup behaviour since v71: an existing installation is detected from the engine's uninstall entry (folder, version and chosen options are prefilled, the button becomes “Update”); a running Kryo or legacy Kryonyx is asked to close before files are replaced (Restart Manager is the backstop); the previous `_internal` runtime folder is removed before copying so stale modules never mix with new ones; shortcuts for options switched off are removed; engine exit codes map to specific messages and the engine log can be opened from the wizard. Personal data in `%LOCALAPPDATA%\KryonyxMusic` is never touched by an update.

Optional AI module since v72 (Real-ESRGAN upscaling, RIFE smooth motion): it is **not** part of the build. The installer copies `setup-ai.bat` and `requirements-ai.txt` next to the app; the player's “Install AI module” button (or `setup-ai.bat auto|cpu|cu118|cu126|cu128` in the program folder) creates `.ai-venv` there with Python 3.10–3.12 and PyTorch (about 3 GB with CUDA; nothing is installed system-wide). The worker sources (`kryonyx/ai_worker.py`, `ai_arch.py`) ship as plain files in `_internal/ai_worker` so that interpreter can import them. Model weights (2.5–67 MB each) are downloaded by the player on first use over HTTPS and accepted only with the published size and SHA-256. A powerful PC is required: an NVIDIA GPU with 6 GB of video memory or more is recommended; on the processor it works but is very slow (a clip can take hours). Uninstall removes `.ai-venv`.

## Outputs

| Path | Purpose |
| --- | --- |
| `dist/Kryo/Kryo.exe` | App; keep the entire adjacent folder, including `_internal` |
| `dist/Kryo-1.0.0-setup.exe` | User-facing installer |
| `dist/Kryo-1.0.0-engine.exe` | Internal installation payload |
| `build/payload.json` | Size/file-count manifest bundled into the setup (generated) |
| `licenses/build-environment/MANIFEST.json` | Actual build dependency versions and notices |

The script removes old build output in `dist` and `build/work`, not personal data in `%LOCALAPPDATA%\Kryo` or the retained legacy `%LOCALAPPDATA%\KryonyxMusic`. Back up personal data with the app closed. No signing certificate is configured; SmartScreen behavior is untested.

## Troubleshooting

- Missing Python: install Python 3.12 x64, reopen PowerShell and retry.
- Incompatible virtual environment: delete only the project's `.venv`, then rebuild.
- Missing Inno: install Inno Setup 6 or set `$env:ISCC` to the actual `ISCC.exe` path.
- No window: install/update WebView2 Runtime; test the sources with `python run.py --browser`. The setup itself offers to open the WebView2 download page when the runtime is missing.
- Setup reports “files are in use”: close Kryo from the tray icon (Exit) and press Update again; “Open installation log” shows the engine log for this run.
- Download failure: verify network access and the provider error. Do not interpret partial files as a successful build.
- Old taskbar icon: Windows caches icons. Restart the app/Explorer; `ie4uinit.exe -show` may refresh cached icons.
- AI module: “Install AI module” opens `setup-ai.bat` in its own console. If it fails, install Python 3.10–3.12 from python.org (tick “Add python.exe to PATH”) and run it again; older NVIDIA drivers: `setup-ai.bat cu118`; no NVIDIA GPU: `setup-ai.bat cpu`. Then press “Check again” in the player.
- Do not rename the app EXE independently or copy it without its bundled runtime folder.

## Test and release

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

JavaScript/browser tests are under `tests`. They need Playwright and Chromium plus a local fixture server. These QA dependencies are not needed by end users. Browser tests use fixture metadata, generated audio and mocked services where documented; they are not proof of all live external sources.

Optional karaoke engines/models use separate `requirements-karaoke*.txt` files. A successful base app build does not mean those models are installed. Acoustic recognition uses the declared `shazamio-core` wheel. Asset preparation and rights checks remain necessary: hiding character previews does not remove images from the package.

Read [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before redistribution. Preserve exact dependency manifests and binary hashes. Network-installed dependencies are not fully pinned, so builds are not bit-for-bit reproducible. Review all license inventory `reviewRequired` flags and actual FFmpeg licensing/corresponding-source obligations.

On first start, the old data directory is copied into `%LOCALAPPDATA%\Kryo` only if that destination does not already exist; close all old player instances first. The original is retained. See CHANGES.md for failure handling and limitations.
