---
type: concept
title: "Modern Runtime, Toolchain, and Build System"
description: "How VCClient Forge establishes deterministic builds, modern Python tooling, and cross-platform workflows."
tags: [uv, python, toolchain, packaging, onnxruntime, cuda]
timestamp: 2026-10-14T12:28:00Z
---

# Modern Runtime, Toolchain, and Build System

## 1. Deterministic Python Management with `uv`

Upstream distributions relied on bundled standalone Python embeds or instructions requiring manual Anaconda/virtual environment setup. VCClient Forge standardizes on [`uv`](https://docs.astral.sh/uv/):

- **Python Version**: Strictly pinned to a specific Python version for each development/runtime baseline; update the pin as the project deliberately moves to newer Python releases.
- **Lockfile Integrity**: All dependency trees are locked deterministically in `uv.lock`.
- **Fast Virtualenvs**: `uv sync` provisions an isolated environment from the cross-platform lockfile. Installed artifacts remain platform- and Python-specific.

## 2. Modern Python & NumPy 2.x Audio Pipeline

VCClient Forge moves beyond the original distribution's Python 3.10 stack and uses NumPy 2.x. Runtime versions are pinned in project configuration and the lockfile. These upgrades modernize the supported toolchain; performance and latency benefits should be established with application-specific benchmarks:

- **NumPy 2.x**: Provides optimized array kernels, including CPU SIMD implementations where supported. Measure the operations and target platforms used by the audio pipeline before attributing end-to-end latency improvements.
- **Current CPython**: Use the project's pinned Python release and validate compatibility/performance as that pin advances.
- **CPU Inference**: ONNX Runtime CPUExecutionProvider is available as a backend; its throughput and scheduling impact depend on model, thread settings, and hardware.

## 3. Pure-ONNX Architecture and CUDA 13 Support

VCClient Forge prioritizes high-performance, lightweight pure-ONNX inference:

- **ONNX Runtime GPU**: Uses the CUDA execution provider with unified CUDA 13 (`nvidia-cublas`, `nvidia-cudnn-cu13`, `nvidia-cufft`, `nvidia-cuda-runtime`, `nvidia-curand`) across Windows x64, Linux x64, and Linux ARM64 selected by the project's `cuda` extra.
- **Transparent Hardware Acceleration Runtime Hook**: [`runtime_env.py`](../backend/vcclient/device/runtime_env.py) delegates to [`vcclient.device.providers`](../backend/vcclient/device/providers/) (`cuda.py`, `openvino.py`, `directml.py`, `coreml.py`) to locate and preload CUDA/cuDNN runtime libraries and register OpenVINO Execution Provider plugins via `os.add_dll_directory`, `onnxruntime.preload_dlls`, and `onnxruntime.register_execution_provider_library`, avoiding manual system-wide CUDA or OpenVINO installations.
- **Hardware Backends**: Supports CUDA, OpenVINO (CPU/GPU/NPU), DirectML (Windows), CoreML (macOS), and CPU (`CPUExecutionProvider`).

## 4. Hybrid Task Runner via `package.json`

To bridge developer experience between the Node.js/Web frontend ecosystem and Python backend services, `package.json` acts as the unified task runner:

| Command                  | Action                                                 | Implementation                                                      |
| ------------------------ | ------------------------------------------------------ | ------------------------------------------------------------------- |
| `npm start`              | Launch VCClient from source                            | `uv run --project backend python backend/main.py`                   |
| `npm test`               | Run backend type checks and tests, and desktop tests   | `npm run test:backend && npm run test:desktop`                      |
| `npm run lint`           | Lint with Ruff                                         | `uv run --project backend ruff check backend`                       |
| `npm run lint:fix`       | Auto-fix lints                                         | `uv run --project backend ruff check --fix backend`                 |
| `npm run format`         | Format backend Python and desktop Go                   | `uv run --project backend ruff format backend && gofmt -w desktop`  |
| `npm run format:check`   | Check backend Python formatting without modifying      | `uv run --project backend ruff format --check backend`              |
| `npm run clean`          | Clean build artifacts, venv, and caches                | `node scripts/clean.js`                                             |
| `npm run build`          | Invoke frontend, desktop, and backend npm tasks        | `node scripts/build.js`                                             |
| `npm run build:frontend` | Build production Svelte 5 assets                       | `npm --prefix frontend run build -- --outDir dist`                  |
| `npm run test:frontend`  | Run Playwright browser tests                           | `npm --prefix frontend test`                                        |
| `npm run build:backend`  | Sync backend dependencies for target edition           | `uv run --no-project --python 3.14 python scripts/build_backend.py` |
| `npm run package`        | Freeze backend (onedir) and package standalone archive | `uv run --no-project --python 3.14 python scripts/build_package.py` |

## 5. Portable Packaging Pipeline (`scripts/build_package.py`)

Build and sync artifacts first, then package into standalone distributions:

```bash
# Build standard components (default), then package:
npm run build
npm run package

# Build standalone CUDA package (verified under 2GB):
npm run build -- --edition cuda
npm run package -- --edition cuda
```

Build command definitions live only in `package.json`; `scripts/build.js` invokes the named component tasks rather than maintaining another set of frontend/desktop commands in Python. The backend development task `scripts/build_backend.py` synchronizes backend dependencies for the target edition. The standalone packaging pipeline `scripts/build_package.py` synchronizes an isolated edition-specific build environment under `build/packaging/`, runs PyInstaller in **onedir** mode, validates prerequisites, and packages the desktop binary (`vcclient-forge.exe` on Windows, `vcclient-forge` on Linux/macOS) and frozen backend into a `.7z` archive. The distribution contains `main.exe` (or `main`) and `_internal/` with Python, its standard library, and required dependencies; it does not ship a virtual environment. Frontend assets and writable model/settings directories stay beside the executable, with `vcclient-forge.exe` / `vcclient-forge` alongside them. The optional `.7z` archive is written to `dist/` and must be smaller than 2 GiB. Existing artifacts are protected; select a new `--output-dir` when repackaging instead of cleaning user data.

For the full architectural analysis on achieving a sub-2GB CUDA portable distribution for direct GitHub Releases hosting, see **[Sub-2GB Portable Distribution and Packaging Architecture](./sub-2gb-portable-distribution-and-packaging.md)**.
