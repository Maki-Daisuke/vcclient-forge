import json
import logging
from pathlib import Path
from typing import Any, cast

import onnxruntime

from .....const import LOGGER_NAME
from .....exception import (
    ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED,
    ERROR_CODE_RVC_INVALID_ONNX_MODEL,
    ERROR_CODE_RVC_INVALID_ONNX_MODEL_VERSION_VALUE,
    VCClientError,
)
from ....data_types.slot_manager_data_types import RVCSlotInfo
from ....voice_chanager_const import EmbedderType, InferencerType


def estimate_rvc_model(model_path: Path) -> RVCSlotInfo:
    if not model_path.exists():
        raise VCClientError(ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED, f"Model file not found: {model_path}")
    if model_path.suffix == ".onnx":
        return estimate_rvc_model_onnx(model_path)
    # .pth は推論対象外。PyTorch 推論は廃止済みで、.pth は import / 移行時に export_pth_to_onnx で ONNX 化してから渡す。
    logging.getLogger(LOGGER_NAME).error(f"input file: {model_path}")
    raise VCClientError(ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED, f"input file: {model_path}")


def estimate_rvc_model_onnx(model_path: Path) -> RVCSlotInfo:
    tmp_onnx_session = onnxruntime.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    modelmeta = tmp_onnx_session.get_modelmeta()
    input_shapes = []
    for input_node in tmp_onnx_session.get_inputs():
        input_shapes.append(input_node.shape)
    output_shapes = []
    for output_node in tmp_onnx_session.get_outputs():
        output_shapes.append(output_node.shape)
    try:
        metadata = json.loads(modelmeta.custom_metadata_map["metadata"])
        logging.getLogger(LOGGER_NAME).info(f"Trying to import onnx model: {metadata}")
        logging.getLogger(LOGGER_NAME).info(f"Input shapes: {input_shapes}")
        logging.getLogger(LOGGER_NAME).info(f"Output shapes: {output_shapes}")
        if metadata["version"] == "3.0":
            return onnx_v3_x(metadata, model_path)
        else:
            return onnx_v2_x(metadata, model_path)
    except Exception as e:
        logging.getLogger(LOGGER_NAME).error(f"Failed to load metadata: {e}")
        raise VCClientError(ERROR_CODE_RVC_INVALID_ONNX_MODEL, f"Failed to load metadata: {e}")


def onnx_v3_x(metadata: dict[str, Any], model_path: Path) -> RVCSlotInfo:
    if metadata["version"] == "3.0":
        version = "v3.0"
    else:
        logging.getLogger(LOGGER_NAME).error(f"Invalid onnx model version: {metadata['version']}")
        raise VCClientError(ERROR_CODE_RVC_INVALID_ONNX_MODEL_VERSION_VALUE, f"Invalid version: {metadata['version']}")

    is_f0 = True if metadata["f0"] == 1 else False
    inferencer_type: InferencerType = "onnxRVC" if metadata["f0"] == 1 else "onnxRVCNono"

    return RVCSlotInfo(
        slot_index=-1,
        name="",
        description="",
        credit="",
        terms_of_use_url="",
        icon_file=None,
        speakers={},
        model_file=Path(model_path.name),
        index_file=None,
        is_onnx=True,
        inferencer_type=inferencer_type,
        sample_rate=metadata["samplingRate"],
        is_f0=is_f0,
        deprecated=False,
        embedder=cast(EmbedderType, metadata["embedder"]),
        pitch_estimator="rmvpe",
        sample_id=None,
        version=version,
        chunk_sec=0.5,
        pitch_shift=0,
        index_ratio=0,
        protect_ratio=0.5,
    )


def onnx_v2_x(metadata: dict[str, Any], model_path: Path) -> RVCSlotInfo:
    embedder: EmbedderType
    if metadata["embChannels"] == 256 and metadata["embOutputLayer"] == 9 and metadata["useFinalProj"] is True:
        if metadata["embedder"] == "hubert-base-japanese":
            embedder = "hubert_base_japanese_l9fp"
        else:
            embedder = "hubert_base_l9fp"
    elif metadata["embChannels"] == 768 and metadata["embOutputLayer"] == 12 and metadata["useFinalProj"] is False:
        if metadata["embedder"] == "hubert-base-japanese":
            embedder = "hubert_base_japanese_l12"
        else:
            embedder = "hubert_base_l12"
    else:
        logging.getLogger(LOGGER_NAME).error(
            f"Invalid embedder: {metadata.get('embedder_name')}, emb_channels: {metadata.get('embChannels')}"
        )
        raise VCClientError(
            ERROR_CODE_RVC_INVALID_ONNX_MODEL,
            f"Invalid embedder: {metadata.get('embedder_name')}, emb_channels: {metadata.get('embChannels')}",
        )

    embedder_legacy = metadata["embedder"]
    logging.getLogger(LOGGER_NAME).info(f"Trying to import onnx model ---------- embedder_legacy: {embedder_legacy}")

    version = "v1"
    if metadata["embChannels"] == 256:
        if metadata["version"] == "2.1":
            version = "v1.1"
        elif metadata["version"] == "2.3":
            version = "v1.3"
        else:
            version = "v1"
    elif metadata["embChannels"] == 768:
        if metadata["version"] == "2":
            version = "v2"
        elif metadata["version"] == "2.1":
            version = "v2.1"
        elif metadata["version"] == "2.2":
            version = "v2.2"

    inferencer_type: InferencerType = "onnxRVC" if metadata["f0"] == 1 else "onnxRVCNono"
    is_f0 = True if metadata["f0"] == 1 else False

    return RVCSlotInfo(
        slot_index=-1,
        name="",
        description="",
        credit="",
        terms_of_use_url="",
        icon_file=None,
        speakers={},
        model_file=Path(model_path.name),
        index_file=None,
        is_onnx=True,
        inferencer_type=inferencer_type,
        sample_rate=metadata["samplingRate"],
        is_f0=is_f0,
        deprecated=False,
        embedder=embedder,
        pitch_estimator="rmvpe",
        sample_id=None,
        version=version,
        chunk_sec=0.5,
        pitch_shift=0,
        index_ratio=0,
        protect_ratio=0.5,
    )
