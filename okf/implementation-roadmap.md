---
type: roadmap
title: "Consolidated Implementation Roadmap"
description: "Dependency-ordered implementation priorities across the Forge architecture, frontend, audio, and packaging plans."
tags: [roadmap, priorities, architecture, frontend, audio, packaging]
timestamp: 2026-10-19T00:00:00Z
---

# Consolidated Implementation Roadmap

## 1. Purpose and Scope

This is the execution-order index for future work scattered across OKF. The linked documents retain the detailed rationale and acceptance criteria; this file records recommended sequencing, dependencies, and conditional work. Numbering is a recommended priority order, not a requirement to finish every earlier item before starting any later item. This is a plan, not evidence that the listed features are implemented.

Keep the scope local and single-user: one selected input, one main output, and one optional monitor output. Native audio remains the initial reference. Browser audio may later return as independent input/output adapters rather than a mandatory coupled mode. Multi-user hosting, multiple simultaneous inputs, and arbitrary output counts are not prerequisites.

## 2. Recommended Implementation Order

### Completed Baseline: Native Desktop Host (Wails v3)

The native desktop wrapper has been established using **Wails v3 (Go)** under `desktop/` with Vite, TypeScript, and xterm.js (commit `b260979`). It embeds a lightweight startup/bootstrap page, supervises the local Python backend, handles process tree termination cleanly, and navigates to `http://127.0.0.1:18888` upon readiness. See [Migrating Desktop Host from Tauri to Wails v3](./migrating-desktop-host-from-tauri-to-wails.md).

### Current Priority: Audio Pipeline Refactoring & Modern UI

With desktop packaging and hardware sub-model benchmarking established, active development focuses on:
1. One-way fixed-chunk audio stream refactoring (`convert_chunk_bulk_internal` separation)
2. Svelte 5 + Vite UI migration (Server Mode first)
3. Concurrent Hybrid Pipelining (overlapping CPU preparation with GPU vocoder synthesis)

### 1. Establish the Baseline and Confirm Remaining Cleanup [Sub-Model Benchmarks Completed]

- **Sub-Model Component Benchmarking [Completed]**: Empirical micro-benchmarks for all RVC pipeline components (ContentVec, RMVPE, FAISS, HiFi-GAN Vocoder, and PCIe DMA transfers) were measured on modern hardware (AMD Ryzen 9 7950X, NVIDIA GeForce RTX 4090). Key results are documented in [Hybrid CPU-GPU Pipelining](./hybrid-cpu-gpu-pipeline-architecture.md):
  - PCIe DMA latency: 18.3 μs (16 KB audio chunk), 37.2 μs (147 KB ContentVec embedding).
  - Preparation stage: CPU 23.37 ms vs RTX 4090 25.74 ms (RMVPE is 2.3× faster on CPU: 7.35 ms vs 16.91 ms).
  - Synthesis stage: HiFi-GAN vocoder runs in 11.71 ms on RTX 4090 vs 145.43 ms on CPU (12.4× GPU acceleration).
- **Remaining Baseline Work**:
  - Run continuous long-duration (30+ minutes) streaming and silent-input tests on the active pipeline to evaluate end-to-end microphone-to-output latency, queue age, and clock drift.
  - Reconcile the old Beatrice cleanup checklist: backend references in `backend/vcclient` are removed; verify remaining frontend/assets and regression coverage.
