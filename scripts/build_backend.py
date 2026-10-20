"""Freeze backend artifacts for portable distribution."""

import argparse
import json
import os
import platform
from pathlib import Path

import build_package as package_tools


def requires_nvidia_wheel_binaries(edition: str) -> bool:
    machine = platform.machine().lower()
    return edition == "cuda" and not (platform.system() == "Linux" and machine in ("aarch64", "arm64"))


def freeze_backend(edition: str, python_version: str = "3.14") -> Path:
    root = package_tools.PROJECT_ROOT
    build_dir = package_tools.get_build_dir(edition, python_version)
    manifest = build_dir / "backend-manifest.json"
    manifest.unlink(missing_ok=True)
    runtime_dir = build_dir / ".venv"
    runtime_python = runtime_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")

    if not runtime_dir.exists():
        print(">>> 1. Creating isolated build environment with uv...")
        package_tools.run_cmd(["uv", "venv", str(runtime_dir), "--python", python_version])
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
        f"{backend_dir / 'vcclient' / 'version.txt'}:vcclient",
        "--collect-submodules",
        "uvicorn",
        "--hidden-import",
        "engineio.async_drivers.asgi",
        "--hidden-import",
        "vcclient.server.vcserver_socketio",
    ]
    if requires_nvidia_wheel_binaries(edition):
        for package in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cufft", "nvidia.cuda_runtime"):
            freeze_command.extend(["--hidden-import", package, "--collect-binaries", package])
    freeze_command.append(str(backend_dir / "main.py"))
    package_tools.run_cmd(freeze_command, cwd=root, env=env)
    frozen = build_dir / "dist" / "main"
    executable = frozen / ("main.exe" if platform.system() == "Windows" else "main")
    if not executable.is_file() or executable.stat().st_size == 0 or not (frozen / "_internal").is_dir():
        raise FileNotFoundError(f"Incomplete PyInstaller output: {frozen}")
    files = {
        path.relative_to(frozen).as_posix(): path.stat().st_size for path in sorted(frozen.rglob("*")) if path.is_file()
    }
    if not any(name.startswith("_internal/") for name in files):
        raise FileNotFoundError(f"PyInstaller runtime files are missing: {frozen / '_internal'}")
    manifest.write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
    return frozen


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the frozen backend")
    parser.add_argument("--edition", choices=["cuda", "dml", "cpu", "mac"], default="cpu")
    parser.add_argument("--python-version", default="3.14")
    args = parser.parse_args()
    package_tools.run_cmd(
        ["uv", "sync", "--project", "backend", "--extra", args.edition], cwd=package_tools.PROJECT_ROOT
    )
    freeze_backend(args.edition, args.python_version)


if __name__ == "__main__":
    main()
