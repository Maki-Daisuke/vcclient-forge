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


@pytest.mark.parametrize(
    ("ep_metadatas", "expected_ids"),
    [
        # Hybrid laptop (iGPU at DXGI 0, single NVIDIA dGPU at DXGI 1) must still map CUDA ordinal to 0
        ([{"Description": "NVIDIA GeForce RTX 3050 Laptop GPU", "DxgiAdapterNumber": "1"}], [0]),
        # Multi-GPU with iGPU at DXGI 0
        (
            [
                {"Description": "NVIDIA GeForce RTX 4090", "DxgiAdapterNumber": "1"},
                {"Description": "NVIDIA GeForce RTX 3060", "DxgiAdapterNumber": "2"},
            ],
            [0, 1],
        ),
        # Linux / environments without DxgiAdapterNumber
        ([{"Description": "NVIDIA GeForce RTX 4090"}], [0]),
    ],
)
def test_detect_nvidia_gpus_uses_cuda_ordinal_not_dxgi_adapter(
    monkeypatch: pytest.MonkeyPatch,
    ep_metadatas: list[dict[str, str]],
    expected_ids: list[int],
):
    from types import SimpleNamespace

    monkeypatch.setattr(cuda_module, "is_cuda_available", lambda: True)
    fake_eps = [
        SimpleNamespace(ep_name="CPUExecutionProvider", device=SimpleNamespace(metadata={"Description": "CPU"})),
        *[
            SimpleNamespace(ep_name="CUDAExecutionProvider", device=SimpleNamespace(metadata=meta))
            for meta in ep_metadatas
        ],
    ]
    monkeypatch.setattr(ort, "get_ep_devices", lambda: fake_eps)

    gpus = detect_nvidia_gpus()
    assert [g.device_id_int for g in gpus] == expected_ids
    assert [g.device_id for g in gpus] == [str(i) for i in expected_ids]
