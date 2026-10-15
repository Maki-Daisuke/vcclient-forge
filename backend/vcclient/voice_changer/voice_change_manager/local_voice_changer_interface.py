import logging
import time
import traceback
from queue import Empty, Queue

import numpy as np
import sounddevice as sd

from vcclient.server.event_emitter_manager import EventEmitterManager

from ...const import LOGGER_NAME
from ...exception import (
    ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED,
    ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED,
    VCClientError,
)
from ..auido_device_manager.audio_device_manager import AudioDeviceManager
from ..configuration_manager.configuration_manager import ConfigurationManager
from .voice_changer import VoiceChanger

local_voice_changer_callback_chunk_sec = 0.01
local_voice_changer_loop_interval_sec = 0.2


class LocalVoiceChangerInterface:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.stop_flag = True
        self.local_voice_changer_enabled = False
        self.out_queue = Queue()
        self.monitor_queue = Queue()
        self.waveform_rest_output = np.array([], dtype=np.float32)
        self.waveform_rest_monitor = np.array([], dtype=np.float32)
        self.split_length = 0

    def start(self):
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        if conf.audio_input_device_index == -1:
            raise VCClientError(ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED)
        if conf.audio_output_device_index == -1:
            raise VCClientError(ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED)
        self.local_voice_changer_enabled = True

    def stop(self):
        self.local_voice_changer_enabled = False
        self.vc = VoiceChanger.get_instance()
        self.vc.stop_convert_chunk_bulk()

    def run(self):
        self.setup()
        self.launch_converter()

    def setup(self):
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        if conf.audio_input_device_index == -1:
            raise VCClientError(ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED)
        if conf.audio_output_device_index == -1:
            raise VCClientError(ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED)
        self.vc = VoiceChanger.get_instance()
        self.vc.start_convert_chunk_bulk()
        self.vc_info = self.vc.get_voice_changer_information()
        self.vc_chunk_sec = self.vc_info.chunk_sec

        if conf.audio_input_device_sample_rate == -1:
            self.audio_input_device_sample_rate = AudioDeviceManager.get_instance().get_default_sample_rate(
                conf.audio_input_device_index, "audioinput"
            )
        else:
            self.audio_input_device_sample_rate = conf.audio_input_device_sample_rate

        if conf.audio_output_device_sample_rate == -1:
            self.audio_output_device_sample_rate = AudioDeviceManager.get_instance().get_default_sample_rate(
                conf.audio_output_device_index, "audiooutput"
            )
        else:
            self.audio_output_device_sample_rate = conf.audio_output_device_sample_rate

        if conf.audio_monitor_device_index != -1 and conf.audio_monitor_device_sample_rate == -1:
            self.audio_monitor_device_sample_rate = AudioDeviceManager.get_instance().get_default_sample_rate(
                conf.audio_monitor_device_index, "audiooutput"
            )
        else:
            self.audio_monitor_device_sample_rate = conf.audio_monitor_device_sample_rate

        logging.getLogger(LOGGER_NAME).info(
            f"audio input device:{conf.audio_input_device_index}, sr:{self.audio_input_device_sample_rate}"
        )
        logging.getLogger(LOGGER_NAME).info(
            f"audio output device:{conf.audio_output_device_index}, sr:{self.audio_output_device_sample_rate}"
        )
        logging.getLogger(LOGGER_NAME).info(
            f"audio monitor device:{conf.audio_monitor_device_index}, sr:{self.audio_monitor_device_sample_rate}"
        )

        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        conf.input_sample_rate = round(self.audio_input_device_sample_rate)
        conf.output_sample_rate = round(self.audio_output_device_sample_rate)
        conf.monitor_sample_rate = round(self.audio_monitor_device_sample_rate)
        self.input_block_size = int(round(local_voice_changer_callback_chunk_sec * self.audio_input_device_sample_rate))
        self.output_block_size = int(
            round(local_voice_changer_callback_chunk_sec * self.audio_output_device_sample_rate)
        )
        self.monitor_block_size = int(
            round(local_voice_changer_callback_chunk_sec * self.audio_monitor_device_sample_rate)
        )
        logging.getLogger(LOGGER_NAME).info(
            f"block size:{self.input_block_size}, {self.output_block_size}, {self.monitor_block_size}"
        )

        exclusive_mode = getattr(conf, "wasapi_exclusive_enabled", getattr(conf, "wasapi_exclude_emabled", False))
        logging.getLogger(LOGGER_NAME).info(f"wasapi_exclusive_enabled:{exclusive_mode}")

        input_audio_device = AudioDeviceManager.get_instance().get_audio_input_device(conf.audio_input_device_index)
        if (
            hasattr(input_audio_device, "host_api")
            and "WASAPI" in input_audio_device.host_api
            and exclusive_mode is True
        ):
            self.input_extra_settings = sd.WasapiSettings(exclusive=True)
        else:
            self.input_extra_settings = None

        output_audio_device = AudioDeviceManager.get_instance().get_audio_output_device(conf.audio_output_device_index)
        if (
            hasattr(output_audio_device, "host_api")
            and "WASAPI" in output_audio_device.host_api
            and exclusive_mode is True
        ):
            self.output_extra_settings = sd.WasapiSettings(exclusive=True)
        else:
            self.output_extra_settings = None

        monitor_audio_device = AudioDeviceManager.get_instance().get_audio_output_device(
            conf.audio_monitor_device_index
        )
        if (
            monitor_audio_device is not None
            and hasattr(monitor_audio_device, "host_api")
            and "WASAPI" in monitor_audio_device.host_api
            and exclusive_mode is True
        ):
            self.monitor_extra_settings = sd.WasapiSettings(exclusive=True)
        else:
            self.monitor_extra_settings = None

        if monitor_audio_device is not None:
            self.vc.set_monitor_enable(True)
        else:
            self.vc.set_monitor_enable(False)

    def launch_converter(self):
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        stop_check_counter = 0
        if self.audio_input_device_sample_rate < 0:
            return None
        with sd.InputStream(
            device=conf.audio_input_device_index,
            callback=self.audio_input_callback,
            samplerate=self.audio_input_device_sample_rate,
            blocksize=self.input_block_size,
            extra_settings=self.input_extra_settings,
        ) as input_stream:
            with sd.OutputStream(
                device=conf.audio_output_device_index,
                callback=self.audio_output_callback,
                samplerate=self.audio_output_device_sample_rate,
                blocksize=self.output_block_size,
                extra_settings=self.output_extra_settings,
            ) as output_stream:
                if conf.audio_monitor_device_index != -1:
                    with sd.OutputStream(
                        device=conf.audio_monitor_device_index,
                        callback=self.audio_monitor_callback,
                        samplerate=self.audio_monitor_device_sample_rate,
                        blocksize=self.monitor_block_size,
                        extra_settings=self.monitor_extra_settings,
                    ) as monitor_stream:
                        logging.getLogger(LOGGER_NAME).info(
                            f"Start Local Voice Changer(2way), sr:[{input_stream.samplerate}, {output_stream.samplerate}, {monitor_stream.samplerate}], ch:[{input_stream.channels}, {output_stream.channels}, {monitor_stream.channels}], depth:[{input_stream.dtype}, {output_stream.dtype}, {monitor_stream.dtype}]"
                        )
                        while True:
                            time.sleep(local_voice_changer_loop_interval_sec)
                            stop_check_counter += 1
                            if self.local_voice_changer_enabled is False:
                                break
                            if stop_check_counter % 100 == 0:
                                logging.getLogger(LOGGER_NAME).debug(
                                    f"Start Local Voice Changer(2way) counter:{stop_check_counter}, sr:[{input_stream.samplerate}, {output_stream.samplerate}, {monitor_stream.samplerate}], ch:[{input_stream.channels}, {output_stream.channels}, {monitor_stream.channels}], depth:[{input_stream.dtype}, {output_stream.dtype}, {monitor_stream.dtype}]"
                                ) if logging.getLogger(LOGGER_NAME).isEnabledFor(logging.DEBUG) else None
                else:
                    logging.getLogger(LOGGER_NAME).info(
                        f"Start Local Voice Changer(1way), sr:[{input_stream.samplerate}, {output_stream.samplerate}], ch:[{input_stream.channels}, {output_stream.channels}], depth:[{input_stream.dtype}, {output_stream.dtype}]"
                    )
                    while True:
                        time.sleep(local_voice_changer_loop_interval_sec)
                        stop_check_counter += 1
                        if self.local_voice_changer_enabled is False:
                            break
                        if stop_check_counter % 100 == 0:
                            logging.getLogger(LOGGER_NAME).info(
                                f"Start Local Voice Changer(1way)  counter:{stop_check_counter}, sr:[{input_stream.samplerate}, {output_stream.samplerate}], ch:[{input_stream.channels}, {output_stream.channels}], depth:[{input_stream.dtype}, {output_stream.dtype}]"
                            )
        logging.getLogger(LOGGER_NAME).info("Local Voice Changer main thread stopped")

    def audio_input_callback(self, indata, frames, times, status):
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        try:
            indata = indata[:, 0].copy() * conf.audio_input_device_gain
            converted, converted_for_monitor, performance_data = self.vc.convert_chunk_bulk(indata)
            event_emitter = EventEmitterManager.get_instance().get_event_emitter()
            if event_emitter is not None and performance_data is not None:
                event_emitter.emit_coroutine("perf", performance_data.model_dump_json())

            if converted is not None:
                if self.waveform_rest_output.dtype != converted.dtype:
                    self.waveform_rest_output = np.array([], dtype=converted.dtype)
                self.waveform_rest_output = np.concatenate([self.waveform_rest_output, converted])
                splitted_waveforms = [
                    self.waveform_rest_output[i : i + self.output_block_size]
                    for i in range(0, len(self.waveform_rest_output), self.output_block_size)
                ]
                self.split_length = len(splitted_waveforms)
                if len(splitted_waveforms[-1]) < self.output_block_size:
                    self.waveform_rest_output = splitted_waveforms.pop()
                else:
                    self.waveform_rest_output = np.array([], dtype=converted.dtype)
                for w in splitted_waveforms:
                    self.out_queue.put(w)

            if converted_for_monitor is not None:
                if self.waveform_rest_monitor.dtype != converted_for_monitor.dtype:
                    self.waveform_rest_monitor = np.array([], dtype=converted_for_monitor.dtype)
                self.waveform_rest_monitor = np.concatenate([self.waveform_rest_monitor, converted_for_monitor])
                splitted_waveforms = [
                    self.waveform_rest_monitor[i : i + self.monitor_block_size]
                    for i in range(0, len(self.waveform_rest_monitor), self.monitor_block_size)
                ]
                self.split_length = len(splitted_waveforms)
                if len(splitted_waveforms[-1]) < self.monitor_block_size:
                    self.waveform_rest_monitor = splitted_waveforms.pop()
                else:
                    self.waveform_rest_monitor = np.array([], dtype=converted_for_monitor.dtype)
                for w in splitted_waveforms:
                    self.monitor_queue.put(w)
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"audio input callback ex:{e}")
            logging.getLogger(LOGGER_NAME).error(f"audio input {traceback.format_exc()}")

    def audio_output_callback(self, outdata, frames, times, status):
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        current_voice_changer_type = VoiceChanger.get_instance().get_voice_changer_information().voice_changer_type
        try:
            if current_voice_changer_type == "Beatrice_v2":
                buffer_for_trancate = 3
            else:
                buffer_for_trancate = self.split_length * conf.server_device_trancate_buffer_ratio
                buffer_for_trancate = max(buffer_for_trancate, 3)

            if self.out_queue.qsize() > self.split_length + buffer_for_trancate:
                logging.getLogger(LOGGER_NAME).info(f"audio_output_callback trancate queue: {self.out_queue.qsize()}")
                for i in range(self.out_queue.qsize()):
                    out_wav = self.out_queue.get()
            else:
                out_wav = self.out_queue.get(timeout=0.1)

            out_wav = out_wav.reshape(-1, 1)
            out_wav = np.repeat(out_wav, outdata.shape[1]).reshape(-1, outdata.shape[1])
            out_wav = out_wav * conf.audio_output_device_gain
            outdata[:, :] = out_wav[:, :]
        except Empty as e:
            logging.getLogger(LOGGER_NAME).debug(f"audio output callback ex: empty queue :{e}")
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"audio output callback ex:{e}")
            logging.getLogger(LOGGER_NAME).error(f"audio output {traceback.format_exc()}")

    def audio_monitor_callback(self, outdata, frames, times, status):
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        current_voice_changer_type = VoiceChanger.get_instance().get_voice_changer_information().voice_changer_type
        try:
            if current_voice_changer_type == "Beatrice_v2":
                buffer_for_trancate = 3
            else:
                buffer_for_trancate = self.split_length * conf.server_device_trancate_buffer_ratio
                buffer_for_trancate = max(buffer_for_trancate, 3)

            if self.monitor_queue.qsize() > self.split_length + buffer_for_trancate:
                for i in range(self.monitor_queue.qsize()):
                    out_wav = self.monitor_queue.get()
            else:
                out_wav = self.monitor_queue.get(timeout=0.1)

            out_wav = out_wav.reshape(-1, 1)
            out_wav = np.repeat(out_wav, outdata.shape[1]).reshape(-1, outdata.shape[1])
            out_wav = out_wav * conf.audio_output_device_gain
            outdata[:, :] = out_wav[:, :]
        except Empty as e:
            logging.getLogger(LOGGER_NAME).debug(f"audio monitor callback ex: empty queue :{e}")
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"audio monitor callback ex:{e}")
            logging.getLogger(LOGGER_NAME).error(f"audio monitor {traceback.format_exc()}")
