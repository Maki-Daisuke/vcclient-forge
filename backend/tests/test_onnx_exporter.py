import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import onnxruntime
import pytest
import torch

from vcclient.voice_changer.slot_manager.model_importer.rvc_model_estimator.rvc_model_estimator import (
    estimate_rvc_model,
)
from vcclient.voice_changer.slot_manager.onnx_exporter import export_pth_to_onnx
from vcclient.voice_changer.slot_manager.onnx_exporter.models import SynthesizerTrnF0, SynthesizerTrnNoF0


@pytest.fixture
def dummy_rvc_v2_f0_checkpoint(tmp_path: Path) -> Path:
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


@pytest.fixture
def dummy_rvc_v1_nof0_checkpoint(tmp_path: Path) -> Path:
    """RVC v1 F0 なしの最小チェックポイント (.pth) を生成する"""
    config = [
        1025,
        32,
        192,
        192,
        768,
        2,
        2,
        3,
        0.0,
        "1",
        [3, 7, 11],
        [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
        [10, 8, 2, 2],
        512,
        [16, 16, 4, 4],
        1,
        256,
        40000,
    ]

    model = SynthesizerTrnNoF0(
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
        emb_channels=256,
    )

    cpt = {
        "config": config,
        "weight": model.state_dict(),
        "f0": 0,
        "version": "v1",
    }
    pth_path = tmp_path / "dummy_v1_nof0.pth"
    torch.save(cpt, pth_path)
    return pth_path


def test_export_pth_to_onnx_v2_f0(dummy_rvc_v2_f0_checkpoint: Path, tmp_path: Path):
    """v2 F0 モデルのエクスポートと推論の整合性をテスト"""
    onnx_path = tmp_path / "dummy_v2_f0.onnx"
    res_path = export_pth_to_onnx(dummy_rvc_v2_f0_checkpoint, onnx_path)
    assert res_path == onnx_path
    assert onnx_path.exists()
    assert onnx_path.stat().st_size > 1000

    # ONNX メタデータの検証
    slot_info = estimate_rvc_model(onnx_path)
    assert slot_info.is_onnx is True
    assert slot_info.inferencer_type == "onnxRVC"
    assert slot_info.sample_rate == 40000
    assert slot_info.is_f0 is True
    assert slot_info.embedder == "hubert_base_l12"
    assert slot_info.version == "v2.1"

    # ONNX Runtime セッションでの推論検証
    session = onnxruntime.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    feats = np.random.randn(1, 32, 768).astype(np.float32)
    p_len = np.array([32], dtype=np.int64)
    pitch = np.zeros((1, 32), dtype=np.int64)
    pitchf = np.zeros((1, 32), dtype=np.float32)
    sid = np.array([0], dtype=np.int64)

    outputs = session.run(
        ["audio"],
        {
            "feats": feats,
            "p_len": p_len,
            "pitch": pitch,
            "pitchf": pitchf,
            "sid": sid,
        },
    )
    assert len(outputs) == 1
    audio = outputs[0]
    # 出力は音声波形
    assert audio.size > 0
    assert not np.isnan(audio).any()


def test_export_pth_to_onnx_v1_nof0(dummy_rvc_v1_nof0_checkpoint: Path, tmp_path: Path):
    """v1 noF0 モデルのエクスポートと推論の整合性をテスト"""
    onnx_path = tmp_path / "dummy_v1_nof0.onnx"
    res_path = export_pth_to_onnx(dummy_rvc_v1_nof0_checkpoint, onnx_path)
    assert res_path == onnx_path
    assert onnx_path.exists()

    # ONNX メタデータの検証
    slot_info = estimate_rvc_model(onnx_path)
    assert slot_info.is_onnx is True
    assert slot_info.inferencer_type == "onnxRVCNono"
    assert slot_info.sample_rate == 40000
    assert slot_info.is_f0 is False
    assert slot_info.embedder == "hubert_base_l9fp"
    assert slot_info.version == "v1.1"

    # ONNX Runtime セッションでの推論検証
    session = onnxruntime.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    feats = np.random.randn(1, 32, 256).astype(np.float32)
    p_len = np.array([32], dtype=np.int64)
    sid = np.array([0], dtype=np.int64)

    outputs = session.run(
        ["audio"],
        {
            "feats": feats,
            "p_len": p_len,
            "sid": sid,
        },
    )
    assert len(outputs) == 1
    audio = outputs[0]
    assert audio.size > 0
    assert not np.isnan(audio).any()


def test_estimate_rvc_model_rejects_pth(dummy_rvc_v2_f0_checkpoint: Path):
    """estimate_rvc_model は .onnx のみを受理する。.pth は export 後に ONNX として渡す運用のため拒否する。"""
    from vcclient.exception import ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED, VCClientError

    with pytest.raises(VCClientError) as exc_info:
        estimate_rvc_model(dummy_rvc_v2_f0_checkpoint)
    assert exc_info.value.info.code == ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED


def test_import_model_auto_converts_pth(dummy_rvc_v2_f0_checkpoint: Path, tmp_path: Path):
    """import_model に .pth を渡した際、自動的に .onnx に変換されて .pth が削除されることをテスト"""
    from vcclient.voice_changer.data_types.slot_manager_data_types import RVCModelImportParam
    from vcclient.voice_changer.slot_manager.model_importer.model_importer import import_model
    from vcclient.voice_changer.voice_changer_const import SLOT_PARAM_FILE

    model_dir = tmp_path / "models"
    slot_index = 0
    import_param = RVCModelImportParam(
        slot_index=slot_index,
        name="test_model",
        voice_changer_type="RVC",
        model_file=dummy_rvc_v2_f0_checkpoint,
    )

    import_model(model_dir, import_param)

    slot_dir = model_dir / str(slot_index)
    onnx_file = slot_dir / f"{dummy_rvc_v2_f0_checkpoint.stem}.onnx"
    pth_file = slot_dir / dummy_rvc_v2_f0_checkpoint.name

    # .onnx が生成され、元の .pth は削除されていること
    assert onnx_file.exists()
    assert not pth_file.exists()

    # slot_param.json の検証
    param_file = slot_dir / SLOT_PARAM_FILE
    assert param_file.exists()
    data = json.loads(param_file.read_text(encoding="utf-8"))
    assert data["is_onnx"] is True
    assert data["inferencer_type"] == "onnxRVC"
    assert data["model_file"] == onnx_file.name


def test_model_import_requires_slot_index_before_creating_directory(tmp_path: Path):
    from vcclient.exception import ERROR_CODE_IMPORT_MODEL_FAILED, VCClientError
    from vcclient.voice_changer.data_types.slot_manager_data_types import ModelImportParam
    from vcclient.voice_changer.slot_manager.model_importer.model_importer import import_model

    with pytest.raises(VCClientError) as error:
        import_model(tmp_path, ModelImportParam(voice_changer_type="RVC", name="Invalid"))

    assert error.value.info.code == ERROR_CODE_IMPORT_MODEL_FAILED
    assert list(tmp_path.iterdir()) == []


def test_invalid_model_architecture_is_rejected_with_optimization(tmp_path: Path):
    script = """
from vcclient.voice_changer.slot_manager.onnx_exporter.attentions import MultiHeadAttention
from vcclient.voice_changer.slot_manager.onnx_exporter.modules import ConvReluNorm, ResidualCouplingLayer, WN

invalid_models = {
    "attention heads": lambda: MultiHeadAttention(3, 3, 2),
    "layer count": lambda: ConvReluNorm(1, 1, 1, 3, 1, 0),
    "kernel size": lambda: WN(1, 2, 1, 1),
    "channel count": lambda: ResidualCouplingLayer(3, 1, 3, 1, 1),
}
for label, build in invalid_models.items():
    try:
        build()
    except ValueError:
        continue
    raise RuntimeError(f"Invalid {label} was accepted")
"""
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
