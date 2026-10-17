import logging

from ...const import LOGGER_NAME
from ..data_types.voice_changer_data_types import VoiceChangerManagerInfo
from .local_voice_changer_interface import LocalVoiceChangerInterface
from .voice_changer import VoiceChanger


class VoiceChangerManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_info(self):
        logging.getLogger(LOGGER_NAME).info("Getting voice changer manager information.")
        local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
        voice_changer_information = VoiceChanger.get_instance().get_voice_changer_information()

        return VoiceChangerManagerInfo(
            local_voice_changer_interface_active=local_voice_changer_interface.local_voice_changer_enabled is True,
            voice_changer_information=voice_changer_information,
        )
