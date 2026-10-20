from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from vcclient.exception import ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED, VCClientError
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


def _voice_changer_without_pipeline() -> VoiceChanger:
    voice_changer = VoiceChanger.__new__(VoiceChanger)
    voice_changer.vc_info = SimpleNamespace(bulk_process_start_flag=True, monitor_enabled=False)
    voice_changer.waveform_rest = np.array([], dtype=np.float32)
    voice_changer.input_sample_rate = 1
    voice_changer.vc_pipeline = None
    voice_changer._check_reload_model_is_required_and_update = MagicMock()
    voice_changer._check_and_update_pitch_estimator = MagicMock()
    voice_changer._check_and_update_sample_rate = MagicMock()
    voice_changer._check_and_update_filter = MagicMock()
    return voice_changer


def test_convert_chunk_bulk_reports_missing_pipeline():
    voice_changer = _voice_changer_without_pipeline()

    try:
        with pytest.raises(VCClientError) as exc_info:
            voice_changer.convert_chunk_bulk(np.ones(1, dtype=np.float32))
    finally:
        voice_changer.vc_info.bulk_process_start_flag = False

    assert exc_info.value.info.code == ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED


def test_stop_convert_chunk_bulk_without_worker_thread():
    voice_changer = _voice_changer_without_pipeline()
    voice_changer.bulk_process = None

    voice_changer.stop_convert_chunk_bulk()

    assert voice_changer.vc_info.bulk_process_start_flag is False
