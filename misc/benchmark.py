"""Cross-Platform Hardware Capability Benchmark for VCClient Forge.

Benchmarks RMVPE, FCPE, ContentVec, and RVC ONNX models across all
available Execution Providers and hardware devices, outputting structured
Markdown reports to stdout.
"""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure backend directory is in sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent / "backend"
if _BACKEND_DIR.exists() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Initialize CUDA / GPU runtime environment transparently via vcclient
from vcclient.utils.cuda_env import setup_cuda_env

setup_cuda_env()

import numpy as np
import onnxruntime as ort


@dataclass
class DeviceInfo:
    os_name: str
    os_version: str
    architecture: str
    processor_name: str
    cpu_cores: int | None
    numpy_runtime: str
    available_providers: list[str]
    ep_devices: list[dict[str, Any]] = field(default_factory=list)
    raw_ep_devices: list[Any] = field(default_factory=list)


@dataclass
class TargetConfig:
    label: str
    provider_name: str
    provider_options: dict[str, Any]
    ep_device: Any = None


@dataclass
class BenchmarkResult:
    model_name: str
    provider_name: str
    provider_options: dict[str, Any]
    active_providers: list[str]
    success: bool
    error_message: str | None = None
    latencies_ms: list[float] = field(default_factory=list)
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    stdev_ms: float = 0.0


def probe_hardware() -> DeviceInfo:
    """Enumerate platform hardware using in-band NumPy and ONNX Runtime APIs."""
    # 1. Platform information
    os_name = platform.system()
    os_version = platform.release()
    arch = platform.machine()
    processor = platform.processor() or "Unknown Processor"
    cpu_cores = os.cpu_count()

    # 2. NumPy SIMD Telemetry
    np_runtime_summary = "N/A"
    try:
        # np.show_runtime() emits text; capture or inspect cpu features
        cpu_features = getattr(
            getattr(np, "_core", None) or getattr(np, "core", None),
            "_multiarray_umath",
            None,
        )
        features_dict = getattr(cpu_features, "__cpu_features__", None)
        if features_dict:
            active_simd = [k for k, v in features_dict.items() if v]
            np_runtime_summary = ", ".join(active_simd) if active_simd else "None"
        elif hasattr(np, "show_runtime"):
            np_runtime_summary = "NumPy runtime introspection supported"
    except Exception:  # noqa: BLE001
        np_runtime_summary = "Telemetry unavailable"

    # 3. ONNX Runtime Execution Providers
    available_providers = ort.get_available_providers()

    # 4. ONNX Runtime Device Topology (get_ep_devices)
    ep_devices_info: list[dict[str, Any]] = []
    raw_devices: list[Any] = []
    if hasattr(ort, "get_ep_devices"):
        try:
            raw_devices = list(ort.get_ep_devices())
            for dev in raw_devices:
                dev_type_str = str(getattr(dev.device, "type", "Unknown"))
                # Simplify OrtHardwareDeviceType enum representation
                if "." in dev_type_str:
                    dev_type_str = dev_type_str.split(".")[-1]
                ep_devices_info.append(
                    {
                        "ep_name": dev.ep_name,
                        "type": dev_type_str,
                        "vendor": getattr(dev.device, "vendor", "Unknown"),
                        "device_id": getattr(dev.device, "device_id", 0),
                        "metadata": getattr(dev.device, "metadata", {}),
                    }
                )
        except Exception as e:  # noqa: BLE001
            ep_devices_info.append({"error": f"get_ep_devices failed: {e}"})

    return DeviceInfo(
        os_name=os_name,
        os_version=os_version,
        architecture=arch,
        processor_name=processor,
        cpu_cores=cpu_cores,
        numpy_runtime=np_runtime_summary,
        available_providers=available_providers,
        ep_devices=ep_devices_info,
        raw_ep_devices=raw_devices,
    )


