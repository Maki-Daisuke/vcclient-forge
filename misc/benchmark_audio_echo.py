"""Compare binary echo RTT over raw WebSocket and Socket.IO.

Run from the repository root:
    uv run --project backend --with aiohttp python misc/benchmark_audio_echo.py

By default this starts an isolated benchmark server, not the application's audio
server. Pass --url with an HTTP(S) origin to use an existing benchmark server.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import statistics
import struct
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import aiohttp
import socketio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


def create_app():
    api = FastAPI()
    sio = socketio.AsyncServer(async_mode="asgi", logger=False, engineio_logger=False)

    @api.websocket("/ws/audio/echo")
    async def websocket_echo(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                payload = await websocket.receive_bytes()
                await websocket.send_bytes(payload)
        except WebSocketDisconnect:
            pass

    @sio.on("audio_echo", namespace="/bench")
    async def socketio_echo(sid: str, payload: bytes):
        await sio.emit("audio_echo_response", payload, to=sid, namespace="/bench")

    return socketio.ASGIApp(sio, other_asgi_app=api)


async def serve():
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(), host="127.0.0.1", port=0, log_level="error", access_log=False
        )
    )
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            await task
            raise RuntimeError("Benchmark server did not start")
        await asyncio.sleep(0.01)
    sockets = server.servers[0].sockets
    if not sockets:
        raise RuntimeError("Benchmark server has no listening socket")
    print(json.dumps({"port": sockets[0].getsockname()[1]}), flush=True)
    await task


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(values: list[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": max(values),
    }


async def measure(
    exchange: Callable[[bytes], Awaitable[bytes]],
    payload: bytes,
    warmup: int,
    count: int,
    pace: float,
):
    result: list[float] = []
    for index in range(warmup + count):
        started = time.perf_counter_ns()
        response = await asyncio.wait_for(exchange(payload), timeout=5)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        if response != payload:
            raise RuntimeError("Echo payload did not match the sent data")
        if index >= warmup:
            result.append(elapsed)
        if pace:
            remaining = pace - (time.perf_counter_ns() - started) / 1_000_000_000
            if remaining > 0:
                await asyncio.sleep(remaining)
    return result


async def run_benchmark(
    base: str, count: int, warmup: int, rounds: int, sizes: list[int], pace: float
):
    results: dict[str, dict[str, list[float]]] = {
        str(size): {"websocket": [], "socketio": []} for size in sizes
    }
    async with aiohttp.ClientSession() as session:  # noqa: SIM117
        async with session.ws_connect(f"{base}/ws/audio/echo", compress=0) as ws:
            sio = socketio.AsyncClient(
                http_session=session,
                logger=False,
                engineio_logger=False,
                reconnection=False,
            )
            replies: asyncio.Queue[bytes] = asyncio.Queue()

            @sio.on("audio_echo_response", namespace="/bench")
            async def on_response(data):
                await replies.put(data)

            await sio.connect(base, transports=["websocket"], namespaces=["/bench"])

            async def raw_exchange(payload: bytes) -> bytes:
                await ws.send_bytes(payload)
                message = await ws.receive()
                if message.type != aiohttp.WSMsgType.BINARY:
                    raise RuntimeError(f"Unexpected WebSocket response: {message.type}")
                return message.data

            async def socketio_exchange(payload: bytes) -> bytes:
                await sio.emit("audio_echo", payload, namespace="/bench")
                return await replies.get()

            exchanges = {"websocket": raw_exchange, "socketio": socketio_exchange}
            try:
                for round_index in range(rounds):
                    for size in sizes:
                        # Deterministic float32 PCM-like samples; no actual audio capture.
                        payload = struct.pack(
                            f"<{size}f", *(math.sin(i / 16) * 0.5 for i in range(size))
                        )
                        names = (
                            ("websocket", "socketio")
                            if round_index % 2 == 0
                            else ("socketio", "websocket")
                        )
                        for name in names:
                            print(
                                f"round {round_index + 1}/{rounds}, {size} samples, {name}",
                                file=sys.stderr,
                                flush=True,
                            )
                            result = await measure(
                                exchanges[name], payload, warmup, count, pace
                            )
                            results[str(size)][name].extend(result)
            finally:
                await sio.disconnect()
    return {
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "aiohttp": aiohttp.__version__,
        },
        "setup": {
            "sample_rate_hz": 48000,
            "channels": 1,
            "format": "float32 little-endian",
            "rounds": rounds,
            "warmup_per_case": warmup,
            "samples_per_case_per_round": count,
            "pace_seconds": pace,
            "client": "Python aiohttp; python-socketio AsyncClient for Socket.IO",
            "target": base,
            "transport": "TCP, WebSocket transport for both",
            "mode": "one outstanding message; connection setup excluded",
        },
        "results": {
            size: {name: summarize(values) for name, values in modes.items()}
            for size, modes in results.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--url", help="Use an existing benchmark server instead of starting a local one"
    )
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--sizes", type=int, nargs="+", default=[2400, 4800, 9600])
    parser.add_argument("--pace-ms", type=float, default=0)
    args = parser.parse_args()
    if args.serve:
        asyncio.run(serve())
        return
    if (
        args.count < 1
        or args.warmup < 0
        or args.rounds < 1
        or any(size < 1 for size in args.sizes)
        or args.pace_ms < 0
    ):
        parser.error(
            "counts and sizes must be positive; warmup and pace must not be negative"
        )
    if args.url:
        parsed = urlsplit(args.url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            parser.error(
                "--url must be an HTTP(S) origin without a path, query, fragment, or credentials"
            )
        base = args.url.rstrip("/")
        results = asyncio.run(
            run_benchmark(
                base,
                args.count,
                args.warmup,
                args.rounds,
                args.sizes,
                args.pace_ms / 1000,
            )
        )
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return
    process = subprocess.Popen(
        [sys.executable, __file__, "--serve"],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready = json.loads(process.stdout.readline())
        results = asyncio.run(
            run_benchmark(
                f"http://127.0.0.1:{ready['port']}",
                args.count,
                args.warmup,
                args.rounds,
                args.sizes,
                args.pace_ms / 1000,
            )
        )
        print(json.dumps(results, indent=2, ensure_ascii=False))
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    main()
