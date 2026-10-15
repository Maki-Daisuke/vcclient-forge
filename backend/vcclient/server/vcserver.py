import asyncio
import importlib.util
import logging
import os
import threading

import portpicker
import uvicorn

from vcclient.const import LOGGER_NAME
from vcclient.server.key_generator import generate_self_signed_cert
from vcclient.server.vcserver_socketio_server import SocketIOServer


class VCServer:
    _instance = None

    port = 0

    server_thread: threading.Thread | None = None

    @classmethod
    def get_instance(
        cls,
        host: str = "127.0.0.1",
        port: int | None = None,
        https: bool = False,
        allow_origins: list[str] | None = None,
    ):
        if cls._instance is None:
            app_fastapi = VCServer(host=host, port=port, https=https, allow_origins=allow_origins)
            cls._instance = app_fastapi
        return cls._instance

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
        https: bool = False,
        allow_origins: list[str] | None = None,
    ):
        super().__init__()
        self.host = host
        self.https = https
        self.allow_origins = allow_origins
        if port is not None:
            self.port = port
            return
        self.port = portpicker.pick_unused_port()

    def start(self):

        this_modeule = importlib.util.find_spec(__name__)

        if this_modeule is None:
            raise Exception("FastAPI instance is not initialized.")

        module_parent = this_modeule.parent

        if self.https is True:
            (cert, key) = generate_self_signed_cert()

            config = uvicorn.Config(
                f"""{module_parent}.vcserver_socketio:serverio_app""",
                host=self.host,
                port=self.port,
                log_level="info",
                log_config=None,
                ssl_keyfile=key,
                ssl_certfile=cert,
            )

        else:
            config = uvicorn.Config(
                f"""{module_parent}.vcserver_socketio:serverio_app""",
                host=self.host,
                port=self.port,
                log_level="info",
                log_config=None,
            )

        self.server = uvicorn.Server(config)

        self.server_thread = threading.Thread(target=self.start_server)

        self.server_thread.start()

        return self.port

    async def stop_all_sockets(self):

        sio = SocketIOServer.get_instance()

        for sid in list(sio.eio.sockets.keys()):
            await sio.disconnect(sid)

    def start_server(self):

        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        logging.getLogger(LOGGER_NAME).info(f"""Starting VCServer on port {self.port}""")

        self.loop = asyncio.new_event_loop()

        asyncio.set_event_loop(self.loop)

        self.loop.create_task(self.server.serve())

        self.loop.run_forever()

    def stop(self):
        if hasattr(self, "server") and self.server:
            self.server.should_exit = True
        logging.getLogger(LOGGER_NAME).info("wait vccserver to stop...")
        if hasattr(self, "loop") and self.loop and self.loop.is_running():
            self.loop.stop()
        if hasattr(self, "server_thread") and self.server_thread and self.server_thread.is_alive():
            self.server_thread.join()
        logging.getLogger(LOGGER_NAME).info("wait vccserver to stop...done")
