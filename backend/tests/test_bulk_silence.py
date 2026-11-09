from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from vcclient.voice_changer.data_types.data_types import PerformanceData
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


@pytest.mark.parametrize(
    ("output_values", "monitor_values", "input_rate", "input_size", "expected_output", "expected_monitor"),
    [
        # Two 100 ms silent chunks are retained, then silence is skipped; sound resets the delay.
        ([0, 0, 0, 1, 0, 0, 0], [0, 0, 0, 1, 0, 0, 0], 10, 1, [0, 1, 3, 4, 5], [0, 1, 3, 4, 5]),
        # The main and monitor streams track silence independently.
        ([0, 0, 0, 0, 0], [0, 1, 0, 0, 0], 10, 1, [0, 1], [0, 1, 2, 3]),
        # A whole chunk crossing 200 ms is retained.
        ([0, 0, 0], [0, 0, 0], 20, 3, [0, 1], [0, 1]),
        # Even very small nonzero samples reset the timer.
        ([0, 0, 0.000001, 0, 0, 0], [0, 0, 0.000001, 0, 0, 0], 10, 1, [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]),
    ],
)
def test_worker_delays_silence_skipping(
    output_values, monitor_values, input_rate, input_size, expected_output, expected_monitor
):
    voice_changer = VoiceChanger.__new__(VoiceChanger)
    voice_changer.bulk_process = None
    voice_changer.vc_info = SimpleNamespace(bulk_process_start_flag=True)
    voice_changer.input_sample_rate = input_rate
    voice_changer.convert_chunk_bulk_queue_in = Queue()
    voice_changer.convert_chunk_bulk_queue_out = Queue()
    voice_changer.convert_chunk_bulk_queue_monitor = Queue()
    output_queue = voice_changer.convert_chunk_bulk_queue_out
    monitor_queue = voice_changer.convert_chunk_bulk_queue_monitor
    for _ in output_values:
        voice_changer.convert_chunk_bulk_queue_in.put(np.ones(input_size))
    index = 0

    def convert(_waveform):
        nonlocal index
        output = np.array([output_values[index]])
        monitor = np.array([monitor_values[index]])
        performance = PerformanceData(elapsed_time=float(index))
        index += 1
        if index == len(output_values):
            voice_changer.vc_info.bulk_process_start_flag = False
        return output, monitor, performance

    voice_changer.convert_chunk = convert
    voice_changer.convert_chunk_bulk_internal()

    # Performance metadata is delivered for all chunks, including skipped audio.
    for index, value in enumerate(output_values):
        audio, performance = output_queue.get_nowait()
        assert performance.elapsed_time == float(index)
        if index in expected_output:
            np.testing.assert_array_equal(audio, [value])
        else:
            assert audio is None
    assert output_queue.empty()
    for index in expected_monitor:
        audio, performance = monitor_queue.get_nowait()
        np.testing.assert_array_equal(audio, [monitor_values[index]])
        assert performance.elapsed_time == float(index)
    assert monitor_queue.empty()


def test_metadata_only_entry_keeps_performance_without_audio():
    voice_changer = VoiceChanger.__new__(VoiceChanger)
    voice_changer.bulk_process = None
    voice_changer.vc_info = SimpleNamespace(bulk_process_start_flag=True, monitor_enabled=False)
    voice_changer.waveform_rest = np.array([], dtype=np.float32)
    voice_changer.input_sample_rate = 1
    voice_changer.vc_pipeline = MagicMock()
    voice_changer.vc_pipeline.get_chunk_sec.return_value = 1
    voice_changer.convert_chunk_bulk_queue_in = Queue()
    voice_changer.convert_chunk_bulk_queue_out = Queue()
    voice_changer.convert_chunk_bulk_queue_monitor = Queue()
    voice_changer.convert_chunk_bulk_queue_out.put((None, PerformanceData(elapsed_time=2.0)))

    output, monitor, performance = voice_changer.convert_chunk_bulk(np.ones(1, dtype=np.float32))

    assert output is None
    assert monitor is None
    assert performance is not None
    assert performance.elapsed_time == 2.0
