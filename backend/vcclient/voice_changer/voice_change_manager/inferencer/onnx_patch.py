"""In-memory ONNX graph patch utilities for hardware accelerator compatibility."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import onnx
from onnx import helper, numpy_helper

from vcclient.logger import logger


def verify_3d_to_4d_resize_parity(scale_factor: float) -> float:
    """Validate numerical equivalence between 3D linear Resize and 4D Unsqueeze+Resize+Squeeze."""
    import onnxruntime as ort

    x_3d = np.linspace(-1.0, 1.0, 16, dtype=np.float32).reshape(1, 1, 16)

    # 1. 3D reference graph
    sc3_init = numpy_helper.from_array(np.array([1.0, 1.0, scale_factor], dtype=np.float32), name="sc3")
    r3 = helper.make_node(
        "Resize",
        ["x3", "", "sc3"],
        ["y3"],
        mode="linear",
        coordinate_transformation_mode="half_pixel",
    )
    g3 = helper.make_graph(
        [r3],
        "ref3d",
        [helper.make_tensor_value_info("x3", onnx.TensorProto.FLOAT, [1, 1, 16])],
        [helper.make_tensor_value_info("y3", onnx.TensorProto.FLOAT, [1, 1, None])],
        [sc3_init],
    )
    m3 = helper.make_model(g3, opset_imports=[helper.make_opsetid("", 18)], ir_version=9)

    # 2. 4D patched graph
    ax_init = numpy_helper.from_array(np.array([2], dtype=np.int64), name="ax")
    sc4_init = numpy_helper.from_array(np.array([1.0, 1.0, 1.0, scale_factor], dtype=np.float32), name="sc4")
    unsq = helper.make_node("Unsqueeze", ["x4", "ax"], ["x4_4d"])
    r4 = helper.make_node(
        "Resize",
        ["x4_4d", "", "sc4"],
        ["y4_4d"],
        mode="linear",
        coordinate_transformation_mode="half_pixel",
    )
    sq = helper.make_node("Squeeze", ["y4_4d", "ax"], ["y4"])
    g4 = helper.make_graph(
        [unsq, r4, sq],
        "patch4d",
        [helper.make_tensor_value_info("x4", onnx.TensorProto.FLOAT, [1, 1, 16])],
        [helper.make_tensor_value_info("y4", onnx.TensorProto.FLOAT, [1, 1, None])],
        [ax_init, sc4_init],
    )
    m4 = helper.make_model(g4, opset_imports=[helper.make_opsetid("", 18)], ir_version=9)

    so = ort.SessionOptions()
    so.log_severity_level = 3
    s3 = ort.InferenceSession(m3.SerializeToString(), so, providers=["CPUExecutionProvider"])
    s4 = ort.InferenceSession(m4.SerializeToString(), so, providers=["CPUExecutionProvider"])

    y3 = s3.run(None, {"x3": x_3d})[0]
    y4 = s4.run(None, {"x4": x_3d})[0]

    max_diff = float(np.max(np.abs(y3 - y4)))
    if max_diff > 1e-5:
        raise ValueError(f"3D-to-4D Resize transformation parity check failed (max diff: {max_diff} > 1e-5)")
    return max_diff


def patch_rvc_model_for_openvino(model_source: Path | str | bytes) -> bytes:
    """In-memory ONNX patch: convert SineGen 3D Resize to 4D to satisfy OpenVINO GPU tensor rank requirements.

    Strictly identifies the SineGen 3D linear Resize node and resolves its scale factor from model initializers.
    Returns the patched model bytes, or original bytes if no 3D linear Resize node is present (e.g. non-F0 models).
    """
    if isinstance(model_source, bytes):
        m = onnx.load_model_from_string(model_source)
        model_name = "in-memory-model"
    else:
        path = Path(model_source)
        model_name = path.name
        m = onnx.load(str(path), load_external_data=False)

    candidates = []
    for i, n in enumerate(m.graph.node):
        if n.op_type == "Resize" and any(a.name == "mode" and a.s in (b"linear", "linear") for a in n.attribute):
            candidates.append((i, n))

    if not candidates:
        logger.debug("No linear Resize node found in %s; skipping 4D patch.", model_name)
        if isinstance(model_source, bytes):
            return model_source
        with open(model_source, "rb") as f:
            return f.read()

    if len(candidates) > 1:
        m_source_candidates = [
            (i, n) for i, n in candidates if "m_source" in n.name.lower() or "sin_gen" in n.name.lower()
        ]
        if len(m_source_candidates) == 1:
            target_idx, target_node = m_source_candidates[0]
        else:
            logger.warning(
                "Multiple linear Resize nodes found in %s (%s); skipping 4D patch.",
                model_name,
                [n.name for _, n in candidates],
            )
            if isinstance(model_source, bytes):
                return model_source
            with open(model_source, "rb") as f:
                return f.read()
    else:
        target_idx, target_node = candidates[0]

    if len(target_node.input) < 3 or not target_node.input[2]:
        logger.warning("Target Resize node '%s' lacks scales input; skipping 4D patch.", target_node.name)
        if isinstance(model_source, bytes):
            return model_source
        with open(model_source, "rb") as f:
            return f.read()

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
        logger.warning(
            "Could not resolve scales initializer/constant '%s'; skipping 4D patch.",
            orig_scales_name,
        )
        if isinstance(model_source, bytes):
            return model_source
        with open(model_source, "rb") as f:
            return f.read()

    scales_flat = scales_arr.flatten()
    if len(scales_flat) != 3:
        # Already 4D or unexpected shape
        logger.debug(
            "Resize node '%s' scales shape is %s (not 3D); skipping 4D patch.", target_node.name, scales_arr.shape
        )
        if isinstance(model_source, bytes):
            return model_source
        with open(model_source, "rb") as f:
            return f.read()

    scale_factor = float(scales_flat[2])
    verify_3d_to_4d_resize_parity(scale_factor)

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
    logger.info("Successfully applied OpenVINO 4D SineGen patch to %s", model_name)
    return m.SerializeToString()


def patch_rmvpe_model_for_openvino(model_source: Path | str | bytes) -> bytes:
    """In-memory ONNX patch: supply explicit min bound for Clip nodes with empty min.

    OpenVINO's Intel GPU plugin has a compiler bug where an ONNX Clip node with an
    omitted/empty `min` input (e.g. `[data, "", max]`) incorrectly zeroes out all elements
    instead of clamping to `(-inf, max]`. In RMVPE (`modules/rmvpe/rmvpe_20231006.onnx`),
    the centroid mask clipping node `/rmvpe/Clip_1` uses `inputs=['/rmvpe/Add_1_output_0', '', '/rmvpe/Cast_7_output_0']`.
    Because `/rmvpe/Add_1_output_0` represents non-negative bin indices (ArgMax + 5 >= 5),
    setting `min = 0` is mathematically exact and unconstraining, preventing the kernel from
    zeroing out the centroid mask and restoring full pitch estimation fidelity.
    """
    if isinstance(model_source, bytes):
        m = onnx.load_model_from_string(model_source)
        model_name = "in-memory-model"
    else:
        path = Path(model_source)
        model_name = path.name
        m = onnx.load(str(path), load_external_data=False)

    patched_count = 0
    for node in m.graph.node:
        if node.op_type == "Clip" and len(node.input) >= 2 and node.input[1] == "":
            dtype: Any = np.int64
            if len(node.input) >= 3 and node.input[2]:
                max_name = node.input[2]
                for init in m.graph.initializer:
                    if init.name == max_name:
                        arr = numpy_helper.to_array(init)
                        dtype = arr.dtype
                        break

            min_name = f"{node.name}_min_zero"
            min_init = numpy_helper.from_array(np.array(0, dtype=dtype), name=min_name)
            m.graph.initializer.append(min_init)
            node.input[1] = min_name
            patched_count += 1

    if patched_count == 0:
        logger.debug("No Clip nodes with empty min found in %s; skipping patch.", model_name)
        if isinstance(model_source, bytes):
            return model_source
        with open(model_source, "rb") as f:
            return f.read()

    onnx.checker.check_model(m)
    logger.info("Successfully applied OpenVINO Clip fix patch (%s node(s)) to %s", patched_count, model_name)
    return m.SerializeToString()
