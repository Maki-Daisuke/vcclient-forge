import onnxruntime as ort
import pytest

from vcclient.device.providers import cuda as cuda_module
from vcclient.device.providers.cuda import (
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


def test_detect_nvidia_gpus_handles_na_vram(monkeypatch: pytest.MonkeyPatch):
    """Ensure GPUs reporting [N/A] memory (e.g. Unified Memory GB10) don't crash nvidia-smi parsing."""
    import subprocess
    from unittest.mock import MagicMock

    monkeypatch.setattr(cuda_module, "is_cuda_available", lambda: True)
    # Force native detection to fail so it falls back to nvidia-smi
    monkeypatch.setattr(ort, "get_ep_devices", lambda: (_ for _ in ()).throw(RuntimeError("fail")))

    fake_stdout = "0, NVIDIA GB10, [N/A]\n1, NVIDIA RTX 4090, 24576\n"
    mock_run = MagicMock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_stdout, stderr=""))
    monkeypatch.setattr(subprocess, "run", mock_run)

    gpus = detect_nvidia_gpus()
    assert len(gpus) == 2
    assert gpus[0].name == "[CUDA] NVIDIA GB10"
    assert gpus[0].adapter_ram == 0
    assert gpus[0].device_id_int == 0
    assert gpus[1].name == "[CUDA] NVIDIA RTX 4090"
    assert gpus[1].adapter_ram == 24576 * 1024 * 1024
    assert gpus[1].device_id_int == 1
