import json

from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.data_types import VoiceChangerConfiguration


def test_transient_states_excluded_from_saved_config(tmp_path, monkeypatch):
    test_conf_path = tmp_path / "vc_conf.json"
    monkeypatch.setattr(
        "vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile",
        str(test_conf_path),
    )

    # Initialize fresh instance
    cm = ConfigurationManager()
    cm.voice_changer_configuration = VoiceChangerConfiguration()
    cm.voice_changer_configuration.pass_through = True
    cm.voice_changer_configuration.recording_started = True

    # Save to disk
    cm.save_voice_changer_configuration()

    assert test_conf_path.exists()
    saved_data = json.loads(test_conf_path.read_text(encoding="utf-8"))

    # Transient runtime states must NOT be persisted to disk
    assert "pass_through" not in saved_data
    assert "recording_started" not in saved_data


def test_reload_resets_transient_states_even_if_present_in_legacy_file(tmp_path, monkeypatch):
    test_conf_path = tmp_path / "vc_conf.json"
    monkeypatch.setattr(
        "vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile",
        str(test_conf_path),
    )

    # Create a legacy config containing pass_through and recording_started set to True
    legacy_conf = VoiceChangerConfiguration().model_dump()
    legacy_conf["pass_through"] = True
    legacy_conf["recording_started"] = True
    test_conf_path.write_text(json.dumps(legacy_conf), encoding="utf-8")

    # Reload from disk
    cm = ConfigurationManager()
    assert cm.voice_changer_configuration.pass_through is False
    assert cm.voice_changer_configuration.recording_started is False


def test_gpu_device_id_normalization(tmp_path, monkeypatch):
    test_conf_path = tmp_path / "vc_conf.json"
    monkeypatch.setattr(
        "vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile",
        str(test_conf_path),
    )

    # Legacy config with gpu_device_id_int = -1
    legacy_conf = VoiceChangerConfiguration().model_dump()
    legacy_conf["gpu_device_id_int"] = -1
    test_conf_path.write_text(json.dumps(legacy_conf), encoding="utf-8")

    cm = ConfigurationManager()
    # -1 should normalize to index 0 (CPU)
    assert cm.voice_changer_configuration.gpu_device_id_int == 0

    # Set configuration with out-of-bounds id
    new_conf = VoiceChangerConfiguration()
    new_conf.gpu_device_id_int = 9999
    cm.set_voice_changer_configuration(new_conf)
    assert cm.voice_changer_configuration.gpu_device_id_int == 0


def test_configuration_ignores_legacy_crossfade_sec(tmp_path, monkeypatch):
    """Verify crossfade_sec is removed from model and legacy config with crossfade_sec is parsed without error."""
    test_conf_path = tmp_path / "vc_conf.json"
    monkeypatch.setattr(
        "vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile",
        str(test_conf_path),
    )

    data = VoiceChangerConfiguration().model_dump()
    assert "crossfade_sec" not in data

    # Add legacy crossfade_sec and verify deserialization ignores it safely
    data["crossfade_sec"] = 0.052
    test_conf_path.write_text(json.dumps(data), encoding="utf-8")

    cm = ConfigurationManager()
    assert not hasattr(cm.voice_changer_configuration, "crossfade_sec")


def test_api_put_configuration_accepts_legacy_crossfade_sec(client=None):
    """Verify FastAPI PUT /api/configuration-manager/configuration accepts payloads containing crossfade_sec."""
    from starlette.testclient import TestClient

    from vcclient.server.vcserver_rest_api import get_rest_api

    app = get_rest_api()
    test_client = TestClient(app)

    get_res = test_client.get("/api/configuration-manager/configuration")
    assert get_res.status_code == 200
    config_dict = get_res.json()
    assert "crossfade_sec" not in config_dict

    # Simulate legacy client sending crossfade_sec in PUT
    config_dict["crossfade_sec"] = 0.052
    put_res = test_client.put("/api/configuration-manager/configuration", json=config_dict)
    assert put_res.status_code == 200


def test_operation_initialize_removed():
    from starlette.testclient import TestClient

    from vcclient.server.vcserver_rest_api import _create_rest_api

    client = TestClient(_create_rest_api())
    response = client.post("/api/operation/initialize")
    assert response.status_code == 404


