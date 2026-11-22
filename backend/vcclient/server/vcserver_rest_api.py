from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.openapi.docs import swagger_ui_default_parameters
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from vcclient.const import LOG_FILE, SERVER_IO_RECORDING_FILE_OUT
from vcclient.logger import logger
from vcclient.server.api_common import DomainApiError, DomainApiRoute, is_recording_active
from vcclient.server.server_const import get_frontend_path
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.server.vcserver_rest_api_audio_device_manager import RestAPIAudioDeviceManager
from vcclient.server.vcserver_rest_api_configuration_manager import RestAPIConfigurationManager
from vcclient.server.vcserver_rest_api_devices import RestAPIDevices
from vcclient.server.vcserver_rest_api_gpu_device_manager import RestAPIGPUDeviceManager
from vcclient.server.vcserver_rest_api_local_voice_changer_interface import RestAPILocalVoiceChangerInterface
from vcclient.server.vcserver_rest_api_models import RestAPIModels
from vcclient.server.vcserver_rest_api_settings import RestAPISettings
from vcclient.server.vcserver_rest_api_slot_manager import RestAPISlotManager
from vcclient.server.vcserver_rest_api_voice_changer import RestAPIVoiceChanger
from vcclient.server.vcserver_websocket import WebSocketHub
from vcclient.voice_changer.voice_changer_const import ModelDir


class NoCacheMiddleware:
    """ASGI middleware setting Cache-Control: no-store on all HTTP responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_no_cache(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_no_cache)


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


_rest_api_app: FastAPI | None = None


def get_rest_api() -> FastAPI:
    global _rest_api_app
    if _rest_api_app is None:
        _rest_api_app = _create_rest_api()
    return _rest_api_app


def register_api_exception_handlers(app_fastapi: FastAPI) -> None:
    @app_fastapi.exception_handler(DomainApiError)
    async def domain_api_error_handler(_request: Request, exc: DomainApiError):
        return exc.to_response()

    @app_fastapi.exception_handler(StarletteHTTPException)
    async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            try:
                json.loads(exc.detail)
                detail = exc.detail
            except Exception:
                code = (
                    "NOT_SUPPORTED"
                    if exc.status_code == 404 and str(exc.detail) == "Not Found"
                    else "ERR_HTTP_EXCEPTION"
                )
                detail = json.dumps({"code": code, "message": str(exc.detail)})
            return JSONResponse(status_code=exc.status_code, content={"detail": detail})
        return await http_exception_handler(request, exc)


def _create_rest_api() -> FastAPI:
    app_fastapi = FastAPI(title="VCClient REST API", docs_url=None, redoc_url=None)
    app_fastapi.add_middleware(NoCacheMiddleware)
    app_fastapi.router.route_class = ValidationErrorLoggingRoute
    register_api_exception_handlers(app_fastapi)

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
    def serve_output_wav():
        return _serve_audio_file(SERVER_IO_RECORDING_FILE_OUT)

    @app_fastapi.get("/vcclient.log", include_in_schema=False)
    def serve_log_file():
        file_path = Path(LOG_FILE)
        if not file_path.exists():
            return JSONResponse(status_code=404, content={"detail": f"Log file {LOG_FILE} not found"})
        return FileResponse(
            path=str(file_path),
            media_type="text/plain",
        )

    app_fastapi.get("/docs", include_in_schema=False)(custom_swagger_ui_html)
    app_fastapi.mount(f"""/{ModelDir}""", StaticFiles(directory=ModelDir), name="static")

    rest_slot_manager = RestAPISlotManager()
    app_fastapi.include_router(rest_slot_manager.router)
    rest_configuration_manager = RestAPIConfigurationManager()
    app_fastapi.include_router(rest_configuration_manager.router)
    rest_audio_device_manager = RestAPIAudioDeviceManager()
    app_fastapi.include_router(rest_audio_device_manager.router)
    rest_gpu_device_manager = RestAPIGPUDeviceManager()
    app_fastapi.include_router(rest_gpu_device_manager.router)
    voice_changer = RestAPIVoiceChanger()
    app_fastapi.include_router(voice_changer.router)
    local_voice_changer_interface = RestAPILocalVoiceChangerInterface()
    app_fastapi.include_router(local_voice_changer_interface.router)

    rest_devices = RestAPIDevices()
    app_fastapi.include_router(rest_devices.router)
    rest_models = RestAPIModels()
    app_fastapi.include_router(rest_models.router)
    rest_settings = RestAPISettings()
    app_fastapi.include_router(rest_settings.router)

    domain_system_router = APIRouter(route_class=DomainApiRoute)

    @domain_system_router.get("/api/recordings/latest")
    def get_latest_recording():
        if is_recording_active():
            raise DomainApiError(
                409,
                "recording_in_progress",
                "Cannot download recording while recording is in progress.",
            )
        file_path = Path(SERVER_IO_RECORDING_FILE_OUT)
        if not file_path.exists():
            raise DomainApiError(404, "recording_not_found", f"Recording {file_path.name} not found.")
        return FileResponse(path=str(file_path), media_type="audio/wav", filename=file_path.name)

    @domain_system_router.get("/api/logs")
    def get_logs():
        file_path = Path(LOG_FILE)
        if not file_path.exists():
            raise DomainApiError(404, "log_not_found", f"Log file {file_path.name} not found.")
        return FileResponse(path=str(file_path), media_type="text/plain", filename=file_path.name)

    app_fastapi.include_router(domain_system_router)

    ws_hub = WebSocketHub()
    ws_hub.subscribe_core_events()
    app_fastapi.state.ws_hub = ws_hub
    app_fastapi.include_router(ws_hub.router)

    async def unknown_api(scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        raise StarletteHTTPException(status_code=404, detail="Not Found")

    app_fastapi.mount("/api", unknown_api)
    app_fastapi.mount("/", StaticFiles(directory=str(get_frontend_path()), html=True, check_dir=False), name="frontend")
    return app_fastapi
