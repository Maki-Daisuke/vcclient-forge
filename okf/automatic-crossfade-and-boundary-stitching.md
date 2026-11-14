# Automatic Crossfade and Buffer-Boundary Stitching

## 1. Context and Problem Statement

In the legacy `w-okada/voice-changer` architecture, the crossfade duration (`crossfade_sec`) was exposed as a user-configurable setting in `VoiceChangerConfiguration` (defaulting to `0.05` s = 50 ms).

Exposing this parameter as an unconstrained user setting created three operational issues:

1. **Acoustic Degradation on Sub-50ms Crossfades**:
   When the crossfade duration was configured below ~40–50 ms (for instance, in UI prototypes allowing 1 ms step adjustments down to 0 ms, or via manual configuration edits in an attempt to lower latency), the audio output suffered from audible phase-cancellation and window-modulation artifacts, manifesting as a thin, raspy, or hollow vocal timbre.
   In practice, reducing `crossfade_sec` does not meaningfully reduce end-to-end latency:
   - Crossfade overlap is drawn from *past* input samples already held in the ring buffer, so it adds no input buffering (lookahead) wait time.
   - Although the overlap region is included in each chunk's inference window (`RVCPipeline._generate_inputs`), on parallel hardware (GPUs, NPUs, and SIMD CPUs) the sequence length difference of $\le 50\text{ ms}$ ($\le 800$ samples at 16 kHz) has a negligible effect on per-chunk inference execution time.

2. **Buffer Overrun and Shape Mismatches on Short Output Chunks**:
   In `VoiceChanger._convert_chunk`, when `direct_from_server=True` (Web client Socket.IO / REST streaming), `output_size` is derived from the incoming `waveform.shape[0]` rather than the slot's nominal `vc_chunk_sec`. Previously, `real_crossfade_sec` was clamped only against `vc_chunk_sec` (`min(vc_chunk_sec, conf.crossfade_sec)`), and integer truncation vs. rounding could also allow `crossfade_frame` to exceed `output_size`. When `crossfade_size > output_audio_size`, array slicing in `CrossfadeProcessor.apply` attempted to broadcast buffers of incompatible shapes, raising unhandled exceptions (`ValueError: operands could not be broadcast together with shapes`).

3. **UI Consolidation**:
   In the Svelte 5 UI (`frontend/`), the user control for `crossfade_sec` is omitted from the control panels, and the legacy Classic (`v2.0.78`) and Modern (`v2.1.4`) `web_front/` bundles have been removed.

---

## 2. Acoustic Mechanics of SOLA Crossfading

VCClient Forge stitches consecutive audio chunks in `CrossfadeProcessor` (`backend/vcclient/voice_changer/voice_change_manager/crossfade_processor.py`) using the **Synchronized OverLap-Add (SOLA)** algorithm.

### 2.1 The Role of SOLA and Implementation Mechanics

When converting real-time streaming audio chunk-by-chunk, each chunk is synthesized independently by the acoustic pipeline (pitch estimation, ContentVec feature extraction, and RVC neural vocoder). Consequently, the boundary between chunk $k-1$ and chunk $k$ exhibits discontinuities in waveform phase.

Rather than performing a crossfade at a fixed offset—which causes destructive interference when harmonics are out of phase—`CrossfadeProcessor.apply` searches for an alignment offset $\Delta \in [0, S_{\text{sola}}]$ (where $S_{\text{sola}}$ corresponds to `sola_search_frame_sec = 0.012` s = 12 ms).

At the end of chunk $k-1$, the processor extracts the trailing $L$ samples (`crossfade_size`) immediately following the emitted chunk and pre-multiplies them by a raised-cosine fade-out window to form `prev_rest_buffer`:

$$\tilde{y}_{k-1}(n) = y_{k-1}(n) \cdot \cos^2\left(\frac{n}{L} \frac{\pi}{2}\right), \quad 0 \le n < L$$

When chunk $k$ arrives (`audio_with_overlap_buffer`, denoted $x_k$), `CrossfadeProcessor.apply` evaluates the cross-correlation score across the search window using 1D valid convolution (`np.convolve`):

$$R(\Delta) = \frac{\sum_{n=0}^{L-1} x_k(n + \Delta) \cdot \tilde{y}_{k-1}(n)}{\sqrt{\sum_{n=0}^{L-1} x_k^2(n + \Delta) + \epsilon}}, \quad 0 \le \Delta \le S_{\text{sola}}$$

where $\epsilon = 0.001$ prevents division by zero during silence. Because the energy of $\tilde{y}_{k-1}$ is constant with respect to the candidate shift $\Delta$, omitting $\sum \tilde{y}_{k-1}^2(n)$ from the denominator preserves $\Delta_{\text{opt}} = \arg\max_{\Delta} R(\Delta)$ without redundant computation.

