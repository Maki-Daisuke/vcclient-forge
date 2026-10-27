from __future__ import annotations

import os
import time

from ...exception import (
    ERROR_CODE_LOCAL_INPUT_DEVICE_CANNOT_BE_NONE,
    ERROR_CODE_LOCAL_INPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED,
    ERROR_CODE_LOCAL_MONITOR_DEVICE_SAMPLE_RATE_CHECK_FAILED,
    ERROR_CODE_LOCAL_OUTPUT_DEVICE_CANNOT_BE_NONE,
    ERROR_CODE_LOCAL_OUTPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED,
    ERROR_CODE_LOCAL_VOICE_CHANGER_INTERFACE_ACTIVE,
    VCClientError,
)
from ..audio_device_manager.audio_device_manager import AudioDeviceManager
from ..data_types.data_types import VoiceChangerConfiguration
from ..voice_changer_const import ConfigFile


class ConfigurationManager:
    _instance: ConfigurationManager | None = None
    voice_changer_configuration: VoiceChangerConfiguration

    @classmethod
    def get_instance(cls) -> ConfigurationManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.reload()
        self.voice_changer_configuration.recording_started = False
        self.voice_changer_configuration.pass_through = False

    def reload(self) -> None:
        if os.path.exists(ConfigFile):
            with open(ConfigFile, "r", encoding="utf-8") as f:
                self.voice_changer_configuration = VoiceChangerConfiguration.model_validate_json(f.read())
            self.voice_changer_configuration.recording_started = False
            self.voice_changer_configuration.pass_through = False
            return None

        self.voice_changer_configuration = VoiceChangerConfiguration()
        self.save_voice_changer_configuration()

    def get_voice_changer_configuration(self) -> VoiceChangerConfiguration:
        return self.voice_changer_configuration

    def set_voice_changer_configuration(self, conf: VoiceChangerConfiguration) -> None:
        from ..voice_change_manager.local_voice_changer_interface import (
            LocalVoiceChangerInterface,
            local_voice_changer_loop_interval_sec,
        )

        if self.voice_changer_configuration.voice_changer_input_mode != conf.voice_changer_input_mode:
            local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
            if local_voice_changer_interface.stop_flag is False:
                raise VCClientError(ERROR_CODE_LOCAL_VOICE_CHANGER_INTERFACE_ACTIVE)

        if conf.recording_started and not self.voice_changer_configuration.recording_started:
            from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

            vc = VoiceChanger.get_instance()
            vc.start_recording()
        elif not conf.recording_started and self.voice_changer_configuration.recording_started:
            from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger

            vc = VoiceChanger.get_instance()
            vc.stop_recording()

        change_audio = False
        if (
            conf.audio_input_device_index != self.voice_changer_configuration.audio_input_device_index
            or conf.audio_input_device_sample_rate != self.voice_changer_configuration.audio_input_device_sample_rate
            or conf.audio_output_device_index != self.voice_changer_configuration.audio_output_device_index
            or conf.audio_output_device_sample_rate != self.voice_changer_configuration.audio_output_device_sample_rate
            or conf.audio_monitor_device_index != self.voice_changer_configuration.audio_monitor_device_index
            or conf.audio_monitor_device_sample_rate
            != self.voice_changer_configuration.audio_monitor_device_sample_rate
            or conf.wasapi_exclude_emabled != self.voice_changer_configuration.wasapi_exclude_emabled
        ):
            change_audio = True

        if change_audio is True:
            local_voice_changer_interface = LocalVoiceChangerInterface.get_instance()
            if local_voice_changer_interface.local_voice_changer_enabled is True:
                active_flag = True
            else:
                active_flag = False

            if active_flag == True:
                if conf.audio_input_device_index == -1:
                    raise VCClientError(ERROR_CODE_LOCAL_INPUT_DEVICE_CANNOT_BE_NONE)
                if conf.audio_output_device_index == -1:
                    raise VCClientError(ERROR_CODE_LOCAL_OUTPUT_DEVICE_CANNOT_BE_NONE)

            if active_flag:
                local_voice_changer_interface.stop()
                time.sleep(local_voice_changer_loop_interval_sec * 2)

            try:
                audio_device_manager = AudioDeviceManager.get_instance()
                if conf.audio_input_device_index != -1 and conf.audio_input_device_sample_rate != -1:
                    available = audio_device_manager.check_available_sample_rate(
                        conf.audio_input_device_index, conf.audio_input_device_sample_rate, "audioinput"
                    )
                    if not available:
                        raise VCClientError(ERROR_CODE_LOCAL_INPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED)
                if conf.audio_output_device_index != -1 and conf.audio_output_device_sample_rate != -1:
                    available = audio_device_manager.check_available_sample_rate(
                        conf.audio_output_device_index, conf.audio_output_device_sample_rate, "audiooutput"
                    )
                    if not available:
                        raise VCClientError(ERROR_CODE_LOCAL_OUTPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED)
                if conf.audio_monitor_device_index != -1 and conf.audio_monitor_device_sample_rate != -1:
                    available = audio_device_manager.check_available_sample_rate(
                        conf.audio_monitor_device_index, conf.audio_monitor_device_sample_rate, "audiooutput"
                    )
                    if not available:
                        raise VCClientError(ERROR_CODE_LOCAL_MONITOR_DEVICE_SAMPLE_RATE_CHECK_FAILED)
            finally:
                if active_flag:
                    local_voice_changer_interface.setup()
                    local_voice_changer_interface.start()

        input_sample_rate = self.voice_changer_configuration.input_sample_rate
        output_sample_rate = self.voice_changer_configuration.output_sample_rate
        monitor_sample_rate = self.voice_changer_configuration.monitor_sample_rate
        self.voice_changer_configuration = conf
        self.voice_changer_configuration.input_sample_rate = input_sample_rate
        self.voice_changer_configuration.output_sample_rate = output_sample_rate
        self.voice_changer_configuration.monitor_sample_rate = monitor_sample_rate
        self.save_voice_changer_configuration()

    def save_voice_changer_configuration(self) -> None:
        with open(ConfigFile, "w", encoding="utf-8") as f:
            f.write(
                self.voice_changer_configuration.model_dump_json(
                    indent=4,
                    exclude={"pass_through", "recording_started"},
                )
            )
