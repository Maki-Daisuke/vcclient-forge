import time
from queue import Queue

import numpy as np

from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import (
    LocalVoiceChangerInterface,
)


def test_audio_output_callback_zero_fills_when_queue_empty(monkeypatch):
    """Verify that audio_output_callback fills outdata with zeros and returns immediately

    when the output queue is empty.
    """
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
