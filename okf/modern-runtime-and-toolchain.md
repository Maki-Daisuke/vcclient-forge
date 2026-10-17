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

- **Python Version**: Strictly pinned to `3.14` (CPython 3.14.8) via `.python-version` and `pyproject.toml`.
- **Lockfile Integrity**: All dependency trees are locked deterministically in `uv.lock`.
- **Fast Virtualenvs**: `uv sync` provisions an identical, reproducible virtual environment across Windows, Linux, and macOS in seconds without global pollution.

## 2. Higher-Efficiency Audio Pipeline (Python 3.14 & NumPy 2.x)

VCClient Forge upgrades from the legacy Python 3.12 stack to Python 3.14.8 and NumPy >= 2.0.0 (2.5.4), delivering improved stability, pipeline efficiency, and lower latency for real-time voice conversion:

- Optimized Array Operations (NumPy 2.x): Leverages NumPy 2.x's refined Universal Intrinsics for CPU-native SIMD vectorization across AVX2, AVX-512, and ARM NEON. Basic array operations, type casting, slicing, and windowing functions execute with minimal overhead, maintaining tight audio buffer latencies.
- CPython Runtime Enhancements: Python 3.14 provides streamlined frame evaluation and interpreter-level optimizations, reducing invocation overhead within high-frequency audio chunk loops (typically 40–100Hz real-time processing).
- CPU Inference Efficiency: Streamlined pre/post-processing combined with ONNX Runtime optimizations (CPUExecutionProvider) reduces overall CPU utilization and jitter, preserving vital system headroom for gaming and streaming workloads.

## 3. Pure-ONNX Architecture and CUDA 12 Support

VCClient Forge prioritizes high-performance, lightweight pure-ONNX inference:

- **ONNX Runtime GPU**: Targets `onnxruntime-gpu>=1.20.0`, fully compatible with NVIDIA CUDA 12.x and TensorRT.
- **Transparent CUDA Environment Hook**: [`cuda_env.py`](../backend/vcclient/utils/cuda_env.py) dynamically locates and registers CUDA runtime libraries into Windows DLL search paths, eliminating `cublas64_12.dll` missing errors without requiring manual system environment variable manipulation.
- **Hardware Fallback**: Supports CUDA, DirectML (Windows AMD/Intel), and highly parallelized CPU execution (`CPUExecutionProvider`).

## 4. Hybrid Task Runner via `package.json`

To bridge developer experience between the Node.js/Web frontend ecosystem and Python backend services, `package.json` acts as the unified task runner:

| Command                 | Action                                  | Implementation                                              |
| ----------------------- | --------------------------------------- | ----------------------------------------------------------- |
| `npm start`             | Launch VCClient in Server mode          | `uv run --project backend python backend/main.py server`    |
| `npm test`              | Run test suite                          | `uv run --project backend pytest backend/tests`             |
| `npm run lint`          | Lint with Ruff                          | `uv run --project backend ruff check backend`               |
| `npm run lint:fix`      | Auto-fix lints                          | `uv run --project backend ruff check --fix backend`         |
| `npm run format`        | Format code with Ruff                   | `uv run --project backend ruff format backend`              |
| `npm run format:check`  | Check formatting without modifying      | `uv run --project backend ruff format --check backend`      |
| `npm run clean`         | Clean build artifacts, venv, and caches | `node scripts/clean.js`                                     |
| `npm run build:package` | Build portable distribution 7z          | `uv run --project backend python scripts/build_package.py`  |

## 5. Portable Packaging Pipeline (`scripts/build_package.py`)

A fully automated standalone distribution generator compiles portable bundles:

```bash
# Clean workspace to ensure a fresh build
npm run clean

# Build standalone CPU package (default)
npm run build:package

# Build standalone CUDA package (verified under 2GB)
npm run build:package -- --edition cuda
```

The build script creates a self-contained runtime environment using `uv`, includes only production assets, purges bytecode/compiler caches, and outputs a ready-to-distribute `.7z` archive into `dist/`.

For the full architectural analysis on achieving a sub-2GB CUDA portable distribution for direct GitHub Releases hosting, see **[Sub-2GB Portable Distribution and Packaging Architecture](./sub-2gb-portable-distribution-and-packaging.md)**.
