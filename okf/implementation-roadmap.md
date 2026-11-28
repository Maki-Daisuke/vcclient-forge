---
type: roadmap
title: "Consolidated Implementation Roadmap"
description: "Remaining audio and inference work, ordered by dependency, with conditional experiments."
tags: [roadmap, priorities, architecture, frontend, audio, packaging]
timestamp: 2026-10-19T00:00:00Z
---

# Consolidated Implementation Roadmap

Remaining work for Forge's local, single-user audio pipeline. Priorities are ordered by dependency. The [knowledge map](./index.md) and [API reference](./api-reference.md) describe the existing architecture.

## 1. Measure sustained audio behavior

- Run at least 30 minutes of continuous and silent-input conversion. Record microphone-to-output latency, queue age, dropped audio, underflows, and clock drift.
- Validate browser audio under sustained load and across disconnect/reconnect, including remote connections where practical. Verify live control edits and error recovery against the real backend.
- Use the results as a baseline for stream changes. See [Measurement baseline](./server-first-architecture-and-static-pipeline-roadmap.md#phase-0-measurement-baseline).

## 2. Finish the native fixed-chunk audio path

- Move window preparation and result collection out of the input callback. Reuse the serial inference worker and deliver completed audio to outputs without waiting for another input callback.
- Use owned, reusable buffers and bounded queues. Define backlog limits in audio time, silence on underflow, and how to discard stale results and reset history after a discontinuity.
- Verify sample counts, correct rate and gain handling, independent main/monitor output buffering, safe restart, and stable queue age in long runs.
- Evaluate defaulting new configurations to native audio while preserving existing mode selections. See [Fixed-chunk worker](./server-first-architecture-and-static-pipeline-roadmap.md#phase-1-server-first-defaults--fixed-chunk-worker).

## 3. Evaluate mixed native/browser routing

After validating both audio paths, evaluate independent native or browser inputs and outputs. Define which combinations to support and verify clock drift, network jitter, sample-rate conversion, output isolation, and disconnect recovery. See [Audio adapter and routing contracts](./server-first-architecture-and-static-pipeline-roadmap.md#37-future-roadmap-audio-adapter-contracts-output-routing-and-control-separation).

## 4. Evaluate inference optimizations

- Establish stable runtime shapes and measure reusable buffers and GPU I/O binding before splitting work across devices.
- Prototype overlapping preparation for one chunk with vocoder synthesis for the preceding chunk. Measure throughput and end-to-end latency separately, and retain serial execution if overlap adds delay without a sustained benefit.
- Evaluate single-graph inference separately. Prototype ONNX top-1 retrieval before integrating components, and compare retrieval behavior against FAISS, including model-specific index changes.
- Compare the candidates under the same audio, model, index, and chunk settings on integrated and discrete hardware. Record output quality, latency including tail latency, queue delay, throughput, provider placement, memory, startup time, and power where practical.
- Investigate CUDA Graph capture, NPU offload, and lightweight vocoders where measurements justify them. See [Hybrid CPU-GPU pipelining](./hybrid-cpu-gpu-pipeline-architecture.md) and [Stable runtime shapes](./server-first-architecture-and-static-pipeline-roadmap.md#phase-2-stable-runtime-shapes--gpu-io-binding).

## Conditional work

- **FAISS SQ8** — Compare in-memory SQ8 with IVFFlat on representative indexes and query sizes. Preserve the source file and original float32 vectors. Compare search latency, memory, startup cost, ID agreement, and audio quality with the same search settings where supported.
- **Runtime component exchange** — Evaluate in-flight swaps where interruption matters, after defining state compatibility and restart behavior.
- **Buffer and control abstractions** — Consider rings, separate postprocessing, or reactive control only when measurements or concrete coordination needs justify them.
- **Package size** — Evaluate reductions against a measured self-contained archive for the same platform and edition. See [Packaging headroom](./sub-2gb-portable-distribution-and-packaging.md#4-future-headroom-and-roadmap).
