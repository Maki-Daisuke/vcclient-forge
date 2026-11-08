from __future__ import annotations

from .providers.coreml import setup_coreml_runtime
from .providers.cuda import setup_cuda_runtime
from .providers.directml import setup_directml_runtime
from .providers.openvino import setup_openvino_runtime

_initialized = False


def setup_runtime_env() -> None:
    """Setup platform-specific CUDA / DirectML / OpenVINO / CoreML runtime environment transparently.

    Delegates hardware-specific initialization to dedicated provider modules:
    - providers.cuda: setup_cuda_runtime()
    - providers.directml: setup_directml_runtime()
    - providers.openvino: setup_openvino_runtime()
    - providers.coreml: setup_coreml_runtime()
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    setup_cuda_runtime()
    setup_directml_runtime()
    setup_openvino_runtime()
    setup_coreml_runtime()
