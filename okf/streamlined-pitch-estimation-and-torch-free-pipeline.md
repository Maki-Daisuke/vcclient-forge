---
title: "Pitch Estimation: RMVPE Default and FCPE Alternative"
date: "2026-10-15"
author: "VCClient Forge Team"
category: "Architecture & Engineering Decisions"
tags:
  - pitch-estimation
  - rmvpe
  - fcpe
  - onnx
  - pure-onnx
  - ux
  - simplicity
---

# Pitch Estimation: RMVPE Default and FCPE Alternative

## Executive Summary

VCClient Forge currently supports two fundamental-frequency ($f_0$) estimators: **RMVPE** and **FCPE**, using ONNX Runtime for model inference and NumPy-based surrounding processing.

The primary selection rationale is ecosystem compatibility: RMVPE is the de facto standard in the current RVC ecosystem, and many RVC models/workflows are trained or configured with RMVPE-derived pitch features. FCPE remains available as an alternative. Unsupported legacy estimator settings are normalized to RMVPE; this preserves a usable configuration path but does not guarantee identical output quality for every older model.

---

## 1. Context & Modern Reality

### RMVPE as the Ecosystem Default

Traditional estimators such as `harvest` (WORLD vocoder) and `dio` were used in older RVC workflows. Forge chooses RMVPE as its default because it is widely used in the current RVC ecosystem and is the compatibility-oriented choice for models trained/configured around RMVPE pitch extraction. This is an ecosystem-compatibility decision, not a claim that RMVPE wins every accuracy, robustness, or latency comparison against every alternative.

### Decompilation Finding

During reverse-engineering of v2.0.78-beta, several legacy estimator classes (`harvest`, `dio`, and an older `fcpe` implementation) were reconstructed as empty stubs. Forge did not restore those implementations; it selected RMVPE as the ecosystem-compatible default and supports a separate ONNX FCPE implementation as an alternative.

---

## 2. Core Reasons for Consolidating to RMVPE and FCPE

The decision to support RMVPE as the default and FCPE as an alternative rests on these project-specific reasons:

### 1. RMVPE Compatibility

Many RVC models and workflows use RMVPE-derived pitch features. Making it the default therefore best matches common training and configuration assumptions in the model ecosystem.

### 2. FCPE as an Alternative

FCPE is retained as an alternative supported ONNX estimator. Its relative accuracy, robustness, and latency should be evaluated on representative hardware and input audio before making universal performance claims.

### 3. Radical Code Maintainability ("Less Code is Better")

Keeping the supported estimator set focused limits maintenance surface. Dependency and distribution-size effects should be described separately and backed by the actual package contents.

### 4. Fewer Choices, Less Decision Friction

The user-facing goal is to reduce the number of pitch-estimator choices a user must compare and configure. RMVPE is the compatibility-oriented default, while FCPE remains an explicit alternative for users who want it. This is about reducing decision friction, not claiming other estimators are universally inferior.

---

## 3. ONNX Runtime Implementations

Both supported estimators use ONNX Runtime for model inference, with NumPy-based surrounding processing:

- **RMVPE**: Runs `rmvpe_20231006.onnx`. NumPy handles silence trimming, key-shifting, and mel-scale coarse pitch quantization.
- **FCPE**: Uses the community-exported `fcpe.onnx` model. It accepts 16 kHz audio and returns fundamental frequency in Hz for the RVC pipeline.

---

## 4. Summary of Benefits

| Aspect                   | Legacy Approach                                     | Forge Modern Approach                                         |
| :----------------------- | :-------------------------------------------------- | :------------------------------------------------------------ |
| **Supported Estimators** | Historical estimator options vary by upstream version | **RMVPE** (ecosystem-compatible default) & **FCPE** (supported alternative) |
| **Runtime Dependency** | Mixed (PyWorld C extensions + PyTorch) | **Pure ONNX Runtime + NumPy** (Zero PyTorch) |
| **User Experience** | More estimator choices to compare | RMVPE default with FCPE as one alternative |
| **Code Surface** | High maintenance overhead | Minimal, clean, and easily auditable |
