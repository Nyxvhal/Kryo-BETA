//! The Python backend as a child process ("sidecar").
//!
//! The shell does not reimplement the backend. It starts the same server the
//! pywebview window uses (`--server-only`), hands it a random per-launch token
//! in `KRYONYX_SHELL_TOKEN` and waits until `GET /api/shell/hello` answers with
//! that token. The token is how the shell tells *its* backend apart from
//! another Kryonyx instance that already listens on the default port.

use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::http;

pub const DEFAULT_PORT: u16 = 8765;
/// The backend binds the first free port of `port .. port + PORT_SPAN`.
pub const PORT_SPAN: u16 = 12;
const LOG_LINES: usize = 200;

#[derive(Clone, Debug, Default)]
pub struct Options {
    /// `--backend`: a frozen KryonyxMusic executable or a `run.py`.
    pub backend: Option<PathBuf>,
    /// `--python`: the interpreter for a source checkout.
    pub python: Option<PathBuf>,
    /// `--app-dir`: the folder with `run.py` and `kryonyx/`.
    pub app_dir: Option<PathBuf>,
    pub port: Option<u16>,
    pub safe: bool,
}

/// One way to start the backend.
#[derive(Clone, Debug, PartialEq)]
pub struct Plan {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub cwd: Option<PathBuf>,
    pub describe: String,
}

type Log = Arc<Mutex<VecDeque<String>>>;

pub struct Backend {
    child: Mutex<Child>,
    pub port: u16,
    /// The port that answered `/api/shell/hello` (0 until then).
    ready_port: AtomicU16,
    pub token: String,
    pub describe: String,
    log: Log,
    #[cfg(windows)]
    _job: Option<crate::job::Job>,
}

impl Backend {
    /// Starts the first plan that can be spawned.
    ///
    /// Must run on the main thread: on Linux the child gets SIGTERM when the
    /// *thread* that spawned it ends (PR_SET_PDEATHSIG).
    pub fn start(opts: &Options) -> Result<Backend, String> {
        let plans = plans(opts);
        if plans.is_empty() {
            return Err("Kryo was not found next to the shell. Put kryonyx-shell next to \
                        Kryo.exe or run.py, or pass --backend / --app-dir."
                .to_string());
        }
        let token = new_token();
        let port = opts.port.unwrap_or(DEFAULT_PORT);
        let mut errors = Vec::new();
        for plan in plans {
            match spawn(&plan, port, opts.safe, &token) {
                Ok(mut child) => {
                    #[cfg(windows)]
                    let job = crate::job::Job::new().filter(|job| job.assign(&child));
                    let log: Log = Arc::new(Mutex::new(VecDeque::with_capacity(LOG_LINES)));
                    if let Some(out) = child.stdout.take() {
                        pump(out, log.clone());
                    }
                    if let Some(err) = child.stderr.take() {
                        pump(err, log.clone());
                    }
                    return Ok(Backend {
                        child: Mutex::new(child),
                        port,
                        ready_port: AtomicU16::new(0),
                        token,
                        describe: plan.describe,
                        log,
                        #[cfg(windows)]
                        _job: job,
                    });
                }
                Err(error) => errors.push(format!("{}: {}", plan.describe, error)),
            }
        }
        Err(format!("The backend could not be started:\n{}", errors.join("\n")))
    }

    /// `Some(reason)` once the process has ended.
    pub fn exited(&self) -> Option<String> {
        let mut child = self.child.lock().ok()?;
        match child.try_wait() {
            Ok(Some(status)) => Some(match status.code() {
                Some(code) => format!("exit code {code}"),
                None => "terminated".to_string(),
            }),
            Ok(None) => None,
            Err(error) => Some(error.to_string()),
        }
    }

    pub fn log_tail(&self, lines: usize) -> String {
        let log = match self.log.lock() {
            Ok(log) => log,
            Err(_) => return String::new(),
        };
        tail(&log, lines)
    }

    pub fn last_line(&self) -> String {
        self.log.lock().ok().and_then(|log| log.back().cloned()).unwrap_or_default()
    }

    /// Polls `/api/shell/hello` on every port the backend may have taken.
    pub fn wait_ready(
        &self,
        timeout: Duration,
        mut on_tick: impl FnMut(u64, String),
    ) -> Result<(u16, serde_json::Value), String> {
        let started = Instant::now();
        let mut reported = u64::MAX;
        loop {
            for offset in 0..PORT_SPAN {
                let Some(port) = self.port.checked_add(offset) else { break };
                let probe = http::request(
                    port,
                    "GET",
                    "/api/shell/hello",
                    Some(&self.token),
                    None,
                    Duration::from_millis(800),
                );
                if let Ok(reply) = probe {
                    if reply.status == 200 {
                        let hello = reply.json();
                        if hello.get("app").is_some() {
                            self.ready_port.store(port, Ordering::Relaxed);
                            return Ok((port, hello));
                        }
                    }
                }
            }
            if let Some(reason) = self.exited() {
                return Err(format!("The backend stopped before it was ready ({reason})."));
            }
            let seconds = started.elapsed().as_secs();
            if seconds != reported {
                reported = seconds;
                on_tick(seconds, self.last_line());
            }
            if started.elapsed() >= timeout {
                return Err(format!(
                    "The backend did not answer within {} seconds.",
                    timeout.as_secs()
                ));
            }
            std::thread::sleep(Duration::from_millis(250));
        }
    }

