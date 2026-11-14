import time
from queue import Queue
from types import SimpleNamespace

import numpy as np
import pytest

from vcclient.voice_changer.configuration_manager.configuration_manager import (
    ConfigurationManager,
)
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import (
    LocalVoiceChangerInterface,
)


def test_audio_output_callback_zero_fills_when_queue_empty(monkeypatch):
    """Verify that audio_output_callback fills outdata with zeros and returns immediately

    when the output queue is empty.
    """
    ConfigurationManager.get_instance()
    interface = LocalVoiceChangerInterface.get_instance()
    empty_queue = Queue()
    monkeypatch.setattr(interface, "out_queue", empty_queue)
    monkeypatch.setattr(interface, "split_length", 1)

    # Initialize outdata with non-zero garbage values
    outdata = np.full((480, 2), 999.0, dtype=np.float32)

    start = time.perf_counter()
    interface.audio_output_callback(outdata, 480, None, None)
    elapsed = time.perf_counter() - start

    # Must be non-blocking (much less than the old 100ms timeout)
    assert elapsed < 0.05
    # Must be filled with zeros (silence)
    assert np.all(outdata == 0)


def test_audio_monitor_callback_zero_fills_when_queue_empty(monkeypatch):
    """Verify that audio_monitor_callback fills outdata with zeros and returns immediately

    when the monitor queue is empty.
    """
    ConfigurationManager.get_instance()
    interface = LocalVoiceChangerInterface.get_instance()
    empty_queue = Queue()
    monkeypatch.setattr(interface, "monitor_queue", empty_queue)
    monkeypatch.setattr(interface, "split_length", 1)

    outdata = np.full((480, 2), 999.0, dtype=np.float32)

    start = time.perf_counter()
    interface.audio_monitor_callback(outdata, 480, None, None)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.05
    assert np.all(outdata == 0)


def test_audio_output_callback_copies_data_when_available(monkeypatch):
    """Verify that audio_output_callback properly copies queued audio to outdata."""
    interface = LocalVoiceChangerInterface.get_instance()
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    monkeypatch.setattr(conf, "audio_output_device_gain", 1.0)
    q = Queue()
    dummy_wav = np.full(480, 0.5, dtype=np.float32)
    q.put(dummy_wav)

    monkeypatch.setattr(interface, "out_queue", q)
    monkeypatch.setattr(interface, "split_length", 1)

    outdata = np.zeros((480, 2), dtype=np.float32)
    interface.audio_output_callback(outdata, 480, None, None)

    assert outdata.shape == (480, 2)
    # Check that gain is applied and values match
    assert np.allclose(outdata[:, 0], 0.5)
    assert np.allclose(outdata[:, 1], 0.5)


def test_audio_output_callback_truncation_is_bounded(monkeypatch):
    """Verify that truncation loop is bounded by initial qsize and does not run infinitely

    even if items are continuously pushed during reading.
    """
    interface = LocalVoiceChangerInterface.get_instance()
    q = Queue()
    dummy_wav = np.full(480, 0.5, dtype=np.float32)

    # Initial 8 items (exceeding split_length 1 + buffer 3 = 4)
    for _ in range(8):
        q.put(dummy_wav)

    monkeypatch.setattr(interface, "out_queue", q)
    monkeypatch.setattr(interface, "split_length", 1)

    # Wrap get_nowait to inject new items during truncation
    original_get_nowait = q.get_nowait
    get_count = 0

    def injecting_get_nowait():
        nonlocal get_count
        get_count += 1
        q.put(dummy_wav)
        return original_get_nowait()

    monkeypatch.setattr(q, "get_nowait", injecting_get_nowait)

    outdata = np.zeros((480, 2), dtype=np.float32)
    interface.audio_output_callback(outdata, 480, None, None)

    # Must process exactly the initial 8 items, NOT loop forever or process injected items
    assert get_count == 8


