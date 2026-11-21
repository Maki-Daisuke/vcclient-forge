from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from vcclient.device import DeviceConfig, get_device_catalog, reload_device_catalog
from vcclient.initializer import recommend_compute_device
from vcclient.server.api_common import DomainApiError, DomainApiRoute, ensure_session_stopped
from vcclient.voice_changer.audio_device_manager import (
    get_audio_input_devices,
    get_audio_output_devices,
    reload_audio_devices,
)
from vcclient.voice_changer.data_types.data_types import AudioDevice
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface


class AudioDevicesResponse(BaseModel):
    """Cached or freshly probed input and output PortAudio device lists."""

    inputs: list[AudioDevice]
    outputs: list[AudioDevice]


class ComputeDeviceRecommendation(BaseModel):
    """Recommended compute device returned without mutating persisted settings."""

    compute_device_id: int
    device: DeviceConfig


class RestAPIDevices:
    """Domain API router for audio and compute device discovery, reload, and auto-selection."""

    def __init__(self) -> None:
        self.router = APIRouter(route_class=DomainApiRoute)
        self.router.add_api_route("/api/devices/audio", self.get_audio_devices, methods=["GET"])
        self.router.add_api_route("/api/devices/audio/reload", self.post_audio_devices_reload, methods=["POST"])
        self.router.add_api_route("/api/devices/compute", self.get_compute_devices, methods=["GET"])
        self.router.add_api_route("/api/devices/compute/reload", self.post_compute_devices_reload, methods=["POST"])
        self.router.add_api_route("/api/devices/compute/auto-select", self.post_compute_auto_select, methods=["POST"])

    def get_audio_devices(self) -> AudioDevicesResponse:
        return AudioDevicesResponse(
            inputs=get_audio_input_devices(),
            outputs=get_audio_output_devices(),
        )

    def post_audio_devices_reload(self) -> AudioDevicesResponse:
        local = LocalVoiceChangerInterface.get_instance()
        with local.lifecycle_lock:
            ensure_session_stopped("Cannot reload audio devices while a conversion session is active.")
            inputs, outputs = reload_audio_devices()
        return AudioDevicesResponse(inputs=inputs, outputs=outputs)

    def get_compute_devices(self) -> list[DeviceConfig]:
        return get_device_catalog()

    def post_compute_devices_reload(self) -> list[DeviceConfig]:
        local = LocalVoiceChangerInterface.get_instance()
        with local.lifecycle_lock:
            ensure_session_stopped("Cannot reload compute devices while a conversion session is active.")
            return reload_device_catalog()

    def post_compute_auto_select(self) -> ComputeDeviceRecommendation:
        local = LocalVoiceChangerInterface.get_instance()
        with local.lifecycle_lock:
            ensure_session_stopped("Cannot run compute device auto-selection while a conversion session is active.")
            try:
                device = recommend_compute_device()
            except LookupError as exc:
                raise DomainApiError(409, "model_not_found", str(exc)) from exc
            except RuntimeError as exc:
                raise DomainApiError(500, "compute_auto_select_failed", str(exc)) from exc
        return ComputeDeviceRecommendation(compute_device_id=device.id, device=device)
