from fastapi import APIRouter

from vcclient.server.task_manager.task_manager import TaskManager
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute


class RestAPITaskManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/task-manager/tasks/{id}", self.get_task, methods=["GET"])
        self.router.add_api_route("/api/task-manager/tasks/{id}", self.delete_task, methods=["DELETE"])

    def get_task(self, id: str):
        task_manager = TaskManager.get_instance()
        return task_manager.get_task(id)

    def delete_task(self, id: str):
        task_manager = TaskManager.get_instance()
        return task_manager.delete_task(id)
