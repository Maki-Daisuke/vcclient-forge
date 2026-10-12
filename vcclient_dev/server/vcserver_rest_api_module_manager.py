import asyncio

from fastapi import APIRouter
from tqdm import tqdm

from vcclient_dev.server.task_manager.task_manager import TaskManager
from vcclient_dev.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient_dev.voice_changer.data_types.module_manager_data_types import ModuleDownloadStatus
from vcclient_dev.voice_changer.module_manager.module_manager import ModuleManager


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
        self.router.add_api_route("/api_module-manager_modules", self.get_modules, methods=["GET"])
        self.router.add_api_route(
            "/api_module-manager_modules_operation_download_applio_modules",
            self.post_download_applio_modules,
            methods=["POST"],
        )

    def get_modules(self, reload: bool = False):
        moduele_manager = ModuleManager.get_instance()
        if reload:
            moduele_manager.reload()
        return moduele_manager.get_modules()

    async def run_download(self, task_id: str):
        module_manager = ModuleManager.get_instance()
        task_manager = TaskManager.get_instance()
        pbar_dict_module = {}

        def download_callback(status: list[ModuleDownloadStatus]):
            position = 0
            for s in status:
                if s.id not in pbar_dict_module:
                    pbar_dict_module[s.id] = tqdm(
                        total=100, unit="%", desc=f"Downloading {s.id[:10]}", leave=False, position=position
                    )
                    position += 1
                pbar = pbar_dict_module[s.id]
                pbar.n = int(s.progress * 100)
                all_progress = sum([s.progress for s in status]) / len(status)
                task_manager.update_task(task_id, "progress", all_progress, result="not finished")
                pbar.refresh()
                if s.status == "done":
                    pbar.close()
                    all_task_done = all([s.status == "done" for s in status])
                    if all_task_done:
                        task_manager.update_task(task_id, "done", progress=position / len(status), result="success")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, module_manager.download_applio_modules, download_callback)

    async def post_download_applio_modules(self):
        module_manager = ModuleManager.get_instance()
        if module_manager.applio_modules_ready() is True:
            return None
        task_manager = TaskManager.get_instance()
        task_id = task_manager.add_task()
        task_manager.update_task(task_id, "progress", progress=0)
        task = task_manager.get_task(task_id)
        asyncio.create_task(self.run_download(task_id))
        return task
