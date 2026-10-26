package main

import (
	"embed"
	"fmt"
	"log"
	"os"
	"sync"

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
	var (
		cleanupMu sync.Mutex
		cleanup   func()
	)

	doCleanup := func() {
		cleanupMu.Lock()
		defer cleanupMu.Unlock()
		if cleanup != nil {
			cleanup()
			cleanup = nil
		}
	}

	app := application.New(application.Options{
		Name:        "VCClient Forge",
		Description: "VCClient Forge Desktop Host",
		Assets: application.AssetOptions{
			Handler: application.AssetFileServerFS(assets),
		},
		Mac: application.MacOptions{
			ApplicationShouldTerminateAfterLastWindowClosed: true,
		},
		OnShutdown: doCleanup,
	})

	window := app.Window.NewWithOptions(application.WebviewWindowOptions{
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

	showFatalError := func(msg string) {
		log.Print(msg)
		app.Event.Emit("backend-log", fmt.Sprintf("\r\n\x1b[31m%s\x1b[0m\r\n", msg))
		dialog := app.Dialog.Error().
			SetTitle("VCClient Forge").
			SetMessage(msg)
		dialog.AddButton("OK").SetAsDefault().SetAsCancel().OnClick(func() {
			app.Quit()
		})
		dialog.Show()
	}

	remoteAddr := parseRemoteAddr(os.Args[1:])

	app.Event.OnApplicationEvent(events.Common.ApplicationStarted, func(*application.ApplicationEvent) {
		if remoteAddr != "" {
			go startRemoteProxy(app, window, remoteAddr, &cleanupMu, &cleanup, showFatalError)
		} else {
			go startLocalBackend(app, window, &cleanupMu, &cleanup, showFatalError)
		}
	})

	window.OnWindowEvent(events.Common.WindowClosing, func(*application.WindowEvent) {
		doCleanup()
	})

	// Run application on the MAIN OS THREAD
	err := app.Run()

	// Ensure cleanup is executed across all platforms
	doCleanup()

	if err != nil {
		log.Fatalf("Application exited with error: %v", err)
	}
}
