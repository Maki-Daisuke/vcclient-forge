"""Cross-Platform Hardware Capability Benchmark for VCClient Forge.

Benchmarks RMVPE, FCPE, ContentVec, and RVC ONNX models across all
available Execution Providers and hardware devices, outputting structured
Markdown reports to stdout.
"""

from __future__ import annotations

import argparse
import json
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

# Initialize hardware accelerator runtime environment transparently via vcclient
from vcclient.device import setup_runtime_env

setup_runtime_env()

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
    skip_npu: bool = False,
    providers_filter: list[str] | None = None,
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
            if skip_npu and "NPU" in ov_target.upper():
                continue
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
            if skip_npu and dev_type == "NPU":
                continue
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

    if providers_filter:
        normalized_filter = [p.strip().upper() for p in providers_filter if p.strip()]
        targets = [
            t
            for t in targets
            if any(
                f in t.label.upper() or f in t.provider_name.upper()
                for f in normalized_filter
            )
        ]

    return targets


def get_openvino_device_name(target: TargetConfig) -> str:
    """Extract OpenVINO target hardware device name (GPU, NPU, CPU) from TargetConfig."""
    lbl = target.label.upper()
    if "GPU" in lbl:
        return "GPU"
    if "NPU" in lbl:
        return "NPU"
    if "CPU" in lbl:
        return "CPU"
    if target.ep_device is not None:
        raw_type = str(
            getattr(getattr(target.ep_device, "device", None), "type", "")
        ).upper()
        if "GPU" in raw_type:
            return "GPU"
        if "NPU" in raw_type:
            return "NPU"
        if "CPU" in raw_type:
            return "CPU"
    dev_type = str(target.provider_options.get("device_type", "")).upper()
    if dev_type in ("GPU", "NPU", "CPU"):
        return dev_type
    return "GPU"


