from unittest.mock import MagicMock

import pytest

from vcclient.device import DeviceConfig, device_selector
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
        device(10, "webgpu", 1),
        device(11, "webgpu", 0),
    ]
    assert [item.id for item in device_selector._initial_device_candidates(devices)] == [9, 8, 7, 4, 3, 2, 1, 11, 10, 0]


def test_discrete_gpus_outrank_integrated_gpus_across_providers():
    devices = [
        device(1, "openvino", 0, metadata={"ov_device": "GPU.0"}),
        device(2, "webgpu", 0, metadata={"discrete": True}),
        device(3, "directml", 0, metadata={"discrete": True}),
        device(4, "openvino", 1, metadata={"ov_device": "GPU.1", "discrete": True}),
    ]
    assert [item.id for item in device_selector._initial_device_candidates(devices)] == [4, 3, 2, 1]


def test_failed_pipeline_is_collected_before_next_device(monkeypatch):
    import weakref

    class CyclicPipeline:
        def __init__(self):
            self.self_ref = self

        def warmup(self):
            raise RuntimeError("device failed")

    refs = []

    def probe(slot):
        assert all(ref() is None for ref in refs)
        pipeline = CyclicPipeline()
        refs.append(weakref.ref(pipeline))
        return pipeline

    monkeypatch.setattr(
        device_selector,
        "get_device_catalog",
        lambda: [device(0, "cpu", device_type="CPU"), device(1, "webgpu", 0), device(2, "webgpu", 1)],
    )
    monkeypatch.setattr(rvc_pipeline, "RVCPipeline", probe)
    monkeypatch.setattr(device_selector, "_verify_device_sessions", lambda *_: None)
    # pytest's log capture would retain exc_info tracebacks, which keep failed pipelines alive.
    monkeypatch.setattr(device_selector.logger, "warning", lambda *_, **__: None)
    with pytest.raises(RuntimeError, match="No inference device"):
        device_selector._probe_first_working_device(VoiceChangerConfiguration(), MagicMock())
    assert len(refs) == 3


def test_openvino_priority_uses_device_number_not_enumeration_order():
    devices = [
        device(1, "openvino", 0, metadata={"ov_device": "GPU.1"}),
        device(2, "openvino", 1, metadata={"ov_device": "GPU.0"}),
    ]
    assert [item.id for item in device_selector._initial_device_candidates(devices)] == [1, 2]


def test_first_start_tries_next_device_before_saving(monkeypatch):
    config = VoiceChangerConfiguration()
    manager = MagicMock()
    manager.get_voice_changer_configuration.return_value = config
    monkeypatch.setattr(ConfigurationManager, "get_instance", lambda: manager)
    monkeypatch.setattr(
        device_selector,
        "_get_probe_slot",
        lambda _preferred=None: RVCSlotInfo(slot_index=-1, model_id="model_1", model_file="model.onnx"),
    )
    monkeypatch.setattr(
        device_selector,
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
    monkeypatch.setattr(device_selector, "_verify_device_sessions", verify)
    selected = device_selector.recommend_compute_device()
    assert selected.id == 1
    assert attempted == [2, 1]
    # recommend_compute_device probes without mutating the caller's configured device ID.
    assert config.gpu_device_id_int == 0
    assert verify.call_count == 3
    assert verify.call_args_list[0].args[0].warmup.call_count == 1
    assert verify.call_args_list[1].args[0].warmup.call_count == 1
    manager.save_voice_changer_configuration.assert_not_called()


def test_all_device_failures_do_not_save(monkeypatch):
    config = VoiceChangerConfiguration()
    manager = MagicMock()
    manager.get_voice_changer_configuration.return_value = config
    monkeypatch.setattr(ConfigurationManager, "get_instance", lambda: manager)
    monkeypatch.setattr(
        device_selector,
        "_get_probe_slot",
        lambda _preferred=None: RVCSlotInfo(slot_index=-1, model_id="model_1", model_file="model.onnx"),
    )
    monkeypatch.setattr(device_selector, "get_device_catalog", lambda: [device(0, "cpu", device_type="CPU")])
    monkeypatch.setattr(rvc_pipeline, "RVCPipeline", MagicMock(side_effect=RuntimeError("failure")))
    with pytest.raises(RuntimeError, match="No inference device"):
        device_selector.recommend_compute_device()
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
        device_selector._verify_device_sessions(pipeline, pipeline.device)


def test_pipeline_verification_disables_runtime_provider_fallback():
    pipeline = rvc_pipeline.RVCPipeline.__new__(rvc_pipeline.RVCPipeline)
    pipeline.device = device(1, "cuda")
    session = MagicMock()
    session.get_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    pipeline.pitch_estimator = MagicMock(onnx_session=session)
    pipeline.embedder = MagicMock(onnx_session=session)
    pipeline.rvc = MagicMock(onnx_session=session)
    pipeline.onnx_upscaler = session
    device_selector._verify_device_sessions(pipeline, pipeline.device)
    assert session.disable_fallback.call_count == 4


def test_pipeline_verification_accepts_webgpu_provider():
    pipeline = rvc_pipeline.RVCPipeline.__new__(rvc_pipeline.RVCPipeline)
    pipeline.device = device(1, "webgpu")
    session = MagicMock()
    session.get_providers.return_value = ["WebGpuExecutionProvider", "CPUExecutionProvider"]
    pipeline.pitch_estimator = MagicMock(onnx_session=session)
    pipeline.embedder = MagicMock(onnx_session=session)
    pipeline.rvc = MagicMock(onnx_session=session)
    pipeline.onnx_upscaler = session
    device_selector._verify_device_sessions(pipeline, pipeline.device)
    assert session.disable_fallback.call_count == 4
