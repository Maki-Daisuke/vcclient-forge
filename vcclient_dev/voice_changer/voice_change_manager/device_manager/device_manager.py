import logging

import torch

try:
    import torch_directml

    directml_available = True
except (ImportError, ModuleNotFoundError, Exception):
    directml_available = False

import onnxruntime

from vcclient_dev.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager

from ....const import LOGGER_NAME


class DeviceManager(object):
    _instance = None

    force_tensor: bool = False

    def get_instance(cls):

        if cls._instance is None:
            cls._instance = cls()

        return cls._instance

    get_instance = classmethod(get_instance)

    def __init__(self):

        if directml_available:
            self.gpu_num = torch_directml.device_count()

        else:
            self.gpu_num = torch.cuda.device_count()

        if getattr(torch.backends, "mps", None) is not None:
            pass

        self.mps_enabled = torch.backends.mps.is_available()

        logging.getLogger(LOGGER_NAME).info(
            f"""GPU num: {self.gpu_num}, mps_enabled: {self.mps_enabled}, directml_available: {directml_available}"""
        )

    def get_pytorch_device(self=None, id=None):

        res = self._get_pytorch_device(id)

        logging.getLogger(LOGGER_NAME).info(f"""get_pytorch_device: {res}""")

        return res

    def _get_pytorch_device(self=None, id=None):

        if id < 0 or self.gpu_num == 0:
            if self.mps_enabled is False:
                dev = torch.device("cpu")

                return dev

            dev = torch.device("mps")

            return dev

        if id < self.gpu_num:
            if directml_available:
                dev = torch_directml.device(device_id=id)

                dev = torch.device(dev)

                return dev

            dev = torch.device("cuda", index=id)

            return dev

        print("[Voice Changer] pytorch failed to detect device. fallback to cpu")

        dev = torch.device("cpu")

        return dev

    def get_onnx_execution_provider(self=None, device_id=None):

        res = self._get_onnx_execution_provider(device_id)

        logging.getLogger(LOGGER_NAME).info(f"""get_onnx_execution_privider: {res}""")

        return res

    def _get_onnx_execution_provider(self=None, device_id=None):

        available_providers = onnxruntime.get_available_providers()

        logging.getLogger(LOGGER_NAME).info(f"""available_providers: {available_providers}""")

        cuda_info = GPUDeviceManager.get_instance().get_cuda_info()

        gpu_info = GPUDeviceManager.get_instance().get_gpu_info()

        cuda_len = len(cuda_info)

        gpu_len = len(gpu_info) - 1

        gpu_num = max(cuda_len, gpu_len)

        logging.getLogger(LOGGER_NAME).info(f"""gpu_num: {gpu_num}, cuda_len: {cuda_len}, gpu_len: {gpu_len}""")

        logging.getLogger(LOGGER_NAME).info(f"""gpu_num: {gpu_num}, cuda_len: {cuda_len}, gpu_len: {gpu_len}""")

        if device_id >= 0 and "CUDAExecutionProvider" in available_providers and gpu_num > 0:
            if device_id < gpu_num:
                return (["CUDAExecutionProvider"], [{"device_id": device_id}])

            logging.getLogger(LOGGER_NAME).info(
                f"""device detection error, fallback to cpu. device_id: {device_id} >= dev_num: {gpu_num}"""
            )

            return (
                ["CPUExecutionProvider"],
                [
                    {
                        "intra_op_num_threads": 8,
                        "execution_mode": onnxruntime.ExecutionMode.ORT_PARALLEL,
                        "inter_op_num_threads": 8,
                    }
                ],
            )

        if None >= 0 and "DmlExecutionProvider" in available_providers:
            return (["DmlExecutionProvider"], [{"device_id": device_id}])

        return (
            [None],
            [
                {
                    "intra_op_num_threads": 8,
                    "execution_mode": onnxruntime.ExecutionMode.ORT_PARALLEL,
                    "inter_op_num_threads": 8,
                }
            ],
        )

    def set_force_tensor(self=None, force_tensor=None):

        self.forceTens
