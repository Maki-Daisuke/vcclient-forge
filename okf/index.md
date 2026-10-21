---
title: "VCClient Forge Knowledge Base"
version: "0.1.0"
okf_version: "0.2"
description: "Open Knowledge Format bundle capturing architectural insights, reverse-engineering findings, and modernization decisions for VCClient Forge."
entries:
  - implementation-roadmap.md
  - origin-and-reverse-engineering.md
  - architectural-evolution.md
  - decompyle-plus-plus-traps-and-fixes.md
  - modern-runtime-and-toolchain.md
  - frontend-architecture-and-roadmap.md
  - streamlined-pitch-estimation-and-torch-free-pipeline.md
  - sub-2gb-portable-distribution-and-packaging.md
  - deprecating-and-removing-beatrice.md
  - deprecating-and-removing-ngrok.md
  - server-first-architecture-and-static-pipeline-roadmap.md
  - inversion-of-control-and-process-lifecycle.md
---

# VCClient Forge Knowledge Base

This knowledge bundle documents the reverse-engineering discoveries, historical architecture, bug fixes, and engineering decisions established during the development of **VCClient Forge** (a community-driven modernization and fork of `w-okada/voice-changer` v2.0.78-beta).

For recommended implementation order, dependencies, and conditional experiments, start with the **[Consolidated Implementation Roadmap](./implementation-roadmap.md)**. The articles below retain the detailed rationale and acceptance criteria.

## Knowledge Map

1. **[Origin and Reverse Engineering](./origin-and-reverse-engineering.md)**
   Why Forge reconstructed the unavailable 2.x source from the v2.0.78-beta binary distribution, and how bytecode extraction, decompilation, and disassembly made that possible. Explains the choice of an RVC-capable baseline and the model ecosystem behind Forge's dedicated RVC focus.

2. **[Architectural Evolution](./architectural-evolution.md)**
   How upstream evolved from a monolithic 1.x server into the modular 2.x application, and how Forge reorganized the inherited monorepo. Covers frontend/backend separation, entry-point consolidation, a stable frontend build location for the UI replacement, and removal of the redundant terminal UI.

3. **[Decompyle++ Traps and Critical Fixes](./decompyle-plus-plus-traps-and-fixes.md)**
   Symptom-to-fix post-mortems from restoring the reconstructed application: native audio startup, CPU provider selection, server startup, API response validation, and WASAPI compatibility. Shows how disassembly and root-cause analysis exposed broken control flow, calls, and defaults.

4. **[Modern Runtime and Toolchain](./modern-runtime-and-toolchain.md)**
   How Forge makes development and distribution reproducible with pinned Python environments, `uv` dependency locking, and unified npm tasks. Covers the ONNX Runtime hardware backends, automatic CUDA library discovery, and automated standalone packaging.

5. **[Next-Gen Frontend Architecture and Roadmap](./frontend-architecture-and-roadmap.md)**
   Why the legacy UI needs a redesign to make settings responsive and new backend features usable, and why Forge selects Svelte 5 + Vite and Tauri. Plans a Server Mode-first replacement, WebSocket notifications and Socket.IO removal, then WebSocket Client Mode, while preserving community translations.

6. **[Pitch Estimation: RMVPE Default and FCPE Alternative](./streamlined-pitch-estimation-and-torch-free-pipeline.md)**
   Why Forge chooses the RVC ecosystem's widely used RMVPE as its default and retains FCPE as an alternative. Consolidating pitch estimation reduces maintenance and user decision friction, with both estimators running through ONNX Runtime and NumPy.

7. **[Sub-2GB Portable Distribution and Packaging Architecture](./sub-2gb-portable-distribution-and-packaging.md)**
   How Forge fits a standalone CUDA distribution under GitHub Releases' 2 GiB per-asset limit using ONNX inference, CPU-only PyTorch for export, selected CUDA dependencies, PyInstaller onedir, and 7z compression. Covers the resulting 1.228 GiB archive, external writable data, safe workspace cleanup, and further packaging headroom.

8. **[Deprecating and Pruning Beatrice](./deprecating-and-removing-beatrice.md)**
   Why Forge chose to remove Beatrice even after restoring a working backend: distinct UI requirements and cross-platform native builds impose substantial maintenance costs, while dedicated Beatrice tools already exist. Concentrating on RVC keeps the application cohesive and development resources focused.

9. **[Deprecating and Removing ngrok](./deprecating-and-removing-ngrok.md)**
   Why ngrok no longer belongs in Forge: Colab's restrictions have largely ended the historical free-Colab workflow, and remote audio round trips conflict with the project's local real-time purpose. Includes Tailscale Serve as optional, separately managed access to a user's own host.

10. **[Server-First Audio Architecture & Static-Shape Pipeline Roadmap](./server-first-architecture-and-static-pipeline-roadmap.md)**
    A roadmap toward local round-trip latency of 100 ms or less, built around native Server Mode, fixed-length inference, direct output delivery, and bounded buffering. Develops GPU optimization through IO Binding, pitch estimation + RVC integration, retrieval-free full integration, and ONNX retrieval evaluation, assessing CUDA Graph capture at applicable stages.

11. **[Inversion of Control: Client-Driven Architecture and Process Lifecycle](./inversion-of-control-and-process-lifecycle.md)**
    How Forge inverts the legacy Python-centric master/slave model by isolating the Python backend to a pure HTTP/Socket.IO server, shifting UI and browser launching to client launchers (Tauri, shell scripts), and standardizing process lifecycle management via standard OS signals.
