from pathlib import Path

import pytest

from vcclient.exception import ERROR_CODE_SLOT_STATE_CONFLICT, VCClientError
from vcclient.voice_changer.data_types.slot_manager_data_types import (
    RVCModelImportParam,
    RVCSlotInfo,
)
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager, reload_slot_infos
from vcclient.voice_changer.voice_changer_const import SLOT_PARAM_FILE


def test_reload_slot_infos_empty_dir(tmp_path: Path):
    """モデルが1つもない場合、スロット0のみ（要素数1の空き枠）を返す。"""
    slot_infos = reload_slot_infos(tmp_path)
    assert len(slot_infos) == 1
    assert slot_infos[0].slot_index == 0
    assert slot_infos[0].voice_changer_type is None


def test_reload_slot_infos_with_models(tmp_path: Path):
    """スロット0と2が存在する場合、[0, 1, 2, 3] の4要素を返し、10202等の範囲外フォルダは無視される。"""
    # スロット0を作成
    slot0_dir = tmp_path / "0"
    slot0_dir.mkdir(parents=True)
    slot0_info = RVCSlotInfo(
        slot_index=0,
        voice_changer_type="RVC",
        name="ModelZero",
        model_file="m0.onnx",
    )
    with open(slot0_dir / SLOT_PARAM_FILE, "w", encoding="utf-8") as f:
        f.write(slot0_info.model_dump_json())

    # スロット2を作成（スロット1は空き）
    slot2_dir = tmp_path / "2"
    slot2_dir.mkdir(parents=True)
    slot2_info = RVCSlotInfo(
        slot_index=2,
        voice_changer_type="RVC",
        name="ModelTwo",
        model_file="m2.onnx",
    )
    with open(slot2_dir / SLOT_PARAM_FILE, "w", encoding="utf-8") as f:
        f.write(slot2_info.model_dump_json())

    # 旧Beatrice等の範囲外フォルダが存在していても無視されること
    out_of_range_dir = tmp_path / "10202"
    out_of_range_dir.mkdir(parents=True)
    with open(out_of_range_dir / SLOT_PARAM_FILE, "w", encoding="utf-8") as f:
        f.write('{"voice_changer_type": "BROKEN"}')

    slot_infos = reload_slot_infos(tmp_path)
    assert len(slot_infos) == 4

    # スロット0: ModelZero
    assert slot_infos[0].slot_index == 0
    assert slot_infos[0].voice_changer_type == "RVC"
    assert slot_infos[0].name == "ModelZero"

    # スロット1: ブランクスロット
    assert slot_infos[1].slot_index == 1
    assert slot_infos[1].voice_changer_type is None

    # スロット2: ModelTwo
    assert slot_infos[2].slot_index == 2
    assert slot_infos[2].voice_changer_type == "RVC"
    assert slot_infos[2].name == "ModelTwo"

    # スロット3: 空き枠（次の枠）
    assert slot_infos[3].slot_index == 3
    assert slot_infos[3].voice_changer_type is None


def test_get_blank_slot_index_and_out_of_range_lookup(monkeypatch, tmp_path: Path):
    """get_blank_slot_index が最小の空き番号を返し、get_slot_info が範囲外で VCClientError を投げる。"""
    import pytest

    from vcclient.exception import VCClientError

    slot_mgr = SlotManager.get_instance()
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path)

    # スロット0にモデルを配置
    slot0_dir = tmp_path / "0"
    slot0_dir.mkdir(parents=True)
    slot0_info = RVCSlotInfo(
        slot_index=0,
        voice_changer_type="RVC",
        name="ModelZero",
        model_file="m0.onnx",
    )
    with open(slot0_dir / SLOT_PARAM_FILE, "w", encoding="utf-8") as f:
        f.write(slot0_info.model_dump_json())

    slot_mgr.reload()

    # 次の空きインデックスは1
    assert slot_mgr.get_blank_slot_index() == 1

    # 範囲外のインデックス（例: 200 や 4000000000、負の数）にアクセスした場合はエラー
    with pytest.raises(VCClientError):
        slot_mgr.get_slot_info(200)

    with pytest.raises(VCClientError):
        slot_mgr.get_slot_info(4000000000)

    with pytest.raises(VCClientError):
        slot_mgr.get_slot_info(-1)


def test_slot_state_conflicts_are_rejected_without_overwriting_existing_model(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path)
    slot_dir = tmp_path / "0"
    slot_dir.mkdir()
    params_file = slot_dir / SLOT_PARAM_FILE
    existing_info = RVCSlotInfo(slot_index=0, name="Existing", model_file="existing.onnx")
    params_file.write_text(existing_info.model_dump_json(), encoding="utf-8")
    manager = SlotManager()

    import_param = RVCModelImportParam(slot_index=0, name="Replacement", model_file=tmp_path / "new.onnx")
    with pytest.raises(VCClientError) as error:
        manager.set_new_slot(import_param)
    assert error.value.info.code == ERROR_CODE_SLOT_STATE_CONFLICT
    assert RVCSlotInfo.model_validate_json(params_file.read_text(encoding="utf-8")).name == "Existing"


def test_slot_updates_reject_invalid_states(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path)
    slot_dir = tmp_path / "0"
    slot_dir.mkdir()
    params_file = slot_dir / SLOT_PARAM_FILE
    params_file.write_text(
        RVCSlotInfo(slot_index=0, name="Existing", model_file="existing.onnx").model_dump_json(), encoding="utf-8"
    )
    manager = SlotManager()

    with pytest.raises(VCClientError) as error:
        manager.update_slot_info(RVCSlotInfo(slot_index=1, name="Missing", model_file="missing.onnx"))
    assert error.value.info.code == ERROR_CODE_SLOT_STATE_CONFLICT
    assert RVCSlotInfo.model_validate_json(params_file.read_text(encoding="utf-8")).name == "Existing"


