---
title: "DeviceConfig & Catalog Index Architecture"
version: "0.2.0"
okf_version: "0.2"
description: "Architectural specification for transitioning from overloaded integer sentinels to a sequential hardware catalog index (DeviceConfig) across API contracts, UI compatibility, and inference pipelines."
---

# DeviceConfig & Catalog Index Architecture

Forge represents each available compute target as a pairing of an execution provider and an adapter. The catalog replaces upstream's overloaded integers, where values such as `-1` and `1000` mixed fallback behavior and provider selection.

## Catalog and settings

[`device_manager.py`](../backend/vcclient/device/device_manager.py) builds a list of [`DeviceConfig`](../backend/vcclient/device/data_types.py) records. Each record has:

- `id`: its position in the current catalog. CPU is always at index `0`.
- `canonical_id`: a provider-scoped identifier such as `cpu`, `cuda:0`, `dml:0`, or `webgpu:0`.
- `provider`, `device_type`, and `device_index`: the execution provider, hardware class, and provider-local adapter index.
- `name`, `adapter_ram`, and `metadata`: display information and provider-specific details.

The session and settings APIs accept a catalog index as `compute_device_id`. The configuration layer also reads the legacy field name `gpu_device_id_int`. Legacy or out-of-range values that cannot resolve to a catalog entry fall back to CPU when loading configuration. Session writes reject invalid indices. Catalog indices can refer to different devices after discovery changes, so check the selected device after changing hardware or editions.

## Discovery and auto-selection

- `GET /api/devices/compute` reads the catalog. `POST /api/devices/compute/reload` rescans devices while conversion is stopped.
- `POST /api/devices/compute/auto-select` tries ranked candidates against a valid RVC model and returns the first one whose pipeline passes warmup. It checks whether each session exposes the requested provider. It does not persist the recommendation or report per-node placement.
- The probe tries CUDA GPUs first, then the CoreML target that allows all compute units, then OpenVINO, DirectML, or WebGPU GPUs with discrete GPUs ranked ahead of integrated ones. CPU is the last candidate. See [the selector](../backend/vcclient/device/device_selector.py) and [API reference](./api-reference.md).

## Provider routing

`DeviceConfig.create_session()` delegates session options and model preparation to the provider modules. CUDA and DirectML use provider-specific adapter indices. OpenVINO targets a named device, and CoreML passes its compute-unit policy to the execution provider. Linux WebGPU registers the plugin, enumerates Vulkan adapters through the system loader, and binds the adapter index using ONNX Runtime session options. See the [hardware and edition matrix](./npu-cpu-hardware-acceleration-and-universal-distribution.md#54-consolidated-production-edition-matrix).

A session selects one compute target for its inference pipeline. Individual operations may still run on CPU depending on provider support. Separate analysis and synthesis devices are a [planned experiment](./implementation-roadmap.md#4-evaluate-inference-optimizations).
