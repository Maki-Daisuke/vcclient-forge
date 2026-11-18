from queue import Queue
from types import SimpleNamespace

import numpy as np
import pytest

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
        index += 1
        if index == len(output_values):
            voice_changer.vc_info.bulk_process_start_flag = False
        return output, monitor

    voice_changer.convert_chunk = convert
    voice_changer.convert_chunk_bulk_internal()

    for index in expected_output:
        audio = output_queue.get_nowait()
        np.testing.assert_array_equal(audio, [output_values[index]])
    assert output_queue.empty()
    for index in expected_monitor:
        audio = monitor_queue.get_nowait()
        np.testing.assert_array_equal(audio, [monitor_values[index]])
    assert monitor_queue.empty()
