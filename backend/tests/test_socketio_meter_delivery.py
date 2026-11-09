import asyncio
import json
import threading
import time

import pytest
import socketio
import uvicorn
import websockets

from vcclient.server import event_emitter, vcserver_socketio
from vcclient.voice_changer.event_emitter import EventEmitter


@pytest.mark.asyncio
async def test_meter_event_from_audio_thread_reaches_socketio_client(monkeypatch):
    voice = EventEmitter()
    audio = EventEmitter()
    previous_emitter = event_emitter._emitter
    monkeypatch.setattr(vcserver_socketio.VoiceChanger, "get_instance", lambda: voice)
    monkeypatch.setattr(vcserver_socketio.LocalVoiceChangerInterface, "get_instance", lambda: audio)
    sio = socketio.AsyncServer(async_mode="asgi")
    namespace = vcserver_socketio.SocketIONamespace("/test")
    sio.register_namespace(namespace)
    server = uvicorn.Server(
        uvicorn.Config(socketio.ASGIApp(sio), host="127.0.0.1", port=0, log_level="error", access_log=False)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}/socket.io/?EIO=4&transport=websocket") as ws:
            assert (await asyncio.wait_for(ws.recv(), 3)).startswith("0")
            await ws.send("40/test,")
            assert (await asyncio.wait_for(ws.recv(), 3)).startswith("40/test,")
            data = ["realtime_output_status", json.dumps({"inputRms": 0.25, "outputRms": 0.5})]
            await asyncio.to_thread(audio.emit, "data", data)
            message = await asyncio.wait_for(ws.recv(), 3)
            assert message.startswith("42/test,")
            assert json.loads(message.removeprefix("42/test,")) == ["data", data]
    finally:
        server.should_exit = True
        await asyncio.to_thread(thread.join, 5)
        assert not thread.is_alive()
        vcserver_socketio.set_event_emitter(previous_emitter)
