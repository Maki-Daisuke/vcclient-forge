from unittest.mock import MagicMock

import pytest

from vcclient import initializer
from vcclient.device import DeviceConfig
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.data_types import VoiceChangerConfiguration
from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
from vcclient.voice_changer.voice_change_manager.vc_pipelines import rvc_pipeline


def device(index, provider, device_index=0, device_type="GPU", metadata=None):
    return DeviceConfig(
        id=index,
        canonical_id=f"{provider}:{device_index}",
        provider=provider,
        device_index=device_index,
        device_type=device_type,
        name=f"{provider}-{device_index}",
        metadata=metadata or {},
    )


def test_initial_candidate_order_and_unsupported_devices():
    devices = [
        device(0, "cpu", device_type="CPU"),
        device(1, "directml", 0),
        device(2, "directml", 1),
        device(3, "openvino", 0),
        device(4, "openvino", 1),
        device(5, "openvino", 0, "NPU"),
        device(6, "coreml", 1, metadata={"compute_units": "CPUAndGPU"}),
        device(7, "coreml", 0, "NPU", {"compute_units": "ALL"}),
        device(8, "cuda", 0),
        device(9, "cuda", 1),
    ]
    assert [item.id for item in initializer._initial_device_candidates(devices)] == [9, 8, 7, 4, 3, 2, 1, 0]


def test_openvino_priority_uses_device_number_not_enumeration_order():
    devices = [
        device(1, "openvino", 0, metadata={"ov_device": "GPU.1"}),
        device(2, "openvino", 1, metadata={"ov_device": "GPU.0"}),
    ]
    assert [item.id for item in initializer._initial_device_candidates(devices)] == [1, 2]


def test_first_start_tries_next_device_before_saving(monkeypatch):
    config = VoiceChangerConfiguration()
    manager = MagicMock()
    manager.get_voice_changer_configuration.return_value = config
    slot_manager = MagicMock()
    slot_manager.get_slot_info.return_value = RVCSlotInfo(slot_index=0, model_file="model.onnx")
    monkeypatch.setattr(initializer.ConfigurationManager, "get_instance", lambda: manager)
    monkeypatch.setattr(initializer.SlotManager, "get_instance", lambda: slot_manager)
    monkeypatch.setattr(
        initializer,
        "get_device_catalog",
        lambda: [device(0, "cpu", device_type="CPU"), device(1, "cuda", 0), device(2, "cuda", 1)],
    )
    attempted = []

    def probe(slot):
        assert not manager.save_voice_changer_configuration.called
        attempted.append(config.gpu_device_id_int)
        pipeline = MagicMock()
        if config.gpu_device_id_int == 2:
            pipeline.warmup.side_effect = RuntimeError("device failed")
        return pipeline

    monkeypatch.setattr(rvc_pipeline, "RVCPipeline", probe)
    verify = MagicMock()
    monkeypatch.setattr(initializer, "_verify_device_sessions", verify)
    assert initializer._select_initial_compute_device() is True
    assert attempted == [2, 1]
    assert config.gpu_device_id_int == 1
    assert verify.call_count == 3
    assert verify.call_args_list[0].args[0].warmup.call_count == 1
    assert verify.call_args_list[1].args[0].warmup.call_count == 1
    manager.save_voice_changer_configuration.assert_not_called()


def test_all_device_failures_do_not_save(monkeypatch):
    config = VoiceChangerConfiguration()
    manager = MagicMock()
    manager.get_voice_changer_configuration.return_value = config
    slot_manager = MagicMock()
    slot_manager.get_slot_info.return_value = RVCSlotInfo(slot_index=0, model_file="model.onnx")
    monkeypatch.setattr(initializer.ConfigurationManager, "get_instance", lambda: manager)
    monkeypatch.setattr(initializer.SlotManager, "get_instance", lambda: slot_manager)
    monkeypatch.setattr(initializer, "get_device_catalog", lambda: [device(0, "cpu", device_type="CPU")])
    monkeypatch.setattr(rvc_pipeline, "RVCPipeline", MagicMock(side_effect=RuntimeError("failure")))
    with pytest.raises(RuntimeError, match="No inference device"):
        initializer._select_initial_compute_device()
    manager.save_voice_changer_configuration.assert_not_called()


def test_deferred_first_configuration_is_not_saved_until_selected(tmp_path, monkeypatch):
    config_path = tmp_path / "vc_conf.json"
    monkeypatch.setattr("vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile", config_path)
    manager = ConfigurationManager(defer_initial_save=True)
    assert not config_path.exists()
    manager.save_voice_changer_configuration()
    assert config_path.exists()


def test_first_run_audio_defaults():
    config = VoiceChangerConfiguration()
    assert config.voice_changer_input_mode == "client"
    assert config.extra_frame_sec == 0.5
    assert config.noise_gate == -35
    assert config.enable_high_pass_filter and config.high_pass_filter_cutoff == 100
    assert config.enable_low_pass_filter and config.low_pass_filter_cutoff == 12000


def test_pipeline_verification_rejects_provider_fallback():
    pipeline = rvc_pipeline.RVCPipeline.__new__(rvc_pipeline.RVCPipeline)
    pipeline.device = device(1, "cuda")
    session = MagicMock()
    session.get_providers.return_value = ["CPUExecutionProvider"]
    pipeline.pitch_estimator = MagicMock(onnx_session=session)
    pipeline.embedder = MagicMock(onnx_session=session)
    pipeline.rvc = MagicMock(onnx_session=session)
    pipeline.onnx_upscaler = session
    with pytest.raises(RuntimeError, match="CUDAExecutionProvider"):
        initializer._verify_device_sessions(pipeline, pipeline.device)


def test_pipeline_verification_disables_runtime_provider_fallback():
    pipeline = rvc_pipeline.RVCPipeline.__new__(rvc_pipeline.RVCPipeline)
    pipeline.device = device(1, "cuda")
    session = MagicMock()
    session.get_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    pipeline.pitch_estimator = MagicMock(onnx_session=session)
    pipeline.embedder = MagicMock(onnx_session=session)
    pipeline.rvc = MagicMock(onnx_session=session)
    pipeline.onnx_upscaler = session
    initializer._verify_device_sessions(pipeline, pipeline.device)
    assert session.disable_fallback.call_count == 4


def test_strict_warmup_propagates_inference_failure(monkeypatch):
    pipeline = rvc_pipeline.RVCPipeline.__new__(rvc_pipeline.RVCPipeline)
    pipeline.pitch_estimator = MagicMock()
    pipeline.embedder = MagicMock()
    pipeline.rvc = MagicMock()
    pipeline.onnx_upscaler = MagicMock()
    reset = MagicMock()
    monkeypatch.setattr(pipeline, "_reset_buffers", reset)
    monkeypatch.setattr(pipeline, "get_chunk_sec", lambda: 0.5)
    monkeypatch.setattr(pipeline, "run", MagicMock(side_effect=RuntimeError("inference failed")))
    pipeline.slot_index = 0

    with pytest.raises(RuntimeError, match="inference failed"):
        pipeline.warmup()
    reset.assert_called_once_with()
