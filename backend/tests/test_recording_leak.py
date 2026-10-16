from unittest.mock import MagicMock

import numpy as np

from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


def test_monitor_record_does_not_leak_memory_when_recording_is_stopped_passthrough(monkeypatch):
    """Verify that monitor_record and output_record do not accumulate audio chunks

    when recording_start_flag is False during pass-through mode.
    """
    vc = VoiceChanger.get_instance()
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()

    monkeypatch.setattr(conf, "pass_through", True)
    monkeypatch.setattr(vc.vc_info, "monitor_enabled", True)
    monkeypatch.setattr(vc.vc_info, "recording_start_flag", False)

    vc.input_record = []
    vc.output_record = []
    vc.monitor_record = []

    dummy_chunk = np.zeros(1024, dtype=np.float32)

    for _ in range(5):
        vc._convert_chunk(dummy_chunk, direct_from_server=True)

    assert len(vc.output_record) == 0
    assert len(vc.monitor_record) == 0


def test_records_accumulate_properly_without_duplicates_when_recording_passthrough(monkeypatch):
    """Verify that output_record and monitor_record accumulate exactly 1 item per chunk

    during pass-through mode when recording is active.
    """
    vc = VoiceChanger.get_instance()
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()

    monkeypatch.setattr(conf, "pass_through", True)
    monkeypatch.setattr(vc.vc_info, "monitor_enabled", True)
    monkeypatch.setattr(vc.vc_info, "recording_start_flag", True)

    vc.input_record = []
    vc.output_record = []
    vc.monitor_record = []

    dummy_chunk = np.zeros(1024, dtype=np.float32)

    for _ in range(3):
        vc._convert_chunk(dummy_chunk, direct_from_server=True)

    assert len(vc.output_record) == 3
    assert len(vc.monitor_record) == 3


def test_monitor_record_does_not_leak_in_normal_conversion_path(monkeypatch):
    """Verify that monitor_record does not accumulate audio chunks during normal conversion

    path (non-pass-through) when recording_start_flag is False.
    """
    vc = VoiceChanger.get_instance()
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()

    monkeypatch.setattr(conf, "pass_through", False)
    monkeypatch.setattr(vc.vc_info, "monitor_enabled", True)
    monkeypatch.setattr(vc.vc_info, "recording_start_flag", False)
    monkeypatch.setattr(vc.vc_info, "vc_input_sample_rate", 16000)
    monkeypatch.setattr(vc.vc_info, "vc_output_sample_rate", 48000)
    monkeypatch.setattr(vc.vc_info, "resample_ratio_in", 1.0)
    monkeypatch.setattr(vc.vc_info, "resample_ratio_out", 1.0)
    monkeypatch.setattr(vc.vc_info, "resample_ratio_monitor", 1.0)

    mock_pipeline = MagicMock()
    mock_pipeline.get_chunk_sec.return_value = 0.25
    mock_pipeline.get_input_bitdepth.return_value = np.float32
    mock_pipeline.get_output_bitdepth.return_value = np.float32
    mock_pipeline.needs_crossfade.return_value = False
    mock_pipeline.run.return_value = np.zeros(1024, dtype=np.float32)

    monkeypatch.setattr(vc, "vc_pipeline", mock_pipeline)
    monkeypatch.setattr(vc, "_check_reload_model_is_required_and_update", lambda: None)
    monkeypatch.setattr(vc, "_check_and_update_pitch_estimator", lambda: None)
    monkeypatch.setattr(vc, "_check_and_update_sample_rate", lambda: None)
    monkeypatch.setattr(vc, "_check_and_update_filter", lambda: None)
    monkeypatch.setattr(vc, "_exec_resample_in", lambda w: w)
    monkeypatch.setattr(vc, "_exec_resample_out", lambda w: w)
    monkeypatch.setattr(vc, "_exec_resample_monitor", lambda w: w)

    vc.input_record = []
    vc.output_record = []
    vc.monitor_record = []

    dummy_chunk = np.zeros(1024, dtype=np.float32)

    for _ in range(5):
        vc._convert_chunk(dummy_chunk, direct_from_server=True)

    assert len(vc.output_record) == 0
    assert len(vc.monitor_record) == 0


def test_records_accumulate_properly_in_normal_conversion_path(monkeypatch):
    """Verify that output_record and monitor_record accumulate exactly 1 item per chunk

    during normal conversion path when recording is active (no duplicate output_record).
    """
    vc = VoiceChanger.get_instance()
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()

    monkeypatch.setattr(conf, "pass_through", False)
    monkeypatch.setattr(vc.vc_info, "monitor_enabled", True)
    monkeypatch.setattr(vc.vc_info, "recording_start_flag", True)
    monkeypatch.setattr(vc.vc_info, "vc_input_sample_rate", 16000)
    monkeypatch.setattr(vc.vc_info, "vc_output_sample_rate", 48000)
    monkeypatch.setattr(vc.vc_info, "resample_ratio_in", 1.0)
    monkeypatch.setattr(vc.vc_info, "resample_ratio_out", 1.0)
    monkeypatch.setattr(vc.vc_info, "resample_ratio_monitor", 1.0)

    mock_pipeline = MagicMock()
    mock_pipeline.get_chunk_sec.return_value = 0.25
    mock_pipeline.get_input_bitdepth.return_value = np.float32
    mock_pipeline.get_output_bitdepth.return_value = np.float32
    mock_pipeline.needs_crossfade.return_value = False
    mock_pipeline.run.return_value = np.zeros(1024, dtype=np.float32)

    monkeypatch.setattr(vc, "vc_pipeline", mock_pipeline)
    monkeypatch.setattr(vc, "_check_reload_model_is_required_and_update", lambda: None)
    monkeypatch.setattr(vc, "_check_and_update_pitch_estimator", lambda: None)
    monkeypatch.setattr(vc, "_check_and_update_sample_rate", lambda: None)
    monkeypatch.setattr(vc, "_check_and_update_filter", lambda: None)
    monkeypatch.setattr(vc, "_exec_resample_in", lambda w: w)
    monkeypatch.setattr(vc, "_exec_resample_out", lambda w: w)
    monkeypatch.setattr(vc, "_exec_resample_monitor", lambda w: w)

    vc.input_record = []
    vc.output_record = []
    vc.monitor_record = []

    dummy_chunk = np.zeros(1024, dtype=np.float32)

    for _ in range(3):
        vc._convert_chunk(dummy_chunk, direct_from_server=True)

    assert len(vc.output_record) == 3
    assert len(vc.monitor_record) == 3
