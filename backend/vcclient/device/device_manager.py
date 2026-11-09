from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any

import onnxruntime

from vcclient.logger import logger
from vcclient.voice_changer.data_types.data_types import GPUInfo

from . import providers
from .data_types import DeviceConfig, DeviceType

# --- Hardware Detection & GPU Device Management ---

_gpu_info: list[GPUInfo] = []
_cuda_info: list[GPUInfo] = []
_cuda_available: bool = False
_device_catalog: list[DeviceConfig] = []


def _detect_linux_gpus() -> list[GPUInfo]:
    gpu_list: list[GPUInfo] = []
    try:
        cmd = ["lspci"]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            idx = 0
            for line in result.stdout.splitlines():
                if "VGA compatible controller" in line or "3D controller" in line:
                    parts = line.split(":", 2)
                    name = parts[-1].strip() if len(parts) >= 3 else line
                    gpu_list.append(
                        GPUInfo(
                            name=name,
                            device_id=str(idx),
                            adapter_ram=0,
                            device_id_int=idx,
                        )
                    )
                    idx += 1
    except Exception as e:
        logger.debug("Linux GPU detection skipped: %s", e)
    return gpu_list


def get_driver_and_cuda_version() -> tuple[str | None, str | None]:
    return providers.cuda.get_driver_and_cuda_version()


def reload_device_catalog() -> list[DeviceConfig]:
    """Discover available execution providers and construct sequential DeviceConfig catalog."""
    global _device_catalog
    catalog: list[DeviceConfig] = []

    # 1. Index 0 is strictly CPU
    catalog.append(
        DeviceConfig(
            id=0,
            canonical_id="cpu",
            provider="cpu",
            device_index=0,
            device_type="CPU",
            name="CPU",
            adapter_ram=0,
        )
    )

    # 2. NVIDIA GPUs (CUDA)
    if is_cuda_available():
        nvidia_gpus = providers.cuda.detect_nvidia_gpus()
        for g in nvidia_gpus:
            catalog.append(
                DeviceConfig(
                    id=len(catalog),
                    canonical_id=f"cuda:{g.device_id_int}",
                    provider="cuda",
                    device_index=g.device_id_int,
                    device_type="GPU",
                    name=g.name,
                    adapter_ram=g.adapter_ram,
                )
            )

    # 3. DirectML (Windows) / CoreML (macOS) / Linux GPUs
    system = platform.system()
    if system == "Windows":
        sys_gpus = providers.directml.detect_windows_gpus()
        for g in sys_gpus:
            catalog.append(
                DeviceConfig(
                    id=len(catalog),
                    canonical_id=f"dml:{g.device_id_int}",
                    provider="directml",
                    device_index=g.device_id_int,
                    device_type="GPU",
                    name=g.name,
                    adapter_ram=g.adapter_ram,
                )
            )
    elif system == "Darwin":
        sys_gpus = providers.coreml.detect_macos_gpus()
        for g in sys_gpus:
            is_ane = g.device_id_int % 2 == 0
            compute_units = "ALL" if is_ane else "CPUAndGPU"
            dtype: DeviceType = "NPU" if is_ane else "GPU"
            canonical_id = f"coreml:ane:{g.device_id_int // 2}" if is_ane else f"coreml:gpu:{g.device_id_int // 2}"
            catalog.append(
                DeviceConfig(
                    id=len(catalog),
                    canonical_id=canonical_id,
                    provider="coreml",
                    device_index=g.device_id_int,
                    device_type=dtype,
                    name=g.name,
                    adapter_ram=g.adapter_ram,
                    metadata={"compute_units": compute_units},
                )
            )
    elif system == "Linux" and not is_cuda_available():
        sys_gpus = _detect_linux_gpus()
        for g in sys_gpus:
            catalog.append(
                DeviceConfig(
                    id=len(catalog),
                    canonical_id=f"gpu:{g.device_id_int}",
                    provider="cpu",
                    device_index=g.device_id_int,
                    device_type="GPU",
                    name=g.name,
                    adapter_ram=g.adapter_ram,
                )
            )

    # 4. OpenVINO (Windows / Linux)
    if is_openvino_available():
        try:
            ov_devices = providers.openvino.detect_openvino_devices()
            for dev in ov_devices:
                catalog.append(
                    DeviceConfig(
                        id=len(catalog),
                        canonical_id=dev.canonical_id,
                        provider="openvino",
                        device_index=dev.device_index,
                        device_type=dev.device_type,
                        name=dev.name,
                        adapter_ram=dev.adapter_ram,
                        metadata=dev.metadata,
                    )
                )
        except Exception as e:
            logger.debug("OpenVINO detection skipped: %s", e)

    _device_catalog = catalog
    logger.info(
        "Device catalog initialized with %s targets: %s",
        len(_device_catalog),
        [d.canonical_id for d in _device_catalog],
    )
    return _device_catalog


