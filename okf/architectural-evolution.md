---
type: architecture
title: "Architectural Evolution and Monorepo Anatomy"
description: "Analysis of the architectural transition from 1.x to 2.x, original distribution topology, and cleanup of legacy monorepo artifacts."
tags: [architecture, packaging, monorepo, legacy, cleanup]
timestamp: 2026-10-14T12:26:00Z
---

# Architectural Evolution and Monorepo Anatomy

## 1. Evolution from 1.x to 2.x

Upstream `voice-changer` underwent a radical architectural overhaul that was never publicly committed to Git:

| Dimension | 1.x Series (GitHub Master) | 2.x Series (`v2.0.78-beta`) |
|---|---|---|
| **Entry Point** | Root `MMVCServerSIO.py` (monolithic) | Root `main.py` invoking `vcclient_dev` |
| **Package Structure** | Flat / unstructured scripts | Structured `vcclient_dev/` library package |
| **Web Server** | Socket.IO server embedded in script | FastAPI REST API + Socket.IO server |
| **Model Pipelines** | Tightly coupled MMVC/RVC scripts | Abstract `PipelineManager` with pure-ONNX inference |
| **Distribution** | Shell scripts running in user venv | Bundled standalone PyInstaller (`main.exe`) |

## 2. Anatomy of the Upstream "Chimera Monorepo"

The upstream repository grew organically as a multi-purpose monorepo housing unrelated sub-projects:

* **`docs/` (Removed in Forge)**: Not documentation, but a standalone client-side Web application ("Voice Recorder") hosted on GitHub Pages (`https://w-okada.github.io/voice-changer/`). Used in 2022 to record reading scripts (including Natsume Soseki's *I Am a Cat* and the ITA corpus) to build training datasets for MMVC. Not used by VCClient.
* **`trainer/`**: Dockerfiles and notebooks for training MMVC models on Google Colab or local GPU rigs.
* **`client/`**: Electron wrapper assets for desktop packaging.
* **`server/`**: The frozen 2024 source of the v1.x server, completely superseded by `vcclient_dev`.
* **`web_front/`**: Compiled SPA assets (React/Webpack) served statically by FastAPI.

## 3. Entry Point Resolution: The `main.py` Puzzle

During initial reverse-engineering, a copy of `main.py` was mistakenly placed both at the root and inside `vcclient_dev/`:

1. **Original Upstream Topology**: In the upstream build tree, `vcclient_dev/` contained **no** `main.py`. The single entry point was root `main.py`, which PyInstaller packaged as `main.exe`.
2. **Decompilation Duplication**: Decompilation produced `vcclient_dev/main.py`. Because edits were made to the duplicate while `npm start` executed root `main.py`, bug fixes were initially shadowed.
3. **Forge Resolution**: Consolidated all production entry logic into root [`main.py`](../main.py) with defensive `sys.path` bootstrapping, and removed the duplicate `vcclient_dev/main.py`.

## 4. Future Architecture Roadmap

A core design objective for VCClient Forge is transforming the legacy, idiosyncratic directory layout into an immediately intuitive, modern full-stack architecture:

* **Symmetric `frontend/` and `backend/` Structure**:
  * **`backend/`**: Refactor `vcclient_dev/` and consolidate all Python code under a unified `backend/` directory. All FastAPI routers, audio streaming interfaces, and ONNX/PyTorch inference pipelines will live cleanly here.
  * **`frontend/`**: Transition `web_front/` into a dedicated `frontend/` directory with a modern, reproducible build pipeline (Webpack/Vite), enabling transparent development and automated packaging.
  * **Instant Cognitive Clarity**: Anyone inspecting the repository root will immediately recognize where code lives (`frontend/` vs. `backend/`), cleanly eliminating ambiguity inherited from the legacy `vcclient_dev` naming.
