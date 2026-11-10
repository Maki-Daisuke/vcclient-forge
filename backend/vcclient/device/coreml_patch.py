"""In-memory ONNX graph patch utilities for CoreML accelerator compatibility on Apple Silicon."""

from __future__ import annotations

import math
from pathlib import Path

import onnx

from vcclient.logger import logger

COREML_CONV_MEMORY_LIMIT = 16384


def calculate_target_feats_length(
    chunk_sec: float,
    crossfade_sec: float = 0.05,
    extra_frame_sec: float = 0.34,
    sola_search_frame_sec: float = 0.012,
) -> int:
    """Calculate the exact feature frame length (feats.shape[1]) produced by RVCPipeline._generate_inputs."""
    new_frame_size = int(round(chunk_sec * 16000))
    crossfade_overlap_size = int(round(min(chunk_sec, crossfade_sec) * 16000))
    sola_search_frame_size = int(round(sola_search_frame_sec * 16000))
    extra_frame_size = int(round(extra_frame_sec * 16000))

    convert_size = new_frame_size + crossfade_overlap_size + sola_search_frame_size + extra_frame_size
    embedder_hop_size = 160
    hop_mod = convert_size % embedder_hop_size
    if hop_mod != 0:
        convert_size = convert_size + (embedder_hop_size - hop_mod)

    c_len = (convert_size - 80) // 320
    upscaled = c_len * 2
    npy_offset = math.floor(extra_frame_sec * 16000) // 360
    return upscaled - npy_offset * 2


def patch_rvc_model_for_coreml(
    model_source: Path | str | bytes,
    target_frames: int,
) -> bytes:
    """In-memory ONNX patch: set static input shapes for RVC model inputs to enable CoreML MLProgram execution."""
    if isinstance(model_source, bytes):
        m = onnx.load_model_from_string(model_source)
        model_name = "in-memory-model"
    else:
        path = Path(model_source)
        model_name = path.name
        m = onnx.load(str(path), load_external_data=False)

    for inp in m.graph.input:
        if inp.name in ("feats", "pitch", "pitchf"):
            for dim_idx, dim in enumerate(inp.type.tensor_type.shape.dim):
                if dim_idx == 0:
                    dim.dim_value = 1
                    dim.ClearField("dim_param")
                elif dim_idx == 1:
                    dim.dim_value = target_frames
                    dim.ClearField("dim_param")
        elif inp.name in ("p_len", "sid"):
            dim = inp.type.tensor_type.shape.dim[0]
            dim.dim_value = 1
            dim.ClearField("dim_param")

    logger.info(
        "Patched RVC model %s with static shape target_frames=%s for CoreML MLProgram", model_name, target_frames
    )
    return m.SerializeToString()
