from fastapi import APIRouter

from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.auido_device_manager.audio_device_manager import AudioDeviceManager


class RestAPIAudioDeviceManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/audio-device-manager/input_devices", self.get_input_devices, methods=["GET"])
        self.router.add_api_route("/api/audio-device-manager/output_devices", self.get_output_devices, methods=["GET"])
        self.router.add_api_route("/api_audio-device-manager_input_devices", self.get_input_devices, methods=["GET"])
        self.router.add_api_route("/api_audio-device-manager_output_devices", self.get_output_devices, methods=["GET"])

    def get_input_devices(self, reload: bool = False):
        audio_device_manager = AudioDeviceManager.get_instance()
        if reload:
            audio_device_manager.reload_device()
        return audio_device_manager.get_audio_input_devices()

    def get_output_devices(self, reload: bool = False):
        audio_device_manager = AudioDeviceManager.get_instance()
        if reload:
            audio_device_manager.reload_device()
        return audio_device_manager.get_audio_output_devices()