Once $\Delta_{\text{opt}}$ is selected, the current chunk is sliced from $\Delta_{\text{opt}}$ and blended with `prev_rest_buffer` over the first $L$ samples using the complementary fade-in window (`np_cur_strength`):

$$y_{\text{out}}(n) = x_k(n + \Delta_{\text{opt}}) \cdot \cos^2\left(\left(1 - \frac{n}{L}\right)\frac{\pi}{2}\right) + \tilde{y}_{k-1}(n), \quad 0 \le n < L$$

Since $\cos^2(\theta) + \cos^2\left(\frac{\pi}{2} - \theta\right) = 1$, in-phase signals maintain constant amplitude across the transition.

### 2.2 Why ~50 ms is the Acoustic Sweet Spot (Neither Shorter Nor Longer)

Human voice fundamental frequencies ($F_0$) typically span:
- Male voices: 80 Hz to 160 Hz (period $T_0 \approx 6.25\text{ ms} \text{ to } 12.5\text{ ms}$)
- Female voices: 150 Hz to 300 Hz (period $T_0 \approx 3.3\text{ ms} \text{ to } 6.7\text{ ms}$)

Combined with the 12 ms SOLA search range ($S_{\text{sola}}$, covering one full fundamental period down to $\approx 83.3\text{ Hz}$), the crossfade window length $L$ is governed by two competing physical constraints:

1. **Why Sub-50ms Crossfading Degrades Audio**:
   - **Feature Frame Granularity**: ContentVec / HuBERT operates with a 320-sample hop size at 16 kHz (**20 ms per feature frame**). A crossfade window below 20 ms provides less than one full feature frame of overlap at the neural vocoder input boundary.
   - **Pitch Period Coverage & Window Modulation**: At 5–20 ms, an 80–100 Hz male fundamental contains fewer than 2 full cycles within the correlation template, making phase correlation sensitive to local formant peaks. Furthermore, a very short fade window (5–15 ms) acts as a rapid amplitude modulation whose main-lobe bandwidth ($1/L \approx 67\text{–}200\text{ Hz}$) falls directly into the audible fundamental frequency range, producing sideband roughness when blending independently synthesized chunks.
   - **At 50 ms**: Even an 80 Hz voice spans 4 full pitch periods (and 2.5 ContentVec feature frames), stabilizing correlation peak selection and keeping window modulation below the pitch band.

2. **Why Extending Crossfades Beyond 50 ms Does Not Improve Quality**:
   - **Limits of Speech Quasi-Stationarity**: Human speech is only quasi-stationary over ~20–40 ms intervals; across 100–500 ms, pitch ($F_0$) and formant structure shift continuously. Because SOLA applies a single constant offset $\Delta_{\text{opt}}$ across the entire window $L$, an overly long window averages across changing pitch periods, smearing the correlation peak.
   - **Phase Drift and Transient Smearing**: Because consecutive chunks are synthesized with different context windows, slight differences in estimated $F_0$ or harmonic phase can occur. Blending two chunks slowly over $> 100\text{ ms}$ allows phase drift to accumulate while both signals are audible, introducing chorus/flanging (double-voice) artifacts and softening plosive consonants.
   - **Redundant Re-Inference**: Every additional millisecond of crossfade overlap increases the audio length re-evaluated on each chunk (`convert_size`) without improving boundary continuity.

Because both reducing `crossfade_sec` below 50 ms and increasing it above 50 ms are counterproductive, exposing `crossfade_sec` as a user-tunable parameter offers no practical benefit.

---

## 3. Architectural Decision: Fixed 50 ms Pipeline Target with Adaptive Clamping

Forge removes `crossfade_sec` from user-facing configuration and fixes the pipeline target to 50 ms (`DEFAULT_CROSSFADE_SEC = 0.05`), automatically clamping to the actual chunk duration when a shorter buffer is processed.

### 3.1 Pipeline Changes

1. **Removal from `VoiceChangerConfiguration`**:
   `crossfade_sec` is removed from the Pydantic model `VoiceChangerConfiguration` in `backend/vcclient/voice_changer/data_types/data_types.py`.
   - Incoming legacy HTTP PUT payloads containing `crossfade_sec` are ignored by Pydantic without validation errors.
   - Legacy configuration files (`vc_conf.json`) are parsed safely, dropping the removed field upon deserialization.

2. **Canonical Default Constant**:
   Defined in `backend/vcclient/voice_changer/voice_changer_const.py`:
   ```python
   DEFAULT_CROSSFADE_SEC: float = 0.05
   ```

