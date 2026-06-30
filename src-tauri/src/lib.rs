use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager, RunEvent};

/// Holds the Python backend child process handle.
struct BackendState(Mutex<Option<Child>>);

/// Persisted user settings (written to <app_data>/settings.json).
#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(default)]
pub struct AppSettings {
    pub openai_api_key: String,
    pub openai_base_url: String,
    pub embedding_model: String,
    pub llm_model: String,
    /// "memory" | "chroma" | "pgvector"
    pub vector_store: String,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            openai_api_key: String::new(),
            openai_base_url: "https://api.openai.com/v1".to_string(),
            embedding_model: "text-embedding-3-small".to_string(),
            llm_model: "gpt-4o-mini".to_string(),
            // Chroma is offline-safe in this project (we store our own
            // pre-computed embeddings; chroma never downloads a model).
            vector_store: "chroma".to_string(),
        }
    }
}

// --------------------------------------------------------------------- helpers

fn app_data_dir(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
}

fn settings_path(app: &AppHandle) -> PathBuf {
    app_data_dir(app).join("settings.json")
}

fn load_settings(app: &AppHandle) -> AppSettings {
    let path = settings_path(app);
    if path.exists() {
        std::fs::read_to_string(&path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default()
    } else {
        AppSettings::default()
    }
}

fn save_settings_file(app: &AppHandle, settings: &AppSettings) {
    let dir = app_data_dir(app);
    let _ = std::fs::create_dir_all(&dir);
    if let Ok(content) = serde_json::to_string_pretty(settings) {
        let _ = std::fs::write(settings_path(app), &content);
    }
}

/// Path to the bundled backend executable (Nuitka standalone layout), if present.
/// Returns None in dev builds or when `scripts/build_backend.py` hasn't been run.
fn bundled_backend_path(app: &AppHandle) -> Option<PathBuf> {
    let res = app.path().resource_dir().ok()?;
    let exe_name = if cfg!(target_os = "windows") {
        "ops-intel-agent-backend.exe"
    } else {
        "ops-intel-agent-backend"
    };
    let candidate = res
        .join("binaries")
        .join("ops-intel-agent-backend")
        .join(exe_name);
    if candidate.exists() {
        Some(candidate)
    } else {
        None
    }
}

// ------------------------------------------------------------------- commands

#[tauri::command]
fn get_settings(app: AppHandle) -> AppSettings {
    load_settings(&app)
}

#[tauri::command]
fn save_settings(app: AppHandle, settings: AppSettings) {
    save_settings_file(&app, &settings);
}

#[tauri::command]
fn restart_backend(app: AppHandle, state: tauri::State<BackendState>) -> Result<(), String> {
    // Stop the existing backend, then start a fresh one with the new settings.
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    let settings = load_settings(&app);
    match start_backend(&app, &settings) {
        Ok(child) => {
            if let Ok(mut guard) = state.0.lock() {
                *guard = Some(child);
            }
            Ok(())
        }
        Err(e) => Err(e),
    }
}

// ------------------------------------------------------------- backend launch

fn start_backend(app: &AppHandle, settings: &AppSettings) -> Result<Child, String> {
    let data_dir = app_data_dir(app);
    let _ = std::fs::create_dir_all(&data_dir);

    let mut cmd = if let Some(bin) = bundled_backend_path(app) {
        log::info!("starting bundled backend: {}", bin.display());
        let mut c = Command::new(bin);
        c.args(["--host", "127.0.0.1", "--port", "8000"]);
        c
    } else {
        // Dev / unpackaged fallback: requires uv + the repo on the host.
        log::warn!("bundled backend not found; falling back to `uv run uvicorn`");
        let mut c = Command::new("uv");
        c.args([
            "run",
            "uvicorn",
            "ops_intel_agent.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--log-level",
            "info",
        ]);
        c
    };

    // OpenAI (optional) — when a key is set, flip embedding + LLM to OpenAI.
    if !settings.openai_api_key.is_empty() {
        cmd.env("OIA_OPENAI_API_KEY", &settings.openai_api_key);
        cmd.env("OIA_EMBEDDING_PROVIDER", "openai");
        cmd.env("OIA_LLM_PROVIDER", "openai");
    }
    if !settings.openai_base_url.is_empty() {
        cmd.env("OIA_OPENAI_BASE_URL", &settings.openai_base_url);
    }
    if !settings.embedding_model.is_empty() {
        cmd.env("OIA_EMBEDDING_MODEL", &settings.embedding_model);
    }
    if !settings.llm_model.is_empty() {
        cmd.env("OIA_LLM_MODEL", &settings.llm_model);
    }

    // Desktop-mode wiring: persist all data in the per-user app data dir, and
    // let Tauri serve the frontend (FastAPI must NOT mount the SPA itself).
    let db_path = data_dir.join("ops_intel_agent.db");
    let chroma_path = data_dir.join("chroma_db");
    let vectors_path = data_dir.join("ops_intel_agent.vectors.json");
    cmd.env("OIA_VECTOR_STORE", &settings.vector_store);
    cmd.env(
        "OIA_DATABASE_URL",
        format!(
            "sqlite+aiosqlite:///{}",
            db_path.display().to_string().replace('\\', "/")
        ),
    );
    cmd.env("OIA_CHROMA_PATH", chroma_path.to_string_lossy().to_string());
    cmd.env(
        "OIA_MEMORY_VECTOR_PATH",
        vectors_path.to_string_lossy().to_string(),
    );
    cmd.env("OIA_FRONTEND_DIR", "");
    cmd.env("OIA_ENVIRONMENT", "prod");
    cmd.env("OIA_LOG_LEVEL", "info");

    cmd.spawn().map_err(|e| format!("spawn backend: {e}"))
}

// ----------------------------------------------------------------------- entry

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .manage(BackendState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            get_settings,
            save_settings,
            restart_backend,
        ])
        .setup(|app| {
            let settings = load_settings(app.handle());
            match start_backend(app.handle(), &settings) {
                Ok(child) => {
                    let state: tauri::State<BackendState> = app.state::<BackendState>();
                    *state.0.lock().unwrap() = Some(child);
                    log::info!("backend started on http://127.0.0.1:8000");
                }
                Err(e) => log::error!("failed to start backend: {e}"),
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<BackendState>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                            log::info!("backend stopped");
                        }
                    }
                }
            }
        });
}
