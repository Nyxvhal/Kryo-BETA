// No console window behind the player in release builds on Windows.
#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "windows")]
//! Kryo — optional native shell (v73).
//!
//! What this program is: a native window (tao + wry: WebView2 on Windows,
//! WebKitGTK on Linux, WKWebView on macOS) around the existing Python
//! backend. It starts `Kryo.exe --server-only` or
//! `python run.py --server-only` as a child process, waits until it answers
//! and shows the same interface the pywebview window shows. The window bridge
//! (`window.pywebview.api`) is reimplemented here, so frame.js, mini.js,
//! tray.js and the Save As code work unchanged.
//!
//! What it is not: a Rust rewrite of the backend. Search, streaming, library,
//! karaoke and AI stay in Python.

mod platform;

use std::borrow::Cow;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tao::dpi::{LogicalPosition, LogicalSize, PhysicalPosition};
use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoop, EventLoopBuilder, EventLoopProxy, EventLoopWindowTarget};
use tao::window::{Fullscreen, Icon, ResizeDirection, Window, WindowBuilder, WindowId};
use wry::{WebContext, WebView, WebViewBuilder};

use kryonyx_shell_core::cli::{parse_args, Args, Parsed};
use kryonyx_shell_core::{bridge, http, sidecar, winstate};

const APP: &str = "Kryo";
const MIN_W: f64 = 400.0;
const MIN_H: f64 = 560.0;
const DEF_W: f64 = 1360.0;
const DEF_H: f64 = 860.0;
const MINI_W: f64 = 420.0;
const MINI_H: f64 = 180.0;
const MINI_MIN_W: f64 = 360.0;
const MINI_MIN_H: f64 = 128.0;
/// The first start may install Python libraries; keep waiting while the
/// process is alive.
const READY_TIMEOUT: Duration = Duration::from_secs(300);
const SAVE_TIMEOUT: Duration = Duration::from_secs(180);
const SPLASH_HTML: &str = include_str!("splash.html");
const ICON_RGBA: &[u8] = include_bytes!("../assets/icon-64.rgba");
const SCHEME: &str = "kryonyx";
/// wry serves custom schemes as http://<scheme>.<host> on Windows.
#[cfg(windows)]
const SPLASH_URL: &str = "http://kryonyx.localhost/splash";
#[cfg(windows)]
const SPLASH_PREFIX: &str = "http://kryonyx.localhost/";
#[cfg(not(windows))]
const SPLASH_URL: &str = "kryonyx://localhost/splash";
#[cfg(not(windows))]
const SPLASH_PREFIX: &str = "kryonyx://localhost/";
#[cfg(windows)]
const WEBVIEW2_URL: &str = "https://go.microsoft.com/fwlink/p/?LinkId=2124703";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Which {
    Main,
    Mini,
}

enum UserEvent {
    Ipc { which: Which, body: String, url: String },
    Ready { generation: u64, port: u16, hello: Value, url: Option<String> },
    Failed { generation: u64, message: String },
    Status { generation: u64, seconds: u64, line: String },
    Plan { id: u64, kind: String, payload: Value, plan: Result<Value, String> },
    Saved { id: u64, value: Value },
}

/// Text for the person who started the shell: the console in debug builds
/// and outside Windows, a message box for the windowed release build.
fn say(text: &str, error: bool) {
    if cfg!(all(windows, not(debug_assertions))) {
        let level = if error { rfd::MessageLevel::Error } else { rfd::MessageLevel::Info };
        rfd::MessageDialog::new()
            .set_level(level)
            .set_title(APP)
            .set_description(text)
            .set_buttons(rfd::MessageButtons::Ok)
            .show();
    } else if error {
        eprintln!("{text}");
    } else {
        println!("{text}");
    }
}

fn fatal(message: &str) -> ! {
    rfd::MessageDialog::new()
        .set_level(rfd::MessageLevel::Error)
        .set_title(APP)
        .set_description(message)
        .set_buttons(rfd::MessageButtons::Ok)
        .show();
    std::process::exit(1);
}

#[cfg(windows)]
fn webview_missing(error: &wry::Error) -> ! {
    let answer = rfd::MessageDialog::new()
        .set_level(rfd::MessageLevel::Error)
        .set_title(APP)
        .set_description(format!(
            "The window needs Microsoft Edge WebView2 Runtime, and it could not start:\n{error}\n\n\
             Open the download page now? (Kryo.exe --browser works without it.)"
        ))
        .set_buttons(rfd::MessageButtons::YesNo)
        .show();
    if answer == rfd::MessageDialogResult::Yes {
        platform::open_external(WEBVIEW2_URL);
    }
    std::process::exit(1);
}

