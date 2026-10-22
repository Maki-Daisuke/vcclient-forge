import json
import warnings
from pathlib import Path
from typing import Any

import onnx
import torch

from vcclient.exception import (
    ERROR_CODE_RVC_INVALID_CONFIG_LENGTH,
    ERROR_CODE_RVC_INVALID_F0_VALUE,
    ERROR_CODE_RVC_INVALID_TORCH_MODEL,
    ERROR_CODE_RVC_INVALID_TORCH_MODEL_VERSION_VALUE,
    ERROR_CODE_RVC_UNKNOWN_EMBEDDER,
    VCClientError,
)
from vcclient.logger import logger

from .models import SynthesizerTrnF0, SynthesizerTrnNoF0


def extract_metadata_from_checkpoint(cpt: dict[str, Any]) -> dict[str, Any]:
    """PyTorch チェックポイントからメタデータを解析・抽出する"""
    version = cpt.get("version", "v1") or "v1"
    if version not in ("v1", "v2"):
        logger.error("Invalid torch version: %s", version)
        raise VCClientError(ERROR_CODE_RVC_INVALID_TORCH_MODEL_VERSION_VALUE, f"Invalid torch version: {version}")

    f0_val = cpt.get("f0", 1)
    if f0_val == 1:
        is_f0 = True
    elif f0_val == 0:
        is_f0 = False
    else:
        logger.error("Invalid f0 value: %s", f0_val)
        raise VCClientError(ERROR_CODE_RVC_INVALID_F0_VALUE, f"Invalid f0 value: {f0_val}")

    if "config" in cpt:
        config = cpt["config"]
        config_len = len(config)
        sample_rate = config[-1]
        if config_len == 18:
            training_by = "official"
            emb_channels = 256 if version == "v1" else 768
        elif config_len == 19:
            training_by = "ddpn"
            emb_channels = config[17]
        else:
            logger.error("config_len: %s", config_len)
            raise VCClientError(ERROR_CODE_RVC_INVALID_CONFIG_LENGTH, f"config_len:{config_len}")
    elif "params" in cpt:
        params = cpt["params"]
        sample_rate = params.get("sr", 40000)
        training_by = "webui"
        emb_channels = params.get("emb_channels", 256 if version == "v1" else 768)
    else:
        logger.error("Checkpoint missing both config and params")
        raise VCClientError(ERROR_CODE_RVC_INVALID_TORCH_MODEL, "Checkpoint missing both config and params")

    if training_by == "official":
        if version == "v1":
            embedder = "hubert_base_l9fp"
            emb_output_layer = 9
            use_final_proj = True
        else:
            embedder = "hubert_base_l12"
            emb_output_layer = 12
            use_final_proj = False
    elif training_by == "ddpn":
        embedder_name = cpt.get("embedder_name", "hubert_base")
        if embedder_name in ("hubert_base", "contentvec") and emb_channels == 256:
            embedder = "hubert_base_l9fp"
            emb_output_layer = 9
            use_final_proj = True
        elif embedder_name == "hubert-base-japanese" and emb_channels == 256:
            embedder = "hubert_base_japanese_l9fp"
            emb_output_layer = 9
            use_final_proj = True
        elif embedder_name in ("hubert_base", "contentvec") and emb_channels == 768:
            embedder = "hubert_base_l12"
            emb_output_layer = 12
            use_final_proj = False
        elif embedder_name == "hubert-base-japanese" and emb_channels == 768:
            embedder = "hubert_base_japanese_l12"
            emb_output_layer = 12
            use_final_proj = False
        else:
            logger.error("Invalid embedder: %s, emb_channels: %s", embedder_name, emb_channels)
            raise VCClientError(
                ERROR_CODE_RVC_UNKNOWN_EMBEDDER,
                f"Invalid embedder: {embedder_name}, emb_channels: {emb_channels}",
            )
    else:  # webui
        if emb_channels == 256:
            embedder = "hubert_base_l9fp"
            emb_output_layer = 9
            use_final_proj = True
        else:
            embedder = "hubert_base_l12"
            emb_output_layer = 12
            use_final_proj = False

    return {
        "application": "VC_CLIENT",
        "version": "2.1",
        "samplingRate": sample_rate,
        "f0": 1 if is_f0 else 0,
        "embChannels": emb_channels,
        "embedder": embedder,
        "embOutputLayer": emb_output_layer,
        "useFinalProj": use_final_proj,
        "model_version": version,
    }


