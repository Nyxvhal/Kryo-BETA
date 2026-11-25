//! Command line of the shell. Pure code, tested on every platform.

use std::path::PathBuf;

use crate::{bridge, sidecar};

pub const USAGE: &str = "kryonyx-shell — native window for Kryo (the backend stays Python)

Usage: kryonyx-shell [options]

  --backend PATH   Kryo executable or run.py to start (default: next to
                   the shell, then the source checkout around it)
  --python PATH    Python for a source checkout (default: .venv, py -3, python3)
  --app-dir DIR    folder with run.py and kryonyx/
  --port N         first port to try (default 8765; the backend tries 12)
  --safe           light mode: no atmosphere, wallpapers or animations
  --url URL        attach to an already running backend (development; Save As
                   needs the backend started by the shell)
  --devtools       allow the inspector, context menus and browser hotkeys
  -h, --help       this text
  -V, --version    version

Environment: KRYONYX_BACKEND, KRYONYX_PYTHON.";

#[derive(Default)]
pub struct Args {
    pub opts: sidecar::Options,
    pub url: Option<String>,
    pub devtools: bool,
}

pub enum Parsed {
    Run(Args),
    Exit(String),
}

fn take(it: &mut impl Iterator<Item = String>, inline: Option<String>, name: &str) -> Result<String, String> {
    inline.or_else(|| it.next()).filter(|v| !v.is_empty()).ok_or_else(|| format!("{name} needs a value"))
}

pub fn parse_args(raw: Vec<String>) -> Result<Parsed, String> {
    let mut args = Args::default();
    let mut it = raw.into_iter();
    while let Some(arg) = it.next() {
        let (key, inline) = match arg.split_once('=') {
            Some((k, v)) if k.starts_with("--") => (k.to_string(), Some(v.to_string())),
            _ => (arg.clone(), None),
        };
        match key.as_str() {
            "-h" | "--help" => return Ok(Parsed::Exit(USAGE.to_string())),
            "-V" | "--version" => {
                return Ok(Parsed::Exit(format!("kryonyx-shell {}", env!("CARGO_PKG_VERSION"))))
            }
            "--backend" => args.opts.backend = Some(PathBuf::from(take(&mut it, inline, "--backend")?)),
            "--python" => args.opts.python = Some(PathBuf::from(take(&mut it, inline, "--python")?)),
            "--app-dir" => args.opts.app_dir = Some(PathBuf::from(take(&mut it, inline, "--app-dir")?)),
            "--port" => {
                let value = take(&mut it, inline, "--port")?;
                let port = value.parse::<u16>().ok().filter(|p| *p >= 1024);
                args.opts.port = Some(port.ok_or("--port expects a number from 1024 to 65535")?);
            }
            "--safe" => args.opts.safe = true,
            "--url" => {
                let value = take(&mut it, inline, "--url")?;
                if !bridge::origin_of(&value).is_some_and(|o| bridge::is_loopback_origin(&o)) {
                    return Err("--url expects http://127.0.0.1:PORT/".to_string());
                }
                args.url = Some(value);
            }
            "--devtools" => args.devtools = true,
            other => return Err(format!("Unknown option: {other}\n\n{USAGE}")),
        }
    }
    Ok(Parsed::Run(args))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(args: &[&str]) -> Result<Parsed, String> {
        parse_args(args.iter().map(|s| s.to_string()).collect())
    }

    #[test]
    fn parses_options() {
        let Ok(Parsed::Run(a)) = run(&["--port", "9000", "--safe", "--backend=C:/K/Kryo.exe"]) else {
            panic!("expected options")
        };
        assert_eq!(a.opts.port, Some(9000));
        assert!(a.opts.safe);
        assert_eq!(a.opts.backend, Some(PathBuf::from("C:/K/Kryo.exe")));
        assert!(!a.devtools);
        let Ok(Parsed::Run(b)) = run(&["--url", "http://127.0.0.1:8765/", "--devtools", "--app-dir", "D:/src"]) else {
            panic!("expected options")
        };
        assert_eq!(b.url.as_deref(), Some("http://127.0.0.1:8765/"));
        assert!(b.devtools);
        assert_eq!(b.opts.app_dir, Some(PathBuf::from("D:/src")));
    }

    #[test]
    fn rejects_bad_options() {
        assert!(matches!(run(&["--help"]), Ok(Parsed::Exit(_))));
        assert!(matches!(run(&["-V"]), Ok(Parsed::Exit(v)) if v == format!("kryonyx-shell {}", env!("CARGO_PKG_VERSION"))));
        assert!(run(&["--port", "80"]).is_err());
        assert!(run(&["--port", "70000"]).is_err());
        assert!(run(&["--port=abc"]).is_err());
        assert!(run(&["--url", "file:///x"]).is_err());
        assert!(run(&["--url", "https://example.com/"]).is_err());
        assert!(run(&["--wat"]).is_err());
        assert!(run(&["--python"]).is_err());
        assert!(run(&["--backend="]).is_err());
    }
}