def test_update_slot_metadata_rejects_empty_slot_without_copying_icon(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path / "models")
    manager = SlotManager()
    icon_file = tmp_path / "icon.png"
    icon_file.write_bytes(b"icon")

    with pytest.raises(VCClientError) as error:
        manager.update_slot_metadata(0, icon_file=icon_file)

    assert error.value.info.code == ERROR_CODE_SLOT_STATE_CONFLICT
    assert icon_file.exists()
    assert not (tmp_path / "models" / "0").exists()


def test_update_slot_metadata_replaces_icon_atomically_without_pipeline_reload(monkeypatch, tmp_path: Path):
    models_dir = tmp_path / "models"
    slot_dir = models_dir / "0"
    slot_dir.mkdir(parents=True)
    old_icon = slot_dir / "old_icon.png"
    old_icon.write_bytes(b"old-icon")
    model_file = slot_dir / "voice.onnx"
    model_file.write_bytes(b"onnx-bytes")
    slot_info = RVCSlotInfo(
        slot_index=0,
        voice_changer_type="RVC",
        name="InitialName",
        model_file=Path("voice.onnx"),
        icon_file=Path("old_icon.png"),
    )
    (slot_dir / SLOT_PARAM_FILE).write_text(slot_info.model_dump_json(indent=4), encoding="utf-8")

    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", models_dir)
    manager = SlotManager()
    check_calls = 0

    def fail_if_called():
        nonlocal check_calls
        check_calls += 1
        raise AssertionError("check_and_update_pipeline must not be called for metadata-only edits")

    monkeypatch.setattr(
        "vcclient.voice_changer.voice_change_manager.voice_changer.VoiceChanger.get_instance",
        lambda: type("DummyVC", (), {"check_and_update_pipeline": staticmethod(fail_if_called)})(),
    )

    new_icon = tmp_path / "icon_abc123.webp"
    new_icon.write_bytes(b"new-icon")
    updated = manager.update_slot_metadata(0, name="  Renamed  ", icon_file=new_icon)

    assert updated.name == "Renamed"
    assert updated.icon_file == Path("icon_abc123.webp")
    assert check_calls == 0
    assert (slot_dir / "icon_abc123.webp").read_bytes() == b"new-icon"
    assert not old_icon.exists()
    assert model_file.exists()
    persisted = RVCSlotInfo.model_validate_json((slot_dir / SLOT_PARAM_FILE).read_text(encoding="utf-8"))
    assert persisted.name == "Renamed"
    assert persisted.icon_file == Path("icon_abc123.webp")


def test_update_slot_metadata_invalid_name_preserves_existing_icon(monkeypatch, tmp_path: Path):
    models_dir = tmp_path / "models"
    slot_dir = models_dir / "0"
    slot_dir.mkdir(parents=True)
    old_icon = slot_dir / "old.png"
    old_icon.write_bytes(b"old-icon")
    slot_info = RVCSlotInfo(
        slot_index=0,
        voice_changer_type="RVC",
        name="Original",
        model_file=Path("voice.onnx"),
        icon_file=Path("old.png"),
    )
    (slot_dir / SLOT_PARAM_FILE).write_text(slot_info.model_dump_json(indent=4), encoding="utf-8")

    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", models_dir)
    manager = SlotManager()
    new_icon = tmp_path / "icon_new.png"
    new_icon.write_bytes(b"new-icon")

    with pytest.raises(ValueError, match="empty"):
        manager.update_slot_metadata(0, name="   ", icon_file=new_icon)

    assert old_icon.read_bytes() == b"old-icon"
    assert not (slot_dir / "icon_new.png").exists()
    persisted = RVCSlotInfo.model_validate_json((slot_dir / SLOT_PARAM_FILE).read_text(encoding="utf-8"))
    assert persisted.name == "Original"
    assert persisted.icon_file == Path("old.png")


def test_update_slot_metadata_save_failure_rolls_back_memory_and_icon(monkeypatch, tmp_path: Path):
    models_dir = tmp_path / "models"
    slot_dir = models_dir / "0"
    slot_dir.mkdir(parents=True)
    old_icon = slot_dir / "old.png"
    old_icon.write_bytes(b"old-icon")
    slot_info = RVCSlotInfo(
        slot_index=0,
        voice_changer_type="RVC",
        name="Original",
        model_file=Path("voice.onnx"),
        icon_file=Path("old.png"),
    )
    (slot_dir / SLOT_PARAM_FILE).write_text(slot_info.model_dump_json(indent=4), encoding="utf-8")

    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", models_dir)
    manager = SlotManager()
    monkeypatch.setattr(manager, "save_slot_info", lambda _info: (_ for _ in ()).throw(OSError("disk full")))

    new_icon = tmp_path / "icon_failed.png"
    new_icon.write_bytes(b"new-icon")

    with pytest.raises(OSError, match="disk full"):
        manager.update_slot_metadata(0, name="FailedRename", icon_file=new_icon)

    in_memory = manager.get_slot_info(0)
    assert isinstance(in_memory, RVCSlotInfo)
    assert in_memory.name == "Original"
    assert in_memory.icon_file == Path("old.png")
    assert old_icon.read_bytes() == b"old-icon"
    assert not (slot_dir / "icon_failed.png").exists()
    persisted = RVCSlotInfo.model_validate_json((slot_dir / SLOT_PARAM_FILE).read_text(encoding="utf-8"))
    assert persisted.name == "Original"
    assert persisted.icon_file == Path("old.png")
