from queue import Queue
from unittest.mock import MagicMock

import numpy as np
import pytest
from scipy.io import wavfile

from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.voice_changer_data_types import VoiceChangerInformation
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    from vcclient.voice_changer.voice_change_manager import voice_changer

    for suffix in ("IN", "OUT", "MONITOR"):
        monkeypatch.setattr(voice_changer, f"SERVER_IO_RECORDING_FILE_{suffix}", str(tmp_path / f"{suffix}.wav"))

    vc = VoiceChanger.__new__(VoiceChanger)
    vc.vc_info = VoiceChangerInformation()
    vc.vc_info.vc_input_sample_rate = 48000
    vc.vc_info.vc_output_sample_rate = 48000
    vc.vc_info.resample_ratio_in = 1.0
    vc.input_sample_rate = 48000
    vc.output_sample_rate = 48000
    vc.monitor_sample_rate = 44100
    pipeline = MagicMock()
    pipeline.get_chunk_sec.return_value = 0.1
    pipeline.get_input_bitdepth.return_value = np.float32
    pipeline.get_output_bitdepth.return_value = np.float32
    pipeline.needs_crossfade.return_value = False
    pipeline.run.side_effect = lambda waveform, **_kwargs: waveform * 0.5
    vc.vc_pipeline = pipeline
    monkeypatch.setattr(vc, "_exec_resample_in", lambda waveform: waveform)
    monkeypatch.setattr(vc, "_exec_resample_out", lambda waveform: waveform)
    monkeypatch.setattr(vc, "_exec_resample_monitor", lambda waveform: waveform)
    monkeypatch.setattr(vc, "_exec_resample_pass_through_in_out", lambda waveform: waveform)
    monkeypatch.setattr(vc, "_exec_resample_pass_through_in_monitor", lambda waveform: waveform)
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    monkeypatch.setattr(conf, "enable_high_pass_filter", False)
    monkeypatch.setattr(conf, "enable_low_pass_filter", False)
    return vc, conf, tmp_path


@pytest.mark.parametrize("modes", [(True,), (False, True, False), (True, False, True)])
def test_recording_preserves_input_and_output_across_passthrough_changes(recorder, monkeypatch, modes):
    vc, conf, path = recorder
    vc.start_recording()
    expected_input = []
    expected_output = []
    for index, passthrough in enumerate(modes, start=1):
        monkeypatch.setattr(conf, "pass_through", passthrough)
        chunk = np.full(16, index / 10, dtype=np.float32)
        vc._convert_chunk(chunk, direct_from_server=True)
        expected_input.append(chunk)
        expected_output.append(chunk if passthrough else chunk * 0.5)
    vc.stop_recording()
    input_rate, input_audio = wavfile.read(path / "IN.wav")
    output_rate, output_audio = wavfile.read(path / "OUT.wav")
    assert input_rate == output_rate == 48000
    np.testing.assert_array_equal(input_audio, np.concatenate(expected_input))
    np.testing.assert_array_equal(output_audio, np.concatenate(expected_output))
    assert vc.vc_info.recording_start_flag is False


def test_int16_input_preserves_audio_level_across_passthrough_changes(recorder, monkeypatch):
    vc, conf, path = recorder
    monkeypatch.setattr(vc, "_exec_resample_pass_through_in_out", lambda waveform: waveform.astype(np.float32))
    chunk = np.full(16, 16384, dtype=np.int16)
    vc.start_recording()
    for passthrough in (True, False, True):
        monkeypatch.setattr(conf, "pass_through", passthrough)
        vc._convert_chunk(chunk, direct_from_server=True)
    vc.stop_recording()
    _, output = wavfile.read(path / "OUT.wav")
    np.testing.assert_allclose(output, np.concatenate([np.full(16, level) for level in (0.5, 0.25, 0.5)]))


def test_recording_armed_before_worker_starts_records_passthrough(recorder, monkeypatch):
    vc, conf, path = recorder
    monkeypatch.setattr(conf, "pass_through", True)
    monkeypatch.setattr(conf, "realtime_process_status_enabled", False)
    monkeypatch.setattr(vc, "check_and_update_pipeline", lambda: None)
    vc.convert_chunk_bulk_queue_in = Queue()
    vc.convert_chunk_bulk_queue_out = Queue()
    vc.convert_chunk_bulk_queue_monitor = Queue()
    vc.waveform_rest = np.empty(0, dtype=np.float32)
    vc.start_recording()
    vc.start_convert_chunk_bulk()
    try:
        chunk = np.full(4800, 0.25, dtype=np.float32)
        vc.convert_chunk_bulk(chunk)
        output, _ = vc.convert_chunk_bulk_queue_out.get(timeout=5)
        np.testing.assert_array_equal(output, chunk)
    finally:
        vc.stop_convert_chunk_bulk()
    vc.stop_recording()
    _, saved = wavfile.read(path / "OUT.wav")
    np.testing.assert_array_equal(saved, chunk)


@pytest.mark.parametrize("monitor_enabled", [False, True])
def test_empty_recording_writes_empty_wav_without_reusing_previous_output(recorder, monitor_enabled):
    vc, _, path = recorder
    (path / "OUT.wav").write_bytes(b"previous recording")
    vc.vc_info.monitor_enabled = monitor_enabled
    vc.start_recording()
    vc.stop_recording()
    for name, expected_rate in [("IN", 48000), ("OUT", 48000)] + ([("MONITOR", 44100)] if monitor_enabled else []):
        rate, samples = wavfile.read(path / f"{name}.wav")
        assert rate == expected_rate
        assert samples.size == 0
    assert vc.vc_info.recording_start_flag is False


def test_empty_recording_before_audio_initialization_uses_configured_rates(recorder, monkeypatch):
    vc, conf, path = recorder
    for name in ("input_sample_rate", "output_sample_rate", "monitor_sample_rate"):
        delattr(vc, name)
    monkeypatch.setattr(conf, "input_sample_rate", 44100)
    monkeypatch.setattr(conf, "output_sample_rate", 48000)
    vc.start_recording()
    vc.stop_recording()
    assert wavfile.read(path / "IN.wav")[0] == 44100
    assert wavfile.read(path / "OUT.wav")[0] == 48000
