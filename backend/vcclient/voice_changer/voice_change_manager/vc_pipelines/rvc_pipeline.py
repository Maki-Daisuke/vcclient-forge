import logging
from typing import cast

import faiss
import numpy as np
import onnxruntime
from onnx import TensorProto
from onnx.helper import make_graph, make_model, make_node, make_opsetid, make_tensor_value_info

from vcclient.voice_changer.voice_change_manager.device_manager.device_manager import DeviceManager

from ....const import LOGGER_NAME
from ...configuration_manager.configuration_manager import ConfigurationManager
from ...data_types.slot_manager_data_types import RVCSlotInfo
from ...data_types.voice_changer_data_types import RVCInferencerInfo, RVCPipelineInfo
from ...slot_manager.slot_manager import SlotManager
from ...voice_chanager_const import ModelDir, RVCInferencerOnnxVersion
from ..embedders.embedder_manager import EmbedderManager
from ..inferencer.inferrencer_manager import InferencerManager
from ..inferencer.rvc_inferencer import RVCInferencer
from ..pitch_estimator.pitch_estimator_manager import PitchEstimatorManager
from .vc_pipeline import VCPipeline


class RVCPipeline(VCPipeline):
    processing_window: int = 160
    rvc: RVCInferencer

    def __init__(self, slot_info: RVCSlotInfo):
        assert isinstance(slot_info, RVCSlotInfo)
        self.slot_info = slot_info
        self.slot_index = self.slot_info.slot_index
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        self.gpu_device_id = conf.gpu_device_id_int
        self.pitch_estimator_type = self.slot_info.pitch_estimator
        logging.getLogger(LOGGER_NAME).info(
            f"construct new pipelinepitch: slot_index:{self.slot_index}, gpu_device_id:{self.gpu_device_id} pitch_estimator: {self.pitch_estimator_type}"
        )
        self.pitch_estimator = PitchEstimatorManager.get_pitch_estimator(
            self.slot_info.pitch_estimator, conf.gpu_device_id_int
        )
        self.embedder = EmbedderManager.get_embedder(self.slot_info.embedder, conf.gpu_device_id_int)
        assert self.slot_info.model_file is not None
        self.rvc = cast(
            RVCInferencer,
            InferencerManager.get_inferencer(
                self.slot_info.inferencer_type,
                ModelDir / str(self.slot_info.slot_index) / self.slot_info.model_file,
                conf.gpu_device_id_int,
                inferencer_type_version=cast(RVCInferencerOnnxVersion, slot_info.version),
            ),
        )
        if self.slot_info.index_file is not None:
            index, big_npy = self._load_index(ModelDir / str(self.slot_info.slot_index) / self.slot_info.index_file)
        else:
            index, big_npy = None, None
        self.index = index
        self.big_npy = big_npy
        if self.slot_info.embedder == "hubert_base_japanese_l9fp" or self.slot_info.embedder == "hubert_base_l9fp":
            embedder_dim_size = 256
        else:
            embedder_dim_size = 768
        self.onnx_upscaler = self.make_onnx_upscaler(embedder_dim_size, conf.gpu_device_id_int)
        self.audio_buffer = np.zeros([16384], dtype=float)
        self.pitchf_buffer = np.zeros([1, 1], dtype=np.float64)
        if self.slot_info.embedder == "hubert_base_l12" or self.slot_info.embedder == "hubert_base_japanese_l12":
            self.feature_buffer = np.zeros((1, 1, 768), dtype=np.float64)
        else:
            self.feature_buffer = np.zeros((1, 1, 256), dtype=np.float64)
        self.prev_vol = 0

    def _load_index(self, index_file: str):
        try:
            index = faiss.read_index(str(index_file))
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"load index failed. {index_file}")
            raise e
        if index is not None:
            big_npy = index.reconstruct_n(0, index.ntotal)
        else:
            big_npy = None
        return (index, big_npy)

    def make_onnx_upscaler(self, dim_size, gpu_device_id_int, ir_version=9):
        try:
            input = make_tensor_value_info("in", TensorProto.FLOAT, [1, dim_size, None])
            scales = make_tensor_value_info("scales", TensorProto.FLOAT, [None])
            output = make_tensor_value_info("out", TensorProto.FLOAT, [1, dim_size, None])
            resize_node = make_node("Resize", inputs=["in", "", "scales"], outputs=["out"], mode="nearest", axes=[2])
            graph = make_graph([resize_node], "upscaler", [input, scales], [output])
            onnx_model = make_model(graph, ir_version=ir_version, opset_imports=[make_opsetid("", 20)])
            onnx_providers, onnx_provider_options = DeviceManager.get_instance().get_onnx_execution_provider(
                gpu_device_id_int
            )
            return onnxruntime.InferenceSession(
                onnx_model.SerializeToString(), providers=onnx_providers, provider_options=onnx_provider_options
            )
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"make_onnx_upscaler failed. {e}")
            print("make_onnx_upscaler failed.", e)
            raise e

    def get_input_sample_rate(self):

        return 16000

    def get_output_sample_rate(self):

        return self.slot_info.sample_rate

    def get_input_bitdepth(self):

        return np.float32

    def get_output_bitdepth(self):

        return np.float32

    def get_chunk_sec(self):

        return SlotManager.get_instance().get_slot_info(self.slot_index).chunk_sec

    def needs_crossfade(self):

        return True

    def get_pitch_estimator_type(self):

        return self.pitch_estimator_type

    def get_gpu_device_id(self):

        return self.gpu_device_id

    def set_pitch_estimator_type(self, pitch_estimator_type=None):

        logging.getLogger(LOGGER_NAME).info(
            f"""pitch extimator is changed: {self.pitch_estimator_type} -> {pitch_estimator_type}"""
        )

        self.pitch_estimator_type = pitch_estimator_type

        self.pitch_estimator = PitchEstimatorManager.get_pitch_estimator(
            self.slot_info.pitch_estimator, self.gpu_device_id
        )

        logging.getLogger(LOGGER_NAME).info("pitch extimator is changed: done")

    def _generate_inputs(
        self, audio: np.ndarray, crossfade_overlap_sec: float, sola_search_frame_sec: float, extra_frame_sec: float
    ):
        new_frame_size = audio.shape[0]
        crossfade_overlap_size = int(crossfade_overlap_sec * self.get_input_sample_rate())
        sola_search_frame_size = int(sola_search_frame_sec * self.get_input_sample_rate())
        extra_frame_size = int(extra_frame_sec * self.get_input_sample_rate())
        self.audio_buffer = np.concatenate([self.audio_buffer, audio], 0)
        convert_size = new_frame_size + crossfade_overlap_size + sola_search_frame_size + extra_frame_size
        embedder_hop_size = self.processing_window * 1
        hop_mod = convert_size % embedder_hop_size
        if hop_mod != 0:
            convert_size = convert_size + (embedder_hop_size - hop_mod)
        real_convert_size = (new_frame_size + crossfade_overlap_size + sola_search_frame_size) * (
            self.get_output_sample_rate() / self.get_input_sample_rate()
        )
        real_convert_size = int(round(real_convert_size))
        if self.audio_buffer.shape[0] < convert_size:
            self.audio_buffer = np.concatenate([np.zeros([convert_size]), self.audio_buffer])
        self.audio_buffer = self.audio_buffer[-1 * convert_size :]
        crop_offset = -1 * (new_frame_size + crossfade_overlap_size)
        crop_end = -1 * crossfade_overlap_size
        crop = self.audio_buffer[crop_offset:crop_end]
        input_volume = np.sqrt(np.square(crop).mean())
        return (
            self.audio_buffer,
            self.pitchf_buffer,
            self.feature_buffer,
            convert_size,
            input_volume,
            real_convert_size,
        )

    def run(self, audio: np.ndarray, real_crossfade_sec: float):
        assert audio.ndim == 1, "audio should be 1d."
        assert audio.dtype in (np.float32, np.float64), f"audio should be float32 or float64. {audio.dtype}"
        input_sample_num = audio.shape[0]
        slot_info = SlotManager.get_instance().get_slot_info(self.slot_index)
        conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
        crossfacde_overlap_sec = real_crossfade_sec
        sola_search_frame_sec = conf.sola_search_frame_sec
        extra_frame_sec = conf.extra_frame_sec
        index_enabled = self.index is not None and self.big_npy is not None and slot_info.index_ratio > 0
        data = self._generate_inputs(audio, crossfacde_overlap_sec, sola_search_frame_sec, extra_frame_sec)
        audio, prev_pitch, prev_feature, convert_size, vol, real_output_size = data
        reference_volume = 1
        if vol < 1e-06:
            vol_db = -np.inf
        else:
            vol_db = 20 * np.log10(vol / reference_volume)
        if vol_db < conf.noise_gate:
            logging.getLogger(LOGGER_NAME).debug(f"noise gate {vol_db} < {conf.noise_gate}") if logging.getLogger(
                LOGGER_NAME
            ).isEnabledFor(logging.DEBUG) else None
            return np.zeros(real_output_size).astype(float)
        if slot_info.is_f0:
            pitch_coarse, pitch = self.pitch_estimator.estimate(
                audio,
                prev_pitch,
                slot_info.pitch_shift,
                self.get_input_sample_rate(),
                self.processing_window,
                extra_frame_sec,
            )
        else:
            pitch_coarse, pitch = None, None

        feats = self.embedder.extract_features(audio)
        if index_enabled is True:
            new_feats = feats[0]
            feats_length = new_feats.shape[0]
            feats_channels = new_feats.shape[1]
            latest_audio_feats_length = int(round(input_sample_num / 320))
            new_feats = new_feats[-1 * latest_audio_feats_length :, :]
            if new_feats.dtype != np.float32:
                new_feats = new_feats.astype("float32")
            _, ix = self.index.search(new_feats, 1)
            new_feats_retrieved = self.big_npy[ix.squeeze()]
            new_feats_retrieved = np.concatenate(
                [
                    np.zeros((feats_length, feats_channels), dtype=np.float32),
                    prev_feature.squeeze(axis=0)[::2].astype("float32"),
                    new_feats_retrieved,
                ]
            )[-1 * feats_length :]
            feats = (
                new_feats_retrieved[np.newaxis, :] * self.slot_info.index_ratio
                + (1 - self.slot_info.index_ratio) * feats
            )

        feats = feats.transpose(0, 2, 1)
        feats = self.onnx_upscaler.run(["out"], {"in": feats, "scales": np.array([2], dtype=np.float32)})
        assert isinstance(feats[0], np.ndarray)
        feats = feats[0].transpose(0, 2, 1)

        import math

        npy_offset = math.floor(extra_frame_sec * 16000) // 360
        feats = feats[:, npy_offset * 2 :, :]
        if pitch is not None and pitch_coarse is not None:
            pitch = pitch[:, -feats.shape[1] :]
            pitch_coarse = pitch_coarse[:, -feats.shape[1] :]

        feats_len_np = np.array([feats.shape[1]], dtype=np.int64)
        sid = np.array([0], dtype=np.int64)
        converted = self.rvc.infer(feats, feats_len_np, pitch_coarse, pitch, sid, convert_length=real_output_size)
        converted = converted[-real_output_size:]
        self.pitchf_buffer = pitch
        self.feature_buffer = feats

        if conf.volume_tuning_type == "linear":
            converted = converted * vol
        elif conf.volume_tuning_type == "linear_ratio":
            converted_vol = np.sqrt(np.square(converted).mean())
            vol_scaling_factor = vol / converted_vol
            converted = converted * vol_scaling_factor
        elif conf.volume_tuning_type == "sqrt":
            converted = converted * np.sqrt(vol)
        elif conf.volume_tuning_type == "sqrt_ratio":
            converted_vol = np.sqrt(np.square(converted).mean())
            vol_scaling_factor = np.sqrt(vol) / converted_vol
            converted = converted * vol_scaling_factor

        return converted

    def get_pipeline_info(self):
        inferencer_info = self.rvc.get_info()
        assert isinstance(inferencer_info, RVCInferencerInfo)
        return RVCPipelineInfo(
            slot_index=self.slot_index,
            input_sample_rate=self.get_input_sample_rate(),
            output_sample_rate=self.get_output_sample_rate(),
            chunk_sec=self.get_chunk_sec(),
            slot_info=self.slot_info.model_dump(),
            embedder_info=self.embedder.get_info(),
            pitch_estimator_info=self.pitch_estimator.get_info(),
            inferencer_info=inferencer_info,
        )
