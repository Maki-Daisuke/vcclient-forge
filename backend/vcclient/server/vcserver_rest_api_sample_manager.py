from fastapi import APIRouter

from vcclient.server.server_const import UPLOAD_DIR
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.data_types.data_types import RVCSampleInfo
from vcclient.voice_changer.sample_manager import (
    SampleDownloadParam,
    download_sample,
    get_samples,
)


class RestAPISampleManager:
    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/sample-manager/samples", self.get_samples, methods=["GET"])
        self.router.add_api_route(
            "/api/sample-manager/samples/operation/download", self.post_download, methods=["POST"]
        )

    def get_samples(self) -> list[RVCSampleInfo]:
        return get_samples()

    def post_download(self, param: SampleDownloadParam) -> None:
        download_sample(UPLOAD_DIR, param)
