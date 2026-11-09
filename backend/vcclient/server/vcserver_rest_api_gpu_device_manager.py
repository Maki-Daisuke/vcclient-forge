from fastapi import APIRouter

from vcclient.device import (
    DeviceConfig,
    get_device_catalog,
    reload_device_catalog,
)
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute


class RestAPIGPUDeviceManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/gpu-device-manager/devices", self.get_devices, methods=["GET"])

    def get_devices(self, reload: bool = False) -> list[DeviceConfig]:
        if reload:
            reload_device_catalog()
        return get_device_catalog()
