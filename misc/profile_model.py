"""Profile inspector for ONNX Runtime models across execution providers."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Ensure repository root and backend directory are in sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
if _REPO_ROOT.exists() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if _BACKEND_DIR.exists() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Initialize hardware accelerator runtime environment transparently
from vcclient.utils.runtime_env import setup_runtime_env

setup_runtime_env()

import numpy as np
import onnxruntime as ort

from misc.benchmark import get_openvino_reshape_input

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def profile_model(
    model_path: Path,
    provider: str = "DmlExecutionProvider",
    device: str = "GPU",
    runs: int = 5,
    samples: int = 4096,
) -> str:
    so = ort.SessionOptions()
    so.enable_profiling = True

    # 1. Trigger dynamic provider library discovery
    _ = ort.get_available_providers()

    # 2. Find matching ep_device if dynamic plugins are present (e.g. OpenVINO on Windows)
    matched_ep_device = None
    target_options: dict[str, str] = {}
    if hasattr(ort, "get_ep_devices"):
        raw_devs = list(ort.get_ep_devices())
        for d in raw_devs:
            ep_name = getattr(d, "ep_name", "")
            dev_type = str(getattr(getattr(d, "device", None), "type", "")).upper()
            ov_dev = ""
            if hasattr(d, "ep_metadata") and isinstance(d.ep_metadata, dict):
                ov_dev = str(d.ep_metadata.get("ov_device", "")).upper()
            elif hasattr(getattr(d, "device", None), "metadata") and isinstance(
                d.device.metadata, dict
            ):
                ov_dev = str(d.device.metadata.get("ov_device", "")).upper()

            # Check provider match
            name_match = (
                provider.lower() in ep_name.lower()
                or ep_name.lower() in provider.lower()
                or ("openvino" in provider.lower() and "openvino" in ep_name.lower())
                or ("dml" in provider.lower() and "dml" in ep_name.lower())
            )
            # Check device match
            device_match = (
                device.upper() in dev_type
                or device.upper() in ov_dev
                or (device.upper() == "GPU" and "AUTO" in ov_dev)
            )

            if name_match and device_match:
                matched_ep_device = d
                print(
                    f"[Info] Selected EP device: {ep_name} (type={dev_type}, ov_device={ov_dev or 'N/A'})"
                )
                break

    if "openvino" in provider.lower():
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL

    is_npu = device.upper() == "NPU" or (
        matched_ep_device
        and "NPU"
        in str(getattr(getattr(matched_ep_device, "device", None), "type", "")).upper()
    )
    if is_npu and "reshape_input" not in target_options:
        reshape_spec = get_openvino_reshape_input(model_path, samples)
        if reshape_spec:
            target_options["reshape_input"] = reshape_spec
            print(f"[OpenVINO NPU] Configured static shapes: {reshape_spec}")

    try:
        if matched_ep_device and hasattr(so, "add_provider_for_devices"):
            so.add_provider_for_devices([matched_ep_device], target_options)
            session = ort.InferenceSession(str(model_path), sess_options=so)
        else:
            if "openvino" in provider.lower():
                target_options["device_type"] = device.upper()
            session = ort.InferenceSession(
                str(model_path),
                sess_options=so,
                providers=[provider],
                provider_options=[target_options],
            )
    except Exception as e:  # noqa: BLE001
        print(f"Session creation failed for {provider}: {e}", file=sys.stderr)
        return ""

    active_providers = session.get_providers()
    print(f"Active providers: {active_providers}")
    if not any(
        provider.lower() in p.lower() or p.lower() in provider.lower()
        for p in active_providers
    ):
        print(
            f"[Warning] Silent fallback detected! Requested '{provider}' ({device}) but active is {active_providers}",
            file=sys.stderr,
        )

    inputs = session.get_inputs()
    feed = {}
    for inp in inputs:
        if inp.name in ("waveform", "audio"):
            if len(inp.shape) == 3:
                feed[inp.name] = np.random.randn(1, samples, 1).astype(np.float32)
            else:
                feed[inp.name] = np.random.randn(1, samples).astype(np.float32)
        elif inp.name == "threshold":
            feed[inp.name] = np.array([0.3], dtype=np.float32)
        elif inp.name == "feats":
            feed[inp.name] = np.random.randn(1, samples // 160, 256).astype(np.float32)
        elif inp.name == "p_len":
            feed[inp.name] = np.array([samples // 160], dtype=np.int64)
        elif inp.name == "pitch":
            feed[inp.name] = np.zeros((1, samples // 160), dtype=np.int64)
        elif inp.name == "pitchf":
            feed[inp.name] = np.zeros((1, samples // 160), dtype=np.float32)
        elif inp.name == "sid":
            feed[inp.name] = np.array([0], dtype=np.int64)
        else:
            shape = [d if isinstance(d, int) and d > 0 else 1 for d in inp.shape]
            feed[inp.name] = np.ones(
                shape, dtype=np.float32 if "float" in inp.type else np.int64
            )

    output_names = [o.name for o in session.get_outputs()]

    print(f"Running {runs} inferences on {provider} ({model_path.name})...")
    for _ in range(runs):
        session.run(output_names, feed)

    prof_file = session.end_profiling()
    with open(prof_file, "r", encoding="utf-8") as f:
        events = json.load(f)

    model_runs = [e for e in events if e.get("name") == "model_run"]
    print(f"\n=== 全 {len(model_runs)} 回の実行時間推移 ===")
    for i, r in enumerate(model_runs):
        dur_ms = r.get("dur", 0) / 1000.0
        label = (
            " (初回コールドスタート / シェーダー初期化)" if i == 0 else " (定常実行)"
        )
        print(f"  {i + 1} 回目: {dur_ms:6.2f} ms{label}")

    if model_runs:
        last_run = model_runs[-1]
        start_ts = last_run["ts"]
        end_ts = start_ts + last_run["dur"]
        last_nodes = [
            e for e in events if e.get("cat") == "Node" and start_ts <= e["ts"] < end_ts
        ]

        by_provider = Counter(e.get("args", {}).get("provider") for e in last_nodes)
        print(
            f"\n=== 最終回 ({last_run.get('dur', 0) / 1000.0:.2f} ms) のプロバイダ別ノード数 ==="
        )
        for p, cnt in by_provider.items():
            print(f"  {p}: {cnt} ノード")

        last_nodes.sort(key=lambda x: x.get("dur", 0), reverse=True)
        print("\n=== 最終回の遅いノード Top 10 ===")
        for i, n in enumerate(last_nodes[:10]):
            op = n.get("args", {}).get("op_name", "Unknown")
            dur = n.get("dur", 0) / 1000.0
            name = n.get("name", "")
            prov = n.get("args", {}).get("provider", "")
            print(f"  {i + 1:2d}. {dur:6.2f} ms | {prov:20s} | {op:15s} | {name}")

    print(f"\nChrome Tracing JSON: {prof_file}")
    return prof_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Profile ONNX Runtime model")
    parser.add_argument(
        "model",
        nargs="?",
        default="modules/rmvpe/rmvpe_20231006.onnx",
        help="Model path",
    )
    parser.add_argument(
        "--provider", default="DmlExecutionProvider", help="Execution provider"
    )
    parser.add_argument("--device", default="GPU", help="Target device (GPU, NPU, CPU)")
    parser.add_argument("--runs", type=int, default=5, help="Number of inferences")
    args = parser.parse_args()

    profile_model(
        Path(args.model),
        provider=args.provider,
        device=args.device,
        runs=args.runs,
    )