3. **Pipeline Warmup and Target Feature Length in `RVCPipeline`**:
   `RVCPipeline._warmup` and `RVCPipeline._calculate_target_feats_length` in `backend/vcclient/voice_changer/voice_change_manager/vc_pipelines/rvc_pipeline.py` reference `DEFAULT_CROSSFADE_SEC` directly (`min(chunk_sec, DEFAULT_CROSSFADE_SEC)`), removing runtime configuration coupling during ONNX session initialization and static/bounded shape calculation.

4. **Dynamic Clamping in `VoiceChanger._convert_chunk`**:
   In `backend/vcclient/voice_changer/voice_change_manager/voice_changer.py`, the runtime calculates the effective chunk duration from the actual output sample count (`output_size`), covering both bulk queue chunks (`vc_chunk_sec`) and arbitrary-length `direct_from_server=True` buffers:
   ```python
   if hasattr(self, "vc_info") and self.vc_info.vc_output_sample_rate > 0 and output_size > 0:
       actual_chunk_sec = output_size / self.vc_info.vc_output_sample_rate
   else:
       actual_chunk_sec = vc_chunk_sec

   real_crossfade_sec = min(DEFAULT_CROSSFADE_SEC, actual_chunk_sec)
   ```
   For all standard chunk sizes ($\ge 0.05\text{ s}$), `real_crossfade_sec` remains 50 ms. When processing buffers shorter than 50 ms, the crossfade window scales down proportionally so it does not exceed the output chunk duration.

5. **Defensive Clamping in `CrossfadeProcessor.apply`**:
   In `backend/vcclient/voice_changer/voice_change_manager/crossfade_processor.py`, to prevent NumPy broadcast exceptions even if rounding or direct callers pass `crossfade_size > output_audio_size`:
   ```python
   crossfade_size = min(crossfade_size, output_audio_size)
   ```

### 3.2 Why 1:1 Clamping (`min(DEFAULT_CROSSFADE_SEC, actual_chunk_sec)`) Instead of Fractional Scaling

When `actual_chunk_sec <= 0.05` s (such as at the minimum standard `chunk_sec = 0.05` s), `min(DEFAULT_CROSSFADE_SEC, actual_chunk_sec)` sets `real_crossfade_sec = actual_chunk_sec` rather than scaling the crossfade down by a fractional factor (e.g., `actual_chunk_sec * 0.75`):

1. **50% Overlap-Add Synthesis Geometry ($L = N$ within $2N$)**:
   In `RVCPipeline._generate_inputs`, the synthesized waveform length per step is:
   $$\text{real\_convert\_size} = \underbrace{\text{output\_audio\_size}}_{N} + \underbrace{\text{crossfade\_size}}_{L} + \underbrace{\text{sola\_search\_frame}}_{S}$$
   When $L = N$ (e.g., $N = 50\text{ ms}$ hop size and $L = 50\text{ ms}$ crossfade), each inference step synthesizes $2N = 100\text{ ms}$ of audio (plus the 12 ms SOLA search margin) and advances by $N = 50\text{ ms}$. In `CrossfadeProcessor.apply`, the emitted slice $[\Delta_{\text{opt}} : \Delta_{\text{opt}} + N]$ and the next chunk's fade-out tail `prev_rest_buffer` ($[\Delta_{\text{opt}} + N : \Delta_{\text{opt}} + N + L]$) remain disjoint segments of the synthesized buffer. Consequently, $L = N$ corresponds to the standard **50% overlap-add (OLA)** condition with complementary $\cos^2$ + $\sin^2 = 1$ windows.

2. **Preserving Maximum Available Pitch Cycles on Minimum Chunks**:
   Applying a fractional multiplier such as `0.75` would have no effect on chunks $\ge 0.08\text{ s}$ (`min(0.05, 0.08 * 0.75) = 0.05`), while reducing the crossfade at `chunk_sec = 0.05` s from **50 ms to 37.5 ms** (and reducing sub-50ms buffers even further). Shortening the window on the smallest chunks—where boundary transitions occur most frequently—reduces ContentVec overlap below 2 frames (37.5 ms = 1.875 frames) and reduces 80 Hz pitch coverage from 4 cycles to 3 cycles, increasing susceptibility to boundary roughness.

3. **Exact Sample-Level Guard and Pipeline Consistency**:
   Because `CrossfadeProcessor.apply` enforces `crossfade_size = min(crossfade_size, output_audio_size)` directly on sample counts, a fractional margin is unnecessary to guard against rounding mismatches. Keeping `min(DEFAULT_CROSSFADE_SEC, actual_chunk_sec)` also maintains consistent dimension derivation with `calculate_target_feats_length` in `backend/vcclient/device/coreml_patch.py`.
