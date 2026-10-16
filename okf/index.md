---
title: "VCClient Forge Knowledge Base"
version: "0.1.0"
okf_version: "0.2"
description: "Open Knowledge Format bundle capturing architectural insights, reverse-engineering findings, and modernization decisions for VCClient Forge."
entries:
  - origin-and-reverse-engineering.md
  - architectural-evolution.md
  - decompyle-plus-plus-traps-and-fixes.md
  - modern-runtime-and-toolchain.md
  - frontend-architecture-and-roadmap.md
  - streamlined-pitch-estimation-and-torch-free-pipeline.md
  - sub-2gb-portable-distribution-and-packaging.md
  - deprecating-and-removing-beatrice.md
  - deprecating-and-removing-ngrok.md
---

# VCClient Forge Knowledge Base

This knowledge bundle documents the reverse-engineering discoveries, historical architecture, bug fixes, and engineering decisions established during the development of **VCClient Forge** (a community-driven modernization and fork of `w-okada/voice-changer` v2.0.78-beta).

## Knowledge Map

1. **[Origin and Reverse Engineering](./origin-and-reverse-engineering.md)**
   Why and how this project was reverse-engineered from the Hugging Face v2.0.78-beta distribution zip, addressing the missing upstream source code (GitHub Issue #1521) and explaining why v2.0.78-beta was chosen over the fragmented v2.2.2-beta.

2. **[Architectural Evolution](./architectural-evolution.md)**
   The journey from the monolithic 1.x era (`MMVCServerSIO.py`) to the modular 2.x era (`vcclient_dev`), PyInstaller bundling structure, and cleanup of legacy monorepo artifacts.

3. **[Decompyle++ Traps and Critical Fixes](./decompyle-plus-plus-traps-and-fixes.md)**
   Deep-dive technical post-mortem on bytecode decompilation errors that broke server-device audio monitoring, CPU execution provider fallback, and API validation.

4. **[Modern Runtime and Toolchain](./modern-runtime-and-toolchain.md)**
   Modern Python engineering principles applied to the codebase: `uv` package management, `pyproject.toml`, pure-ONNX execution, and `package.json` task running.

5. **[Next-Gen Frontend Architecture and Roadmap](./frontend-architecture-and-roadmap.md)**
   Analysis of legacy UI bottlenecks (slider locking, unbuffered network flood), complete preservation of 13-language i18n JSON assets, and the 2-stage transition strategy from Svelte 5 Web SPA to ultra-lightweight Wails desktop packaging.

6. **[Streamlined Pitch Estimation: Why RMVPE & FCPE Only](./streamlined-pitch-estimation-and-torch-free-pipeline.md)**
   Consolidating pitch estimation to the definitive standard (RMVPE) and a newer ultra-fast model (FCPE), eliminating decision fatigue, pure-ONNX execution, and self-healing whitelist fallback.

7. **[Sub-2GB Portable Distribution and Packaging Architecture](./sub-2gb-portable-distribution-and-packaging.md)**
   Overcoming upstream's 2GB GitHub Releases limitation to enable direct, one-click distribution: pure-ONNX inference, CPU-only PyTorch relegation, surgical CUDA dependency selection, and workspace reset architecture (`npm run clean`).

8. **[Deprecating and Pruning Beatrice](./deprecating-and-removing-beatrice.md)**
   Architectural rationale for fully pruning Beatrice support: dual-UI maintenance burden, limits of maintaining a native C/C++ cross-platform toolchain, presence of dedicated official tools, and doubling down on deep-learning RVC.

9. **[Deprecating and Removing ngrok](./deprecating-and-removing-ngrok.md)**
   Why cloud HTTP tunneling via ngrok was excised: network latency contradiction with real-time audio DSP, expiration of Google Colab's historical use case, browser Web Audio SSL/TLS friction, and recommending direct WireGuard mesh routing (Tailscale Serve) for remote compute.
