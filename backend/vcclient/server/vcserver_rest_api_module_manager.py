from fastapi import APIRouter

from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.module_manager.module_manager import ModuleManager


class RestAPIModuleManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/module-manager/modules", self.get_modules, methods=["GET"])
        self.router.add_api_route(
            "/api/module-manager/modules/operation/download_applio_modules",
            self.post_download_applio_modules,
            methods=["POST"],
        )

    def get_modules(self, reload: bool = False):
        moduele_manager = ModuleManager.get_instance()
        if reload:
            moduele_manager.reload()
        return moduele_manager.get_modules()

    async def post_download_applio_modules(self):
        return None
