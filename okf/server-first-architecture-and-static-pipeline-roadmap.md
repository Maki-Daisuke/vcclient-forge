---
type: architecture
title: "Server-First Audio Architecture & Static-Shape Pipeline Roadmap"
description: "Server-first roadmap for fixed-chunk processing, pitch-estimation and RVC integration, retrieval-free full integration, and measured ONNX retrieval experiments."
tags: [architecture, audio-dsp, inference, latency, optimization, roadmap]
timestamp: 2026-10-18T05:12:00Z
---

# Server-First Audio Architecture & Static-Shape Pipeline Roadmap

## 1. Executive Summary

VCClient Forge prioritizes low-latency real-time voice conversion for local desktop use: Discord, gaming, live streaming, and stage performance.

The deployment assumption is **one user and one active audio client on a local machine or a trusted network managed by that user**. Multi-user hosting, application-level authentication, and per-client inference sessions are outside this roadmap. Server Mode and Client Mode are alternative audio sources, not simultaneous inputs to a shared pipeline.

The roadmap has three priorities:

- Make **Server Mode** (native OS audio devices) the default, retaining Client Mode as a fallback.
- Reorganize the existing inference worker into a one-way, event-driven stream pipeline with fixed-size inference windows, bounded buffer age, and direct delivery of completed audio to output.
- Integrate **pitch estimation + RVC first**, then add ContentVec without retrieval, and evaluate ONNX retrieval before attempting retrieval-enabled full integration.

The local end-to-end latency target is **100 ms or less on documented hardware/model configurations**, subject to measurement and audio-quality checks. CUDA Graph capture is a separate, CUDA-specific optimization gate, not an automatic consequence of integration or fixed shapes.

---

## 2. Historical Context & The "Dynamic Shape Tax"

### 2.1 The Legacy Heritage of Google Colab

Upstream `voice-changer` was initially conceived in an era where deep learning models ran remotely on Google Colab or external GPU compute instances while the user interacted through a web browser:

- **Browser and Network Boundaries**: Web Audio render blocks, transport messages, and inference chunks have different boundaries. Network arrival timing can fluctuate even when message sizes are fixed.
- **Defensive Variable-Length Design**: The backend's `RVCPipeline` was designed defensively to accept any arbitrary chunk size (`audio.shape[0]`).
- **Client-First Defaults**: `voice_changer_input_mode` defaults to `"client"`. Server Mode already uses audio callbacks and a conversion worker; its lifecycle polling is not the audio delivery clock.

### 2.2 Why Fixed-Length Inference Chunks Are the Design Choice

**Decision: accept input flexibly, but execute real-time inference with fixed-length chunks for the selected execution profile.** The current [`rvc_pipeline.py`](../backend/vcclient/voice_changer/voice_change_manager/vc_pipelines/rvc_pipeline.py) derives its conversion window from `audio.shape[0]` plus overlap, search, and context lengths. It therefore lets incoming chunk length determine the downstream inference workload instead of enforcing a stable window at the worker boundary. Passing variable-length windows into inference carries that variability into feature extraction, pitch estimation, and RVC synthesis.

Fixed-length inference is the basis for the following improvements:

1. **Predictable Work and Output Cadence**: Processing the same number of new samples with the same context on each iteration gives the worker a consistent workload and a defined output interval. This makes deadline budgeting and queue sizing straightforward and removes chunk-length changes as a source of timing variation.
2. **Reusable Buffers instead of Repeated Reconstruction**: The current audio-history path concatenates arrays and resizes its retained window for each call. A fixed window lets us replace this with fixed-capacity history and pre-allocated staging/input/output buffers, reducing allocation and copying in the steady-state path.
3. **Stable GPU Execution Shapes**: Fixed feature, pitch, and synthesis tensor dimensions let sessions warm up for the actual recurring workload and reuse matching device buffers. This reduces shape-dependent allocation and setup work and provides a stable foundation for IO Binding and model specialization.
4. **A Foundation for GPU-Resident Integration**: Stable shapes and buffer layouts simplify connecting pitch estimation, ContentVec, retrieval, and RVC without intermediate host transfers. Combined with fixed GPU addresses and the CUDA execution requirements in Section 4.3, they enable capture/replay for supported integrated graphs.

