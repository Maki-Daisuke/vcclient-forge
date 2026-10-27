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
