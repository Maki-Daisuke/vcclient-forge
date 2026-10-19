fn main() {
    let manifest = tauri_build::AppManifest::new().commands(&["startup_status", "retry_backend"]);
    let attributes = tauri_build::Attributes::new()
        .app_manifest(manifest)
        .windows_attributes(
            tauri_build::WindowsAttributes::new().window_icon_path("../web_front/favicon.ico"),
        );
    tauri_build::try_build(attributes).expect("failed to build desktop resources");
}
