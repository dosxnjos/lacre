//! Commands exposed to the UI. Names and argument names are a contract with `ui/src/backend.ts`
//! (Tauri passes arguments in camelCase: `defaultName`, `requestId`).

use std::path::{Path, PathBuf};
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use tauri::{AppHandle, Manager, Runtime, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

use crate::engine::{error_obj, timeout_for, Engine, EngineStatus};

/// Commands the UI may not send: the shell owns the engine's lifecycle.
const RESERVED_CMDS: &[&str] = &["shutdown"];

fn err_string(e: &Value) -> String {
    e.to_string()
}

/// Sends a protocol request and waits for its response. `Err` is the engine's error object as a
/// JSON string (`{"code":..,"detail":..}`). `requestId` is optional: pass one to be able to
/// `cancel` the request later (events carry the same id).
#[tauri::command]
pub async fn engine_request(
    engine: State<'_, Arc<Engine>>,
    cmd: String,
    args: Option<Value>,
    request_id: Option<String>,
) -> Result<Value, String> {
    if cmd.is_empty() || RESERVED_CMDS.contains(&cmd.as_str()) {
        return Err(err_string(&error_obj(
            "internal",
            &format!("command not allowed: {cmd}"),
        )));
    }
    let args = match args {
        None | Some(Value::Null) => Value::Object(Map::new()),
        Some(v @ Value::Object(_)) => v,
        Some(_) => return Err(err_string(&error_obj("internal", "args must be an object"))),
    };
    let id = match request_id {
        Some(id) if !id.trim().is_empty() => id,
        _ => engine.new_id(),
    };
    let timeout = timeout_for(&cmd, &args);
    let engine = Arc::clone(&engine);
    engine
        .request(id, &cmd, args, timeout)
        .await
        .map_err(|e| err_string(&e))
}

#[tauri::command]
pub fn engine_status(engine: State<'_, Arc<Engine>>) -> EngineStatus {
    engine.status()
}

/// Native save dialog, then writes `contents` (UTF-8). Returns the path, or `None` if cancelled.
#[tauri::command]
pub async fn save_text_file<R: Runtime>(
    app: AppHandle<R>,
    default_name: String,
    contents: String,
    kind: String,
) -> Result<Option<String>, String> {
    let (label, extensions): (&str, &[&str]) = match kind.as_str() {
        "html" => ("HTML", &["html", "htm"]),
        "txt" => ("Text", &["txt"]),
        other => return Err(format!("unsupported kind: {other}")),
    };
    let file_name = sanitize_file_name(&default_name, extensions[0]);

    let mut dialog = app
        .dialog()
        .file()
        .set_file_name(&file_name)
        .add_filter(label, extensions);
    if let Some(window) = app.get_webview_window("main") {
        dialog = dialog.set_parent(&window);
    }
    let (tx, rx) = tokio::sync::oneshot::channel();
    dialog.save_file(move |picked| {
        let _ = tx.send(picked);
    });
    let Some(picked) = rx
        .await
        .map_err(|_| "dialog closed unexpectedly".to_string())?
    else {
        return Ok(None);
    };
    let path = picked
        .into_path()
        .map_err(|e| format!("invalid path: {e}"))?;
    let path = with_extension_if_missing(path, extensions);
    std::fs::write(&path, contents.as_bytes()).map_err(|e| format!("write failed: {e}"))?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// Keeps only a plain file name (no directories, no characters Windows rejects).
fn sanitize_file_name(name: &str, default_ext: &str) -> String {
    let base = Path::new(name)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    let cleaned: String = base
        .chars()
        .map(|c| {
            if c.is_control() || r#"<>:"/\|?*"#.contains(c) {
                '_'
            } else {
                c
            }
        })
        .collect();
    let cleaned = cleaned.trim().trim_end_matches('.');
    if cleaned.is_empty() {
        format!("lacre.{default_ext}")
    } else {
        cleaned.to_string()
    }
}

fn with_extension_if_missing(path: PathBuf, extensions: &[&str]) -> PathBuf {
    let has = path
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| extensions.iter().any(|x| x.eq_ignore_ascii_case(e)))
        .unwrap_or(false);
    if has {
        path
    } else {
        let mut s = path.into_os_string();
        s.push(".");
        s.push(extensions[0]);
        PathBuf::from(s)
    }
}

// ---------------------------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------------------------

const LANGS: &[&str] = &["pt-BR", "en"];

#[derive(Serialize, Deserialize, Debug, PartialEq, Eq)]
pub struct Settings {
    pub lang: Option<String>,
}

