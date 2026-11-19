import asyncio
import threading
import time
from unittest.mock import MagicMock

import numpy as np
import pytest
import uvicorn
import websockets
from fastapi import FastAPI
from starlette.testclient import TestClient

from vcclient.server import vcserver_websocket
from vcclient.voice_changer.event_emitter import EventEmitter


def test_audio_websocket_returns_bulk_conversion_to_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    voice = MagicMock()
    voice.is_convert_chunk_bulk_started.return_value = False
    expected_audio = np.array([0.25, -0.5], dtype=np.float32)
    voice.convert_chunk_bulk.return_value = (expected_audio, None)
    monkeypatch.setattr(vcserver_websocket.VoiceChanger, "get_instance", lambda: voice)
    monkeypatch.setattr(vcserver_websocket.LocalVoiceChangerInterface, "get_instance", EventEmitter)

    app = FastAPI()
    hub = vcserver_websocket.WebSocketHub()
    app.include_router(hub.router)

    input_audio = np.array([0.5, -0.25], dtype=np.float32)
    with TestClient(app).websocket_connect("/api/ws/audio") as ws:
        ws.send_bytes(input_audio.tobytes())
        received = ws.receive_bytes()

    voice.start_convert_chunk_bulk.assert_called_once_with()
    np.testing.assert_array_equal(voice.convert_chunk_bulk.call_args.args[0], input_audio)
    assert received == expected_audio.astype("<f4").tobytes()


def test_audio_websocket_without_converted_output_sends_no_response(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_audio = np.array([0.125, -0.75], dtype=np.float32)
    voice = MagicMock()
    voice.is_convert_chunk_bulk_started.return_value = True
    voice.convert_chunk_bulk.side_effect = [(None, None), (expected_audio, None)]
    monkeypatch.setattr(vcserver_websocket.VoiceChanger, "get_instance", lambda: voice)
    monkeypatch.setattr(vcserver_websocket.LocalVoiceChangerInterface, "get_instance", EventEmitter)

    app = FastAPI()
    hub = vcserver_websocket.WebSocketHub()
    app.include_router(hub.router)

    first_input = np.zeros(2, dtype=np.float32)
    second_input = np.array([0.5, 0.25], dtype=np.float32)
    with TestClient(app).websocket_connect("/api/ws/audio") as ws:
        ws.send_bytes(first_input.tobytes())
        ws.send_bytes(second_input.tobytes())
        received = ws.receive_bytes()

    voice.start_convert_chunk_bulk.assert_not_called()
    assert voice.convert_chunk_bulk.call_count == 2
    assert received == expected_audio.astype("<f4").tobytes()


def test_audio_websocket_ignores_unaligned_binary_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_audio = np.array([0.5], dtype=np.float32)
    voice = MagicMock()
    voice.is_convert_chunk_bulk_started.return_value = True
    voice.convert_chunk_bulk.return_value = (expected_audio, None)
    monkeypatch.setattr(vcserver_websocket.VoiceChanger, "get_instance", lambda: voice)
    monkeypatch.setattr(vcserver_websocket.LocalVoiceChangerInterface, "get_instance", EventEmitter)

    app = FastAPI()
    hub = vcserver_websocket.WebSocketHub()
    app.include_router(hub.router)

    valid_audio = np.array([0.25], dtype=np.float32)
    with TestClient(app).websocket_connect("/api/ws/audio") as ws:
        ws.send_bytes(b"\x01\x02\x03")
        ws.send_bytes(valid_audio.tobytes())
        received = ws.receive_bytes()

    voice.convert_chunk_bulk.assert_called_once()
    np.testing.assert_array_equal(voice.convert_chunk_bulk.call_args.args[0], valid_audio)
    assert received == expected_audio.astype("<f4").tobytes()


@pytest.mark.asyncio
async def test_status_event_from_audio_thread_reaches_websocket_client(monkeypatch: pytest.MonkeyPatch) -> None:
    voice = EventEmitter()
    audio = EventEmitter()
    monkeypatch.setattr(vcserver_websocket.VoiceChanger, "get_instance", lambda: voice)
    monkeypatch.setattr(vcserver_websocket.LocalVoiceChangerInterface, "get_instance", lambda: audio)

    app = FastAPI()
    hub = vcserver_websocket.WebSocketHub()
    hub.subscribe_core_events()
    app.include_router(hub.router)

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]

        async with websockets.connect(f"ws://127.0.0.1:{port}/api/ws/status", proxy=None) as ws:
            output_data = {"inputRms": 0.25, "outputRms": 0.5}
            await asyncio.to_thread(audio.emit, "status", "realtime_output_status", output_data)
            first_message = await asyncio.wait_for(ws.recv(), 3)
            assert isinstance(first_message, str)

            process_data = {"inputBufferSize": 4800, "elapsedTime": 0.05}
            await asyncio.to_thread(voice.emit, "status", "realtime_process_status", process_data)
            second_message = await asyncio.wait_for(ws.recv(), 3)
            assert isinstance(second_message, str)

        import json

        assert json.loads(first_message) == {"type": "realtime_output_status", "data": output_data}
        assert json.loads(second_message) == {"type": "realtime_process_status", "data": process_data}
    finally:
        await hub.close_all()
        server.should_exit = True
        await asyncio.to_thread(thread.join, 5)
        assert not thread.is_alive()
