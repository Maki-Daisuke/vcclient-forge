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


def test_clear_configuration_resets_only_settings_and_preserves_models_and_modules(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    from vcclient.server.vcserver_rest_api import _create_rest_api
    from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
    from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

    conf_path = tmp_path / "vc_conf.json"
    models_dir = tmp_path / "model_dir"
    model_file = models_dir / "7" / "model.onnx"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"model-data")
    modules_dir = tmp_path / "modules"
    module_file = modules_dir / "contentvec" / "contentvec-f.onnx"
    module_file.parent.mkdir(parents=True)
    module_file.write_bytes(b"module-data")

    monkeypatch.setattr("vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile", conf_path)
    monkeypatch.setattr(ConfigurationManager, "_instance", None)

    cm = ConfigurationManager.get_instance()
    custom = VoiceChangerConfiguration(
        current_slot_index=7,
        voice_changer_input_mode="server",
        audio_input_device_index=3,
        audio_output_device_gain=2.5,
        noise_gate=-45,
    )
    cm.voice_changer_configuration = custom
    cm.save_voice_changer_configuration()

    voice = VoiceChanger.get_instance()
    voice.vc_pipeline = object()  # type: ignore[assignment]
    local = LocalVoiceChangerInterface.get_instance()
    monkeypatch.setattr(local, "local_voice_changer_enabled", False)
    monkeypatch.setattr(local, "stream_running", False)

    client = TestClient(_create_rest_api())
    response = client.post("/api/configuration-manager/clear")
    assert response.status_code == 200

    expected = VoiceChangerConfiguration().model_dump()
    assert response.json() == expected
    assert cm.get_voice_changer_configuration() == VoiceChangerConfiguration()
    saved = json.loads(conf_path.read_text(encoding="utf-8"))
    assert saved["current_slot_index"] == 0
    assert saved["voice_changer_input_mode"] == "client"
    assert voice.vc_pipeline is None
    assert model_file.read_bytes() == b"model-data"
    assert module_file.read_bytes() == b"module-data"


def test_clear_configuration_rejects_while_audio_is_active(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    from vcclient.server.vcserver_rest_api import _create_rest_api
    from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
    from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

    conf_path = tmp_path / "vc_conf.json"
    monkeypatch.setattr("vcclient.voice_changer.configuration_manager.configuration_manager.ConfigFile", conf_path)
    monkeypatch.setattr(ConfigurationManager, "_instance", None)

    cm = ConfigurationManager.get_instance()
    cm.voice_changer_configuration = VoiceChangerConfiguration(current_slot_index=5, noise_gate=-55)
    cm.save_voice_changer_configuration()

    local = LocalVoiceChangerInterface.get_instance()
    voice = VoiceChanger.get_instance()
    client = TestClient(_create_rest_api())

    for active_target, attr in (
        (local, "local_voice_changer_enabled"),
        (local, "stream_running"),
    ):
        with monkeypatch.context() as m:
            m.setattr(active_target, attr, True)
            res = client.post("/api/configuration-manager/clear")
            assert res.status_code == 409

    with monkeypatch.context() as m:
        m.setattr(voice, "is_convert_chunk_bulk_started", lambda: True)
        res = client.post("/api/configuration-manager/clear")
        assert res.status_code == 409

    assert cm.get_voice_changer_configuration().current_slot_index == 5
    saved = json.loads(conf_path.read_text(encoding="utf-8"))
    assert saved["noise_gate"] == -55