def get_device_catalog() -> list[DeviceConfig]:
    """Return active device catalog, reloading if empty."""
    if not _device_catalog:
        reload_device_catalog()
    return _device_catalog


def get_device(device_id: int) -> DeviceConfig:
    """Retrieve DeviceConfig by catalog index in O(1) time."""
    catalog = get_device_catalog()
    if 0 <= device_id < len(catalog):
        return catalog[device_id]
    # Negative values (e.g. legacy default -1) or out-of-bounds indices fall back to CPU (Index 0)
    return catalog[0]


def resolve_legacy_device_id(legacy_id: int) -> DeviceConfig:
    """Resolve legacy integer sentinels (-1, 1000) or direct catalog indices to DeviceConfig."""
    catalog = get_device_catalog()
    if legacy_id == -1:
        return catalog[0]
    if legacy_id == 1000:
        for dev in catalog:
            if dev.provider == "openvino":
                return dev
        return catalog[0]
    if 0 <= legacy_id < len(catalog):
        return catalog[legacy_id]
    return catalog[0]


def reload_gpu_devices() -> list[GPUInfo]:
    global _gpu_info, _cuda_info, _cuda_available
    logger.info("Reloading GPU info")

    # Reload unified DeviceConfig catalog
    reload_device_catalog()

    # 1. NVIDIA GPU の検出 (Windows / Linux 共通)
    nvidia_gpus = providers.cuda.detect_nvidia_gpus()

    # 2. プラットフォームごとのシステムGPU検出
    system = platform.system()
    if system == "Windows":
        sys_gpus = providers.directml.detect_windows_gpus()
    elif system == "Darwin":
        sys_gpus = providers.coreml.detect_macos_gpus()
    elif system == "Linux":
        sys_gpus = _detect_linux_gpus()
    else:
        sys_gpus = []

    cpu_entry = GPUInfo(name="CPU", device_id="-1", adapter_ram=0, device_id_int=-1)

    # システムGPUリスト (CPU + 検出されたGPU)
    all_sys = [cpu_entry]
    detected = nvidia_gpus if nvidia_gpus else sys_gpus
    for g in detected:
        if g.name.lower() != "cpu":
            all_sys.append(g)

    # 3. OpenVINO Execution Provider (GPU)
    try:
        if is_openvino_available():
            all_sys.extend(providers.openvino.detect_openvino_gpus())
    except Exception as e:
        logger.debug("OpenVINO detection skipped: %s", e)

    _gpu_info = all_sys

    # CUDA/アクセラレータGPUリスト
    all_cuda = [cpu_entry]
    for g in nvidia_gpus:
        all_cuda.append(g)
    _cuda_info = all_cuda

    _cuda_available = is_cuda_available()
    cuda_driver_version, _ = get_driver_and_cuda_version()

    logger.info("GPU[sys]: %s", _gpu_info)
    logger.info(
        "GPU[cuda]: available:%s, num:%s, driver_version:%s",
        _cuda_available,
        len(nvidia_gpus),
        cuda_driver_version,
    )
    logger.info("GPU[cuda_info]: %s", _cuda_info)
    return _gpu_info


# Alias for backward-compatibility if needed
reload = reload_gpu_devices


def get_gpu_info() -> list[GPUInfo]:
    if not _gpu_info:
        reload_gpu_devices()
    return _gpu_info


def get_cuda_info() -> list[GPUInfo]:
    if not _cuda_info:
        reload_gpu_devices()
    return _cuda_info


def is_cuda_available() -> bool:
    """Check if CUDAExecutionProvider is available in the current runtime environment."""
    return providers.cuda.is_cuda_available()


# --- ONNX Runtime Execution Provider & Session Management ---


def is_openvino_available() -> bool:
    """Check if OpenVINOExecutionProvider is available in the current runtime environment."""
    return providers.openvino.is_openvino_available()


