//! The platform-independent half of the Kryonyx shell (desktop-rs).
//!
//! Everything here builds and is tested without a window system: the
//! backend sidecar (start, readiness, clean stop), the JavaScript bridge and
//! its message format, the command line and the window-state file. The
//! window itself (tao + wry) lives in the `kryonyx-shell` binary.

pub mod bridge;
pub mod cli;
pub mod http;
#[cfg(windows)]
pub mod job;
pub mod sidecar;
pub mod winstate;
