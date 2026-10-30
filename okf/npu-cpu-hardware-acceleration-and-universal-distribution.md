---
title: "Modern Client Hardware Acceleration: AVX-512, NPUs, Execution Providers, and Universal Distribution"
date: "2026-10-29"
author: "VCClient Forge Team"
category: "Architecture & Engineering Decisions"
tags:
  - hardware
  - cpu
  - avx512
  - npu
  - openvino
  - directml
  - onnxruntime
  - distribution
---

# Modern Client Hardware Acceleration: AVX-512, NPUs, Execution Providers, and Universal Distribution

> **Implementation Status & Roadmap Notice**:
> This document records empirical micro-benchmarking data, hardware architecture evaluations, and the **target design specification for upcoming implementation milestones** (specifically Roadmap Item 9 / Hybrid Phase 5 and the future Two-Tier Universal Distribution transition). The current repository baseline maintains legacy backend device detection and distinct per-hardware packages. The cross-platform probing architecture and multi-EP packaging described herein represent the planned implementation roadmap for future releases.

## Executive Summary

Real-time neural voice conversion has historically been treated across the community as a workload strictly requiring a discrete GPU. This assumption originated in PyTorch-based execution environments where small-batch CPU inference suffers from significant framework overhead.

Through micro-benchmarks on modern x86/ARM hardware and architectural evaluation of client accelerators, VCClient Forge re-evaluates the role of modern CPUs, Neural Processing Units (NPUs), and execution providers:

1. **CPU SIMD Acceleration**: On the Ryzen 9 7950X testbed, standalone ONNX Runtime execution achieves **7.35 ms** for RMVPE pitch estimation (batch size 1, 256 ms analysis window), outperforming an NVIDIA GeForce RTX 4090 (**16.91 ms**). As verified in micro-benchmarks, PCIe DMA transfers are negligible (tens of microseconds); the GPU latency floor is hypothesized to stem from driver kernel launch overhead across sequential micro-operators and low arithmetic intensity at batch size 1.
2. **Integrated NPUs for Continuous Streaming**: Client processors (Intel Core Ultra with Intel AI Boost, AMD Ryzen AI with XDNA/XDNA 2) feature integrated NPUs rated at 10–55 TOPS within low TDP envelopes (typically 2–5 W silicon block power). Streaming audio with fixed chunk sizes aligns well with NPU execution characteristics, offering an architectural avenue to reduce thermal dissipation and decouple inference from 3D graphics rendering.
3. **Execution Provider Landscape**:
   - `OpenVINOExecutionProvider` (Intel): Available as an official standalone plugin package (`onnxruntime-ep-openvino`: ~75.8 MB on Windows, ~52.6 MB on Linux), exposing Level Zero and oneDNN acceleration across Intel CPUs, integrated GPUs, Arc discrete GPUs, and AI Boost NPUs with heterogeneous (`HETERO:`) and automatic (`AUTO:`) device selection.
   - `DmlExecutionProvider` (DirectML): Microsoft's DirectX 12 compute provider across Windows. While DirectML is currently in a servicing phase with active development transitioning toward Windows ML, it remains the standard out-of-the-box accelerator for AMD Radeon GPUs (discrete and integrated).
4. **Target Distribution Architecture: Pragmatic Layered Editions**:
   Rather than maintaining fragmented platform editions, Forge's packaging roadmap establishes a consolidated tiering:
   - **Universal Edition (Planned)**: Lightweight standard release bundling platform baselines (`onnxruntime-directml` + `onnxruntime-ep-openvino` plugin on Windows x64; `onnxruntime` + OpenVINO plugin on Linux x64; `onnxruntime` CPU on Linux ARM64; `onnxruntime` CoreML on macOS ARM64).
   - **CUDA Edition (Planned)**: High-performance release bundling `onnxruntime-gpu` plus the standalone `onnxruntime-ep-openvino` plugin on x64, and native CUDA 13 on ARM64 (targeting the NVIDIA DGX Spark / GB10 Grace Blackwell Superchip), enabling hybrid offloading while respecting PyPI wheel coexistence boundaries.

---

## 1. Dissecting the "GPU-Only" Assumption in Community Voice Conversion

### 1.1 The PyTorch Eager Mode Overhead