    /// Asks the backend to stop, then makes sure it is gone.
    pub fn stop(&self) {
        let Ok(mut child) = self.child.lock() else { return };
        if let Ok(Some(_)) = child.try_wait() {
            return;
        }
        // A clean exit first: the backend closes its jobs and the database
        // (Windows has no SIGTERM, so this is the only polite way there).
        let port = self.ready_port.load(Ordering::Relaxed);
        if port != 0 {
            let asked = http::request(
                port,
                "POST",
                "/api/shell/quit",
                Some(&self.token),
                Some(b"{}"),
                Duration::from_millis(1500),
            );
            if matches!(asked, Ok(ref reply) if reply.status == 200) && wait_exit(&mut child, Duration::from_secs(5)) {
                return;
            }
        }
        #[cfg(unix)]
        {
            unsafe {
                libc::kill(child.id() as libc::pid_t, libc::SIGTERM);
            }
            if wait_exit(&mut child, Duration::from_millis(1500)) {
                return;
            }
        }
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn wait_exit(child: &mut Child, limit: Duration) -> bool {
    let until = Instant::now() + limit;
    loop {
        if let Ok(Some(_)) = child.try_wait() {
            return true;
        }
        if Instant::now() >= until {
            return false;
        }
        std::thread::sleep(Duration::from_millis(40));
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}

pub fn tail(log: &VecDeque<String>, lines: usize) -> String {
    let skip = log.len().saturating_sub(lines);
    log.iter().skip(skip).cloned().collect::<Vec<_>>().join("\n")
}

fn pump<R: Read + Send + 'static>(reader: R, log: Log) {
    std::thread::spawn(move || {
        let mut reader = BufReader::new(reader);
        let mut buffer = Vec::new();
        loop {
            buffer.clear();
            match reader.read_until(b'\n', &mut buffer) {
                Ok(0) | Err(_) => break,
                Ok(_) => {
                    let line = String::from_utf8_lossy(&buffer).trim_end().to_string();
                    if line.is_empty() {
                        continue;
                    }
                    if let Ok(mut log) = log.lock() {
                        if log.len() >= LOG_LINES {
                            log.pop_front();
                        }
                        log.push_back(line);
                    }
                }
            }
        }
    });
}

fn spawn(plan: &Plan, port: u16, safe: bool, token: &str) -> std::io::Result<Child> {
    let mut command = Command::new(&plan.program);
    command
        .args(&plan.args)
        .arg("--server-only")
        .arg("--port")
        .arg(port.to_string());
    if safe {
        command.arg("--safe");
    }
    if let Some(dir) = &plan.cwd {
        command.current_dir(dir);
    }
    command
        .env("KRYONYX_SHELL_TOKEN", token)
        .env("KRYONYX_SHELL", "rust")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUTF8", "1")
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(target_os = "linux")]
    {
        use std::os::unix::process::CommandExt;
        unsafe {
            command.pre_exec(|| {
                libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM);
                Ok(())
            });
        }
    }
    command.spawn()
}

/// 256 bits from the standard library's randomly keyed SipHash, as 64 hex
/// characters (the backend accepts 32–256 alphanumeric characters).
pub fn new_token() -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or_default();
    let mut token = String::with_capacity(64);
    for round in 0..4u64 {
        let mut hasher = RandomState::new().build_hasher();
        hasher.write_u128(nanos);
        hasher.write_u32(std::process::id());
        hasher.write_u64(round);
        token.push_str(&format!("{:016x}", hasher.finish()));
    }
    token
}

const FROZEN: &[&str] = if cfg!(windows) { &["Kryo.exe", "KryonyxMusic.exe"] } else { &["KryonyxMusic", "kryonyx-music"] };