def test_audio_monitor_callback_truncation_is_bounded(monkeypatch):
    """Verify that monitor truncation loop is bounded by initial qsize."""
    interface = LocalVoiceChangerInterface.get_instance()
    q = Queue()
    dummy_wav = np.full(480, 0.5, dtype=np.float32)

    for _ in range(8):
        q.put(dummy_wav)

    monkeypatch.setattr(interface, "monitor_queue", q)
    monkeypatch.setattr(interface, "split_length", 1)

    original_get_nowait = q.get_nowait
    get_count = 0

    def injecting_get_nowait():
        nonlocal get_count
        get_count += 1
        q.put(dummy_wav)
        return original_get_nowait()

    monkeypatch.setattr(q, "get_nowait", injecting_get_nowait)

    outdata = np.zeros((480, 2), dtype=np.float32)
    interface.audio_monitor_callback(outdata, 480, None, None)

    assert get_count == 8


def _drain_queue(queue: Queue[np.ndarray]) -> list[np.ndarray]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _setup_preroll_interface(monkeypatch, chunk_sec: float, block_size: int = 8):
    conf = SimpleNamespace(audio_input_device_gain=1.0, realtime_output_status_enabled=False)
    monkeypatch.setattr(
        "vcclient.voice_changer.voice_change_manager.local_voice_changer_interface.ConfigurationManager.get_instance",
        lambda: SimpleNamespace(get_voice_changer_configuration=lambda: conf),
    )
    interface = LocalVoiceChangerInterface()
    interface.output_block_size = block_size
    interface.monitor_block_size = block_size
    interface.vc_chunk_sec = chunk_sec
    interface.vc = SimpleNamespace(vc_chunk_sec=chunk_sec)
    return interface, block_size


@pytest.mark.parametrize(
    ("chunk_sec", "expected_preroll_blocks"),
    [
        (0.05, 2),
        (0.1, 2),
        (0.2, 2),
        (0.3, 3),
        (0.5, 5),
    ],
)
def test_audio_input_callback_inserts_relative_preroll_on_start_and_silence_resumption(
    monkeypatch, chunk_sec: float, expected_preroll_blocks: int
):
    interface, block_size = _setup_preroll_interface(monkeypatch, chunk_sec)
    speech_chunk = np.full(block_size, 0.25, dtype=np.float32)
    silent_chunk = np.zeros(block_size, dtype=np.float32)
    resumed_chunk = np.full(block_size, 0.5, dtype=np.float32)
    responses = iter(
        [
            (speech_chunk, speech_chunk, None),
            (silent_chunk, silent_chunk, None),
            (None, None, None),
            (resumed_chunk, resumed_chunk, None),
        ]
    )
    interface.vc.convert_chunk_bulk = lambda _indata: next(responses)
    indata = np.zeros((block_size, 1), dtype=np.float32)

    # Initial speech chunk receives relative preroll on both main and monitor queues.
    interface.audio_input_callback(indata, block_size, None, None)
    main_blocks = _drain_queue(interface.out_queue)
    monitor_blocks = _drain_queue(interface.monitor_queue)
    assert len(main_blocks) == expected_preroll_blocks + 1
    assert len(monitor_blocks) == expected_preroll_blocks + 1
    assert all(np.all(block == 0) for block in main_blocks[:expected_preroll_blocks])
    assert all(np.all(block == 0) for block in monitor_blocks[:expected_preroll_blocks])
    np.testing.assert_array_equal(main_blocks[-1], speech_chunk)
    np.testing.assert_array_equal(monitor_blocks[-1], speech_chunk)

    # Silence drains and skipped chunks re-arm preroll for the next speech chunk.
    interface.audio_input_callback(indata, block_size, None, None)
    _drain_queue(interface.out_queue)
    _drain_queue(interface.monitor_queue)
    interface.audio_input_callback(indata, block_size, None, None)
    interface.audio_input_callback(indata, block_size, None, None)

    resumed_main = _drain_queue(interface.out_queue)
    resumed_monitor = _drain_queue(interface.monitor_queue)
    assert len(resumed_main) == expected_preroll_blocks + 1
    assert len(resumed_monitor) == expected_preroll_blocks + 1
    assert all(np.all(block == 0) for block in resumed_main[:expected_preroll_blocks])
    assert all(np.all(block == 0) for block in resumed_monitor[:expected_preroll_blocks])
    np.testing.assert_array_equal(resumed_main[-1], resumed_chunk)
    np.testing.assert_array_equal(resumed_monitor[-1], resumed_chunk)


