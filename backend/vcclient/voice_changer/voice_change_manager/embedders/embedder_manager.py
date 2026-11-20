from __future__ import annotations

from vcclient.device import DeviceConfig
from vcclient.logger import logger

from ...module_manager import get_module_filepath
from ...voice_changer_const import EmbedderType
from .contentvec_onnx import ContentvecOnnx
from .embedder import Embedder


class EmbedderManager:
    @classmethod
    def get_embedder(
        cls,
        embedder_type: EmbedderType,
        device: DeviceConfig | int | None = None,
        *,
        device_id: DeviceConfig | int | None = None,
    ) -> Embedder:
        target = device if device is not None else (device_id if device_id is not None else 0)
        try:
            return cls.load_embedder(embedder_type, target)
        except Exception as e:
            logger.error("load embedder failed. %s", e)
            raise RuntimeError(f"{e}")

    @classmethod
    def load_embedder(
        cls,
        embedder_type: EmbedderType,
        device: DeviceConfig | int | None = None,
        *,
        device_id: DeviceConfig | int | None = None,
    ) -> Embedder:
        target = device if device is not None else (device_id if device_id is not None else 0)
        """
        hubert, hubert_jpはonnxモデルを使用する。torchはロードしない方針。
        """
        if embedder_type == "hubert_base_l9fp":
            file = get_module_filepath("contentvec-f.onnx")
            return ContentvecOnnx().load_model(file, target, 9, embedder_type=embedder_type)
        elif embedder_type == "hubert_base_l12":
            file = get_module_filepath("contentvec-f.onnx")
            return ContentvecOnnx().load_model(file, target, 12, embedder_type=embedder_type)
        elif embedder_type == "hubert_base_japanese_l9fp":
            file = get_module_filepath("rinna_hubert_base-f.onnx")
            return ContentvecOnnx().load_model(file, target, 9, embedder_type=embedder_type)
        elif embedder_type == "hubert_base_japanese_l12":
            file = get_module_filepath("rinna_hubert_base-f.onnx")
            return ContentvecOnnx().load_model(file, target, 12, embedder_type=embedder_type)
        else:
            raise RuntimeError(f"Unknown Embedder {embedder_type}")