fn settings_path<R: Runtime>(app: &AppHandle<R>) -> Result<PathBuf, String> {
    app.path()
        .app_config_dir()
        .map(|d| d.join("settings.json"))
        .map_err(|e| format!("no config dir: {e}"))
}

fn read_settings_map(path: &Path) -> Map<String, Value> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .and_then(|v| match v {
            Value::Object(m) => Some(m),
            _ => None,
        })
        .unwrap_or_default()
}

fn valid_lang(v: Option<&str>) -> Option<String> {
    v.filter(|l| LANGS.contains(l)).map(str::to_string)
}

#[tauri::command]
pub fn get_settings<R: Runtime>(app: AppHandle<R>) -> Settings {
    let lang = settings_path(&app)
        .ok()
        .map(|p| read_settings_map(&p))
        .and_then(|m| valid_lang(m.get("lang").and_then(Value::as_str)));
    Settings { lang }
}

/// Persists the UI language (`"pt-BR"`, `"en"` or `null` to follow the system).
#[tauri::command]
pub fn set_settings<R: Runtime>(app: AppHandle<R>, lang: Option<String>) -> Result<(), String> {
    if let Some(l) = &lang {
        if !LANGS.contains(&l.as_str()) {
            return Err(format!("unsupported lang: {l}"));
        }
    }
    let path = settings_path(&app)?;
    write_settings(&path, lang)
}

fn write_settings(path: &Path, lang: Option<String>) -> Result<(), String> {
    let mut map = read_settings_map(path); // keep keys added by future versions
    map.insert(
        "lang".into(),
        lang.map(Value::String).unwrap_or(Value::Null),
    );
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("create config dir: {e}"))?;
    }
    let body = serde_json::to_string_pretty(&Value::Object(map)).map_err(|e| e.to_string())?;
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, body).map_err(|e| format!("write settings: {e}"))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("save settings: {e}"))
}

// ---------------------------------------------------------------------------------------------
// External links
// ---------------------------------------------------------------------------------------------

fn checked_web_url(url: &str) -> Result<tauri::Url, String> {
    let parsed = tauri::Url::parse(url.trim()).map_err(|e| format!("invalid url: {e}"))?;
    match parsed.scheme() {
        "http" | "https" if parsed.host_str().is_some() => Ok(parsed),
        _ => Err("only http/https links can be opened".into()),
    }
}

/// Opens an http/https URL in the system browser (e.g. the Apple Devices store page).
#[tauri::command]
pub fn open_external<R: Runtime>(app: AppHandle<R>, url: String) -> Result<(), String> {
    let url = checked_web_url(&url)?;
    app.opener()
        .open_url(url.as_str(), None::<&str>)
        .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn web_urls_only() {
        assert!(checked_web_url("https://apps.microsoft.com/detail/9np83lwlpz9k").is_ok());
        assert!(checked_web_url("http://example.com").is_ok());
        for bad in [
            "file:///C:/Windows/System32/calc.exe",
            "javascript:alert(1)",
            "ms-settings:",
            "",
            "https://",
        ] {
            assert!(checked_web_url(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn file_names_are_sanitized() {
        assert_eq!(
            sanitize_file_name("lacre-2026-11-09.html", "html"),
            "lacre-2026-11-09.html"
        );
        assert_eq!(sanitize_file_name("..\\..\\evil.html", "html"), "evil.html");
        assert_eq!(sanitize_file_name("a<b?.txt", "txt"), "a_b_.txt");
        assert_eq!(sanitize_file_name("", "txt"), "lacre.txt");
    }

    #[test]
    fn extension_added_when_missing() {
        assert_eq!(
            with_extension_if_missing("r".into(), &["html", "htm"]),
            PathBuf::from("r.html")
        );
        assert_eq!(
            with_extension_if_missing("r.HTM".into(), &["html", "htm"]),
            PathBuf::from("r.HTM")
        );
        assert_eq!(
            with_extension_if_missing("r.v2".into(), &["txt"]),
            PathBuf::from("r.v2.txt")
        );
    }

    #[test]
    fn settings_roundtrip_keeps_unknown_keys() {
        let dir = std::env::temp_dir().join(format!("lacre-settings-{}", std::process::id()));
        let path = dir.join("settings.json");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(&path, r#"{"lang":"en","future":1}"#).unwrap();
        write_settings(&path, Some("pt-BR".into())).unwrap();
        let m = read_settings_map(&path);
        assert_eq!(m["lang"], "pt-BR");
        assert_eq!(m["future"], 1);
        write_settings(&path, None).unwrap();
        assert!(read_settings_map(&path)["lang"].is_null());
        assert_eq!(valid_lang(Some("fr")), None);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