Variable-length support belongs at the input adapters, where buffering absorbs differences in device blocks and WebSocket messages. The inference worker consumes a configured number of new samples plus a fixed amount of overlap/context per iteration. Users can select a different chunk size by switching execution profiles and rebuilding the associated buffers outside the audio callback. The goal is predictable real-time execution, not one immutable chunk size for every device and model.

---

## 3. The Server-First Architectural Shift

Native local execution is the primary path. The change is **not to introduce worker-based inference from scratch**, but to complete the separation already present in VCClient: input callbacks submit audio, the worker processes it, and output callbacks consume completed audio independently.

### 3.1 Current Implementation: Worker Inference, Input-Driven Result Collection

[`local_voice_changer_interface.py`](../backend/vcclient/voice_changer/voice_change_manager/local_voice_changer_interface.py) calls `VoiceChanger.convert_chunk_bulk()` from `audio_input_callback`. In [`voice_changer.py`](../backend/vcclient/voice_changer/voice_change_manager/voice_changer.py), `start_convert_chunk_bulk()` starts a thread running `convert_chunk_bulk_internal()`, which dequeues input and calls `convert_chunk()` for actual inference.

`convert_chunk_bulk()` accumulates/splits input and enqueues complete chunks. It also drains already completed results if any are available; it **does not wait for inference of the newly submitted audio**. A returned result can belong to an earlier input. The native bulk path already assembles configured-size chunks; the pipeline entry itself remains variable-length, so enforcing fixed windows for every input adapter is still part of the target design.

```text
Input callback --> accumulate/split --> input Queue --> inference worker
   |                                                     |
   +--> collect completed results <-- result Queue <-----+
   |
   +--> split for playback --> output Queue --> output callback
```

The existing design has pipeline concurrency, but completed audio must wait for another input callback to collect and forward it. That callback also performs settings/reload checks, allocation, result aggregation, playback splitting, and performance notification. Continuous input normally makes collection recur, but output delivery should follow inference completion rather than depend on the next input arrival.

### 3.2 Target: One-Way Stream Processing

Both input modes use the same processing worker through source-specific adapters. Server Mode and Client Mode are alternatives, and Client Mode is added after the Server-Mode-first UI migration:

```text
Native input callback / WebSocket receiver
           |
           v
   Pre-allocated input slots
   + bounded input Queue
           |
           v
   Preparation worker (chunk N+1)
   Accumulate + fixed window
   Independent pre-inference preparation
           |
      v
   Prepared slots + bounded Queue
           |
      v
   Serial inference worker (chunk N)
   F0 --> ContentVec --> RVC
   SOLA / crossfade --> output slot
      |
      +--> Server Mode: bounded playback buffer --> output callback
      +--> Client Mode: send when ready --> client playback buffer
```

- **Completion-Driven Output**: The worker publishes postprocessed audio directly to the selected output path, including a separate monitor buffer when enabled. Do not route completed results back through `audio_input_callback` or require another input message to retrieve them.
- **Pre-Inference Overlap**: Use a lightweight preparation worker to assemble the next fixed-duration input window and perform independent pre-inference work while the inference worker is running the current chunk. The goal is to have the next prepared slot ready when the inference worker finishes, rather than making it wait for input copying, framing, or other preparation.
- **GIL and ONNX Runtime**: The ONNX Runtime Python binding releases the GIL during `InferenceSession.run()`, allowing Python code in another thread to progress during the native run. This enables CPU-side preparation to overlap; it does not guarantee more CPU/GPU capacity or lower end-to-end latency by itself.
- **Inference Ownership and Order**: Keep pitch estimation, feature extraction, and RVC calls serial in one inference worker initially. Their histories and accelerator resources are stateful/shared; parallelize these calls only after defining state ownership and measuring actual device contention.
- **Post-Inference Path**: Initially run SOLA/crossfade in the inference worker after RVC and publish the result directly to the output slot. This avoids another inter-stage handoff. Measure whether postprocessing delays the following inference before introducing a separate output-processing stage.
- **Event-Driven Scheduling**: Wake stages when a slot is ready and pass slot identifiers/metadata through bounded queues. This requires a preparation worker and a serial inference worker, not a separate thread for every individual operation.
- **Defaulting to `"server"` Mode**: New configurations default to `voice_changer_input_mode = "server"`; preserve an existing user's explicit mode and require device selection before starting audio.
- **Callback Boundary**: Input callbacks copy samples into an available owned, pre-allocated slot and signal readiness before returning; output callbacks fill the supplied `outdata` from completed audio. Move accumulation/splitting, result collection, settings/reload checks, allocation-heavy processing, logging, and notifications out of callbacks.
- **Preparation Boundary**: A preparation worker owns input accumulation and fixed-window assembly, independently of device block size or WebSocket message boundaries. It may prepare chunk N+1 while inference handles chunk N, while preserving order for stateful filters/resamplers.
- **Inference Boundary**: The serial inference worker owns pitch/feature/RVC histories and model calls, then applies initial SOLA/crossfade postprocessing and publishes to output. Keep profile changes at safe processing boundaries.