def get_openvino_reshape_input(model_path: Path, window_samples: int) -> str | None:
    """Infer concrete static input shapes for OpenVINO NPU compilation."""
    try:
        import onnx

        m = onnx.load(str(model_path), load_external_data=False)
        shapes: list[str] = []
        frames = max(1, window_samples // 128)
        for inp in m.graph.input:
            dims: list[int] = []
            for idx, dim in enumerate(inp.type.tensor_type.shape.dim):
                if dim.dim_value > 0:
                    dims.append(dim.dim_value)
                else:
                    name = inp.name.lower()
                    if "waveform" in name or "audio" in name:
                        dims.append(window_samples)
                    elif (
                        "feats" in name
                        or "pitch" in name
                        or ("rnd" in name and idx == 2)
                    ):
                        dims.append(frames)
                    elif idx == 0:
                        dims.append(1)
                    else:
                        dims.append(1)
            shapes.append(f"{inp.name}[{','.join(str(d) for d in dims)}]")
        return ",".join(shapes)
    except Exception as e:  # noqa: BLE001
        print(
            f"[Warning] Failed to inspect ONNX shapes for {model_path.name}: {e}",
            file=sys.stderr,
        )
        return None


def verify_3d_to_4d_resize_parity(
    scale_factor: float, tolerance: float = 1e-5
) -> float:
    """Validate numerical equivalence between 3D linear Resize and 4D Unsqueeze+Resize+Squeeze."""
    import onnx
    from onnx import helper, numpy_helper

    rng = np.random.RandomState(42)
    test_in = rng.randn(1, 2, 16).astype(np.float32)

    # 1. 3D reference graph
    x3 = helper.make_tensor_value_info("x3", onnx.TensorProto.FLOAT, [1, 2, 16])
    y3 = helper.make_tensor_value_info("y3", onnx.TensorProto.FLOAT, [1, 2, None])
    sc3 = numpy_helper.from_array(
        np.array([1.0, 1.0, scale_factor], dtype=np.float32), name="sc3"
    )
    n3 = helper.make_node(
        "Resize",
        ["x3", "", "sc3"],
        ["y3"],
        mode="linear",
        coordinate_transformation_mode="align_corners",
    )
    g3 = helper.make_graph([n3], "g3", [x3], [y3], [sc3])
    m3 = helper.make_model(
        g3, opset_imports=[helper.make_opsetid("", 17)], ir_version=8
    )
    s3 = ort.InferenceSession(
        m3.SerializeToString(), providers=["CPUExecutionProvider"]
    )
    out3 = s3.run(None, {"x3": test_in})[0]

    # 2. 4D patched graph
    x4 = helper.make_tensor_value_info("x4", onnx.TensorProto.FLOAT, [1, 2, 16])
    y4 = helper.make_tensor_value_info("y4", onnx.TensorProto.FLOAT, [1, 2, None])
    ax = numpy_helper.from_array(np.array([2], dtype=np.int64), name="ax")
    sc4 = numpy_helper.from_array(
        np.array([1.0, 1.0, 1.0, scale_factor], dtype=np.float32), name="sc4"
    )
    unsq = helper.make_node("Unsqueeze", ["x4", "ax"], ["x4_4d"])
    n4 = helper.make_node(
        "Resize",
        ["x4_4d", "", "sc4"],
        ["y4_4d"],
        mode="linear",
        coordinate_transformation_mode="align_corners",
    )
    sq = helper.make_node("Squeeze", ["y4_4d", "ax"], ["y4"])
    g4 = helper.make_graph([unsq, n4, sq], "g4", [x4], [y4], [ax, sc4])
    m4 = helper.make_model(
        g4, opset_imports=[helper.make_opsetid("", 17)], ir_version=8
    )
    s4 = ort.InferenceSession(
        m4.SerializeToString(), providers=["CPUExecutionProvider"]
    )
    out4 = s4.run(None, {"x4": test_in})[0]

    max_diff = float(np.max(np.abs(out3 - out4)))
    if max_diff > tolerance:
        raise ValueError(
            f"Numerical parity check failed for scale {scale_factor}: max_diff={max_diff:.6e} exceeds tolerance {tolerance}"
        )
    return max_diff


def patch_rvc_for_openvino_gpu(model_path: Path) -> tuple[bytes, float]:
    """In-memory ONNX patch: convert SineGen 3D Resize to 4D to satisfy OpenVINO GPU tensor rank requirements.

    Strictly identifies the SineGen 3D linear Resize node and resolves its scale factor from model initializers.
    Performs numerical parity verification before applying the patch. Raises ValueError if validation fails.
    """
    import onnx
    from onnx import helper, numpy_helper

    m = onnx.load(str(model_path), load_external_data=False)
    candidates = []
    for i, n in enumerate(m.graph.node):
        if n.op_type == "Resize" and any(
            a.name == "mode" and a.s in (b"linear", "linear") for a in n.attribute
        ):
            candidates.append((i, n))

    if not candidates:
        raise ValueError(f"No linear Resize node found in {model_path.name}")

    if len(candidates) > 1:
        m_source_candidates = [
            (i, n)
            for i, n in candidates
            if "m_source" in n.name.lower() or "sin_gen" in n.name.lower()
        ]
        if len(m_source_candidates) == 1:
            target_idx, target_node = m_source_candidates[0]
        else:
            raise ValueError(
                f"Multiple linear Resize nodes found in {model_path.name} ({[n.name for _, n in candidates]}); "
                f"could not unambiguously identify the SineGen pitch interpolation node."
            )
    else:
        target_idx, target_node = candidates[0]

    if len(target_node.input) < 3 or not target_node.input[2]:
        raise ValueError(
            f"Target Resize node '{target_node.name}' does not specify a scales input tensor."
        )

    orig_scales_name = target_node.input[2]
    scales_arr = None
    for init in m.graph.initializer:
        if init.name == orig_scales_name:
            scales_arr = numpy_helper.to_array(init)
            break

    if scales_arr is None:
        for n in m.graph.node:
            if n.op_type == "Constant" and orig_scales_name in n.output:
                for attr in n.attribute:
                    if attr.name == "value":
                        scales_arr = numpy_helper.to_array(attr.t)
                        break
                if scales_arr is not None:
                    break

    if scales_arr is None:
        raise ValueError(
            f"Could not resolve scales initializer or constant '{orig_scales_name}' for node '{target_node.name}'."
        )

    scales_flat = scales_arr.flatten()
    if len(scales_flat) != 3:
        raise ValueError(
            f"Expected 3D scale vector for node '{target_node.name}', but found shape {scales_arr.shape} ({scales_flat})."
        )

    if not (
        np.isclose(scales_flat[0], 1.0)
        and np.isclose(scales_flat[1], 1.0)
        and scales_flat[2] > 0
    ):
        raise ValueError(
            f"Invalid 3D scale vector {scales_flat} for node '{target_node.name}'; expected [1.0, 1.0, scale > 0]."
        )

    scale_factor = float(scales_flat[2])
    parity_diff = verify_3d_to_4d_resize_parity(scale_factor)

    orig_in = target_node.input[0]
    orig_out = target_node.output[0]

    axes_name = f"{target_node.name}_axes_dim2"
    axes_init = numpy_helper.from_array(np.array([2], dtype=np.int64), name=axes_name)
    m.graph.initializer.append(axes_init)

    scales_4d_name = f"{target_node.name}_scales_4d"
    scales_4d_init = numpy_helper.from_array(
        np.array([1.0, 1.0, 1.0, scale_factor], dtype=np.float32),
        name=scales_4d_name,
    )
    m.graph.initializer.append(scales_4d_init)

    unsqueeze_out = orig_in + "_unsqueeze_4d"
    unsqueeze_node = helper.make_node(
        "Unsqueeze",
        inputs=[orig_in, axes_name],
        outputs=[unsqueeze_out],
        name=target_node.name + "_unsqueeze4d",
    )

    resize_out_4d = orig_out + "_resize_4d"
    target_node.input[0] = unsqueeze_out
    target_node.input[2] = scales_4d_name
    target_node.output[0] = resize_out_4d

    squeeze_node = helper.make_node(
        "Squeeze",
        inputs=[resize_out_4d, axes_name],
        outputs=[orig_out],
        name=target_node.name + "_squeeze4d",
    )

    m.graph.node.insert(target_idx, unsqueeze_node)
    m.graph.node.insert(target_idx + 2, squeeze_node)

    onnx.checker.check_model(m)
    return m.SerializeToString(), parity_diff


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

    target_options = dict(target.provider_options)
    is_npu = (
        "NPU" in target.label.upper()
        or str(target_options.get("device_type", "")).upper() == "NPU"
        or (
            target.ep_device is not None
            and "NPU"
            in str(
                getattr(getattr(target.ep_device, "device", None), "type", "")
            ).upper()
        )
    )

    so = ort.SessionOptions()
    so.log_severity_level = 3  # Suppress driver diagnostic warnings
    # DirectML EP is heterogeneous by design and delegates certain scalar/indexing nodes
    # to the default CPU EP. Disabling CPU fallback prevents DirectML sessions from initializing.
    if target.provider_name not in ("CPUExecutionProvider", "DmlExecutionProvider"):
        so.add_session_config_entry("session.disable_cpu_ep_fallback", "1")

    if target.provider_name == "OpenVINOExecutionProvider":
        # Disabling ORT high-level graph optimizations allows OpenVINO's compiler
        # to ingest pristine model topology and manage native layer fusion.
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL

        # NPU requires static dimensions or bounded shapes. Set reshape_input
        # to match the benchmark analysis window samples.
        if is_npu and "reshape_input" not in target_options:
            reshape_spec = get_openvino_reshape_input(model_path, window_samples)
            if reshape_spec:
                target_options["reshape_input"] = reshape_spec
                print(
                    f"[OpenVINO NPU] Configured static shapes ({model_name}): {reshape_spec}",
                    file=sys.stderr,
                )

        # RVC float models contain mixed ops (ScatterNDUpdate in FP32 + Gather in FP16)
        # that cause OpenVINO GPU's auto-FP16 conversion to fail with element type mismatch.
        # OpenVINO GPU requires load_config with EXECUTION_MODE_HINT="ACCURACY" to prevent auto-FP16 downconversion.
        if model_name == "RVC" and "load_config" not in target_options:
            ov_dev = get_openvino_device_name(target)
            target_options["load_config"] = json.dumps(
                {ov_dev: {"EXECUTION_MODE_HINT": "ACCURACY"}}
            )

    model_data: str | bytes = str(model_path)
    if model_name == "RVC" and target.provider_name == "OpenVINOExecutionProvider":
        ov_dev = get_openvino_device_name(target)
        if ov_dev == "GPU":
            try:
                print(
                    "\n  [OpenVINO GPU] Applying in-memory 4D SineGen patch to satisfy GPU tensor rank limits...",
                    file=sys.stderr,
                    end="",
                    flush=True,
                )
                model_data, parity_diff = patch_rvc_for_openvino_gpu(model_path)
                print(
                    f" verified (parity max diff: {parity_diff:.2e})...",
                    file=sys.stderr,
                    end="",
                    flush=True,
                )
            except Exception as patch_e:  # noqa: BLE001
                err_msg = f"Failed to apply OpenVINO GPU 4D SineGen patch: {patch_e}"
                print(f"\n  [Error] {err_msg}", file=sys.stderr)
                result.error_message = err_msg
                return result

    result.provider_options = target_options
    target_options_str = {k: str(v) for k, v in target_options.items()}

    if "intra_op_num_threads" in target.provider_options:
        so.intra_op_num_threads = int(target.provider_options["intra_op_num_threads"])

    try:
        if target.ep_device is not None and hasattr(so, "add_provider_for_devices"):
            so.add_provider_for_devices([target.ep_device], target_options_str)
            session = ort.InferenceSession(
                model_data,
                sess_options=so,
            )
        else:
            session = ort.InferenceSession(
                model_data,
                sess_options=so,
                providers=[target.provider_name],
                provider_options=[target_options],
            )
    except Exception as e:  # noqa: BLE001
        err_msg = str(e)
        if target.provider_name == "OpenVINOExecutionProvider" and any(
            tok in err_msg
            for tok in ("same element type", "Type::merge", "element::Type")
        ):
            print(
                f"\n  [OpenVINO Recovery] Mixed-precision mismatch detected ({model_name}). Retrying with EXECUTION_MODE_HINT='ACCURACY'...",
                file=sys.stderr,
                end="",
                flush=True,
            )
            ov_dev = get_openvino_device_name(target)
            target_options["load_config"] = json.dumps(
                {ov_dev: {"EXECUTION_MODE_HINT": "ACCURACY"}}
            )
            result.provider_options = target_options
            target_options_str = {k: str(v) for k, v in target_options.items()}
            try:
                so_retry = ort.SessionOptions()
                so_retry.log_severity_level = 3
                if target.provider_name not in (
                    "CPUExecutionProvider",
                    "DmlExecutionProvider",
                ):
                    so_retry.add_session_config_entry(
                        "session.disable_cpu_ep_fallback", "1"
                    )
                so_retry.graph_optimization_level = (
                    ort.GraphOptimizationLevel.ORT_DISABLE_ALL
                )
                if "intra_op_num_threads" in target.provider_options:
                    so_retry.intra_op_num_threads = int(
                        target.provider_options["intra_op_num_threads"]
                    )
                if target.ep_device is not None and hasattr(
                    so_retry, "add_provider_for_devices"
                ):
                    so_retry.add_provider_for_devices(
                        [target.ep_device], target_options_str
                    )
                    session = ort.InferenceSession(model_data, sess_options=so_retry)
                else:
                    session = ort.InferenceSession(
                        model_data,
                        sess_options=so_retry,
                        providers=[target.provider_name],
                        provider_options=[target_options],
                    )
            except Exception as retry_e:  # noqa: BLE001
                result.error_message = (
                    f"Session creation failed (even with ACCURACY): {retry_e}"
                )
                return result
        else:
            if "interpolate.cpp" in err_msg or "linear_onnx" in err_msg:
                result.error_message = (
                    "OpenVINO Intel GPU plugin does not support 3D tensor 'linear_onnx' interpolation in RVC SineGen. "
                    "Use DirectML EP for Intel GPU execution on Windows."
                )
            else:
                result.error_message = f"Session creation failed: {e}"
            return result

    if hasattr(session, "disable_fallback"):
        session.disable_fallback()

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

        # Filter feed to match model's expected inputs
        model_input_names = {i.name for i in session.get_inputs()}
        feed = {k: v for k, v in feed.items() if k in model_input_names}

        # Filter output_names to match model's expected outputs
        model_output_names = [o.name for o in session.get_outputs()]
        if output_names:
            output_names = [
                o for o in output_names if o in model_output_names
            ] or model_output_names[:1]

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
        "--models",
        type=str,
        default=None,
        help="Comma-separated list of models to benchmark (e.g. FCPE,RMVPE,ContentVec,RVC)",
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
        "--skip-npu",
        action="store_true",
        help="Skip NPU execution provider targets",
    )
    parser.add_argument(
        "--allow-rvc-npu",
        action="store_true",
        help="Attempt compiling RVC on NPU (warning: HiFi-GAN compilation may take 15+ minutes or hang)",
    )
    parser.add_argument(
        "--providers",
        type=str,
        default=None,
        help="Comma-separated filter for target providers/devices (e.g. CPU,OpenVINO,CUDA,DML,NPU)",
    )
    parser.add_argument(
        "--ov-precision",
        type=str,
        default=None,
        choices=["FP32", "FP16", "f32", "f16"],
        help="Explicit precision override for OpenVINO Execution Provider (e.g. FP32)",
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
    if args.models:
        selected = {m.strip().upper() for m in args.models.split(",") if m.strip()}
        models = {k: v for k, v in models.items() if k.upper() in selected}

    # 3. Build target provider list
    providers_filter = (
        [p.strip() for p in args.providers.split(",")] if args.providers else None
    )
    targets = generate_benchmark_targets(
        hw_info,
        threads=args.threads,
        skip_npu=args.skip_npu,
        providers_filter=providers_filter,
    )
    if args.ov_precision:
        hint = (
            "ACCURACY"
            if args.ov_precision.upper() in ("FP32", "ACCURACY", "F32")
            else "PERFORMANCE"
        )
        for t in targets:
            if t.provider_name == "OpenVINOExecutionProvider":
                ov_dev = get_openvino_device_name(t)
                t.provider_options["load_config"] = json.dumps(
                    {ov_dev: {"EXECUTION_MODE_HINT": hint}}
                )

    # 4. Run benchmarks
    results_by_model: dict[str, list[BenchmarkResult]] = {}
    window_ms = (args.samples / 16000.0) * 1000.0

    for model_name, model_path in models.items():
        if not model_path:
            results_by_model[model_name] = []
            continue

        print(
            f"\n>>> Running benchmarks for: {model_name} ({model_path.name})",
            file=sys.stderr,
        )

        model_results: list[BenchmarkResult] = []
        for target in targets:
            is_target_npu = (
                "NPU" in target.label.upper()
                or str(target.provider_options.get("device_type", "")).upper() == "NPU"
                or (
                    target.ep_device is not None
                    and "NPU"
                    in str(
                        getattr(getattr(target.ep_device, "device", None), "type", "")
                    ).upper()
                )
            )

            print(
                f"  --> [{model_name}] Testing on {target.label}...",
                end="",
                flush=True,
                file=sys.stderr,
            )

            if model_name == "RVC" and is_target_npu and not args.allow_rvc_npu:
                print(
                    " [SKIPPED] (HiFi-GAN vocoder exceeds NPU compiler scheduling limits; pass --allow-rvc-npu to force)",
                    file=sys.stderr,
                )
                model_results.append(
                    BenchmarkResult(
                        model_name=model_name,
                        provider_name=target.label,
                        provider_options=target.provider_options,
                        active_providers=[],
                        success=False,
                        error_message="Skipped: RVC HiFi-GAN vocoder topology exceeds NPU SRAM compilation capacity (use --allow-rvc-npu to force).",
                    )
                )
                continue

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
            if res.success:
                print(
                    f" [OK] {res.mean_ms:.2f} ms (min: {res.min_ms:.2f} ms)",
                    file=sys.stderr,
                )
            else:
                print(f" [FAILED] ({res.error_message})", file=sys.stderr)

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
