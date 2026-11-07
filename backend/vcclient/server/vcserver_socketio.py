from __future__ import annotations

import asyncio
import struct
from collections.abc import Callable
from typing import Any

import numpy as np
import socketio

from vcclient.const import (
    LOG_FILE,
    SERVER_IO_RECORDING_FILE_IN,
    SERVER_IO_RECORDING_FILE_MONITOR,
    SERVER_IO_RECORDING_FILE_OUT,
)
from vcclient.logger import logger
from vcclient.server.event_emitter import set_event_emitter
from vcclient.server.server_const import get_frontend_path
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

__all__ = [
    "SocketIONamespace",
    "SocketIOServer",
    "create_socketio_app",
    "create_socketio_server",
]


class SocketIONamespace(socketio.AsyncNamespace):
    sid: int = 0

    def __init__(
        self,
        namespace: str = "/test",
        list_all_sids: Callable[..., list[str]] | None = None,
    ) -> None:
        super().__init__(namespace)
        self.namespace = namespace
        self.list_all_sids = list_all_sids
        set_event_emitter(self)

    async def emit_to(self, event: str, data: Any, to: str | None) -> None:
        await self.emit(event, data, to=to)

    def emit_coroutine(self, event: str, data: Any, to: str | None = None) -> None:
        if to is None:
            asyncio.run(self.emit_to(event, data, to=None))
            return None
        asyncio.run(self.emit_to(event, data, to=to))

    def on_connect(self, sid: str, environ: dict[str, Any]) -> None:
        self.sid = int(sid) if isinstance(sid, int) else 0
        logger.info("connect sid: %s", sid)

    async def on_request_message(self, sid: str, msg: list[Any]) -> None:
        try:
            self.sid = int(sid) if isinstance(sid, int) else 0
            timestamp = int(msg[0])
            bulk = bool(msg[1])
            data = msg[2]
            if isinstance(data, str):
                logger.debug("Received string data on request message: %s", data)
                await self.emit("response", [timestamp, 0], to=sid)
                return None
            data_size = len(data) // struct.calcsize("<f")
            unpacked_data = np.array(struct.unpack(f"<{data_size}f", data)).astype(np.float32)
            vc = VoiceChanger.get_instance()
            if not vc.is_convert_chunk_bulk_started():
                vc.start_convert_chunk_bulk()
            if bulk:
                converted_np, _, performance_data = vc.convert_chunk_bulk(unpacked_data)
            else:
                converted_np, _, performance_data = vc.convert_chunk(unpacked_data, direct_from_server=True)
            if converted_np is None:
                return None
            audio1 = converted_np
            perf = performance_data.model_dump_json() if performance_data is not None else "{}"
            data_size = len(audio1)
            bin_data = struct.pack(f"<{data_size}f", *audio1)
            if ConfigurationManager.get_instance().get_voice_changer_configuration().sio_broadcast is True:
                await self.emit("response", [timestamp, bin_data, perf])
            else:
                await self.emit("response", [timestamp, bin_data, perf], to=sid)
            return None
        except Exception as e:
            logger.error("Error processing request message: %s", e)
            return None

    def on_disconnect(self, sid: str) -> None:
        pass


class SocketIOServer(socketio.AsyncServer):
    def list_all_sids(self, namespace: str, room: tuple[str, str | None] = ("/", None)) -> list[str]:
        return [sid for sid in self.manager.get_participants(namespace, room)]


def create_socketio_server(allowed_origins: list[str] | None = None) -> SocketIOServer:
    if allowed_origins is None:
        sio = SocketIOServer(async_mode="asgi")
    else:
        sio = SocketIOServer(async_mode="asgi", cors_allowed_origins=allowed_origins)

    namespace = SocketIONamespace("/test", list_all_sids=sio.list_all_sids)
    sio.register_namespace(namespace)
    return sio


def create_socketio_app(
    sio: SocketIOServer,
    app_fastapi: Any = None,
) -> socketio.ASGIApp:
    frontend_path = get_frontend_path()

    static_files: dict[str, Any] = {
        "/vcclient.log": {"filename": f"{LOG_FILE}", "content_type": "text/plain"},
        "/input.wav": {"filename": f"{SERVER_IO_RECORDING_FILE_IN}", "content_type": "audio/wav"},
        "/output.wav": {"filename": f"{SERVER_IO_RECORDING_FILE_OUT}", "content_type": "audio/wav"},
        "/monitor.wav": {"filename": f"{SERVER_IO_RECORDING_FILE_MONITOR}", "content_type": "audio/wav"},
    }

    if not (frontend_path / "ui").exists():
        static_files[""] = f"{frontend_path}"
        static_files["/"] = f"{frontend_path}/index.html"

    return socketio.ASGIApp(
        sio,
        other_asgi_app=app_fastapi,
        static_files=static_files,
    )