def _setup_clear_test_env(tmp_path, monkeypatch, config: VoiceChangerConfiguration):
    from pathlib import Path
    from types import SimpleNamespace

    from starlette.testclient import TestClient

    from vcclient.server.vcserver_rest_api import _create_rest_api
    from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo
    from vcclient.voice_changer.slot_manager.slot_manager import SlotManager
    from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
    from vcclient.voice_changer.voice_change_manager.vc_pipelines.pipeline_manager import PipelineManager
    from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

    conf_path = tmp_path / "vc_conf.json"
    models_dir = tmp_path / "model_dir"
    slot_dir = models_dir / str(config.current_slot_index)
    slot_dir.mkdir(parents=True)
    model_file = slot_dir / "model.onnx"
    model_file.write_bytes(b"model-data")
    slot_info = RVCSlotInfo(
        slot_index=config.current_slot_index,
        name="Test Model",
        model_file=Path("model.onnx"),
        is_onnx=True,
    )
    (slot_dir / "params.json").write_text(slot_info.model_dump_json(), encoding="utf-8")

    modules_dir = tmp_path / "modules"
    module_file = modules_dir / "contentvec" / "contentvec-f.onnx"
    module_file.parent.mkdir(parents=True)
    module_file.write_bytes(b"module-data")

    monkeypatch.setattr("vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile", conf_path)
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", models_dir)
    monkeypatch.setattr(ConfigurationManager, "_instance", None)
    monkeypatch.setattr(SlotManager, "_instance", None)
    monkeypatch.setattr(LocalVoiceChangerInterface, "_instance", None)
    monkeypatch.setattr(VoiceChanger, "_instance", None)

    def _fake_get_pipeline(loaded_slot_info):
        assert loaded_slot_info.slot_index == config.current_slot_index
        return SimpleNamespace(
            get_input_sample_rate=lambda: 48000,
            get_output_sample_rate=lambda: 48000,
            get_pitch_estimator_type=lambda: loaded_slot_info.pitch_estimator,
            get_gpu_device_id=lambda: 0,
        )

    monkeypatch.setattr(PipelineManager, "get_pipeline", _fake_get_pipeline)

    cm = ConfigurationManager.get_instance()
    cm.voice_changer_configuration = config
    cm.save_voice_changer_configuration()

    local = LocalVoiceChangerInterface.get_instance()
    voice = VoiceChanger.get_instance()
    assert voice.vc_info.slot_index == config.current_slot_index
    assert voice.vc_pipeline is not None

    return SimpleNamespace(
        client=TestClient(_create_rest_api()),
        cm=cm,
        conf_path=conf_path,
        model_file=model_file,
        module_file=module_file,
        local=local,
        voice=voice,
    )


def test_clear_configuration_resets_only_settings_and_preserves_models_and_modules(tmp_path, monkeypatch):
    env = _setup_clear_test_env(
        tmp_path,
        monkeypatch,
        VoiceChangerConfiguration(
            current_slot_index=7,
            voice_changer_input_mode="server",
            audio_input_device_index=3,
            audio_output_device_gain=2.5,
            noise_gate=-45,
        ),
    )

    response = env.client.post("/api/configuration-manager/clear")
    assert response.status_code == 200

    expected = VoiceChangerConfiguration().model_dump()
    assert response.json() == expected
    assert env.cm.get_voice_changer_configuration() == VoiceChangerConfiguration()
    saved = json.loads(env.conf_path.read_text(encoding="utf-8"))
    assert saved["current_slot_index"] == 0
    assert saved["voice_changer_input_mode"] == "client"
    assert env.voice.vc_pipeline is None
    assert env.model_file.read_bytes() == b"model-data"
    assert env.module_file.read_bytes() == b"module-data"


def test_clear_configuration_rejects_while_audio_is_active(tmp_path, monkeypatch):
    env = _setup_clear_test_env(
        tmp_path,
        monkeypatch,
        VoiceChangerConfiguration(current_slot_index=5, noise_gate=-55),
    )

    for active_target, attr in (
        (env.local, "local_voice_changer_enabled"),
        (env.local, "stream_running"),
    ):
        with monkeypatch.context() as m:
            m.setattr(active_target, attr, True)
            res = env.client.post("/api/configuration-manager/clear")
            assert res.status_code == 409

    with monkeypatch.context() as m:
        m.setattr(env.voice, "is_convert_chunk_bulk_started", lambda: True)
        res = env.client.post("/api/configuration-manager/clear")
        assert res.status_code == 409

    assert env.cm.get_voice_changer_configuration().current_slot_index == 5
    saved = json.loads(env.conf_path.read_text(encoding="utf-8"))
    assert saved["noise_gate"] == -55
