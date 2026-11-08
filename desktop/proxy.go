package main

import (
	"fmt"
	"io"
	"net"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/spf13/pflag"
	"github.com/wailsapp/wails/v3/pkg/application"
)

// parseRemoteAddr parses CLI args for --remote / -r using pflag.
func parseRemoteAddr(args []string) string {
	fs := pflag.NewFlagSet("desktop", pflag.ContinueOnError)
	fs.ParseErrorsAllowlist.UnknownFlags = true
	var remote string
	fs.StringVarP(&remote, "remote", "r", "", "Remote backend address (e.g. 192.168.11.22:18888)")
	_ = fs.Parse(args)
	return normalizeRemoteAddr(remote)
}

// normalizeRemoteAddr normalizes a remote address or URL into a host:port TCP address (defaults to port :18888).
// Handles:
// - "192.168.1.100" -> "192.168.1.100:18888"
// - "192.168.1.100:8080" -> "192.168.1.100:8080"
// - "http://grandcypher.tail5532f5.ts.net:18888/" -> "grandcypher.tail5532f5.ts.net:18888"
// - "http://grandcypher.tail5532f5.ts.net/" -> "grandcypher.tail5532f5.ts.net:18888"
// - "https://remote.example.com" -> "remote.example.com:18888"
// - "remote.example.com:18888/foo/bar" -> "remote.example.com:18888"
func normalizeRemoteAddr(addr string) string {
	addr = strings.TrimSpace(addr)
	if addr == "" {
		return ""
	}

	// 1. If URL scheme is present, parse via net/url
	if strings.Contains(addr, "://") {
		if u, err := url.Parse(addr); err == nil && u.Host != "" {
			addr = u.Host
		}
	}

	// 2. Strip any trailing path or slash if present (e.g. "myhost:18888/path")
	if idx := strings.Index(addr, "/"); idx != -1 {
		addr = addr[:idx]
	}
	addr = strings.TrimRight(addr, "/")

	// 3. Ensure host:port format
	host, port, err := net.SplitHostPort(addr)
	if err != nil {
		// Missing port or raw IP/hostname
		return net.JoinHostPort(strings.Trim(addr, "[]"), "18888")
	}
	if port == "" {
		port = "18888"
	}
	return net.JoinHostPort(strings.Trim(host, "[]"), port)
}

// startRemoteProxy listens on localhost:18888 and forwards all traffic to remoteAddr.
func startRemoteProxy(
	app *application.App,
	window *application.WebviewWindow,
	remoteAddr string,
	cleanupMu *sync.Mutex,
	cleanup *func(),
	showFatalError func(string),
) {
	app.Event.Emit("backend-log", fmt.Sprintf("Starting TCP proxy to remote backend: %s\r\n", remoteAddr))

	ln, err := net.Listen("tcp", "127.0.0.1:18888")
	if err != nil {
		showFatalError(fmt.Sprintf("Failed to bind local proxy port: %v", err))
		return
	}

	stopCh := make(chan struct{})
	cleanupMu.Lock()
	*cleanup = func() {
		select {
		case <-stopCh:
		default:
			close(stopCh)
		}
		_ = ln.Close()
	}
	cleanupMu.Unlock()

	// Accept loop for incoming connections
	go func() {
		for {
			conn, err := ln.Accept()
			if err != nil {
				return
			}
			go proxyConnection(conn, remoteAddr)
		}
	}()

	// Monitor readiness of the remote server
	app.Event.Emit("backend-log", fmt.Sprintf("Waiting for remote connection at %s...\r\n", remoteAddr))
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	var lastLoggedErr string
	for {
		conn, err := net.DialTimeout("tcp", remoteAddr, 1*time.Second)
		if err == nil {
			_ = conn.Close()
			app.Event.Emit("backend-log", fmt.Sprintf("\r\n\x1b[32m>>> Connected to remote backend at %s! Navigating...\x1b[0m\r\n", remoteAddr))
			app.Event.Emit("backend-ready", true)
			window.SetURL(BACKEND_URL)
			return
		}

		errMsg := err.Error()
		if errMsg != lastLoggedErr {
			app.Event.Emit("backend-log", fmt.Sprintf("Connecting to %s failed: %v (retrying...)\r\n", remoteAddr, err))
			lastLoggedErr = errMsg
		}

		select {
		case <-stopCh:
			return
		case <-ticker.C:
		}
	}
}

// proxyConnection forwards bytes bi-directionally between src and target.
func proxyConnection(src net.Conn, target string) {
	defer src.Close()
	dst, err := net.DialTimeout("tcp", target, 5*time.Second)
	if err != nil {
		return
	}
	defer dst.Close()

	done := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(dst, src)
		done <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(src, dst)
		done <- struct{}{}
	}()
	<-done
}