#[cfg(not(windows))]
fn webview_missing(error: &wry::Error) -> ! {
    fatal(&format!(
        "The web view could not start: {error}\nOn Linux install WebKitGTK 4.1 (libwebkit2gtk-4.1)."
    ));
}

fn icon() -> Option<Icon> {
    Icon::from_rgba(ICON_RGBA.to_vec(), 64, 64).ok()
}

fn js(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".into())
}

fn direction(edge: &str) -> Option<ResizeDirection> {
    Some(match edge {
        "n" => ResizeDirection::North,
        "s" => ResizeDirection::South,
        "e" => ResizeDirection::East,
        "w" => ResizeDirection::West,
        "ne" => ResizeDirection::NorthEast,
        "nw" => ResizeDirection::NorthWest,
        "se" => ResizeDirection::SouthEast,
        "sw" => ResizeDirection::SouthWest,
        _ => return None,
    })
}

/// Only our own pages load in the window; web links open in the browser.
fn allow_navigation(url: &str, origin: &str) -> bool {
    match bridge::navigation(url, origin, SPLASH_PREFIX) {
        bridge::Nav::Allow => true,
        bridge::Nav::External => {
            platform::open_external(url);
            false
        }
        bridge::Nav::Block => false,
    }
}

#[allow(clippy::too_many_arguments)]
fn build_view(
    window: &Window,
    context: &mut WebContext,
    which: Which,
    url: &str,
    api: &[&str],
    drag: &str,
    devtools: bool,
    proxy: EventLoopProxy<UserEvent>,
    origin: Arc<Mutex<String>>,
) -> wry::Result<WebView> {
    let mut builder = WebViewBuilder::new_with_web_context(context)
        .with_initialization_script_for_main_only(bridge::shim(api, drag), true)
        .with_ipc_handler(move |request: wry::http::Request<String>| {
            let url = request.uri().to_string();
            let body = request.into_body();
            let _ = proxy.send_event(UserEvent::Ipc { which, body, url });
        })
        .with_navigation_handler(move |url: String| {
            let origin = origin.lock().map(|o| o.clone()).unwrap_or_default();
            allow_navigation(&url, &origin)
        })
        .with_new_window_req_handler(|url: String, _features: wry::NewWindowFeatures| {
            platform::open_external(&url);
            wry::NewWindowResponse::Deny
        })
        .with_background_color((7, 7, 10, 255))
        .with_devtools(devtools)
        .with_autoplay(true)
        .with_hotkeys_zoom(true)
        .with_clipboard(true)
        .with_url(url);
    if which == Which::Main {
        builder = builder.with_custom_protocol(SCHEME.to_string(), |_id, _request| {
            wry::http::Response::builder()
                .header("Content-Type", "text/html; charset=utf-8")
                .header("Cache-Control", "no-store")
                .body(Cow::Borrowed(SPLASH_HTML.as_bytes()))
                .unwrap_or_else(|_| wry::http::Response::new(Cow::Borrowed(&b""[..])))
        });
    }
    #[cfg(windows)]
    {
        use wry::WebViewBuilderExtWindows;
        // Like pywebview outside debug mode: no browser hotkeys (F5, Ctrl+P,
        // Ctrl+F) and no default context menu.
        builder = builder.with_browser_accelerator_keys(devtools).with_default_context_menus(devtools);
    }
    #[cfg(any(windows, target_os = "macos"))]
    {
        builder.build(window)
    }
    #[cfg(not(any(windows, target_os = "macos")))]
    {
        use tao::platform::unix::WindowExtUnix;
        use wry::WebViewBuilderExtUnix;
        let vbox = window.default_vbox().ok_or(wry::Error::UnsupportedWindowHandle)?;
        builder.build_gtk(vbox)
    }
}

/// Field order matters: the web view must go before its window.
struct Mini {
    view: WebView,
    window: Window,
}

struct App {
    proxy: EventLoopProxy<UserEvent>,
    args: Args,
    view: WebView,
    mini: Option<Mini>,
    context: WebContext,
    window: Window,
    backend: Option<Arc<sidecar::Backend>>,
    generation: u64,
    origin: Arc<Mutex<String>>,
    port: u16,
    hello: Value,
    state: winstate::State,
    dirty: Option<Instant>,
    mini_state: Value,
    saving: bool,
    on_top: bool,
    maximized: bool,
    status: (u64, String),
    failure: Option<(String, String, String)>,
    ui_up: bool,
    caption: String,
    quit: bool,
    shut: bool,
}