### 3.3 Output Buffers: Bridge Production and Playback, Not Extra Batch Waiting

In the current `sounddevice.OutputStream(callback=...)` design, PortAudio supplies `outdata` and determines when samples are needed. The application keeps completed samples between worker completion and these callbacks; the driver/PortAudio buffers do not replace that worker-to-callback handoff.

Server Mode therefore uses a bounded playback buffer to supply the requested number of samples at each callback. Make completed audio available to the next output callback without deliberately waiting for additional converted chunks. The callback must fill all of `outdata`, including silence for any missing samples.

Client Mode can send converted audio as soon as it is ready, without an additional server-side batch-accumulation stage. Bound any pending transport data so a slow receiver cannot create an unlimited backlog. Playback buffering belongs at the client AudioWorklet, which consumes samples on the audio clock.

An alternative blocking `OutputStream.write()` design can delegate more buffering to PortAudio, but the call can wait for output capacity; it must not stall the inference worker. The selected callback design keeps production and playback independent.

### 3.4 Bounded Latency and Discontinuity Recovery

- **Input Backlog / Overflow**: Bound pending input by audio duration and oldest-sample age, not only the number of Queue objects. Discard old, unprocessed audio in whole inference-chunk units when the latency budget is exceeded, preserving a recent aligned window instead of trying to play every stale sample.
- **Output Backlog / Overflow**: Bound playback and transport age separately. Discard obsolete output under a defined recovery policy so dropping input does not leave an old output backlog playing first.
- **Output Underflow**: This means playback needs samples that are not ready. Never wait for inference inside the output callback; fill the missing portion with silence and count the event. Input backlog and output underflow are different conditions.
- **Discontinuities**: Carry sample positions/timestamps and a continuity generation through processing. When input is skipped or a stream restarts, reset or rebuild resampler/filter state, F0/feature history, and SOLA/crossfade history as appropriate. Reject obsolete in-flight results from an earlier generation at safe worker/output boundaries.
- **Ownership**: Define who reads/writes each buffer and performs drops/resets. Do not concurrently clear or overwrite data that a worker or callback is consuming. Reporting and recovery coordination stay outside the real-time callbacks.

The purpose is to bound user-visible delay and recover toward current audio, not to increase inference throughput by dropping samples. Persistent overload remains observable through dropped-duration and underflow counters.

