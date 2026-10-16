use crate::sidecar::Supervisor;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::State;

#[derive(Default)]
pub struct Files(Mutex<HashMap<String, (PathBuf, Instant)>>);

#[tauri::command]
pub async fn choose_backup(files: State<'_, Files>) -> Result<Option<Value>, String> {
    let picked = rfd::AsyncFileDialog::new()
        .add_filter("CipherMoth backup", &["cmbackup", "zip"])
        .pick_file()
        .await;
    let Some(file) = picked else { return Ok(None) };
    let ticket = uuid::Uuid::new_v4().to_string();
    let name = file.file_name();
    let mut grants = files.0.lock().unwrap();
    grants.clear(); // one pending selection; bounded, single use, expires
    grants.insert(ticket.clone(), (file.path().to_path_buf(), Instant::now()));
    Ok(Some(json!({"ticket":ticket,"name":name})))
}

async fn file_request(
    core: &Supervisor,
    operation: &str,
    path: PathBuf,
    session: String,
    body: Value,
) -> Result<Value, String> {
    if session.len() != 43 {
        return Err("Unlock your vault first.".into());
    }
    let (head, data) = core
        .request(
            json!({"native":operation,"file":path,"session":session}),
            serde_json::to_vec(&body).unwrap(),
            Duration::from_secs(1800),
            None,
        )
        .await
        .map_err(|_| {
            "The file operation did not finish. Check the vault and try again.".to_string()
        })?;
    let result: Value = serde_json::from_slice(&data)
        .map_err(|_| "The file operation did not finish.".to_string())?;
    if head["status"].as_u64() != Some(200) {
        return Err(result["detail"]
            .as_str()
            .unwrap_or("The file operation did not finish.")
            .to_string());
    }
    Ok(result)
}

#[tauri::command]
pub async fn backup_export(
    session: String,
    password: String,
    core: State<'_, Arc<Supervisor>>,
) -> Result<Value, String> {
    if password.len() > 4096 {
        return Err("Password is too long.".into());
    }
    let picked = rfd::AsyncFileDialog::new()
        .set_file_name("ciphermoth-backup.cmbackup")
        .add_filter("CipherMoth backup", &["cmbackup"])
        .save_file()
        .await;
    let Some(file) = picked else {
        return Err("Backup cancelled.".into());
    };
    file_request(
        &core,
        "backup_export",
        file.path().into(),
        session,
        json!({"master_password":password}),
    )
    .await
}

#[tauri::command]
pub async fn backup_import(
    session: String,
    password: String,
    ticket: String,
    on_conflict: String,
    files: State<'_, Files>,
    core: State<'_, Arc<Supervisor>>,
) -> Result<Value, String> {
    if password.len() > 4096 || !["skip", "overwrite"].contains(&on_conflict.as_str()) {
        return Err("Invalid restore options.".into());
    }
    let (path, selected) = files
        .0
        .lock()
        .unwrap()
        .remove(&ticket)
        .ok_or("Select the backup file again.")?;
    if selected.elapsed() > Duration::from_secs(600) {
        return Err("Select the backup file again.".into());
    }
    file_request(
        &core,
        "backup_import",
        path,
        session,
        json!({"master_password":password,"on_conflict":on_conflict}),
    )
    .await
}

#[tauri::command]
pub async fn save_file(request: tauri::ipc::Request<'_>) -> Result<(), String> {
    let data = match request.body() {
        tauri::ipc::InvokeBody::Raw(bytes) if bytes.len() <= 5 * 1024 * 1024 => bytes.clone(),
        _ => return Err("Invalid attachment.".into()),
    };
    // Only a suggested basename, never a renderer-provided destination path.
    let name = request
        .headers()
        .get("x-filename")
        .and_then(|h| h.to_str().ok())
        .unwrap_or("attachment");
    let name = percent_encoding::percent_decode_str(name).decode_utf8_lossy();
    let name = name.rsplit(['/', '\\']).next().unwrap_or("attachment");
    let picked = rfd::AsyncFileDialog::new()
        .set_file_name(name)
        .save_file()
        .await;
    let Some(file) = picked else {
        return Err("Save cancelled.".into());
    };
    use std::io::Write;
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut out = options
        .open(file.path())
        .map_err(|_| "Choose a new filename in a writable folder.")?;
    if out.write_all(&data).and_then(|_| out.sync_all()).is_err() {
        drop(out);
        let _ = std::fs::remove_file(file.path());
        return Err("Could not save the attachment. Check available disk space.".into());
    }
    Ok(())
}

#[tauri::command]
pub fn open_external(url: String) -> Result<(), String> {
    let parsed = url::Url::parse(&url).map_err(|_| "Invalid link.")?;
    if !["https", "http", "mailto"].contains(&parsed.scheme()) || url.len() > 8192 {
        return Err("This link type cannot be opened.".into());
    }
    open::that_detached(url).map_err(|_| "Could not open the link.".into())
}
