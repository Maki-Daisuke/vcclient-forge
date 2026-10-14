import os
import sys
from pathlib import Path

_initialized = False


def setup_cuda_env() -> None:
    """Setup platform-specific CUDA / GPU runtime environment transparently.

    - Windows: Python 3.8+ restricts DLL search paths. We explicitly register
      PyTorch's bundled CUDA 12 and cuDNN 9 libraries via os.add_dll_directory
      so ONNX Runtime GPU can load cublas, cudart, and cudnn without requiring
      a system-wide CUDA Toolkit installation.
    - Linux / macOS: Hook for any future shared library paths or device configs.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    if sys.platform == "win32":
        try:
            import torch

            torch_lib = Path(torch.__file__).parent / "lib"
            if torch_lib.exists():
                os.add_dll_directory(str(torch_lib))
                os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass
    elif sys.platform == "linux":
        # Future Linux-specific environment hook (e.g., LD_LIBRARY_PATH checks)
        pass
    elif sys.platform == "darwin":
        # macOS uses CoreML Execution Provider natively
        pass