def find_model_path(candidates: list[str | Path]) -> Path | None:
    """Find the first existing model file from candidate paths or glob patterns."""
    for cand in candidates:
        cand_str = str(cand)
        if "*" in cand_str:
            matches = list(Path(".").glob(cand_str))
            if matches:
                return matches[0]
        else:
            p = Path(cand_str)
            if p.exists() and p.is_file():
                return p
    return None


def discover_models(args: argparse.Namespace) -> dict[str, Path | None]:
    """Discover paths for RMVPE, FCPE, ContentVec, and RVC models."""
    models: dict[str, Path | None] = {}

    # Base search prefixes
    base_dirs = [
        Path(args.models_dir) if args.models_dir else None,
        Path("modules"),
        Path("model_dir"),
        Path("dist"),
        Path("."),
    ]
    base_dirs = [d for d in base_dirs if d and d.exists()]

    # 1. RMVPE
    rmvpe_candidates = [args.rmvpe] if args.rmvpe else []
    for b in base_dirs:
        rmvpe_candidates.extend(
            [
                b / "rmvpe" / "rmvpe_20231006.onnx",
                b / "modules" / "rmvpe" / "rmvpe_20231006.onnx",
                f"{b}/**/rmvpe_20231006.onnx",
                f"{b}/**/rmvpe*.onnx",
            ]
        )
    models["RMVPE"] = find_model_path(rmvpe_candidates)

    # 2. FCPE
    fcpe_candidates = [args.fcpe] if args.fcpe else []
    for b in base_dirs:
        fcpe_candidates.extend(
            [
                b / "fcpe" / "fcpe.onnx",
                b / "modules" / "fcpe" / "fcpe.onnx",
                f"{b}/**/fcpe.onnx",
            ]
        )
    models["FCPE"] = find_model_path(fcpe_candidates)

    # 3. ContentVec
    cvec_candidates = [args.contentvec] if args.contentvec else []
    for b in base_dirs:
        cvec_candidates.extend(
            [
                b / "contentvec" / "contentvec-f.onnx",
                b / "modules" / "contentvec" / "contentvec-f.onnx",
                f"{b}/**/contentvec-f.onnx",
                f"{b}/**/contentvec*.onnx",
            ]
        )
    models["ContentVec"] = find_model_path(cvec_candidates)

    # 4. RVC
    rvc_candidates = [args.rvc] if args.rvc else []
    for b in base_dirs:
        rvc_candidates.extend(
            [
                b / "0" / "kikoto_kurage_v2_40k_e100_float.onnx",
                f"{b}/model_dir/*/*.onnx",
                f"{b}/**/kikoto_kurage*.onnx",
                f"{b}/**/model_dir/*/*.onnx",
            ]
        )
    models["RVC"] = find_model_path(rvc_candidates)

    return models


