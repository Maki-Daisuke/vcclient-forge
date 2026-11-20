import json
from pathlib import Path

import pytest

from vcclient.voice_changer.slot_manager.reorder_transaction import ModelTransaction, ModelTransactionError


@pytest.fixture
def storage(tmp_path: Path):
    models = tmp_path / "models"
    models.mkdir()
    for number in (0, 2, 5):
        directory = models / str(number)
        directory.mkdir()
        (directory / "params.json").write_text(
            json.dumps({"slot_index": number, "name": f"model {number}"}), encoding="utf-8"
        )
        (directory / "voice.onnx").write_bytes(f"model {number}".encode())
    config = tmp_path / "settings.json"
    config.write_text(json.dumps({"current_slot_index": 2, "other": "retained"}), encoding="utf-8")
    return models, config


def test_reorders_compacts_and_updates_selected(storage):
    models, config = storage
    transaction = ModelTransaction(models, config)
    assert transaction.apply([0, 2, 5], [5, 0, 2], 2) == 2
    assert [(models / str(i) / "voice.onnx").read_bytes() for i in range(3)] == [b"model 5", b"model 0", b"model 2"]
    assert [
        json.loads((models / str(i) / "params.json").read_text(encoding="utf-8"))["slot_index"] for i in range(3)
    ] == [0, 1, 2]
    assert json.loads(config.read_text(encoding="utf-8")) == {"current_slot_index": 2, "other": "retained"}


def test_deletes_one_model_and_clears_selected(storage):
    models, config = storage
    transaction = ModelTransaction(models, config)
    assert transaction.apply([0, 2, 5], [0, 5], 2) == -1
    assert (models / "1" / "voice.onnx").read_bytes() == b"model 5"
    assert json.loads(config.read_text(encoding="utf-8"))["current_slot_index"] == -1
    assert sorted(p.name for p in models.iterdir()) == ["0", "1"]


@pytest.mark.parametrize("failure_at", [1, 2, 3, 4, 5, 6])
def test_interrupted_renames_are_recovered(storage, monkeypatch, failure_at):
    models, config = storage
    original_rename = Path.rename
    attempts = 0

    def interrupted(path, target):
        nonlocal attempts
        attempts += 1
        if attempts == failure_at:
            raise KeyboardInterrupt("simulated termination")
        return original_rename(path, target)

    with monkeypatch.context() as context:
        context.setattr(Path, "rename", interrupted)
        with pytest.raises(KeyboardInterrupt):
            ModelTransaction(models, config).apply([0, 2, 5], [5, 0, 2], 2)
    ModelTransaction(models, config).recover()
    assert sorted(p.name for p in models.iterdir()) == ["0", "2", "5"]
    for i in (0, 2, 5):
        assert (models / str(i) / "voice.onnx").read_bytes() == f"model {i}".encode()
        assert json.loads((models / str(i) / "params.json").read_text(encoding="utf-8"))["slot_index"] == i
    assert json.loads(config.read_text(encoding="utf-8"))["current_slot_index"] == 2


def test_does_not_overwrite_untracked_directory(storage):
    models, config = storage
    (models / "1").mkdir()
    (models / "1" / "untracked").write_bytes(b"important")
    with pytest.raises(ModelTransactionError):
        ModelTransaction(models, config).apply([0, 2, 5], [5, 0, 2], 2)
    assert (models / "1" / "untracked").read_bytes() == b"important"


def test_failed_config_update_rolls_back_files_and_metadata(storage, monkeypatch):
    models, config = storage
    transaction = ModelTransaction(models, config)
    original_write = transaction._write_config
    attempts = 0

    def fail_once(data):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated config write failure")
        return original_write(data)

    monkeypatch.setattr(transaction, "_write_config", fail_once)
    with pytest.raises(ModelTransactionError, match="rolled back"):
        transaction.apply([0, 2, 5], [5, 0, 2], 2)
    assert sorted(p.name for p in models.iterdir()) == ["0", "2", "5"]
    for i in (0, 2, 5):
        assert (models / str(i) / "voice.onnx").read_bytes() == f"model {i}".encode()
        assert json.loads((models / str(i) / "params.json").read_text(encoding="utf-8"))["slot_index"] == i
    assert json.loads(config.read_text(encoding="utf-8"))["current_slot_index"] == 2


@pytest.mark.parametrize("failure_at", [1, 2, 3, 4, 5, 6])
def test_interrupted_recovery_can_be_retried(storage, monkeypatch, failure_at):
    models, config = storage
    transaction = ModelTransaction(models, config)
    original_rename = Path.rename
    attempts = 0

    def interrupt_publish(path, target):
        nonlocal attempts
        attempts += 1
        if attempts == 6:
            raise KeyboardInterrupt()
        return original_rename(path, target)

    with monkeypatch.context() as context:
        context.setattr(Path, "rename", interrupt_publish)
        with pytest.raises(KeyboardInterrupt):
            transaction.apply([0, 2, 5], [5, 0, 2], 2)
    attempts = 0

    def interrupt_recovery(path, target):
        nonlocal attempts
        attempts += 1
        if attempts == failure_at:
            raise KeyboardInterrupt()
        return original_rename(path, target)

    with monkeypatch.context() as context:
        context.setattr(Path, "rename", interrupt_recovery)
        try:
            transaction.recover()
        except KeyboardInterrupt:
            pass
    transaction.recover()
    for i in (0, 2, 5):
        assert (models / str(i) / "voice.onnx").read_bytes() == f"model {i}".encode()
    assert json.loads(config.read_text(encoding="utf-8"))["current_slot_index"] == 2
