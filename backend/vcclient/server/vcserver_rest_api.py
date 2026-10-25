from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.openapi.docs import swagger_ui_default_parameters
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from vcclient.const import (
    SERVER_IO_RECORDING_FILE_IN,
    SERVER_IO_RECORDING_FILE_MONITOR,
    SERVER_IO_RECORDING_FILE_OUT,
)
from vcclient.logger import logger
from vcclient.server.fileuploader.fileuploader import EasyFileUploader
from vcclient.server.server_const import TMP_DIR, UPLOAD_DIR, get_frontend_path
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.server.vcserver_rest_api_audio_device_manager import RestAPIAudioDeviceManager
from vcclient.server.vcserver_rest_api_configuration_manager import RestAPIConfigurationManager
from vcclient.server.vcserver_rest_api_gpu_device_manager import RestAPIGPUDeviceManager
from vcclient.server.vcserver_rest_api_hello import RestHello
from vcclient.server.vcserver_rest_api_local_voice_changer_interface import RestAPILocalVoiceChangerInterface
from vcclient.server.vcserver_rest_api_module_manager import RestAPIModuleManager
from vcclient.server.vcserver_rest_api_sample_manager import RestAPISampleManager
from vcclient.server.vcserver_rest_api_slot_manager import RestAPISlotManager
from vcclient.server.vcserver_rest_api_task_manager import RestAPITaskManager
from vcclient.server.vcserver_rest_api_voice_changer import RestAPIVoiceChanger
from vcclient.voice_changer.audio_device_manager.audio_device_manager import AudioDeviceManager
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager
from vcclient.voice_changer.module_manager.module_manager import ModuleManager
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger
from vcclient.voice_changer.voice_changer_const import ConfigFile, ModelDir, ModuleDir


def get_custom_swagger_ui_html(
    *,
    openapi_url: str,
    title: str,
    swagger_js_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
    swagger_css_url: str = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css",
    swagger_favicon_url: str = "https://fastapi.tiangolo.com/img/favicon.png",
    oauth2_redirect_url: Optional[str] = None,
    init_oauth: Optional[Dict[str, Any]] = None,
    swagger_ui_parameters: Optional[Dict[str, Any]] = None,
):
    current_swagger_ui_parameters = swagger_ui_default_parameters.copy()
    if swagger_ui_parameters:
        current_swagger_ui_parameters.update(swagger_ui_parameters)

    html = f'''\n    <!DOCTYPE html>\n    <html>\n    <head>\n    <link type="text/css" rel="stylesheet" href="{swagger_css_url}">\n    <link rel="shortcut icon" href="{swagger_favicon_url}">\n    <title>{title}</title>\n    </head>\n    <body>\n    <div style="color:red;font-weight: 600;">Note: API may be subject to change in the future.</div>\n    <div id="swagger-ui">\n    </div>\n    <script src="{swagger_js_url}"></script>\n    <!-- `SwaggerUIBundle` is now available on the page -->\n    <script>\n    const ui = SwaggerUIBundle({{\n        url: \'{openapi_url}\',\n    '''

    for key, value in current_swagger_ui_parameters.items():
        html += f"""{json.dumps(key)}: {json.dumps(jsonable_encoder(value))},\n"""

    if oauth2_redirect_url:
        html += f"""oauth2RedirectUrl: window.location.origin + \'{oauth2_redirect_url}\',"""

    html += "\n    presets: [\n        SwaggerUIBundle.presets.apis,\n        SwaggerUIBundle.SwaggerUIStandalonePreset\n        ],\n    })"

    if init_oauth:
        html += f"""\n        ui.initOAuth({json.dumps(jsonable_encoder(init_oauth))})\n        """

    html += "\n    </script>\n    </body>\n    </html>\n    "
    return HTMLResponse(html)


