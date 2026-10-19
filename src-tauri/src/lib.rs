mod backend;

use std::sync::atomic::Ordering;
use std::sync::Arc;
use tauri::{Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};

#[tauri::command]
fn startup_status(state: State<'_, Arc<backend::Desktop>>) -> backend::StartupStatus {
    state.status.lock().unwrap().clone()
}

#[tauri::command]
fn retry_backend(app: tauri::AppHandle, state: State<'_, Arc<backend::Desktop>>) {
    backend::launch(app, Arc::clone(state.inner()));
}

pub fn run() {
    let desktop = Arc::new(backend::Desktop::default());
    let setup_desktop = Arc::clone(&desktop);
    let app = tauri::Builder::default()
        .manage(desktop)
        .invoke_handler(tauri::generate_handler![startup_status, retry_backend])
        .setup(move |app| {
            let window =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                    .title("VCClient Forge")
                    .inner_size(1180.0, 800.0)
                    .min_inner_size(360.0, 480.0)
                    .on_navigation(backend::allowed_navigation)
                    .build()?;
            *setup_desktop.bootstrap_url.lock().unwrap() = Some(window.url()?);
            backend::launch(app.handle().clone(), Arc::clone(&setup_desktop));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to create VCClient Forge desktop host");

    app.run(|app, event| {
        if let RunEvent::ExitRequested {
            code: None, api, ..
        } = event
        {
            api.prevent_exit();
            let desktop = app.state::<Arc<backend::Desktop>>();
            if !desktop.exiting.swap(true, Ordering::SeqCst) {
                let desktop = Arc::clone(desktop.inner());
                let app = app.clone();
                std::thread::spawn(move || {
                    while desktop.active.load(Ordering::SeqCst) {
                        std::thread::sleep(std::time::Duration::from_millis(50));
                    }
                    app.exit(0);
                });
            }
        }
    });
}