impl App {
    // ------------------------------------------------------------ backend
    fn start_backend(&mut self) {
        self.generation += 1;
        let generation = self.generation;
        self.failure = None;
        self.status = (0, String::new());
        if let Some(url) = self.args.url.clone() {
            let _ = self.proxy.send_event(UserEvent::Ready { generation, port: 0, hello: json!({}), url: Some(url) });
            return;
        }
        // Spawned here, on the main thread: see sidecar::Backend::start.
        match sidecar::Backend::start(&self.args.opts) {
            Ok(backend) => {
                let backend = Arc::new(backend);
                self.backend = Some(backend.clone());
                let proxy = self.proxy.clone();
                std::thread::spawn(move || {
                    let ticks = proxy.clone();
                    let result = backend.wait_ready(READY_TIMEOUT, |seconds, line| {
                        let _ = ticks.send_event(UserEvent::Status { generation, seconds, line });
                    });
                    let _ = proxy.send_event(match result {
                        Ok((port, hello)) => UserEvent::Ready { generation, port, hello, url: None },
                        Err(message) => UserEvent::Failed { generation, message },
                    });
                });
            }
            Err(message) => {
                let _ = self.proxy.send_event(UserEvent::Failed { generation, message });
            }
        }
    }

    fn retry(&mut self) {
        if let Some(old) = self.backend.take() {
            old.stop();
        }
        self.start_backend();
        self.push_splash();
    }

    fn token(&self) -> Option<String> {
        self.backend.as_ref().map(|b| b.token.clone())
    }

    fn on_ready(&mut self, port: u16, hello: Value, url: Option<String>) {
        let safe = if self.args.opts.safe { "?safe=1" } else { "" };
        let url = url.unwrap_or_else(|| format!("http://127.0.0.1:{port}/{safe}"));
        let origin = bridge::origin_of(&url).unwrap_or_default();
        if let Ok(mut current) = self.origin.lock() {
            *current = origin;
        }
        self.port = port;
        self.hello = hello;
        self.ui_up = true;
        self.failure = None;
        let _ = self.view.load_url(&url);
    }

    fn fail(&mut self, message: String) {
        let (log, describe) = match &self.backend {
            Some(backend) => (backend.log_tail(80), backend.describe.clone()),
            None => (String::new(), String::new()),
        };
        let report = platform::config_dir().join("backend-failure.log");
        let _ = std::fs::create_dir_all(platform::config_dir());
        let _ = std::fs::write(&report, format!("{message}\n{describe}\n\n{log}\n"));
        self.failure = Some((message, log, describe));
        self.mini_close();
        if self.ui_up {
            self.ui_up = false;
            if let Ok(mut current) = self.origin.lock() {
                current.clear();
            }
            // The splash posts __splash when it is up; the failure goes there.
            let _ = self.view.load_url(SPLASH_URL);
        } else {
            self.push_splash();
        }
    }

    fn push_splash(&self) {
        let script = match &self.failure {
            Some((message, log, describe)) => {
                format!("window.__splash&&__splash.fail({},{},{})", js(message), js(log), js(describe))
            }
            None => format!("window.__splash&&__splash.status({},{})", self.status.0, js(&self.status.1)),
        };
        let _ = self.view.evaluate_script(&script);
    }

    // ------------------------------------------------------------- window
    fn bounds_of(window: &Window) -> winstate::Bounds {
        let scale = window.scale_factor();
        let position = window
            .outer_position()
            .unwrap_or(PhysicalPosition::new(0, 0))
            .to_logical::<f64>(scale);
        let size = window.inner_size().to_logical::<f64>(scale);
        winstate::Bounds { x: position.x, y: position.y, width: size.width, height: size.height }
    }

    fn bounds(&self) -> Value {
        let b = Self::bounds_of(&self.window);
        json!({"x": b.x.round(), "y": b.y.round(), "width": b.width.round(), "height": b.height.round()})
    }

    fn touch(&mut self) {
        if self.dirty.is_none() {
            self.dirty = Some(Instant::now());
        }
    }

    /// Remember the main window bounds — not while minimized, maximized or
    /// full screen.
    fn capture(&mut self) {
        let w = &self.window;
        if !self.state.remember() || w.is_minimized() || w.is_maximized() || w.fullscreen().is_some() {
            return;
        }
        let bounds = Self::bounds_of(w);
        if self.state.set_bounds(bounds) {
            self.touch();
        }
    }

    fn flush(&mut self) {
        self.dirty = None;
        let _ = self.state.save();
    }

    fn eval_main(&self, script: &str) {
        let _ = self.view.evaluate_script(script);
    }

    fn show(&self) {
        self.window.set_visible(true);
        self.window.set_minimized(false);
        self.window.set_focus();
    }

    fn reply(&self, which: Which, id: u64, result: Result<Value, String>) {
        if id == 0 {
            return;
        }
        let (ok, value) = match result {
            Ok(value) => (true, value),
            Err(message) => (false, Value::String(message)),
        };
        let script = bridge::resolve_js(id, ok, &value);
        match which {
            Which::Main => {
                let _ = self.view.evaluate_script(&script);
            }
            Which::Mini => {
                if let Some(mini) = &self.mini {
                    let _ = mini.view.evaluate_script(&script);
                }
            }
        }
    }

