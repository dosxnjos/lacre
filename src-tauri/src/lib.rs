//! Lacre desktop shell: starts the engine, bridges commands/events to the UI.

mod commands;
pub mod engine;

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use tauri::path::BaseDirectory;
use tauri::{AppHandle, Emitter, Manager, RunEvent, Runtime};

use engine::{Engine, EventSink, Launch, Signal};

/// Tauri event carrying each protocol event line (payload = the JSON line as sent by the engine).
pub const ENGINE_EVENT: &str = "engine-event";
/// Tauri event sent when the engine starts or stops (payload = `{running, mode}`).
pub const ENGINE_STATUS_EVENT: &str = "engine-status";

/// Picks how to run the engine:
/// 1. debug builds only: `LACRE_ENGINE=<path to lacre-engine(.exe)>` runs a frozen engine
///    (to test the PyInstaller build without making an installer);
/// 2. debug builds: `uv run --project <repo>/engine python -m lacre_engine`;
/// 3. release builds: the bundled resource `engine/lacre-engine(.exe)` (no override).
fn resolve_launch<R: Runtime>(app: &AppHandle<R>) -> Launch {
    if cfg!(debug_assertions) {
        if let Some(path) = std::env::var_os("LACRE_ENGINE").filter(|p| !p.is_empty()) {
            return Launch::bundled(PathBuf::from(path));
        }
        let engine_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("engine");
        return Launch::dev(engine_dir);
    }
    let rel = format!("engine/{}", engine::bundled_exe_name());
    let exe = app
        .path()
        .resolve(&rel, BaseDirectory::Resource)
        .unwrap_or_else(|_| PathBuf::from(&rel));
    Launch::bundled(exe)
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let handle = app.handle().clone();
            let sink: EventSink = Arc::new(move |signal| {
                let res = match signal {
                    Signal::Event(payload) => handle.emit(ENGINE_EVENT, payload),
                    Signal::Status(status) => handle.emit(ENGINE_STATUS_EVENT, status),
                };
                if let Err(e) = res {
                    eprintln!("[lacre] emit failed: {e}");
                }
            });
            if let Ok(dir) = app.path().app_log_dir() {
                let _ = engine::ENGINE_LOG.set(dir.join("engine.log"));
            }
            let engine = Engine::new(resolve_launch(app.handle()), sink);
            engine.start_or_retry();
            app.manage(engine);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::engine_request,
            commands::engine_status,
            commands::save_text_file,
            commands::get_settings,
            commands::set_settings,
            commands::open_external,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Lacre");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(engine) = handle.try_state::<Arc<Engine>>() {
                engine.shutdown(Duration::from_secs(3));
            }
        }
    });
}
