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

- **Python Version**: Strictly pinned to `3.12` via `.python-version` and `pyproject.toml`.
- **Lockfile Integrity**: All dependency trees are locked deterministically in `uv.lock`.
- **Fast Virtualenvs**: `uv sync` provisions an identical, reproducible virtual environment across Windows, Linux, and macOS in seconds without global pollution.

## 2. Pure-ONNX Architecture and CUDA 12 Support

VCClient Forge prioritizes high-performance, lightweight pure-ONNX inference:

- **ONNX Runtime GPU**: Targets `onnxruntime-gpu>=1.19.0`, fully compatible with NVIDIA CUDA 12.x and TensorRT.
- **Transparent CUDA Environment Hook**: [`cuda_env.py`](../vcclient_dev/cuda_env.py) dynamically locates and registers CUDA runtime libraries into Windows DLL search paths, eliminating `cublas64_12.dll` missing errors without requiring manual system environment variable manipulation.
- **Hardware Fallback**: Supports CUDA, DirectML (Windows AMD/Intel), and highly parallelized CPU execution (`CPUExecutionProvider`).

## 3. Hybrid Task Runner via `package.json`

To bridge developer experience between the Node.js/Web frontend ecosystem and Python backend services, `package.json` acts as the unified task runner:

| Command                 | Action                                  | Implementation                           |
| ----------------------- | --------------------------------------- | ---------------------------------------- |
| `npm start`             | Launch VCClient in CUI/Server mode      | `uv run python main.py cui`              |
| `npm test`              | Run test suite                          | `uv run pytest`                          |
| `npm run lint`          | Lint with Ruff                          | `uv run ruff check`                      |
| `npm run lint:fix`      | Auto-fix lints                          | `uv run ruff check --fix`                |
| `npm run format`        | Format code with Ruff                   | `uv run ruff format`                     |
| `npm run clean`         | Clean build artifacts, venv, and caches | `node scripts/clean.js`                  |
| `npm run build:package` | Build portable distribution zip         | `uv run python scripts/build_package.py` |

## 4. Portable Packaging Pipeline (`scripts/build_package.py`)

A fully automated standalone distribution generator compiles portable bundles:

```bash
# Clean workspace to ensure a fresh build
npm run clean

# Build standalone CPU package (default)
npm run build:package

# Build standalone CUDA package (verified under 2GB)
npm run build:package -- --edition cuda
```

The build script creates a self-contained runtime environment using `uv`, includes only production assets, purges bytecode/compiler caches, and outputs a ready-to-distribute `.zip` archive into `dist/`.

For the full architectural analysis on achieving a sub-2GB CUDA portable distribution for direct GitHub Releases hosting, see **[Sub-2GB Portable Distribution and Packaging Architecture](./sub-2gb-portable-distribution-and-packaging.md)**.
