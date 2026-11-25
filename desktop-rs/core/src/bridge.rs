//! The JavaScript half of the window bridge and the parsing of its messages.
//!
//! The interface talks to its window through `window.pywebview.api.*` (see
//! web/js/frame.js, mini.js, tray.js, file-save-v27.js). The shell provides
//! the same object: every method posts `{id, cmd, args}` through wry's IPC
//! channel and returns a Promise that the shell settles with
//! `__kryonyxShell.resolve(id, ok, value)`.

use serde_json::Value;

/// Methods of `DesktopApi` (kryonyx/main.py) that the main window exposes.
pub const MAIN_API: &[&str] = &[
    "minimize",
    "toggle_maximize",
    "maximized",
    "close",
    "toggle_fullscreen",
    "info",
    "bounds",
    "set_bounds",
    "screen",
    "set_on_top",
    "set_remember",
    "flush_state",
    "note_minimized",
    "show_window",
    "now_playing",
    "tray_action",
    "mini_open",
    "mini_close",
    "mini_update",
    "save_export",
    "save_clip",
    "save_shared_audio",
];

/// Methods of `MiniApi`: the mini player can only steer playback and itself.
pub const MINI_API: &[&str] = &["state", "action", "seek", "volume", "move_by", "resize", "size", "close"];

/// Elements that move the window when dragged.
pub const MAIN_DRAG: &str = ".pywebview-drag-region";
/// The mini player moves itself: mini-view.js calls `__drag` through
/// `opts.nativeDragStart` (see web/mini.html), so no selector is needed here.
pub const MINI_DRAG: &str = "";

const SHIM: &str = r#"(function () {
  'use strict';
  if (window.__kryonyxShell) return;
  var API = __API__, DRAG = __DRAG__;
  var seq = 0, waiting = Object.create(null);
  function post(message) { window.ipc.postMessage(JSON.stringify(message)); }
  function call(cmd, args) {
    return new Promise(function (resolve, reject) {
      var id = ++seq;
      waiting[id] = [resolve, reject];
      try { post({ id: id, cmd: cmd, args: args }); }
      catch (error) { delete waiting[id]; reject(error); }
    });
  }
  var shell = {
    native: 'rust',
    lastToggle: 0,
    post: post,
    resolve: function (id, ok, value) {
      var entry = waiting[id];
      if (!entry) return;
      delete waiting[id];
      if (ok) entry[0](value);
      else entry[1](new Error(typeof value === 'string' ? value : 'The window did not answer'));
    }
  };
  window.__kryonyxShell = shell;

  /* Moving and resizing are native: the shell starts the system move/size
     loop, so Windows snap layouts and the minimum size work as usual. */
  var EDGES = { top: 'n', bottom: 's', left: 'w', right: 'e',
                topleft: 'nw', topright: 'ne', bottomleft: 'sw', bottomright: 'se' };
  function interactive(node) {
    return !!(node.closest && node.closest('button,a,input,select,textarea,label,[contenteditable=""],[contenteditable="true"],[role="button"],[data-no-drag]'));
  }
  function region(node) {
    return DRAG && node && node.closest ? node.closest(DRAG) : null;
  }
  document.addEventListener('mousedown', function (event) {
    if (event.button !== 0) return;
    var target = event.target;
    if (!target || !target.closest) return;
    var edge = target.closest('#resizers .rz[data-edge]');
    if (edge && EDGES[edge.dataset.edge]) {
      var body = document.body;
      if (body && (body.classList.contains('max') || body.classList.contains('fs'))) return;
      event.preventDefault();
      event.stopPropagation();
      post({ id: 0, cmd: '__resize', args: [EDGES[edge.dataset.edge]] });
      return;
    }
    if (!region(target) || interactive(target)) return;
    event.preventDefault();
    if (event.detail === 2 && API.indexOf('toggle_maximize') !== -1) {
      shell.lastToggle = Date.now();
      call('toggle_maximize', []).then(function (state) {
        if (window.Frame && window.Frame.applyMax) window.Frame.applyMax(!!state);
      }).catch(function () {});
      return;
    }
    if (event.detail > 2) return;
    post({ id: 0, cmd: '__drag', args: [] });
  }, true);
  /* frame.js maximizes on dblclick as well; the shell already did it on the
     second mousedown, so the native dblclick must not toggle it back. */
  document.addEventListener('dblclick', function (event) {
    if (Date.now() - shell.lastToggle < 800 && region(event.target)) event.stopImmediatePropagation();
  }, true);

  var host = location.hostname;
  if (location.protocol !== 'http:' || (host !== '127.0.0.1' && host !== 'localhost')) return;
  var api = {};
  API.forEach(function (name) {
    api[name] = function () { return call(name, Array.prototype.slice.call(arguments)); };
  });
  window.pywebview = { api: api, platform: 'kryonyx-shell', token: '' };
  function ready() { window.dispatchEvent(new CustomEvent('pywebviewready')); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(ready, 0); });
  else setTimeout(ready, 0);
})();"#;

