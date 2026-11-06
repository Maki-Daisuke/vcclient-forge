"""Parity verification for RVC voice conversion across execution providers using JVNV voice sample."""

import os
import sys
import wave
from pathlib import Path

# Setup paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_BACKEND_DIR))

from vcclient.utils.runtime_env import setup_runtime_env

setup_runtime_env()

import numpy as np
import onnxruntime as ort
import samplerate

from vcclient.voice_changer.voice_change_manager.device_manager.device_manager import DeviceManager
from vcclient.voice_changer.voice_change_manager.inferencer.onnx_patch import patch_rvc_model_for_openvino


def load_wav_as_float32(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        n_frames = w.getnframes()
        data = w.readframes(n_frames)

    if sampwidth == 2:
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 3:
        raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3)
        padded = np.zeros((len(raw), 4), dtype=np.uint8)
        padded[:, 1:] = raw
        int32_arr = padded.view(np.int32).flatten() // 256
        audio = int32_arr.astype(np.float32) / 8388608.0
    elif sampwidth == 4:
        audio = np.frombuffer(data, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sampwidth: {sampwidth}")

    if n_channels > 1:
        audio = audio.reshape(-1, n_channels)[:, 0]
    return audio, sr


def save_float32_as_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
    int16_data = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16_data.tobytes())


