//! The shell's own window state: size, position, maximized, mini player.
//!
//! Same rules as `window.json` of the pywebview window (kryonyx/main.py):
//! "remember" is on by default, and the (-32000, -32000) position Windows
//! reports for a minimized window is never stored.

use std::path::PathBuf;

use serde_json::{Map, Value};

/// Anything at or beyond this is a minimized / hidden window.
pub const OFFSCREEN: f64 = -30000.0;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Bounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Clone, Debug)]
pub struct State {
    path: PathBuf,
    data: Map<String, Value>,
}

fn get(data: &Map<String, Value>, key: &str) -> Option<f64> {
    data.get(key).and_then(Value::as_f64).filter(|v| v.is_finite())
}

impl State {
    pub fn load(path: PathBuf) -> State {
        let data = std::fs::read(&path)
            .ok()
            .and_then(|raw| serde_json::from_slice::<Value>(&raw).ok())
            .and_then(|value| match value {
                Value::Object(map) => Some(map),
                _ => None,
            })
            .unwrap_or_default();
        State { path, data }
    }

    pub fn remember(&self) -> bool {
        self.data.get("remember").and_then(Value::as_bool).unwrap_or(true)
    }

    pub fn set_remember(&mut self, on: bool) {
        self.data.insert("remember".into(), Value::Bool(on));
    }

    /// The saved main window bounds, only if they are plausible.
    pub fn bounds(&self, min_width: f64, min_height: f64) -> Option<Bounds> {
        let (x, y) = (get(&self.data, "x")?, get(&self.data, "y")?);
        let (width, height) = (get(&self.data, "width")?, get(&self.data, "height")?);
        if x <= OFFSCREEN || y <= OFFSCREEN || width < min_width || height < min_height {
            return None;
        }
        Some(Bounds { x, y, width, height })
    }

    /// Stores the bounds unless they belong to a minimized window.
    pub fn set_bounds(&mut self, bounds: Bounds) -> bool {
        if bounds.x <= OFFSCREEN || bounds.y <= OFFSCREEN || bounds.width < 1.0 || bounds.height < 1.0 {
            return false;
        }
        for (key, value) in [("x", bounds.x), ("y", bounds.y), ("width", bounds.width), ("height", bounds.height)] {
            self.data.insert(key.into(), Value::from(value.round() as i64));
        }
        true
    }

    pub fn maximized(&self) -> bool {
        self.data.get("maximized").and_then(Value::as_bool).unwrap_or(false)
    }

    pub fn set_maximized(&mut self, on: bool) {
        self.data.insert("maximized".into(), Value::Bool(on));
    }

    pub fn mini_position(&self) -> Option<(f64, f64)> {
        let (x, y) = (get(&self.data, "mini_x")?, get(&self.data, "mini_y")?);
        (x > OFFSCREEN && y > OFFSCREEN).then_some((x, y))
    }

    pub fn set_mini_position(&mut self, x: f64, y: f64) {
        if x > OFFSCREEN && y > OFFSCREEN {
            self.data.insert("mini_x".into(), Value::from(x.round() as i64));
            self.data.insert("mini_y".into(), Value::from(y.round() as i64));
        }
    }

    pub fn mini_size(&self) -> Option<(f64, f64)> {
        Some((get(&self.data, "mini_w")?, get(&self.data, "mini_h")?))
    }

    pub fn set_mini_size(&mut self, width: f64, height: f64) {
        if width >= 300.0 && height >= 110.0 {
            self.data.insert("mini_w".into(), Value::from(width.round() as i64));
            self.data.insert("mini_h".into(), Value::from(height.round() as i64));
        }
    }

    /// Atomic write: a crash mid-write never leaves a broken file behind.
    pub fn save(&self) -> std::io::Result<()> {
        if let Some(dir) = self.path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let text = serde_json::to_vec_pretty(&Value::Object(self.data.clone()))?;
        let temp = self.path.with_extension("json.tmp");
        std::fs::write(&temp, text)?;
        std::fs::rename(&temp, &self.path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn remembers_by_default_and_round_trips() {
        let dir = std::env::temp_dir().join(format!("kryonyx-state-{}", std::process::id()));
        let path = dir.join("shell.json");
        let mut state = State::load(path.clone());
        assert!(state.remember());
        assert_eq!(state.bounds(400.0, 560.0), None);
        assert!(state.set_bounds(Bounds { x: 10.0, y: 20.0, width: 1200.0, height: 800.0 }));
        assert!(!state.set_bounds(Bounds { x: -32000.0, y: -32000.0, width: 160.0, height: 28.0 }));
        state.set_maximized(true);
        state.set_mini_position(1500.0, 900.0);
        state.set_mini_size(200.0, 50.0);
        state.save().unwrap();
        let again = State::load(path);
        assert_eq!(again.bounds(400.0, 560.0), Some(Bounds { x: 10.0, y: 20.0, width: 1200.0, height: 800.0 }));
        assert!(again.maximized());
        assert_eq!(again.mini_position(), Some((1500.0, 900.0)));
        assert_eq!(again.mini_size(), None);
        std::fs::remove_dir_all(dir).unwrap();
    }
}
