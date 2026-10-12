import json
import logging
from pathlib import Path

import onnxruntime
import torch

from .....const import LOGGER_NAME
from .....exception import (
    ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED,
    ERROR_CODE_RVC_INVALID_CONFIG_LEGNTH,
    ERROR_CODE_RVC_INVALID_F0_VALUE,
    ERROR_CODE_RVC_INVALID_ONNX_MODEL,
    ERROR_CODE_RVC_INVALID_ONNX_MODEL_VERSION_VALUE,
    ERROR_CODE_RVC_INVALID_TORCH_MODEL,
    ERROR_CODE_RVC_INVALID_TORCH_MODEL_VERSION_VALUE,
    ERROR_CODE_RVC_UNKNOWN_EMBEDDER,
    VCClientError,
)
from ....data_types.slot_manager_data_types import RVCSlotInfo


def estimate_rvc_model(model_path: Path):
    assert model_path.exists(), f"Model file not found: {model_path}"
    if model_path.suffix == ".pth":
        return estimate_rvc_model_pytorch(model_path)
    elif model_path.suffix == ".onnx":
        return estimate_rvc_model_onnx(model_path)
    else:
        logging.getLogger(LOGGER_NAME).error(f"input file: {model_path}")
        raise VCClientError(ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED, f"input file: {model_path}")


def estimate_rvc_model_pytorch(model_path: Path):
    cpt = torch.load(model_path, map_location="cpu", weights_only=False)
    config_len = len(cpt["config"])
    version = cpt.get("version", "v1")
    if version is None:
        version = "v1"
    sample_rate = cpt["config"][-1]

    if config_len == 18:
        training_by = "official"
    elif config_len == 19:
        training_by = "ddpn"
    else:
        logging.getLogger(LOGGER_NAME).error(f"config_len:{config_len}")
        raise VCClientError(ERROR_CODE_RVC_INVALID_CONFIG_LEGNTH, f"config_len:{config_len}")

    if cpt["f0"] == 1:
        is_f0 = True
    elif cpt["f0"] == 0:
        is_f0 = False
    else:
        logging.getLogger(LOGGER_NAME).error(f"Invalid f0 value: {cpt['f0']}")
        raise VCClientError(ERROR_CODE_RVC_INVALID_F0_VALUE, f"Invalid f0 value: {cpt['f0']}")

    if version == "v1":
        torch_version = "v1"
    elif version == "v2":
        torch_version = "v2"
    else:
        logging.getLogger(LOGGER_NAME).error(f"Invalid torch version: {version}")
        raise VCClientError(ERROR_CODE_RVC_INVALID_TORCH_MODEL_VERSION_VALUE, f"Invalid torch version: {version}")

    if training_by == "official" and is_f0 is True and torch_version == "v1":
        inferencer_type = "pyTorchRVC"
        embedder = "hubert_base_l9fp"
    elif training_by == "official" and is_f0 is False and torch_version == "v1":
        inferencer_type = "pyTorchRVCNono"
        embedder = "hubert_base_l9fp"
    elif training_by == "official" and is_f0 is True and torch_version == "v2":
        inferencer_type = "pyTorchRVCv2"
        embedder = "hubert_base_l12"
    elif training_by == "official" and is_f0 is False and torch_version == "v2":
        inferencer_type = "pyTorchRVCv2Nono"
        embedder = "hubert_base_l12"
    elif training_by == "ddpn":
        inferencer_type = "pyTorchDDPN" if is_f0 is True else "pyTorchDDPNNono"
        emb_channels = cpt["config"][17]
        if cpt["embedder_name"] == "hubert_base" and emb_channels == 256:
            embedder = "hubert_base_l9fp"
        elif cpt["embedder_name"] == "contentvec" and emb_channels == 256:
            embedder = "hubert_base_l9fp"
        elif cpt["embedder_name"] == "hubert-base-japanese" and emb_channels == 256:
            embedder = "hubert_base_japanese_l9fp"
        elif cpt["embedder_name"] == "hubert_base" and emb_channels == 768:
            embedder = "hubert_base_l12"
        elif cpt["embedder_name"] == "contentvec" and emb_channels == 768:
            embedder = "hubert_base_l12"
        elif cpt["embedder_name"] == "hubert-base-japanese" and emb_channels == 768:
            embedder = "hubert_base_japanese_l12"
        else:
            logging.getLogger(LOGGER_NAME).error(
                f"Invalid embedder: {cpt['embedder_name']}, emb_channels: {emb_channels}"
            )
            raise VCClientError(
                ERROR_CODE_RVC_UNKNOWN_EMBEDDER,
                f"Invalid embedder: {cpt['embedder_name']}, emb_channels: {emb_channels}",
            )
    else:
        logging.getLogger(LOGGER_NAME).error(
            f"Invalid model: training_by {training_by}, is_f0 {is_f0}, torch_version {torch_version}"
        )
        raise VCClientError(
            ERROR_CODE_RVC_INVALID_TORCH_MODEL,
            f"Invalid model: training_by {training_by}, is_f0 {is_f0}, torch_version {torch_version}",
        )

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
        is_onnx=False,
        inferencer_type=inferencer_type,
        sample_rate=sample_rate,
        is_f0=is_f0,
        deprecated=False,
        embedder=embedder,
        pitch_estimator="rmvpe_onnx",
        sample_id=None,
        version=version,
        chunk_sec=0.5,
        pitch_shift=0,
        index_ratio=0,
        protect_ratio=0.5,
    )


def estimate_rvc_model_onnx(model_path: Path):
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


def onnx_v3_x(metadata: dict, model_path: Path):
    if metadata["version"] == "3.0":
        version = "v3.0"
    else:
        logging.getLogger(LOGGER_NAME).error(f"Invalid onnx model version: {metadata['version']}")
        raise VCClientError(ERROR_CODE_RVC_INVALID_ONNX_MODEL_VERSION_VALUE, f"Invalid version: {metadata['version']}")

    is_f0 = True if metadata["f0"] == 1 else False
    inferencer_type = "onnxRVC" if metadata["f0"] == 1 else "onnxRVCNono"

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
        embedder=metadata["embedder"],
        pitch_estimator="rmvpe_onnx",
        sample_id=None,
        version=version,
        chunk_sec=0.5,
        pitch_shift=0,
        index_ratio=0,
        protect_ratio=0.5,
    )


def onnx_v2_x(metadata: dict, model_path: Path):
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
            f"Invalid embedder: {metadata['embedder_name']}, emb_channels: {metadata['embChannels']}"
        )
        raise VCClientError(
            ERROR_CODE_RVC_INVALID_ONNX_MODEL,
            f"Invalid embedder: {metadata['embedder_name']}, emb_channels: {metadata['embChannels']}",
        )

    embedder_legacy = metadata["embedder"]
    logging.getLogger(LOGGER_NAME).info(f"Trying to import onnx model ---------- embedder_legacy: {embedder_legacy}")

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

    inferencer_type = "onnxRVC" if metadata["f0"] == 1 else "onnxRVCNono"
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
        pitch_estimator="rmvpe_onnx",
        sample_id=None,
        version=version,
        chunk_sec=0.5,
        pitch_shift=0,
        index_ratio=0,
        protect_ratio=0.5,
    )
