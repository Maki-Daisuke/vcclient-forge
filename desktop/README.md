# VCClient Forge Desktop Host (Wails v3)

Dedicated, lightweight Windows desktop host built with **Wails v3 (Go)**.

## Role & Architecture

- **Process Supervision**: Manages the local Python backend lifecycle (`backend/main.py` in dev, `main.exe` in packaged distribution) with clean process-tree termination.
- **Embedded UI (Vite + xterm.js)**: Serves a modern Vite frontend (`desktop/frontend/`) with `@xterm/xterm` for real-time ANSI terminal log rendering and retry controls, embedded directly into the Go binary.
- **Auto-Navigation & Link Routing**: Automatically navigates to `http://127.0.0.1:18888/` upon backend readiness, while routing external links (`window.open`, Electron API) to the default system browser via declarative `WebviewWindowOptions.JS` injection.
- **Zero-CGO & Instant Build**: Compiles with `CGO_ENABLED=0` in ~3 seconds with no MSVC or Windows SDK requirements.

## Commands

```bash
# Run tests
go test -v ./...

# Build production executable (bin/vcclient-forge.exe)
wails3 task build
```
