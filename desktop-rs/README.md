# kryonyx-shell — optional native window in Rust (v73)

`kryonyx-shell` is a small Rust program that opens the Kryo window
itself (tao + wry: WebView2 on Windows, WebKitGTK on Linux, WKWebView on macOS)
and runs the existing **Python backend** as a child process:

```
kryonyx-shell.exe ──starts──▶ Kryo.exe --server-only   (or: python run.py --server-only)
      │                              │
      │  native window, splash,      │  search, streaming, library, karaoke, AI,
      │  mini player, Save As,       │  settings, files — unchanged
      │  window state                │
      └──── http://127.0.0.1:PORT ◀──┘
```

**What it is not:** a Rust rewrite of the player. Search, playback sources,
the library, karaoke and the AI module stay in Python (`kryonyx/`). The shell
replaces only the pywebview window layer, so the interface (`kryonyx/web`) runs
unchanged: the shell provides the same `window.pywebview.api` that frame.js,
mini.js, tray.js and the Save As code already use.

The pywebview window remains the default. The shell is optional and can be
tried side by side.

## Layout

| Path | What |
| --- | --- |
| `src/main.rs` | windows, web views, event loop, mini player, Save As dialog |
| `src/platform.rs` | monitor work area, opening links in the browser, config folder |
| `src/splash.html` | start screen: progress, the backend's last log line, error view with Retry |
| `core/` | everything without a window, tested on any OS: |
| `core/src/sidecar.rs` | finds and starts the backend, waits for it, stops it cleanly |
| `core/src/bridge.rs` | the injected `window.pywebview` script and its message format |
| `core/src/cli.rs`, `http.rs`, `winstate.rs` | command line, loopback HTTP client, window state file |

## Build

Windows (recommended; MSVC toolchain, WebView2 runtime — preinstalled on Windows 10/11):

```
cd desktop-rs
cargo build --release
copy target\release\kryonyx-shell.exe <folder with Kryo.exe or run.py>
```

Linux: install the WebKitGTK 4.1 and GTK 3 development packages
(`libwebkit2gtk-4.1-dev libgtk-3-dev` on Debian/Ubuntu), then `cargo build --release`.

Tests that need no window system (backend start/stop, bridge, command line, state file):

```
cargo test -p kryonyx-shell-core
cargo run -p kryonyx-shell-core --example backend_e2e -- .. /tmp/out   # starts the real backend
```

The bridge script is also exercised in Chromium against the real interface:
`node tests/browser_v73.cjs` with `ONLY=shell` (see that file).

## Run

Put `kryonyx-shell.exe` next to `Kryo.exe` (or anywhere inside a
source checkout with `run.py`) and start it. Options:

```
--backend PATH   Kryo executable or run.py to start
--python PATH    Python for a source checkout (default: .venv, py -3, python3)
--app-dir DIR    folder with run.py and kryonyx/
--port N         first port to try (default 8765)
--safe           light mode
--url URL        attach to an already running backend (development)
--devtools       inspector, context menus and browser hotkeys
```

How the two halves trust each other: the shell creates a random token for every
launch and passes it to the backend in `KRYONYX_SHELL_TOKEN`. The backend's
`/api/shell/*` endpoints (hello, save-plan, save, quit) answer only to that
token, and the token never reaches web pages. The window API is injected only
into the backend's own `http://127.0.0.1:PORT` page; links to other sites open
in the system browser. On Windows the backend runs inside a job object, so it
cannot outlive the shell even after a crash. On close the shell asks the
backend to stop (`/api/shell/quit`), so jobs and the database close cleanly.

If the backend does not come up, the splash shows the error with its last log
lines and a Retry button; the same text is written to
`%LOCALAPPDATA%\KryonyxMusic\shell\backend-failure.log` (Linux:
`~/.config/kryonyx-music/shell/`, macOS: `~/Library/Application Support/KryonyxMusic/shell/`).
The windowed release build has no console, so this file is the report to send.

## Not ported yet

- tray icon and its menu (the pywebview build has one); closing the window quits
- taskbar thumbnail buttons (prev / play / next)
- the exe icon resource (the window and taskbar icon are set at run time)
- single-instance handoff (a second shell starts a second backend on the next port)

## Status

`cargo check`/`clippy` pass for `x86_64-pc-windows-msvc`; a Windows build was
also linked by cross-compilation (`x86_64-pc-windows-gnu`, zig). The core tests
and the end-to-end backend test pass on Linux; the bridge passes the browser
test. It has not been run on a real Windows desktop in this environment yet —
please report what you see.
