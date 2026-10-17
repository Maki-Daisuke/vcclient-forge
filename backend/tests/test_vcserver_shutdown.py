import asyncio
import logging
import math
import socket
import threading
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import socketio
import uvicorn
from engineio.async_socket import AsyncSocket
from starlette.applications import Starlette

from vcclient.const import LOGGER_NAME
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
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)

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
@pytest.mark.parametrize("namespace", ["/", "/test"])
async def test_stop_all_sockets_disconnects_registered_clients(namespace: str, monkeypatch: pytest.MonkeyPatch) -> None:
    sio = socketio.AsyncServer(async_mode="asgi")
    engineio_sid = "shutdown-test-engineio-id"
    socketio_sid = await sio.manager.connect(engineio_sid, namespace)
    engineio_socket = AsyncSocket(sio.eio, engineio_sid)
    monkeypatch.setattr(engineio_socket.queue, "join", AsyncMock())
    sio.eio.sockets[engineio_sid] = engineio_socket
    monkeypatch.setattr("vcclient.server.vcserver.SocketIOServer.get_instance", lambda: sio)
    server = VCServer(host="127.0.0.1", port=0)
    try:
        assert socketio_sid != engineio_sid
        assert sio.manager.is_connected(socketio_sid, namespace)

        await asyncio.wait_for(server.stop_all_sockets(), timeout=2)

        assert not sio.manager.is_connected(socketio_sid, namespace), (
            f"Client remained connected to {namespace} after stop_all_sockets()"
        )
    finally:
        await sio.manager.disconnect(socketio_sid, namespace)
        sio.eio.sockets.clear()


def test_shutdown_finishes_with_unconsumed_polling_packets(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sio = socketio.AsyncServer(async_mode="asgi")
    engineio_sid = "shutdown-unconsumed-polling-id"
    finished = threading.Event()
    errors: list[BaseException] = []
    sockets: list[AsyncSocket] = []
    server = VCServer(host="127.0.0.1", port=0)

    async def serve() -> None:
        await sio.manager.connect(engineio_sid, "/test")
        engineio_socket = AsyncSocket(sio.eio, engineio_sid)
        sockets.append(engineio_socket)
        sio.eio.sockets[engineio_sid] = engineio_socket
        await sio.eio.send(engineio_sid, "packet without a polling receiver")
        assert not engineio_socket.queue.empty()

    def run_server() -> None:
        try:
            server.start_server()
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    server.server = SimpleNamespace(serve=serve)
    monkeypatch.setattr("vcclient.server.vcserver.SocketIOServer.get_instance", lambda: sio)
    server.server_thread = threading.Thread(target=run_server, daemon=True)
    caplog.set_level(logging.ERROR, logger="asyncio")
    server.server_thread.start()
    try:
        assert finished.wait(timeout=8), "Shutdown blocked waiting for undelivered polling packets"
        server.server_thread.join(timeout=1)
        assert not server.server_thread.is_alive()
        assert not errors, f"Shutdown failed: {errors}"
        assert sockets, "The polling connection was not initialized"
        assert server.loop.is_closed()
        assert "Task was destroyed but it is pending" not in caplog.text
    finally:
        if hasattr(server, "loop") and server.loop.is_running():

            def cancel_remaining_tasks() -> None:
                for task in asyncio.all_tasks(server.loop):
                    task.cancel()

            server.loop.call_soon_threadsafe(cancel_remaining_tasks)
        server.server_thread.join(timeout=2)
        if not server.server_thread.is_alive() and hasattr(server, "loop") and not server.loop.is_closed():
            pending = list(asyncio.all_tasks(server.loop))
            for task in pending:
                task.cancel()
            if pending:
                server.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            server.loop.close()
        sio.eio.sockets.clear()