/// The initialization script for a window with the given API.
pub fn shim(api: &[&str], drag: &str) -> String {
    let names = serde_json::to_string(api).unwrap_or_else(|_| "[]".into());
    let drag = serde_json::to_string(drag).unwrap_or_else(|_| "''".into());
    SHIM.replace("__API__", &names).replace("__DRAG__", &drag)
}

#[derive(Clone, Debug, PartialEq)]
pub struct Call {
    pub id: u64,
    pub cmd: String,
    pub args: Vec<Value>,
}

/// `{id, cmd, args}` from the page; anything else is ignored.
pub fn parse(body: &str) -> Option<Call> {
    if body.len() > 8 * 1024 * 1024 {
        return None;
    }
    let value: Value = serde_json::from_str(body).ok()?;
    let id = value.get("id")?.as_u64()?;
    let cmd = value.get("cmd")?.as_str()?;
    if cmd.is_empty() || cmd.len() > 64 || !cmd.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
        return None;
    }
    let args = match value.get("args") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items.clone(),
        Some(_) => return None,
    };
    Some(Call { id, cmd: cmd.to_string(), args })
}

/// The script that settles the page's Promise number `id`.
pub fn resolve_js(id: u64, ok: bool, value: &Value) -> String {
    let json = serde_json::to_string(value).unwrap_or_else(|_| "null".into());
    format!("window.__kryonyxShell&&window.__kryonyxShell.resolve({id},{ok},{json})")
}

/// A JavaScript call `target(argument)` guarded by `guard`.
pub fn call_js(guard: &str, target: &str, argument: &Value) -> String {
    let json = serde_json::to_string(argument).unwrap_or_else(|_| "null".into());
    format!("{guard}&&{target}({json})")
}

/// `url` belongs to `origin` (scheme://host:port), not to a look-alike such
/// as `http://127.0.0.1:87650`.
pub fn same_origin(url: &str, origin: &str) -> bool {
    !origin.is_empty()
        && url.starts_with(origin)
        && matches!(url.as_bytes().get(origin.len()), None | Some(b'/') | Some(b'?') | Some(b'#'))
}

/// `scheme://host[:port]` of an http(s) URL.
pub fn origin_of(url: &str) -> Option<String> {
    let (scheme, rest) = url.split_once("://")?;
    if scheme != "http" && scheme != "https" {
        return None;
    }
    let host = rest.split(['/', '?', '#']).next().unwrap_or("");
    if host.is_empty() || host.contains('@') {
        return None;
    }
    Some(format!("{scheme}://{host}"))
}

/// `http://127.0.0.1[:port]`, `http://localhost[:port]` or `http://[::1][:port]`:
/// the only origins that the window ever gives the bridge to.
pub fn is_loopback_origin(origin: &str) -> bool {
    let Some(host) = origin.strip_prefix("http://") else {
        return false;
    };
    let (name, port) = match host.strip_prefix("[::1]") {
        Some(rest) => ("[::1]", rest),
        None => match host.split_once(':') {
            Some((name, _)) => (name, host.get(name.len()..).unwrap_or("")),
            None => (host, ""),
        },
    };
    let port_ok = port.is_empty()
        || port
            .strip_prefix(':')
            .is_some_and(|p| !p.is_empty() && p.len() <= 5 && p.bytes().all(|b| b.is_ascii_digit()));
    matches!(name, "127.0.0.1" | "localhost" | "[::1]") && port_ok
}

/// Like Python's `_num` in main.py: a finite, non-negative number or 0.
pub fn num(value: Option<&Value>) -> f64 {
    let number = match value {
        Some(Value::Number(n)) => n.as_f64().unwrap_or(0.0),
        Some(Value::String(s)) => s.trim().parse::<f64>().unwrap_or(0.0),
        Some(Value::Bool(true)) => 1.0,
        _ => 0.0,
    };
    if number.is_finite() && (0.0..1e7).contains(&number) {
        number
    } else {
        0.0
    }
}

/// A screen coordinate: may be negative (monitors left of / above the
/// primary one), must be finite and plausible.
pub fn coord(value: Option<&Value>) -> Option<f64> {
    let number = match value {
        Some(Value::Number(n)) => n.as_f64()?,
        Some(Value::String(s)) => s.trim().parse::<f64>().ok()?,
        _ => return None,
    };
    (number.is_finite() && number.abs() < 1e6).then_some(number)
}

/// Python truthiness for the few boolean arguments.
pub fn flag(value: Option<&Value>) -> bool {
    match value {
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().map(|v| v != 0.0).unwrap_or(false),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
        _ => false,
    }
}

/// Only web links leave the app; everything else is ignored.
pub fn is_external_link(url: &str) -> bool {
    let lower = url.trim().to_ascii_lowercase();
    (lower.starts_with("https://") || lower.starts_with("http://") || lower.starts_with("mailto:"))
        && !url.chars().any(|c| c.is_control())
}

/// What the window does with a navigation request.
#[derive(Debug, PartialEq, Eq)]
pub enum Nav {
    /// Our own page: the splash or the backend that the shell started.
    Allow,
    /// A web link: opened in the system browser, the window stays.
    External,
    /// Anything else (file:, javascript:, data:, ...).
    Block,
}