def find_openvino_ep_device(preferred_type: str = "GPU") -> Any | None:
    """Find the most suitable OpenVINO EP device from ort.get_ep_devices()."""
    return providers.openvino.find_openvino_ep_device(preferred_type)


def configure_session_options(
    so: onnxruntime.SessionOptions,
    ep_providers_or_device: list[str] | DeviceConfig | None = None,
) -> onnxruntime.SessionOptions:
    """Configure SessionOptions with hardware/EP-specific performance and stability flags."""
    if isinstance(ep_providers_or_device, DeviceConfig):
        if ep_providers_or_device.provider == "openvino":
            providers.openvino.configure_openvino_session_options(so, device=ep_providers_or_device)
    elif isinstance(ep_providers_or_device, list):
        if any("openvino" in p.lower() for p in ep_providers_or_device):
            providers.openvino.configure_openvino_session_options(so)
    return so


def create_inference_session(
    model_payload: str | bytes | Path,
    providers: list[str],
    provider_options: list[dict] | None = None,
    so: onnxruntime.SessionOptions | None = None,
    device: DeviceConfig | None = None,
) -> onnxruntime.InferenceSession:
    if so is None:
        so = onnxruntime.SessionOptions()
        so.log_severity_level = 3
    configure_session_options(so, device if device is not None else providers)

    path_or_bytes = str(model_payload) if isinstance(model_payload, Path) else model_payload

    # When SessionOptions has already been configured with providers (e.g. via add_provider_for_devices),
    # passing providers or provider_options to InferenceSession causes ONNX Runtime to override
    # and discard the SessionOptions configuration, leading to silent CPU fallback for dynamic plugins like OpenVINO.
    if hasattr(so, "has_providers") and so.has_providers():
        session = onnxruntime.InferenceSession(path_or_bytes, sess_options=so)
    else:
        session = onnxruntime.InferenceSession(
            path_or_bytes,
            sess_options=so,
            providers=providers,
            provider_options=provider_options,
        )

    name = (
        model_payload.name
        if isinstance(model_payload, Path)
        else (model_payload if isinstance(model_payload, str) else "<bytes>")
    )
    logger.info("ONNX session initialized for %s with active providers: %s", name, session.get_providers())
    return session


