from .rvc_pipeline import RVCPipeline


class PipelineManager:
    def get_pipeline(cls=None, slot_info=None):

        if slot_info.voice_changer_type == "RVC":
            rvc_pipeline = RVCPipeline(slot_info)

            return rvc_pipeline

        raise ValueError(f"""Unknown voice changer type:{slot_info.voice_changer_type}""")

    get_pipeline = classmethod(get_pipeline)
