package main

import (
	"embed"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"unsafe"

	"github.com/wailsapp/wails/v3/pkg/application"
	"github.com/wailsapp/wails/v3/pkg/events"
)

const (
	READY_SENTINEL = "Application: http://localhost:18888"
	STDIO_BUF_LEN  = max(128, len(READY_SENTINEL))
	BACKEND_URL    = "http://127.0.0.1:18888"
)

//go:embed all:frontend/dist
var assets embed.FS

func main() {
	app := application.New(application.Options{
		Name:        "VCClient Forge",
		Description: "VCClient Forge Desktop Host",
		Assets: application.AssetOptions{
			Handler: application.AssetFileServerFS(assets),
		},
		Mac: application.MacOptions{
			ApplicationShouldTerminateAfterLastWindowClosed: true,
		},
	})

	var window *application.WebviewWindow
	var windowMu sync.Mutex

	window = app.Window.NewWithOptions(application.WebviewWindowOptions{
		Title:     "VCClient Forge",
		Width:     1000,
		Height:    800,
		MinWidth:  360,
		MinHeight: 480,
		URL:       "/",
		JS: `
		// Transparently redirect window.open() to default system browser
		window.open = function(url) {
			if (url && typeof url === 'string') {
				if (url.startsWith('/')) {
					url = 'http://127.0.0.1:18888' + url;
				}
				if (window.wails && window.wails.Browser) {
					window.wails.Browser.OpenURL(url);
				}
			}
			return null;
		};

		// Polyfill legacy Electron API for v2.0.78 UI
		window.electronAPI = {
			openBrowser: function(url) {
				if (url && typeof url === 'string') {
					if (url.startsWith('/')) {
						url = 'http://127.0.0.1:18888' + url;
					}
					if (window.wails && window.wails.Browser) {
						window.wails.Browser.OpenURL(url);
					}
				}
			}
		};
		`,
	})

	var cmdMutex sync.Mutex
	var activeCmd *exec.Cmd

	// Launch Python backend in a background goroutine
	go func() {
		binPath, args, workDir, err := resolveBackendCommand()
		if err != nil {
			app.Event.Emit("backend-log", fmt.Sprintf("Failed to resolve backend command: %v\r\n", err))
			return
		}

		cmd := createCommand(binPath, args...)
		cmd.Dir = workDir
		cmd.Env = append(os.Environ(),
			"PYTHONUNBUFFERED=1",
			"PYTHONIOENCODING=utf-8",
		)

		stdout, err := cmd.StdoutPipe()
		if err != nil {
			app.Event.Emit("backend-log", fmt.Sprintf("Failed to open stdout pipe: %v\r\n", err))
			return
		}
		stderr, err := cmd.StderrPipe()
		if err != nil {
			app.Event.Emit("backend-log", fmt.Sprintf("Failed to open stderr pipe: %v\r\n", err))
			return
		}

		if err := cmd.Start(); err != nil {
			app.Event.Emit("backend-log", fmt.Sprintf("Failed to spawn backend process: %v\r\n", err))
			return
		}

		cmdMutex.Lock()
		activeCmd = cmd
		cmdMutex.Unlock()

		// Stream stdout & monitor readiness
		go func() {
			buf := make([]byte, STDIO_BUF_LEN)
			slideBuf := make([]byte, STDIO_BUF_LEN*2)
			slideLen := 0
			for {
				n, err := stdout.Read(buf)
				if n > 0 {
					text := unsafe.String(&buf[0], n)
					app.Event.Emit("backend-log", text)
					copy(slideBuf[slideLen:cap(slideBuf)], buf[:n])
					slideLen += n
					if strings.Contains(unsafe.String(&slideBuf[0], slideLen), READY_SENTINEL) {
						app.Event.Emit("backend-log", "\r\n\x1b[32m>>> Backend is ready! Navigating...\x1b[0m\r\n")
						app.Event.Emit("backend-ready", true)
						windowMu.Lock()
						if window != nil {
							window.SetURL(BACKEND_URL)
						}
						windowMu.Unlock()
						return
					}
					if slideLen > STDIO_BUF_LEN {
						copy(slideBuf, slideBuf[slideLen-STDIO_BUF_LEN:slideLen])
						slideLen -= STDIO_BUF_LEN
					}
				}
				if err != nil {
					if err == io.EOF {
						app.Event.Emit("backend-log", "\r\n\x1b[31m>>> Backend process exited\x1b[0m\r\n")
					}
					return
				}
			}
		}()

		// Stream stderr
		go func() {
			buf := make([]byte, STDIO_BUF_LEN)
			for {
				n, err := stderr.Read(buf)
				if n > 0 {
					app.Event.Emit("backend-log", unsafe.String(&buf[0], n))
				}
				if err != nil {
					return
				}
			}
		}()
	}()

	// Terminate child process when window closes
	window.OnWindowEvent(events.Common.WindowClosing, func(e *application.WindowEvent) {
		cmdMutex.Lock()
		defer cmdMutex.Unlock()
		if activeCmd != nil {
			stopProcess(activeCmd)
		}
	})

	// Run application on the MAIN OS THREAD
	if err := app.Run(); err != nil {
		log.Fatalf("Application exited with error: %v", err)
	}

	// Ensure cleanup on normal exit
	cmdMutex.Lock()
	if activeCmd != nil {
		stopProcess(activeCmd)
	}
	cmdMutex.Unlock()
}

// resolveBackendCommand returns the path to the executable and its initial arguments.
func resolveBackendCommand() (string, []string, string, error) {
	// Look for executable directory first
	exePath, err := os.Executable()
	if err != nil {
		return "", nil, "", fmt.Errorf("resolving executable path: %w", err)
	}
	exeDir := filepath.Dir(exePath)

	// Check if running from a distribution bundle (main.exe / main exists beside desktop binary)
	prodBinary := "main"
	if runtime.GOOS == "windows" {
		prodBinary = "main.exe"
	}
	prodPath := filepath.Join(exeDir, prodBinary)
	if _, err := os.Stat(prodPath); err == nil {
		return prodPath, []string{"--host=127.0.0.1", "--port=18888"}, exeDir, nil
	}

	// Otherwise, check for development workspace root
	// We might be run from `desktop/` or repository root
	candidates := []string{
		".",
		"..",
		filepath.Dir(exeDir),
		filepath.Dir(filepath.Dir(exeDir)),
	}

	for _, cand := range candidates {
		absCand, err := filepath.Abs(cand)
		if err != nil {
			continue
		}
		pyScript := filepath.Join(absCand, "backend", "main.py")
		if _, err := os.Stat(pyScript); err == nil {
			// Found workspace root!
			var pythonExe string
			if runtime.GOOS == "windows" {
				pythonExe = filepath.Join(absCand, "backend", ".venv", "Scripts", "python.exe")
			} else {
				pythonExe = filepath.Join(absCand, "backend", ".venv", "bin", "python")
			}
			if _, err := os.Stat(pythonExe); err != nil {
				return "", nil, "", fmt.Errorf("Python venv not found at %s. Run uv sync --project backend.", pythonExe)
			}
			args := []string{"-u", pyScript, "--host=127.0.0.1", "--port=18888"}
			return pythonExe, args, absCand, nil
		}
	}

	return "", nil, "", fmt.Errorf("cannot locate backend executable or source tree")
}