def generate_benchmark_targets(
    hw_info: DeviceInfo,
    threads: int,
) -> list[TargetConfig]:
    """Build list of TargetConfig configurations to benchmark."""
    targets: list[TargetConfig] = []

    # 1. CPUExecutionProvider
    if "CPUExecutionProvider" in hw_info.available_providers:
        targets.append(
            TargetConfig(
                label=f"CPU EP (intra_op_num_threads={threads})",
                provider_name="CPUExecutionProvider",
                provider_options={"intra_op_num_threads": threads},
            )
        )

    # 2. OpenVINO Execution Provider
    # 2a. Check dynamic plugin EP devices (ort.get_ep_devices)
    ov_devices = [
        d
        for d in hw_info.raw_ep_devices
        if getattr(d, "ep_name", "") == "OpenVINOExecutionProvider"
    ]
    if ov_devices:
        for d in ov_devices:
            ov_target = "UNKNOWN"
            if hasattr(d, "ep_metadata") and isinstance(d.ep_metadata, dict):
                ov_target = d.ep_metadata.get("ov_device", "AUTO")
            elif hasattr(d, "device"):
                ov_target = str(getattr(d.device, "type", "UNKNOWN"))
                if "." in ov_target:
                    ov_target = ov_target.split(".")[-1]
            dev_id = getattr(getattr(d, "device", None), "device_id", 0)
            targets.append(
                TargetConfig(
                    label=f"OpenVINO EP ({ov_target}, id={dev_id})",
                    provider_name="OpenVINOExecutionProvider",
                    provider_options={},
                    ep_device=d,
                )
            )
    elif "OpenVINOExecutionProvider" in hw_info.available_providers:
        # 2b. Fallback to in-tree OpenVINO providers if available
        for dev_type in ["CPU", "GPU", "NPU"]:
            targets.append(
                TargetConfig(
                    label=f"OpenVINO EP (device_type={dev_type})",
                    provider_name="OpenVINOExecutionProvider",
                    provider_options={"device_type": dev_type},
                )
            )

    # 3. CUDAExecutionProvider
    if "CUDAExecutionProvider" in hw_info.available_providers:
        targets.append(
            TargetConfig(
                label="CUDA EP (device_id=0)",
                provider_name="CUDAExecutionProvider",
                provider_options={"device_id": 0},
            )
        )

    # 4. DmlExecutionProvider
    if "DmlExecutionProvider" in hw_info.available_providers:
        targets.append(
            TargetConfig(
                label="DirectML EP (device_id=0)",
                provider_name="DmlExecutionProvider",
                provider_options={"device_id": 0},
            )
        )

    # 5. CoreMLExecutionProvider
    if "CoreMLExecutionProvider" in hw_info.available_providers:
        targets.append(
            TargetConfig(
                label="CoreML EP",
                provider_name="CoreMLExecutionProvider",
                provider_options={},
            )
        )

    return targets


