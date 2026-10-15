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
        # 1. PyTorch's bundled lib (if CUDA-enabled PyTorch is present)
        try:
            import torch

            torch_lib = Path(torch.__file__).parent / "lib"
            if torch_lib.exists():
                os.add_dll_directory(str(torch_lib))
                os.environ["PATH"] = str(torch_lib) + os.pathsep + os.environ.get("PATH", "")
        except Exception:
            pass

        # 2. nvidia-* pip packages (for pure-ONNX mode with CPU PyTorch)
        import importlib.util

        nvidia_pkgs = [
            "nvidia.cublas",
            "nvidia.cudnn",
            "nvidia.cuda_runtime",
            "nvidia.cufft",
        ]
        for pkg in nvidia_pkgs:
            try:
                spec = importlib.util.find_spec(pkg)
                if spec and spec.submodule_search_locations:
                    loc = Path(list(spec.submodule_search_locations)[0])
                    bin_dir = loc / "bin"
                    if bin_dir.exists():
                        os.add_dll_directory(str(bin_dir))
                        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass
    elif sys.platform == "linux":
        # Future Linux-specific environment hook (e.g., LD_LIBRARY_PATH checks)
        pass
    elif sys.platform == "darwin":
        # macOS uses CoreML Execution Provider natively
        pass
