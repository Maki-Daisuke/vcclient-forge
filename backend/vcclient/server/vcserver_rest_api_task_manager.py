from fastapi import APIRouter

from vcclient.server.task_manager import Task, delete_task, get_task
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute


class RestAPITaskManager:
    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/task-manager/tasks/{id}", self.get_task, methods=["GET"])
        self.router.add_api_route("/api/task-manager/tasks/{id}", self.delete_task, methods=["DELETE"])

    def get_task(self, id: str) -> Task | None:
        return get_task(id)

    def delete_task(self, id: str) -> None:
        delete_task(id)