def run_benchmark_for_model(
    model_name: str,
    model_path: Path,
    target: TargetConfig,
    warmup_runs: int,
    benchmark_runs: int,
    sample_rate: int = 16000,
    window_samples: int = 4096,  # 256 ms @ 16kHz
) -> BenchmarkResult:
    """Benchmark a single model on a specific Execution Provider configuration."""
    result = BenchmarkResult(
        model_name=model_name,
        provider_name=target.label,
        provider_options=target.provider_options,
        active_providers=[],
        success=False,
    )

    so = ort.SessionOptions()
    so.log_severity_level = 3  # Suppress driver diagnostic warnings

    if "intra_op_num_threads" in target.provider_options:
        so.intra_op_num_threads = int(target.provider_options["intra_op_num_threads"])

    try:
        if target.ep_device is not None and hasattr(so, "add_provider_for_devices"):
            so.add_provider_for_devices([target.ep_device], target.provider_options)
            session = ort.InferenceSession(
                str(model_path),
                sess_options=so,
            )
        else:
            session = ort.InferenceSession(
                str(model_path),
                sess_options=so,
                providers=[target.provider_name],
                provider_options=[target.provider_options],
            )
    except Exception as e:  # noqa: BLE001
        result.error_message = f"Session creation failed: {e}"
        return result

    result.active_providers = session.get_providers()

    # Silent fallback verification
    if target.provider_name not in result.active_providers:
        result.error_message = (
            f"Provider '{target.provider_name}' was not retained by ONNX Runtime. "
            f"Active providers: {result.active_providers} (silent fallback detected)"
        )
        return result

    # Prepare model-specific test feed
    feed: dict[str, np.ndarray] = {}
    output_names: list[str] | None = None

    try:
        if model_name == "RMVPE":
            # waveform: [1, n_samples], threshold: [1]
            audio = np.random.randn(1, window_samples).astype(np.float32)
            th = np.array([0.3], dtype=np.float32)
            feed = {"waveform": audio, "threshold": th}
            output_names = ["pitchf"]

        elif model_name == "FCPE":
            # audio: [1, n_samples, 1]
            audio = np.random.randn(1, window_samples, 1).astype(np.float32)
            feed = {"audio": audio}
            output_names = ["f0_hz"]

        elif model_name == "ContentVec":
            # audio: [1, n_samples]
            audio = np.random.randn(1, window_samples).astype(np.float32)
            feed = {"audio": audio}
            output_names = ["unit12"]

        elif model_name == "RVC":
            # Determine feature dimension from model inputs (256 for v1, 768 for v2)
            feats_input = next(
                (i for i in session.get_inputs() if i.name == "feats"), None
            )
            dim = 768
            if (
                feats_input
                and len(feats_input.shape) == 3
                and isinstance(feats_input.shape[2], int)
            ):
                dim = feats_input.shape[2]

            # 256 ms @ 16kHz = ~32 frames (hop size 128)
            frames = max(1, window_samples // 128)
            feats = np.random.randn(1, frames, dim).astype(np.float32)
            p_len = np.array([frames], dtype=np.int64)
            # pitch must be in range [1, 255] for RVC coarse embedding
            pitch = np.random.randint(1, 255, size=(1, frames), dtype=np.int64)
            pitchf = np.random.uniform(50.0, 400.0, size=(1, frames)).astype(np.float32)
            sid = np.array([0], dtype=np.int64)

            feed = {
                "feats": feats,
                "p_len": p_len,
                "pitch": pitch,
                "pitchf": pitchf,
                "sid": sid,
            }
            output_names = ["audio"]

        else:
            result.error_message = f"Unsupported model name: {model_name}"
            return result

        # Warmup executions
        for _ in range(warmup_runs):
            session.run(output_names, feed)

        # Timed benchmark runs
        latencies: list[float] = []
        for _ in range(benchmark_runs):
            t_start = time.perf_counter_ns()
            session.run(output_names, feed)
            t_end = time.perf_counter_ns()
            latencies.append((t_end - t_start) / 1_000_000.0)

        result.latencies_ms = latencies
        result.min_ms = min(latencies)
        result.max_ms = max(latencies)
        result.mean_ms = statistics.mean(latencies)
        result.median_ms = statistics.median(latencies)
        result.stdev_ms = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
        result.success = True

    except Exception as e:  # noqa: BLE001
        result.error_message = f"Inference execution failed: {e}"

    return result


def render_markdown_report(
    hw_info: DeviceInfo,
    model_paths: dict[str, Path | None],
    results_by_model: dict[str, list[BenchmarkResult]],
    window_ms: float,
    warmup_runs: int,
    benchmark_runs: int,
) -> str:
    """Format benchmark results into structured Markdown."""
    lines: list[str] = []

    lines.append("# VCClient Forge Hardware Capability Benchmark Report")
    lines.append("")
    lines.append(f"> Generated at: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append(
        f"> Test Parameters: Analysis Window = {window_ms:.1f} ms, Warmup = {warmup_runs} runs, Benchmark = {benchmark_runs} runs"
    )
    lines.append("")

    # Section 1: Detected Devices
    lines.append("## 検出したデバイス一覧")
    lines.append("")
    lines.append(
        f"- **OS**: {hw_info.os_name} {hw_info.os_version} ({hw_info.architecture})"
    )
    lines.append(
        f"- **CPU**: {hw_info.processor_name} ({hw_info.cpu_cores} logical cores)"
    )
    lines.append(f"- **NumPy Active Vector Extensions**: {hw_info.numpy_runtime}")
    lines.append(
        f"- **ONNX Runtime Available Providers**: `{hw_info.available_providers}`"
    )
    lines.append("")

    if hw_info.ep_devices:
        lines.append("### ORT EP Devices (`ort.get_ep_devices()`)")
        lines.append("")
        for idx, dev in enumerate(hw_info.ep_devices):
            if "error" in dev:
                lines.append(f"- Device {idx}: {dev['error']}")
            else:
                desc = dev.get("metadata", {}).get("Description", "N/A")
                lines.append(
                    f"- **[{dev['ep_name']}]** {dev['vendor']} {desc} (Type: `{dev['type']}`, ID: `{dev['device_id']}`)"
                )
        lines.append("")

    # Model Summary Table
    lines.append("### 計測対象モデルファイル")
    lines.append("")
    lines.append("| Model | Status | Resolved Path |")
    lines.append("| :--- | :--- | :--- |")
    for model_name, p in model_paths.items():
        if p:
            lines.append(f"| **{model_name}** | Found | `{p.as_posix()}` |")
        else:
            lines.append(f"| **{model_name}** | Not Found (Skipped) | — |")
    lines.append("")

    # Section 2+: Results per Model
    for model_name, results in results_by_model.items():
        lines.append(f"## {model_name}の計測結果")
        lines.append("")

        if not results:
            lines.append("*(モデルファイルが存在しないため、計測をスキップしました)*")
            lines.append("")
            continue

        for res in results:
            lines.append(f"### {res.provider_name}の計測結果")
            lines.append("")

            if not res.success:
                lines.append("- **Status**: [FAILED / SKIPPED]")
                lines.append(f"- **Reason**: {res.error_message}")
                lines.append(f"- **Active Providers**: `{res.active_providers}`")
                lines.append("")
                continue

            lines.append("- **統計情報**:")
            lines.append(f"  - **最小値 (Min)**: `{res.min_ms:.2f} ms`")
            lines.append(f"  - **最大値 (Max)**: `{res.max_ms:.2f} ms`")
            lines.append(f"  - **平均値 (Mean)**: `{res.mean_ms:.2f} ms`")
            lines.append(f"  - **中央値 (Median)**: `{res.median_ms:.2f} ms`")
            lines.append(f"  - **標準偏差 (StdDev)**: `{res.stdev_ms:.2f} ms`")
            lines.append("")
            raw_formatted = ", ".join(f"{x:.2f}" for x in res.latencies_ms)
            lines.append(f"- **生の計測値 (ms)**: `[{raw_formatted}]`")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    # Ensure stdout/stderr handles UTF-8 on Windows
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Benchmark RMVPE, FCPE, ContentVec, and RVC models across ONNX Execution Providers."
    )
    parser.add_argument(
        "--models-dir", type=str, default=None, help="Base directory containing models"
    )
    parser.add_argument(
        "--rmvpe", type=str, default=None, help="Explicit path to rmvpe.onnx"
    )
    parser.add_argument(
        "--fcpe", type=str, default=None, help="Explicit path to fcpe.onnx"
    )
    parser.add_argument(
        "--contentvec", type=str, default=None, help="Explicit path to contentvec.onnx"
    )
    parser.add_argument(
        "--rvc", type=str, default=None, help="Explicit path to rvc.onnx"
    )
    parser.add_argument(
        "--warmup", type=int, default=5, help="Number of warmup executions (default: 5)"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of timed benchmark runs (default: 10)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=8,
        help="Number of intra-op threads for CPU EP (default: 8)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=4096,
        help="Audio window samples @ 16kHz (default: 4096 = 256ms)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Optional file path to save Markdown report",
    )

    args = parser.parse_args()

    # 1. Enumerate hardware and providers
    hw_info = probe_hardware()

    # 2. Discover model files
    models = discover_models(args)

    # 3. Build target provider list
    targets = generate_benchmark_targets(hw_info, threads=args.threads)

    # 4. Run benchmarks
    results_by_model: dict[str, list[BenchmarkResult]] = {}
    window_ms = (args.samples / 16000.0) * 1000.0

    for model_name, model_path in models.items():
        if not model_path:
            results_by_model[model_name] = []
            continue

        model_results: list[BenchmarkResult] = []
        for target in targets:
            res = run_benchmark_for_model(
                model_name=model_name,
                model_path=model_path,
                target=target,
                warmup_runs=args.warmup,
                benchmark_runs=args.runs,
                sample_rate=16000,
                window_samples=args.samples,
            )
            model_results.append(res)

        results_by_model[model_name] = model_results

    # 5. Render Markdown report
    report_md = render_markdown_report(
        hw_info=hw_info,
        model_paths=models,
        results_by_model=results_by_model,
        window_ms=window_ms,
        warmup_runs=args.warmup,
        benchmark_runs=args.runs,
    )

    # Output to stdout
    print(report_md)

    # Optional file output
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")
        print(
            f"\n[Info] Benchmark report saved to: {out_path.resolve()}", file=sys.stderr
        )


if __name__ == "__main__":
    main()
