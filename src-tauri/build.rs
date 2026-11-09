use std::path::PathBuf;

/// `bundle.resources` maps `../engine/dist/lacre-engine/` (the PyInstaller onedir output) into the
/// app. tauri-build refuses to run when that path is missing, which would block `cargo check` and
/// debug runs (they use `uv run` instead of the frozen engine). So:
/// - debug: create the (gitignored) empty directory if the engine was not packaged yet;
/// - release: fail loudly, because an installer without the engine is useless.
fn ensure_engine_resource() {
    let manifest = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let dir = manifest
        .join("..")
        .join("engine")
        .join("dist")
        .join("lacre-engine");
    // build scripts run on the host: ask cargo for the *target* OS
    let target_windows = std::env::var("CARGO_CFG_TARGET_OS")
        .map(|os| os == "windows")
        .unwrap_or(false);
    let exe = dir.join(if target_windows {
        "lacre-engine.exe"
    } else {
        "lacre-engine"
    });
    println!("cargo:rerun-if-changed={}", exe.display());

    let release = std::env::var("PROFILE")
        .map(|p| p == "release")
        .unwrap_or(false);
    if release && !exe.exists() {
        panic!(
            "frozen engine not found at {} - build it first (see engine/README or engine/build.py)",
            exe.display()
        );
    }
    if !dir.exists() {
        std::fs::create_dir_all(&dir).expect("create placeholder engine resource dir");
    }
}

fn main() {
    ensure_engine_resource();
    tauri_build::build()
}
