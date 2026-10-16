from abc import ABC, abstractmethod


class VCPipeline(ABC):
    @abstractmethod
    def get_input_sample_rate(self) -> int:
        pass

    @abstractmethod
    def get_output_sample_rate(self) -> int:
        pass

    @abstractmethod
    def get_input_bitdepth(self):
        pass

    @abstractmethod
    def get_output_bitdepth(self):
        pass

    @abstractmethod
    def get_chunk_sec(self) -> float:
        pass

    @abstractmethod
    def needs_crossfade(self) -> bool:
        pass

    @abstractmethod
    def get_pitch_estimator_type(self):
        pass

    @abstractmethod
    def get_gpu_device_id(self):
        pass

    @abstractmethod
    def set_pitch_estimator_type(self, pitch_estimator_type):
        pass

    @abstractmethod
    def get_pipeline_info(self):
        pass

    @abstractmethod
    def run(self, audio, real_crossfade_sec):
        pass
