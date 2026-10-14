import logging
from typing import OrderedDict

import torch

from ....const import LOGGER_NAME
from ....exception import (
    ERROR_CODE_RVC_MERGE_FAILED_FIRST_MODEL_NOT_FOUND,
    ERROR_CODE_RVC_MERGE_FAILED_INVALID_PARAM,
    ERROR_CODE_RVC_MERGE_FAILED_UNSUPPORTED_MODEL_TYPE,
    VCClientError,
)
from ...slot_manager.slot_manager import SlotManager


class RVCModelMerger:
    def _estimate_inferencer_type(self=None, params=None):

        first_model = SlotManager.get_instance().get_slot_info(params.files[0].slot_index)

        if first_model is None:
            raise VCClientError(ERROR_CODE_RVC_MERGE_FAILED_FIRST_MODEL_NOT_FOUND)

    # WARNING: Decompyle incomplete

    def _extract(self=None, ckpt=None):

        a = ckpt["model"]

        opt = OrderedDict()

        opt["weight"] = {}

        for key in a.keys():
            if "enc_q" in key:
                continue

            opt["weight"][key] = a[key]

        return opt

    def _load_weight(self=None, model_file=None):

        state_dict = torch.load(model_file, map_location="cpu", weights_only=False)

        logging.getLogger(LOGGER_NAME).info(f"""statedict:{state_dict.keys()}""")

        if "model" in state_dict:
            logging.getLogger(LOGGER_NAME).warn("pth has model attribute.")

            weight = self._extract(state_dict)

            return (weight, state_dict)

        weight = state_dict["weight"]
        return (weight, state_dict)

    def merge(self=None, store_path=None, params=None):

        if len(params.files) == 0:
            raise VCClientError(ERROR_CODE_RVC_MERGE_FAILED_INVALID_PARAM, "len(params.files) == 0")

        inferencer_type = self._estimate_inferencer_type(params)

        if inferencer_type not in (
            "pyTorchRVC",
            "pyTorchRVCNono",
            "pyTorchRVCv2",
            "pyTorchRVCv2Nono",
            "pyTorchDDPN",
            "pyTorchDDPNNono",
        ):
            logging.getLogger(LOGGER_NAME).error(f"""rvc merge, unsupported inferencer_type:{inferencer_type}""")

            raise VCClientError(
                ERROR_CODE_RVC_MERGE_FAILED_UNSUPPORTED_MODEL_TYPE, f"""unsupported inferencer_type:{inferencer_type}"""
            )

        weights = []

        alphas = []

    # WARNING: Decompyle incomplete
