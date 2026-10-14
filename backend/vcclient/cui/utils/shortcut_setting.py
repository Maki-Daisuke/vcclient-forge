from typing import List

from pydantic import BaseModel


class Shortcut(BaseModel):
    command: str
    function: str
    description: str
    show: bool


class ShortcutList(BaseModel):
    shortcuts: List[Shortcut]
