from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vcclient.logger import logger
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

__all__ = [
    "STATUS_QUEUE_MAXSIZE",
    "WebSocketHub",
]

STATUS_QUEUE_MAXSIZE = 32


def _enqueue_latest(queue: asyncio.Queue[str | None], payload: str | None) -> None:
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass


class WebSocketHub:
    """Manages native FastAPI WebSocket endpoints for realtime telemetry and audio streaming."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status_clients: dict[WebSocket, tuple[asyncio.AbstractEventLoop, asyncio.Queue[str | None]]] = {}
        self._audio_clients: set[WebSocket] = set()
        self.router = APIRouter()
        self.router.add_api_websocket_route("/api/ws/status", self.websocket_status)
        self.router.add_api_websocket_route("/api/ws/audio", self.websocket_audio)

    def subscribe_core_events(self) -> None:
        vc = VoiceChanger.get_instance()
        vc.on("status", self.broadcast_status)

        lvci = LocalVoiceChangerInterface.get_instance()
        lvci.on("status", self.broadcast_status)

    def broadcast_status(self, event_type: str, data: dict[str, Any]) -> None:
        with self._lock:
            if not self._status_clients:
                return
            targets = list(self._status_clients.values())

        payload = json.dumps({"type": event_type, "data": data})
        for loop, queue in targets:
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(_enqueue_latest, queue, payload)
                except RuntimeError:
                    pass

    async def websocket_status(self, websocket: WebSocket) -> None:
        await websocket.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=STATUS_QUEUE_MAXSIZE)
        with self._lock:
            self._status_clients[websocket] = (loop, queue)

        async def deliver_status() -> None:
            while True:
                payload = await queue.get()
                if payload is None:
                    return
                await websocket.send_text(payload)

        async def wait_for_disconnect() -> None:
            # Server-to-client only; receive() is required for ASGI to detect peer disconnect promptly.
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    return

        deliver_task = asyncio.create_task(deliver_status())
        disconnect_task = asyncio.create_task(wait_for_disconnect())
        try:
            done, _ = await asyncio.wait(
                {deliver_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                if not task.cancelled():
                    exc = task.exception()
                    if exc is not None and not isinstance(exc, (WebSocketDisconnect, RuntimeError)):
                        logger.debug("Status WebSocket task ended with error: %s", exc)
        finally:
            for task in (deliver_task, disconnect_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(deliver_task, disconnect_task, return_exceptions=True)
            with self._lock:
                self._status_clients.pop(websocket, None)

    async def websocket_audio(self, websocket: WebSocket) -> None:
        await websocket.accept()
        with self._lock:
            self._audio_clients.add(websocket)

        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if not data:
                    continue
                if len(data) % 4 != 0:
                    logger.warning("Ignoring audio WebSocket frame with unaligned byte length: %d", len(data))
                    continue

                try:
                    unpacked_data = np.frombuffer(data, dtype="<f4").astype(np.float32, copy=True)
                    vc = VoiceChanger.get_instance()
                    if not vc.is_convert_chunk_bulk_started():
                        vc.start_convert_chunk_bulk()
                    converted_np, _ = vc.convert_chunk_bulk(unpacked_data)
                except Exception as e:
                    logger.error("Error processing audio WebSocket message: %s", e)
                    continue

                if converted_np is None or len(converted_np) == 0:
                    continue
                await websocket.send_bytes(converted_np.astype("<f4", copy=False).tobytes())
        except WebSocketDisconnect, RuntimeError:
            pass
        finally:
            with self._lock:
                self._audio_clients.discard(websocket)

    async def close_all(self, code: int = 1001) -> None:
        with self._lock:
            status_entries = list(self._status_clients.items())
            self._status_clients.clear()
            audio_entries = list(self._audio_clients)
            self._audio_clients.clear()

        for websocket, (loop, queue) in status_entries:
            try:
                await websocket.close(code=code)
            except Exception:
                pass
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(_enqueue_latest, queue, None)
                except RuntimeError:
                    pass

        for websocket in audio_entries:
            try:
                await websocket.close(code=code)
            except Exception:
                pass
