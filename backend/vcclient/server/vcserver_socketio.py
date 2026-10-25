from typing import Any

import socketio

from vcclient.const import (
    LOG_FILE,
    SERVER_IO_RECORDING_FILE_IN,
    SERVER_IO_RECORDING_FILE_MONITOR,
    SERVER_IO_RECORDING_FILE_OUT,
)
from vcclient.logger import logger
from vcclient.server.vcserver import VCServer
from vcclient.server.vcserver_rest_api import RestAPI

from .server_const import VoiceChangerParams, get_frontend_path
from .vcserver_socketio_server import SocketIOServer


class SocketIOApp:
    _instance: socketio.ASGIApp | None = None

    @classmethod
    def get_instance(cls, app_fastapi=None, allow_origins=None):
        if cls._instance is None:
            sio = SocketIOServer.get_instance(allowed_origins=allow_origins)
            frontend_path = get_frontend_path()

            static_files: dict[str, Any] = {
                "/vcclient.log": {"filename": f"""{LOG_FILE}""", "content_type": "text/plain"},
                "/input.wav": {"filename": f"""{SERVER_IO_RECORDING_FILE_IN}""", "content_type": "audio/wav"},
                "/output.wav": {"filename": f"""{SERVER_IO_RECORDING_FILE_OUT}""", "content_type": "audio/wav"},
                "/monitor.wav": {"filename": f"""{SERVER_IO_RECORDING_FILE_MONITOR}""", "content_type": "audio/wav"},
            }

            if not (frontend_path / "ui").exists():
                static_files[""] = f"""{frontend_path}"""
                static_files["/"] = f"""{frontend_path}/index.html"""

            app_socketio = socketio.ASGIApp(
                sio,
                other_asgi_app=app_fastapi,
                static_files=static_files,
            )

            cls._instance = app_socketio

            return cls._instance

        return cls._instance


voice_changer_params = VoiceChangerParams(vc_model_dir="model_dir")

rest = RestAPI.get_instance(voice_changer_params)

allow_origins = VCServer.get_instance().allow_origins

logger.info("SocketIOApp Allow Origins %s", allow_origins)

serverio_app = SocketIOApp.get_instance(rest, allow_origins=allow_origins)
