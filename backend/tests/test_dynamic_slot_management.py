from pathlib import Path

import pytest

from vcclient.exception import ERROR_CODE_SLOT_STATE_CONFLICT, VCClientError
from vcclient.voice_changer.data_types.slot_manager_data_types import (
    MoveModelParam,
    RVCModelImportParam,
    RVCSlotInfo,
    SetIconParam,
)
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager, reload_slot_infos
from vcclient.voice_changer.voice_chanager_const import SLOT_PARAM_FILE


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

    slot_mgr.reload(use_log=False)

    # 次の空きインデックスは1
    assert slot_mgr.get_blank_slot_index() == 1

    # 範囲外のインデックス（例: 200 や 4000000000、負の数）にアクセスした場合はエラー
    with pytest.raises(VCClientError):
        slot_mgr.get_slot_info(200)

    with pytest.raises(VCClientError):
        slot_mgr.get_slot_info(4000000000)

    with pytest.raises(VCClientError):
        slot_mgr.get_slot_info(-1)


def test_delete_slot_with_readonly_attributes(monkeypatch, tmp_path: Path):
    """Windows の ReadOnly 属性が付与されたファイルやフォルダでも安全に delete_slot できることを確認。"""
    import os
    import stat

    slot_mgr = SlotManager.get_instance()
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path)

    slot_dir = tmp_path / "7"
    slot_dir.mkdir(parents=True)
    param_file = slot_dir / SLOT_PARAM_FILE
    param_file.write_text("{}", encoding="utf-8")
    dummy_model = slot_dir / "model.onnx"
    dummy_model.write_text("dummy", encoding="utf-8")

    # ReadOnly 属性をファイルおよびディレクトリに付与
    os.chmod(param_file, stat.S_IREAD)
    os.chmod(dummy_model, stat.S_IREAD)
    os.chmod(slot_dir, stat.S_IREAD)

    slot_mgr.reload(use_log=False)
    assert slot_dir.exists()

    # 削除実行
    slot_mgr.delete_slot(7)

    # ディレクトリごと安全に削除されていること
    assert not slot_dir.exists()


def test_slot_state_conflicts_are_rejected_without_overwriting_existing_model(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path)
    slot_dir = tmp_path / "0"
    slot_dir.mkdir()
    params_file = slot_dir / SLOT_PARAM_FILE
    existing_info = RVCSlotInfo(slot_index=0, name="Existing", model_file="existing.onnx")
    params_file.write_text(existing_info.model_dump_json(), encoding="utf-8")
    manager = SlotManager()

    import_param = RVCModelImportParam(slot_index=0, name="Replacement", model_file=tmp_path / "new.onnx")
    for operation in (lambda: manager.set_new_slot(import_param), lambda: manager.reserve_slot_for_sample(0)):
        with pytest.raises(VCClientError) as error:
            operation()
        assert error.value.info.code == ERROR_CODE_SLOT_STATE_CONFLICT
        assert RVCSlotInfo.model_validate_json(params_file.read_text(encoding="utf-8")).name == "Existing"


def test_slot_updates_and_moves_reject_invalid_states(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path)
    slot_dir = tmp_path / "0"
    slot_dir.mkdir()
    params_file = slot_dir / SLOT_PARAM_FILE
    params_file.write_text(
        RVCSlotInfo(slot_index=0, name="Existing", model_file="existing.onnx").model_dump_json(), encoding="utf-8"
    )
    manager = SlotManager()

    invalid_operations = (
        lambda: manager.update_slot_for_sample(0, 0.5),
        lambda: manager.update_slot_info(RVCSlotInfo(slot_index=1, name="Missing", model_file="missing.onnx")),
        lambda: manager.move_model_slot(MoveModelParam(src=0, dst=0)),
        lambda: manager.move_model_slot(MoveModelParam(src=1, dst=2)),
    )
    for operation in invalid_operations:
        with pytest.raises(VCClientError) as error:
            operation()
        assert error.value.info.code == ERROR_CODE_SLOT_STATE_CONFLICT
    assert RVCSlotInfo.model_validate_json(params_file.read_text(encoding="utf-8")).name == "Existing"


def test_set_icon_rejects_empty_slot_before_moving_upload(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("vcclient.voice_changer.slot_manager.slot_manager.ModelDir", tmp_path / "models")
    manager = SlotManager()
    icon_file = tmp_path / "icon.png"
    icon_file.write_bytes(b"icon")

    with pytest.raises(VCClientError) as error:
        manager.set_icon_file(SetIconParam(slot_index=0, icon_file=icon_file))

    assert error.value.info.code == ERROR_CODE_SLOT_STATE_CONFLICT
    assert icon_file.exists()
