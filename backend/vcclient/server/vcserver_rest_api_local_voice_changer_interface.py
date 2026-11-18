from __future__ import annotations

from fastapi import APIRouter

from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.voice_changer_data_types import LocalVoiceChangerInterfaceInfo
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface


class RestAPILocalVoiceChangerInterface:
    def __init__(self) -> None:
        self.router = APIRouter()
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
            "/api/local-voice-changer-interface/information",
            self.get_information,
            methods=["GET"],
        )

    def post_start(self) -> None:
        configuration_manager = ConfigurationManager.get_instance()
        conf = configuration_manager.get_voice_changer_configuration()
        if conf.voice_changer_input_mode == "server":
            local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
            local_voice_changer_interface.start()
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
