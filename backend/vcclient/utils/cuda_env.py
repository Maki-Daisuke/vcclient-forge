import os
import sys
from pathlib import Path

_initialized = False


def setup_cuda_env() -> None:
    """Setup platform-specific CUDA / GPU / OpenVINO runtime environment transparently.

    - Windows: Python 3.8+ restricts DLL search paths. We explicitly register
      PyTorch's or nvidia-* wheels' bundled CUDA and cuDNN libraries via
      os.add_dll_directory and onnxruntime.preload_dlls so ONNX Runtime GPU can
      load cublas, cudart, and cudnn without requiring a system-wide CUDA Toolkit.
      Also registers onnxruntime-ep-openvino plugin DLLs if installed.
    - Linux: Preload bundled nvidia-* wheel shared libraries (CUDA 12 / CUDA 13
      and cuDNN 9) via onnxruntime.preload_dlls so both source execution and
      PyInstaller portable builds work without system-wide CUDA / cuDNN packages.
      Also sets LD_LIBRARY_PATH and registers onnxruntime-ep-openvino plugin if present.
    - macOS: Uses CoreML Execution Provider natively.
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
            "nvidia.curand",
            "nvidia.cu13",
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
                        for arch_dir in bin_dir.iterdir():
                            if arch_dir.is_dir():
                                os.add_dll_directory(str(arch_dir))
                                os.environ["PATH"] = str(arch_dir) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass

        try:
            import onnxruntime

            if hasattr(onnxruntime, "preload_dlls") and getattr(onnxruntime, "cuda_version", None):
                onnxruntime.preload_dlls(directory="")
        except Exception:
            pass
    elif sys.platform == "linux":
        import importlib.util

        nvidia_pkgs = [
            "nvidia.cublas",
            "nvidia.cudnn",
            "nvidia.cuda_runtime",
            "nvidia.cufft",
            "nvidia.curand",
            "nvidia.cu13",
        ]
        lib_dirs: list[str] = []
        for pkg in nvidia_pkgs:
            try:
                spec = importlib.util.find_spec(pkg)
                if spec and spec.submodule_search_locations:
                    for search_loc in spec.submodule_search_locations:
                        lib_dir = Path(search_loc) / "lib"
                        if lib_dir.is_dir():
                            lib_dirs.append(str(lib_dir))
            except Exception:
                pass
        if lib_dirs:
            existing = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(lib_dirs + ([existing] if existing else []))

        try:
            import onnxruntime

            if hasattr(onnxruntime, "preload_dlls") and getattr(onnxruntime, "cuda_version", None):
                onnxruntime.preload_dlls(directory="")
        except Exception:
            pass
    # 3. OpenVINO Execution Provider Plugin registration (Windows & Linux)
    try:
        import onnxruntime_ep_openvino as openvino_ep

        pkg_dir = Path(openvino_ep.__file__).parent
        if sys.platform == "win32":
            os.add_dll_directory(str(pkg_dir))
            os.environ["PATH"] = str(pkg_dir) + os.pathsep + os.environ.get("PATH", "")
        elif sys.platform == "linux":
            existing = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join([str(pkg_dir)] + ([existing] if existing else []))

        import onnxruntime

        if hasattr(onnxruntime, "register_execution_provider_library"):
            lib_path = openvino_ep.get_library_path()
            ep_name = openvino_ep.get_ep_name()
            onnxruntime.register_execution_provider_library(ep_name, lib_path)
    except Exception:
        pass
