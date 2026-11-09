from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

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
