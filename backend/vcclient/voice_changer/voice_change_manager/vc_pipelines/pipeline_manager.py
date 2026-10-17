from .rvc_pipeline import RVCPipeline


class PipelineManager:
    @classmethod
    def get_pipeline(cls, slot_info=None):
        if slot_info.voice_changer_type == "RVC":
            return RVCPipeline(slot_info)

        raise ValueError(f"Unknown voice changer type:{slot_info.voice_changer_type}")
