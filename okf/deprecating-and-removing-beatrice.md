---
title: "Deprecating and Pruning Beatrice: Why VCClient Forge Focuses Exclusively on RVC"
date: "2026-10-16"
author: "VCClient Forge Team"
category: "Architecture & Engineering Decisions"
tags:
  - beatrice
  - deprecation
  - pruning
  - rvc
  - architecture
  - engineering-capacity
  - simplicity
---

# Deprecating and Pruning Beatrice: Why VCClient Forge Focuses Exclusively on RVC

## Executive Summary

VCClient Forge has made the deliberate architectural decision to **fully deprecate and prune all support for the Beatrice engine (v1 JVS and v2 Alpha 2 / Beta 1)** from the codebase.

Following a thorough investigation and proof-of-concept backend restoration under modern Python 3.14 + NumPy 2.x, we evaluated the long-term feasibility and maintenance overhead of hosting Beatrice alongside RVC. The conclusion was based on core engineering and UX realities:

1. **Dual UI Maintenance Burden**: Beatrice and RVC have distinct operational models and parameter sets. Supporting Beatrice requires designing and maintaining virtually two separate, parallel user interfaces within a single client application.
2. **Native C/C++ Toolchain Maintenance**: Beatrice is implemented in C/C++ without official prebuilt PyPI wheels. Integrating native compilation into Forge's build pipeline and maintaining it across Windows, macOS, and Linux exceeds the engineering capacity of our development team.
3. **Official, Dedicated Alternatives Already Exist**: Dedicated standalone implementations—namely [aq2r/beatrice-client](https://github.com/aq2r/beatrice-client) and [prj-beatrice/beatrice-vst](https://github.com/prj-beatrice/beatrice-vst)—already deliver a purpose-built, optimal user experience for Beatrice.
4. **Architectural Cohesion**: VCClient Forge is anchored on ONNX Runtime and modern GPU acceleration (CUDA, DirectML). Focusing exclusively on this paradigm preserves codebase simplicity and maximizes engineering impact.

Pruning Beatrice eliminates substantial maintenance liabilities, keeps the project lean and maintainable, and allows the Forge team to dedicate its resources entirely to perfecting the RVC workflow.

---

## 1. Context & Technical Investigation

### Historical Background

In the upstream v2.0 era, experimental support was introduced for Beatrice v2 (Alpha 2 and Beta 1), alongside earlier Beatrice-JVS support. When modernization began on Python 3.14 and NumPy 2.x, Beatrice functionality was found broken:

- As a natural limitation of reverse engineering, the surviving distribution packages contained only compiled binaries; the glue code binding VCClient's Python codebase to Beatrice's underlying C/C++ engine, as well as the build scripts and procedures used to compile them, could not be recovered.
- Beatrice slot data types (`BeatriceV2SlotInfo`) and parameter extraction logic were incomplete.

### Proof-of-Concept Backend Restoration

Through disassembly and static binary analysis, the VCClient Forge team successfully reversed and restored the complete Beatrice v2 backend:

- Reconstructed `BeatriceV2SlotInfo` to parse model metadata and speaker configurations from `.toml`.
- Implemented a dynamic C-API dispatch shim to emulate NumPy 1.x ABI compatibility under NumPy 2.x.
- Reconstructed `SimpleBeatrice` and `Beatricev2Pipeline` with spherical speaker interpolation.
- Verified end-to-end audio conversion with passing test suites across both slot 10202 (Alpha 2) and slot 10203 (Beta 1).

While this proved that Beatrice _could_ be made to run, it also allowed us to objectively assess the practical realities of long-term maintenance.

---

## 2. Key Discoveries: Maintenance Reality & UX Duplication

### ① The Dual-UI Problem

Because Beatrice and RVC operate on entirely different concepts:

- Upstream handled this by conditionally hiding RVC controls (F0 Detectors, Index Ratio, GPU pickers, crossfade buffers) and rendering Beatrice-specific controls (formant shift, auto pitch alignment, and spherical morphing weight sliders) when a Beatrice model was selected.
- However, this essentially meant maintaining **two distinct application UIs and state-management lifecycles** crammed into a single codebase.
- For users seeking a streamlined voice changer, this split identity added complexity; for maintainers, any frontend refactor required double the testing and design effort.

### ② Native Build & Multi-Platform Maintenance Limits

While the official C/C++ source code for Beatrice is publicly accessible (e.g., in the `beatrice-vst` repository) and could theoretically be recompiled rather than relying on extracted binary shims, doing so introduces operational challenges:

- There are no official prebuilt PyPI wheels for Beatrice.
- Although upstream distributed precompiled binaries for Windows and macOS, Linux binaries were entirely absent.
- Incorporating C/C++ native builds (with platform-specific SIMD optimizations) into Forge’s automated build and release pipeline across Windows, macOS, and Linux requires ongoing platform-specific maintenance and build infrastructure.

### ③ Dedicated Standalone Tools Offer Superior UX

Users who want to utilize Beatrice have access to dedicated, first-class alternatives:

- **[aq2r/beatrice-client](https://github.com/aq2r/beatrice-client)**: An official, lightweight GUI specifically designed and optimized for Beatrice.
- **[prj-beatrice/beatrice-vst](https://github.com/prj-beatrice/beatrice-vst)**: A high-performance VST3 plugin running directly in DAWs.

Because these standalone tools provide a tailored, native experience, maintaining a third, compromised Beatrice client inside VCClient Forge provides little value to end users while imposing a heavy engineering tax on the project.

---

## 3. Decision & Architectural Focus

### The Decision

VCClient Forge will **fully prune all Beatrice support** from the backend and frontend codebases.

### Doubling Down on RVC and Modern GPU Acceleration

Rather than dividing attention across divergent architectures, VCClient Forge focuses its resources squarely on the RVC pipeline:

- **ONNX Runtime & GPU Acceleration**: Maximizing performance and efficiency across modern CUDA and DirectML runtimes.
- **Streamlined Pitch Tracking**: Perfecting low-latency, glitch-free vocal tracking with RMVPE and FCPE.
- **Lightweight Distribution**: Delivering a clean, portable distribution with automated workspace lifecycle management.
- **Cohesive Modern UI**: Building a fast, unified, responsive interface without fragmented model-specific branching.

---

## 4. Cleanup Roadmap

1. **Backend Pruning**:
   - Remove `simple_beatrice.py` and `beatricev2_pipeline.py`.
   - Prune Beatrice data models and branch logic from `slot_manager.py`, `slot_manager_data_types.py`, and `pipeline_manager.py`.
2. **Frontend Pruning**:
   - Remove Beatrice-specific components, SVG assets, and conditional branches from the frontend.
3. **Verification**:
   - Validate that all remaining RVC pipeline and regression tests continue to pass with 100% reliability.
