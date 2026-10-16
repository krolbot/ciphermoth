use crate::{clipboard::Clipboard, sidecar::Supervisor};
use std::sync::{Arc, OnceLock};
use tauri::{Emitter, Manager};
static APP: OnceLock<tauri::AppHandle> = OnceLock::new();
#[cfg(target_os = "macos")]
extern "C" {
    fn cm_observe_lock(callback: extern "C" fn());
}
pub(super) extern "C" fn lock() {
    if let Some(app) = APP.get() {
        reset_renderer(app);
        app.state::<Arc<Clipboard>>().clear();
        // Kill the process that owns all keys and pending KDFs, independent of
        // the renderer event loop. SQLite rolls back any unfinished write.
        app.state::<Arc<Supervisor>>().lock();
        let _ = app.emit("vault-locked", ());
    }
}
pub fn install(app: tauri::AppHandle) {
    let _ = APP.set(app);
    #[cfg(target_os = "macos")]
    unsafe {
        cm_observe_lock(lock);
    }
    // A wall-clock gap also locks on resume if a platform notification was lost.
    std::thread::spawn(|| {
        let mut previous = std::time::SystemTime::now();
        loop {
            std::thread::sleep(std::time::Duration::from_secs(2));
            let now = std::time::SystemTime::now();
            if now.duration_since(previous).unwrap_or_default().as_secs() > 8 {
                lock();
            }
            previous = now;
        }
    });
}

#[tauri::command]
pub fn vault_lock() {
    lock();
}

pub fn reset_renderer(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        // Hide stale decrypted DOM before asking the webview to load a fresh
        // document. No JavaScript callback is needed to remove it from view.
        let _ = window.hide();
        if let Ok(mut url) = window.url() {
            url.set_path("/login");
            url.set_query(None);
            url.set_fragment(None);
            let _ = window.navigate(url);
        }
    }
}
