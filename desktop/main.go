package main

import (
	"embed"
	"fmt"
	"log"
	"os"
	"runtime"
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

	initJS := `
		// Only the log viewer uses a native child window; other links still open in the browser.
		window.vcclientForge = {
			openLogWindow: function() {
				if (window._wails && typeof window._wails.invoke === 'function') {
					window._wails.invoke('wails:event:emit:open-log-window');
					return true;
				}
				return false;
			}
		};
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
	`

	if runtime.GOOS == "darwin" {
		initJS += `
		// Audio output compatibility polyfill (WebKit / Safari / macOS WKWebView)
		(function() {
			try {
				var patchMediaDevices = function(proto) {
					if (!proto || !proto.enumerateDevices || proto._patchedForDefaultSink) return;
					var orig = proto.enumerateDevices;
					proto.enumerateDevices = async function() {
						var devices = await orig.apply(this, arguments);
						if (Array.isArray(devices)) {
							var hasDefault = devices.some(function(d) {
								return d.kind === 'audiooutput' && d.deviceId === 'default';
							});
							if (!hasDefault) {
								return devices.concat([{
									deviceId: 'default',
									kind: 'audiooutput',
									label: 'Default Output Device',
									groupId: 'default',
									toJSON: function() { return this; }
								}]);
							}
						}
						return devices;
					};
					proto._patchedForDefaultSink = true;
				};

				if (typeof MediaDevices !== 'undefined' && MediaDevices.prototype) {
					patchMediaDevices(MediaDevices.prototype);
				}
				if (typeof navigator !== 'undefined' && navigator.mediaDevices) {
					patchMediaDevices(navigator.mediaDevices);
				}

				if (typeof HTMLMediaElement !== 'undefined') {
					var origSetSinkId = HTMLMediaElement.prototype.setSinkId;
					HTMLMediaElement.prototype.setSinkId = async function(sinkId) {
						if (!sinkId || sinkId === 'default') {
							if (origSetSinkId) {
								try {
									return await origSetSinkId.call(this, '');
								} catch (_) {}
							}
							return;
						}
						if (origSetSinkId) {
							try {
								return await origSetSinkId.call(this, sinkId);
							} catch (_) {}
						}
					};
				}
			} catch (_) {}
		})();
		`
	}

	window := app.Window.NewWithOptions(application.WebviewWindowOptions{
		Name:                 "main",
		Title:                "VCClient Forge",
		Width:                1000,
		Height:               800,
		MinWidth:             360,
		MinHeight:            480,
		URL:                  "/",
		JS:                   initJS,
		AllowSimpleEventEmit: true,
	})

	app.Event.On("open-log-window", func(event *application.CustomEvent) {
		if event.Sender != "main" {
			return
		}
		if logWindow, ok := app.Window.GetByName("log-viewer"); ok {
			logWindow.Show()
			logWindow.Focus()
			return
		}
		app.Window.NewWithOptions(application.WebviewWindowOptions{
			Name: "log-viewer", Title: "VCClient Forge - Log", Width: 900, Height: 600,
			MinWidth: 360, MinHeight: 300, URL: BACKEND_URL + "/?view=log",
		})
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
		if logWindow, ok := app.Window.GetByName("log-viewer"); ok {
			logWindow.Close()
		}
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
