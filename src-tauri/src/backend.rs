use serde::Serialize;
use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, Url};

const BACKEND_URL: &str = "http://127.0.0.1:18888/";
const READY_MESSAGE: &str = "VCCLIENT_DESKTOP_READY:18888";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(600);
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Clone, Serialize)]
pub struct StartupStatus {
    phase: String,
    message: String,
    logs: VecDeque<String>,
}

impl Default for StartupStatus {
    fn default() -> Self {
        Self {
            phase: "starting".into(),
            message: "Starting the local backend".into(),
            logs: VecDeque::new(),
        }
    }
}

#[derive(Default)]
pub struct Desktop {
    pub status: Mutex<StartupStatus>,
    pub active: AtomicBool,
    pub exiting: AtomicBool,
    pub bootstrap_url: Mutex<Option<Url>>,
}

pub fn allowed_navigation(url: &Url) -> bool {
    let embedded = (url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (url.scheme() == "http"
            && url.host_str() == Some("tauri.localhost")
            && url.port().is_none());
    let backend =
        url.scheme() == "http" && url.host_str() == Some("127.0.0.1") && url.port() == Some(18888);
    (embedded || backend) && url.username().is_empty() && url.password().is_none()
}

fn backend_command() -> Result<Command, String> {
    let mut command;
    if cfg!(debug_assertions) {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .ok_or("Cannot locate the project root")?
            .to_path_buf();
        let python = root.join(if cfg!(windows) {
            "backend/.venv/Scripts/python.exe"
        } else {
            "backend/.venv/bin/python"
        });
        if !python.is_file() {
            return Err("Python environment not found. Run uv sync --project backend --extra cpu (or your hardware edition).".into());
        }
        command = Command::new(python);
        command.arg("-u").arg(root.join("backend/main.py"));
        command.current_dir(root);
    } else {
        let executable = std::env::current_exe().map_err(|error| error.to_string())?;
        let root = executable
            .parent()
            .ok_or("Cannot locate the application directory")?;
        command = Command::new(root.join(if cfg!(windows) { "main.exe" } else { "main" }));
        command.current_dir(root);
    }
    command.args([
        "server",
        "--host=127.0.0.1",
        "--port=18888",
        "--https=False",
        "--launch_client=False",
        "--desktop_control=True",
    ]);
    command
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8");
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    Ok(command)
}

fn read_output(
    stream: impl Read + Send + 'static,
    stdout: bool,
    sender: mpsc::SyncSender<(bool, String)>,
) {
    thread::spawn(move || {
        for line in BufReader::new(stream).lines() {
            let Ok(line) = line else { break };
            if stdout && line.trim() == READY_MESSAGE {
                let _ = sender.send((stdout, line));
            } else {
                let _ = sender.try_send((stdout, line));
            }
        }
    });
}

fn stop_backend(child: &mut Child) -> Result<(), String> {
    if child
        .try_wait()
        .map_err(|error| error.to_string())?
        .is_some()
    {
        return Ok(());
    }
    if let Some(mut input) = child.stdin.take() {
        let _ = input.write_all(b"shutdown\n");
    }
    let deadline = Instant::now() + SHUTDOWN_TIMEOUT;
    while Instant::now() < deadline {
        if child
            .try_wait()
            .map_err(|error| error.to_string())?
            .is_some()
        {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(50));
    }
    child
        .kill()
        .map_err(|error| format!("Cannot stop the owned backend: {error}"))?;
    child.wait().map_err(|error| error.to_string())?;
    Ok(())
}

fn supervise(app: &AppHandle, desktop: &Desktop) -> Result<(), String> {
    let mut child = backend_command()?
        .spawn()
        .map_err(|error| format!("Cannot start Python: {error}"))?;
    let (sender, output) = mpsc::sync_channel(128);
    read_output(child.stdout.take().unwrap(), true, sender.clone());
    read_output(child.stderr.take().unwrap(), false, sender);
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    let mut ready = false;
    let result = loop {
        if desktop.exiting.load(Ordering::SeqCst) {
            break Ok(());
        }
        match child.try_wait() {
            Ok(Some(status)) => {
                break Err(format!("Backend exited ({status}). See the startup log."))
            }
            Err(error) => break Err(format!("Cannot monitor Python: {error}")),
            Ok(None) => {}
        }
        if !ready && Instant::now() >= deadline {
            break Err("Backend startup timed out after 10 minutes.".into());
        }
        if let Ok((stdout, line)) = output.recv_timeout(Duration::from_millis(100)) {
            {
                let mut status = desktop.status.lock().unwrap();
                status.logs.push_back(line.chars().take(2000).collect());
                if status.logs.len() > 40 {
                    status.logs.pop_front();
                }
            }
            if !ready && stdout && line.trim() == READY_MESSAGE {
                let Some(window) = app.get_webview_window("main") else {
                    break Err("Application window is unavailable".into());
                };
                if let Err(error) = window.navigate(Url::parse(BACKEND_URL).unwrap()) {
                    break Err(format!("Cannot open the backend UI: {error}"));
                }
                ready = true;
                let mut status = desktop.status.lock().unwrap();
                status.phase = "ready".into();
                status.message = "Backend connected".into();
            }
        }
    };
    drop(output);
    stop_backend(&mut child)?;
    result
}

pub fn launch(app: AppHandle, desktop: Arc<Desktop>) {
    if desktop.exiting.load(Ordering::SeqCst)
        || desktop
            .active
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
    {
        return;
    }
    *desktop.status.lock().unwrap() = StartupStatus::default();
    thread::spawn(move || {
        let result = supervise(&app, &desktop);
        if let Err(message) = result {
            {
                let mut status = desktop.status.lock().unwrap();
                status.phase = "failed".into();
                status.message = message;
            }
            if !desktop.exiting.load(Ordering::SeqCst) {
                if let (Some(window), Some(url)) = (
                    app.get_webview_window("main"),
                    desktop.bootstrap_url.lock().unwrap().clone(),
                ) {
                    if let Err(error) = window.navigate(url) {
                        eprintln!("Cannot restore the startup page: {error}");
                    }
                }
            }
        }
        desktop.active.store(false, Ordering::SeqCst);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn navigation_is_limited_to_embedded_assets_and_our_loopback_server() {
        for address in [
            "tauri://localhost/index.html",
            "http://tauri.localhost/",
            BACKEND_URL,
        ] {
            assert!(allowed_navigation(&Url::parse(address).unwrap()));
        }
        for address in [
            "http://127.0.0.1:18889/",
            "http://127.0.0.1/",
            "http://tauri.localhost:18888/",
            "http://user@127.0.0.1:18888/",
            "file:///index.html",
            "https://example.com/",
        ] {
            assert!(!allowed_navigation(&Url::parse(address).unwrap()));
        }
    }
}
