//! Compiled only into the separately identified native QA artifact.
#[tauri::command]
pub async fn qa_backup(
    operation: String,
    session: String,
    password: String,
    core: tauri::State<'_, std::sync::Arc<crate::sidecar::Supervisor>>,
) -> Result<serde_json::Value, String> {
    if !["backup_export", "backup_import"].contains(&operation.as_str()) {
        return Err("Invalid QA operation".into());
    }
    let root = std::path::PathBuf::from(
        std::env::var("CIPHERMOTH_QA_ROOT").map_err(|_| "QA root missing")?,
    );
    let path = root.join("transport.cmbackup");
    // Fixed synthetic destination authorized by the test host. This exercises
    // the real native transfer, separately from optional OS-picker automation.
    let result = crate::native::file_request(
        &core,
        &operation,
        path.clone(),
        session,
        serde_json::json!({"master_password": password, "on_conflict": "skip"}),
    )
    .await?;
    Ok(
        serde_json::json!({"result": result, "bytes": std::fs::metadata(path).map_err(|_| "Missing backup")?.len()}),
    )
}

#[tauri::command]
pub async fn qa_report(mut result: serde_json::Value) -> Result<(), String> {
    let root = std::env::var("CIPHERMOTH_QA_ROOT").map_err(|_| "QA root missing")?;
    let root = std::path::Path::new(&root);
    let ack = if cfg!(target_os = "macos")
        && [Some("clipboard_timeout"), Some("clipboard_replaced")]
            .contains(&result["stage"].as_str())
    {
        let nonce = uuid::Uuid::new_v4().to_string();
        result["ack"] = serde_json::json!(nonce);
        Some(root.join(format!("{nonce}.done")))
    } else {
        None
    };
    std::fs::write(
        root.join("webview.partial"),
        serde_json::to_vec_pretty(&result).unwrap(),
    )
    .map_err(|_| "Could not write QA report")?;
    std::fs::rename(root.join("webview.partial"), root.join("webview.json"))
        .map_err(|_| "Could not publish QA report")?;
    if let Some(ack) = ack {
        for _ in 0..600 {
            if ack.exists() {
                std::fs::remove_file(ack).map_err(|_| "Could not consume QA acknowledgement")?;
                return Ok(());
            }
            tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        }
        return Err("The host did not acknowledge the clipboard check".into());
    }
    Ok(())
}

#[tauri::command]
pub fn qa_lock(app: tauri::AppHandle) -> Result<(), String> {
    app.run_on_main_thread(|| {
        #[cfg(target_os = "macos")]
        unsafe {
            extern "C" {
                fn cm_test_sleep_notification();
            }
            cm_test_sleep_notification();
        }
        #[cfg(not(target_os = "macos"))]
        crate::lock::vault_lock();
    })
    .map_err(|_| "Could not deliver native lock event".into())
}
