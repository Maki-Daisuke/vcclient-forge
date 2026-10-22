import onnxruntime

from vcclient.logger import logger
from vcclient.utils.cuda_env import setup_cuda_env
from vcclient.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager


class DeviceManager:
    _instance = None

    @classmethod
    def get_instance(cls) -> "DeviceManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        setup_cuda_env()
        logger.info("DeviceManager initialized in pure-ONNX mode.")

    def get_onnx_execution_provider(self, device_id: int) -> tuple[list[str], list[dict]]:
        res = self._get_onnx_execution_provider(device_id)
        logger.info("get_onnx_execution_provider: %s", res)
        return res

    def _get_onnx_execution_provider(self, device_id: int) -> tuple[list[str], list[dict]]:
        available_providers = onnxruntime.get_available_providers()
        logger.info("available_providers: %s", available_providers)

        cuda_info = GPUDeviceManager.get_instance().get_cuda_info()
        gpu_info = GPUDeviceManager.get_instance().get_gpu_info()

        cuda_len = len(cuda_info)
        gpu_len = len(gpu_info) - 1
        gpu_num = max(cuda_len, gpu_len)

        logger.info("gpu_num: %s, cuda_len: %s, gpu_len: %s", gpu_num, cuda_len, gpu_len)

        if device_id >= 0 and "CUDAExecutionProvider" in available_providers and gpu_num > 0:
            if device_id < gpu_num:
                return (["CUDAExecutionProvider"], [{"device_id": device_id}])

            logger.info("device detection error, fallback to cpu. device_id: %s >= dev_num: %s", device_id, gpu_num)
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

        if device_id >= 0 and "DmlExecutionProvider" in available_providers:
            return (["DmlExecutionProvider"], [{"device_id": device_id}])

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
