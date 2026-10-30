"""Freeze backend artifacts for portable distribution."""

import argparse
import json
import os
import platform
from pathlib import Path

import build_package as package_tools

NVIDIA_CUDA_PACKAGES = (
    "nvidia.cublas",
    "nvidia.cudnn",
    "nvidia.cufft",
    "nvidia.cuda_runtime",
    "nvidia.curand",
    "nvidia.cu13",
)
NVIDIA_BINARY_PATTERNS = ("*.dll", "*.dylib", "lib*.so", "lib*.so.*")


def requires_nvidia_wheel_binaries(edition: str) -> bool:
    return edition == "cuda"


def has_openvino_plugin(runtime_dir: Path) -> bool:
    for d in runtime_dir.rglob("site-packages/onnxruntime_ep_openvino"):
        if d.is_dir():
            return True
    return False


def collect_nvidia_binary_args(runtime_dir: Path) -> list[str]:
    found: list[tuple[str, str]] = []
    for nvidia_dir in sorted(runtime_dir.rglob("site-packages/nvidia")):
        if not nvidia_dir.is_dir():
            continue
        base = nvidia_dir.parent
        for pat in NVIDIA_BINARY_PATTERNS:
            for f in sorted(nvidia_dir.rglob(pat)):
                if f.is_file() or f.is_symlink():
                    dest = f.parent.relative_to(base).as_posix()
                    found.append((str(f), dest))
    args: list[str] = []
    for src, dest in dict.fromkeys(found):
        args.extend(["--add-binary", f"{src}:{dest}"])
    return args


def freeze_backend(edition: str, python_version: str = "3.14") -> Path:
    root = package_tools.PROJECT_ROOT
    build_dir = package_tools.get_build_dir(edition, python_version)
    manifest = build_dir / "backend-manifest.json"
    manifest.unlink(missing_ok=True)
    runtime_dir = build_dir / ".venv"
    runtime_python = runtime_dir / (
        "Scripts/python.exe" if platform.system() == "Windows" else "bin/python"
    )

    if not runtime_dir.exists():
        print(">>> 1. Creating isolated build environment with uv...")
        package_tools.run_cmd(
            ["uv", "venv", str(runtime_dir), "--python", python_version]
        )
    else:
        print(">>> 1. Reusing isolated build environment...")

    print(f">>> 2. Installing build dependencies for edition '{edition}'...")
    backend_dir = root / "backend"
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(runtime_dir.resolve())
    package_tools.run_cmd(
        [
            "uv",
            "sync",
            "--locked",
            "--active",
            "--extra",
            edition,
            "--no-dev",
            "--group",
            "build",
            "--no-install-project",
            "--python",
            python_version,
        ],
        cwd=backend_dir,
        env=env,
    )

    print(">>> 3. Freezing backend with PyInstaller (onedir)...")
    freeze_command = [
        str(runtime_python),
        "-m",
        "PyInstaller",
        "--onedir",
        "--noupx",
        "--noconfirm",
        "--optimize",
        "1",
        "--name",
        "main",
        "--distpath",
        str(build_dir / "dist"),
        "--workpath",
        str(build_dir / "work"),
        "--specpath",
        str(build_dir),
        "--paths",
        str(backend_dir),
        "--add-data",
        f"{root / 'package.json'}:vcclient",
        "--collect-submodules",
        "uvicorn",
        "--hidden-import",
        "engineio.async_drivers.asgi",
        "--hidden-import",
        "vcclient.server.vcserver_socketio",
    ]
    if requires_nvidia_wheel_binaries(edition):
        for package in (
            "nvidia.cublas",
            "nvidia.cudnn",
            "nvidia.cufft",
            "nvidia.cuda_runtime",
        ):
            freeze_command.extend(
                ["--hidden-import", package, "--collect-binaries", package]
            )
        freeze_command.extend(collect_nvidia_binary_args(runtime_dir))
    if has_openvino_plugin(runtime_dir):
        freeze_command.extend(["--collect-all", "onnxruntime_ep_openvino"])
    freeze_command.append(str(backend_dir / "main.py"))
    package_tools.run_cmd(freeze_command, cwd=root, env=env)
    frozen = build_dir / "dist" / "main"
    executable = frozen / ("main.exe" if platform.system() == "Windows" else "main")
    if (
        not executable.is_file()
        or executable.stat().st_size == 0
        or not (frozen / "_internal").is_dir()
    ):
        raise FileNotFoundError(f"Incomplete PyInstaller output: {frozen}")
    files = {
        path.relative_to(frozen).as_posix(): path.stat().st_size
        for path in sorted(frozen.rglob("*"))
        if path.is_file()
    }
    if not any(name.startswith("_internal/") for name in files):
        raise FileNotFoundError(
            f"PyInstaller runtime files are missing: {frozen / '_internal'}"
        )
    manifest.write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
    return frozen


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the frozen backend")
    parser.add_argument(
        "--edition",
        choices=["standard", "cuda"],
        default="standard",
    )
    parser.add_argument("--python-version", default="3.14")
    args = parser.parse_args()
    package_tools.run_cmd(
        ["uv", "sync", "--project", "backend", "--extra", args.edition],
        cwd=package_tools.PROJECT_ROOT,
    )
    freeze_backend(args.edition, args.python_version)


if __name__ == "__main__":
    main()
