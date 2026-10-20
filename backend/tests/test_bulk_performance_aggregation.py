from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from vcclient.voice_changer.data_types.data_types import PerformanceData
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


def test_bulk_performance_average_uses_only_measured_chunks():
    voice_changer = VoiceChanger.__new__(VoiceChanger)
    voice_changer.vc_info = SimpleNamespace(bulk_process_start_flag=True, monitor_enabled=False)
    voice_changer.waveform_rest = np.array([], dtype=np.float32)
    voice_changer.input_sample_rate = 1
    voice_changer.vc_pipeline = MagicMock()
    voice_changer.vc_pipeline.get_chunk_sec.return_value = 1
    voice_changer.convert_chunk_bulk_queue_in = Queue()
    voice_changer.convert_chunk_bulk_queue_out = Queue()
    voice_changer.convert_chunk_bulk_queue_monitor = Queue()
    voice_changer._check_reload_model_is_required_and_update = MagicMock()
    voice_changer._check_and_update_pitch_estimator = MagicMock()
    voice_changer._check_and_update_sample_rate = MagicMock()
    voice_changer._check_and_update_filter = MagicMock()

    measured = PerformanceData(elapsed_time=2.0, data_num=1)
    voice_changer.convert_chunk_bulk_queue_out.put((np.ones(1, dtype=np.float32), measured))
    voice_changer.convert_chunk_bulk_queue_out.put((np.ones(1, dtype=np.float32), None))

    try:
        _, _, performance_data = voice_changer.convert_chunk_bulk(np.ones(1, dtype=np.float32))
    finally:
        voice_changer.vc_info.bulk_process_start_flag = False

    assert performance_data is not None
    assert performance_data.elapsed_time == 2.0
    assert performance_data.data_num == 1
