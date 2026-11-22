from __future__ import annotations

import asyncio
import json
import threading
import time
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


def _enqueue_close(queue: asyncio.Queue[tuple[int, str] | None], signal: tuple[int, str] | None) -> None:
    try:
        queue.put_nowait(signal)
    except asyncio.QueueFull:
        pass


class WebSocketHub:
    """Manages native FastAPI WebSocket endpoints for realtime telemetry and audio streaming."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status_clients: dict[WebSocket, tuple[asyncio.AbstractEventLoop, asyncio.Queue[str | None]]] = {}
        self._audio_clients: dict[
            WebSocket, tuple[asyncio.AbstractEventLoop, asyncio.Queue[tuple[int, str] | None], threading.Event]
        ] = {}
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
        from vcclient.voice_changer.session_manager import is_client_session_running

        if not is_client_session_running():
            await websocket.accept()
            await websocket.close(code=1008)
            return

        loop = asyncio.get_running_loop()
        close_queue: asyncio.Queue[tuple[int, str] | None] = asyncio.Queue(maxsize=4)
        closed_event = threading.Event()
        entry = (loop, close_queue, closed_event)

        with self._lock:
            previous_clients = list(self._audio_clients.values())
            self._audio_clients.clear()
            self._audio_clients[websocket] = entry

        for prev_loop, prev_queue, _ in previous_clients:
            if not prev_loop.is_closed():
                try:
                    prev_loop.call_soon_threadsafe(_enqueue_close, prev_queue, (4001, "superseded"))
                except RuntimeError:
                    pass

        if previous_clients:
            deadline = time.monotonic() + 1.0
            for _, _, prev_closed in previous_clients:
                while not prev_closed.is_set() and time.monotonic() < deadline:
                    await asyncio.sleep(0.005)
            vc_existing = VoiceChanger.peek_instance()
            if vc_existing is not None:
                vc_existing.reset_client_stream_buffers()

        await websocket.accept()

        def _cleanup_task[T](task: asyncio.Task[T]) -> None:
            if not task.done():
                task.cancel()
                task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
            elif not task.cancelled():
                task.exception()

        close_task = asyncio.create_task(close_queue.get())
        try:
            while True:
                receive_task = asyncio.create_task(websocket.receive())
                try:
                    done, pending = await asyncio.wait(
                        {receive_task, close_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                except BaseException:
                    _cleanup_task(receive_task)
                    raise
                if close_task in done:
                    _cleanup_task(receive_task)
                    signal = close_task.result()
                    if signal is not None:
                        close_code, close_reason = signal
                        try:
                            await websocket.close(code=close_code, reason=close_reason)
                        except Exception:
                            pass
                    break

                message = receive_task.result()
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
                    vc = VoiceChanger.peek_instance()
                    if vc is None or not vc.is_convert_chunk_bulk_started():
                        continue
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
            # Cancel synchronously without awaiting so Starlette TestClient's
            # disconnect cancel-scope cleanup is never interrupted on exit.
            _cleanup_task(close_task)
            with self._lock:
                if self._audio_clients.get(websocket) is entry:
                    self._audio_clients.pop(websocket, None)
            closed_event.set()

    def close_audio_clients(self, code: int = 1000, reason: str = "") -> None:
        with self._lock:
            entries = list(self._audio_clients.values())
            self._audio_clients.clear()

        for loop, close_queue, _ in entries:
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(_enqueue_close, close_queue, (code, reason))
                except RuntimeError:
                    pass

        deadline = time.monotonic() + 2.0
        for _, _, closed_event in entries:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                closed_event.wait(timeout=remaining)

    async def close_all(self, code: int = 1001) -> None:
        with self._lock:
            status_entries = list(self._status_clients.items())
            self._status_clients.clear()
            audio_entries = list(self._audio_clients.items())
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

        for websocket, (loop, close_queue, _) in audio_entries:
            try:
                await websocket.close(code=code)
            except Exception:
                pass
            if not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(_enqueue_close, close_queue, None)
                except RuntimeError:
                    pass
