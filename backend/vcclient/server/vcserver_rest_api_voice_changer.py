from fastapi import APIRouter

from vcclient.logger import logger
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.data_types.voice_changer_data_types import VoiceChangerManagerInfo
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


class RestAPIVoiceChanger:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route(
            "/api/voice-changer-manager/information", self.get_voice_changer_information, methods=["GET"]
        )

    def get_voice_changer_information(self) -> VoiceChangerManagerInfo:
        local_vc = LocalVoiceChangerInterface.get_instance()
        vc_info = VoiceChanger.get_instance().get_voice_changer_information()
        info = VoiceChangerManagerInfo(
            local_voice_changer_interface_active=local_vc.local_voice_changer_enabled is True,
            voice_changer_information=vc_info,
        )
        logger.info("get_voice_changer_information %s", info)
        return info
