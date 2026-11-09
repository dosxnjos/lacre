//! Bridge to the Python engine: a long-lived child process speaking JSON Lines on stdin/stdout
//! (contract: docs/PROTOCOL.md).
//!
//! - `Router` matches response lines to pending requests by `id` and recognises event lines.
//! - `Engine` owns the child process: spawn, write requests, read stdout on a thread, drain stderr,
//!   restart with backoff when the engine dies, and send `shutdown` on app exit.
//!
//! Nothing here depends on Tauri: the shell plugs in an `EventSink` that emits Tauri events, and the
//! tests plug in a closure that records what was forwarded.

use std::collections::HashMap;
use std::ffi::OsString;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::{json, Value};
use tokio::sync::oneshot;

/// Protocol version written on every request.
pub const PROTOCOL_VERSION: u64 = 1;

/// Id of the `shutdown` request the shell sends on exit (its response has no waiter).
const SHUTDOWN_ID: &str = "shell-shutdown";

/// Result of one request: `Ok(data)` or `Err(error object {code, detail})`.
pub type Outcome = Result<Value, Value>;

/// Builds an error object with a code from PROTOCOL.md and a short technical detail.
pub fn error_obj(code: &str, detail: &str) -> Value {
    json!({ "code": code, "detail": detail })
}

fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    // A panic while holding one of these locks must not take the whole bridge down.
    m.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

// ---------------------------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------------------------

/// What a single stdout line turned out to be.
#[derive(Debug, PartialEq)]
pub enum Routed {
    /// A response that was delivered to the pending request with this id.
    Delivered(String),
    /// A response whose id nobody is waiting for (late, cancelled or timed out).
    Unmatched(String),
    /// An event line (`"event"` key present); carries the full JSON line.
    Event(Value),
    /// Blank, not JSON, or not a protocol object.
    Invalid,
}

/// Pending requests keyed by id; each one waits on a oneshot channel.
#[derive(Default)]
pub struct Router {
    pending: Mutex<HashMap<String, oneshot::Sender<Outcome>>>,
}

impl Router {
    /// Registers a pending request. Fails if the id is already waiting.
    pub fn register(&self, id: &str) -> Result<oneshot::Receiver<Outcome>, String> {
        let mut pending = lock(&self.pending);
        if pending.contains_key(id) {
            return Err(format!("duplicate request id {id}"));
        }
        let (tx, rx) = oneshot::channel();
        pending.insert(id.to_string(), tx);
        Ok(rx)
    }

    /// Forgets a pending request (timeout, write failure). Its receiver gets nothing more.
    pub fn forget(&self, id: &str) {
        lock(&self.pending).remove(id);
    }

    pub fn pending_count(&self) -> usize {
        lock(&self.pending).len()
    }

    /// Classifies one stdout line and delivers it if it is a response.
    pub fn route_line(&self, line: &str) -> Routed {
        let line = line.trim();
        if line.is_empty() {
            return Routed::Invalid;
        }
        let Ok(value) = serde_json::from_str::<Value>(line) else {
            return Routed::Invalid;
        };
        let Some(obj) = value.as_object() else {
            return Routed::Invalid;
        };
        if obj.contains_key("event") {
            return Routed::Event(value);
        }
        let Some(id) = obj.get("id").and_then(Value::as_str).map(str::to_string) else {
            return Routed::Invalid;
        };
        let outcome = if obj.get("ok").and_then(Value::as_bool) == Some(true) {
            Ok(obj.get("data").cloned().unwrap_or(Value::Null))
        } else {
            let err = obj
                .get("error")
                .cloned()
                .filter(|e| e.get("code").is_some());
            Err(err.unwrap_or_else(|| error_obj("internal", "malformed engine response")))
        };
        match lock(&self.pending).remove(&id) {
            Some(tx) => {
                // The receiver may be gone (caller dropped); that is not an error here.
                let _ = tx.send(outcome);
                Routed::Delivered(id)
            }
            None => Routed::Unmatched(id),
        }
    }