    fn info(&self) -> Value {
        let h = |key: &str| self.hello.get(key).cloned().unwrap_or(Value::Null);
        json!({
            "version": h("version"), "version_label": h("version_label"),
            "platform": h("platform"), "data_dir": h("data_dir"), "app_dir": h("app_dir"),
            "desktop": true, "frameless": true,
            "maximized": self.window.is_maximized(),
            "on_top": self.on_top,
            "remember": self.state.remember(),
            "min_width": MIN_W, "min_height": MIN_H,
            "shell": "rust", "shell_version": env!("CARGO_PKG_VERSION"),
        })
    }

    fn caption(&mut self, info: Option<&Value>) {
        let field = |key: &str| {
            info.and_then(|i| i.get(key)).and_then(Value::as_str).unwrap_or("").chars().take(200).collect::<String>()
        };
        let (title, artist) = (field("title"), field("artist"));
        let label = if !title.is_empty() && !artist.is_empty() { format!("{title} — {artist}") } else { title };
        let version = self.hello.get("version_label").and_then(Value::as_str).unwrap_or("");
        let caption = if label.is_empty() { format!("{APP} {version}").trim().to_string() } else { format!("{label} · {APP}") };
        if caption != self.caption {
            self.window.set_title(&caption);
            self.caption = caption;
        }
    }

    fn close(&mut self) {
        self.capture();
        self.quit = true;
    }

    fn shutdown(&mut self) {
        if self.shut {
            return;
        }
        self.shut = true;
        self.capture();
        self.flush();
        self.mini = None;
        // Gone at once for the user; the backend then gets a few seconds
        // to close its jobs and the database.
        let _ = self.view.evaluate_script(
            "try{document.querySelectorAll('audio,video').forEach(function(m){m.muted=true;m.pause()})}catch(e){}",
        );
        self.window.set_visible(false);
        if let Some(backend) = self.backend.take() {
            backend.stop();
        }
    }

    // --------------------------------------------------------- mini player
    fn mini_open(&mut self, target: &EventLoopWindowTarget<UserEvent>) -> bool {
        if let Some(mini) = &self.mini {
            mini.window.set_always_on_top(true);
            return true;
        }
        let origin = self.origin.lock().map(|o| o.clone()).unwrap_or_default();
        if origin.is_empty() {
            return false;
        }
        let (width, height) = self
            .state
            .mini_size()
            .map(|(w, h)| (w.clamp(MINI_MIN_W, 1400.0), h.clamp(MINI_MIN_H, 900.0)))
            .unwrap_or((MINI_W, MINI_H));
        let position = self.state.mini_position().or_else(|| {
            platform::work_area(&self.window).map(|(x, y, w, h)| (x + w - width - 24.0, y + h - height - 72.0))
        });
        let mut builder = WindowBuilder::new()
            .with_title(format!("{APP} · mini"))
            .with_decorations(false)
            .with_always_on_top(true)
            .with_resizable(true)
            .with_focused(false)
            .with_min_inner_size(LogicalSize::new(MINI_MIN_W, MINI_MIN_H))
            .with_inner_size(LogicalSize::new(width, height))
            .with_window_icon(icon());
        if let Some((x, y)) = position {
            builder = builder.with_position(LogicalPosition::new(x, y));
        }
        #[cfg(windows)]
        {
            use tao::platform::windows::WindowBuilderExtWindows;
            builder = builder.with_skip_taskbar(true).with_undecorated_shadow(true);
        }
        #[cfg(all(unix, not(target_os = "macos")))]
        {
            use tao::platform::unix::WindowBuilderExtUnix;
            builder = builder.with_skip_taskbar(true);
        }
        let Ok(window) = builder.build(target) else { return false };
        let url = format!("{origin}/mini.html");
        match build_view(
            &window,
            &mut self.context,
            Which::Mini,
            &url,
            bridge::MINI_API,
            bridge::MINI_DRAG,
            self.args.devtools,
            self.proxy.clone(),
            self.origin.clone(),
        ) {
            Ok(view) => {
                self.mini = Some(Mini { view, window });
                true
            }
            Err(_) => false,
        }
    }

    fn mini_close(&mut self) {
        self.mini = None;
    }

    fn mini_closed_by_itself(&mut self) {
        self.mini_close();
        self.eval_main("window.MiniPlayer&&MiniPlayer.closed()");
    }

