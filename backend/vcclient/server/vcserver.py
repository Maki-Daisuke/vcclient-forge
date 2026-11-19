from __future__ import annotations

import asyncio
import os
import threading
from typing import TYPE_CHECKING

import portpicker
import uvicorn

from vcclient.logger import logger
from vcclient.server.vcserver_rest_api import get_rest_api

if TYPE_CHECKING:
    from fastapi import FastAPI

    from vcclient.server.vcserver_websocket import WebSocketHub


class VCServer:
    port: int = 0
    server_thread: threading.Thread | None = None
    server: uvicorn.Server
    loop: asyncio.AbstractEventLoop
    app: FastAPI
    ws_hub: WebSocketHub

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
    ):
        super().__init__()
        self.host = host
        self.port = port if port is not None else portpicker.pick_unused_port()
        self.app = get_rest_api()
        self.ws_hub = self.app.state.ws_hub

    def start(self):
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
            log_config=None,
            timeout_graceful_shutdown=5,
        )

        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self.start_server)
        self.server_thread.start()
        return self.port

    async def stop_all_sockets(self) -> None:
        await self.ws_hub.close_all()

    def start_server(self):
        logger.info("Starting VCServer on port %s", self.port)
        if os.name == "nt":
            self.loop = asyncio.SelectorEventLoop()
        else:
            self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.server.serve())
        finally:
            try:
                self.loop.run_until_complete(self.stop_all_sockets())
            except Exception:
                pass

            pending = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

            try:
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            except Exception:
                pass
            self.loop.close()

    def stop(self):
        logger.info("wait vcserver to stop...")
        if hasattr(self, "loop") and self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.ws_hub.close_all(), self.loop)
            try:
                future.result(timeout=2)
            except Exception:
                pass
        if hasattr(self, "server") and self.server:
            self.server.should_exit = True
        if hasattr(self, "server_thread") and self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=10)
            if self.server_thread.is_alive():
                logger.error("Server thread failed to terminate within timeout")
                return False
        logger.info("wait vcserver to stop...done")
        return True
