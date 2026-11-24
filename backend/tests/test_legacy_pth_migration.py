import json
import shutil
from pathlib import Path

import pytest
import torch

from vcclient.voice_changer.model_catalog import get_model_entry, list_models
from vcclient.voice_changer.slot_manager.onnx_exporter.models import SynthesizerTrnF0
from vcclient.voice_changer.voice_changer_const import SLOT_PARAM_FILE


@pytest.fixture
def dummy_rvc_pth(tmp_path: Path) -> Path:
    """RVC v2 F0 ありの最小チェックポイント (.pth) を生成する"""
    config = [
        1025,  # spec_channels
        32,  # segment_size
        192,  # inter_channels
        192,  # hidden_channels
        768,  # filter_channels
        2,  # n_heads
        2,  # n_layers
        3,  # kernel_size
        0.0,  # p_dropout
        "1",  # resblock
        [3, 7, 11],  # resblock_kernel_sizes
        [[1, 3, 5], [1, 3, 5], [1, 3, 5]],  # resblock_dilation_sizes
        [10, 8, 2, 2],  # upsample_rates
        512,  # upsample_initial_channel
        [16, 16, 4, 4],  # upsample_kernel_sizes
        1,  # spk_embed_dim
        256,  # gin_channels
        40000,  # sr
    ]

    model = SynthesizerTrnF0(
        spec_channels=config[0],
        segment_size=config[1],
        inter_channels=config[2],
        hidden_channels=config[3],
        filter_channels=config[4],
        n_heads=config[5],
        n_layers=config[6],
        kernel_size=config[7],
        p_dropout=config[8],
        resblock=config[9],
        resblock_kernel_sizes=config[10],
        resblock_dilation_sizes=config[11],
        upsample_rates=config[12],
        upsample_initial_channel=config[13],
        upsample_kernel_sizes=config[14],
        spk_embed_dim=config[15],
        gin_channels=config[16],
        sr=config[17],
        emb_channels=768,
        is_half=False,
    )

    cpt = {
        "config": config,
        "weight": model.state_dict(),
        "f0": 1,
        "version": "v2",
    }
    pth_path = tmp_path / "dummy_v2_f0.pth"
    torch.save(cpt, pth_path)
    return pth_path


def test_migration_converts_legacy_pth_slot_with_params_json(dummy_rvc_pth: Path, tmp_path: Path, monkeypatch):
    """本家の params.json (inferencer_type: pyTorchRVC, .pth) があるスロットを起動時に自動で ONNX に変換することをテスト"""
    models_dir = tmp_path / "model_dir"
    slot_index = 3
    slot_dir = models_dir / str(slot_index)
    slot_dir.mkdir(parents=True, exist_ok=True)

    # .pth をスロットフォルダに配置
    target_pth = slot_dir / dummy_rvc_pth.name
    shutil.copy(dummy_rvc_pth, target_pth)

    # 本家スタイルの params.json を配置 (inferencer_type が pyTorchRVC)
    legacy_params = {
        "voice_changer_type": "RVC",
        "name": "My Migrated Character",
        "description": "Imported from upstream v2.0.78",
        "credit": "Original Author",
        "terms_of_use_url": "https://example.com/terms",
        "model_file": target_pth.name,
        "index_file": None,
        "icon_file": None,
        "is_onnx": False,
        "inferencer_type": "pyTorchRVC",  # 本家レガシー値
        "sample_rate": 40000,
        "is_f0": True,
        "pitch_shift": 12,
        "index_ratio": 0.8,
        "protect_ratio": 0.33,
        "speakers": {"0": "Legacy"},
        "deprecated": False,
        "sample_id": "legacy-sample",
    }
    (slot_dir / SLOT_PARAM_FILE).write_text(json.dumps(legacy_params, indent=4), encoding="utf-8")

    # ModelDir / ConfigFile をモック
    monkeypatch.setattr("vcclient.voice_changer.voice_changer_const.ModelDir", models_dir)
    monkeypatch.setattr("vcclient.voice_changer.voice_changer_const.ConfigFile", tmp_path / "vc_conf.json")

    # model_catalog のスキャンで旧スロットが自動変換・移行されること
    models = list_models()
    assert len(models) == 1
    model, stored, entry_dir = get_model_entry(models[0].id)

    # .onnx が生成され、ユーザーの大切な元の .pth も安全に保持されていること
    expected_onnx = entry_dir / f"{dummy_rvc_pth.stem}.onnx"
    assert expected_onnx.exists()
    assert (entry_dir / dummy_rvc_pth.name).exists()

    # モデル情報が正しく更新され、ユーザー設定（名前やピッチシフトなど）が引き継がれていること
    assert stored.voice_changer_type == "RVC"
    assert stored.is_onnx is True
    assert stored.inferencer_type == "onnxRVC"
    assert stored.model_file == expected_onnx.name
    assert model.name == "My Migrated Character"
    assert model.pitch_shift == 12
    assert model.index_ratio == 0.8
    dumped = stored.model_dump()
    for legacy_key in (
        "description",
        "credit",
        "terms_of_use_url",
        "protect_ratio",
        "speakers",
        "deprecated",
        "sample_id",
    ):
        assert legacy_key not in dumped