    fn mini_call(&mut self, id: u64, cmd: &str, args: &[Value]) {
        let arg = |i: usize| args.get(i);
        let result: Result<Value, String> = match cmd {
            "state" => Ok(self.mini_state.clone()),
            "action" => {
                let name = arg(0).and_then(Value::as_str).unwrap_or("");
                match name {
                    "prev" | "next" | "toggle" => {
                        self.eval_main(&bridge::call_js("window.KTray", "window.KTray.act", &json!(name)));
                        Ok(json!(true))
                    }
                    "lyrics" | "queue" => {
                        self.show();
                        self.eval_main(&bridge::call_js("window.MiniPlayer", "MiniPlayer.action", &json!(name)));
                        Ok(json!(true))
                    }
                    "show" => {
                        self.show();
                        self.mini_closed_by_itself();
                        Ok(json!(true))
                    }
                    _ => Ok(json!(false)),
                }
            }
            "seek" => {
                let value = bridge::num(arg(0)).clamp(0.0, 1.0);
                self.eval_main(&bridge::call_js("window.MiniPlayer", "MiniPlayer.seek", &json!(value)));
                Ok(json!(true))
            }
            "volume" => {
                let value = bridge::num(arg(0)).clamp(0.0, 100.0);
                self.eval_main(&bridge::call_js("window.MiniPlayer", "MiniPlayer.volume", &json!(value)));
                Ok(json!(true))
            }
            "move_by" => Ok(json!(self.mini_move_by(arg(0), arg(1)))),
            "resize" => {
                let width = bridge::num(arg(0)).clamp(MINI_MIN_W, 1400.0);
                let height = bridge::num(arg(1)).clamp(MINI_MIN_H, 900.0);
                if let Some(mini) = &self.mini {
                    mini.window.set_inner_size(LogicalSize::new(width, height));
                }
                Ok(json!({"width": width.round(), "height": height.round()}))
            }
            "size" => Ok(match &self.mini {
                Some(mini) => {
                    let size = mini.window.inner_size().to_logical::<f64>(mini.window.scale_factor());
                    json!({"width": size.width.round(), "height": size.height.round()})
                }
                None => json!({"width": 0, "height": 0}),
            }),
            "close" => {
                self.mini_closed_by_itself();
                Ok(json!(true))
            }
            _ => Err(format!("{cmd} is not available here")),
        };
        self.reply(Which::Mini, id, result);
    }

    /// Fallback for `move_by` (the page normally asks for the native move
    /// loop): device pixels, fractions included.
    fn mini_move_by(&mut self, dx: Option<&Value>, dy: Option<&Value>) -> bool {
        let Some(mini) = &self.mini else { return false };
        let clamp = |v: Option<&Value>| bridge::coord(v).unwrap_or(0.0).clamp(-4096.0, 4096.0);
        let scale = mini.window.scale_factor();
        let Ok(position) = mini.window.outer_position() else { return false };
        let x = position.x as f64 + (clamp(dx) * scale).round();
        let y = position.y as f64 + (clamp(dy) * scale).round();
        mini.window.set_outer_position(PhysicalPosition::new(x as i32, y as i32));
        true
    }