def export_pth_to_onnx(
    pth_path: Path | str,
    output_path: Path | str | None = None,
    is_half: bool = False,
    device: str = "cpu",
) -> Path:
    """RVC の .pth (PyTorch チェックポイント) を pure-ONNX ランタイム対応の .onnx に変換・保存する。"""
    pth_file = Path(pth_path)
    if not pth_file.exists():
        raise FileNotFoundError(f"Model file not found: {pth_file}")

    if output_path is None:
        out_file = pth_file.with_suffix(".onnx")
    else:
        out_file = Path(output_path)

    out_file.parent.mkdir(parents=True, exist_ok=True)

    with warnings.catch_warnings():
        # PyTorch JIT Tracer / weight_norm deprecation / Constant folding などの既知の警告を抑止
        warnings.simplefilter("ignore")

        cpt = torch.load(pth_file, map_location="cpu", weights_only=False)
        metadata = extract_metadata_from_checkpoint(cpt)

        is_f0 = metadata["f0"] == 1
        emb_channels = metadata["embChannels"]
        sample_rate = metadata["samplingRate"]

        dev = torch.device(device)
        if is_half and dev.type != "cuda":
            # CPU での float16 onnx export は一部オペレータで非対応となる可能性があるため float32 を推奨
            is_half = False

        # モデル構築
        if "config" in cpt:
            config = cpt["config"]
            # config の末尾は sr
            model_kwargs = {
                "spec_channels": config[0],
                "segment_size": config[1],
                "inter_channels": config[2],
                "hidden_channels": config[3],
                "filter_channels": config[4],
                "n_heads": config[5],
                "n_layers": config[6],
                "kernel_size": config[7],
                "p_dropout": config[8],
                "resblock": config[9],
                "resblock_kernel_sizes": config[10],
                "resblock_dilation_sizes": config[11],
                "upsample_rates": config[12],
                "upsample_initial_channel": config[13],
                "upsample_kernel_sizes": config[14],
                "spk_embed_dim": config[15],
                "gin_channels": config[16],
                "sr": sample_rate,
                "emb_channels": emb_channels,
                "is_half": is_half,
            }
        else:
            params = cpt["params"]
            model_kwargs = {
                **params,
                "sr": sample_rate,
                "emb_channels": emb_channels,
                "is_half": is_half,
            }

        net_g: SynthesizerTrnF0 | SynthesizerTrnNoF0
        if is_f0:
            net_g = SynthesizerTrnF0(**model_kwargs)
        else:
            net_g = SynthesizerTrnNoF0(**model_kwargs)

        net_g.eval().to(dev)
        if "weight" in cpt:
            net_g.load_state_dict(cpt["weight"], strict=False)
        elif "model" in cpt:
            net_g.load_state_dict(cpt["model"], strict=False)

        if is_half:
            net_g = net_g.half()

        # ダミー入力テンソルの準備
        feats_len = 64
        feats = torch.randn(1, feats_len, emb_channels, device=dev, dtype=torch.float16 if is_half else torch.float32)
        p_len = torch.tensor([feats_len], device=dev, dtype=torch.int64)
        sid = torch.tensor([0], device=dev, dtype=torch.int64)

        inputs: tuple[torch.Tensor, ...]
        if is_f0:
            pitch = torch.zeros(1, feats_len, device=dev, dtype=torch.int64)
            pitchf = torch.zeros(1, feats_len, device=dev, dtype=torch.float32)
            inputs = (feats, p_len, pitch, pitchf, sid)
            input_names = ["feats", "p_len", "pitch", "pitchf", "sid"]
            dynamic_axes = {
                "feats": {1: "time"},
                "pitch": {1: "time"},
                "pitchf": {1: "time"},
            }
        else:
            inputs = (feats, p_len, sid)
            input_names = ["feats", "p_len", "sid"]
            dynamic_axes = {
                "feats": {1: "time"},
            }

        output_names = ["audio"]

        logger.info(
            "Exporting PyTorch model to ONNX: %s -> %s (f0=%s, emb_channels=%s)",
            pth_file,
            out_file,
            is_f0,
            emb_channels,
        )

        # ONNX エクスポート実行（PyTorch 2.9+ では dynamo=False で TorchScript エクスポーターを指定）
        export_kwargs: dict[str, Any] = {
            "input_names": input_names,
            "output_names": output_names,
            "dynamic_axes": dynamic_axes,
            "do_constant_folding": True,
            "opset_version": 17,
            "verbose": False,
        }
        try:
            torch.onnx.export(net_g, inputs, str(out_file), dynamo=False, **export_kwargs)
        except TypeError:
            torch.onnx.export(net_g, inputs, str(out_file), **export_kwargs)

        # メタデータ書き込み
        model_onnx = onnx.load(str(out_file))

        # onnxsim 最適化（利用可能な場合）
        try:
            import onnxsim

            model_simp, check = onnxsim.simplify(model_onnx)
            if check:
                model_onnx = model_simp
                logger.debug("ONNX model successfully simplified with onnxsim.")
        except Exception as e:
            logger.debug("onnxsim simplification skipped: %s", e)

        meta = model_onnx.metadata_props.add()
        meta.key = "metadata"
        # model_version は内部管理用なので ONNX メタデータからは除いて標準キーにする
        export_metadata = {k: v for k, v in metadata.items() if k != "model_version"}
        meta.value = json.dumps(export_metadata)

        onnx.save(model_onnx, str(out_file))

    logger.info("Successfully exported ONNX model to %s", out_file)

    return out_file
