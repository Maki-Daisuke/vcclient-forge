import logging

from fastapi import APIRouter

from vcclient.const import LOGGER_NAME
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.configuration_manager.configuration_manager import (
    ConfigurationManager,
    VoiceChangerConfiguration,
)


class RestAPIConfigurationManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/configuration-manager/configuration", self.get_configuration, methods=["GET"])
        self.router.add_api_route("/api/configuration-manager/configuration", self.put_configuration, methods=["PUT"])

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
        logging.getLogger(LOGGER_NAME).info(f"Configuration updated: {configuration}")
        configuration_manager.set_voice_changer_configuration(configuration)
