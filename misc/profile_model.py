"""Profile inspector for ONNX Runtime models across execution providers."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def profile_model(
    model_path: Path,
    provider: str = "DmlExecutionProvider",
    runs: int = 5,
    samples: int = 4096,
) -> str:
    so = ort.SessionOptions()
    so.enable_profiling = True

    try:
        session = ort.InferenceSession(
            str(model_path), sess_options=so, providers=[provider]
        )
    except Exception as e:  # noqa: BLE001
        print(f"Session creation failed for {provider}: {e}", file=sys.stderr)
        return ""

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
    parser.add_argument("--runs", type=int, default=5, help="Number of inferences")
    args = parser.parse_args()

    profile_model(Path(args.model), provider=args.provider, runs=args.runs)
