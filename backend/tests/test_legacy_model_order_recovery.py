import base64
import json
from pathlib import Path

import pytest

from vcclient.voice_changer import voice_changer_const
from vcclient.voice_changer.model_catalog import get_model_entry, list_models
from vcclient.voice_changer.slot_manager.legacy_recovery import recover_legacy_model_order


def _make_transaction(tmp_path: Path, phase: str) -> tuple[Path, Path]:
    model_dir = tmp_path / "models"
    journal = model_dir / ".model-order-transaction"
    journal.mkdir(parents=True)
    config_file = tmp_path / "settings.json"
    original_config = json.dumps({"current_slot_index": 2, "noise_gate": -42}).encode()
    config_file.write_bytes(original_config)
    originals = [0, 2, 5]
    order = [5, 0, 2]
    params = {}
    for index in originals:
        data = {
            "slot_index": index,
            "voice_changer_type": "RVC",
            "name": f"model {index}",
            "model_file": "voice.onnx",
            "sample_rate": 40000,
            "is_f0": True,
            "embedder": "hubert_base_l12",
        }
        params[str(index)] = base64.b64encode(json.dumps(data).encode()).decode()
        directory = journal / f"model-{index}"
        directory.mkdir()
        (directory / "params.json").write_text(json.dumps(data), encoding="utf-8")
        (directory / "voice.onnx").write_bytes(f"model {index}".encode())
    manifest = {
        "phase": phase,
        "originals": originals,
        "order": order,
        "params": params,
        "config": base64.b64encode(original_config).decode(),
    }
    (journal / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if phase == "staging":
        (journal / "model-5").rename(model_dir / "5")
    elif phase == "publishing":
        (journal / "model-5").rename(model_dir / "0")
        published_params = model_dir / "0" / "params.json"
        data = json.loads(published_params.read_text(encoding="utf-8"))
        data["slot_index"] = 0
        published_params.write_text(json.dumps(data), encoding="utf-8")
    elif phase == "restoring":
        (journal / "model-0").rename(model_dir / "0")
    return model_dir, config_file


@pytest.mark.parametrize("phase", ["staging", "publishing", "restoring"])
def test_recovery_then_catalog_migration_preserves_models_and_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    model_dir, config_file = _make_transaction(tmp_path, phase)
    monkeypatch.setattr(voice_changer_const, "ModelDir", model_dir)
    monkeypatch.setattr(voice_changer_const, "ConfigFile", config_file)

    recover_legacy_model_order(model_dir, config_file)
    assert not (model_dir / ".model-order-transaction").exists()
    assert json.loads(config_file.read_text(encoding="utf-8"))["current_slot_index"] == 2

    models = list_models()
    assert [model.name for model in models] == ["model 0", "model 2", "model 5"]
    for model in models:
        _, _, directory = get_model_entry(model.id)
        assert (directory / "voice.onnx").read_bytes() == model.name.encode()
    config = json.loads(config_file.read_text(encoding="utf-8"))
    assert config["model_id"] == models[1].id
    assert config["noise_gate"] == -42


@pytest.mark.parametrize("failure_at", [1, 2, 3, 4])
def test_interrupted_recovery_can_be_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: int) -> None:
    model_dir, config_file = _make_transaction(tmp_path, "publishing")
    original_rename = Path.rename
    attempts = 0

    def interrupted(path, target):
        nonlocal attempts
        attempts += 1
        if attempts == failure_at:
            raise OSError("simulated interruption")
        return original_rename(path, target)

    with monkeypatch.context() as context:
        context.setattr(Path, "rename", interrupted)
        with pytest.raises(OSError, match="simulated interruption"):
            recover_legacy_model_order(model_dir, config_file)
    recover_legacy_model_order(model_dir, config_file)
    assert [(model_dir / str(index) / "voice.onnx").read_bytes() for index in (0, 2, 5)] == [
        b"model 0",
        b"model 2",
        b"model 5",
    ]


def test_committed_transaction_only_cleans_up(tmp_path: Path) -> None:
    model_dir, config_file = _make_transaction(tmp_path, "committed")
    (model_dir / "0").mkdir()
    (model_dir / "0" / "voice.onnx").write_bytes(b"committed")
    recover_legacy_model_order(model_dir, config_file)
    assert (model_dir / "0" / "voice.onnx").read_bytes() == b"committed"
    assert not (model_dir / ".model-order-transaction").exists()


def test_missing_manifest_with_model_files_stops_recovery(tmp_path: Path) -> None:
    journal = tmp_path / "models" / ".model-order-transaction"
    (journal / "model-0").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="no recovery manifest"):
        recover_legacy_model_order(journal.parent, tmp_path / "settings.json")
    assert (journal / "model-0").is_dir()


def test_startup_recovers_before_loading_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import main

    config_file = tmp_path / "settings.json"
    config_file.write_text("{}", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(main.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(main, "init_logger", lambda: calls.append("logger"))
    monkeypatch.setattr(main, "ConfigFile", config_file)
    monkeypatch.setattr(main, "recover_legacy_model_order", lambda *_args: calls.append("recover"))
    monkeypatch.setattr(main, "_check_and_download_rvc_modules", lambda: calls.append("modules"))
    monkeypatch.setattr(main, "list_models", lambda: calls.append("models"))
    monkeypatch.setattr(main, "_check_and_download_initial_samples", lambda: calls.append("samples"))
    monkeypatch.setattr(main, "is_app_stopping", lambda: True)

    main.start_server()
    assert calls == ["logger", "recover", "modules", "models", "samples"]