def resolve_provider_for_device(
    device: DeviceConfig,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Resolve ONNX Runtime execution provider and options for a typed DeviceConfig."""
    if device.is_cpu():
        return providers.cpu.resolve_cpu_provider()

    if device.provider == "cuda":
        available = onnxruntime.get_available_providers()
        if "CUDAExecutionProvider" in available:
            return (["CUDAExecutionProvider"], [{"device_id": device.device_index}])
        logger.warning(
            "CUDA requested for %s but CUDAExecutionProvider not available, falling back to CPU",
            device.canonical_id,
        )
        return providers.cpu.resolve_cpu_provider()

    if device.provider == "directml":
        available = onnxruntime.get_available_providers()
        if "DmlExecutionProvider" in available:
            return (["DmlExecutionProvider", "CPUExecutionProvider"], [{"device_id": device.device_index}, {}])
        logger.warning(
            "DirectML requested for %s but DmlExecutionProvider not available, falling back to CPU",
            device.canonical_id,
        )
        return providers.cpu.resolve_cpu_provider()

    if device.provider == "openvino":
        return providers.openvino.resolve_openvino_device_provider(device)

    if device.provider == "coreml":
        available = onnxruntime.get_available_providers()
        if "CoreMLExecutionProvider" in available:
            compute_units = device.metadata.get("compute_units", "ALL")
            coreml_options: dict[str, Any] = {
                "ModelFormat": "NeuralNetwork",
                "MLComputeUnits": compute_units,
                "RequireStaticInputShapes": "0",
                "EnableOnSubgraphs": "0",
            }
            try:
                providers.coreml.CoreMLCacheDir.mkdir(parents=True, exist_ok=True)
                coreml_options["ModelCacheDirectory"] = str(providers.coreml.CoreMLCacheDir.resolve())
            except Exception:
                pass
            return (["CoreMLExecutionProvider", "CPUExecutionProvider"], [coreml_options, {}])
        logger.warning(
            "CoreML requested for %s but CoreMLExecutionProvider not available, falling back to CPU",
            device.canonical_id,
        )
        return providers.cpu.resolve_cpu_provider()

    return providers.cpu.resolve_cpu_provider()


def _resolve_onnx_execution_provider(device_id: int) -> tuple[list[str], list[dict[str, Any]]]:
    available_providers = onnxruntime.get_available_providers()
    logger.info("available_providers: %s", available_providers)

    # 1. OpenVINO Execution Provider
    ov_res = providers.openvino.resolve_openvino_provider(device_id, available=is_openvino_available())
    if ov_res is not None:
        return ov_res

    # 2. CUDA Execution Provider
    cuda_info = get_cuda_info()
    gpu_info = get_gpu_info()
    cuda_len = len(cuda_info)
    gpu_len = len(gpu_info) - 1
    gpu_num = max(cuda_len, gpu_len)
    logger.info("gpu_num: %s, cuda_len: %s, gpu_len: %s", gpu_num, cuda_len, gpu_len)

    cuda_res = providers.cuda.resolve_cuda_provider(device_id, gpu_num, available_providers)
    if cuda_res is not None:
        return cuda_res

    # 3. DirectML Execution Provider
    dml_res = providers.directml.resolve_directml_provider(device_id, available_providers)
    if dml_res is not None:
        return dml_res

    # 4. CoreML Execution Provider
    coreml_res = providers.coreml.resolve_coreml_provider(device_id, available_providers)
    if coreml_res is not None:
        return coreml_res

    # 5. Default CPU Execution Provider
    return providers.cpu.resolve_cpu_provider()


def get_onnx_execution_provider(device_id: int) -> tuple[list[str], list[dict[str, Any]]]:
    res = _resolve_onnx_execution_provider(device_id)
    logger.info("get_onnx_execution_provider: %s", res)
    return res


def create_pipeline_session(
    model_payload: str | bytes | Path,
    device: DeviceConfig | int | None = None,
    patch_type: str | None = None,
    so: onnxruntime.SessionOptions | None = None,
    *,
    device_id: DeviceConfig | int | None = None,
) -> tuple[onnxruntime.InferenceSession, list[str], list[dict[str, Any]]]:
    """Create an ONNX InferenceSession for pipeline components, resolving EPs and hardware patches.

    Args:
        model_payload: Model file path or in-memory bytes.
        device: Target DeviceConfig or catalog integer ID (0 for CPU, >= 1 for accelerators, or legacy sentinel).
        patch_type: Optional hardware patch mode ("rvc" for SineGen 3D->4D, "rmvpe" for Clip min bound).
        so: Optional custom SessionOptions.
        device_id: Backward-compatible keyword alias for device.

    Returns:
        tuple of (session, candidate_providers, candidate_provider_options).
    """
    target = device if device is not None else (device_id if device_id is not None else 0)

    if isinstance(target, DeviceConfig):
        resolved_device = target
        if resolved_device.provider == "openvino" and resolved_device.device_type == "NPU" and patch_type == "rvc":
            logger.warning("RVC vocoder is not supported on NPU; falling back to CPU for synthesis session.")
            resolved_device = get_device(0)
        providers_list, provider_options = resolve_provider_for_device(resolved_device)
    else:
        providers_list, provider_options = get_onnx_execution_provider(target)
        resolved_device = resolve_legacy_device_id(target)

    if any("openvino" in p.lower() for p in providers_list):
        if patch_type == "rvc":
            try:
                from .openvino_patch import patch_rvc_model_for_openvino

                model_payload = patch_rvc_model_for_openvino(model_payload)
            except Exception as e:
                logger.warning("Failed to apply OpenVINO 4D SineGen patch to %s: %s", model_payload, e)
        elif patch_type == "rmvpe":
            try:
                from .openvino_patch import patch_rmvpe_model_for_openvino

                model_payload = patch_rmvpe_model_for_openvino(model_payload)
            except Exception as e:
                logger.warning("Failed to apply OpenVINO patch to RMVPE model %s: %s", model_payload, e)

    try:
        session = create_inference_session(
            model_payload,
            providers_list,
            provider_options,
            so=so,
            device=resolved_device,
        )
    except TypeError as e:
        if "device" in str(e):
            session = create_inference_session(
                model_payload,
                providers_list,
                provider_options,
                so=so,
            )
        else:
            raise
    return session, providers_list, provider_options