    /// Fails every pending request with the same error (engine died or is shutting down).
    pub fn fail_all(&self, error: &Value) {
        let drained: Vec<_> = lock(&self.pending).drain().collect();
        for (_, tx) in drained {
            let _ = tx.send(Err(error.clone()));
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Launch spec
// ---------------------------------------------------------------------------------------------

/// How the engine runs: from source via `uv` ("dev") or as the frozen PyInstaller build ("bundled").
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Dev,
    Bundled,
}

#[derive(Clone, Debug)]
pub struct Launch {
    pub program: OsString,
    pub args: Vec<OsString>,
    pub cwd: Option<PathBuf>,
    pub mode: Mode,
}

impl Launch {
    /// `uv run --project <repo>/engine python -m lacre_engine`
    pub fn dev(engine_dir: PathBuf) -> Self {
        Launch {
            program: "uv".into(),
            args: vec![
                "run".into(),
                "--project".into(),
                engine_dir.clone().into_os_string(),
                "python".into(),
                "-m".into(),
                "lacre_engine".into(),
            ],
            cwd: Some(engine_dir),
            mode: Mode::Dev,
        }
    }

    /// The frozen executable (`engine/lacre-engine(.exe)` inside the app resources).
    pub fn bundled(exe: PathBuf) -> Self {
        let cwd = exe.parent().map(PathBuf::from);
        Launch {
            program: exe.into_os_string(),
            args: vec![],
            cwd,
            mode: Mode::Bundled,
        }
    }

    fn command(&self) -> Command {
        let mut cmd = Command::new(&self.program);
        cmd.args(&self.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env("PYTHONUNBUFFERED", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUTF8", "1");
        if let Some(cwd) = &self.cwd {
            cmd.current_dir(cwd);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        cmd
    }
}

/// File name of the frozen engine inside the `engine/` resource folder.
pub fn bundled_exe_name() -> &'static str {
    if cfg!(windows) {
        "lacre-engine.exe"
    } else {
        "lacre-engine"
    }
}

// ---------------------------------------------------------------------------------------------
// Engine process
// ---------------------------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct EngineStatus {
    pub running: bool,
    pub mode: Mode,
}

/// What the bridge pushes to the frontend.
#[derive(Debug)]
pub enum Signal {
    /// A protocol event line, forwarded verbatim (Tauri event `engine-event`).
    Event(Value),
    /// Engine started or stopped (Tauri event `engine-status`).
    Status(EngineStatus),
}

pub type EventSink = Arc<dyn Fn(Signal) + Send + Sync>;

/// Restart policy: at most this many attempts inside the window, with exponential backoff.
const RESTART_MAX: usize = 5;
const RESTART_WINDOW: Duration = Duration::from_secs(60);
const RESTART_BASE_DELAY: Duration = Duration::from_millis(300);
const RESTART_MAX_DELAY: Duration = Duration::from_secs(5);

#[derive(Default)]
struct Proc {
    stdin: Option<ChildStdin>,
    child: Option<Child>,
    /// Incremented on every spawn so a stale reader thread cannot clobber a newer process.
    generation: u64,
}

pub struct Engine {
    launch: Launch,
    sink: EventSink,
    router: Router,
    proc: Mutex<Proc>,
    running: AtomicBool,
    shutting_down: AtomicBool,
    restarting: AtomicBool,
    restart_log: Mutex<Vec<Instant>>,
    next_id: AtomicU64,
}

impl Engine {
    pub fn new(launch: Launch, sink: EventSink) -> Arc<Self> {
        Arc::new(Engine {
            launch,
            sink,
            router: Router::default(),
            proc: Mutex::new(Proc::default()),
            running: AtomicBool::new(false),
            shutting_down: AtomicBool::new(false),
            restarting: AtomicBool::new(false),
            restart_log: Mutex::new(Vec::new()),
            next_id: AtomicU64::new(1),
        })
    }

    pub fn status(&self) -> EngineStatus {
        EngineStatus {
            running: self.running.load(Ordering::SeqCst),
            mode: self.launch.mode,
        }
    }

    fn emit_status(&self) {
        (self.sink)(Signal::Status(self.status()));
    }

    /// Starts the engine; on failure, retries in the background with backoff.
    pub fn start_or_retry(self: &Arc<Self>) {
        if let Err(e) = self.start() {
            eprintln!("[lacre] engine failed to start: {e}");
            self.schedule_restart();
        }
    }

    /// Spawns the engine process if it is not running. Idempotent.
    pub fn start(self: &Arc<Self>) -> std::io::Result<()> {
        if self.shutting_down.load(Ordering::SeqCst) {
            return Err(std::io::Error::other("shutting down"));
        }
        let mut proc = lock(&self.proc);
        if proc.stdin.is_some() {
            return Ok(());
        }
        let mut child = self.launch.command().spawn()?;
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        proc.generation += 1;
        let generation = proc.generation;
        proc.stdin = stdin;
        proc.child = Some(child);
        self.running.store(true, Ordering::SeqCst);
        drop(proc);

        if let Some(stderr) = stderr {
            // Must be drained, or the engine blocks once the pipe buffer fills.
            std::thread::Builder::new()
                .name("lacre-engine-stderr".into())
                .spawn(move || drain_stderr(stderr))?;
        }
        if let Some(stdout) = stdout {
            let me = Arc::clone(self);
            std::thread::Builder::new()
                .name("lacre-engine-stdout".into())
                .spawn(move || {
                    me.read_stdout(stdout);
                    me.on_exit(generation);
                })?;
        }
        self.emit_status();
        Ok(())
    }

    fn read_stdout(&self, stdout: impl Read) {
        let mut reader = BufReader::new(stdout);
        let mut buf = Vec::with_capacity(64 * 1024);
        loop {
            buf.clear();
            match reader.read_until(b'\n', &mut buf) {
                Ok(0) => break,
                Ok(_) => {
                    self.handle_line(&String::from_utf8_lossy(&buf));
                }
                Err(e) => {
                    eprintln!("[lacre] engine stdout read error: {e}");
                    break;
                }
            }
        }
    }

    /// Routes one stdout line: responses to their waiter, events to the frontend.
    pub fn handle_line(&self, line: &str) -> Routed {
        let routed = self.router.route_line(line);
        match &routed {
            Routed::Event(v) => (self.sink)(Signal::Event(v.clone())),
            Routed::Unmatched(id) if id != SHUTDOWN_ID => {
                eprintln!("[lacre] engine response for unknown id {id}")
            }
            Routed::Invalid if !line.trim().is_empty() => {
                eprintln!(
                    "[lacre] ignoring non-protocol engine output: {}",
                    truncate(line.trim(), 200)
                )
            }
            _ => {}
        }
        routed
    }

    /// Called by the stdout thread at EOF: reap the child, fail pending requests, maybe restart.
    fn on_exit(self: &Arc<Self>, generation: u64) {
        let child = {
            let mut proc = lock(&self.proc);
            if proc.generation != generation {
                return;
            }
            proc.stdin = None;
            proc.child.take()
        };
        if let Some(mut child) = child {
            match child.wait() {
                Ok(status) => eprintln!("[lacre] engine exited: {status}"),
                Err(e) => eprintln!("[lacre] engine wait failed: {e}"),
            }
        }
        self.running.store(false, Ordering::SeqCst);
        let shutting_down = self.shutting_down.load(Ordering::SeqCst);
        let detail = if shutting_down {
            "engine_shutdown"
        } else {
            "engine_exited"
        };
        self.router.fail_all(&error_obj("internal", detail));
        self.emit_status();
        if !shutting_down {
            self.schedule_restart();
        }
    }

    /// Background restart with exponential backoff, capped at `RESTART_MAX` attempts per window.
    fn schedule_restart(self: &Arc<Self>) {
        if self.restarting.swap(true, Ordering::SeqCst) {
            return;
        }
        let me = Arc::clone(self);
        let spawned = std::thread::Builder::new()
            .name("lacre-engine-restart".into())
            .spawn(move || {
                loop {
                    let delay = {
                        let mut log = lock(&me.restart_log);
                        let now = Instant::now();
                        log.retain(|t| now.duration_since(*t) < RESTART_WINDOW);
                        if log.len() >= RESTART_MAX {
                            eprintln!(
                                "[lacre] engine keeps dying; giving up until the next request"
                            );
                            break;
                        }
                        log.push(now);
                        let exp = u32::try_from(log.len() - 1).unwrap_or(u32::MAX).min(8);
                        (RESTART_BASE_DELAY * 2u32.pow(exp)).min(RESTART_MAX_DELAY)
                    };
                    std::thread::sleep(delay);
                    if me.shutting_down.load(Ordering::SeqCst) {
                        break;
                    }
                    match me.start() {
                        Ok(()) => break,
                        Err(e) => eprintln!("[lacre] engine restart failed: {e}"),
                    }
                }
                me.restarting.store(false, Ordering::SeqCst);
            });
        if spawned.is_err() {
            self.restarting.store(false, Ordering::SeqCst);
        }
    }

    fn write_line(&self, line: &str) -> Result<(), Value> {
        let mut proc = lock(&self.proc);
        let Some(stdin) = proc.stdin.as_mut() else {
            return Err(error_obj("internal", "engine_not_running"));
        };
        let res = stdin
            .write_all(line.as_bytes())
            .and_then(|_| stdin.write_all(b"\n"))
            .and_then(|_| stdin.flush());
        res.map_err(|e| error_obj("internal", &format!("engine_write_failed: {e}")))
    }

    /// Generates a fresh request id.
    pub fn new_id(&self) -> String {
        format!("ui-{}", self.next_id.fetch_add(1, Ordering::SeqCst))
    }

    /// Sends one request and waits for its response. Never holds a lock across the await, so
    /// long requests (`read`, `fdr`) do not block others.
    pub async fn request(
        self: &Arc<Self>,
        id: String,
        cmd: &str,
        args: Value,
        timeout: Duration,
    ) -> Outcome {
        if !self.running.load(Ordering::SeqCst) && !self.restarting.load(Ordering::SeqCst) {
            // The restart budget may have run out earlier; a new request is a fresh chance.
            if let Err(e) = self.start() {
                return Err(error_obj("internal", &format!("engine_not_running: {e}")));
            }
        }
        let rx = self
            .router
            .register(&id)
            .map_err(|e| error_obj("internal", &e))?;
        let line = json!({ "v": PROTOCOL_VERSION, "id": id, "cmd": cmd, "args": args }).to_string();
        if let Err(e) = self.write_line(&line) {
            self.router.forget(&id);
            return Err(e);
        }
        match tokio::time::timeout(timeout, rx).await {
            Ok(Ok(outcome)) => outcome,
            Ok(Err(_)) => Err(error_obj("internal", "engine_dropped_request")),
            Err(_) => {
                self.router.forget(&id);
                Err(error_obj("timeout", "shell_timeout"))
            }
        }
    }

    /// Asks the engine to exit (`shutdown`), waits up to `grace`, then kills it. No restart after.
    pub fn shutdown(&self, grace: Duration) {
        self.shutting_down.store(true, Ordering::SeqCst);
        let line =
            json!({ "v": PROTOCOL_VERSION, "id": SHUTDOWN_ID, "cmd": "shutdown", "args": {} })
                .to_string();
        let _ = self.write_line(&line);
        let child = {
            let mut proc = lock(&self.proc);
            proc.stdin = None; // closing stdin is a second "please exit" signal
            proc.child.take()
        };
        if let Some(mut child) = child {
            let deadline = Instant::now() + grace;
            loop {
                match child.try_wait() {
                    Ok(Some(_)) => break,
                    Ok(None) if Instant::now() < deadline => {
                        std::thread::sleep(Duration::from_millis(50))
                    }
                    _ => {
                        let _ = child.kill();
                        let _ = child.wait();
                        break;
                    }
                }
            }
        }
        self.running.store(false, Ordering::SeqCst);
        self.router
            .fail_all(&error_obj("internal", "engine_shutdown"));
    }
}

/// Default time the shell waits for a response before giving up with `timeout`.
pub fn timeout_for(cmd: &str, args: &Value) -> Duration {
    match cmd {
        // The engine has its own wait (default 900 s for the user to press the buttons);
        // add room for generating, downloading and cleaning the sysdiagnose.
        "fdr" => {
            let engine_wait = args.get("timeout_s").and_then(Value::as_u64).unwrap_or(900);
            Duration::from_secs(engine_wait.saturating_add(600))
        }
        "read" => Duration::from_secs(300),
        "analyze" => Duration::from_secs(120),
        _ => Duration::from_secs(60),
    }
}

/// Where the engine's stderr (its log) is appended. Set once at startup by the app; unset in tests.
pub static ENGINE_LOG: std::sync::OnceLock<PathBuf> = std::sync::OnceLock::new();
const ENGINE_LOG_MAX_BYTES: u64 = 2 * 1024 * 1024;

fn open_engine_log() -> Option<std::fs::File> {
    let path = ENGINE_LOG.get()?;
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    // Keep the log small: start over once it passes the cap (previous run kept as .old).
    if std::fs::metadata(path).map(|m| m.len() > ENGINE_LOG_MAX_BYTES).unwrap_or(false) {
        let _ = std::fs::rename(path, path.with_extension("log.old"));
    }
    std::fs::OpenOptions::new().create(true).append(true).open(path).ok()
}

fn drain_stderr(stderr: impl Read) {
    use std::io::Write as _;
    let mut reader = BufReader::new(stderr);
    let mut buf = Vec::new();
    let mut log = open_engine_log();
    if let Some(f) = log.as_mut() {
        let secs = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(f, "---- engine started (unix {secs}) ----");
    }
    loop {
        buf.clear();
        match reader.read_until(b'\n', &mut buf) {
            Ok(0) | Err(_) => break,
            Ok(_) => {
                if cfg!(debug_assertions) {
                    eprint!("[engine] {}", String::from_utf8_lossy(&buf));
                }
                if let Some(f) = log.as_mut() {
                    let _ = f.write_all(&buf);
                }
            }
        }
    }
}

fn truncate(s: &str, max: usize) -> &str {
    match s.char_indices().nth(max) {
        Some((i, _)) => &s[..i],
        None => s,
    }
}

// ---------------------------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn recording_sink() -> (EventSink, Arc<Mutex<Vec<Value>>>) {
        let seen = Arc::new(Mutex::new(Vec::new()));
        let seen2 = Arc::clone(&seen);
        let sink: EventSink = Arc::new(move |s| {
            if let Signal::Event(v) = s {
                seen2.lock().unwrap().push(v);
            }
        });
        (sink, seen)
    }

    #[test]
    fn response_goes_to_matching_id_only() {
        let r = Router::default();
        let mut a = r.register("a").unwrap();
        let mut b = r.register("b").unwrap();
        let routed = r.route_line(r#"{"v":1,"id":"b","ok":true,"data":{"x":2}}"#);
        assert_eq!(routed, Routed::Delivered("b".into()));
        assert_eq!(b.try_recv().unwrap(), Ok(json!({"x": 2})));
        assert!(a.try_recv().is_err(), "a must still be waiting");
        assert_eq!(r.pending_count(), 1);
        r.route_line("{\"v\":1,\"id\":\"a\",\"ok\":true,\"data\":[1,2]}\r\n");
        assert_eq!(a.try_recv().unwrap(), Ok(json!([1, 2])));
        assert_eq!(r.pending_count(), 0);
    }

    #[test]
    fn error_response_carries_error_object() {
        let r = Router::default();
        let mut rx = r.register("e").unwrap();
        r.route_line(r#"{"v":1,"id":"e","ok":false,"error":{"code":"not_trusted","detail":"x"}}"#);
        assert_eq!(
            rx.try_recv().unwrap(),
            Err(json!({"code":"not_trusted","detail":"x"}))
        );

        let mut rx = r.register("m").unwrap();
        r.route_line(r#"{"v":1,"id":"m","ok":false}"#);
        let err = rx.try_recv().unwrap().unwrap_err();
        assert_eq!(err["code"], "internal");
    }

    #[test]
    fn ok_without_data_is_null() {
        let r = Router::default();
        let mut rx = r.register("s").unwrap();
        r.route_line(r#"{"v":1,"id":"s","ok":true}"#);
        assert_eq!(rx.try_recv().unwrap(), Ok(Value::Null));
    }

    #[test]
    fn unknown_id_is_unmatched_and_harmless() {
        let r = Router::default();
        let mut rx = r.register("a").unwrap();
        assert_eq!(
            r.route_line(r#"{"v":1,"id":"zzz","ok":true,"data":{}}"#),
            Routed::Unmatched("zzz".into())
        );
        assert!(rx.try_recv().is_err());
        assert_eq!(r.pending_count(), 1);
    }

    #[test]
    fn duplicate_id_is_rejected() {
        let r = Router::default();
        let _rx = r.register("dup").unwrap();
        assert!(r.register("dup").is_err());
    }

    #[test]
    fn event_lines_are_not_responses() {
        let r = Router::default();
        let mut rx = r.register("read-1").unwrap();
        let line =
            r#"{"v":1,"id":"read-1","event":"progress","step":"battery","done":2,"total":6}"#;
        match r.route_line(line) {
            Routed::Event(v) => {
                assert_eq!(v, serde_json::from_str::<Value>(line).unwrap());
            }
            other => panic!("expected event, got {other:?}"),
        }
        assert!(
            rx.try_recv().is_err(),
            "an event must not resolve the request"
        );
    }

    #[test]
    fn invalid_lines_are_ignored() {
        let r = Router::default();
        for line in ["", "   ", "not json", "[1,2]", "42", r#"{"v":1,"ok":true}"#] {
            assert_eq!(r.route_line(line), Routed::Invalid, "line: {line:?}");
        }
    }

    #[test]
    fn fail_all_resolves_every_pending_request() {
        let r = Router::default();
        let mut a = r.register("a").unwrap();
        let mut b = r.register("b").unwrap();
        r.fail_all(&error_obj("internal", "engine_exited"));
        for rx in [&mut a, &mut b] {
            assert_eq!(
                rx.try_recv().unwrap().unwrap_err()["detail"],
                "engine_exited"
            );
        }
        assert_eq!(r.pending_count(), 0);
    }

    #[test]
    fn engine_forwards_events_to_sink_without_process() {
        let (sink, seen) = recording_sink();
        let engine = Engine::new(Launch::bundled(PathBuf::from("does-not-exist")), sink);
        let mut rx = engine.router.register("f-1").unwrap();
        let ev = r#"{"v":1,"id":"f-1","event":"fdr","stage":"waiting_trigger"}"#;
        engine.handle_line(ev);
        engine.handle_line("garbage");
        engine.handle_line(r#"{"v":1,"id":"f-1","ok":true,"data":{"has_fdr":false}}"#);
        assert_eq!(
            *seen.lock().unwrap(),
            vec![serde_json::from_str::<Value>(ev).unwrap()]
        );
        assert_eq!(rx.try_recv().unwrap(), Ok(json!({"has_fdr": false})));
    }

    #[test]
    fn timeouts_follow_command() {
        assert_eq!(
            timeout_for("fdr", &json!({"timeout_s": 100})),
            Duration::from_secs(700)
        );
        assert_eq!(timeout_for("fdr", &json!({})), Duration::from_secs(1500));
        assert_eq!(timeout_for("hello", &json!({})), Duration::from_secs(60));
    }

    #[test]
    fn truncate_respects_char_boundaries() {
        assert_eq!(truncate("ação", 2), "aç");
        assert_eq!(truncate("ab", 5), "ab");
    }

    /// The real dev launch path (`uv run --project ../engine python -m lacre_engine`): `hello`, then
    /// `shutdown`. Run with `cargo test -- --ignored real_engine`.
    #[tokio::test]
    #[ignore = "needs uv and the engine sources"]
    async fn real_engine_hello_dev() {
        let engine_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("engine");
        let (sink, _seen) = recording_sink();
        let engine = Engine::new(Launch::dev(engine_dir), sink);
        engine.start().unwrap();
        let hello = engine
            .request(
                engine.new_id(),
                "hello",
                json!({}),
                Duration::from_secs(120),
            )
            .await
            .expect("hello");
        assert!(hello.get("engine_version").is_some(), "{hello}");
        engine.shutdown(Duration::from_secs(5));
        assert!(!engine.status().running);
    }

    /// End-to-end against a fake engine (Python on PATH). Run with `cargo test -- --ignored`.
    #[tokio::test]
    #[ignore = "needs `python` on PATH"]
    async fn fake_engine_end_to_end() {
        const FAKE: &str = r#"
import json, sys, threading, time
lock = threading.Lock()
def out(o):
    with lock:
        sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
def handle(req):
    i, cmd = req["id"], req["cmd"]
    if cmd == "slow":
        out({"v":1,"id":i,"event":"progress","step":"identity","done":1,"total":2})
        time.sleep(1.0)
        out({"v":1,"id":i,"ok":True,"data":{"slow":True}})
    elif cmd == "hello":
        out({"v":1,"id":i,"ok":True,"data":{"engine_version":"0.0.0"}})
    elif cmd == "boom":
        out({"v":1,"id":i,"ok":False,"error":{"code":"no_device","detail":"none"}})
    elif cmd == "die":
        sys.stdout.flush(); import os; os._exit(3)
    elif cmd == "shutdown":
        out({"v":1,"id":i,"ok":True,"data":{}}); sys.exit(0)
for line in sys.stdin:
    threading.Thread(target=handle, args=(json.loads(line),)).start()
"#;
        let dir = std::env::temp_dir().join(format!("lacre-fake-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let script = dir.join("fake_engine.py");
        std::fs::write(&script, FAKE).unwrap();
        let launch = Launch {
            program: "python".into(),
            args: vec!["-u".into(), script.into_os_string()],
            cwd: Some(dir.clone()),
            mode: Mode::Dev,
        };
        let (sink, seen) = recording_sink();
        let engine = Engine::new(launch, sink);
        engine.start().unwrap();
        let t = Duration::from_secs(10);

        // Warm up (interpreter start-up time varies a lot under load).
        let hello = engine
            .request(engine.new_id(), "hello", json!({}), t)
            .await
            .unwrap();
        assert_eq!(hello["engine_version"], "0.0.0");

        // A slow request must not block a fast one: hello resolves while slow is still pending.
        let e2 = Arc::clone(&engine);
        let slow = tokio::spawn(async move { e2.request("s1".into(), "slow", json!({}), t).await });
        tokio::time::sleep(Duration::from_millis(100)).await;
        engine
            .request(engine.new_id(), "hello", json!({}), t)
            .await
            .unwrap();
        assert!(!slow.is_finished(), "hello waited for slow");
        assert_eq!(slow.await.unwrap().unwrap(), json!({"slow": true}));
        assert_eq!(seen.lock().unwrap()[0]["event"], "progress");

        // Error responses come back as the error object.
        let err = engine
            .request(engine.new_id(), "boom", json!({}), t)
            .await
            .unwrap_err();
        assert_eq!(err["code"], "no_device");

        // Engine death fails the pending request, then the engine restarts by itself.
        let err = engine
            .request(engine.new_id(), "die", json!({}), t)
            .await
            .unwrap_err();
        assert_eq!(err["detail"], "engine_exited");
        let mut ok = false;
        for _ in 0..50 {
            tokio::time::sleep(Duration::from_millis(100)).await;
            if engine.status().running {
                ok = engine
                    .request(engine.new_id(), "hello", json!({}), t)
                    .await
                    .is_ok();
                break;
            }
        }
        assert!(ok, "engine did not come back after dying");

        // Shell timeout.
        let err = engine
            .request(
                engine.new_id(),
                "unknown_cmd",
                json!({}),
                Duration::from_millis(300),
            )
            .await
            .unwrap_err();
        assert_eq!(err["code"], "timeout");

        engine.shutdown(Duration::from_secs(3));
        assert!(!engine.status().running);
        let _ = std::fs::remove_dir_all(dir);
    }
}
