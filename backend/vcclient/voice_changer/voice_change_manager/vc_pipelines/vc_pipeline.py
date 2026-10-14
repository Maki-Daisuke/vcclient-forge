from abc import ABC, abstractmethod


class VCPipeline(ABC):
    def get_input_sample_rate(self=None):

        pass

    get_input_sample_rate = abstractmethod(get_input_sample_rate)

    def get_output_sample_rate(self=None):

        pass

    get_output_sample_rate = abstractmethod(get_output_sample_rate)

    def get_input_bitdepth(self):

        pass

    get_input_bitdepth = abstractmethod(get_input_bitdepth)

    def get_output_bitdepth(self):

        pass

    get_output_bitdepth = abstractmethod(get_output_bitdepth)

    def get_chunk_sec(self=None):

        pass

    get_chunk_sec = abstractmethod(get_chunk_sec)

    def needs_crossfade(self=None):

        pass

    needs_crossfade = abstractmethod(needs_crossfade)

    def get_pitch_estimator_type(self=None):

        pass

    get_pitch_estimator_type = abstractmethod(get_pitch_estimator_type)

    def get_gpu_device_id(self=None):

        pass

    get_gpu_device_id = abstractmethod(get_gpu_device_id)

    def set_pitch_estimator_type(self=None, pitch_estimator_type=None):

        pass

    set_pitch_estimator_type = abstractmethod(set_pitch_estimator_type)

    def get_pipeline_info(self=None):

        pass

    get_pipeline_info = abstractmethod(get_pipeline_info)

    def run(self=None, audio=None, real_crossfade_sec=abstractmethod):

        pass

    run = abstractmethod(run)
