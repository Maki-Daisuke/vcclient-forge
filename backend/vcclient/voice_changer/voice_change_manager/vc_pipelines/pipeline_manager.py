from vcclient.logger import logger

from ...data_types.slot_manager_data_types import SlotInfoMember
from .rvc_pipeline import RVCPipeline
from .vc_pipeline import VCPipeline


class PipelineManager:
    @classmethod
    def get_pipeline(cls, slot_info: SlotInfoMember) -> VCPipeline:
        if slot_info.voice_changer_type == "RVC":
            pipeline = RVCPipeline(slot_info)
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
