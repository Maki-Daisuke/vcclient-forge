from fastapi import APIRouter

from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.data_types.data_types import ModuleStatus
from vcclient.voice_changer.module_manager import get_modules, reload_modules


class RestAPIModuleManager:
    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/module-manager/modules", self.get_modules, methods=["GET"])
        self.router.add_api_route(
            "/api/module-manager/modules/operation/download_applio_modules",
            self.post_download_applio_modules,
            methods=["POST"],
        )

    def get_modules(self, reload: bool = False) -> list[ModuleStatus]:
        if reload:
            reload_modules()
        return get_modules()

    async def post_download_applio_modules(self) -> None:
        return None
