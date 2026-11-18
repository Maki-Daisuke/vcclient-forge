from __future__ import annotations

import asyncio
import struct
from typing import Any

import numpy as np
import socketio
from starlette.datastructures import MutableHeaders

from vcclient.const import LOG_FILE
from vcclient.logger import logger
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

__all__ = [
    "SocketIONamespace",
    "create_socketio_app",
    "create_socketio_server",
]


class SocketIONamespace(socketio.AsyncNamespace):
    def __init__(self, namespace: str = "/test") -> None:
        super().__init__(namespace)
        self._subscribe_core_events()

    def _subscribe_core_events(self) -> None:
        vc = VoiceChanger.get_instance()
        vc.on("data", lambda data: self.emit_coroutine("data", data))

        lvci = LocalVoiceChangerInterface.get_instance()
        lvci.on("data", lambda data: self.emit_coroutine("data", data))

    async def emit_to(self, event: str, data: Any, to: str | None) -> None:
        await self.emit(event, data, to=to)

    def emit_coroutine(self, event: str, data: Any, to: str | None = None) -> None:
        asyncio.run(self.emit_to(event, data, to=to))

    def on_connect(self, sid: str, environ: dict[str, Any]) -> None:
        logger.info("connect sid: %s", sid)

    async def on_request_message(self, sid: str, msg: list[Any]) -> None:
        try:
            timestamp = int(msg[0])
            data = msg[2]
            data_size = len(data) // struct.calcsize("<f")
            unpacked_data = np.array(struct.unpack(f"<{data_size}f", data)).astype(np.float32)
            vc = VoiceChanger.get_instance()
            if not vc.is_convert_chunk_bulk_started():
                vc.start_convert_chunk_bulk()
            converted_np, _ = vc.convert_chunk_bulk(unpacked_data)
            if converted_np is None:
                return None
            data_size = len(converted_np)
            bin_data = struct.pack(f"<{data_size}f", *converted_np)
            await self.emit("response", [timestamp, bin_data], to=sid)
            return None
        except Exception as e:
            logger.error("Error processing request message: %s", e)
            return None


def create_socketio_server(allowed_origins: list[str] | None = None) -> socketio.AsyncServer:
    if allowed_origins is None:
        sio = socketio.AsyncServer(async_mode="asgi")
    else:
        sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=allowed_origins)

    namespace = SocketIONamespace("/test")
    sio.register_namespace(namespace)
    return sio


class NoCacheASGIApp(socketio.ASGIApp):
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await super().__call__(scope, receive, send)

        async def send_no_cache(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["Cache-Control"] = "no-store"
            await send(message)

        return await super().__call__(scope, receive, send_no_cache)


def create_socketio_app(
    sio: socketio.AsyncServer,
    app_fastapi: Any = None,
) -> socketio.ASGIApp:
    static_files: dict[str, Any] = {
        "/vcclient.log": {"filename": f"{LOG_FILE}", "content_type": "text/plain"},
    }

    return NoCacheASGIApp(
        sio,
        other_asgi_app=app_fastapi,
        static_files=static_files,
    )
