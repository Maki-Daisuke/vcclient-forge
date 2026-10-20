from abc import ABC, abstractmethod

import numpy as np

from ...data_types.voice_changer_data_types import PipelineInfoMember
from ...voice_chanager_const import PitchEstimatorType


class VCPipeline(ABC):
    @abstractmethod
    def get_input_sample_rate(self) -> int:
        pass

    @abstractmethod
    def get_output_sample_rate(self) -> int:
        pass

    @abstractmethod
    def get_input_bitdepth(self) -> type[np.generic]:
        pass

    @abstractmethod
    def get_output_bitdepth(self) -> type[np.generic]:
        pass

    @abstractmethod
    def get_chunk_sec(self) -> float:
        pass

    @abstractmethod
    def needs_crossfade(self) -> bool:
        pass

    @abstractmethod
    def get_pitch_estimator_type(self) -> PitchEstimatorType:
        pass

    @abstractmethod
    def get_gpu_device_id(self) -> int:
        pass

    @abstractmethod
    def set_pitch_estimator_type(self, pitch_estimator_type: PitchEstimatorType) -> None:
        pass

    @abstractmethod
    def get_pipeline_info(self) -> PipelineInfoMember:
        pass

    @abstractmethod
    def run(self, audio: np.ndarray, real_crossfade_sec: float) -> np.ndarray:
        pass
