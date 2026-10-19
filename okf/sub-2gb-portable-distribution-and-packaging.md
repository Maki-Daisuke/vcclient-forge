---
title: "Sub-2GB Portable Distribution and Packaging Architecture"
date: "2026-10-16"
author: "VCClient Forge Team"
category: "Architecture & Engineering Decisions"
tags:
  - packaging
  - distribution
  - github-releases
  - cuda
  - onnxruntime
  - optimization
  - ux
---

# Sub-2GB Portable Distribution and Packaging Architecture

## Executive Summary

One of the foundational design objectives of **VCClient Forge** is to deliver a completely standalone, zero-setup portable distribution that can be downloaded and run with a single click.

Crucially, VCClient Forge establishes a strict engineering constraint: **the portable distribution package (including CUDA runtime dependencies) must remain strictly under 2.00 GiB (2,147,483,648 bytes)**. This constraint enables direct hosting and automated release deployments on GitHub Releases, eliminating the multi-gigabyte bloat that likely drove upstream to rely on third-party hosting platforms like Hugging Face.

Through pure-ONNX inference, CPU-only PyTorch relegation, selected CUDA dependencies, and multi-threaded 7z (LZMA2) packaging, the Windows CUDA **PyInstaller onedir** distribution measured on 2026-10-19 is **1,318,130,525 bytes (1257.1 MiB / 1.228 GiB)**, including the Python interpreter and standard library. This leaves approximately **791 MiB** below the 2 GiB budget. The builder rejects archives at or above that limit.

---

## 1. Context: The "2GB Barrier" & Upstream Bloat

### Upstream Distribution via Hugging Face: The Presumed Reason

The original `w-okada/voice-changer` distributions were provided primarily via Hugging Face rather than GitHub Releases. It is presumed that the technical reason behind that choice was the package size:

- Upstream bundled a full CUDA-enabled PyTorch distribution (`torch`, `torchaudio`, and comprehensive NVIDIA CUDA/cuDNN shared libraries). The CUDA-enabled PyTorch runtime alone (especially monolithic shared libraries like `torch_cuda.dll` exceeding 1.5 GB uncompressed) generated an enormous disk footprint.
- As a result, distribution archives consistently ballooned over **3 GiB**.
- Because **GitHub Releases enforces a strict 2.00 GiB per-asset limit**, hosting these massive binaries directly on GitHub Releases was technically impossible, making external hosting on Hugging Face the practical necessity.

### The Downside of External Hosting

External hosting introduced substantial UX friction and maintenance overhead:

1. **User Confusion**: Non-technical users often struggled to identify the correct file to download amidst numerous branches, model checkpoints, and fragmented versions on Hugging Face.
2. **Broken CI/CD Automation**: Release pipelines could not publish standard GitHub Release assets automatically via straightforward GitHub Actions workflows.
3. **Bandwidth & Storage Inefficiency**: Users were forced to download gigabytes of unused PyTorch training kernels and redundant framework binaries just to perform real-time inference.

**VCClient Forge Core Directive:**

> _"If a feature or library is not strictly required for real-time inference, it must not be in the runtime bundle. Distribution must fit within standard GitHub Releases."_

---

## 2. Core Architectural Breakthroughs for Sub-2GB Packaging

Achieving a sub-2GB CUDA portable distribution was made possible by four foundational architectural decisions:

```
+-------------------------------------------------------------------------------+
|                       Core Architectural Pillars                              |
+-------------------------------------------------------------------------------+
|  1. Pure-ONNX Inference Pipeline       --> Eliminate Torch from hot path      |
|  2. CPU-Only PyTorch Relegation         --> 118MB vs 2.5GB+ CUDA Torch         |
|  3. Surgical NVIDIA Dependency Pruning --> Keep only ONNX Runtime CUDA DLLs   |
|  4. PyInstaller onedir + 7z (LZMA2)    --> 1.228GiB self-contained archive   |
+-------------------------------------------------------------------------------+
```

### 1. Pure-ONNX Inference Pipeline (Torch-Free)

All runtime inference components—RVC voice conversion, RMVPE/FCPE pitch estimation, audio feature extraction, and sinc resampling—run exclusively on **ONNX Runtime and NumPy**. Not a single inference tensor passes through PyTorch.

### 2. CPU-Only PyTorch for In-Place Model Export

PyTorch is retained strictly as an offline utility for the automatic `.pth` ➡ `.onnx` in-place exporter. Because model export is run only once upon importing a voice slot and is not latency-critical:

