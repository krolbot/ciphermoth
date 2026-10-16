//! Compiled only into the separately identified native QA artifact.
#[tauri::command]
pub fn qa_report(result: serde_json::Value) -> Result<(), String> {
    let root = std::env::var("CIPHERMOTH_QA_ROOT").map_err(|_| "QA root missing")?;
    let root = std::path::Path::new(&root);
    std::fs::write(
        root.join("webview.partial"),
        serde_json::to_vec_pretty(&result).unwrap(),
    )
    .map_err(|_| "Could not write QA report")?;
    std::fs::rename(root.join("webview.partial"), root.join("webview.json"))
        .map_err(|_| "Could not publish QA report".into())
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
