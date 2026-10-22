import socketio

from vcclient.const import LOG_FILE, SERVER_IO_RECORDING_FILE_IN, SERVER_IO_RECORDING_FILE_OUT
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

            app_socketio = socketio.ASGIApp(
                sio,
                other_asgi_app=app_fastapi,
                static_files={
                    "/assets/icons/github.svg": {
                        "filename": f"""{get_frontend_path()}/assets/icons/github.svg""",
                        "content_type": "image/svg+xml",
                    },
                    "/assets/icons/help-circle.svg": {
                        "filename": f"""{get_frontend_path()}/assets/icons/help-circle.svg""",
                        "content_type": "image/svg+xml",
                    },
                    "/assets/icons/monitor.svg": {
                        "filename": f"""{get_frontend_path()}/assets/icons/monitor.svg""",
                        "content_type": "image/svg+xml",
                    },
                    "/assets/icons/tool.svg": {
                        "filename": f"""{get_frontend_path()}/assets/icons/tool.svg""",
                        "content_type": "image/svg+xml",
                    },
                    "/assets/icons/folder.svg": {
                        "filename": f"""{get_frontend_path()}/assets/icons/folder.svg""",
                        "content_type": "image/svg+xml",
                    },
                    "assets/icons/buymeacoffee.png": {
                        "filename": f"""{get_frontend_path()}/assets/icons/buymeacoffee.png""",
                        "content_type": "image/png",
                    },
                    "/ort-wasm-simd.wasm": {
                        "filename": f"""{get_frontend_path()}/ort-wasm-simd.wasm""",
                        "content_type": "application/wasm",
                    },
                    "": f"""{get_frontend_path()}""",
                    "/": f"""{get_frontend_path()}/index.html""",
                    "/vcclient.log": {"filename": f"""{LOG_FILE}""", "content_type": "text/plain"},
                    "/input.wav": {"filename": f"""{SERVER_IO_RECORDING_FILE_IN}""", "content_type": "audio/wav"},
                    "/output.wav": {"filename": f"""{SERVER_IO_RECORDING_FILE_OUT}""", "content_type": "audio/wav"},
                },
            )

            cls._instance = app_socketio

            return cls._instance

        return cls._instance


voice_changer_params = VoiceChangerParams(vc_model_dir="model_dir")

rest = RestAPI.get_instance(voice_changer_params)

allow_origins = VCServer.get_instance().allow_origins

logger.info("SocketIOApp Allow Origins %s", allow_origins)

serverio_app = SocketIOApp.get_instance(rest, allow_origins=allow_origins)
