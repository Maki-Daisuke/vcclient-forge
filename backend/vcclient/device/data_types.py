from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, computed_field

if TYPE_CHECKING:
    from pathlib import Path

    import onnxruntime

ExecutionProviderType = Literal[
    "cpu",
    "cuda",
    "directml",
    "openvino",
    "coreml",
]

DeviceType = Literal["CPU", "GPU", "NPU"]


class DeviceConfig(BaseModel):
    """Unified, provider-agnostic compute device descriptor."""

    id: int = Field(
        ...,
        description="Sequential zero-based catalog index (0 for CPU, 1..N for accelerators).",
    )
    canonical_id: str = Field(
        ...,
        description="Deterministic string identifier (e.g. 'cpu', 'cuda:0', 'dml:0', 'openvino:gpu:0', 'openvino:npu:0').",
    )
    provider: ExecutionProviderType = Field(
        ...,
        description="Target execution provider backend.",
    )
    device_index: int = Field(
        default=0,
        description="Physical hardware/adapter index within the provider space.",
    )
    device_type: DeviceType = Field(
        default="GPU",
        description="Hardware execution classification (CPU, GPU, or NPU).",
    )
    name: str = Field(
        default="",
        description="Human-readable display name with provider prefix (e.g. '[DirectML] Intel(R) Arc(TM) Graphics').",
    )
    adapter_ram: int = Field(
        default=0,
        description="Dedicated video/adapter memory in bytes (0 for host-shared/unified memory).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata (DXGI LUID, OpenVINO 'ov_device', CoreML 'compute_units', etc.).",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def device_id_int(self) -> int:
        """Exposes catalog index as device_id_int in JSON responses for legacy web_front contracts."""
        return self.id

    @computed_field  # type: ignore[prop-decorator]
    @property
    def device_id(self) -> str:
        """Exposes canonical_id as device_id in JSON responses for legacy GPUInfo compatibility."""
        return self.canonical_id

    def is_cpu(self) -> bool:
        return self.id == 0 or self.provider == "cpu" or self.device_type == "CPU"

    def _fallback_to_cpu(self, requested_ep: str) -> tuple[list[str], list[dict[str, Any]]]:
        from vcclient.logger import logger

        from .providers.cpu import resolve_cpu_provider

        logger.warning(
            "%s requested for %s but execution provider not available, falling back to CPU",
            requested_ep,
            self.canonical_id,
        )
        return resolve_cpu_provider()

    def _resolve_provider(self) -> tuple[list[str], list[dict[str, Any]]]:
        """Resolve ONNX Runtime execution provider and options for this device descriptor."""
        if self.is_cpu():
            from .providers.cpu import resolve_cpu_provider

            return resolve_cpu_provider()

        import onnxruntime as ort

        if self.provider == "cuda":
            if "CUDAExecutionProvider" in ort.get_available_providers():
                return (["CUDAExecutionProvider"], [{"device_id": self.device_index}])
            return self._fallback_to_cpu("CUDAExecutionProvider")

        if self.provider == "directml":
            if "DmlExecutionProvider" in ort.get_available_providers():
                return (["DmlExecutionProvider", "CPUExecutionProvider"], [{"device_id": self.device_index}, {}])
            return self._fallback_to_cpu("DmlExecutionProvider")

        if self.provider == "openvino":
            from .providers.openvino import is_openvino_available, resolve_openvino_device_provider

            if not is_openvino_available():
                return self._fallback_to_cpu("OpenVINOExecutionProvider")
            return resolve_openvino_device_provider(self)

        if self.provider == "coreml":
            if "CoreMLExecutionProvider" in ort.get_available_providers():
                from .providers.coreml import resolve_coreml_device_provider

                return resolve_coreml_device_provider(self)
            return self._fallback_to_cpu("CoreMLExecutionProvider")

        from .providers.cpu import resolve_cpu_provider

        return resolve_cpu_provider()

    def _configure_session_options(
        self,
        so: onnxruntime.SessionOptions | None = None,
    ) -> onnxruntime.SessionOptions:
        """Configure SessionOptions with hardware/EP-specific performance and stability flags."""
        import onnxruntime as ort

        if so is None:
            so = ort.SessionOptions()
            so.log_severity_level = 3

        if self.provider == "openvino":
            from .providers.openvino import configure_openvino_session_options

            configure_openvino_session_options(so, device=self)
        return so

    def create_session(
        self,
        model_payload: str | bytes | Path,
        patch_type: str | None = None,
        so: onnxruntime.SessionOptions | None = None,
    ) -> tuple[onnxruntime.InferenceSession, list[str], list[dict[str, Any]]]:
        """Create an ONNX InferenceSession optimized for this compute device descriptor.

        Handles EP resolution, provider options, device-specific graph patches,
        and NPU-to-CPU vocoder safety fallbacks.
        """
        from pathlib import Path

        import onnxruntime as ort

        from vcclient.logger import logger

        target_device = self

        # RVC HiFi-GAN vocoder exceeds client NPU SRAM capacity; fall back to CPU if NPU is selected pipeline-wide
        if target_device.provider == "openvino" and target_device.device_type == "NPU" and patch_type == "rvc":
            logger.warning("RVC vocoder is not supported on NPU; falling back to CPU for synthesis session.")
            from .device_manager import get_device

            target_device = get_device(0)

        providers_list, provider_options = target_device._resolve_provider()

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

        so = target_device._configure_session_options(so)

        path_or_bytes = str(model_payload) if isinstance(model_payload, Path) else model_payload

        # When SessionOptions has already been configured with providers (e.g. via add_provider_for_devices),
        # passing providers or provider_options to InferenceSession causes ONNX Runtime to override
        # and discard the SessionOptions configuration, leading to silent CPU fallback for dynamic plugins like OpenVINO.
        if hasattr(so, "has_providers") and so.has_providers():
            session = ort.InferenceSession(path_or_bytes, sess_options=so)
        else:
            session = ort.InferenceSession(
                path_or_bytes,
                sess_options=so,
                providers=providers_list,
                provider_options=provider_options,
            )

        name = (
            model_payload.name
            if isinstance(model_payload, Path)
            else (model_payload if isinstance(model_payload, str) else "<bytes>")
        )
        logger.info("ONNX session initialized for %s with active providers: %s", name, session.get_providers())
        return session, providers_list, provider_options
