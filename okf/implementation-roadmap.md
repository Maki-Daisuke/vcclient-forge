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

### Current Priority: Establish the Desktop Baseline First

The immediate priority is the Tauri v2 desktop shell around the **existing Python-served legacy UI**, before the Svelte migration and audio refactors below. Keep `src-tauri/` at the project root. Embed a small startup/error/retry page, supervise the local Python process, wait for its readiness notification, then navigate to its loopback URL. Preserve existing REST, Socket.IO, and audio workflows; validate native and Client Mode permissions separately before claiming upstream UX parity.

Keep connection selection separate from local process ownership so future remote attachment need not start or stop a backend. Remote attachment is not part of the initial implementation. A Rust WebSocket client does not remove WebView microphone secure-context requirements; remote HTTP content must not receive broad native permissions. The initial portable desktop packaging target is Windows, retaining the entire PyInstaller onedir distribution and writable external state. See the [desktop development instructions](../README_dev.md#windows-desktop-host-tauri-v2).

### 1. Establish the Baseline and Confirm Remaining Cleanup

- Record stage timings, queue age, allocations, underruns, and actual microphone-to-output latency with hardware, model, provider, and settings. Include speech/silence quality fixtures and continuous/silent-input runs of at least 30 minutes.
- Reconcile the old Beatrice cleanup checklist with the checkout: no Beatrice references were found in `backend/vcclient` or the backend manifest during this inventory. Check remaining frontend/assets and regression coverage before treating the entire cleanup as complete; do not recreate already removed backend work.
- **Exit**: A reproducible performance/quality baseline and a confirmed list of remaining cleanup, rather than historical plans mistaken for open tasks.
- **Sources**: [Audio Phase 0](./server-first-architecture-and-static-pipeline-roadmap.md#phase-0-measurement-baseline), [Beatrice cleanup](./deprecating-and-removing-beatrice.md#4-cleanup-roadmap).

### 2. Separate Configuration Acceptance, Notification, and Application

- Keep `ConfigurationManager` responsible for configuration storage/persistence. Introduce serialized request coordination, validation, coherent snapshots/change classification, and revision-aware requested/applied state.
- Deliver commands to the owning thread. Apply scalar inference changes at chunk boundaries; coordinate structural changes explicitly and report completion/failure instead of waiting a fixed sleep. Treat recording start/stop as commands.
- Define input/inference/output lifecycle and audio-format contracts, plus ownership of input context (`extra_chunk`), resampler/filter state, model histories, and crossfade state. Initially allow stop, finish in-flight work, reset affected state, rebuild, and restart.
- Preserve current serialized settings and workflows until an explicit migration; do not require RxPY, seamless replacement, or cross-component state transfer for this separation.
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

### 6. Package the Native Desktop Experience with Tauri v2

- Establish the existing-UI desktop baseline first as described above, then reuse the shell when the Svelte UI replaces the legacy bundle. Keep the main UI Python-served and the startup page embedded.
- Retain the self-contained PyInstaller backend and externally writable state. Validate relocation/startup and the complete edition-specific archive, including desktop-shell additions, against the strict under-2-GiB limit.
- **Depends on**: The working legacy UI and self-contained Python backend for the initial shell; the later Svelte transition follows item 4. Neither protocol modernization nor Boost Mode is a prerequisite.
- **Exit**: A usable packaged native desktop workflow with clean process lifecycle and measured distribution size/resource use on target platforms.
- **Sources**: [Tauri plan](./frontend-architecture-and-roadmap.md#planned-desktop-packaging-tauri-v2), [Packaging headroom](./sub-2gb-portable-distribution-and-packaging.md#4-future-headroom-and-roadmap).

### 7. Restore Browser Audio as WebSocket Adapters

- Add `/ws/audio` with a specified little-endian Float32 PCM format and frame/continuity metadata; use the common preparation/inference path. Add AudioWorklet capture/playback and reuse `/ws/events`.
- First restore browser-input/browser-output operation alongside the native pair, without Socket.IO. Keep main/monitor routing contracts intact. Bound transport/client playback buffers and handle rate/channel conversion, overload, disconnects, and history recovery.
- Validate browser secure-context/microphone requirements and Tauri WebView permissions where applicable. Optional Tailscale Serve remains user-managed, not a bundled tunnel dependency.
- **Depends on**: Item 5, shared adapter contracts, and bounded audio processing. Does not depend on Tauri packaging being complete.
- **Exit**: Browser audio works through WebSocket only, with one selected input and bounded latency/recovery behavior.
- **Sources**: [UI Step 3](./frontend-architecture-and-roadmap.md#step-3-incremental-websocket-client-mode), [Independent adapter direction](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application).

### 8. Evaluate Mixed Native/Browser Routing

- Independently select native or WebSocket input and main/monitor destinations. Evaluate native input to browser output and browser input to native output; mode names may survive as presets rather than internal coupling.
- Define and test independent clock drift, network jitter, conversion, output isolation, and failure/reconnect policies before supporting each combination. Do not infer compatibility from modular interfaces alone.
- **Depends on**: Proven native and browser adapter paths from items 3 and 7.
- **Exit**: Explicitly supported combinations pass routing, rate, main/monitor isolation, and discontinuity tests. This is an extension, not a gate for the native release.
- **Source**: [Routing and monitor contract](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application).

### 9. Optimize Inference Incrementally: The Boost Mode Track

This is a separate track after the baseline and stable worker path (items 1 and 3); it need not wait for items 6-8. Preserve normal inference and CPU FAISS fallbacks. Follow the source roadmap's phases in order:

| Order         | Work                                                                             | Gate                                                                                                                                                                                     |
| ------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Audio Phase 2 | Stable runtime shapes, warmup, reusable buffers, GPU IO Binding                  | Measured benefit and equivalent quality; fixed-shape export only if justified; respect DirectML-specific session constraints.                                                            |
| Audio Phase 3 | Integrate RMVPE/FCPE pitch estimation and RVC; keep ContentVec/CPU FAISS outside | Correct alignment/history and reduced F0 host roundtrip with retrieval preserved.                                                                                                        |
| Audio Phase 4 | Add ContentVec for retrieval-free full integration                               | Fixed-shape explicit-state execution improves measured waveform-to-waveform performance/quality.                                                                                         |
| Audio Phase 5 | Evaluate standalone ONNX retrieval against real FAISS indexes                    | Match index metric/semantics as required; measure quality, latency, memory, provider placement, and practical index-size limits. A failed experiment does not invalidate earlier phases. |
| Audio Phase 6 | Conditionally integrate retrieval into the full graph                            | Only adopt combinations passing Phase 5; retain CPU FAISS plus Phase 3 otherwise.                                                                                                        |

CUDA Graph capture is a separate CUDA-only gate at applicable integration stages: verify node placement, fixed shapes/addresses, serialized session calls, state correctness, and actual benefit. Do not treat it as automatic or mandatory. Tune chunk/device/buffer sizes with measurements toward the documented-hardware local round-trip target of 100 ms or less, not a universal latency promise.

**Source**: [Optimization phases and acceptance criteria](./server-first-architecture-and-static-pipeline-roadmap.md#5-optimization-roadmap).

## 3. Conditional Improvements, Not Initial Requirements

- **Reactive control library**: Evaluate RxPY or lightweight signals after control ownership is clear; notifications do not replace application acknowledgements or thread dispatch.
- **Seamless component exchange**: Add only where interruption matters and state compatibility is defined. Safe stop/reset/restart comes first.
- **Alternative buffers and stage splitting**: Evaluate rings, custom synchronization, or separate postprocessing only if the bounded-queue baseline exposes a measured bottleneck. No new C++ toolchain solely for a ring wrapper.
- **Further package reduction**: Measure against the self-contained CUDA archive baseline (1.228 GiB), not against the former environment-dependent package. Tauri is the currently documented desktop-shell direction, not a reason to restart completed packaging work.

Sources: [Control and state plan](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-separate-configuration-acceptance-notification-and-application), [Buffer selection](./server-first-architecture-and-static-pipeline-roadmap.md#35-select-buffer-data-structures-after-defining-stream-contracts), [Packaging roadmap](./sub-2gb-portable-distribution-and-packaging.md#4-future-headroom-and-roadmap).

## 4. Existing Foundations, Not New Roadmap Tasks

- [Runtime/toolchain](./modern-runtime-and-toolchain.md): uv-managed pinned Python, locked hardware editions, root npm tasks, and PyInstaller onedir packaging already exist. Continue testing them as migration gates.
- [Architecture separation](./architectural-evolution.md): Backend separation and legacy CUI removal are established; the frontend build currently copies tracked legacy assets and still needs item 4's Vite migration.
- [Pitch estimators](./streamlined-pitch-estimation-and-torch-free-pipeline.md): RMVPE default and ONNX FCPE alternative already exist. Pure-ONNX inference does not mean removing CPU PyTorch needed for legacy model export.
- [ngrok removal](./deprecating-and-removing-ngrok.md): Bundled ngrok is already removed. Tailscale Serve is optional external setup, not an unfinished Forge integration.
- [Beatrice decision](./deprecating-and-removing-beatrice.md): RVC-only scope is established; backend references are absent in this inventory. Frontend/assets and the stale cleanup checklist still require reconciliation in item 1.

Keep this execution index updated when a milestone lands or an experiment is rejected; update the corresponding detailed document rather than accumulating conflicting completion claims.
