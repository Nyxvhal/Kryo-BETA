//! The shell's backend handshake against the real Python server, without a window:
//! `cargo run -p kryonyx-shell-core --example backend_e2e -- APP_DIR OUT_DIR`
//! (APP_DIR has run.py; set KRYONYX_DATA_DIR to keep your own data untouched).
use kryonyx_shell_core::{http, sidecar};
use serde_json::json;
use std::time::{Duration, Instant};

fn post(port: u16, path: &str, token: &str, body: serde_json::Value) -> (u16, serde_json::Value) {
    let bytes = serde_json::to_vec(&body).unwrap();
    let r = http::request(port, "POST", path, Some(token), Some(&bytes), Duration::from_secs(30)).expect("answer");
    (r.status, r.json())
}

fn main() {
    let app_dir = std::env::args().nth(1).expect("app dir");
    let out = std::env::args().nth(2).expect("out dir");
    let opts = sidecar::Options { app_dir: Some(app_dir.into()), port: Some(8811), ..Default::default() };
    let t0 = Instant::now();
    let backend = sidecar::Backend::start(&opts).expect("start");
    println!("started: {}", backend.describe);
    let (port, hello) = backend
        .wait_ready(Duration::from_secs(120), |s, line| eprintln!("  [{s}s] {line}"))
        .expect("ready");
    println!("ready on {port} after {:.1}s: app={} version={}", t0.elapsed().as_secs_f64(), hello["app"], hello["version"]);
    let r = http::request(port, "GET", "/api/shell/hello", None, None, Duration::from_secs(5)).unwrap();
    println!("hello without token -> {}", r.status);
    let r = http::request(port, "GET", "/api/shell/hello", Some("wrongwrongwrongwrongwrongwrongwrong1"), None, Duration::from_secs(5)).unwrap();
    println!("hello with a wrong token -> {}", r.status);
    let r = http::request(port, "GET", "/", None, None, Duration::from_secs(10)).unwrap();
    println!("GET / -> {} ({} bytes, has app shell: {})", r.status, r.body.len(), String::from_utf8_lossy(&r.body).contains("titlebarDrag"));
    let spec = json!({"kind": "theme", "name": "Night drive", "text": "{\"name\":\"Night drive\",\"accent\":\"#7c5cff\"}"});
    let (s, plan) = post(port, "/api/shell/save-plan", &backend.token, json!({"kind": "export", "payload": {"spec": spec}}));
    println!("save-plan -> {s} {plan}");
    let target = format!("{out}/Night drive");
    let (s, saved) = post(port, "/api/shell/save", &backend.token, json!({"kind": "export", "payload": {"spec": spec}, "path": target}));
    println!("save -> {s} {saved}");
    let written = std::fs::read_to_string(format!("{out}/Night drive.json")).unwrap_or_default();
    println!("file on disk: {written}");
    let (s, bad) = post(port, "/api/shell/save-plan", &backend.token, json!({"kind": "shared_audio", "payload": {"token": "nope"}}));
    println!("expired share -> {s} {bad}");
    let t1 = Instant::now();
    backend.stop();
    println!("stopped in {:.2}s, exited: {:?}", t1.elapsed().as_secs_f64(), backend.exited());
    let r = http::request(port, "GET", "/api/shell/hello", Some(&backend.token), None, Duration::from_secs(2));
    println!("after stop the port answers: {}", r.is_ok());
}