pub fn navigation(url: &str, origin: &str, splash_prefix: &str) -> Nav {
    if url.starts_with(splash_prefix) || url == "about:blank" || same_origin(url, origin) {
        Nav::Allow
    } else if is_external_link(url) {
        Nav::External
    } else {
        Nav::Block
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_calls_and_rejects_junk() {
        let call = parse(r#"{"id":7,"cmd":"set_bounds","args":[1,2,800,600]}"#).unwrap();
        assert_eq!(call.id, 7);
        assert_eq!(call.cmd, "set_bounds");
        assert_eq!(call.args.len(), 4);
        assert_eq!(parse(r#"{"id":0,"cmd":"__drag"}"#).unwrap().args, Vec::<Value>::new());
        assert!(parse("not json").is_none());
        assert!(parse(r#"{"id":-1,"cmd":"close"}"#).is_none());
        assert!(parse(r#"{"id":1,"cmd":"close(); alert(1)"}"#).is_none());
        assert!(parse(r#"{"id":1,"cmd":"close","args":"x"}"#).is_none());
    }

    #[test]
    fn origin_checks_are_exact() {
        let origin = "http://127.0.0.1:8765";
        assert!(same_origin("http://127.0.0.1:8765/", origin));
        assert!(same_origin("http://127.0.0.1:8765/?safe=1", origin));
        assert!(same_origin("http://127.0.0.1:8765", origin));
        assert!(!same_origin("http://127.0.0.1:87650/", origin));
        assert!(!same_origin("http://127.0.0.1:8765.evil.example/", origin));
        assert!(!same_origin("https://example.com/", origin));
        assert!(!same_origin("http://127.0.0.1:8765/", ""));
        assert_eq!(origin_of("http://127.0.0.1:8766/?safe=1").as_deref(), Some("http://127.0.0.1:8766"));
        assert_eq!(origin_of("file:///C:/x"), None);
        assert_eq!(origin_of("http://user@host/"), None);
        assert!(is_loopback_origin("http://127.0.0.1:8765"));
        assert!(is_loopback_origin("http://localhost"));
        assert!(is_loopback_origin("http://[::1]:9000"));
        assert!(!is_loopback_origin("https://127.0.0.1:8765"));
        assert!(!is_loopback_origin("http://127.0.0.1.evil.example:8765"));
        assert!(!is_loopback_origin("http://localhost:80x"));
        assert!(!is_loopback_origin("http://example.com"));
    }

    #[test]
    fn numbers_follow_the_python_rules() {
        assert_eq!(num(Some(&json!(0.25))), 0.25);
        assert_eq!(num(Some(&json!("12"))), 12.0);
        assert_eq!(num(Some(&json!(-3))), 0.0);
        assert_eq!(num(Some(&json!(1e9))), 0.0);
        assert_eq!(num(None), 0.0);
        assert_eq!(coord(Some(&json!(-1920))), Some(-1920.0));
        assert_eq!(coord(Some(&json!("nan"))), None);
        assert!(flag(Some(&json!(true))));
        assert!(!flag(Some(&json!(0))));
        assert!(!flag(None));
    }

    #[test]
    fn scripts_embed_json_safely() {
        let js = resolve_js(3, true, &json!({"path": "C:\\Music\\a\"b.mp3"}));
        assert_eq!(js, r#"window.__kryonyxShell&&window.__kryonyxShell.resolve(3,true,{"path":"C:\\Music\\a\"b.mp3"})"#);
        let shim = shim(MAIN_API, MAIN_DRAG);
        assert!(shim.contains("\"save_export\""));
        assert!(shim.contains("\".pywebview-drag-region\""));
        assert!(!shim.contains("__API__") && !shim.contains("__DRAG__"));
        assert_eq!(call_js("window.Mini", "Mini.update", &json!({"t": 1})), r#"window.Mini&&Mini.update({"t":1})"#);
    }

    #[test]
    fn only_web_links_are_external() {
        assert!(is_external_link("https://example.com/a?b=1"));
        assert!(is_external_link("mailto:someone@example.com"));
        assert!(!is_external_link("file:///C:/Windows/System32/calc.exe"));
        assert!(!is_external_link("javascript:alert(1)"));
        assert!(!is_external_link("https://example.com/\n--flag"));
    }

    #[test]
    fn navigation_stays_inside_the_app() {
        let splash = "kryonyx://localhost/";
        let origin = "http://127.0.0.1:8765";
        assert_eq!(navigation("kryonyx://localhost/splash", "", splash), Nav::Allow);
        assert_eq!(navigation("http://127.0.0.1:8765/?safe=1", origin, splash), Nav::Allow);
        assert_eq!(navigation("about:blank", origin, splash), Nav::Allow);
        assert_eq!(navigation("http://127.0.0.1:8766/", origin, splash), Nav::External);
        assert_eq!(navigation("https://music.youtube.com/watch?v=x", origin, splash), Nav::External);
        assert_eq!(navigation("file:///etc/passwd", origin, splash), Nav::Block);
        assert_eq!(navigation("javascript:alert(1)", origin, splash), Nav::Block);
        assert_eq!(navigation("about:srcdoc", origin, splash), Nav::Block);
    }
}
