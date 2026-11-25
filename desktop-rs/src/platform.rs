//! Small platform helpers: work area of a monitor, opening links in the
//! system browser and the folder for the shell's own state file.

use std::path::PathBuf;

use tao::window::Window;

/// Visible work area of the monitor the window is on, in logical pixels
/// (taskbar / dock excluded where the platform reports it).
pub fn work_area(window: &Window) -> Option<(f64, f64, f64, f64)> {
    let monitor = window.current_monitor().or_else(|| window.primary_monitor())?;
    let scale = window.scale_factor().max(0.1);
    #[cfg(windows)]
    {
        use tao::platform::windows::MonitorHandleExtWindows;
        use windows_sys::Win32::Graphics::Gdi::{GetMonitorInfoW, MONITORINFO};
        let mut info: MONITORINFO = unsafe { std::mem::zeroed() };
        info.cbSize = std::mem::size_of::<MONITORINFO>() as u32;
        let ok = unsafe { GetMonitorInfoW(monitor.hmonitor() as _, &mut info) };
        if ok != 0 {
            let r = info.rcWork;
            return Some((
                r.left as f64 / scale,
                r.top as f64 / scale,
                (r.right - r.left) as f64 / scale,
                (r.bottom - r.top) as f64 / scale,
            ));
        }
    }
    let pos = monitor.position();
    let size = monitor.size();
    Some((
        pos.x as f64 / scale,
        pos.y as f64 / scale,
        size.width as f64 / scale,
        size.height as f64 / scale,
    ))
}

pub fn open_external(url: &str) {
    if !kryonyx_shell_core::bridge::is_external_link(url) {
        return;
    }
    #[cfg(windows)]
    {
        use windows_sys::Win32::UI::Shell::ShellExecuteW;
        use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
        let wide = |s: &str| s.encode_utf16().chain(std::iter::once(0)).collect::<Vec<u16>>();
        let (verb, target) = (wide("open"), wide(url));
        unsafe {
            ShellExecuteW(
                std::ptr::null_mut(),
                verb.as_ptr(),
                target.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                SW_SHOWNORMAL,
            );
        }
    }
    #[cfg(target_os = "macos")]
    {
        let _ = std::process::Command::new("open").arg(url).spawn();
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let _ = std::process::Command::new("xdg-open").arg(url).spawn();
    }
}

/// Where the shell keeps its own small state file (window bounds).
pub fn config_dir() -> PathBuf {
    let env = |k: &str| std::env::var_os(k).map(PathBuf::from);
    #[cfg(windows)]
    let base = env("LOCALAPPDATA").or_else(|| env("APPDATA")).map(|p| p.join("KryonyxMusic").join("shell"));
    #[cfg(target_os = "macos")]
    let base = env("HOME").map(|p| p.join("Library/Application Support/KryonyxMusic/shell"));
    #[cfg(all(unix, not(target_os = "macos")))]
    let base = env("XDG_CONFIG_HOME")
        .or_else(|| env("HOME").map(|h| h.join(".config")))
        .map(|p| p.join("kryonyx-music").join("shell"));
    base.unwrap_or_else(|| std::env::temp_dir().join("kryonyx-shell"))
}
