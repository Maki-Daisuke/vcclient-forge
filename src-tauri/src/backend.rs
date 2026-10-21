use serde::Serialize;
use std::collections::VecDeque;
use std::io::{BufRead, BufReader, Read};
use std::num::NonZeroU16;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, Url};

const BACKEND_URL: &str = "http://127.0.0.1:18888/";
const READY_MESSAGE: &str = "Application: http://localhost:18888";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(600);

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
    command.args(["--host=127.0.0.1", "--port=18888"]);
    command
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8");
    command
        .stdin(Stdio::null())
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
    sender: mpsc::SyncSender<(bool, Vec<u8>)>,
) {
    thread::spawn(move || {
        if stdout {
            for line in BufReader::new(stream).split(b'\n') {
                let Ok(mut line) = line else { break };
                let ready = String::from_utf8_lossy(&line).contains(READY_MESSAGE);
                line.push(b'\n');
                let _ = sender.send((ready, line));
            }
        } else {
            let mut stream = stream;
            let mut buffer = [0; 4096];
            while let Ok(count) = stream.read(&mut buffer) {
                if count == 0 {
                    break;
                }
                let _ = sender.send((false, buffer[..count].to_vec()));
            }
        }
    });
}

fn log_terminal() -> vt100::Parser {
    vt100::Parser::new(
        NonZeroU16::new(40).unwrap(),
        NonZeroU16::new(2000).unwrap(),
        0,
    )
}

fn process_log_output(terminal: &mut vt100::Parser, bytes: &[u8]) {
    for segment in bytes.split_inclusive(|byte| *byte == b'\n') {
        if let Some(line) = segment.strip_suffix(b"\n") {
            terminal.process(line);
            terminal.process(b"\r\n");
        } else {
            terminal.process(segment);
        }
    }
}

fn stop_backend(child: &mut Child) -> Result<(), String> {
    if child
        .try_wait()
        .map_err(|error| error.to_string())?
        .is_some()
    {
        return Ok(());
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
    let mut terminal = log_terminal();
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
        if let Ok((ready_message, bytes)) = output.recv_timeout(Duration::from_millis(100)) {
            process_log_output(&mut terminal, &bytes);
            {
                let mut status = desktop.status.lock().unwrap();
                status.logs = terminal
                    .screen()
                    .contents()
                    .lines()
                    .map(str::to_owned)
                    .collect();
            }
            if !ready && ready_message {
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
    fn progress_updates_rewrite_existing_rows() {
        let mut terminal = log_terminal();
        process_log_output(&mut terminal, b"\rModule A: 10%\n\rModel B: 20%");
        process_log_output(&mut terminal, b"\x1b[A\rModule A: 60%\x1b[B\rModel B: 90%");
        assert_eq!(terminal.screen().contents(), "Module A: 60%\nModel B: 90%");
    }

    #[test]
    fn ansi_and_utf8_can_span_read_boundaries() {
        let mut terminal = log_terminal();
        for byte in "\x1b[32mDownloading \u{2588} 50%\x1b[0m".as_bytes() {
            process_log_output(&mut terminal, &[*byte]);
        }
        assert_eq!(terminal.screen().contents(), "Downloading \u{2588} 50%");
    }

    #[test]
    fn piped_newlines_start_at_the_first_column() {
        let mut terminal = log_terminal();
        process_log_output(&mut terminal, b"first\nsecond\r\nthird\n");
        assert_eq!(terminal.screen().contents(), "first\nsecond\nthird");
    }

    #[test]
    fn readiness_is_only_reported_for_stdout() {
        for stdout in [true, false] {
            let (sender, output) = mpsc::sync_channel(4);
            read_output(
                std::io::Cursor::new(format!("{READY_MESSAGE}\n")),
                stdout,
                sender,
            );
            let (ready, _) = output.recv_timeout(Duration::from_secs(2)).unwrap();
            assert_eq!(ready, stdout);
        }
    }

    #[test]
    fn progress_is_forwarded_without_waiting_for_a_newline_or_eof() {
        struct LiveOutput(mpsc::Receiver<Vec<u8>>);
        impl Read for LiveOutput {
            fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
                let Ok(bytes) = self.0.recv() else {
                    return Ok(0);
                };
                buffer[..bytes.len()].copy_from_slice(&bytes);
                Ok(bytes.len())
            }
        }
        let (input, chunks) = mpsc::channel();
        let (sender, output) = mpsc::sync_channel(4);
        read_output(LiveOutput(chunks), false, sender);
        input.send(b"\rDownloading 40%".to_vec()).unwrap();
        let (ready, bytes) = output.recv_timeout(Duration::from_secs(2)).unwrap();
        assert!(!ready);
        let mut terminal = log_terminal();
        process_log_output(&mut terminal, &bytes);
        assert_eq!(terminal.screen().contents(), "Downloading 40%");
    }

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
