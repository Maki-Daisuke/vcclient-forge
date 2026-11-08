import onnxruntime as ort
import pytest

from vcclient.voice_changer.voice_change_manager.device_manager.providers import cuda as cuda_module
from vcclient.voice_changer.voice_change_manager.device_manager.providers.cuda import (
    detect_nvidia_gpus,
    is_cuda_available,
    resolve_cuda_provider,
)


def test_is_cuda_available(monkeypatch: pytest.MonkeyPatch):
    # When CUDAExecutionProvider is present in available providers
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"])
    assert is_cuda_available() is True

    # When CUDAExecutionProvider is not present (standard edition)
    monkeypatch.setattr(ort, "get_available_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"])
    monkeypatch.setattr(ort, "get_ep_devices", lambda: [])
    assert is_cuda_available() is False


def test_detect_nvidia_gpus_respects_cuda_availability(monkeypatch: pytest.MonkeyPatch):
    # When CUDA EP is unavailable, detect_nvidia_gpus must return [] even if nvidia-smi exists
    monkeypatch.setattr(cuda_module, "is_cuda_available", lambda: False)
    assert detect_nvidia_gpus() == []

    # When CUDA EP is available, detect_nvidia_gpus should detect devices
    monkeypatch.setattr(cuda_module, "is_cuda_available", lambda: True)
    # Mocking ort.get_ep_devices or letting it run
    gpus = detect_nvidia_gpus()
    assert isinstance(gpus, list)


def test_resolve_cuda_provider():
    # CUDA available
    res = resolve_cuda_provider(0, gpu_num=1, available_providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    assert res is not None
    providers, opts = res
    assert providers == ["CUDAExecutionProvider"]
    assert opts == [{"device_id": 0}]

    # CUDA unavailable
    res_none = resolve_cuda_provider(0, gpu_num=1, available_providers=["CPUExecutionProvider"])
    assert res_none is None
