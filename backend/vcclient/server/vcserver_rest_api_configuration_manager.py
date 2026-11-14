from fastapi import APIRouter, HTTPException

from vcclient.logger import logger
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.configuration_manager.configuration_manager import (
    ConfigurationManager,
    VoiceChangerConfiguration,
)
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


class RestAPIConfigurationManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/configuration-manager/configuration", self.get_configuration, methods=["GET"])
        self.router.add_api_route("/api/configuration-manager/configuration", self.put_configuration, methods=["PUT"])
        self.router.add_api_route("/api/configuration-manager/clear", self.clear_configuration, methods=["POST"])
        self.router.add_api_route("/api_configuration-manager_configuration", self.get_configuration, methods=["GET"])
        self.router.add_api_route("/api_configuration-manager_configuration", self.put_configuration, methods=["PUT"])

    def get_configuration(self, reload: bool = False):
        configuration_manager = ConfigurationManager.get_instance()
        if reload:
            configuration_manager.reload()
        return configuration_manager.get_voice_changer_configuration()

    def put_configuration(self, configuration: VoiceChangerConfiguration):
        """
        注意: VoiceChangerConfigurationには初期値が設定されているので、フィールドが欠けていても初期値で補われてエラーが出ない。
        フィールドの型が異なる場合はエラーが出る。
        """
        configuration_manager = ConfigurationManager.get_instance()
        logger.info("Configuration updated: %s", configuration)
        configuration_manager.set_voice_changer_configuration(configuration)
        VoiceChanger.get_instance().check_and_update_pipeline()

    def clear_configuration(self) -> VoiceChangerConfiguration:
        """Reset configuration to defaults while stopped without deleting models or modules."""
        local = LocalVoiceChangerInterface.get_instance()
        with local.lifecycle_lock:
            if local.local_voice_changer_enabled or local.stream_running:
                raise HTTPException(status_code=409, detail="Audio must be stopped before clearing configuration")
            voice = VoiceChanger.get_instance()
            if voice.is_convert_chunk_bulk_started():
                raise HTTPException(status_code=409, detail="Audio must be stopped before clearing configuration")
            configuration_manager = ConfigurationManager.get_instance()
            logger.info("Clearing configuration to defaults")
            configuration_manager.clear_configuration()
            voice.initialize()
            return configuration_manager.get_voice_changer_configuration()