- PyTorch is pinned to its **CPU-only build (`torch==2.*+cpu`)**, requiring only ~118 MB.
- Heavy companion libraries (`torchaudio`, `torchfcpe`, `torchvision`) are completely eradicated.

### 3. Surgical NVIDIA Dependency Selection

ONNX Runtime GPU (`onnxruntime-gpu`) requires specific CUDA/cuDNN libraries for execution (`cublas`, `cudart`, `cudnn`, `cufft`). Previously, these were inherited transitively through the gigantic PyTorch CUDA wheel.

In Forge, we isolate and bundle only the exact PyPI wheels needed by ONNX Runtime:

- Bundled: `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, `nvidia-cufft-cu12`, `nvidia-cuda-runtime-cu12`.
- Pruned: `nvidia-curand-cu12` (saving ~77 MB) and other non-inference components.
- Path Resolution: `backend/vcclient/utils/cuda_env.py` automatically injects these paths into `os.add_dll_directory` and `PATH` on Windows at startup.

### 4. Standardized 7z (LZMA2) Multi-Threaded Packaging

Rather than standard Deflate compression used in `.zip`, VCClient Forge standardizes distribution packaging entirely on **7z (LZMA2)**:

- **Binary Compression**: The measured Windows CUDA onedir payload contains **3,343,350,748 bytes** before compression; the resulting LZMA2 archive contains **1,318,130,525 bytes (1.228 GiB)**. These measurements include Python, unlike the earlier virtual-environment packaging experiment.
- **High-Speed Parallelization**: Built with `7z` native CLI integration configured for balanced thread and dictionary limits (`-mx=5 -md=32m -mmt=4`), avoiding out-of-memory errors on high-core CPUs while compressing multi-gigabyte runtimes in seconds.

### 5. Self-Contained Python via PyInstaller Onedir

A virtual environment is not a portable Python installation: its `python.exe` can still depend on a base installation outside the package. Forge therefore uses `uv` only to prepare isolated edition-specific **build environments**, and PyInstaller to collect the actual interpreter, standard library, application modules, and native dependencies.

- **Onedir layout**: `main.exe` (or `main`) sits next to `_internal/`. Unlike `onefile`, startup does not unpack the multi-gigabyte runtime into a temporary directory.
- **Explicit dynamic dependencies**: Collect the Uvicorn implementations, Engine.IO ASGI driver, dynamically loaded server module, and CUDA edition's `nvidia` packages and shared libraries. Existing PyInstaller hooks collect scientific/audio dependencies.
- **External writable data**: Frontend assets, models, downloaded inference modules, settings, and logs live beside the executable. Frozen startup uses this location regardless of the caller's working directory.
- **Reproducibility and preservation**: PyInstaller is locked in a separate `build` dependency group. Existing package directories and archives are not overwritten; another build uses a new output directory.

---

## 3. Workspace Clean Architecture (`npm run clean`)

To maintain a reproducible build environment, `package.json` provides `npm run clean`, backed by [`scripts/clean.js`](../scripts/clean.js).

### The Windows File-Lock Challenge

In Python on Windows, attempting to delete the active `.venv` from a Python-based cleanup script (`uv run python clean.py`) triggers `PermissionError: [WinError 5] Access is denied` because the executing `python.exe` and loaded DLLs are locked by the operating system.

### The Decoupled Node.js Solution

- `scripts/clean.js` runs externally via Node.js, completely out-of-process from Python.
- It safely tears down `dist/`, `backend/.venv`, `frontend/dist/`, `modules/`, and internal caches.
- **User Safety**: It intentionally leaves `model_dir/` untouched, protecting the user's imported voice models from accidental destruction during development resets.

---

## 4. Future Headroom and Roadmap

The measured Windows CUDA onedir `.7z` package is within the 2 GiB limit (1.228 GiB). Future reductions must be measured against this self-contained baseline:

### Tauri v2 + Svelte Desktop Application

As detailed in [Frontend Architecture & Roadmap](./frontend-architecture-and-roadmap.md), migrating from the legacy web UI to **Tauri v2 + Svelte 5**:

- Avoids bundling Electron's Chromium and Node.js runtime by using the operating system's native WebView, preserving more of the strict 2 GiB archive budget for the Python/CUDA inference runtime.
- Uses a Rust application host without bundling the Node.js runtime used by Electron, keeping desktop-shell memory overhead small relative to the audio inference workload.
