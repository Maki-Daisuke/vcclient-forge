import numpy as np

from ...data_types.voice_changer_data_types import PipelineInfo
from ...slot_manager.slot_manager import SlotManager
from ...voice_chanager_const import (
    GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE,
)
from .vc_pipeline import VCPipeline


class BeatriceV2Pipeline(VCPipeline):
    def __init__(self=None, slot_info=None):

        pass

    # WARNING: Decompyle incomplete

    def get_input_sample_rate(self=None):

        return self.beatrice.IN_SAMPLE_RATE

    def get_output_sample_rate(self=None):

        return self.beatrice.OUT_SAMPLE_RATE

    def get_input_bitdepth(self):

        return np.float32

    def get_output_bitdepth(self):

        return np.float32

    def get_chunk_sec(self=None):

        return self.beatrice.IN_HOP_LENGTH / self.beatrice.IN_SAMPLE_RATE

    def needs_crossfade(self=None):

        return False

    def get_pitch_estimator_type(self=None):

        pass

    def get_gpu_device_id(self=None):

        return GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE

    def set_pitch_estimator_type(self=None, pitch_estimator_type=None):

        pass

    def check_and_update_merged_speaker_setting(self):

        slot_info = SlotManager.get_instance().get_slot_info(self.slot_index)

    # WARNING: Decompyle incomplete

    def _apply_merged_speaker_weights(self):

        pass

    # WARNING: Decompyle incomplete

    def run(self=None, audio=None, real_crossfade_sec=None):

        self.check_and_update_merged_speaker_setting()

        slot_info = SlotManager.get_instance().get_slot_info(self.slot_index)

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        if self.use_merged_speaker_embedding:
            pitch_shift = (
                slot_info.merged_speaker_pitch_shifts[slot_info.merged_speaker_id]
                if slot_info.merged_speaker_id < len(slot_info.merged_speaker_pitch_shifts)
                else 0
            )

            formant_shift = (
                slot_info.merged_speaker_formant_shifts[slot_info.merged_speaker_id]
                if slot_info.merged_speaker_id < len(slot_info.merged_speaker_formant_shifts)
                else 0
            )

        elif slot_info.dst_id < len(slot_info.pitch_shifts):
            pass

        pitch_shift = 0

        formant_shift = (
            slot_info.formant_shifts[slot_info.dst_id] if slot_info.dst_id < len(slot_info.formant_shifts) else 0
        )

        if formant_shift not in (2, 1.5, 1, 0.5, 0, -0.5, -1, -1.5, -2):
            formant_shift = 0

        auto_pitch_shift_calibration_times = 10

        need_calculate_source_average_pitch = False

        if slot_info.auto_pitch_shift == True:
            if self.source_average_pitch < 0:
                need_calculate_source_average_pitch = True

        (converted, source_average_pitch) = self.beatrice.convert_segment(
            audio[: self.beatrice.IN_HOP_LENGTH],
            slot_info.dst_id,
            pitch_shift,
            formant_shift,
            use_merged_speaker_embedding=self.use_merged_speaker_embedding,
            calculate_source_average_pitch=need_calculate_source_average_pitch,
        )

        if need_calculate_source_average_pitch == True:
            if len(self.source_pitch) < auto_pitch_shift_calibration_times:
                if source_average_pitch > 35 and source_average_pitch < 80:
                    self.source_pitch.append(source_average_pitch)

                return converted

            average_pitch = (
                None
                if len(self.source_pitch) < auto_pitch_shift_calibration_times and len(self.source_pitch) > 0
                else None
                if self.use_merged_speaker_embedding
                else slot_info.pitch_shifts[slot_info.dst_id](self.source_pitch) / len(self.source_pitch)
            )

            self.source_average_pitch = average_pitch

            self.source_pitch = []

        return converted

    def get_pipeline_info(self=None):

        return PipelineInfo(
            slot_index=self.slot_index,
            input_sample_rate=self.get_input_sample_rate(),
            output_sample_rate=self.get_output_sample_rate(),
            chunk_sec=self.get_chunk_sec(),
            slot_info=self.slot_info.model_dump(),
        )