def test_audio_input_callback_skips_preroll_during_mid_speech_underrun(monkeypatch):
    interface, block_size = _setup_preroll_interface(monkeypatch, chunk_sec=0.5)
    chunk_a = np.full(block_size, 0.3, dtype=np.float32)
    chunk_b = np.full(block_size, 0.4, dtype=np.float32)
    chunk_c = np.full(block_size, 0.6, dtype=np.float32)
    responses = iter(
        [
            (chunk_a, chunk_a, None),
            (None, None, None),
            (chunk_b, chunk_b, None),
            (chunk_c, chunk_c, None),
        ]
    )
    interface.vc.convert_chunk_bulk = lambda _indata: next(responses)
    indata = np.zeros((block_size, 1), dtype=np.float32)

    interface.audio_input_callback(indata, block_size, None, None)
    _drain_queue(interface.out_queue)
    _drain_queue(interface.monitor_queue)

    # Empty worker poll followed by ongoing speech chunks must not prepend silence.
    for expected in (None, chunk_b, chunk_c):
        interface.audio_input_callback(indata, block_size, None, None)
        main_blocks = _drain_queue(interface.out_queue)
        monitor_blocks = _drain_queue(interface.monitor_queue)
        if expected is None:
            assert main_blocks == []
            assert monitor_blocks == []
        else:
            assert len(main_blocks) == 1
            assert len(monitor_blocks) == 1
            np.testing.assert_array_equal(main_blocks[0], expected)
            np.testing.assert_array_equal(monitor_blocks[0], expected)


@pytest.mark.parametrize(
    ("chunk_sec", "remaining_silent_blocks", "expected_total_silent_blocks"),
    [
        (0.1, 1, 2),
        (0.5, 2, 5),
        (0.5, 5, 5),
    ],
)
def test_audio_input_callback_tops_up_partial_preroll_shortfall_only(
    monkeypatch, chunk_sec: float, remaining_silent_blocks: int, expected_total_silent_blocks: int
):
    interface, block_size = _setup_preroll_interface(monkeypatch, chunk_sec)
    speech_chunk = np.full(block_size, 0.25, dtype=np.float32)
    silent_chunk = np.zeros(block_size * remaining_silent_blocks, dtype=np.float32)
    resumed_chunk = np.full(block_size, 0.75, dtype=np.float32)
    responses = iter(
        [
            (speech_chunk, speech_chunk, None),
            (silent_chunk, silent_chunk, None),
            (resumed_chunk, resumed_chunk, None),
        ]
    )
    interface.vc.convert_chunk_bulk = lambda _indata: next(responses)
    indata = np.zeros((block_size, 1), dtype=np.float32)

    interface.audio_input_callback(indata, block_size, None, None)
    _drain_queue(interface.out_queue)
    _drain_queue(interface.monitor_queue)

    # Leave the queued trailing silence blocks in place before speech resumes.
    interface.audio_input_callback(indata, block_size, None, None)
    assert interface.out_queue.qsize() == remaining_silent_blocks
    assert interface.monitor_queue.qsize() == remaining_silent_blocks

    interface.audio_input_callback(indata, block_size, None, None)
    main_blocks = _drain_queue(interface.out_queue)
    monitor_blocks = _drain_queue(interface.monitor_queue)
    assert len(main_blocks) == expected_total_silent_blocks + 1
    assert len(monitor_blocks) == expected_total_silent_blocks + 1
    assert all(np.all(block == 0) for block in main_blocks[:expected_total_silent_blocks])
    assert all(np.all(block == 0) for block in monitor_blocks[:expected_total_silent_blocks])
    np.testing.assert_array_equal(main_blocks[-1], resumed_chunk)
    np.testing.assert_array_equal(monitor_blocks[-1], resumed_chunk)

    interface.output_preroll_needed = False
    interface.monitor_preroll_needed = False
    interface.truncate_output_buffer()
    assert interface.output_preroll_needed is True
    assert interface.monitor_preroll_needed is True
