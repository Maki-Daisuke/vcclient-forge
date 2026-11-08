from fastapi import APIRouter

from vcclient.device import (
    get_cuda_info,
    get_gpu_info,
    is_cuda_available,
    reload_gpu_devices,
)
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute


class RestAPIGPUDeviceManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/gpu-device-manager/devices", self.get_devices, methods=["GET"])

    def get_devices(self, reload: bool = False):
        if reload:
            reload_gpu_devices()
        if not is_cuda_available():
            return get_gpu_info()
        return get_cuda_info()
