from pathlib import Path

from vcclient.voice_changer.data_types.slot_manager_data_types import RVCSlotInfo, SlotInfo
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager, reload_slot_infos
from vcclient.voice_changer.voice_chanager_const import SLOT_PARAM_FILE


def test_reload_slot_infos_empty_dir(tmp_path: Path):
    """モデルが1つもない場合、スロット0のみ（要素数1の空き枠）を返す。"""
    slot_infos = reload_slot_infos(tmp_path)
    assert len(slot_infos) == 1
    assert slot_infos[0].slot_index == 0
    assert slot_infos[0].voice_changer_type is None


def test_reload_slot_infos_dynamic_sizing_with_blank_padding(tmp_path: Path):
    """スロット0と2が存在する場合、[0, 1, 2, 3] の4要素を返し、末尾に次の空き枠3を設ける。"""
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

    # スロット3: 次の空き枠
    assert slot_infos[3].slot_index == 3
    assert slot_infos[3].voice_changer_type is None


def test_get_blank_slot_index_and_out_of_range_lookup(monkeypatch, tmp_path: Path):
    """get_blank_slot_index が最小の空き番号を返し、get_slot_info が範囲外でもブランクを返す。"""
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

    # 範囲外のインデックス（例: 50）にアクセスしても、クラッシュせずブランクスロットを返す
    slot50 = slot_mgr.get_slot_info(50)
    assert isinstance(slot50, SlotInfo)
    assert slot50.slot_index == 50
    assert slot50.voice_changer_type is None


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