[Upstream issue #1682](https://github.com/w-okada/voice-changer/issues/1682) reports a response delay after roughly 30 minutes idle, cleared by restarting v2.2.2's Beatrice-only build. It motivates long-duration tests, but does not establish the cause in this RVC fork. Input-driven collection alone normally adds a wait until the next callback; progressive delay instead calls for checking accumulated queue age, processing deficits, and input/output clock drift. Even a 100 ppm clock difference corresponds to 180 ms over 30 minutes.

### 3.5 Select Buffer Data Structures After Defining Stream Contracts

The one-way stream architecture requires bounded sample handoffs; it does **not** prescribe a ring buffer. Choose the storage for each producer/consumer boundary after specifying its access pattern, timing requirements, overflow policy, and ownership.

| Boundary                                   | Required behavior                                                                                                                                            | Candidates to evaluate                                                                                                                                                           |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Input callback/receiver → inference worker | Append incoming samples, assemble fixed inference windows, bound backlog by duration, discard stale input at window boundaries, preserve continuity metadata | **Phase 1: Python standard-library `queue.Queue` carrying fixed-duration blocks**; later, a sample ring with a staging window if measurements justify it                         |
| Inference worker → native output callback  | Publish completed samples immediately, allow callback-sized reads across inference-block boundaries, bound playback age, fill a shortage with silence        | **Phase 1: Python standard-library `queue.Queue` carrying fixed-duration output blocks**; later, a sample FIFO/ring or callback-side remainder buffer if measurements justify it |
| Inference worker → Client Mode sender      | Publish a completed frame without waiting for more inference output, bound pending send age, discard obsolete output if the receiver falls behind            | **Phase 1: Python standard-library bounded frame queue** with timestamps/generations                                                                                             |

**Initial implementation decision: use Python's standard `queue.Queue` for the stream handoffs.** Queue fixed-duration blocks so `maxsize` corresponds to a known audio-time budget, and configure a finite capacity. A bound expressed only as a count of arbitrarily sized objects would not provide a stable latency limit. Define non-blocking callback behavior and overflow/underflow handling explicitly: callbacks must never wait for the inference worker, stale input is discarded in aligned chunks, and missing output is filled with silence.

Evaluate the initial queues against callback worst-case execution time, lock/wakeup overhead, allocations and copies per block, variable callback frame counts, overflow/underflow semantics, and recovery after discontinuities. Optimize only if measurements show the queue implementation materially contributes to callback deadline misses, allocation pressure, or latency.

Do not add a C++ toolchain solely to use a ring-buffer wrapper such as [`elijahr/ringbuf`](https://github.com/elijahr/ringbuf) or a separately compiled CFFI binding. A Pure-Python lock-free SPSC ring may be prototyped later, but Python-level synchronization and runtime guarantees must be evaluated rather than assumed; compare its correctness and measured callback behavior against the simpler bounded queue before adopting it.

The upstream RVC [real-time GUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/blob/main/realtime_gui.py) instead uses a fixed-block duplex `sd.Stream`, runs inference inside the same callback, and writes directly to `outdata`. Its shifted PyTorch history arrays and noise-reduction `output_buffer` are not a worker-to-playback handoff. That design comparison informs callback constraints, but does not determine the data structure for VCClient's separate-worker stream pipeline.

### 3.6 Latency and Quality Targets

- Measure inference duration, queue age, and actual microphone-to-output latency separately; report p50/p95/p99 and underrun counts with hardware, execution provider, model, and settings.
- Device callback size is not model chunk size. The current 10 ms device callback feeds an accumulator, while `RVCSlotInfo.chunk_sec` defaults to 500 ms.
- The pipeline's 160-sample processing unit at 16 kHz corresponds to 10 ms, but does not establish the minimum usable input window for every model. Validate feature/F0 alignment, receptive-field requirements, and quality before shrinking chunks.
- Target measured local round-trip latency of **100 ms or less** on specified configurations. Include accumulation, algorithmic delay, resampling, scheduling, transfers, inference, and playback buffering in that measurement.

### 3.7 Future Roadmap: Separate Configuration Acceptance, Notification, and Application

Refactor the responsibilities currently mixed in `ConfigurationManager` into an explicit control flow. This is planned work, not implemented behavior:

1. **Acceptance**: Validate configuration requests and serialize updates through a coordinator. Keep `ConfigurationManager` focused on configuration storage and persistence rather than recording commands, device operations, inference setup, or timing-based waits.
2. **Notification**: Publish coherent configuration snapshots and classified changes with revision identifiers. Distinguish requested configuration from successfully applied runtime state; report application success or failure separately. Recording start/stop remain commands rather than persisted settings.
3. **Application**: Route changes to the component's owning thread through explicit command queues. Apply inference settings at chunk boundaries and coordinate device/profile changes as stop, reconfigure, and restart operations. Do not let independent subscribers reconfigure dependent stages in an unspecified order, or use sleeps as completion acknowledgements.

This separation should support interchangeable input (`PortAudioInput` / `WebSocketInput`), inference (`RvcPipeline` / proposed `BoostModePipeline`), and output (`PortAudioOutput` / `WebSocketOutput`) components with explicit audio-format, lifecycle, and state-ownership contracts. A configuration update does not necessarily rebuild the whole pipeline: update compatible scalar values in place and replace or reopen only affected components under coordinator control.

After the native-only UI migration temporarily removes Client Mode, browser audio may return as independently selectable WebSocket input/output adapters rather than as a coupled "Client Mode" switch. Initially reproduce the native/native and browser/browser combinations; later evaluate native input with browser output and browser input with native output. The earlier Server/Client Mode descriptions specify the initial paired configurations, not a permanent coupling between input and output. Mode names could remain as presets. Mixed routing requires explicit format conversion, clock-drift and network-jitter handling, and disconnect/recovery policies before it is supported; it does not introduce multiple simultaneous inputs or multi-user sessions.

Preserve the existing monitor capability: the minimum routing contract is **one selected input, one main output, and one optional monitor output**, not a single output only. Keep the monitor's signal source distinct from its destination adapter. Each enabled output needs independently owned bounded buffering/read positions, rate conversion and gain as required, and its own overflow/underflow and failure policy. Outputs must not compete to consume one queue, and a slow or disconnected output must not block inference or the other output. Account for independent playback clocks and define safe buffer lifetime if audio storage is shared. Arbitrary output counts are not required for the initial modularization.

Start by separating responsibilities while preserving current workflows. Initially allow a brief interruption for structural changes: wait for in-flight work to finish, reset affected state, rebuild, and restart. Keep input context (`extra_chunk`), resampler/filter state, and inference/crossfade histories under explicit ownership; preserve compatible state for scalar updates, but reset invalidated histories and reject obsolete results when a source or execution profile changes. Seamless replacement and cross-component state transfer are later improvements, not prerequisites for modularization.

Evaluate RxPY (`reactivex`) or lightweight signals only after defining these boundaries; library adoption is not decided. Reactive notifications belong to the control path, not the real-time audio-sample handoffs, and do not replace owner-thread dispatch, ordered reconfiguration, or completion/failure reporting.

---

## 4. The Ultimate Vision: "Boost Mode" (End-to-End Graph Fusion)

### 4.1 Stable Execution Profiles, Adjustable Values

An execution profile fixes the pitch estimator, embedder, RVC model, retrieval table, tensor shapes, dtypes, and buffer layout. Profile changes may require rebuilding sessions, reallocating buffers, resetting history, and warming up again outside the audio callback.

Pitch shift and index ratio can remain runtime tensor inputs whose **values** change while shapes and GPU addresses remain stable. They need not trigger recompilation merely because the user adjusts them. Apply settings at chunk boundaries and distinguish scalar changes from profile changes. Avoid assuming that users never change settings while speaking.

### 4.2 The "Boost Mode" Architecture

Boost Mode incrementally removes intermediate CPU/GPU roundtrips. The first integrated graph accepts waveform, externally prepared ContentVec/FAISS features, and explicit history/parameter inputs. It combines pitch estimation, F0 postprocessing/alignment, and RVC synthesis. ContentVec and CPU FAISS remain outside this graph initially.

```text
First integration:
ContentVec --> CPU FAISS --> prepared features --+
                                               +--> [Pitch estimator + F0 processing + RVC] --> audio
Waveform + pitch history + parameters ----------+

Later, without retrieval:
Waveform + histories + parameters --> [ContentVec + Pitch estimator + RVC] --> audio

Conditional final integration:
Waveform + histories + parameters --> [ContentVec + ONNX retrieval + Pitch estimator + RVC] --> audio
```

Each bracket denotes a proposed integrated ONNX graph, not an already implemented engine. Explicit state inputs/outputs preserve pitch/feature history and chunk alignment. State updates and buffer reuse must be synchronized between calls. F0-free models use a separate profile without the pitch branch.

### 4.3 CUDA Graph Capture Is a Separate Gate

For the selected ONNX Runtime/CUDA version, verify:

- All graph nodes are assigned to CUDA EP, with no unsupported control-flow operators or CPU fallback within the captured graph.
- Input/output tensor shapes and GPU addresses stay fixed for each captured profile; pre-allocated `OrtValue` buffers are bound with IO Binding and updated in place.
- Warmup/capture completes before live audio, and calls to the same captured session are serialized.
- Intermediate histories, signal-dependent behavior, and random operators in the exported models preserve correct behavior across replays; static shape does not imply deterministic values.

Multiple sessions connected through GPU buffers can reduce transfers, but do not automatically form one captured CUDA Graph. Host-to-device input transfer and device-to-host output transfer still remain for native audio devices. The objective is **removing intermediate host roundtrips**, not zero transfer or zero launch latency. Keep a normal execution path when capture is unsupported or slower.

---

## 5. Optimization Roadmap

```mermaid
flowchart LR
   A["Phase 0: Baseline"] --> B["Phase 1: Fixed-chunk worker"]
   B --> C["Phase 2: GPU IO Binding"]
   C --> D["Phase 3: Pitch + RVC"]
   D --> E["Phase 4: Full graph without retrieval"]
   E --> F["Phase 5: ONNX retrieval evaluation"]
   F --> G["Phase 6: Conditional full integration"]
```

### Phase 0: Measurement Baseline

- Record stage timings, transfers, queue age, allocation hot spots, underruns, and measured round-trip latency before optimization.
- Track pending input duration, oldest-input age, completed-result waiting time, playback/transport backlog, dropped audio duration, and output underflows separately. Run continuous and silent-input tests for at least 30 minutes to expose long-term delay growth and clock drift.
- Keep representative recordings for speech, silence, consonants, pitch transitions, and chunk boundaries. Record model/provider/settings alongside results.
- **Acceptance**: A reproducible baseline and quality comparison procedure; performance improvements are measured rather than inferred from framework choices.

### Phase 1: Server-First Defaults & Fixed-Chunk Worker

- Default new configurations to Server Mode and preserve existing selections.
- Reorganize `convert_chunk_bulk_internal()` as the serial inference owner rather than adding another model-inference thread. Replace input-callback-driven result collection with direct worker-to-output publication; separate input submission from output delivery.
- Keep native input callbacks limited to copying samples into an available pre-allocated slot and signaling the preparation stage. The preparation worker assembles fixed-length windows and performs independent pre-inference work for chunk N+1 while the inference worker processes chunk N.
- Define per-boundary producer/consumer contracts and start with standard-library `queue.Queue` instances carrying fixed-duration blocks and bounded audio-time capacity. Use an explicitly owned pre-allocated slot pool for callback/preparation handoff; replace repeated audio-history concatenation with fixed-capacity storage and contiguous staging where necessary. Benchmark alternative ring implementations only if the queue baseline shows a measurable bottleneck.
- Keep RMVPE/FCPE, ContentVec, and RVC calls serial in the inference worker initially; their model histories and accelerator resources require ordered ownership. Run SOLA/crossfade after RVC in the same worker and publish completed audio directly to output buffers. Split postprocessing into another stage only if profiling shows it delays the next inference enough to justify the extra handoff.
- Output callbacks only consume available audio and fill shortages with silence.
- Define the shared input/output adapter contract for both modes, implementing native audio first and connecting the WebSocket adapter when Client Mode returns. Keep overlap, search region, and history/context fixed for each profile, separately from device callback sizes.
- Publish native/monitor audio directly to their bounded playback buffers; publish Client Mode output to the sender as soon as ready, with bounded transport backlog and client-side playback buffering.
- Move settings changes and notifications out of audio callbacks. Implement time-based backlog limits, aligned stale-input/output drops, discontinuity generations, history recovery, and safe handling of obsolete in-flight results.
- **Acceptance**: Prepared chunk N+1 can be ready while the inference worker runs chunk N; callbacks never wait for inference or queue capacity; and completed output reaches its destination without another input callback/message. Verify slot ownership/reuse, bounded queue age, sample counts across block/slot boundaries and rate conversion, overload drops, underflow silence, restart/profile changes, and discontinuity recovery. Long-duration tests must keep buffer age within budget without progressive delay growth. Compare stage timings, allocations, and audio quality with the Phase 0 baseline; retain the simpler path if overlap does not improve measured latency or throughput.

### Phase 2: Stable Runtime Shapes & GPU IO Binding

- First evaluate existing dynamic ONNX models with fixed runtime input shapes, warmup, and reusable device buffers. Fixed-shape export or named-dimension overrides are follow-up options, not prerequisites for every improvement.
- Define shapes per stage: waveform `[1, N]`, ContentVec/RVC features `[1, T, D]`, pitch `[1, T]`, and model-specific outputs. Preserve RMVPE/FCPE padding and feature/F0 alignment requirements.
- For CUDA, use pre-allocated `OrtValue` inputs/outputs and IO Binding where supported. `SessionOptions.enable_mem_pattern` is already `True` by default; enabling it alone is not a new optimization.
- For DirectML, set `enable_mem_pattern = False` and `execution_mode = ORT_SEQUENTIAL`, and serialize runs on each session. Keep CPU/DirectML tuning separate from CUDA-specific capture.
- If static export proves beneficial, extend [`export2onnx.py`](../backend/vcclient/voice_changer/slot_manager/onnx_exporter/export2onnx.py) while retaining existing model compatibility.
- **Acceptance**: Measured transfer/timing improvements with stable memory use and equivalent audio quality; normal inference remains available.

### Phase 3: Pitch Estimation + RVC Integration

- Integrate RMVPE or FCPE with RVC, including pitch shift, coarse quantization, history, and time-axis alignment. Accept externally prepared feature tensors as inputs.
- Preserve ContentVec and existing CPU FAISS behavior. This is a useful production path even if later retrieval experiments do not succeed.
- Separate profile rebuilds from scalar setting updates. Test warmup, silence, restart, and transitions without stale histories.
- Evaluate CUDA Graph capture for this integrated graph only after the independent capture gate passes.
- **Acceptance**: Remove the F0 intermediate CPU roundtrip on the supported GPU path while preserving retrieval behavior and pitch/audio quality.

### Phase 4: Retrieval-Free Full Integration

- With `index_ratio = 0`, add ContentVec, feature resizing/cropping, and alignment to the pitch-estimation + RVC graph.
- Validate complete waveform-to-waveform execution with explicit state and fixed runtime shapes; independently assess capture eligibility.
- **Acceptance**: No intermediate feature/F0 host roundtrips in the integrated path, with measured speed and quality compared to the baseline. Phase 3 remains the retrieval-enabled fallback.

### Phase 5: Standalone ONNX Retrieval Evaluation

- Inspect each FAISS index's type, metric, vector count, dimension, and reconstruction support before choosing a replacement.
- For L2 search, evaluate standard ONNX `MatMul`/reductions, `ArgMin`, and `Gather` to select one nearest vector, then apply the existing mixture. Match other metrics explicitly rather than assuming L2.
- This replaces the search algorithm, not the FAISS library wholesale. Exact full-table search can differ from IVF or other approximate indexes; compare retrieval results and audible behavior.
- Keep new-frame-only search and feature-history reuse. Measure latency and peak VRAM across realistic index sizes, including table storage and distance intermediates.
- A small CPU ONNX prototype has matched NumPy exact L2 search; real-index performance, GPU node placement, and capture compatibility remain unverified.
- **Acceptance**: Identify the index sizes/providers where ONNX retrieval improves total pipeline latency within the VRAM and quality budgets. An unsuccessful experiment does not block Phase 3 or Phase 4.

### Phase 6: Conditional Retrieval-Enabled Full Integration

- Integrate ONNX retrieval into the Phase 4 graph only for configurations that pass Phase 5. Verify state handling and all CUDA Graph conditions again for the resulting graph.
- Retain CPU FAISS + the Phase 3 integrated graph when the index is too large, the provider is unsupported, or the ONNX path is slower or changes quality unacceptably.
- Tune device periods, inference chunks, and output buffering together. Small device periods such as 64-128 samples are experiments for supported drivers, not a guarantee of equivalent inference latency.
- **Acceptance**: Demonstrated end-to-end benefit with bounded queue age, no quality regression, and documented fallback. Pursue the measured 100 ms local round-trip target without treating it as a universal hardware guarantee.

---

## 6. Summary

The foundation is a **one-way stream pipeline around the existing inference worker**: lightweight input submission, worker-owned fixed-length processing, and direct output publication with bounded buffer age and discontinuity recovery. Fixed-chunk buffering and IO Binding then support **pitch estimation + RVC, retrieval-free full integration, ONNX retrieval evaluation, and conditional retrieval-enabled integration**. CUDA Graph capture is verified separately at each applicable stage. CPU FAISS remains a supported fallback, so earlier integration work remains useful regardless of the retrieval experiments.

Reference constraints: [CUDA EP / CUDA Graphs](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#using-cuda-graphs-preview), [DirectML session options](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html#configuration-options), and [TensorRT dynamic-shape profiles](https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html#explicit-shape-range-for-dynamic-shape-input).
