import uuid
from typing import Literal

from pydantic import BaseModel

TaskStatus = Literal["not started", "done", "progress"]
TaskResult = Literal["not finished", "success", "fail"]


class Task(BaseModel):
    id: str
    status: TaskStatus = "not started"
    progress: float = 0
    result: TaskResult = "not finished"


_tasks: list[Task] = []


def add_task() -> str:
    task = Task(id=str(uuid.uuid4()))
    _tasks.append(task)
    return task.id


def get_all_tasks() -> list[Task]:
    return _tasks


def get_task(task_id: str | None = None) -> Task | None:
    for task in _tasks:
        if task.id == task_id:
            return task
    return None


def update_task(
    task_id: str | None = None,
    status: TaskStatus | None = None,
    progress: float = 0,
    result: TaskResult = "not finished",
) -> None:
    task = get_task(task_id)
    if task is not None:
        if status is not None:
            task.status = status
        task.progress = progress
        task.result = result


def delete_task(task_id: str | None = None) -> None:
    task = get_task(task_id)
    if task is not None:
        _tasks.remove(task)
