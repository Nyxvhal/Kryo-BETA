//! Writes the bridge scripts that the shell injects, for the browser test
//! tests/browser_shell_v73.cjs: `cargo run -p kryonyx-shell-core --example dump_shim -- OUT_DIR`.
use kryonyx_shell_core::bridge;
fn main() {
    let out = std::env::args().nth(1).expect("out dir");
    std::fs::write(format!("{out}/shim-main.js"), bridge::shim(bridge::MAIN_API, bridge::MAIN_DRAG)).unwrap();
    std::fs::write(format!("{out}/shim-mini.js"), bridge::shim(bridge::MINI_API, bridge::MINI_DRAG)).unwrap();
    // The scripts that the shell evaluates in the page.
    let v = serde_json::json!({"title": "</script><b>x</b>", "n": 1.5, "s": "\u{2028}"});
    std::fs::write(format!("{out}/resolve.js"), bridge::resolve_js(7, true, &v)).unwrap();
    std::fs::write(format!("{out}/call.js"), bridge::call_js("window.Frame&&window.Frame.applyMax", "window.Frame.applyMax", &serde_json::json!(true))).unwrap();
}
