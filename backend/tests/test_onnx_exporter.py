import json
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import numpy as np
import onnxruntime
import pytest

from vcclient.voice_changer.slot_manager.model_importer.rvc_model_estimator.rvc_model_estimator import (
    estimate_rvc_model,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
MAIN_PY = BACKEND_DIR / "main.py"


def _write_dummy_pth(pth_path: Path, *, f0: int, version: str, emb_channels: int) -> Path:
    """Create a minimal RVC checkpoint in an isolated child process so pytest never imports torch."""
    model_cls = "SynthesizerTrnF0" if f0 == 1 else "SynthesizerTrnNoF0"
    script = dedent(
        f"""
        import torch
        from vcclient.voice_changer.slot_manager.onnx_exporter.models import {model_cls}

        config = [
            1025, 32, 192, 192, 768, 2, 2, 3, 0.0, "1",
            [3, 7, 11], [[1, 3, 5], [1, 3, 5], [1, 3, 5]],
            [10, 8, 2, 2], 512, [16, 16, 4, 4], 1, 256, 40000,
        ]
        model = {model_cls}(
            spec_channels=config[0], segment_size=config[1], inter_channels=config[2],
            hidden_channels=config[3], filter_channels=config[4], n_heads=config[5],
            n_layers=config[6], kernel_size=config[7], p_dropout=config[8], resblock=config[9],
            resblock_kernel_sizes=config[10], resblock_dilation_sizes=config[11],
            upsample_rates=config[12], upsample_initial_channel=config[13],
            upsample_kernel_sizes=config[14], spk_embed_dim=config[15],
            gin_channels=config[16], sr=config[17], emb_channels={emb_channels},
        )
        torch.save({{"config": config, "weight": model.state_dict(), "f0": {f0}, "version": {version!r}}}, {str(pth_path)!r})
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(BACKEND_DIR), env.get("PYTHONPATH", "")]))
    subprocess.run([sys.executable, "-c", script], cwd=BACKEND_DIR.parent, env=env, check=True, timeout=60)
    return pth_path


@pytest.fixture(scope="module")
def dummy_rvc_v2_f0_checkpoint(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """RVC v2 F0 ありの最小チェックポイント (.pth) を生成する"""
    pth_path = tmp_path_factory.mktemp("exporter_v2_f0") / "dummy_v2_f0.pth"
    return _write_dummy_pth(pth_path, f0=1, version="v2", emb_channels=768)


@pytest.fixture(scope="module")
def dummy_rvc_v1_nof0_checkpoint(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """RVC v1 F0 なしの最小チェックポイント (.pth) を生成する"""
    pth_path = tmp_path_factory.mktemp("exporter_v1_nof0") / "dummy_v1_nof0.pth"
    return _write_dummy_pth(pth_path, f0=0, version="v1", emb_channels=256)


def test_export_pth_to_onnx_v2_f0(dummy_rvc_v2_f0_checkpoint: Path, tmp_path: Path):
    """main.py export-onnx サブコマンド経由での v2 F0 モデル変換と推論の整合性をテスト"""
    onnx_path = tmp_path / "dummy_v2_f0.onnx"
    result = subprocess.run(
        [sys.executable, str(MAIN_PY), "export-onnx", str(dummy_rvc_v2_f0_checkpoint), str(onnx_path)],
        cwd=BACKEND_DIR.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
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
    """main.py export-onnx サブコマンド経由での v1 noF0 モデル変換と推論の整合性をテスト"""
    onnx_path = tmp_path / "dummy_v1_nof0.onnx"
    result = subprocess.run(
        [sys.executable, str(MAIN_PY), "export-onnx", str(dummy_rvc_v1_nof0_checkpoint), str(onnx_path)],
        cwd=BACKEND_DIR.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
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


def test_import_model_auto_converts_pth(
    dummy_rvc_v2_f0_checkpoint: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """create_model に .pth を渡した際、自動的に .onnx に変換されて .pth が削除されることをテスト"""
    from vcclient.voice_changer import voice_changer_const
    from vcclient.voice_changer.model_catalog import create_model, get_model_entry

    model_dir = tmp_path / "models"
    monkeypatch.setattr(voice_changer_const, "ModelDir", model_dir)

    model, _ = create_model(name="test_model", model_path=dummy_rvc_v2_f0_checkpoint)
    _, _, entry_dir = get_model_entry(model.id)

    onnx_file = entry_dir / f"{dummy_rvc_v2_f0_checkpoint.stem}.onnx"
    pth_file = entry_dir / dummy_rvc_v2_f0_checkpoint.name

    # .onnx が生成され、元の .pth は削除されていること
    assert onnx_file.exists()
    assert not pth_file.exists()

    # params.json の検証
    param_file = entry_dir / voice_changer_const.SLOT_PARAM_FILE
    assert param_file.exists()
    data = json.loads(param_file.read_text(encoding="utf-8"))
    assert data["is_onnx"] is True
    assert data["inferencer_type"] == "onnxRVC"
    assert data["model_file"] == onnx_file.name


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


def test_process_isolation_server_vs_export_onnx(dummy_rvc_v2_f0_checkpoint: Path, tmp_path: Path) -> None:
    """Server imports never load torch, and export-onnx subcommand never loads faiss or sounddevice."""
    server_probe = dedent(
        """
        import sys
        import main
        from vcclient.server.vcserver_rest_api import get_rest_api

        get_rest_api()
        assert "torch" not in sys.modules, "torch was unexpectedly imported by server process"
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(BACKEND_DIR), env.get("PYTHONPATH", "")]))
    server_res = subprocess.run(
        [sys.executable, "-c", server_probe],
        cwd=BACKEND_DIR.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert server_res.returncode == 0, server_res.stderr

    out_onnx = tmp_path / "isolated_out.onnx"
    export_probe = dedent(
        f"""
        import runpy
        import sys

        sys.argv = [{str(MAIN_PY)!r}, "export-onnx", {str(dummy_rvc_v2_f0_checkpoint)!r}, {str(out_onnx)!r}]
        try:
            runpy.run_path({str(MAIN_PY)!r}, run_name="__main__")
        except SystemExit as exc:
            assert exc.code == 0, f"Unexpected exit code: {{exc.code}}"
        else:
            raise AssertionError("export-onnx did not exit cleanly")

        assert "torch" in sys.modules
        assert "faiss" not in sys.modules, "faiss was unexpectedly imported by export-onnx"
        assert "sounddevice" not in sys.modules, "sounddevice was unexpectedly imported by export-onnx"
        """
    )
    export_res = subprocess.run(
        [sys.executable, "-c", export_probe],
        cwd=BACKEND_DIR.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert export_res.returncode == 0, export_res.stderr
    assert out_onnx.is_file()


def test_export_pth_to_onnx_subprocess_error(tmp_path: Path) -> None:
    """model_catalog_manager.export_pth_to_onnx surfaces child stderr and removes nothing unexpected."""
    from vcclient.voice_changer.model_catalog.model_catalog_manager import export_pth_to_onnx

    missing_pth = tmp_path / "missing.pth"
    missing_out = tmp_path / "missing.onnx"
    with pytest.raises(RuntimeError, match="Model file not found"):
        export_pth_to_onnx(missing_pth, missing_out)
    assert not missing_out.exists()

    corrupt_pth = tmp_path / "corrupt.pth"
    corrupt_out = tmp_path / "corrupt.onnx"
    corrupt_pth.write_bytes(b"not a torch checkpoint")
    with pytest.raises(RuntimeError):
        export_pth_to_onnx(corrupt_pth, corrupt_out)
    assert not corrupt_out.exists()
