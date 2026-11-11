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