/// Every way to start the backend, best first.
pub fn plans(opts: &Options) -> Vec<Plan> {
    let mut out = Vec::new();
    let explicit = opts
        .backend
        .clone()
        .or_else(|| std::env::var_os("KRYONYX_BACKEND").map(PathBuf::from));
    if let Some(path) = explicit {
        if is_script(&path) {
            let root = path.parent().map(Path::to_path_buf);
            for (program, mut args) in pythons(opts, root.as_deref()) {
                args.push(path.display().to_string());
                out.push(Plan {
                    describe: format!("{} {}", program.display(), args.join(" ")),
                    program,
                    args,
                    cwd: root.clone(),
                });
            }
        } else {
            out.push(Plan {
                describe: path.display().to_string(),
                cwd: path.parent().map(Path::to_path_buf),
                program: path,
                args: Vec::new(),
            });
        }
        return out;
    }

    let me = std::env::current_exe().ok().and_then(|p| dunce::canonicalize(p).ok());
    if let Some(dir) = me.as_ref().and_then(|p| p.parent().map(Path::to_path_buf)) {
        for name in FROZEN {
            let candidate = dir.join(name);
            let same = dunce::canonicalize(&candidate).ok() == me;
            if candidate.is_file() && !same {
                out.push(Plan {
                    describe: candidate.display().to_string(),
                    program: candidate,
                    args: Vec::new(),
                    cwd: Some(dir.clone()),
                });
            }
        }
    }

    let mut starts: Vec<PathBuf> = Vec::new();
    if let Some(dir) = &opts.app_dir {
        starts.push(dir.clone());
    }
    if let Some(dir) = me.as_ref().and_then(|p| p.parent().map(Path::to_path_buf)) {
        starts.push(dir);
    }
    if let Ok(dir) = std::env::current_dir() {
        starts.push(dir);
    }
    if let Some(root) = starts.iter().find_map(|dir| source_root(dir)) {
        let script = root.join("run.py");
        for (program, mut args) in pythons(opts, Some(&root)) {
            args.push(script.display().to_string());
            out.push(Plan {
                describe: format!("{} {}", program.display(), args.join(" ")),
                program,
                args,
                cwd: Some(root.clone()),
            });
        }
    }
    out
}

fn is_script(path: &Path) -> bool {
    path.extension().map(|e| e.eq_ignore_ascii_case("py")).unwrap_or(false)
}

/// The nearest folder (this one or up to six parents) with `run.py` and the
/// `kryonyx` package.
pub fn source_root(start: &Path) -> Option<PathBuf> {
    let mut dir = Some(start);
    for _ in 0..7 {
        let here = dir?;
        if here.join("run.py").is_file() && here.join("kryonyx").join("__init__.py").is_file() {
            return Some(here.to_path_buf());
        }
        dir = here.parent();
    }
    None
}

/// Interpreters to try for a source checkout: explicit first, then a local
/// virtual environment, then the ones on PATH.
fn pythons(opts: &Options, root: Option<&Path>) -> Vec<(PathBuf, Vec<String>)> {
    if let Some(python) = opts
        .python
        .clone()
        .or_else(|| std::env::var_os("KRYONYX_PYTHON").map(PathBuf::from))
    {
        return vec![(python, Vec::new())];
    }
    let mut out = Vec::new();
    if let Some(root) = root {
        for venv in [".venv", "venv"] {
            let python = if cfg!(windows) {
                root.join(venv).join("Scripts").join("python.exe")
            } else {
                root.join(venv).join("bin").join("python3")
            };
            if python.is_file() {
                out.push((python, Vec::new()));
            }
        }
    }
    if cfg!(windows) {
        out.push((PathBuf::from("py"), vec!["-3".to_string()]));
        out.push((PathBuf::from("python"), Vec::new()));
        out.push((PathBuf::from("python3"), Vec::new()));
    } else {
        out.push((PathBuf::from("python3"), Vec::new()));
        out.push((PathBuf::from("python"), Vec::new()));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_is_long_alphanumeric_and_unique() {
        let a = new_token();
        let b = new_token();
        assert_eq!(a.len(), 64);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    #[test]
    fn finds_the_source_root_from_a_nested_folder() {
        let base = std::env::temp_dir().join(format!("kryonyx-shell-test-{}", std::process::id()));
        let nested = base.join("desktop-rs").join("target").join("release");
        std::fs::create_dir_all(&nested).unwrap();
        std::fs::create_dir_all(base.join("kryonyx")).unwrap();
        std::fs::write(base.join("run.py"), "").unwrap();
        std::fs::write(base.join("kryonyx").join("__init__.py"), "").unwrap();
        assert_eq!(source_root(&nested), Some(base.clone()));
        let opts = Options { app_dir: Some(nested.clone()), python: Some(PathBuf::from("py-test")), ..Default::default() };
        let found = plans(&opts);
        let last = found.last().expect("a source plan");
        assert_eq!(last.program, PathBuf::from("py-test"));
        assert!(last.args.last().unwrap().ends_with("run.py"));
        assert_eq!(last.cwd.as_deref(), Some(base.as_path()));
        std::fs::remove_dir_all(&base).unwrap();
    }

    #[test]
    fn explicit_script_uses_python() {
        let opts = Options {
            backend: Some(PathBuf::from("/opt/kryonyx/run.py")),
            python: Some(PathBuf::from("/usr/bin/python3")),
            ..Default::default()
        };
        let found = plans(&opts);
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].program, PathBuf::from("/usr/bin/python3"));
        assert_eq!(found[0].args, vec!["/opt/kryonyx/run.py".to_string()]);
    }

    #[test]
    fn tail_keeps_the_last_lines() {
        let log: VecDeque<String> = (1..=5).map(|i| i.to_string()).collect();
        assert_eq!(tail(&log, 2), "4\n5");
        assert_eq!(tail(&log, 10), "1\n2\n3\n4\n5");
    }
}
