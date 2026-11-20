import asyncio
import logging
import math
import socket
import threading
import time
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import uvicorn
import websockets
from starlette.applications import Starlette

from vcclient.logger import logger
from vcclient.server.vcserver import VCServer


def test_vcserver_graceful_shutdown(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    ready = threading.Event()
    errors: list[BaseException] = []

    class ReadyServer(uvicorn.Server):
        async def startup(self, sockets: list[socket.socket] | None = None) -> None:
            await super().startup(sockets=sockets)
            ready.set()

    server = VCServer(host="127.0.0.1", port=0)
    server.server = ReadyServer(uvicorn.Config(Starlette(), host=server.host, port=server.port, log_config=None))
    monkeypatch.setattr(server, "stop_all_sockets", AsyncMock())

    def run_server() -> None:
        try:
            server.start_server()
        except BaseException as error:
            errors.append(error)
        finally:
            ready.set()

    server.server_thread = threading.Thread(target=run_server, daemon=True)
    caplog.set_level(logging.ERROR, logger="asyncio")
    server.server_thread.start()
    try:
        assert ready.wait(timeout=10), "Uvicorn did not finish startup"
        assert not errors, f"Server thread failed: {errors}"
        assert server.server.started
        assert server.server.servers[0].sockets[0].getsockname()[1] > 0

        server.stop()

        assert not server.server_thread.is_alive(), "Server thread survived stop()"
        assert not errors, f"Server thread failed during shutdown: {errors}"
        assert server.loop.is_closed()
        assert "Task was destroyed but it is pending" not in caplog.text
    finally:
        if server.server_thread.is_alive():
            server.server.should_exit = True
            server.server.force_exit = True

            def cancel_remaining_tasks() -> None:
                for task in asyncio.all_tasks(server.loop):
                    task.cancel()

            if hasattr(server, "loop") and server.loop.is_running():
                server.loop.call_soon_threadsafe(cancel_remaining_tasks)
            server.server_thread.join(timeout=2)


@pytest.mark.parametrize("serve_fails", [False, True])
def test_shutdown_cleans_pending_tasks_and_async_generators(
    serve_fails: bool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    server = VCServer(host="127.0.0.1", port=0)
    background_tasks: list[asyncio.Task[None]] = []
    generators: list[AsyncGenerator[int, None]] = []
    task_cancelled = threading.Event()
    generator_closed = threading.Event()

    async def background(started: asyncio.Event) -> None:
        started.set()
        try:
            await asyncio.get_running_loop().create_future()
        finally:
            task_cancelled.set()

    async def generate() -> AsyncGenerator[int, None]:
        try:
            yield 1
        finally:
            generator_closed.set()

    async def serve() -> None:
        started = asyncio.Event()
        background_tasks.append(asyncio.create_task(background(started)))
        await started.wait()
        generator = generate()
        generators.append(generator)
        await anext(generator)
        if serve_fails:
            raise RuntimeError("Simulated serve failure")

    server.server = SimpleNamespace(serve=serve)
    disconnect = AsyncMock()
    monkeypatch.setattr(server, "stop_all_sockets", disconnect)
    caplog.set_level(logging.ERROR, logger="asyncio")

    if serve_fails:
        with pytest.raises(RuntimeError, match="Simulated serve failure"):
            server.start_server()
    else:
        server.start_server()

    disconnect.assert_awaited_once()
    assert task_cancelled.is_set()
    assert all(task.done() and task.cancelled() for task in background_tasks)
    assert generator_closed.is_set()
    assert server.loop.is_closed()
    assert "Task was destroyed but it is pending" not in caplog.text


def test_start_configures_finite_graceful_shutdown_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    thread = MagicMock()
    monkeypatch.setattr("vcclient.server.vcserver.threading.Thread", MagicMock(return_value=thread))
    server = VCServer(host="127.0.0.1", port=0)

    server.start()

    timeout = server.server.config.timeout_graceful_shutdown
    assert timeout is not None, "Uvicorn must not wait indefinitely for active requests"
    assert math.isfinite(timeout) and timeout > 0


def test_stop_reports_failure_if_thread_survives_timeout(caplog: pytest.LogCaptureFixture) -> None:
    server = VCServer(host="127.0.0.1", port=0)
    server.server = SimpleNamespace(should_exit=False)
    server.server_thread = MagicMock()
    server.server_thread.is_alive.return_value = True
    caplog.set_level(logging.INFO, logger=logger.name)

    raised = False
    result = None
    try:
        result = server.stop()
    except RuntimeError, TimeoutError:
        raised = True

    assert server.server.should_exit
    server.server_thread.join.assert_called()
    assert raised or result is False or any(record.levelno >= logging.ERROR for record in caplog.records), (
        "stop() must report failure when its thread is still alive"
    )
    assert not any("stop...done" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("ws_path", ["/api/ws/status", "/api/ws/audio"])
async def test_stop_disconnects_active_websocket_clients(ws_path: str, caplog: pytest.LogCaptureFixture) -> None:
    server = VCServer(host="127.0.0.1", port=0)
    caplog.set_level(logging.ERROR, logger="asyncio")
    server.start()
    try:
        deadline = time.monotonic() + 10
        while not server.server.started and server.server_thread is not None and server.server_thread.is_alive():
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.01)
        assert server.server.started
        port = server.server.servers[0].sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}{ws_path}", proxy=None) as ws:
            stopped = await asyncio.to_thread(server.stop)
            assert stopped is True
            with pytest.raises(websockets.exceptions.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), timeout=2)

        assert server.server_thread is not None
        assert not server.server_thread.is_alive(), "Server thread survived stop()"
        assert server.loop.is_closed()
        assert "Task was destroyed but it is pending" not in caplog.text
    finally:
        if server.server_thread is not None and server.server_thread.is_alive():
            server.server.should_exit = True
            server.server.force_exit = True
            await asyncio.to_thread(server.server_thread.join, 2)
