from typing import Literal

from pydantic import BaseModel

DOWNLOAD_STATE = Literal["processing", "validating", "done", "error"]


class SampleDownloadParam(BaseModel):
    slot_index: int
    sample_id: str


class SampleDownloadStatus(BaseModel):
    id: str
    status: DOWNLOAD_STATE
    progress: float
    error_message: str | None = None
