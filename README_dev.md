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

4. **System Audio Dependency (Linux only)**: Required by `sounddevice` for host audio I/O.
   ```bash
   sudo apt-get update && sudo apt-get install -y libportaudio2
   ```

5. **Tauri v2 Desktop Toolchain (Windows only)**: Required by `npm run build`, `npm run build:desktop`, and `npm run dev:desktop` on Windows.
   * **Rust and Cargo**: Install stable Rust with the MSVC toolchain (normally `x86_64-pc-windows-msvc`), not the GNU toolchain. Verify with `rustc --version` and `cargo --version`.
   * **Visual Studio Build Tools 2022 or Visual Studio 2022**: Select **Desktop development with C++**, including the MSVC C++ build tools and a Windows 10 or Windows 11 SDK. Rust alone does not provide the required Windows linker and SDK.
   * **Microsoft Edge WebView2 Runtime**: Required to run the desktop host during development and on end-user machines. It may already be installed; the portable package does not install it.
   * **Tauri CLI**: Run `npm ci` from the repository root to install the project's locked `@tauri-apps/cli` dependency into `node_modules`. This does **not** install Rust, Visual Studio Build Tools, the Windows SDK, or WebView2; install those separately.
   * After installing system tools, reopen VS Code/terminals so their updated `PATH` is available. Run `npm run tauri -- info` from the repository root to diagnose missing prerequisites.

   For a new Windows x64 development environment, run these commands in PowerShell. The Build Tools installation can take several minutes and may request administrator approval:

   ```powershell
   winget install --id Microsoft.VisualStudio.2022.BuildTools --exact --source winget --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
   winget install --id Rustlang.Rustup --exact --source winget
   winget install --id Microsoft.EdgeWebView2Runtime --exact --source winget
   ```

   The Build Tools command selects the C++ workload and its recommended components, including MSVC and a Windows SDK. If Build Tools is already installed, `winget install` may skip it without adding the workload; open **Visual Studio Installer > Modify** and select **Desktop development with C++** and the components listed above. Skip the WebView2 command if its Runtime is already installed.

   Reopen VS Code/PowerShell, then select the stable MSVC toolchain and verify it:

   ```powershell
   rustup default stable-msvc
   rustc --version
   cargo --version
   ```

   After cloning the repository and running `npm ci` as shown below, run `npm run tauri -- info` to check the desktop environment. See the [Tauri Windows prerequisites](https://v2.tauri.app/start/prerequisites/#windows) for further details.

### Clone and Build Environment

Clone the repository and build the workspace for your target hardware accelerator:

```bash
git clone https://github.com/Maki-Daisuke/vcclient-forge.git
cd vcclient-forge
npm ci

# Choose ONE edition matching your development/testing target:
npm run build -- --edition cuda    # NVIDIA GPU (Windows / Linux)
npm run build -- --edition dml     # Windows Universal GPU (DirectX 12: AMD, Intel, NVIDIA)
npm run build -- --edition mac     # macOS (Apple Silicon M-series CoreML)
npm run build -- --edition cpu     # Generic CPU fallback
```

* `npm run build` builds all supported components (CPU by default): frontend assets in `frontend/dist`, the Python development environment, a frozen backend, and the release Tauri executable on Windows. Windows builds require the [desktop toolchain prerequisites](#prerequisites). Linux/macOS retain backend-only builds.
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

### Windows Desktop Host (Tauri v2)

The desktop host lives in `src-tauri/`. Complete the Windows Tauri toolchain setup under [Prerequisites](#prerequisites) before running these commands.

```powershell
npm ci
uv sync --project backend --extra cpu   # Or cuda / dml; choose one hardware edition
npm run dev:desktop
```

Tauri embeds only `src-tauri/bootstrap/`, displays startup status/logs, and launches `backend/.venv/Scripts/python.exe` directly. It waits for a readiness message from its own backend before navigating to `http://127.0.0.1:18888/`; the existing UI remains Python-served. A port conflict fails startup rather than attaching to an unrelated server. Initial model downloads can take time; startup has a ten-minute limit and failures offer retry.

The backend's private `--desktop_control=True` option disables its old client launcher, watches piped standard input for `shutdown` or EOF, and enables the readiness message. Do not use this option for normal terminal/server startup. Closing Tauri requests graceful shutdown of its own child, with a fifteen-second forced-termination fallback. Remote attachment is not implemented, and Python-served pages receive no Tauri command permissions.

`npm run test:desktop` tests the bootstrap states; `cargo test --locked --manifest-path src-tauri/Cargo.toml` tests Rust code. `npm run build:desktop` builds only the desktop executable, not a complete Python distribution. Bootstrap IPC, retry, navigation to the Python-served UI, and denial of native commands from that UI have been verified on Windows. Microphone permissions, native audio, and shutdown during conversion remain separate runtime checks.

---

## 3. Building Standalone Portable Packages

Build commands are defined once in `package.json`. `npm run build` uses `scripts/build.js` only to invoke `build:frontend`, `build:desktop` (Windows), and `build:backend` in order, forwarding edition/version arguments to the backend task. `scripts/build_backend.py` contains only the backend-specific environment and PyInstaller **onedir** steps; it does not invoke frontend or desktop builds. PyInstaller bundles Python, its standard library, and edition-specific dependencies, including CUDA/cuDNN for CUDA. `npm run package` runs the separate `scripts/build_package.py` to validate, copy, and optionally archive existing artifacts; it does not compile anything or synchronize Python dependencies. Distribute the entire package directory, not just the executable:

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

Windows packages always include the **release** `src-tauri/target/release/vcclient-forge.exe`; a debug build from `dev:desktop` is not sufficient. Missing desktop/backend executables, runtime files, UI assets (including split JavaScript and images), launchers, or license/readme files abort packaging **before creating the output directory**. The backend build records file names and sizes in `backend-manifest.json`; missing or truncated recorded files require rebuilding. Existing pre-split build outputs without this manifest also need rebuilding. WebView2 Runtime must already be installed on the destination computer; the portable package does not install it.

Build environments and PyInstaller analysis files live under `build/packaging/<platform>_<edition>_<python>/`. PyInstaller and its hooks are locked in the backend's `build` dependency group, separate from production and development dependencies. Build on each target operating system; PyInstaller does not cross-compile these distributions.

Archives are created as `dist/vcclient_<platform>_<edition>_v<VERSION>.7z` on all supported platforms:

The version comes from the root `package.json`'s `version` field. An optional leading `v` is removed before constructing the name so the filename contains only one `v` prefix.

Tauri also reads the root manifest through `"version": "../package.json"` in `src-tauri/tauri.conf.json`. Update the root `version` field to change both the native app version and the distribution name; use SemVer without a leading `v`, and keep the root metadata in `package-lock.json` synchronized.

```text
vcclient_<platform>_<edition>_v<VERSION>/
   vcclient-forge.exe        # Windows desktop host (required on Windows)
   main.exe                 # main on Linux/macOS
   _internal/               # Python, stdlib, extension modules, shared libraries
   frontend/dist/           # Web UI and license listings
   modules/                 # Downloaded inference modules (initially empty)
   model_dir/               # User models (initially empty)
   start.bat / start.sh
   README.md / LICENSE
```

End users extract the **entire directory** and launch `vcclient-forge.exe` on Windows, without installing Python or CUDA toolkits. Backend-only entry points (`main.exe`, `start.bat`, or `start.sh`) remain available. Frozen startup sets the working directory to the executable's directory, keeping downloaded models, settings, and logs beside the executable, outside `_internal`. The launchers run only the bundled backend (`main.exe` on Windows, `main` on Linux/macOS); developers use `npm start`.

Existing package folders and archives are never overwritten: use a new `--output-dir` for another build. Archive creation fails when the result is 2 GiB or larger. The Windows CUDA onedir archive measured on 2026-10-19 is **1,318,130,525 bytes (1.228 GiB)**, including Python and the selected CUDA libraries.

For an import/startup check without starting a server or downloading models, use `main.exe -- --help` (`./main -- --help` on Linux/macOS). Fire's help flags follow the separate `--`; `server --help` is not the same check. Windows CPU audio conversion has been confirmed manually. Python-free clean-machine validation and the non-Windows builds remain separate release checks.

---

## 4. Automated Testing & Code Quality

### Running Tests

Automated unit and integration tests are executed using pytest:

```bash
npm test
# Or directly via uv:
uv run --project backend pytest backend/tests
```

Test coverage includes:
* Import verification across server modules and inferencers.
* Graceful shutdown and Socket.IO connection/disconnection lifecycle.
* REST API endpoints (`/api/hello`, chunk conversion).
* Web frontend static file delivery (`/`).
* In-place ONNX export and pitch estimation pipelines (RMVPE, FCPE).

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

* **`ci.yml`**: Runs Ruff linting, formatting checks, and pytest on every push and pull request across Ubuntu, Windows, and macOS using Python 3.14 and Node.js 26.
* **`ci.yml` desktop job**: Tests bootstrap behavior, checks Rust formatting, runs Rust tests, and builds the Windows Tauri executable. It does not exercise real audio devices.
* **`release.yml`**: Automatically builds portable standalone packages across all hardware matrix editions when a new version tag (`v*`) is pushed, attaching the archives directly to GitHub Releases. Windows editions include Tauri; Linux/macOS retain backend-only packaging.

---

## 6. Project Structure Overview

```text
voice-changer/
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
├── frontend/                   # Frontend workspace
│   └── dist/                   # Built Web UI assets (.gitignored)
├── web_front/                  # Reference implementation B (golden 2025 binary assets)
├── client/                     # Reference implementation A (frozen 2024 uncompiled React source)
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
