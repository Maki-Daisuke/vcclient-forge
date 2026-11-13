# VCClient Forge - Developer & Build Guide

This guide covers setting up the development environment, running from source, building standalone distributions, and running the automated test suite.

---

## 1. Development Environment Setup

This project uses [uv](https://docs.astral.sh/uv/) for fast, deterministic Python environment and dependency management.

### Prerequisites

1. **[uv](https://docs.astral.sh/uv/)**: Fast, deterministic Python package and environment manager.
   ```bash
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

   # Linux & macOS
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **[Node.js](https://nodejs.org/) & npm**: Unified task runner and workspace management.
   * Node.js v24+ (v26 LTS recommended).
   * Verified via `node -v` and `npm -v`.

3. **[7-Zip](https://www.7-zip.org/) (`7z`)**: Required for creating ultra-compact standalone `.7z` distributions.
   * **Windows**: `winget install 7zip.7zip` (or install from [7-zip.org](https://www.7-zip.org/)). Ensure `7z` is added to `PATH`.
   * **Ubuntu/Debian**: `sudo apt-get install p7zip-full`
   * **macOS**: `brew install p7zip`

4. **System Audio & Desktop Dependencies (Linux only)**: Required by `sounddevice` for host audio I/O and by Wails v3 for GTK4/WebKitGTK 6.0 compilation.
   ```bash
   sudo apt-get update && sudo apt-get install -y libportaudio2 build-essential pkg-config libgtk-4-dev libwebkitgtk-6.0-dev
   ```

5. **Wails v3 Desktop Toolchain**: Required by `npm run build`, `npm run build:desktop`, `npm run dev:desktop`, and `npm run test:desktop`.
   * **Go 1.27+**: Install from [go.dev](https://go.dev/dl/). Verify with `go version`.
   * **Wails v3 CLI**:
     ```bash
     go install github.com/wailsapp/wails/v3/cmd/wails3@v3.1.0
     ```
   * **Desktop Frontend Dependencies**: Installed by `npm run setup:dev` below.
   * **Windows**: Uses pure Go (`CGO_ENABLED=0`) and Microsoft Edge WebView2 Runtime (pre-installed on Windows 10/11). No MSVC or Windows SDK is required.
   * **Linux / macOS**: Compiles with `CGO_ENABLED=1` against GTK4 + WebKitGTK 6.0 (`libgtk-4-dev` and `libwebkitgtk-6.0-dev` on Ubuntu 24.04) or macOS Cocoa/WebKit frameworks.

### Clone and Build Environment

Clone the repository and build the workspace for your target hardware accelerator:

```bash
git clone https://github.com/Maki-Daisuke/vcclient-forge.git
cd vcclient-forge
npm run setup:dev -- --edition cuda  # Or --edition standard (the default)

# Choose ONE edition matching your development/testing target:
npm run build -- --edition standard  # Universal edition (Intel OpenVINO, AMD/Windows DirectML, Apple CoreML, CPU)
npm run build -- --edition cuda      # NVIDIA Turing or newer (CUDA 13.x / cuDNN 9)
```

* `npm run build` builds all supported components (`standard` by default): the Svelte UI in `frontend/dist`, the Wails v3 desktop executable in `desktop/bin/`, and synchronizes backend dependencies.
* `npm run setup:dev` installs the locked root, Svelte frontend, and desktop frontend npm dependencies, downloads Go modules, and synchronizes backend dependencies for the selected edition. It does not install system prerequisites such as Node.js, uv, Go, Wails, or Linux system libraries.
* `npm run build -- --edition <edition>` selects the hardware edition (`standard` or `cuda`). `npm run build:frontend`, `npm run build:desktop`, and `npm run build:backend -- --edition <edition>` build individual components; `build:backend` synchronizes backend dependencies for the specified edition.
* Python 3.14 is automatically downloaded, isolated, and pinned via `.python-version`.
* The locked dependencies (`backend/uv.lock`) guarantee an identical environment across machines.
* Advanced: You can also synchronize the Python backend directly using `uv sync --project backend --extra <edition>`.

---

## 2. Running from Source

You can run the application directly from the repository using npm or the `uv` CLI:

* **npm (Unified)**: Run `npm start`.
* **CLI (Direct)**:
  ```bash
  uv run --project backend python backend/main.py
  ```

Once launched, the Web UI is served at:
```text
http://localhost:18888/
```

Initial model assets are downloaded into `model_dir/` upon the first startup.

### Svelte Frontend Development

The UI in `frontend/` uses Svelte 5, TypeScript, and Vite. Its dependencies
are managed separately from the root and desktop frontend packages. From the
repository root, install the locked dependencies and start the Vite server:

```bash
npm --prefix frontend ci
npm run dev:frontend
```

Open the URL printed by Vite, normally `http://127.0.0.1:5173`. For model data
and audio features, start the backend in another terminal. If its dependencies
have not been installed, synchronize the edition for your hardware first:

```bash
uv sync --project backend --extra standard  # Or cuda
npm start
```

Vite proxies `/api`, `/model_dir`, `/output.wav`, and Socket.IO to
`http://127.0.0.1:18888`. To use another backend, set `VCCLIENT_BACKEND_URL`
before starting Vite. For example, in PowerShell:

```powershell
$env:VCCLIENT_BACKEND_URL = 'http://127.0.0.1:18889'
npm run dev:frontend
```

The UI reads and updates the backend configuration and models; changes made in
the development UI affect the backend it connects to. Client Mode also requires
browser microphone permission for audio capture.

To check types and build the standalone preview:

```bash
npm run check:frontend
npm run build:frontend:preview
```

The preview build goes to `frontend/preview-dist`; `npm --prefix frontend run preview`
serves it. `npm run build:frontend` builds the UI in `frontend/dist`,
which is served by the backend and included in desktop distributions.

For browser tests, install Playwright's Chromium once and run:

```bash
npm --prefix frontend exec -- playwright install chromium
npm run test:frontend
```

These tests use mocked APIs and start a preview server on port 5174, which must be
free. Alternatively, set `PLAYWRIGHT_CHANNEL` to `msedge` or `chrome` to use an
installed browser. `npm test` does not include frontend tests. See
[frontend/README.md](frontend/README.md) for the UI's current behavior and implementation details.

### Desktop Host (Wails v3)

The desktop host lives in `desktop/`. Complete the Wails v3 toolchain setup under [Prerequisites](#prerequisites) before running these commands.

```bash
npm ci
npm --prefix frontend ci
npm --prefix desktop/frontend ci
uv sync --project backend --extra standard   # Or cuda; choose one hardware edition
npm run dev:desktop
```

Wails embeds `desktop/frontend/dist`, displays startup status/logs via `@xterm/xterm`, and launches the local Python virtual environment (`backend/.venv/Scripts/python.exe` on Windows, `backend/.venv/bin/python` on Linux/macOS) directly. It waits for the readiness sentinel from its own backend before navigating to `http://127.0.0.1:18888/`; the UI is Python-served. Closing the window terminates its child process tree cleanly.

`npm run test:desktop` tests the bootstrap states, builds the Vite frontend, and runs `go test .` inside `desktop/`. `npm run build:desktop` builds only the desktop executable (`desktop/bin/vcclient-forge.exe` on Windows, `desktop/bin/vcclient-forge` on Linux/macOS), not a complete Python distribution.

---

## 3. Building Standalone Portable Packages

Build commands are defined once in `package.json`. `npm run build` uses `scripts/build.js` to invoke `build:frontend`, `build:desktop`, and `build:backend` in order, forwarding edition/version arguments to the backend task. `scripts/build_backend.py` synchronizes backend dependencies for the target edition during development. Standalone distribution packaging is handled by `npm run package` (via `scripts/build_package.py`), which freezes the backend with PyInstaller **onedir** mode, validates prerequisites, bundles desktop/frontend assets, and optionally archives the package:

```bash
# Build all components, then package the SAME edition:
npm run build -- --edition standard
npm run package -- --edition standard

# CUDA example:
npm run build -- --edition cuda
npm run package -- --edition cuda

# Standalone packaging CLI:
uv run --no-project --python 3.14 python scripts/build_package.py --edition standard
uv run --no-project --python 3.14 python scripts/build_package.py --edition cuda
```

* `--edition <edition>`: Target edition (`standard`, `cuda`, default: `standard`).
* `--output-dir <path>`: Destination directory for artifacts (default: `dist/`).
* `--skip-archive`: Create the uncompressed package folder without archiving to `.7z`.
* `--python-version <version>`: Build-environment version (default: `3.14`). Use the same value when building and packaging.

Packages always include the compiled desktop binary (`desktop/bin/vcclient-forge.exe` on Windows, `desktop/bin/vcclient-forge` on Linux/macOS). Missing desktop/backend executables, runtime files, UI assets (including split JavaScript and images), launchers, or license/readme files abort packaging **before creating the output directory**. The backend build records file names and sizes in `backend-manifest.json`; missing or truncated recorded files require rebuilding. Existing pre-split build outputs without this manifest also need rebuilding.

Build environments and PyInstaller analysis files live under `build/packaging/<platform>_<edition>_<python>/`. PyInstaller and its hooks are locked in the backend's `build` dependency group, separate from production and development dependencies. Build on each target operating system; PyInstaller does not cross-compile these distributions.

Archives are created as `dist/vcclient_<platform>_<edition>_v<VERSION>.7z` on all supported platforms:

The version comes from the root `package.json`'s `version` field. An optional leading `v` is removed before constructing the name so the filename contains only one `v` prefix.

```text
vcclient_<platform>_<edition>_v<VERSION>/
   vcclient-forge(.exe)     # Desktop host executable (vcclient-forge.exe on Windows, vcclient-forge on Linux/macOS)
   main(.exe)               # Frozen backend executable (main.exe on Windows, main on Linux/macOS)
   _internal/               # Python, stdlib, extension modules, shared libraries
   frontend/dist/           # Web UI and license listings
   modules/                 # Downloaded inference modules (initially empty)
   model_dir/               # User models (initially empty)
   start.bat / start.sh
   README.md / LICENSE
```

End users extract the **entire directory** and launch `vcclient-forge.exe` (Windows) or `./vcclient-forge` (Linux/macOS), without installing Python or CUDA toolkits. Backend-only entry points (`main.exe` / `main`, `start.bat`, or `start.sh`) remain available. Frozen startup sets the working directory to the executable's directory, keeping downloaded models, settings, and logs beside the executable, outside `_internal`. The launchers run only the bundled backend (`main.exe` on Windows, `main` on Linux/macOS); developers use `npm start`.

Existing package folders and archives are never overwritten: use a new `--output-dir` for another build. Archive creation fails when the result is 2 GiB or larger. The Windows CUDA onedir archive measured on 2026-10-19 is **1,318,130,525 bytes (1.228 GiB)**, including Python and the selected CUDA libraries.

For an import/startup check without starting a server or downloading models, use `main.exe --help` (`./main --help` on Linux/macOS). Real-time audio conversion has been verified on physical hardware across Windows (NVIDIA CUDA, Intel Arc GPU via OpenVINO, AMD via DirectML, and AVX-512 CPU) and macOS (Apple Silicon M2 via CoreML).

---

## 4. Automated Testing & Code Quality

### Running Tests

Automated tests are divided into backend (type checking + pytest) and desktop suites, with a unified `npm test` runner:

```bash
# Run all tests (backend typecheck, pytest, and desktop bootstrap):
npm test

# Run backend tests only (mypy type checking + pytest):
npm run test:backend

# Run desktop bootstrap tests only:
npm run test:desktop

# Or run pytest directly via uv:
uv run --project backend pytest backend/tests
```

Test coverage includes:
* Import verification across server modules and inferencers.
* Graceful shutdown and Socket.IO connection/disconnection lifecycle.
* REST API endpoints (`/api/hello`, chunk conversion).
* Web frontend static file delivery (`/`).
* In-place ONNX export and pitch estimation pipelines (RMVPE, FCPE).
* Desktop bootstrap IPC, retry lifecycle, and navigation security.

### Static Type Checking

Static type analysis is powered by [mypy](https://mypy.readthedocs.io/) configured via `backend/pyproject.toml` (targeting Python 3.14):

```bash
# Run type checks across configured modules
npm run typecheck

# Or directly via uv:
uv run --project backend mypy --config-file backend/pyproject.toml
```

### Linting & Formatting

Code formatting and linting are powered by [Ruff](https://docs.astral.sh/ruff/) configured via `backend/pyproject.toml` (targeting Python 3.14):

```bash
# Check for lint issues
npm run lint

# Automatically fix lint issues
npm run lint:fix

# Format code
npm run format

# Verify formatting without modifying files
npm run format:check
```

---

## 5. CI/CD Architecture

Continuous integration and automated release workflows are configured in `.github/workflows/`:

* **`ci.yml`**: Runs Ruff linting, formatting checks, backend test suite (`npm run test:backend`, including mypy type checking and pytest), desktop test suite (`npm run test:desktop`), Go formatting checks (`gofmt`), and desktop host build (`npm run build:desktop`) on every push and pull request across Ubuntu, Windows, and macOS using Python 3.14, Node.js 26, and Go 1.27.
* **`release.yml`**: Automatically builds portable standalone packages (including the Wails v3 desktop executable and PyInstaller frozen backend) across all hardware matrix editions when a new version tag (`v*`) is pushed, attaching the archives directly to GitHub Releases.

---

## 6. Project Structure Overview

```text
vcclient-forge/
├── backend/                    # Python / uv workspace
│   ├── main.py                 # Backend application entry point (FastAPI + Socket.IO)
│   ├── pyproject.toml          # Python package metadata, dependencies, extras, and tool configs
│   ├── uv.lock                 # Deterministic dependency lockfile (Python 3.14)
│   ├── .python-version         # Pinned Python version (3.14)
│   ├── tests/                  # Pytest test suite
│   └── vcclient/               # Core application package
│       ├── device/             # Unified hardware discovery, execution providers, and runtime initialization
│       ├── server/             # FastAPI REST and Socket.IO servers (graceful shutdown)
│       └── voice_changer/      # Audio pipeline, inferencers, and model management
├── desktop/                    # Wails v3 (Go) cross-platform desktop host
│   ├── main.go                 # Application window, asset server, and backend supervisor
│   ├── sys_windows.go          # Windows hidden console & process-tree termination
│   ├── sys_other.go            # Linux / macOS signal-based process termination
│   ├── supervisor_test.go      # Go unit tests for backend discovery and readiness
│   ├── Taskfile.yml            # Wails v3 cross-platform task definitions
│   ├── build/                  # Platform-specific Taskfiles (windows, linux, darwin), icons, and config
│   └── frontend/               # Embedded bootstrap UI (Vite + TypeScript + xterm.js)
├── frontend/                   # Frontend workspace
│   └── dist/                   # Built Web UI assets (.gitignored)
├── tests/                      # Node.js test suite for desktop bootstrap & build orchestration
├── okf/                        # Open Knowledge Format architectural documentation
├── scripts/
│   ├── build.js                # Invokes component npm tasks without duplicating their commands
│   ├── build_backend.py        # Builds backend artifacts with PyInstaller
│   ├── build_package.py        # Validates and packages existing artifacts (sub-2GB target)
│   └── clean.js                # Workspace cleaning script
├── package.json                # Root task runner (npm start, npm test, etc.)
└── start.bat / start.sh        # Portable-package executable launchers
```
