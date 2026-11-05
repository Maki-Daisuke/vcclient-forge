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

- Current behavior: when the RVC feature-frame length implied by chunk, extra,
  automatic crossfade, or SOLA settings changes, the existing configuration check rebuilds
  the inference pipeline. This prevents reuse of an inference session configured
  for the previous length; it does not yet provide serialized in-flight updates
  or a complete stop/restart state-reset contract.
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

- **Appearance scaffold implemented (2026-11-06)**: `frontend/` has a standalone
  Svelte 5/Vite preview of the v2.1.4 layout using Bits UI, sample data, disabled
  backend controls, navigable dialogs, themes, and the 13 community translation
  dictionaries. It builds to `frontend/preview-dist`; production `frontend/dist`
  still serves the legacy UI. Native conversion and settings synchronization are
  not connected, so this milestone's exit criteria remain open.

- **Read-only model integration implemented (2026-11-06)**: The new UI loads
  stored slots and the configured current slot via GET. A validated API adapter
  maps responses to display data; per-app catalog state owns loading, failure,
  timeout, retry, and selection by ID. Model cards, management, metadata, and
  portraits now use real backend data; offline/error states never use sample
  models. Vite proxies API/image requests to the backend. Model selection and
  settings/audio writes remain disabled; native integration is still pending.

- **Read-only settings display implemented (2026-11-06)**: The existing GET pair
  supplies configuration and selected-model settings to disabled controls.
  Existing device-list GETs resolve native device names/hosts by configured ID,
  including monitor output. Device failures preserve the settings display and
  show IDs with status; reload reads cached lists without a native rescan.
  Missing fields are shown as unknown; failed loads clear prior values. Backend
  APIs are unchanged. Subsequent editing will preserve the complete current
  configuration and merge UI edits before using the existing PUT endpoint;
  draft state and ordered write coordination are not implemented yet.

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

### 9. Optimize Inference: Evaluate Hybrid Pipelining and Boost Mode

The original monolithic end-to-end graph fusion track ("Boost Mode") was evaluated against empirical micro-benchmarks on modern hardware (AMD Ryzen 9 7950X, NVIDIA GeForce RTX 4090). Key findings:

- PCIe Gen 4 x16 DMA transfer latency is 18.3 μs for audio chunks (16 KB) and 37.2 μs for ContentVec embeddings (147 KB), showing that host-device data transfers are not the primary bottleneck.
- For small tensors at batch size 1, CPU execution (7.35 ms) is faster than GPU execution (16.91 ms) for RMVPE due to GPU kernel launch and synchronization overheads.
- A 2-stage concurrent hybrid pipeline is a candidate architecture: CPU preparation ($T_{\text{prep}} \approx 23.4\text{ ms}$ in the component benchmark) could overlap GPU vocoder synthesis ($T_{\text{synth}} \approx 11.7\text{ ms}$) via a bounded double-buffered queue. These component measurements do not compare complete hybrid and Boost implementations.

Revisit Boost Mode as a conditional experiment rather than ruling it out. A
single ONNX graph could combine ContentVec, pitch estimation, feature retrieval,
and synthesis. Prototype ONNX top-1 retrieval first, then integrate components
incrementally. A flat matrix search scans all vectors and is not equivalent to
the current IVF search; evaluate IVF-equivalent retrieval separately, including
model-specific index changes and state handling.

Compare complete implementations on integrated CPU/NPU/GPU systems and systems
with a powerful discrete or integrated GPU. Resource overlap may benefit the
hybrid design, while a single-device session may reduce host dispatch and
intermediate transfers; shared bandwidth, power limits, provider partitioning,
and CPU fallback can change the outcome. Under the same audio, model, index,
chunk settings, and quality criteria, measure sustained throughput, end-to-end
audio latency and tail latency, queue/buffer delay, CPU/GPU/NPU utilization,
memory, startup/rebuild time, and power where practical. Distinguish throughput
from per-chunk latency: overlapping successive chunks does not eliminate the
two sequential stages of an individual chunk. Record actual execution-provider
placement and compare output quality and retrieval results. No winner is assumed.

Follow the concurrent hybrid optimization milestones in order:

| Milestone      | Work                                                                          | Acceptance Gate                                                                                                                                               |
| -------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hybrid Phase 1 | Stable runtime shapes, session warmup, reusable buffers, GPU IO Binding       | Measured memory stability and reduced allocation overhead without breaking DirectML/CUDA fallback. Pipeline-level session warmup implemented in `RVCPipeline` to eliminate initial JIT/AOT compilation spikes across OpenVINO, DirectML, and CUDA. |
| Hybrid Phase 2 | Decouple CPU preparation (ContentVec, RMVPE, FAISS) and GPU vocoder synthesis | Independent worker execution with bounded queues; $T_{\text{effective}} = \max(T_{\text{prep}}, T_{\text{synth}})$ verified under continuous audio streaming. |
| Hybrid Phase 3 | GPU vocoder IO Binding and CUDA stream management                             | Pre-allocated GPU output buffers; minimal host-to-device roundtrip latency verified.                                                                          |
| Hybrid Phase 4 | Lightweight vocoder evaluation (DDSP / Streamable architectures)              | Synthesis latency reduced below 5 ms while maintaining perceptual audio quality thresholds.                                                                   |
| Hybrid Phase 5 | Client NPU streaming offload (Intel AI Boost / AMD XDNA)                      | Evaluation of fixed-chunk inference offload to client NPUs.                                                                                                   |