- **Exit**: A documented end-to-end baseline under continuous streaming and confirmation of remaining legacy cleanup.
- **Sources**: [Audio Phase 0](./server-first-architecture-and-static-pipeline-roadmap.md#phase-0-measurement-baseline), [Hybrid CPU-GPU Pipelining](./hybrid-cpu-gpu-pipeline-architecture.md), [Beatrice cleanup](./deprecating-and-removing-beatrice.md#4-cleanup-roadmap).

### 2. Separate Configuration Acceptance, Notification, and Application

- Keep `ConfigurationManager` responsible for configuration storage/persistence. Introduce serialized request coordination, validation, coherent snapshots/change classification, and revision-aware requested/applied state.
- Deliver commands to the owning thread. Apply scalar inference changes at chunk boundaries; coordinate structural changes explicitly and report completion/failure instead of waiting a fixed sleep. Treat recording start/stop as commands.
- Define input/inference/output lifecycle and audio-format contracts, plus ownership of input context (`extra_chunk`), resampler/filter state, model histories, and crossfade state. Initially allow stop, finish in-flight work, reset affected state, rebuild, and restart.
- Preserve current serialized settings and workflows until an explicit migration; do not require RxPY, uninterrupted in-flight replacement, or cross-component state transfer for this separation.
- **Exit**: Settings changes no longer perform device/inference lifecycle work in the storage manager, and ordered application/failure handling has focused tests.
- **Source**: [Configuration and modularization plan](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application).

### 3. Complete the Native One-Way, Fixed-Chunk Audio Path

- Reuse the existing serial inference worker. Move result collection out of the input callback and publish completed audio directly to outputs.
- Introduce preparation/window assembly outside callbacks, fixed profile-sized inference windows, owned pre-allocated slots, and bounded standard-library queues. Preparation of chunk N+1 may overlap inference of chunk N; retain the simpler path if measurements do not justify overlap.
- Keep callbacks short and non-waiting for inference/capacity. Define backlog limits in audio time, silence on underflow, discontinuity generations, safe history resets, and rejection of obsolete results.
- Support the main and optional monitor outputs with independent buffering/read positions and required rate/gain handling; neither output may stall inference or the other. Preserve existing user mode selections when defaulting new configurations to native audio.
- **Depends on**: Baseline and the ownership/reconfiguration contracts from item 2; complete these together in small slices rather than a whole-system rewrite.
- **Exit**: Correct sample counts, bounded age, main/monitor isolation, safe restart/profile changes, and stable long-duration conversion, compared with the baseline.
- **Sources**: [Stream design](./server-first-architecture-and-static-pipeline-roadmap.md#32-target-one-way-stream-processing), [Audio Phase 1](./server-first-architecture-and-static-pipeline-roadmap.md#phase-1-server-first-defaults--fixed-chunk-worker).

### 4. Deliver the Minimal Svelte 5 Native-Audio UI

- Build Svelte 5 + Vite source in `frontend`, retaining `frontend/dist` as the served/package location and updating the root frontend build task.
- Implement native input/main-output/monitor controls, model selection, start/stop, and core settings. Keep local draft interaction immediate; debounce/coalesce and serialize writes, distinguish draft/confirmed values, reject stale acknowledgements, and expose pending/error/retry states.
- Move all 13 community translation dictionaries and required image/license assets before deleting their old home. Preserve i18next semantics and validate coverage, interpolation, fallback, and RTL behavior.
- **Depends on**: Usable native conversion and a defined settings contract. UI scaffolding and asset migration can proceed alongside items 2-3; advanced inference optimization is not a dependency.
- **Exit**: End-to-end native conversion through the new UI without a Socket.IO client; rapid edits, slow/failed responses, and keyboard completion behave correctly.
- **Sources**: [UI Step 1](./frontend-architecture-and-roadmap.md#step-1-minimal-svelte-5-ui-for-server-mode), [Settings redesign](./frontend-architecture-and-roadmap.md#settings-redesign-decouple-interaction-from-rest-synchronization), [Translation preservation](./frontend-architecture-and-roadmap.md#5-preserving-100-of-community-i18n-translation-assets).

### 5. Migrate Notifications, Then Retire the Legacy UI and Socket.IO

- Add `/ws/events` for performance/state notifications, scheduled outside callbacks on the server event loop. Verify settings/model/device changes and startup/shutdown with the new UI.
- Remove legacy Client Mode, Socket.IO/Engine.IO dependencies and ASGI wiring, obsolete emitters, and replaced tests only after native controls and replacement notifications work.
- Remove `web_front` after asset migration, and retire legacy API assumptions as part of the explicit migration. Do not build a second compatibility protocol for the old UI; rollback uses the previous release.
- **Depends on**: Item 4 and verified native lifecycle behavior. `/ws/audio` must not be required for this cutover.
- **Exit**: Native conversion, monitor output, notifications, and shutdown work without Socket.IO. A temporary browser-audio gap is accepted.
- **Source**: [UI Step 2](./frontend-architecture-and-roadmap.md#step-2-websocket-notifications--socketio-removal).

### 6. Package the Native Desktop Experience with Wails v3 (Migrating from Tauri v2) [Completed]

- Establish the desktop baseline around the Python-served UI. Supervise the child process and render the embedded bootstrap page while backend models initialize.
- **Architectural Update & Completion (2026-10-25)**: Completed migration from Tauri v2 to Wails v3 (Go) with Vite, TypeScript, and xterm.js as detailed in [Migrating Desktop Host from Tauri to Wails v3](./migrating-desktop-host-from-tauri-to-wails.md). Removed `src-tauri/` and Rust dependencies, achieving a net code reduction of **2,846 lines**. Daily build turnaround improved by **~5× (~3–5s vs ~15–30s)**, Windows builds are pure Go (`CGO_ENABLED=0`) without MSVC requirements, and process supervision is cleanly handled via Win32 console integration (`AllocConsole`) and `CTRL_C_EVENT` handling.
- Retain the self-contained PyInstaller backend and externally writable state. Validate relocation/startup and the complete edition-specific archive, including desktop-shell additions, against the strict under-2-GiB limit.
- **Depends on**: The working UI and self-contained Python backend for the initial shell; the later Svelte transition follows item 4. Neither protocol modernization nor Boost Mode is a prerequisite.
- **Exit**: A usable packaged native desktop workflow with clean process lifecycle, fast Go compilation, and measured distribution size/resource use on target platforms. (Verified on Windows x64: `desktop/bin/vcclient-forge.exe` 10.18 MB).
- **Sources**: [Desktop Transition](./frontend-architecture-and-roadmap.md#desktop-packaging-transitioning-from-tauri-to-wails), [Wails ADR](./migrating-desktop-host-from-tauri-to-wails.md), [Packaging headroom](./sub-2gb-portable-distribution-and-packaging.md#4-future-headroom-and-roadmap).

### 7. Restore Browser Audio as WebSocket Adapters

- Add `/ws/audio` with a specified little-endian Float32 PCM format and frame/continuity metadata; use the common preparation/inference path. Add AudioWorklet capture/playback and reuse `/ws/events`.
- First restore browser-input/browser-output operation alongside the native pair, without Socket.IO. Keep main/monitor routing contracts intact. Bound transport/client playback buffers and handle rate/channel conversion, overload, disconnects, and history recovery.
- Validate browser secure-context/microphone requirements and Wails WebView2 permissions where applicable. Optional Tailscale Serve remains user-managed, not a bundled tunnel dependency.
- **Depends on**: Item 5, shared adapter contracts, and bounded audio processing. Desktop packaging is already established with Wails v3.
- **Exit**: Browser audio works through WebSocket only, with one selected input and bounded latency/recovery behavior.
- **Sources**: [UI Step 3](./frontend-architecture-and-roadmap.md#step-3-incremental-websocket-client-mode), [Independent adapter direction](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application).

### 8. Evaluate Mixed Native/Browser Routing

- Independently select native or WebSocket input and main/monitor destinations. Evaluate native input to browser output and browser input to native output; mode names may survive as presets rather than internal coupling.
- Define and test independent clock drift, network jitter, conversion, output isolation, and failure/reconnect policies before supporting each combination. Do not infer compatibility from modular interfaces alone.
- **Depends on**: Proven native and browser adapter paths from items 3 and 7.
- **Exit**: Explicitly supported combinations pass routing, rate, main/monitor isolation, and discontinuity tests. This is an extension, not a gate for the native release.
- **Source**: [Routing and monitor contract](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application).

### 9. Optimize Inference: Concurrent Hybrid Pipelining (Superseding Boost Mode)

The original monolithic end-to-end graph fusion track ("Boost Mode") was evaluated against empirical micro-benchmarks on modern hardware (AMD Ryzen 9 7950X, NVIDIA GeForce RTX 4090). Key findings:
- PCIe Gen 4 x16 DMA transfer latency is 18.3 μs for audio chunks (16 KB) and 37.2 μs for ContentVec embeddings (147 KB), showing that host-device data transfers are not the primary bottleneck.
- For small tensors at batch size 1, CPU execution (7.35 ms) is faster than GPU execution (16.91 ms) for RMVPE due to GPU kernel launch and synchronization overheads.
- Monolithic graph fusion across ContentVec, RMVPE, FAISS, and RVC is superseded by a 2-stage concurrent hybrid pipeline where CPU preparation ($T_{\text{prep}} \approx 23.4\text{ ms}$) overlaps with GPU vocoder synthesis ($T_{\text{synth}} \approx 11.7\text{ ms}$) via a bounded double-buffered queue.

Follow the concurrent hybrid optimization milestones in order:

| Milestone | Work | Acceptance Gate |
| --- | --- | --- |
| Hybrid Phase 1 | Stable runtime shapes, session warmup, reusable buffers, GPU IO Binding | Measured memory stability and reduced allocation overhead without breaking DirectML/CUDA fallback. |
| Hybrid Phase 2 | Decouple CPU preparation (ContentVec, RMVPE, FAISS) and GPU vocoder synthesis | Independent worker execution with bounded queues; $T_{\text{effective}} = \max(T_{\text{prep}}, T_{\text{synth}})$ verified under continuous audio streaming. |
| Hybrid Phase 3 | GPU vocoder IO Binding and CUDA stream management | Pre-allocated GPU output buffers; minimal host-to-device roundtrip latency verified. |
| Hybrid Phase 4 | Lightweight vocoder evaluation (DDSP / Streamable architectures) | Synthesis latency reduced below 5 ms while maintaining perceptual audio quality thresholds. |

CUDA Graph capture remains a conditional investigation for the isolated GPU vocoder stage only, gated on fixed shapes, pinned memory addresses, and measurable speedup.

**Source**: [Concurrent Hybrid Pipeline Architecture](./hybrid-cpu-gpu-pipeline-architecture.md), [Server-First Architecture and Pipeline Roadmap](./server-first-architecture-and-static-pipeline-roadmap.md#4-architectural-pivot-from-monolithic-graph-fusion-to-concurrent-hybrid-pipelining).

## 3. Conditional Improvements, Not Initial Requirements

- **Reactive control library**: Evaluate RxPY or lightweight signals after control ownership is clear; notifications do not replace application acknowledgements or thread dispatch.
- **Dynamic in-flight component exchange**: Add only where interruption matters and state compatibility is defined. Safe stop/reset/restart comes first.
- **Alternative buffers and stage splitting**: Evaluate rings, custom synchronization, or separate postprocessing only if the bounded-queue baseline exposes a measured bottleneck. No new C++ toolchain solely for a ring wrapper.
- **Further package reduction**: Measure against the self-contained CUDA archive baseline (1.228 GiB), not against the former environment-dependent package. Wails v3 is the established desktop shell, not a reason to restart completed packaging work.

Sources: [Control and state plan](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application), [Buffer selection](./server-first-architecture-and-static-pipeline-roadmap.md#35-select-buffer-data-structures-after-defining-stream-contracts), [Packaging roadmap](./sub-2gb-portable-distribution-and-packaging.md#4-future-headroom-and-roadmap).

## 4. Existing Foundations, Not New Roadmap Tasks

- [Runtime/toolchain](./modern-runtime-and-toolchain.md): uv-managed pinned Python, locked hardware editions, root npm tasks, and PyInstaller onedir packaging already exist. Continue testing them as migration gates.
- [Architecture separation](./architectural-evolution.md): Backend separation and legacy CUI removal are established; the frontend build currently copies tracked legacy assets and still needs item 4's Vite migration.
- [Pitch estimators](./streamlined-pitch-estimation-and-torch-free-pipeline.md): RMVPE default and ONNX FCPE alternative already exist. Pure-ONNX inference does not mean removing CPU PyTorch needed for legacy model export.
- [ngrok removal](./deprecating-and-removing-ngrok.md): Bundled ngrok is already removed. Tailscale Serve is optional external setup, not an unfinished Forge integration.
- [Beatrice decision](./deprecating-and-removing-beatrice.md): RVC-only scope is established; backend references are absent in this inventory. Frontend/assets and the stale cleanup checklist still require reconciliation in item 1.

Keep this execution index updated when a milestone lands or an experiment is rejected; update the corresponding detailed document rather than accumulating conflicting completion claims.
