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
     go install github.com/wailsapp/wails/v3/cmd/wails3@v3.0.0-beta.34
     ```
   * **Desktop Frontend Dependencies**: Run `npm --prefix desktop/frontend ci` from the repository root.
   * **Windows**: Uses pure Go (`CGO_ENABLED=0`) and Microsoft Edge WebView2 Runtime (pre-installed on Windows 10/11). No MSVC or Windows SDK is required.
   * **Linux / macOS**: Compiles with `CGO_ENABLED=1` against GTK4 + WebKitGTK 6.0 (`libgtk-4-dev` and `libwebkitgtk-6.0-dev` on Ubuntu 24.04) or macOS Cocoa/WebKit frameworks.

### Clone and Build Environment

Clone the repository and build the workspace for your target hardware accelerator:

```bash
git clone https://github.com/Maki-Daisuke/vcclient-forge.git
cd vcclient-forge
npm ci
npm --prefix desktop/frontend ci

# Choose ONE edition matching your development/testing target:
npm run build -- --edition cuda    # NVIDIA GPU (Windows / Linux)
npm run build -- --edition dml     # Windows Universal GPU (DirectX 12: AMD, Intel, NVIDIA)
npm run build -- --edition mac     # macOS (Apple Silicon M-series CoreML)
npm run build -- --edition cpu     # Generic CPU fallback
```

* `npm run build` builds all supported components (CPU by default): frontend assets in `frontend/dist`, the Wails v3 desktop executable in `desktop/bin/`, and a frozen backend.
* `npm run build -- --edition <edition>` selects the hardware edition. `npm run build:frontend`, `npm run build:desktop`, and `npm run build:backend -- --edition <edition>` build individual components; `build:backend` freezes the backend rather than just synchronizing dependencies.
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

### Desktop Host (Wails v3)

The desktop host lives in `desktop/`. Complete the Wails v3 toolchain setup under [Prerequisites](#prerequisites) before running these commands.

```bash
npm ci
npm --prefix desktop/frontend ci
uv sync --project backend --extra cpu   # Or cuda / dml / mac; choose one hardware edition
npm run dev:desktop
```

Wails embeds `desktop/frontend/dist`, displays startup status/logs via `@xterm/xterm`, and launches the local Python virtual environment (`backend/.venv/Scripts/python.exe` on Windows, `backend/.venv/bin/python` on Linux/macOS) directly. It waits for the readiness sentinel from its own backend before navigating to `http://127.0.0.1:18888/`; the existing UI remains Python-served. Closing the window terminates its child process tree cleanly.

`npm run test:desktop` tests the bootstrap states, builds the Vite frontend, and runs `go test .` inside `desktop/`. `npm run build:desktop` builds only the desktop executable (`desktop/bin/vcclient-forge.exe` on Windows, `desktop/bin/vcclient-forge` on Linux/macOS), not a complete Python distribution.

---

## 3. Building Standalone Portable Packages

Build commands are defined once in `package.json`. `npm run build` uses `scripts/build.js` only to invoke `build:frontend`, `build:desktop`, and `build:backend` in order, forwarding edition/version arguments to the backend task. `scripts/build_backend.py` contains only the backend-specific environment and PyInstaller **onedir** steps; it does not invoke frontend or desktop builds. PyInstaller bundles Python, its standard library, and edition-specific dependencies, including CUDA/cuDNN for CUDA. `npm run package` runs the separate `scripts/build_package.py` to validate, copy, and optionally archive existing artifacts; it does not compile anything or synchronize Python dependencies. Distribute the entire package directory, not just the executable:

```bash
# Build all components, then package the SAME edition:
npm run build -- --edition cpu
npm run package -- --edition cpu

# CUDA example (or choose dml / mac for both commands):
npm run build -- --edition cuda
npm run package -- --edition cuda

# Backend-only build and packaging CLI (frontend/desktop must already be built):
uv run --no-project --python 3.14 python scripts/build_backend.py --edition cuda
uv run --no-project --python 3.14 python scripts/build_package.py --edition cuda
```

* `--edition <edition>`: Target edition (`cuda`, `dml`, `mac`, `cpu`, default: `cpu`).
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

For an import/startup check without starting a server or downloading models, use `main.exe -- --help` (`./main -- --help` on Linux/macOS). Fire's help flags follow the separate `--`; `server --help` is not the same check. Windows CPU audio conversion has been confirmed manually. Python-free clean-machine validation and the non-Windows builds remain separate release checks.

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
│       ├── utils/cuda_env.py   # Encapsulated platform-specific GPU runtime initialization
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
├── web_front/                  # Bundled web UI assets (/ui/2.1.4/ and /ui/2.0.78/)
├── client/                     # Frozen 2024 uncompiled React reference source
├── tests/                      # Node.js test suite for desktop bootstrap & build orchestration
├── okf/                        # Open Knowledge Format architectural documentation
├── scripts/
│   ├── build.js                # Invokes component npm tasks without duplicating their commands
│   ├── build_frontend.js       # Synchronizes web_front assets to frontend/dist
│   ├── build_backend.py        # Builds backend artifacts with PyInstaller
│   ├── build_package.py        # Validates and packages existing artifacts (sub-2GB target)
│   └── clean.js                # Workspace cleaning script
├── package.json                # Root task runner (npm start, npm test, etc.)
└── start.bat / start.sh        # Portable-package executable launchers
```