CUDA Graph capture is a conditional investigation for the isolated GPU vocoder or a suitable Boost graph, gated on provider support, fixed shapes, stable memory addresses, and measurable benefit.

**Source**: [Concurrent Hybrid Pipeline Architecture](./hybrid-cpu-gpu-pipeline-architecture.md), [Server-First Architecture and Pipeline Roadmap](./server-first-architecture-and-static-pipeline-roadmap.md#4-architectural-pivot-from-monolithic-graph-fusion-to-concurrent-hybrid-pipelining), [Hardware Acceleration & Universal Distribution](./npu-cpu-hardware-acceleration-and-universal-distribution.md).

## 3. Conditional Improvements, Not Initial Requirements

- **FAISS SQ8 retrieval experiment (planned)**: Evaluate converting compatible
  `IndexIVFFlat` indexes to `IndexIVFScalarQuantizer` (SQ8) in memory when a
  model is loaded. The hypothesis is that smaller search codes may improve CPU
  cache behavior and SIMD throughput; no speedup or specific instruction use
  has been established. Preserve the source file and the original float32
  `big_npy` so selected IDs retrieve original reconstructed vectors. Quantization
  can still change the selected IDs. Keep the original cluster centroids,
  `nlist`, `nprobe`, metric, and IDs for a controlled comparison; verify that
  each supported source index permits this and handle invalid search results.
  Compare search latency and tail latency using representative query batch sizes,
  index sizes, CPU architectures, FAISS builds, and thread settings. Measure
  cache/SIMD behavior where tools permit, ID agreement and converted-audio
  quality, startup/rebuild time, steady-state and peak memory, and the break-even
  point for repeated searches. Retain IVFFlat if results do not justify conversion.
- **Reactive control library**: Evaluate RxPY or lightweight signals after control ownership is clear; notifications do not replace application acknowledgements or thread dispatch.
- **Dynamic in-flight component exchange**: Add only where interruption matters and state compatibility is defined. Safe stop/reset/restart comes first.
- **Alternative buffers and stage splitting**: Evaluate rings, custom synchronization, or separate postprocessing only if the bounded-queue baseline exposes a measured bottleneck. No new C++ toolchain solely for a ring wrapper.
- **Further package reduction**: Measure against the self-contained CUDA archive baseline (1.228 GiB), not against the former environment-dependent package. Wails v3 is the established desktop shell, not a reason to restart completed packaging work.

Sources: [Control and state plan](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application), [Buffer selection](./server-first-architecture-and-static-pipeline-roadmap.md#35-select-buffer-data-structures-after-defining-stream-contracts), [Packaging roadmap](./sub-2gb-portable-distribution-and-packaging.md#4-future-headroom-and-roadmap), [Hardware Acceleration and Universal Distribution](./npu-cpu-hardware-acceleration-and-universal-distribution.md).

## 4. Existing Foundations, Not New Roadmap Tasks

- [Runtime/toolchain](./modern-runtime-and-toolchain.md): uv-managed pinned Python, locked hardware editions (`standard` and `cuda`), root npm tasks, and PyInstaller onedir packaging already exist. Continue testing them as migration gates.
- [Architecture separation](./architectural-evolution.md): Backend separation and legacy CUI removal are established; the production frontend build still copies tracked legacy assets. Item 4's Svelte/Vite appearance preview exists separately; native integration and the production build cutover remain planned.
- [Pitch estimators](./streamlined-pitch-estimation-and-torch-free-pipeline.md): RMVPE default and ONNX FCPE alternative already exist. Pure-ONNX inference does not mean removing CPU PyTorch needed for legacy model export.
- [Hardware acceleration & universal distribution](./npu-cpu-hardware-acceleration-and-universal-distribution.md): AVX-512 CPU acceleration benchmarks, NPU execution characteristics, and the layered platform baseline strategy (OpenVINO + DirectML baseline on Windows, CoreML on macOS, OpenVINO on Linux, bundled across `standard` and `cuda` editions) are fully implemented and verified on physical hardware (Windows CUDA, Intel Arc GPU via OpenVINO, AMD via DirectML, and macOS Apple Silicon M2 via CoreML).
- [ngrok removal](./deprecating-and-removing-ngrok.md): Bundled ngrok is already removed. Tailscale Serve is optional external setup, not an unfinished Forge integration.
- [Beatrice decision](./deprecating-and-removing-beatrice.md): RVC-only scope is established; backend references are absent in this inventory. Frontend/assets and the stale cleanup checklist still require reconciliation in item 1.

Keep this execution index updated when a milestone lands or an experiment is rejected; update the corresponding detailed document rather than accumulating conflicting completion claims.