def extract_features_and_pitch(
    audio_16k: np.ndarray,
    contentvec_path: Path,
    rmvpe_path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Extract features (ContentVec) and pitch (RMVPE) using pure ONNX."""
    from vcclient.voice_changer.voice_change_manager.pitch_estimator.onnxrmvpe_pitch_estimator import (
        RMVPEOnnxPitchEstimator,
    )

    # 1. RMVPE pitch estimation
    estimator = RMVPEOnnxPitchEstimator("rmvpe", rmvpe_path, device_id=-1)
    pitch_coarse, pitch_hz = estimator.estimate(
        audio=audio_16k,
        sample_rate=16000,
        window_length=160,
    )

    # 2. ContentVec feature extraction
    so = ort.SessionOptions()
    so.log_severity_level = 3
    s_cv = ort.InferenceSession(str(contentvec_path), sess_options=so, providers=["CPUExecutionProvider"])
    
    # ContentVec expects input shape [1, num_samples]
    cv_in = audio_16k.reshape(1, -1).astype(np.float32)
    feats = s_cv.run(["unit12"], {"audio": cv_in})[0]  # [1, T, 768] (RVC v2 layer 12)

    # Align length between feats and pitch
    t_len = min(feats.shape[1], pitch_coarse.shape[1])
    feats = feats[:, :t_len, :]
    pitch_coarse = pitch_coarse[:, :t_len]
    pitch_hz = pitch_hz[:, :t_len]

    return feats, pitch_coarse, pitch_hz


def main():
    wav_path = _PROJECT_ROOT / "web_front" / "ui" / "2.1.4" / "assets" / "voices" / "JVNV" / "partial" / "F1_happy_regular_26.wav"
    model_path = _PROJECT_ROOT / "model_dir" / "0" / "kikoto_kurage_v2_40k_e100_float.onnx"
    contentvec_path = _PROJECT_ROOT / "modules" / "contentvec" / "contentvec-f.onnx"
    rmvpe_path = _PROJECT_ROOT / "modules" / "rmvpe" / "rmvpe_20231006.onnx"

    print(f"Loading test audio: {wav_path.name}")
    audio, sr = load_wav_as_float32(wav_path)
    print(f"Loaded {len(audio)} samples @ {sr}Hz ({len(audio)/sr:.2f}s)")

    # Resample to 16kHz for frontends
    if sr != 16000:
        audio_16k = samplerate.resample(audio, 16000 / sr, "sinc_fastest")
    else:
        audio_16k = audio

    # Take a 2.0-second slice containing clear speech
    start = int(0.5 * 16000)
    end = start + int(2.0 * 16000)
    audio_slice = audio_16k[start:end]

    print("\nExtracting features and pitch...")
    feats, pitch_coarse, pitch_hz = extract_features_and_pitch(audio_slice, contentvec_path, rmvpe_path)
    p_len = np.array([feats.shape[1]], dtype=np.int64)
    sid = np.array([0], dtype=np.int64)

    print(f"Features shape: {feats.shape}, Pitch shape: {pitch_hz.shape}, Non-zero pitch: {np.count_nonzero(pitch_hz)}/{pitch_hz.size}")

    feed_base = {
        "feats": feats.astype(np.float32),
        "p_len": p_len,
        "pitch": pitch_coarse.astype(np.int64),
        "pitchf": pitch_hz.astype(np.float32),
        "sid": sid,
    }

    # Prepare models: original vs 4D patched
    orig_bytes = model_path.read_bytes()
    patched_bytes = patch_rvc_model_for_openvino(orig_bytes)

    out_dir = _PROJECT_ROOT / "tmp_test_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # 1. Original model on CPU
    print("\n[1] Running Original Model on CPU...")
    s_cpu_orig = ort.InferenceSession(orig_bytes, providers=["CPUExecutionProvider"])
    out_cpu_orig = s_cpu_orig.run(["audio"], feed_base)[0].squeeze()
    results["cpu_orig"] = out_cpu_orig
    save_float32_as_wav(out_dir / "out_cpu_orig.wav", out_cpu_orig, 40000)

    # 2. 4D Patched model on CPU
    print("[2] Running 4D Patched Model on CPU...")
    s_cpu_patched = ort.InferenceSession(patched_bytes, providers=["CPUExecutionProvider"])
    out_cpu_patched = s_cpu_patched.run(["audio"], feed_base)[0].squeeze()
    results["cpu_patched"] = out_cpu_patched
    save_float32_as_wav(out_dir / "out_cpu_patched.wav", out_cpu_patched, 40000)

    diff_patch_cpu = np.max(np.abs(out_cpu_orig - out_cpu_patched))
    print(f"  -> Max abs diff between CPU Orig and CPU Patched: {diff_patch_cpu:.6e}")

    # 3. 4D Patched model on OpenVINO GPU
    print("\n[3] Running 4D Patched Model on OpenVINO GPU...")
    dev_mgr = DeviceManager.get_instance()
    providers, provider_options = dev_mgr.get_onnx_execution_provider(1000)
    try:
        s_ov_gpu = dev_mgr.create_inference_session(patched_bytes, providers, provider_options)
        print(f"  -> Active providers: {s_ov_gpu.get_providers()}")
        out_ov_gpu = s_ov_gpu.run(["audio"], feed_base)[0].squeeze()
        results["ov_gpu"] = out_ov_gpu
        save_float32_as_wav(out_dir / "out_ov_gpu.wav", out_ov_gpu, 40000)

        diff_ov_vs_cpu_orig = np.max(np.abs(out_cpu_orig - out_ov_gpu))
        print(f"  -> Max abs diff between CPU Orig and OpenVINO GPU: {diff_ov_vs_cpu_orig:.6e}")
        
        # Audio energy analysis
        rms_cpu = np.sqrt(np.mean(out_cpu_orig**2))
        rms_ov = np.sqrt(np.mean(out_ov_gpu**2))
        print(f"  -> RMS energy: CPU Orig = {rms_cpu:.4f}, OpenVINO GPU = {rms_ov:.4f}")
    except Exception as e:
        print(f"  -> OpenVINO GPU execution failed: {e}")

    # 4. Original model on DirectML (if available)
    if "DmlExecutionProvider" in ort.get_available_providers():
        print("\n[4] Running Original Model on DirectML...")
        try:
            s_dml = ort.InferenceSession(orig_bytes, providers=["DmlExecutionProvider"])
            out_dml = s_dml.run(["audio"], feed_base)[0].squeeze()
            results["dml"] = out_dml
            save_float32_as_wav(out_dir / "out_dml.wav", out_dml, 40000)
            diff_dml = np.max(np.abs(out_cpu_orig - out_dml))
            print(f"  -> Max abs diff between CPU Orig and DirectML: {diff_dml:.6e}")
            print(f"  -> RMS energy: DirectML = {np.sqrt(np.mean(out_dml**2)):.4f}")
        except Exception as e:
            print(f"  -> DirectML execution failed: {e}")

    print(f"\nSaved test audio files to: {out_dir}")


if __name__ == "__main__":
    main()
