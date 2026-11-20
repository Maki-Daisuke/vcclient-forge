from __future__ import annotations

from typing import Any

import onnxruntime


def resolve_cpu_provider() -> tuple[list[str], list[dict[str, Any]]]:
    """Return default CPUExecutionProvider configuration."""
    return (
        ["CPUExecutionProvider"],
        [
            {
                "intra_op_num_threads": 8,
                "execution_mode": onnxruntime.ExecutionMode.ORT_PARALLEL,
                "inter_op_num_threads": 8,
            }
        ],
    )