def test_migration_converts_legacy_pth_slot_without_params_json(dummy_rvc_pth: Path, tmp_path: Path, monkeypatch):
    """params.json がない場合でも、.pth と .index があれば自動で ONNX に変換し params.json を生成することをテスト"""
    models_dir = tmp_path / "model_dir"
    slot_index = 5
    slot_dir = models_dir / str(slot_index)
    slot_dir.mkdir(parents=True, exist_ok=True)

    # .pth とダミーの .index, .png を配置
    target_pth = slot_dir / dummy_rvc_pth.name
    shutil.copy(dummy_rvc_pth, target_pth)

    index_file = slot_dir / "my_character.index"
    index_file.write_text("dummy index content", encoding="utf-8")

    icon_file = slot_dir / "icon.png"
    icon_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    # params.json は意図的に配置しない

    monkeypatch.setattr("vcclient.voice_changer.voice_changer_const.ModelDir", models_dir)
    monkeypatch.setattr("vcclient.voice_changer.voice_changer_const.ConfigFile", tmp_path / "vc_conf.json")

    models = list_models()
    assert len(models) == 1
    model, stored, entry_dir = get_model_entry(models[0].id)

    expected_onnx = entry_dir / f"{dummy_rvc_pth.stem}.onnx"
    assert expected_onnx.exists()
    assert (entry_dir / dummy_rvc_pth.name).exists()

    # params.json が自動生成され、index と icon も認識されていること
    assert stored.is_onnx is True
    assert stored.inferencer_type == "onnxRVC"
    assert stored.model_file == expected_onnx.name
    assert stored.index_file == index_file.name
    assert stored.icon_file == icon_file.name
    assert model.has_index is True
    assert model.has_icon is True


def test_migration_skips_already_converted_slot(tmp_path: Path, monkeypatch):
    """すでに .onnx が存在するスロットは .pth 変換をスキップして移行されることをテスト"""
    models_dir = tmp_path / "model_dir"
    slot_index = 7
    slot_dir = models_dir / str(slot_index)
    slot_dir.mkdir(parents=True, exist_ok=True)

    # .onnx ファイルを配置
    onnx_file = slot_dir / "my_model.onnx"
    onnx_file.write_bytes(b"dummy onnx content")

    legacy_params = {
        "name": "Already ONNX",
        "voice_changer_type": "RVC",
        "model_file": onnx_file.name,
        "is_onnx": True,
        "inferencer_type": "onnxRVC",
        "sample_rate": 40000,
        "is_f0": True,
        "embedder": "hubert_base_l12",
    }
    (slot_dir / SLOT_PARAM_FILE).write_text(json.dumps(legacy_params, indent=4), encoding="utf-8")

    monkeypatch.setattr("vcclient.voice_changer.voice_changer_const.ModelDir", models_dir)
    monkeypatch.setattr("vcclient.voice_changer.voice_changer_const.ConfigFile", tmp_path / "vc_conf.json")
    monkeypatch.setattr(
        "vcclient.voice_changer.model_catalog.model_catalog_manager.export_pth_to_onnx",
        lambda *_args, **_kwargs: pytest.fail("export_pth_to_onnx should not be called"),
    )

    models = list_models()
    assert len(models) == 1
    model, stored, entry_dir = get_model_entry(models[0].id)
    assert model.name == "Already ONNX"
    assert stored.model_file == onnx_file.name
    assert (entry_dir / onnx_file.name).exists()