Most open-source RVC implementations execute within Python using PyTorch eager mode (`torch.nn.Module`). While effective for batched model training, PyTorch CPU execution incurs structural overhead in low-latency digital signal processing (batch size 1, sequence length ~4096 samples):

- **Dynamic Allocations**: Eager-mode tensor operations allocate and deallocate intermediate memory across layers, inducing memory management overhead.
- **Kernel Dispatch Overhead**: Sequential Python-to-C++ (ATen) call transitions introduce latency that becomes non-trivial when evaluating hundreds of micro-operators sequentially.
- **Multithreading Scheduling**: Default OpenMP thread pools across large core counts (e.g., 32 logical cores) can induce barrier synchronization latency on tiny tensor workloads if thread counts are unconstrained.

Consequently, running RMVPE on CPU under default PyTorch configurations frequently requires **50–100+ ms**, creating the community perception that real-time voice conversion is infeasible without a discrete GPU.

### 1.2 ONNX Runtime CPU Execution Characteristics

In contrast, ONNX Runtime evaluates a pre-optimized computation graph using static memory planning and hand-tuned assembly kernels:

| Dimension | PyTorch CPU (Eager Mode) | ONNX Runtime CPU (MLAS Engine) | Observed Characteristic |
| :--- | :--- | :--- | :--- |
| **Execution Paradigm** | Operator-by-operator eager dispatch | Pre-optimized computation graph | Eliminates Python runtime dispatch overhead |
| **Memory Planning** | Layer-by-layer dynamic allocation | Arena memory allocator (`enable_mem_pattern=True`) | Reuses pre-allocated buffer slots across chunks |
| **Kernel Implementation** | General GEMM & ATen kernels (oneDNN optional) | Dedicated MLAS assembly (AVX2 / AVX-512) | Vectorized register utilization on supported CPUs |
| **Thread Control** | `torch.set_num_threads()` | Tuned `intra_op_num_threads` | Configurable thread pool sizing to balance core usage |
| **Measured RMVPE Latency** | **50–100+ ms** (default PyTorch) | **7.35 ms** (Ryzen 9 7950X, 8 threads) | Demonstrates viability of CPU pitch estimation |

As established in [Hybrid CPU-GPU Pipelining](./hybrid-cpu-gpu-pipeline-architecture.md), physical PCIe bus DMA transfers and synchronization take only tens of microseconds (16–38 μs) and are negligible in the latency budget. The 16.91 ms latency observed for RMVPE on the RTX 4090 is hypothesized to stem from driver kernel launch overhead across fine-grained sequential operators and low arithmetic intensity at batch size 1 (where massive CUDA core arrays remain mostly idle between kernel launches). By contrast, on the Ryzen 9 7950X testbed, the CPU evaluates sequential operations using AVX-512 MLAS assembly without GPU driver dispatch queuing, completing in 7.35 ms.

*(Note: The 7.35 ms measurement reflects a specific desktop testbed featuring an AMD Ryzen 9 7950X with 64 MB L3 cache. It illustrates the performance potential of high-end modern CPUs rather than guaranteeing identical latency across all client processors).*

---

## 2. Integrated NPUs and Hardware Architecture Evolution

### 2.1 The Role of NPUs in Real-Time Audio: Architectural Trade-Offs for Forge

For VCClient Forge's core objective—delivering real-time voice conversion under 100 ms roundtrip latency across diverse client machines—client NPUs (Intel AI Boost, AMD XDNA) introduce a distinct third compute tier alongside CPUs and GPUs with concrete architectural trade-offs.

*(Note on Latency Budget vs. Analysis Window: The 256 ms audio window, or 4096 samples at 16 kHz, represents the analysis context window / receptive field required by pitch estimators and feature extractors to reliably capture vocal intonation. In a real-time streaming pipeline, the stream advances in small hops—such as 32–64 ms—to preserve a sub-100 ms total roundtrip latency budget).*

#### Potential Advantages (Why NPUs Matter for Forge)

1. **Thermal and Acoustic Decoupling**:
   - Discrete GPUs consume 50–300+ W under load, generating heat that triggers high-RPM cooling fans. In live streaming and voice chat, acoustic fan noise is easily picked up by desktop microphones.
   - Client NPU silicon blocks operate within low TDP envelopes (typically 2–5 W for the dedicated accelerator block). Offloading continuous audio inference to an NPU reduces overall thermal dissipation on laptops and quiet desktop systems.
