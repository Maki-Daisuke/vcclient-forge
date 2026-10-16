import logging

import numpy as np

from vcclient.const import LOGGER_NAME


class CrossfadeProcessor:
    crossfade_size = 0

    crossfade_offset = 0

    crossfade_end = 1

    np_prev_strength = np.array([0], dtype=np.float32)

    np_cur_strength = np.array([0], dtype=np.float32)

    np_prev_audio = np.array([0], dtype=np.float32)

    prev_rest_buffer = np.array([0], dtype=np.float32)

    def _generate_strength(self, crossfade_size: int, crossfade_offset: float, crossfade_end: float):

        self.crossfade_size = crossfade_size

        self.crossfade_offset = crossfade_offset

        self.crossfade_end = crossfade_end

        if crossfade_size <= 0:
            self.np_prev_strength = np.array([], dtype=np.float32)
            self.np_cur_strength = np.array([], dtype=np.float32)
            self.prev_rest_buffer = np.array([], dtype=np.float32)
            return

        cf_offset = int(crossfade_size * crossfade_offset)

        cf_end = int(crossfade_size * crossfade_end)

        cf_range = cf_end - cf_offset

        if cf_range <= 0:
            self.np_prev_strength = np.zeros(crossfade_size, dtype=np.float32)
            self.np_cur_strength = np.ones(crossfade_size, dtype=np.float32)
            self.prev_rest_buffer = np.zeros(crossfade_size, dtype=np.float32)
            return

        percent = np.arange(cf_range) / cf_range

        np_prev_strength = np.cos(percent * 0.5 * np.pi) ** 2

        np_cur_strength = np.cos((1 - percent) * 0.5 * np.pi) ** 2

        self.np_prev_strength = np.concatenate(
            [np.ones(cf_offset), np_prev_strength, np.zeros(crossfade_size - cf_offset - len(np_prev_strength))]
        )

        self.np_cur_strength = np.concatenate(
            [np.zeros(cf_offset), np_cur_strength, np.ones(crossfade_size - cf_offset - len(np_cur_strength))]
        )

        logging.getLogger(LOGGER_NAME).info(
            f"""Generated Strengths: for prev:{self.np_prev_strength.shape}, for cur:{self.np_cur_strength.shape}"""
        )

        self.prev_rest_buffer = np.zeros(crossfade_size, dtype=np.float32)

    def apply(
        self,
        audio_with_overlap_buffer: np.ndarray,
        output_audio_size: int,
        crossfade_size: int,
        crossfade_offset: float,
        crossfade_end: float,
        sola_search_frame: int,
    ):
        if crossfade_size <= 0:
            self.crossfade_size = 0
            self.prev_rest_buffer = np.array([], dtype=np.float32)
            if audio_with_overlap_buffer.shape[0] >= output_audio_size:
                return audio_with_overlap_buffer[-output_audio_size:].astype(np.float32)
            result = np.zeros(output_audio_size, dtype=np.float32)
            if audio_with_overlap_buffer.shape[0] > 0:
                result[-audio_with_overlap_buffer.shape[0] :] = audio_with_overlap_buffer
            return result

        if (
            self.crossfade_size != crossfade_size
            or self.crossfade_offset != crossfade_offset
            or self.crossfade_end != crossfade_end
        ):
            self._generate_strength(crossfade_size, crossfade_offset, crossfade_end)

        cor_nom = np.convolve(
            audio_with_overlap_buffer[: crossfade_size + sola_search_frame], np.flip(self.prev_rest_buffer), "valid"
        )
        cor_den = np.sqrt(
            np.convolve(
                audio_with_overlap_buffer[: crossfade_size + sola_search_frame] ** 2, np.ones(crossfade_size), "valid"
            )
            + 0.001
        )

        sola_offset = int(np.argmax(cor_nom / cor_den))
        sola_end = sola_offset + output_audio_size

        output_wav = audio_with_overlap_buffer[sola_offset:sola_end].astype(np.float32)
        output_wav[:crossfade_size] *= self.np_cur_strength
        output_wav[:crossfade_size] += self.prev_rest_buffer[:]
        result = output_wav

        if sola_offset < sola_search_frame:
            offset = -1 * (sola_search_frame + crossfade_size - sola_offset)
            end = -1 * (sola_search_frame - sola_offset)
            prev_rest_buffer_org = audio_with_overlap_buffer[offset:end]
            self.prev_rest_buffer = prev_rest_buffer_org * self.np_prev_strength
            return result

        self.prev_rest_buffer = audio_with_overlap_buffer[-crossfade_size:] * self.np_prev_strength
        return result
