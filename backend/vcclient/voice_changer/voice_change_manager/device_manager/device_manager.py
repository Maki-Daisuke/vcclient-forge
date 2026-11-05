import json
from pathlib import Path
from typing import Any

import onnxruntime

from vcclient.logger import logger
from vcclient.utils.runtime_env import setup_runtime_env
from vcclient.voice_changer.gpu_device_manager.gpu_device_manager import GPUDeviceManager
from vcclient.voice_changer.voice_changer_const import (
    OPENVINO_AUTO_DEVICE_ID,
    OPENVINO_GPU_DEVICE_ID,
    CoreMLCacheDir,
    OpenVinoCacheDir,
)


class DeviceManager:
    _instance = None

    @classmethod
    def get_instance(cls) -> "DeviceManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        setup_runtime_env()
        logger.info("DeviceManager initialized in pure-ONNX mode.")

    @classmethod
    def is_openvino_available(cls) -> bool:
        setup_runtime_env()
        available = onnxruntime.get_available_providers()
        if "OpenVINOExecutionProvider" in available:
            return True
        if hasattr(onnxruntime, "get_ep_devices"):
            try:
                for d in onnxruntime.get_ep_devices():
                    if getattr(d, "ep_name", "") == "OpenVINOExecutionProvider":
                        return True
            except Exception:
                pass
        return False

    @classmethod
    def _find_openvino_ep_device(cls, preferred_type: str = "GPU") -> Any | None:
        """Find the most suitable OpenVINO EP device from ort.get_ep_devices().

        Prioritizes GPU devices to ensure RVC models and dynamic audio graphs execute
        on hardware without NPU compiler scheduling limitations or silent CPU fallback.
        """
        if not hasattr(onnxruntime, "get_ep_devices"):
            return None
        try:
            ep_devices = onnxruntime.get_ep_devices()
            gpu_dev = None
            cpu_dev = None
            fallback_dev = None
            for d in ep_devices:
                if getattr(d, "ep_name", "") != "OpenVINOExecutionProvider":
                    continue
                dev_type = str(getattr(getattr(d, "device", None), "type", "")).upper()
                ov_dev = ""
                if hasattr(d, "ep_metadata") and isinstance(d.ep_metadata, dict):
                    ov_dev = str(d.ep_metadata.get("ov_device", "")).upper()
                elif hasattr(getattr(d, "device", None), "metadata") and isinstance(d.device.metadata, dict):
                    ov_dev = str(d.device.metadata.get("ov_device", "")).upper()

                if "GPU" in dev_type or "GPU" in ov_dev:
                    gpu_dev = d
                    break
                if "CPU" in dev_type or "CPU" in ov_dev:
                    cpu_dev = d
                elif fallback_dev is None:
                    fallback_dev = d

            if preferred_type == "GPU" and gpu_dev is not None:
                return gpu_dev
            return gpu_dev or fallback_dev or cpu_dev
        except Exception as e:
            logger.debug("Failed to inspect OpenVINO ep_devices: %s", e)
            return None

    def get_onnx_execution_provider(self, device_id: int) -> tuple[list[str], list[dict]]:
        res = self._get_onnx_execution_provider(device_id)
        logger.info("get_onnx_execution_provider: %s", res)
        return res

    def configure_session_options(
        self, so: onnxruntime.SessionOptions, providers: list[str]
    ) -> onnxruntime.SessionOptions:
        if any("openvino" in p.lower() for p in providers):
            so.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
            if hasattr(onnxruntime, "get_ep_devices") and hasattr(so, "add_provider_for_devices"):
                try:
                    target_dev = self._find_openvino_ep_device(preferred_type="GPU")
                    if target_dev is not None:
                        gpu_cfg: dict[str, Any] = {
                            "EXECUTION_MODE_HINT": "ACCURACY",
                        }
                        try:
                            OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)
                            cache_dir_str = str(OpenVinoCacheDir.resolve())
                            gpu_cfg["CACHE_DIR"] = cache_dir_str
                        except Exception as e:
                            logger.debug("Failed to set OpenVINO cache_dir: %s", e)

                        opts: dict[str, str] = {
                            "load_config": json.dumps({"GPU": gpu_cfg}),
                        }
                        if "CACHE_DIR" in gpu_cfg:
                            opts["cache_dir"] = gpu_cfg["CACHE_DIR"]

                        so.add_provider_for_devices([target_dev], opts)
                        dev_type = getattr(getattr(target_dev, "device", None), "type", "Unknown")
                        logger.info("Bound OpenVINO EP device: %s (type=%s)", target_dev, dev_type)
                except Exception as e:
                    logger.debug("Failed to bind OpenVINO ep_device: %s", e)
        return so

    def create_inference_session(
        self,
        model_payload: str | bytes | Path,
        providers: list[str],
        provider_options: list[dict] | None = None,
        so: onnxruntime.SessionOptions | None = None,
    ) -> onnxruntime.InferenceSession:
        if so is None:
            so = onnxruntime.SessionOptions()
            so.log_severity_level = 3
        self.configure_session_options(so, providers)

        path_or_bytes = str(model_payload) if isinstance(model_payload, Path) else model_payload

        # When SessionOptions has already been configured with providers (e.g. via add_provider_for_devices),
        # passing providers or provider_options to InferenceSession causes ONNX Runtime to override
        # and discard the SessionOptions configuration, leading to silent CPU fallback for dynamic plugins like OpenVINO.
        if hasattr(so, "has_providers") and so.has_providers():
            session = onnxruntime.InferenceSession(path_or_bytes, sess_options=so)
        else:
            session = onnxruntime.InferenceSession(
                path_or_bytes,
                sess_options=so,
                providers=providers,
                provider_options=provider_options,
            )

        name = (
            model_payload.name
            if isinstance(model_payload, Path)
            else (model_payload if isinstance(model_payload, str) else "<bytes>")
        )
        logger.info("ONNX session initialized for %s with active providers: %s", name, session.get_providers())
        return session

    def _get_onnx_execution_provider(self, device_id: int) -> tuple[list[str], list[dict]]:
        available_providers = onnxruntime.get_available_providers()
        logger.info("available_providers: %s", available_providers)

        if device_id in (OPENVINO_GPU_DEVICE_ID, OPENVINO_AUTO_DEVICE_ID):
            if self.is_openvino_available():
                options: dict[str, str] = {
                    "device_type": "GPU",
                    "load_config": json.dumps({"GPU": {"EXECUTION_MODE_HINT": "ACCURACY"}}),
                }
                try:
                    OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)
                    options["cache_dir"] = str(OpenVinoCacheDir.resolve())
                except Exception as e:
                    logger.debug("Failed to set OpenVINO cache_dir: %s", e)
                return (["OpenVINOExecutionProvider", "CPUExecutionProvider"], [options, {}])

            logger.info("OpenVINO requested but unavailable, fallback to cpu.")
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

        if device_id >= 0 and "CoreMLExecutionProvider" in available_providers:
            coreml_options: dict[str, Any] = {
                "ModelFormat": "MLProgram",
                "MLComputeUnits": "ALL",
                "RequireStaticInputShapes": "0",
                "EnableOnSubgraphs": "0",
            }
            try:
                CoreMLCacheDir.mkdir(parents=True, exist_ok=True)
                coreml_options["ModelCacheDirectory"] = str(CoreMLCacheDir.resolve())
            except Exception as e:
                logger.debug("Failed to set CoreML cache dir: %s", e)
            return (["CoreMLExecutionProvider", "CPUExecutionProvider"], [coreml_options, {}])

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
