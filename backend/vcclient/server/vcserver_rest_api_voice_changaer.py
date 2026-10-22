import numpy as np
from fastapi import APIRouter, File, Header, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from vcclient.logger import logger
from vcclient.server.event_emitter_manager import EventEmitterManager
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.voice_changer_data_types import VoiceChangerManagerInfo
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger
from vcclient.voice_changer.voice_change_manager.voice_changer_manager import VoiceChangerManager


class ConvertFileParam(BaseModel):
    src_path: str
    dst_path: str


class RestAPIVoiceChanger:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/voice-changer/convert_chunk", self.post_convert_chunk, methods=["POST"])
        self.router.add_api_route(
            "/api/voice-changer/convert_chunk_bulk", self.post_convert_chunk_bulk, methods=["POST"]
        )
        self.router.add_api_route("/api/voice-changer/convert_file", self.post_convert_file, methods=["POST"])
        self.router.add_api_route(
            "/api/voice-changer/operation/start_server_device", self.start_server_device, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/voice-changer/operation/stop_server_device", self.stop_server_device, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/voice-changer-manager/information", self.get_voice_changer_information, methods=["GET"]
        )

    async def post_convert_chunk_bulk(
        self, waveform: UploadFile = File(...), x_timestamp: int | None = Header(default=0)
    ):
        """
        音声変換を行うAPI

        Args:
            waveform (UploadFile): 音声データ float32のバイナリデータを想定している。
            x_timestamp (int): タイムスタンプ
        """
        if x_timestamp is None:
            x_timestamp = 0
        chunk = await waveform.read()
        chunk_np = np.frombuffer(chunk, dtype=np.float32)
        vc = VoiceChanger.get_instance()
        if vc.is_convert_chunk_bulk_started() is False:
            vc.start_convert_chunk_bulk()
        converted_np, _, performance_data = vc.convert_chunk_bulk(chunk_np)
        if converted_np is None:
            dummy = np.zeros([1], dtype=np.float32)
            return Response(
                content=dummy.tobytes(),
                media_type="application/octet-stream",
                headers={"x-timestamp": str(x_timestamp)},
            )
        return Response(
            content=converted_np.tobytes(),
            media_type="application/octet-stream",
            headers={
                "x-timestamp": str(x_timestamp),
                "x-performance": performance_data.model_dump_json() if performance_data is not None else "{}",
            },
        )

    async def post_convert_chunk(self, waveform: UploadFile = File(...), x_timestamp: int | None = Header(default=0)):
        """
        音声変換を行うAPI

        Args:
            waveform (UploadFile): 音声データ np.float32のバイナリデータを想定している。
            x_timestamp (int): タイムスタンプ
        """
        chunk = await waveform.read()
        chunk_np = np.frombuffer(chunk, dtype=np.float32)
        vc = VoiceChanger.get_instance()
        converted_np, _, performance_data = vc.convert_chunk(chunk_np, direct_from_server=True)
        return Response(
            content=converted_np.tobytes(),
            media_type="application/octet-stream",
            headers={
                "x-timestamp": str(x_timestamp),
                "x-performance": performance_data.model_dump_json() if performance_data is not None else "{}",
            },
        )

    def post_convert_file(self, convert_file_param: ConvertFileParam):
        vc = VoiceChanger.get_instance()
        vc.convert_file(convert_file_param.src_path, convert_file_param.dst_path)

    def start_server_device(self):
        configuration_manager = ConfigurationManager.get_instance()
        conf = configuration_manager.get_voice_changer_configuration()
        if conf.voice_changer_input_mode == "server":
            vc = LocalVoiceChangerInterface.get_instance()
            vc.start()
            event_emitter = EventEmitterManager.get_instance().get_event_emitter()
            if event_emitter is not None:
                event_emitter.emit_coroutine("command", ["reload"])
                return None
            return None
        raise Exception("Voice changer input mode is not server.")

    def stop_server_device(self):
        vc = LocalVoiceChangerInterface.get_instance()
        vc.stop()

    def get_voice_changer_information(self) -> VoiceChangerManagerInfo:
        voice_chanager_manager = VoiceChangerManager.get_instance()
        info = voice_chanager_manager.get_info()
        logger.info("get_voice_changer_information %s", info)
        return info
