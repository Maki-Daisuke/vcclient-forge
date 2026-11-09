from __future__ import annotations

from vcclient.device import DeviceConfig
from vcclient.logger import logger

from ...module_manager import get_module_filepath
from ...voice_changer_const import EmbedderType
from .contentvec_onnx import ContentvecOnnx
from .embedder import Embedder


class EmbedderManager:
    current_embedder: Embedder | None = None

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
            cls.current_embedder = cls.load_embedder(embedder_type, target)
            return cls.current_embedder
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
            return ContentvecOnnx().load_model(file, target, 9, True)
        elif embedder_type == "hubert_base_l12":
            file = get_module_filepath("contentvec-f.onnx")
            return ContentvecOnnx().load_model(file, target, 12, False)
        elif embedder_type == "hubert_base_japanese_l9fp":
            file = get_module_filepath("rinna_hubert_base-f.onnx")
            return ContentvecOnnx().load_model(file, target, 9, True)
        elif embedder_type == "hubert_base_japanese_l12":
            file = get_module_filepath("rinna_hubert_base-f.onnx")
            return ContentvecOnnx().load_model(file, target, 12, False)
        elif embedder_type in (
            "applio_japanese_hubert_base_l12",
            "applio_chinese_hubert_base_l12",
            "applio_korean_hubert_base_l12",
        ):
            raise RuntimeError(
                f"Applio embedder '{embedder_type}' with PyTorch format is not supported in pure-ONNX runtime."
            )
        else:
            raise RuntimeError(f"Unknown Embedder {embedder_type}")