    // --------------------------------------------------------- main window
    fn main_call(&mut self, id: u64, cmd: &str, args: Vec<Value>, target: &EventLoopWindowTarget<UserEvent>) {
        let arg = |i: usize| args.get(i);
        let result: Result<Value, String> = match cmd {
            "minimize" => {
                self.window.set_minimized(true);
                Ok(json!(true))
            }
            "toggle_maximize" => {
                let next = !self.window.is_maximized();
                self.window.set_maximized(next);
                self.maximized = next;
                self.state.set_maximized(next);
                self.touch();
                Ok(json!(next))
            }
            "maximized" => Ok(json!(self.window.is_maximized())),
            "close" => {
                self.close();
                Ok(json!(true))
            }
            "toggle_fullscreen" => {
                let on = self.window.fullscreen().is_none();
                self.window.set_fullscreen(if on { Some(Fullscreen::Borderless(None)) } else { None });
                Ok(json!(on))
            }
            "info" => Ok(self.info()),
            "bounds" => Ok(self.bounds()),
            "set_bounds" => {
                let x = bridge::coord(arg(0)).unwrap_or(0.0);
                let y = bridge::coord(arg(1)).unwrap_or(0.0);
                let width = bridge::num(arg(2)).max(MIN_W);
                let height = bridge::num(arg(3)).max(MIN_H);
                if self.window.is_maximized() {
                    self.window.set_maximized(false);
                    self.maximized = false;
                }
                self.window.set_inner_size(LogicalSize::new(width, height));
                self.window.set_outer_position(LogicalPosition::new(x, y));
                self.touch();
                Ok(json!({"x": x.round(), "y": y.round(), "width": width.round(), "height": height.round()}))
            }
            "screen" => Ok(match platform::work_area(&self.window) {
                Some((x, y, width, height)) => {
                    json!({"x": x.round(), "y": y.round(), "width": width.round(), "height": height.round(), "real": true})
                }
                None => {
                    let b = Self::bounds_of(&self.window);
                    json!({"x": 0, "y": 0, "width": b.width.round(), "height": b.height.round(), "real": false})
                }
            }),
            "set_on_top" => {
                self.on_top = bridge::flag(arg(0));
                self.window.set_always_on_top(self.on_top);
                Ok(json!(self.on_top))
            }
            "set_remember" => {
                let on = bridge::flag(arg(0));
                self.state.set_remember(on);
                self.capture();
                self.flush();
                Ok(json!(on))
            }
            "flush_state" => {
                self.capture();
                self.flush();
                Ok(Value::Null)
            }
            "note_minimized" => Ok(Value::Null),
            "show_window" => {
                self.show();
                Ok(Value::Null)
            }
            "now_playing" => {
                self.caption(arg(0));
                Ok(json!(true))
            }
            "tray_action" => {
                match arg(0).and_then(Value::as_str).unwrap_or("") {
                    "show" => self.show(),
                    "quit" => self.close(),
                    name @ ("prev" | "next" | "toggle") => {
                        self.eval_main(&bridge::call_js("window.KTray", "window.KTray.act", &json!(name)))
                    }
                    _ => {}
                }
                Ok(Value::Null)
            }
            "mini_open" => Ok(json!(self.mini_open(target))),
            "mini_close" => {
                self.mini_close();
                Ok(json!(true))
            }
            "mini_update" => match arg(0) {
                Some(state @ Value::Object(_)) => {
                    self.mini_state = state.clone();
                    if let Some(mini) = &self.mini {
                        let _ = mini.view.evaluate_script(&bridge::call_js("window.Mini", "Mini.update", state));
                    }
                    Ok(json!(true))
                }
                _ => Ok(json!(false)),
            },
            "save_export" => return self.save_begin(id, "export", json!({"spec": arg(0).cloned().unwrap_or(Value::Null)})),
            "save_clip" => return self.save_begin(id, "clip", json!({"session": arg(0).cloned().unwrap_or(Value::Null)})),
            "save_shared_audio" => {
                return self.save_begin(id, "shared_audio", json!({"token": arg(0).cloned().unwrap_or(Value::Null)}))
            }
            _ => Err(format!("{cmd} is not available in this window")),
        };
        self.reply(Which::Main, id, result);
    }

    // ------------------------------------------------------------ Save As
    // The backend prepares the file and suggests a name, the shell shows the
    // native dialog, the backend writes the file. The same three steps as
    // DesktopApi.save_* inside the pywebview window, over loopback.
    fn save_begin(&mut self, id: u64, kind: &str, payload: Value) {
        let Some(token) = self.token() else {
            let message = "Save As needs the backend started by the shell (not --url)";
            return self.reply(Which::Main, id, Ok(json!({"error": message})));
        };
        if self.saving {
            return self.reply(Which::Main, id, Ok(json!({"error": "Another save dialog is already open"})));
        }
        self.saving = true;
        let (port, proxy, kind) = (self.port, self.proxy.clone(), kind.to_string());
        std::thread::spawn(move || {
            let body = json!({"kind": kind, "payload": payload});
            let plan = post_json(port, "/api/shell/save-plan", &token, &body, "Could not prepare the file");
            let _ = proxy.send_event(UserEvent::Plan { id, kind, payload: body["payload"].clone(), plan });
        });
    }

    fn save_dialog(&mut self, id: u64, kind: String, payload: Value, plan: Result<Value, String>) {
        let plan = match plan {
            Ok(plan) => plan,
            Err(message) => {
                self.saving = false;
                return self.reply(Which::Main, id, Ok(json!({"error": message})));
            }
        };
        let name = plan.get("name").and_then(Value::as_str).unwrap_or("Kryo export");
        let mut dialog = rfd::FileDialog::new().set_file_name(name).set_parent(&self.window);
        for filter in plan.get("filters").and_then(Value::as_array).into_iter().flatten() {
            let label = filter.get(0).and_then(Value::as_str);
            let extensions: Vec<String> = filter
                .get(1)
                .and_then(Value::as_array)
                .map(|items| items.iter().filter_map(|e| e.as_str().map(str::to_string)).collect())
                .unwrap_or_default();
            if let (Some(label), false) = (label, extensions.is_empty()) {
                dialog = dialog.add_filter(label, &extensions);
            }
        }
        let Some(path) = dialog.save_file() else {
            self.saving = false;
            return self.reply(Which::Main, id, Ok(json!({"cancelled": true})));
        };
        let Some(token) = self.token() else {
            self.saving = false;
            return self.reply(Which::Main, id, Ok(json!({"error": "The backend has stopped"})));
        };
        let (port, proxy) = (self.port, self.proxy.clone());
        let path = path.to_string_lossy().to_string();
        std::thread::spawn(move || {
            let body = json!({"kind": kind, "payload": payload, "path": path});
            let fallback = "Could not save the file. Check the source and destination.";
            let value = match post_json(port, "/api/shell/save", &token, &body, fallback) {
                Ok(value) => value,
                Err(message) => json!({"error": message}),
            };
            let _ = proxy.send_event(UserEvent::Saved { id, value });
        });
    }

