# Kryo (Kryonyx Music)

Local desktop music player with YouTube and SoundCloud playback, queue/wave recommendations, karaoke timing and translation, themes, and local library management.

## Requirements

- Windows 10/11 x64 (or Linux/macOS for running from Python sources)
- Python 3.11–3.13 x64 (3.12 recommended for Windows builds)
- Microsoft Edge WebView2 Runtime (for desktop window mode; `--browser` opens in a standard browser)
- Inno Setup 6 (only for building the Windows installer)

## Quick Start (from source)

```powershell
# Windows
start.bat
# Or directly:
python run.py --browser
```

```bash
# Linux / macOS
bash start.sh
```

## Building on Windows

See [BUILD.md](BUILD.md) for full instructions:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build_windows.ps1
```

## Legal, Privacy, and Asset Rights

- [LICENSE](LICENSE) — MIT License for Kryo source code (excludes third-party libraries, binaries, and media assets).
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — Third-party software and binary notices.
- [ARTWORK_RIGHTS.md](ARTWORK_RIGHTS.md) — Audit status of bundled images, icons, and avatars.
- [PRIVACY.md](PRIVACY.md) — Local data storage and network behavior.
- [TERMS.md](TERMS.md) — Terms of use.
- [SECURITY.md](SECURITY.md) — Security reporting and scope.
