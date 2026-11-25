from collections.abc import Callable
from typing import Any

from vcclient.device import DeviceConfig
from vcclient.logger import logger

from ...data_types.slot_manager_data_types import SlotInfoMember
from .rvc_pipeline import RVCPipeline
from .vc_pipeline import VCPipeline


class PipelineManager:
    @classmethod
    def get_pipeline(
        cls,
        slot_info: SlotInfoMember,
        *,
        device: DeviceConfig | int | None = None,
        extra_frame_sec: float | None = None,
        snapshot_getter: Callable[[], Any] | None = None,
    ) -> VCPipeline:
        if slot_info.voice_changer_type == "RVC":
            if device is None and extra_frame_sec is None and snapshot_getter is None:
                pipeline = RVCPipeline(slot_info)
            else:
                pipeline = RVCPipeline(
                    slot_info,
                    device=device,
                    extra_frame_sec=extra_frame_sec,
                    snapshot_getter=snapshot_getter,
                )
            if snapshot_getter is not None:
                pipeline.warmup()
            else:
                cls.warmup(pipeline)
            return pipeline
        raise ValueError(f"Unknown voice changer type:{slot_info.voice_changer_type}")

    @staticmethod
    def warmup(pipeline: VCPipeline) -> None:
        if isinstance(pipeline, RVCPipeline):
            try:
                pipeline.warmup()
            except Exception as e:
                logger.warning("Pipeline warmup encountered an error (continuing anyway): %s", e)
