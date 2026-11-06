import tempfile
from pathlib import Path

import onnxruntime as ort
import pytest

from vcclient.voice_changer.voice_change_manager.device_manager.device_manager import DeviceManager
from vcclient.voice_changer.voice_changer_const import CoreMLCacheDir, SettingsDir


def test_coreml_device_constants():
    assert CoreMLCacheDir.name == "coreml_cache"
    assert CoreMLCacheDir.exists()
    assert CoreMLCacheDir != SettingsDir / "coreml_cache"
    assert Path(tempfile.gettempdir()) in CoreMLCacheDir.parents


def test_device_manager_coreml_provider_configuration(monkeypatch: pytest.MonkeyPatch):
    dev_mgr = DeviceManager.get_instance()

    # 1. When CoreMLExecutionProvider is available (e.g. on macOS)
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    providers, provider_options = dev_mgr.get_onnx_execution_provider(0)

    assert "CoreMLExecutionProvider" in providers
    assert "CPUExecutionProvider" in providers
    assert len(provider_options) == 2
    assert provider_options[0]["ModelFormat"] == "NeuralNetwork"
    assert provider_options[0]["MLComputeUnits"] == "ALL"
    assert provider_options[0]["RequireStaticInputShapes"] == "0"
    assert provider_options[0]["EnableOnSubgraphs"] == "0"
    assert provider_options[0]["ModelCacheDirectory"] == str(CoreMLCacheDir.resolve())

    # 1b. When device_id=1 (GPU preferred), MLComputeUnits should be CPUAndGPU
    providers_gpu, provider_options_gpu = dev_mgr.get_onnx_execution_provider(1)
    assert provider_options_gpu[0]["MLComputeUnits"] == "CPUAndGPU"

    # 2. When CoreMLExecutionProvider is unavailable, fallback to CPU
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    providers_fallback, _ = dev_mgr.get_onnx_execution_provider(0)
    assert "CoreMLExecutionProvider" not in providers_fallback
    assert "CPUExecutionProvider" in providers_fallback
