import uuid
from typing import Literal

from pydantic import BaseModel


class Task(BaseModel):
    id: str
    status: Literal["not started", "done", "progress"] = "not started"
    progress: float = 0
    result: Literal["not finished", "success", "fail"] = "not finished"


class TaskManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):

        self.tasks = []

    def add_task(self):

        task = Task(id=str(uuid.uuid4()))

        self.tasks.append(task)

        return task.id

    def get_all_tasks(self):

        return self.tasks

    def get_task(self, task_id=None):

        for task in self.tasks:
            if task.id == task_id:
                return task

        return None

    def update_task(
        self,
        task_id=None,
        status=None,
        progress: float = 0,
        result: Literal["not finished", "success", "fail"] = "not finished",
    ):

        task = self.get_task(task_id)

        if task is not None:
            if status is not None:
                task.status = status

            task.progress = progress

            task.result = result

            return None

    def delete_task(self, task_id=None):

        task = self.get_task(task_id)

        if task is not None:
            self.tasks.remove(task)

            return None