    // -------------------------------------------------------------- events
    fn ipc(&mut self, which: Which, body: &str, url: &str, target: &EventLoopWindowTarget<UserEvent>) {
        let Some(call) = bridge::parse(body) else { return };
        let origin = self.origin.lock().map(|o| o.clone()).unwrap_or_default();
        let trusted = bridge::same_origin(url, &origin);
        let splash = which == Which::Main && url.starts_with(SPLASH_PREFIX);
        if call.cmd.starts_with("__") {
            match call.cmd.as_str() {
                "__drag" if trusted || splash => {
                    let window = match which {
                        Which::Main => Some(&self.window),
                        Which::Mini => self.mini.as_ref().map(|m| &m.window),
                    };
                    if let Some(window) = window {
                        let _ = window.drag_window();
                    }
                }
                "__resize" if which == Which::Main && (trusted || splash) => {
                    let edge = call.args.first().and_then(Value::as_str).and_then(direction);
                    if let Some(edge) = edge {
                        if !self.window.is_maximized() {
                            let _ = self.window.drag_resize_window(edge);
                        }
                    }
                }
                "__splash" if splash => self.push_splash(),
                "__retry" if splash => self.retry(),
                "__quit" if splash => self.close(),
                _ => {}
            }
            return;
        }
        let from_splash = splash && matches!(call.cmd.as_str(), "toggle_maximize" | "minimize" | "close");
        if !trusted && !from_splash {
            return self.reply(which, call.id, Err("This page may not control the window".to_string()));
        }
        match which {
            Which::Main => self.main_call(call.id, &call.cmd, call.args, target),
            Which::Mini => self.mini_call(call.id, &call.cmd, &call.args),
        }
    }

    fn user_event(&mut self, event: UserEvent, target: &EventLoopWindowTarget<UserEvent>) {
        match event {
            UserEvent::Ipc { which, body, url } => self.ipc(which, &body, &url, target),
            UserEvent::Status { generation, seconds, line } if generation == self.generation => {
                self.status = (seconds, line);
                if !self.ui_up {
                    self.push_splash();
                }
            }
            UserEvent::Ready { generation, port, hello, url } if generation == self.generation => {
                self.on_ready(port, hello, url)
            }
            UserEvent::Failed { generation, message } if generation == self.generation => self.fail(message),
            UserEvent::Plan { id, kind, payload, plan } => self.save_dialog(id, kind, payload, plan),
            UserEvent::Saved { id, value } => {
                self.saving = false;
                self.reply(Which::Main, id, Ok(value));
            }
            _ => {}
        }
    }

    fn window_event(&mut self, id: WindowId, event: WindowEvent) {
        if id == self.window.id() {
            match event {
                WindowEvent::CloseRequested => self.close(),
                WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
                    let maximized = self.window.is_maximized();
                    if maximized != self.maximized && !self.window.is_minimized() {
                        self.maximized = maximized;
                        self.state.set_maximized(maximized);
                        self.touch();
                        self.eval_main(&format!("window.Frame&&Frame.applyMax&&Frame.applyMax({maximized})"));
                    }
                    self.capture();
                }
                _ => {}
            }
            return;
        }
        let Some(mini) = &self.mini else { return };
        if id != mini.window.id() {
            return;
        }
        match event {
            WindowEvent::CloseRequested => self.mini_closed_by_itself(),
            WindowEvent::Moved(_) => {
                let b = Self::bounds_of(&mini.window);
                self.state.set_mini_position(b.x, b.y);
                self.touch();
            }
            WindowEvent::Resized(_) => {
                let b = Self::bounds_of(&mini.window);
                self.state.set_mini_size(b.width, b.height);
                self.touch();
            }
            _ => {}
        }
    }

    /// Runs after every event and at least twice a second.
    fn tick(&mut self) {
        if let Some(since) = self.dirty {
            if since.elapsed() >= Duration::from_secs(1) {
                self.flush();
            }
        }
        if self.ui_up && self.args.url.is_none() {
            let gone = self.backend.as_ref().and_then(|b| b.exited());
            if let Some(reason) = gone {
                self.fail(format!("The backend stopped unexpectedly ({reason})."));
            }
        }
    }
}

