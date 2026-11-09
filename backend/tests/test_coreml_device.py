import tempfile
from pathlib import Path

import onnxruntime as ort
import pytest

from vcclient.device import DeviceConfig
from vcclient.device.providers.coreml import CoreMLCacheDir
from vcclient.voice_changer.voice_changer_const import SettingsDir


def test_coreml_device_constants():
    assert CoreMLCacheDir.name == "coreml_cache"
    assert CoreMLCacheDir.exists()
    assert CoreMLCacheDir != SettingsDir / "coreml_cache"
    assert Path(tempfile.gettempdir()) in CoreMLCacheDir.parents


def test_device_manager_coreml_provider_configuration(monkeypatch: pytest.MonkeyPatch):
    dev_ane = DeviceConfig(
        id=1,
        canonical_id="coreml:ane:0",
        provider="coreml",
        device_index=0,
        device_type="NPU",
        name="[CoreML] Apple M2 (ALL / ANE Preferred)",
        metadata={"compute_units": "ALL"},
    )
    dev_gpu = DeviceConfig(
        id=2,
        canonical_id="coreml:gpu:0",
        provider="coreml",
        device_index=0,
        device_type="GPU",
        name="[CoreML] Apple M2 (CPU + GPU / GPU Preferred)",
        metadata={"compute_units": "CPUAndGPU"},
    )

    # 1. When CoreMLExecutionProvider is available (e.g. on macOS)
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CoreMLExecutionProvider", "CPUExecutionProvider"])
    providers, provider_options = dev_ane._resolve_provider()

    assert "CoreMLExecutionProvider" in providers
    assert "CPUExecutionProvider" in providers
    assert len(provider_options) == 2
    assert provider_options[0]["ModelFormat"] == "NeuralNetwork"
    assert provider_options[0]["MLComputeUnits"] == "ALL"
    assert provider_options[0]["RequireStaticInputShapes"] == "0"
    assert provider_options[0]["EnableOnSubgraphs"] == "0"
    assert provider_options[0]["ModelCacheDirectory"] == str(CoreMLCacheDir.resolve())

    # 1b. When GPU preferred, MLComputeUnits should be CPUAndGPU
    providers_gpu, provider_options_gpu = dev_gpu._resolve_provider()
    assert provider_options_gpu[0]["MLComputeUnits"] == "CPUAndGPU"

    # 2. When CoreMLExecutionProvider is unavailable, fallback safely to CPU
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CPUExecutionProvider"])
    providers_fallback, _ = dev_ane._resolve_provider()
    assert "CoreMLExecutionProvider" not in providers_fallback
    assert "CPUExecutionProvider" in providers_fallback