2. **Workload Isolation from 3D Graphics**:
   - Voice changers are frequently used alongside GPU-intensive 3D gaming and OBS streaming. Running neural audio processing on a discrete GPU forces it to compete for graphics compute queues, risking frame drops or audio buffer underruns.
   - Offloading the audio preparation stage to a separate NPU decouples audio inference queues from 3D rendering (though system DRAM bandwidth and SoC power limits remain shared).
3. **Alignment with Streaming Fixed Windows**:
   - NPUs feature spatial multiply-accumulate (MAC) arrays coupled with on-chip SRAM. This architecture is designed for deterministic, streaming tensor operations over regular, bounded buffer sizes.

#### Technical Constraints and Engineering Challenges

1. **Hardware Execution Precision (FP16 vs. INT8)**:
   - Client NPUs execute natively at lower precisions (primarily FP16 and INT8).
   - In modern runtimes such as OpenVINO, the NPU compiler ingests FP32 or FP16 ONNX models directly and compiles them to hardware FP16 precision at load time, without requiring offline dataset calibration.
   - In contrast, INT8 quantization represents an advanced optimization that can yield higher throughput, but requires careful calibration to ensure quantization noise does not degrade perceptual audio quality.
2. **Shape Constraints & Latency Determinism**:
   - While modern runtimes (such as OpenVINO preview releases for NPU 3720 / NPU 4000) introduce bounded dynamic shape support, dynamic memory allocation during execution can introduce compilation latency.
   - Forge adopts fixed-size chunking (Roadmap Item 3) not because NPUs strictly prohibit dynamic shapes, but to guarantee bounded, deterministic inference times without runtime re-compilation spikes.
3. **Memory Bandwidth Considerations for Synthesis**:
   - While 10–55 TOPS provides ample compute for sequential feature extraction (ContentVec) and pitch estimation, running the standard FP32 HiFi-GAN vocoder involves extensive convolutional layer sweeps that demand high memory bandwidth. Discrete GPUs with dedicated VRAM (e.g., RTX 4090 at 1008 GB/s) excel at this workload.
   - On NPUs sharing system LPDDR5X bandwidth (85–130 GB/s), running the full FP32 HiFi-GAN vocoder under 12 ms is constrained by memory sweep speed, highlighting the strategic necessity of lightweight vocoders (DDSP / Streamable vocoders in Roadmap Item 9).
4. **Ecosystem & Toolchain Divergence**:
   - DirectML does not currently provide an official, verified execution path for AMD NPUs in ONNX Runtime; AMD's official tooling centers on `VitisAIExecutionProvider` (part of Ryzen AI Software). Intel NPUs, by contrast, are officially supported via OpenVINO.

#### Forge Architectural Assessment

| Pipeline Stage | Primary Recommended Target | NPU Feasibility & Strategic Role |
| :--- | :--- | :--- |
| **Pitch Estimation: FCPE (`fcpe.onnx`)** | **Client NPU or CPU** | **High (Hypothesis to be verified)**: Feed-forward depthwise separable 1D convolutions (`Lynx-Net`) without recurrent loops map naturally to spatial MAC arrays. |
| **Pitch Estimation: RMVPE (`rmvpe.onnx`)** | **CPU (AVX-512 / AVX2)** | **Medium**: Recurrent BiGRU layer maintains temporal state dependencies, performing best on modern CPU SIMD (7.35 ms on Zen 4 testbed) or dGPU. |
| **Feature Extraction (ContentVec)** | **CPU or GPU** | **Medium**: Suitable for NPU evaluation once verified on target drivers. |
| **FAISS Vector Search** | **CPU (Host RAM)** | **Not Applicable**: Vector index search remains CPU-native. |
| **HiFi-GAN Vocoder (Synthesis)** | **Discrete GPU (CUDA/DirectML)** | **Low with FP32 HiFi-GAN**; **High with future lightweight vocoders** (DDSP / Streamable). |

### 2.1.1 Structural Pitch Estimator Comparison: RMVPE vs. FCPE on NPUs

Comparing RMVPE and FCPE reveals structural differences relevant to NPU compiler compilation:

