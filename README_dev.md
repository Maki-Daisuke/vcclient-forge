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

### Clone and Build Environment

Clone the repository and build the workspace for your target hardware accelerator:

```bash
git clone https://github.com/Maki-Daisuke/vcclient-forge.git
cd vcclient-forge

# Choose ONE edition matching your development/testing target:
npm run build:cuda    # NVIDIA GPU (Windows / Linux)
npm run build:dml     # Windows Universal GPU (DirectX 12: AMD, Intel, NVIDIA)
npm run build:mac     # macOS (Apple Silicon M-series CoreML)
npm run build:cpu     # Generic CPU fallback
```

* Builds frontend assets into `frontend/dist` and provisions the Python 3.14 virtual environment in one command.
* Python 3.14 is automatically downloaded, isolated, and pinned via `.python-version`.
* The locked dependencies (`backend/uv.lock`) guarantee an identical environment across machines.
* Advanced: You can also synchronize the Python backend directly using `uv sync --project backend --extra <edition>`.

---

## 2. Running from Source

You can run the application directly from the repository using the multi-stage fallback startup scripts, npm, or the `uv` CLI:

* **Windows**: Run `start.bat` (Command Prompt) or `start.ps1` (PowerShell).
* **Linux / macOS**: Run `./start.sh`.
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

---

## 3. Building Standalone Portable Packages

The packaging script (`scripts/build_package.py`) generates fully self-contained portable distributions bundled with an isolated Python standalone runtime and all dependencies:

```bash
# Recommended via npm:
npm run build:package -- --edition cuda   # NVIDIA GPU (Windows / Linux)
npm run build:package -- --edition dml    # Windows Universal GPU (DirectX 12)
npm run build:package -- --edition mac    # Apple Silicon macOS
npm run build:package -- --edition cpu    # Generic CPU

# Or directly via uv:
uv run --project backend python scripts/build_package.py --edition cuda
```

* `--edition <edition>`: Target edition (`cuda`, `dml`, `mac`, `cpu`, default: `cpu`).
* `--output-dir <path>`: Destination directory for artifacts (default: `dist/`).
* `--skip-archive`: Create the uncompressed package folder without archiving to `.7z`.

Artifacts are created as `dist/vcclient_<platform>_<edition>_v<VERSION>.7z`. End users simply extract the archive and launch `start.bat` or `start.sh` without installing Python or CUDA toolkits.

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
* **`release.yml`**: Automatically builds portable standalone packages across all hardware matrix editions when a new version tag (`v*`) is pushed, attaching the archives directly to GitHub Releases.

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
│   ├── build_frontend.js       # Synchronizes web_front assets to frontend/dist
│   ├── build_package.py        # Portable standalone package builder (sub-2GB target)
│   └── clean.js                # Workspace cleaning script
├── package.json                # Root task runner (npm start, npm test, etc.)
└── start.bat / .ps1 / .sh      # Multi-stage launcher scripts
```
