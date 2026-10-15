import asyncio
import logging
import struct

import numpy as np
import socketio

from vcclient.const import LOGGER_NAME
from vcclient.server.event_emitter import EventEmitter
from vcclient.server.event_emitter_manager import EventEmitterManager
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


class SocketIONamespace(EventEmitter, socketio.AsyncNamespace):
    sid: int = 0

    async def emit_to(self, event, data, to):

        await self.emit(event, data, to=to)

    def emit_coroutine(self, event, data, to=(None,)):

        if to is None:
            asyncio.run(self.emit_to(event, data, to=None))

            return None

        asyncio.run(self.emit_to(event, data, to=to))

    def __init__(self=None, namespace=None):

        super().__init__(namespace)

        self.namespace = namespace

        EventEmitterManager.get_instance().set_event_emitter(self)

    def get_instance(cls, list_all_sids):

        if not hasattr(cls, "_instance"):
            cls._instance = cls("/test")

            cls._instance.list_all_sids = list_all_sids

        return cls._instance

    get_instance = classmethod(get_instance)

    def on_connect(self, sid, environ):

        self.sid = sid

        logging.getLogger(LOGGER_NAME).info(f"""connect sid: {sid}""")

    async def on_request_message(self, sid, msg):
        try:
            self.sid = sid
            timestamp = int(msg[0])
            bulk = bool(msg[1])
            data = msg[2]
            if isinstance(data, str):
                print(type(data))
                print(data)
                await self.emit("response", [timestamp, 0], to=sid)
                return None
            data_size = len(data) // struct.calcsize("<f")
            unpacked_data = np.array(struct.unpack(f"<{data_size}f", data)).astype(np.float32)
            vc = VoiceChanger.get_instance()
            if vc.is_convert_chunk_bulk_started() is False:
                vc.start_convert_chunk_bulk()
            if bulk:
                converted_np, _, performance_data = vc.convert_chunk_bulk(unpacked_data)
            else:
                converted_np, _, performance_data = vc.convert_chunk(unpacked_data, direct_from_server=True)
            if converted_np is None:
                return None
            audio1 = converted_np
            if performance_data is not None:
                perf = performance_data.model_dump_json()
            else:
                perf = "{}"
            data_size = len(audio1)
            bin = struct.pack(f"<{data_size}f", *audio1)
            if ConfigurationManager.get_instance().get_voice_changer_configuration().sio_broadcast is True:
                await self.emit("response", [timestamp, bin, perf])
                return None
            else:
                await self.emit("response", [timestamp, bin, perf], to=sid)
                return None
        except Exception as e:
            print(e)
            return None

    def on_disconnect(self, sid):

        pass
