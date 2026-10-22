from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from vcclient.server.event_emitter_manager import EventEmitterManager
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.voice_changer_data_types import LocalVoiceChangerInterfaceInfo
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface


class DummyInputParam(BaseModel):
    url: str


class RestAPILocalVoiceChangerInterface:
    def __init__(self) -> None:
        self.router = APIRouter()
        self.router.add_api_route(
            "/api/local-voice-changer-interface/operation/set_dummy_input",
            self.post_set_dummy_input,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/local-voice-changer-interface/operation/start",
            self.post_start,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/local-voice-changer-interface/operation/stop",
            self.post_stop,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/local-voice-changer-interface/operation/truncate-output-buffer",
            self.post_truncate_output_buffer,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/local-voice-changer-interface/information",
            self.get_information,
            methods=["GET"],
        )

        # Underscore aliases for IPC / proxy compatibility
        self.router.add_api_route(
            "/api_local-voice-changer-interface_operation_set_dummy_input",
            self.post_set_dummy_input,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api_local-voice-changer-interface_operation_start",
            self.post_start,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api_local-voice-changer-interface_operation_stop",
            self.post_stop,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api_local-voice-changer-interface_operation_truncate-output-buffer",
            self.post_truncate_output_buffer,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api_local-voice-changer-interface_information",
            self.get_information,
            methods=["GET"],
        )

    def post_set_dummy_input(self, param: DummyInputParam) -> None:
        local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
        local_voice_changer_interface.set_dummy_input(param.url)

    def post_start(self) -> None:
        configuration_manager = ConfigurationManager.get_instance()
        conf = configuration_manager.get_voice_changer_configuration()
        if conf.voice_changer_input_mode == "server":
            local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
            local_voice_changer_interface.start()
            event_emitter = EventEmitterManager.get_instance().get_event_emitter()
            if event_emitter is not None:
                event_emitter.emit_coroutine("command", ["reload"])
            return None
        raise RuntimeError("Input mode for VC is not server-mode.")

    def post_stop(self) -> None:
        local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
        local_voice_changer_interface.stop()

    def get_information(self) -> LocalVoiceChangerInterfaceInfo:
        local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
        return LocalVoiceChangerInterfaceInfo(
            local_voice_changer_interface_active=local_voice_changer_interface.local_voice_changer_enabled is True
        )

    def post_truncate_output_buffer(self) -> None:
        local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
        local_voice_changer_interface.truncate_output_buffer()