```mermaid
flowchart LR
    subgraph RMVPE_Arch["RMVPE Architecture (Recurrent Bottleneck)"]
        R_In["Audio STFT"] --> R_CNN["2D CNN U-Net"]
        R_CNN --> R_GRU["BiGRU (Recurrent)"]
        R_GRU --> R_Out["F0 Classifier"]
    end

    subgraph FCPE_Arch["FCPE Architecture (Pure Feed-Forward Convolutions)"]
        F_In["Raw Audio"] --> F_STFT["Conv1D STFT"]
        F_STFT --> F_Lynx["Lynx-Net (1D Depthwise Separable Conv)"]
        F_Lynx --> F_Out["F0 Classifier"]
    end
```

1. **Recurrent Feedback (BiGRU) vs. Pure Convolutions**:
   - **RMVPE** relies on a **Bidirectional Gated Recurrent Unit (BiGRU)** to model temporal sequence evolution across pitch frames. Recurrent cells maintain sequential feedback state dependencies ($h_t = f(h_{t-1}, x_t)$). On spatial systolic MAC arrays optimized for wide feed-forward operations, sequential recurrence cannot be broadly parallelized across spatial tiles, risking pipeline stalls or partial CPU fallback.
   - **FCPE** replaces recurrent structures with **Lynx-Net**, a backbone composed entirely of **Depthwise Separable 1D Convolutions** and pointwise projections. In `fcpe.onnx`, the audio front-end (STFT / Mel filterbank) is also implemented as fixed **1D Convolutions (`Conv1D`)**. Because every operator is feed-forward with zero sequential state feedback, temporal frames can theoretically be evaluated in parallel across NPU tile compute units.
2. **Quantization Behavior**:
   - Quantizing BiGRU hidden states and recurrent gate matrices to INT8 can introduce compounding numerical drift across time steps.
   - Feed-forward depthwise separable convolutions in FCPE follow standard convolutional quantization paths, presenting fewer temporal stability challenges.
3. **Strategic Pitch Estimator Pairing in Forge**:
   - **RMVPE**: Remains the default ecosystem-compatible estimator, exceptionally fast on modern high-end CPUs via AVX-512 MLAS assembly (**7.35 ms** on Ryzen 9 7950X).
   - **FCPE**: Serves as the **primary architectural candidate for client NPU acceleration**, subject to empirical benchmarking on Intel AI Boost and AMD XDNA hardware.

### 2.2 Hardware Platforms and Associated Execution Providers

```mermaid
flowchart TD
    App["VCClient Forge Audio Pipeline"] --> Router{"Hardware Dispatcher"}

    Router -->|"NVIDIA discrete GPU"| CUDA["CUDAExecutionProvider<br/>(Tensor Cores / HiFi-GAN Vocoder)"]
    Router -->|"Intel CPU / iGPU / dGPU (Arc) / NPU"| OV["OpenVINOExecutionProvider<br/>(Level Zero / oneDNN / Arc / AI Boost)"]
    Router -->|"AMD Radeon dGPU & iGPU / DirectX 12"| DML["DmlExecutionProvider<br/>(DirectX 12 / AMD Radeon)"]
    Router -->|"x86_64 AVX2 / AVX-512"| CPU["CPUExecutionProvider<br/>(MLAS Native Assembly / RMVPE)"]
```

#### Intel Client Architecture (`OpenVINOExecutionProvider`)

- **Supported Units**:
  - **CPUs**: Intel Core / Core Ultra (AVX2, AVX-512, AVX-VNNI, AMX via oneDNN).
  - **Integrated GPUs (iGPU)**: Intel Iris Xe, Intel Arc Graphics (Meteor Lake, Lunar Lake, Arrow Lake).
  - **Discrete GPUs (dGPU)**: **Intel Arc A-Series (A770, A750, A580, A380, Arc Pro)** and **Intel Arc B-Series (Battlemage B580, B570)**, as well as Data Center Flex/Max GPUs via native Level Zero runtime.
  - **Neural Processing Units (NPU)**: Intel AI Boost (NPU 3720, NPU 4000).