fn post_json(port: u16, path: &str, token: &str, body: &Value, fallback: &str) -> Result<Value, String> {
    let bytes = serde_json::to_vec(body).map_err(|e| e.to_string())?;
    match http::request(port, "POST", path, Some(token), Some(&bytes), SAVE_TIMEOUT) {
        Ok(reply) => {
            let value = reply.json();
            if reply.status == 200 {
                return Ok(value);
            }
            let message = value.get("error").and_then(Value::as_str).map(str::to_string);
            Err(message.unwrap_or_else(|| match reply.status {
                403 => "The backend did not accept this window".to_string(),
                _ => fallback.to_string(),
            }))
        }
        Err(error) => Err(format!("The backend did not answer: {error}")),
    }
}

/// The main window: frameless (the interface draws its own title bar),
/// restored to the remembered place when it is still on a screen.
fn main_window(event_loop: &EventLoop<UserEvent>, state: &winstate::State) -> Result<Window, String> {
    let remember = state.remember();
    let saved = if remember { state.bounds(MIN_W, MIN_H) } else { None };
    let (width, height) = saved.map(|b| (b.width, b.height)).unwrap_or((DEF_W, DEF_H));
    let mut builder = WindowBuilder::new()
        .with_title(APP)
        .with_decorations(false)
        .with_resizable(true)
        .with_min_inner_size(LogicalSize::new(MIN_W, MIN_H))
        .with_inner_size(LogicalSize::new(width, height))
        .with_window_icon(icon())
        .with_maximized(remember && state.maximized());
    if let Some(b) = saved {
        // Only if the title bar would be on one of the screens.
        let visible = event_loop.available_monitors().any(|m| {
            let scale = m.scale_factor();
            let p = m.position().to_logical::<f64>(scale);
            let s = m.size().to_logical::<f64>(scale);
            let (cx, cy) = (b.x + 60.0, b.y + 16.0);
            cx >= p.x && cx < p.x + s.width && cy >= p.y && cy < p.y + s.height
        });
        if visible {
            builder = builder.with_position(LogicalPosition::new(b.x, b.y));
        }
    }
    #[cfg(windows)]
    {
        use tao::platform::windows::WindowBuilderExtWindows;
        builder = builder.with_undecorated_shadow(true).with_taskbar_icon(icon());
    }
    builder.build(event_loop).map_err(|e| e.to_string())
}

fn main() {
    let args = match parse_args(std::env::args().skip(1).collect()) {
        Ok(Parsed::Run(args)) => args,
        Ok(Parsed::Exit(text)) => {
            say(&text, false);
            return;
        }
        Err(message) => {
            say(&message, true);
            std::process::exit(2);
        }
    };
    let event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    let proxy = event_loop.create_proxy();
    let state = winstate::State::load(platform::config_dir().join("shell.json"));
    let window = match main_window(&event_loop, &state) {
        Ok(window) => window,
        Err(error) => fatal(&format!("The window could not be created: {error}")),
    };
    let mut context = WebContext::new(Some(platform::config_dir().join("webview")));
    let origin = Arc::new(Mutex::new(String::new()));
    let view = match build_view(
        &window,
        &mut context,
        Which::Main,
        SPLASH_URL,
        bridge::MAIN_API,
        bridge::MAIN_DRAG,
        args.devtools,
        proxy.clone(),
        origin.clone(),
    ) {
        Ok(view) => view,
        Err(error) => webview_missing(&error),
    };
    let maximized = window.is_maximized();
    let mut app = App {
        proxy,
        args,
        view,
        mini: None,
        context,
        window,
        backend: None,
        generation: 0,
        origin,
        port: 0,
        hello: json!({}),
        state,
        dirty: None,
        mini_state: json!({}),
        saving: false,
        on_top: false,
        maximized,
        status: (0, String::new()),
        failure: None,
        ui_up: false,
        caption: String::new(),
        quit: false,
        shut: false,
    };
    app.start_backend();
    event_loop.run(move |event, target, control_flow| {
        *control_flow = ControlFlow::WaitUntil(Instant::now() + Duration::from_millis(500));
        match event {
            Event::UserEvent(event) => app.user_event(event, target),
            Event::WindowEvent { window_id, event, .. } => app.window_event(window_id, event),
            Event::LoopDestroyed => app.shutdown(),
            _ => {}
        }
        app.tick();
        if app.quit {
            app.shutdown();
            *control_flow = ControlFlow::Exit;
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn edges_map_to_native_directions() {
        assert!(matches!(direction("nw"), Some(ResizeDirection::NorthWest)));
        assert!(matches!(direction("s"), Some(ResizeDirection::South)));
        assert!(direction("middle").is_none());
    }

    #[test]
    fn splash_url_is_inside_the_app() {
        assert!(SPLASH_URL.starts_with(SPLASH_PREFIX));
        assert_eq!(bridge::navigation(SPLASH_URL, "", SPLASH_PREFIX), bridge::Nav::Allow);
    }
}
