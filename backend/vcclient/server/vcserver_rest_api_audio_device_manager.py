from fastapi import APIRouter

from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.audio_device_manager import (
    get_audio_input_devices,
    get_audio_output_devices,
    reload_audio_devices,
)


class RestAPIAudioDeviceManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/audio-device-manager/input_devices", self.get_input_devices, methods=["GET"])
        self.router.add_api_route("/api/audio-device-manager/output_devices", self.get_output_devices, methods=["GET"])

    def get_input_devices(self, reload: bool = False):
        if reload:
            reload_audio_devices()
        return get_audio_input_devices()

    def get_output_devices(self, reload: bool = False):
        if reload:
            reload_audio_devices()
        return get_audio_output_devices()
