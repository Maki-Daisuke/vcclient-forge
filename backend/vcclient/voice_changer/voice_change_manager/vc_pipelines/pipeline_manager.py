from ...data_types.slot_manager_data_types import SlotInfoMember
from .rvc_pipeline import RVCPipeline
from .vc_pipeline import VCPipeline


class PipelineManager:
    @classmethod
    def get_pipeline(cls, slot_info: SlotInfoMember) -> VCPipeline:
        if slot_info.voice_changer_type == "RVC":
            return RVCPipeline(slot_info)
        raise ValueError(f"Unknown voice changer type:{slot_info.voice_changer_type}")
