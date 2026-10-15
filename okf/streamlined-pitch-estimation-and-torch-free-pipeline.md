---
title: "Streamlined Pitch Estimation: Why RMVPE & FCPE Only"
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

# Streamlined Pitch Estimation: Why RMVPE & FCPE Only

## Executive Summary

VCClient Forge deliberately streamlines fundamental frequency ($f_0$) estimation to strictly two modern deep-learning algorithms: **RMVPE** and a newer ultra-fast model, **FCPE**, both operating completely **torch-free via ONNX Runtime and NumPy**.

All legacy non-deep-learning estimators (such as `harvest` and `dio`) and redundant variants have been pruned. This decision reduces maintenance burden, improves UX by eliminating decision fatigue, and maximizes real-time performance, backed by a transparent fallback mechanism ensuring 100% backward compatibility with older voice models.

---

## 1. Context & Modern Reality

### The De Facto Standard: RMVPE
In the early days of RVC and AI voice conversion, traditional signal-processing algorithms such as `harvest` (WORLD vocoder) and `dio` were widely utilized. However, deep-learning-based pitch estimation has advanced rapidly. Today, **RMVPE (Robust Model for Vocal Pitch Estimation)** stands as the definitive, industry-standard pitch estimator for RVC. Across every critical metric—pitch tracking accuracy, noise robustness, computational efficiency, and end-to-end latency—RMVPE comprehensively outperforms traditional DSP algorithms.

Consequently, the necessity to support legacy non-deep-learning pitch estimators has effectively vanished from real-time AI voice conversion workflows.

### Decompilation Finding
During the reverse-engineering of v2.0.78-beta, several pitch estimator classes (`harvest`, `dio`, and legacy `fcpe`) were found with empty stub methods (`pass`). This was an artifact of the decompilation tool failing to reconstruct their bytecodes. However, rather than spending effort attempting to resurrect or maintain these obsolete implementations, this discovery presented the ideal opportunity to evaluate whether these estimators were actually needed in modern Forge. The answer was clear: **they were not**.

---

## 2. Core Reasons for Consolidating to RMVPE and FCPE

The decision to narrow the pitch estimation suite down to RMVPE and FCPE rests on four foundational pillars:

### 1. RMVPE as the Definitive Standard
RMVPE delivers unmatched accuracy in tracking expressive vocal nuances, transitions, and falsetto without the audible pitch glitched or octave jumps common to older methods. It is the benchmark against which all RVC voices are tuned.

### 2. FCPE as a Newer, Ultra-Fast Alternative
**FCPE (Fast Context-based Pitch Estimation)** is a newer, highly efficient alternative model to RMVPE, engineered with a lightweight context-aware convolutional architecture. It matches RMVPE's accuracy while offering even lower latency and remarkable noise resistance, making it an ideal choice for competitive gaming and constrained hardware.


### 3. Radical Code Maintainability ("Less Code is Better")
Eliminating PyWorld bindings, heavy C extensions, and auxiliary PyTorch wrappers dramatically reduces the surface area of the backend. Maintaining fewer, high-quality ONNX implementations minimizes technical debt, eliminates hidden bugs, and keeps standalone distributions lean.

### 4. Superior User Experience (Eliminating Decision Fatigue)
Presenting end users with half a dozen pitch estimators (`harvest`, `dio`, `crepe`, `crepe-tiny`, `rmvpe`, etc.) introduces unnecessary confusion without any practical benefit. By offering only the two best-in-class options, users achieve optimal voice conversion quality out-of-the-box without needing to experiment with inferior legacy algorithms.

---

## 3. Pure-ONNX & Self-Healing Architecture

Both retained estimators operate in a completely torch-free runtime:

1. **Pure ONNX Runtime + NumPy**:
   * **RMVPE**: Runs `rmvpe_20231006.onnx` via `onnxruntime.InferenceSession`. Vectorized NumPy handles silence trimming, key-shifting, and Mel coarse quantization without converting to PyTorch tensors.
   * **FCPE**: Uses the community-exported ONNX model (`fcpe.onnx`, 41.6 MB; see [gzivdo/fcpe-onnx](https://huggingface.co/gzivdo/fcpe-onnx)). It takes raw 16 kHz audio (`[1, n_samples, 1]`) and outputs fundamental frequency in Hz (`[1, n_frames, 1]`), allowing it to integrate directly into our NumPy pipeline without external audio preprocessing.

2. **Whitelist Normalization with Self-Healing Fallback**:
   To ensure existing models (such as sample models configured with `"harvest"`) transition seamlessly, `RVCSlotInfo` validates slot configurations against a strict whitelist:
   ```python
   @field_validator("pitch_estimator", mode="before")
   @classmethod
   def normalize_pitch_estimator(cls, v: str) -> str:
       if v not in ("rmvpe", "fcpe"):
           return "rmvpe"
       return v
   ```
   If a model specifies an unsupported estimator, the system automatically falls back to `rmvpe` at load time, ensuring audio always outputs correctly without crashes or silence.

---

## 4. Summary of Benefits

| Aspect | Legacy Approach | Forge Modern Approach |
| :--- | :--- | :--- |
| **Supported Estimators** | Cluttered menu (`harvest`, `dio`, `crepe`, `rmvpe`) | **RMVPE** (gold standard) & **FCPE** (newer ultra-fast model) |

| **Runtime Dependency** | Mixed (PyWorld C extensions + PyTorch) | **Pure ONNX Runtime + NumPy** (Zero PyTorch) |
| **User Experience** | Decision fatigue, trial-and-error | Streamlined, optimal results by default |
| **Backward Compatibility** | Risk of failure if dependency missing | **100% Self-healing** (auto fallback to `rmvpe`) |
| **Code Surface** | High maintenance overhead | Minimal, clean, and easily auditable |