- **Low-Level Interface**: Bypasses DirectX/Vulkan graphics APIs via native Intel Level Zero driver APIs and oneDNN compute kernels.
- **Plugin Delivery**: Packaged via `onnxruntime-ep-openvino` on PyPI:
  - Windows download size (`win_amd64` wheel): **~75.8 MB**.
  - Linux download size (`manylinux_2_28_x86_64` wheel): **~52.6 MB**.
  - Uncompressed footprint: **~160–190 MB**.
- **Dispatch Features**: Supports `AUTO:` (automatic device selection) and `HETERO:` targeting strings (e.g., `HETERO:NPU,GPU,CPU`) to split graph execution across multiple hardware targets. *(Note: Heterogeneous execution does not guarantee seamless failure-free operation for arbitrary custom operators; graph partitioning behavior must be validated per model).*

#### AMD Client Architecture & Cross-Vendor DirectX (`DmlExecutionProvider`)

- **Primary Role: Out-of-the-Box AMD Radeon GPU Coverage**:
  - DirectML serves as Microsoft's hardware-accelerated DirectX 12 compute API. On Windows, it is the **standard out-of-the-box accelerator for AMD Radeon discrete GPUs (RDNA / RDNA 2 / RDNA 3 / RDNA 4: RX 6000, 7000, 9000 series)** and **Radeon integrated GPUs (RDNA / Vega iGPUs in Ryzen APUs)**.
  - In consumer Windows environments where AMD ROCm is unsupported, and following the upstream removal of `ROCmExecutionProvider` from ONNX Runtime (PR #25181), DirectML provides FP16/FP32 tensor compute across all AMD GPUs with zero external driver toolkits required.
- **API Lifecycle Status**:
  - DirectML is currently in a servicing and maintenance phase within Microsoft's ecosystem, with active developer initiatives shifting toward the broader Windows ML runtime stack. It remains fully functional for DirectX 12 GPU acceleration.
- **AMD NPU Reality**:
  - While Windows 11 includes Microsoft Compute Driver Model (MCDM) drivers for compute-only accelerators, standard DirectML EP routes inference through DXGI graphics adapters. DirectML cannot be assumed to provide an out-of-the-box interface for AMD XDNA NPUs. Official AMD ONNX Runtime NPU acceleration relies on `VitisAIExecutionProvider` within Ryzen AI Software.
- **Universal Fallback**:
  - DirectML also functions across Intel and NVIDIA GPUs on Windows, acting as a reliable GPU fallback whenever dedicated native EPs (CUDA, OpenVINO) are not initialized.

---

## 3. DirectML Device Enumeration Mechanics

When using `onnxruntime-directml`, device selection operates through DXGI (DirectX Graphics Infrastructure) adapter enumeration:

### 3.1 DXGI Adapter Routing

```text
DXGI Adapter Enumeration Order (Typical Windows Laptop):
  Index 0: Discrete GPU (e.g., NVIDIA GeForce / AMD Radeon dGPU) [High Performance]
  Index 1: Integrated GPU (e.g., Intel Arc / AMD Radeon Graphics)
```

- **DXGI Index Binding**: Passing `providers=["DmlExecutionProvider"]` with `provider_options=[{"device_id": target_index}]` binds to the corresponding DXGI display/render adapter. Index 0 defaults to the primary GPU.
- **Compute-Only Adapters**: DXGI enumerates graphics-capable display adapters. Compute-only accelerators exposed exclusively through DXCore (such as MCDM-managed NPUs) are not addressable simply by incrementing DXGI `device_id`.
- **Static Shape Efficiency**: To minimize DirectX 12 descriptor heap churn and pipeline state object (PSO) re-creation, static-shape audio windows (e.g., 256 ms context window) ensure stable execution without driver-level stalls.

---

## 4. Cross-Platform Hardware Capability Probing via ONNX Runtime & NumPy

### 4.1 Eliminating OS-Specific Subprocess Probing

Legacy voice changer implementations and upstream v2.0.78-beta relied heavily on external OS commands to detect compute hardware:
- Spawning PowerShell (`Get-CimInstance Win32_VideoController` or PnP queries) on Windows (~100–300 ms startup latency).
- Spawning `nvidia-smi` across subprocesses (failing in non-NVIDIA or containerized environments).
- Spawning `system_profiler SPDisplaysDataType` on macOS (~300–600 ms blocking delay).

These mechanisms introduce maintenance fragmentation, slow down startup, and fail when running in isolated sandboxes or restricted user accounts.

### 4.2 Target Strategy: In-Band, Framework-Native Detection

Because VCClient Forge relies exclusively on **ONNX Runtime and NumPy** for all inference workflows, future device management will transition away from OS shell subprocesses toward cross-platform, in-band Python APIs provided by ONNX Runtime and NumPy:

1. **CPU Feature Telemetry (NumPy)**:
   - Inspect active vector extensions (AVX-512, AVX2, NEON) via NumPy runtime introspection (e.g., `np.show_runtime()`) for audio preprocessing pipelines (such as SOLA, STFT, and crossfading). Note that ONNX Runtime independently evaluates its own native MLAS assembly vector dispatch at the C++ level.
2. **Provider & Device Enumeration (ONNX Runtime)**:
   - Query registered execution backends via `ort.get_available_providers()` and enumerate physical accelerator devices recognized by active providers via `ort.get_ep_devices()`.
3. **Execution Viability Probing (Subject to Implementation Design)**:
   - Rather than relying solely on static enumeration, the planned device manager will verify that target Execution Providers can genuinely compile kernels and execute without silent fallback to CPU.
   - *Design Status*: Concrete probing details—such as minimal in-memory test graph execution, active provider validation (`session.get_providers()`), and dynamic fallback heuristics (e.g., dGPU -> iGPU/NPU -> CPU)—remain subject to empirical evaluation during the upcoming backend device manager refactoring milestone.

### 4.3 Architectural Advantages

1. **Cross-Platform Consistency**: Discovery logic uses identical Python APIs across Windows, Linux, and macOS.
2. **Subprocess Elimination**: Avoids 100–600 ms delays from spawning OS shells during application startup.
3. **Sandbox & Container Safety**: Functions reliably in sandboxed environments where spawning child processes or querying system management interfaces is restricted or blocked.

---

## 5. Architectural Roadmap: Layered Platform Baselines and Two-Tier Distribution

### 5.1 Historical Fragmented Baseline

The upstream project and initial Forge releases maintained discrete packages per backend:

- `win_x64_cpu`
- `win_x64_dml`
- `win_x64_cuda`
- `linux_x64_cpu`
- `linux_x64_cuda`

This fragmentation created user decision friction, multiplied CI packaging matrices, and prevented hybrid offloading across multiple devices in modern client laptops.

### 5.2 The Determinant Constraint: Python Wheel Namespace and Plugin Coexistence

While initial design discussions considered binary archive footprints, rigorous architectural verification revealed that **archive size is a secondary factor; the true governing architectural determinant of Forge's distribution strategy is Python Wheel Namespace and Plugin Coexistence**.

In the Python ONNX Runtime ecosystem, Execution Providers fall into three distinct architectural categories:

1. **Monolithic In-Tree Runtimes (Mutually Exclusive via pip)**:
   - Packages such as `onnxruntime`, `onnxruntime-gpu`, and `onnxruntime-directml` each distribute full, standalone builds of the C++ engine.
   - Crucially, they install into the **identical Python package namespace** (`site-packages/onnxruntime`) and overwrite the core native bindings (`_pybind_state.pyd` on Windows, `_pybind_state.so` on Linux) and engine DLLs.
   - Consequently, attempting to `pip install` both `onnxruntime-gpu` and `onnxruntime-directml` in a standard Python environment causes binary corruption and symbol mismatch. Coexistence within a single wheel is only possible through custom C++ source builds (`--use_cuda --use_dml`), which imposes an unsustainable CI and maintenance burden that violates Forge's philosophy (*"Less code and less documentation is the ultimate virtue"*).
2. **Out-of-Tree Modular Plugins (Cleanly Composable)**:
   - In contrast, packages like `onnxruntime-ep-openvino` are engineered as official, modular out-of-tree plugins.
   - The plugin installs into its own dedicated namespace and dynamically registers its Level Zero / oneDNN execution provider into the host ONNX Runtime session at runtime.
   - This allows OpenVINO to attach seamlessly to **either** `onnxruntime-directml` (in Universal editions) or `onnxruntime-gpu` (in CUDA editions) using official PyPI wheels without binary collisions or custom builds.
3. **Unpackaged Execution Providers (Excluded from Baseline)**:
   - Execution providers that lack official pre-compiled PyPI wheels—such as `ACLExecutionProvider` (Arm Compute Library)—require local source compilation and manual C++ dependency linking.
   - In strict adherence to Forge's core principle of leveraging existing upstream ecosystems and minimizing self-maintained toolchains, unpackaged EPs are excluded from baseline distributions. Expansion to new hardware backends is strictly gated on the upstream availability of official plugin wheels.

#### Secondary Footprint Validation

Because the modular OpenVINO plugin is compact (~50–80 MB compressed) and DirectML adds only ~20–25 MB:
- The **Universal Edition** (`onnxruntime-directml` + OpenVINO plugin) creates a single lightweight (~100 MB non-CUDA stack) release covering all non-NVIDIA systems.
- The **CUDA Edition** (`onnxruntime-gpu` + OpenVINO plugin) enables Intel hybrid NPU/iGPU offloading alongside NVIDIA dGPU vocoder synthesis with a negligible archive delta (~75 MB), well within GitHub Releases' 2.00 GiB asset ceiling.

Thus, **wheel coexistence boundaries—not arbitrary size targets—naturally dictate Forge's two-tier distribution architecture**.

### 5.3 The Platform Baseline Concept (Target Packaging Architecture)

Forge's distribution roadmap plans to establish non-CUDA components as **permanent platform baselines** across all operating systems:

```mermaid
flowchart TD
    subgraph Baselines["Platform Baselines (Permanent Foundations)"]
        B_x64["x64 Platform Baseline<br/>(OpenVINO Plugin + CPU AVX-512)"]
        B_LinA["Linux ARM64 Baseline<br/>(CPU NEON / SVE)"]
        B_Mac["macOS ARM64 Baseline<br/>(CoreML ANE/Metal + CPU NEON)"]
    end

    B_x64 --> Win_Uni["win / x64 / universal<br/>(+ DirectML)"]
    B_x64 --> Win_CUDA["win / x64 / cuda<br/>(+ CUDA Runtime)"]

    B_x64 --> LinX_Uni["linux / x64 / universal"]
    B_x64 --> LinX_CUDA["linux / x64 / cuda<br/>(+ CUDA Runtime)"]

    B_LinA --> LinA_Uni["linux / arm64 / universal"]
    B_LinA --> LinA_CUDA["linux / arm64 / cuda<br/>(+ DGX Spark / GB10 CUDA)"]

    B_Mac --> Mac_Uni["mac / arm64 / universal"]
```

1. **x64 Platform Baseline (Linux & Windows)**:
   Includes `CPUExecutionProvider` and `OpenVINOExecutionProvider`. Provides hardware-accelerated inference across Intel CPUs, Iris Xe / Arc integrated graphics, Intel Arc discrete GPUs (A-Series / Battlemage B-Series), and Intel AI Boost NPUs via oneDNN and Level Zero.
2. **Windows Graphics Tiering**:
   - **Universal Edition**: Adds `DmlExecutionProvider` to the x64 baseline, providing DirectX 12 hardware acceleration across AMD Radeon discrete and integrated GPUs (RDNA architecture), Intel graphics, and non-CUDA systems.
   - **CUDA Edition**: Layers native NVIDIA CUDA runtime libraries on top of the x64 baseline, delivering maximum Tensor Core performance for GeForce and RTX hardware while retaining OpenVINO for hybrid Intel offloading.
3. **Linux ARM64 Platform Baseline**:
   Includes standard `CPUExecutionProvider` leveraging Arm NEON and SVE/SVE2 vector optimizations natively integrated into ONNX Runtime's MLAS engine. While specialized libraries such as `ACLExecutionProvider` (Arm Compute Library) exist, Microsoft does not distribute official pre-compiled PyPI wheels for ACL. In strict adherence to Forge's core architectural principle—*leveraging existing upstream ecosystems and minimizing custom maintenance overhead*—Forge deliberately avoids requiring custom C++ builds of ONNX Runtime. Additional Execution Providers will only be integrated as out-of-tree plugins with official PyPI package distribution.
   For accelerated GPU workflows, the **`linux / arm64 / cuda`** edition specifically targets modern personal AI supercomputers such as the **NVIDIA DGX Spark (powered by the GB10 Grace Blackwell Superchip)** and Grace-Blackwell/Grace-Hopper workstation platforms. In this architecture, the 20-core Grace Arm CPU and the 1 PFLOPS Blackwell GPU share unified system memory (128GB UMA connected via NVLink-C2C), executing native CUDA 13 kernels with near-zero transfer overhead.
4. **macOS ARM64 Platform Baseline**:
   Bundles `CoreMLExecutionProvider`, which automatically delegates computation between the Apple Neural Engine (ANE) and Metal GPU, backed by NEON/Accelerate CPU execution.

### 5.4 Consolidated Target Edition Matrix

Under the consolidated roadmap, Forge organizes distribution packages into a clean, hierarchical matrix across OS, architecture, and compute tier:

| OS          | Architecture | Edition     | Bundled Execution Providers                               | Intended Hardware                                              |
| :---------- | :----------- | :---------- | :-------------------------------------------------------- | :------------------------------------------------------------- |
| **Windows** | `x64`        | `universal` | `OpenVINO`, `DirectML`, `CPU`                             | Non-NVIDIA systems (AMD Radeon/Ryzen, Intel Arc/Core/Ultra, CPU-only) & NVIDIA DML fallback |
| **Windows** | `x64`        | `cuda`      | **`CUDA`**, `OpenVINO`, `CPU`                             | NVIDIA hardware (GeForce / RTX desktops & hybrid laptops)      |
| **Linux**   | `x64`        | `universal` | `OpenVINO`, `CPU`                                         | Non-NVIDIA systems (AMD / Intel CPU, Intel Arc/iGPU, cloud VMs)|
| **Linux**   | `x64`        | `cuda`      | **`CUDA`**, `OpenVINO`, `CPU`                             | NVIDIA hardware (desktop and server workstations)              |
| **Linux**   | `arm64`      | `universal` | `CPU` (NEON/SVE)                                          | Non-NVIDIA ARM64 systems (RPi 5, RK3588, ARM servers)         |
| **Linux**   | `arm64`      | `cuda`      | **`CUDA`**, `CPU` (NEON/SVE)                              | NVIDIA hardware (DGX Spark / GB10 Grace Blackwell, GPU cloud)  |
| **macOS**   | `arm64`      | `universal` | `CoreML`, `CPU` (NEON)                                    | Apple Silicon (M1/M2/M3/M4: ANE + Metal GPU)                   |

### 5.5 Architectural Advantages of the Planned Bundled Baseline

1. **Hybrid Multi-Device Offloading on Modern Laptops**:
   Modern laptops frequently combine an Intel Core Ultra or AMD Ryzen AI processor with an NVIDIA discrete GPU. By bundling OpenVINO into the CUDA Edition:
   - Pitch estimation (RMVPE / FCPE) or feature extraction (ContentVec) can be dispatched to the integrated Intel NPU or iGPU (via OpenVINO) or CPU (via AVX-512).
   - Synthesis (HiFi-GAN vocoding) runs simultaneously on the discrete NVIDIA GPU (via CUDA).
   - If OpenVINO were stripped from the CUDA edition, NVIDIA laptop users would lose access to their integrated Intel NPU/GPU hardware.
2. **Unified Device Management Codebase**:
   In the target refactoring, backend initialization (`device_manager.py`) will register the full platform provider stack uniformly across all installations. Edition detection will not require fragile conditional imports or guard statements; if CUDA is present, it will be prioritized for vocoder synthesis while maintaining baseline providers.
3. **Negligible Packaging Footprint Impact**:
   Bundling OpenVINO adds only ~50–80 MB compressed to the distribution. The standalone archive growth remains well below the 2.00 GiB release asset threshold.
4. **Elimination of User Confusion**:
   Users with NVIDIA laptops no longer need to decide between a "CUDA edition" and an "OpenVINO edition" to test battery-saving NPU execution. The CUDA edition is a superset that contains all baseline capabilities.
5. **Universal Edition Safety Net for NVIDIA Users**:
   Because `DmlExecutionProvider` is included in the Windows Universal Edition baseline, any NVIDIA user who inadvertently downloads `win_universal` (or selects it intentionally) automatically runs GPU-accelerated inference via DirectX 12. GPU acceleration degrades gracefully rather than dropping precipitously to CPU execution.
