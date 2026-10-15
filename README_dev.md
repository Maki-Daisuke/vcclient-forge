# VCClient Forge - Developer & Build Guide

This guide covers setting up the development environment, running from source, building standalone distributions, and running the automated test suite.

---

## 1. Development Environment Setup

This project uses [uv](https://docs.astral.sh/uv/) for fast, deterministic Python environment and dependency management.

### Prerequisites

Install `uv`:

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Linux & macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Clone and Synchronize

Clone the repository and synchronize the dependencies for your target hardware accelerator:

```bash
git clone https://github.com/Maki-Daisuke/vcclient-forge.git
cd vcclient-forge

# Choose ONE edition matching your development/testing target:
uv sync --extra cuda    # NVIDIA GPU (Windows / Linux)
uv sync --extra dml     # Windows Universal GPU (DirectX 12: AMD, Intel, NVIDIA)
uv sync --extra mac     # macOS (Apple Silicon M-series CoreML)
uv sync --extra cpu     # Generic CPU fallback
```

* Python 3.14 is automatically downloaded, isolated, and pinned via `.python-version`.
* The locked dependencies (`uv.lock`) guarantee an identical environment across machines.

---

## 2. Running from Source

You can run the application directly from the repository using the multi-stage fallback startup scripts or the `uv` CLI:

* **Windows**: Run `start.bat` (Command Prompt) or `start.ps1` (PowerShell).
* **Linux / macOS**: Run `./start.sh`.
* **CLI (Direct)**:
  ```bash
  uv run python main.py
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
# Build NVIDIA CUDA edition (Windows / Linux)
uv run python scripts/build_package.py --edition cuda

# Build Windows DirectML edition
uv run python scripts/build_package.py --edition dml

# Build Apple Silicon macOS edition
uv run python scripts/build_package.py --edition mac

# Build CPU edition
uv run python scripts/build_package.py --edition cpu
```

* `--edition <edition>`: Target edition (`cuda`, `dml`, `mac`, `cpu`, default: `cpu`).
* `--output-dir <path>`: Destination directory for artifacts (default: `dist/`).
* `--skip-zip`: Create the uncompressed package folder without archiving to `.zip`.

You can also use npm to build packages:
```bash
npm run build:package -- --edition cuda
```

Artifacts are created as `dist/vcclient_<platform>_<edition>_v<VERSION>.zip`. End users simply extract the archive and launch `start.bat` or `start.sh` without installing Python or CUDA toolkits.

---

## 4. Automated Testing & Code Quality

### Running Tests

Automated unit and integration tests are executed using pytest:

```bash
uv run pytest
```

Test coverage includes:
* Import verification across server modules, inferencers, and CUI.
* REST API endpoints (`/api/hello`, chunk conversion).
* Web frontend static file delivery (`/`).

### Linting & Formatting

Code formatting and linting are powered by [Ruff](https://docs.astral.sh/ruff/) configured via `pyproject.toml`:

```bash
# Check for lint issues
uv run ruff check

# Automatically fix lint issues
uv run ruff check --fix

# Format code
uv run ruff format
```

---

## 5. CI/CD Architecture

Continuous integration and automated release workflows are configured in `.github/workflows/`:

* **`ci.yml`**: Runs Ruff linting and pytest on every push and pull request across Ubuntu, Windows, and macOS with Python 3.10 and 3.12.
* **`release.yml`**: Automatically builds portable standalone packages across all hardware matrix editions when a new version tag (`v*`) is pushed, attaching the archives directly to GitHub Releases.

---

## 6. Project Structure Overview

```text
voice-changer/
├── main.py                     # Primary application entry point
├── pyproject.toml              # Project metadata, dependencies, extras, and tool configurations
├── uv.lock                     # Deterministic dependency lockfile
├── .python-version             # Pinned Python version (3.12)
├── scripts/
│   └── build_package.py        # Portable package builder
├── start.bat / start.ps1       # Windows startup scripts with 3-stage fallback
├── start.sh                    # Linux / macOS startup script
├── tests/                      # Automated test suite (pytest)
├── vcclient_dev/               # Core application implementation
│   ├── utils/cuda_env.py       # Encapsulated platform-specific GPU runtime initialization
│   ├── server/                 # FastAPI REST and Socket.IO servers
│   └── voice_changer/          # Audio pipeline, inferencers, and model management
└── web_front/                  # Web UI frontend assets (HTML, JavaScript, CSS)
```