class RestAPI:
    _instance = None

    @classmethod
    def get_instance(cls, voice_changer_params=None):
        if cls._instance is None:
            app_fastapi = FastAPI(title="VCClient REST API", docs_url=None, redoc_url=None)
            app_fastapi.router.route_class = ValidationErrorLoggingRoute

            @app_fastapi.exception_handler(StarletteHTTPException)
            async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
                if request.url.path.startswith("/api/"):
                    try:
                        json.loads(exc.detail)
                        detail = exc.detail
                    except Exception:
                        code = "NOT_SUPPORTED" if exc.status_code == 404 else "ERR_HTTP_EXCEPTION"
                        detail = json.dumps({"code": code, "message": str(exc.detail)})
                    return JSONResponse(status_code=exc.status_code, content={"detail": detail})
                return await http_exception_handler(request, exc)

            def custom_swagger_ui_html():
                logger.info("CUSTOM UI")
                return get_custom_swagger_ui_html(
                    openapi_url=app_fastapi.openapi_url or "/openapi.json", title="VCClient API Docs"
                )

            def _serve_audio_file(filename: str) -> Response:
                file_path = Path(filename)
                if not file_path.exists():
                    return JSONResponse(status_code=404, content={"detail": f"Recording {filename} not found"})
                return FileResponse(
                    path=str(file_path),
                    media_type="audio/wav",
                    filename=filename,
                )

            @app_fastapi.get("/output.wav", include_in_schema=False)
            @app_fastapi.get("/ui/2.1.4/output.wav", include_in_schema=False)
            @app_fastapi.get("/ui/2.0.78/output.wav", include_in_schema=False)
            def serve_output_wav():
                return _serve_audio_file(SERVER_IO_RECORDING_FILE_OUT)

            @app_fastapi.get("/input.wav", include_in_schema=False)
            @app_fastapi.get("/ui/2.1.4/input.wav", include_in_schema=False)
            @app_fastapi.get("/ui/2.0.78/input.wav", include_in_schema=False)
            def serve_input_wav():
                return _serve_audio_file(SERVER_IO_RECORDING_FILE_IN)

            @app_fastapi.get("/monitor.wav", include_in_schema=False)
            @app_fastapi.get("/ui/2.1.4/monitor.wav", include_in_schema=False)
            @app_fastapi.get("/ui/2.0.78/monitor.wav", include_in_schema=False)
            def serve_monitor_wav():
                return _serve_audio_file(SERVER_IO_RECORDING_FILE_MONITOR)

            frontend_ui_dir = get_frontend_path() / "ui"
            if frontend_ui_dir.exists():
                app_fastapi.mount("/ui", StaticFiles(directory=str(frontend_ui_dir), html=True), name="ui")

            @app_fastapi.get("/", include_in_schema=False)
            def root_redirect(request: Request):
                query = request.url.query
                target = f"/ui/2.1.4/?{query}" if query else "/ui/2.1.4/"
                return RedirectResponse(url=target, status_code=307)

            custom_swagger_ui_html = app_fastapi.get("/docs", include_in_schema=False)(custom_swagger_ui_html)
            app_fastapi.mount("/tmp", StaticFiles(directory=f"""{TMP_DIR}"""), name="static")
            app_fastapi.mount("/upload_dir", StaticFiles(directory=f"""{UPLOAD_DIR}"""), name="static")
            if sys.platform.startswith("darwin"):
                app_fastapi.mount(f"""/{ModelDir}""", StaticFiles(directory=ModelDir), name="static")
            else:
                app_fastapi.mount(f"""/{ModelDir}""", StaticFiles(directory=ModelDir), name="static")

            rest_hello = RestHello()
            app_fastapi.include_router(rest_hello.router)
            rest_slot_manager = RestAPISlotManager()
            app_fastapi.include_router(rest_slot_manager.router)
            rest_configuration_manager = RestAPIConfigurationManager()
            app_fastapi.include_router(rest_configuration_manager.router)
            rest_audio_device_manager = RestAPIAudioDeviceManager()
            app_fastapi.include_router(rest_audio_device_manager.router)
            rest_gpu_device_manager = RestAPIGPUDeviceManager()
            app_fastapi.include_router(rest_gpu_device_manager.router)
            rest_module_manager = RestAPIModuleManager()
            app_fastapi.include_router(rest_module_manager.router)
            rest_sample_manager = RestAPISampleManager()
            app_fastapi.include_router(rest_sample_manager.router)
            fileuploader = EasyFileUploader(UPLOAD_DIR)
            app_fastapi.include_router(fileuploader.router)
            voice_changer = RestAPIVoiceChanger()
            app_fastapi.include_router(voice_changer.router)
            local_voice_changer_interface = RestAPILocalVoiceChangerInterface()
            app_fastapi.include_router(local_voice_changer_interface.router)
            task_manager = RestAPITaskManager()
            app_fastapi.include_router(task_manager.router)

            app_fastapi.router.add_api_route("/api/operation/initialize", initialize, methods=["POST"])
            cls._instance = app_fastapi
            return cls._instance

        return cls._instance


def initialize():
    ConfigFile.unlink(missing_ok=True)
    shutil.rmtree(ModelDir)
    ModelDir.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(ModuleDir)
    ModuleDir.mkdir(parents=True, exist_ok=True)

    audio_device_manager = AudioDeviceManager.get_instance()
    audio_device_manager.reload_device()
    configuration_manager = ConfigurationManager.get_instance()
    configuration_manager.reload()
    gpu_device_manager = GPUDeviceManager.get_instance()
    gpu_device_manager.reload()
    module_manager = ModuleManager.get_instance()
    module_manager.reload()
    slot_manager = SlotManager.get_instance()
    slot_manager.reload()
    voice_changer = VoiceChanger.get_instance()
    voice_changer.initialize()

    return {"message": "initialized."}
