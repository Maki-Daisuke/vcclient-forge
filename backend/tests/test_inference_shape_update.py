from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


@pytest.fixture
def shape_update(monkeypatch):
    slot = RVCSlotInfo(slot_index=0, voice_changer_type="RVC", model_file="model.onnx", chunk_sec=0.5)
    conf = SimpleNamespace(current_slot_index=0, gpu_device_id_int=0, extra_frame_sec=5.0, sola_search_frame_sec=0.012)
    manager = SimpleNamespace(get_voice_changer_configuration=lambda: conf, set_voice_changer_configuration=Mock())
    monkeypatch.setattr(ConfigurationManager, "get_instance", lambda: manager)
    monkeypatch.setattr(SlotManager, "get_instance", lambda: SimpleNamespace(get_slot_info=lambda _: slot))

    pipeline = RVCPipeline.__new__(RVCPipeline)
    pipeline.slot_index = 0
    pipeline._slot_info = slot
    pipeline.target_frames = pipeline._calculate_target_feats_length()
    vc = VoiceChanger.__new__(VoiceChanger)
    vc.vc_pipeline = pipeline
    vc.vc_info = SimpleNamespace(slot_index=0, gpu_device_index=0, bulk_process_start_flag=False)

    def rebuild(_slot_index):
        pipeline.target_frames = pipeline._calculate_target_feats_length()

    vc._update_model = Mock(side_effect=rebuild)
    vc._set_io_sample_rate = Mock()
    return vc, slot, conf, manager


def test_rebuilds_when_inference_frame_count_changes(shape_update):
    vc, slot, conf, _ = shape_update
    assert vc.vc_pipeline.target_frames == 112

    vc._check_reload_model_is_required_and_update()
    vc._update_model.assert_not_called()

    slot.chunk_sec = 0.1
    vc._check_reload_model_is_required_and_update()
    assert vc.vc_pipeline.target_frames == 72
    assert vc._update_model.call_count == 1

    slot.chunk_sec = 0.5
    vc._check_reload_model_is_required_and_update()
    assert vc.vc_pipeline.target_frames == 112
    assert vc._update_model.call_count == 2

    conf.extra_frame_sec = 0.34
    vc._check_reload_model_is_required_and_update()
    assert vc.vc_pipeline.target_frames == 60
    assert vc._update_model.call_count == 3

    conf.sola_search_frame_sec = 0.052
    vc._check_reload_model_is_required_and_update()
    assert vc.vc_pipeline.target_frames != 60
    assert vc._update_model.call_count == 4

    vc._check_reload_model_is_required_and_update()
    assert vc._update_model.call_count == 4


def test_failed_shape_rebuild_does_not_silently_use_old_pipeline(shape_update):
    vc, slot, _, manager = shape_update
    slot.chunk_sec = 0.1
    vc._update_model.side_effect = RuntimeError("model load failed")

    with pytest.raises(RuntimeError, match="model load failed"):
        vc._check_reload_model_is_required_and_update()

    assert vc.vc_pipeline.target_frames == 112
    manager.set_voice_changer_configuration.assert_not_called()
