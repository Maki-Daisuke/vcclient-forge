"""VCClient Portable Distribution Builder.

Builds a self-contained PyInstaller onedir distribution and optional 7z archive.
Uses `uv` to provision edition-specific build dependencies locked by `uv.lock`.
"""

import argparse
import os
import platform
import shutil
import subprocess
from pathlib import Path

VERSION = "2.0.78-beta"
MAX_ARCHIVE_BYTES = 2 * 1024**3
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "x64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = machine

    if system == "windows":
        return f"win_{arch}"
    elif system == "darwin":
        return f"mac_{arch}"
    elif system == "linux":
        return f"linux_{arch}"
    return f"{system}_{arch}"


def run_cmd(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print(f"[RUN] {' '.join(str(c) for c in cmd)}")
    res = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {res.returncode}: {' '.join(str(c) for c in cmd)}")


def find_7z_binary() -> str:
    for cmd in ("7z", "7za", "7zz"):
        p = shutil.which(cmd)
        if p:
            return p
    raise RuntimeError("7-Zip executable ('7z', '7za', or '7zz') was not found in PATH.")


def build_package(
    edition: str,
    python_version: str = "3.14",
    output_dir: Path | None = None,
    skip_archive: bool = False,
) -> Path:
    if output_dir is None:
        output_dir = PROJECT_ROOT / "dist"
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    plat_tag = get_platform_tag()
    package_name = f"vcclient_{plat_tag}_{edition}_v{VERSION}"
    package_dir = output_dir / package_name
    archive_path = output_dir / f"{package_name}.7z"

    if package_dir.exists() or archive_path.exists():
        raise FileExistsError(f"Package already exists; choose a new --output-dir: {package_dir}")
    seven_zip = None if skip_archive else find_7z_binary()
    build_dir = PROJECT_ROOT / "build" / "packaging" / f"{plat_tag}_{edition}_{python_version}"
    runtime_dir = build_dir / ".venv"
    runtime_python = runtime_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")

    print("\n==========================================")
    print(" Building VCClient Portable Package")
    print(f" Package:  {package_name}")
    print(f" Edition:  {edition}")
    print(f" Python:   {python_version}")
    print(f" Output:   {package_dir}")
    print("==========================================\n")

    if not runtime_dir.exists():
        print(">>> 1. Creating isolated build environment with uv...")
        run_cmd(["uv", "venv", str(runtime_dir), "--python", python_version])
    else:
        print(">>> 1. Reusing isolated build environment...")

    print(f">>> 2. Installing build dependencies for edition '{edition}'...")
    backend_dir = PROJECT_ROOT / "backend"
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(runtime_dir.resolve())
    run_cmd(
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

    print(">>> 3. Preparing frontend distribution...")
    run_cmd(["node", "scripts/build_frontend.js"], cwd=PROJECT_ROOT)

    print(">>> 4. Freezing backend with PyInstaller (onedir)...")
    freeze_command = [
        str(runtime_python),
        "-m",
        "PyInstaller",
        "--onedir",
        "--noupx",
        "--noconfirm",
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
    if edition == "cuda":
        for package in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cufft", "nvidia.cuda_runtime"):
            freeze_command.extend(["--hidden-import", package, "--collect-binaries", package])
    freeze_command.append(str(backend_dir / "main.py"))
    run_cmd(
        freeze_command,
        cwd=PROJECT_ROOT,
        env=env,
    )
    shutil.move(str(build_dir / "dist" / "main"), str(package_dir))

    print(">>> 5. Copying distribution assets...")
    copy_targets = [
        "frontend/dist",
        "start.bat",
        "start.sh",
        "README.md",
        "LICENSE",
    ]

    for item in copy_targets:
        src = PROJECT_ROOT / item
        if not src.exists():
            continue
        dst = package_dir / item
        if src.is_dir():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                src,
                dst,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    ".venv",
                    ".pytest_cache",
                    ".ruff_cache",
                ),
            )
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # Ensure empty modules and model_dir directories exist
    (package_dir / "modules").mkdir(exist_ok=True)
    (package_dir / "model_dir").mkdir(exist_ok=True)

    if skip_archive:
        print(f"\n[OK] Package directory created at: {package_dir}")
        return package_dir

    assert seven_zip is not None
    print(f">>> 6. Creating 7z archive via {seven_zip} (multi-threaded LZMA2)...")
    # -mx=5: balanced high compression ratio and speed
    # -md=32m: 32MB dictionary size (keeps RAM usage safe <= ~1.5GB across threads)
    # -mmt=4: limit to 4 threads to prevent OOM on high-core-count machines
    threads = min(os.cpu_count() or 4, 4)
    run_cmd(
        [
            seven_zip,
            "a",
            "-t7z",
            "-mx=5",
            "-md=32m",
            f"-mmt={threads}",
            archive_path.name,
            package_name,
        ],
        cwd=output_dir,
    )

    archive_bytes = archive_path.stat().st_size
    if archive_bytes >= MAX_ARCHIVE_BYTES:
        raise RuntimeError(f"Archive must be smaller than 2 GiB: {archive_path} ({archive_bytes} bytes)")
    size_mb = archive_bytes / (1024 * 1024)
    size_gib = archive_bytes / (1024 * 1024 * 1024)
    print("\n[OK] Build complete!")
    print(f"Archive: {archive_path}")
    print(f"Size:    {size_mb:.1f} MiB ({size_gib:.3f} GiB)\n")
    return archive_path


def main():
    parser = argparse.ArgumentParser(description="VCClient Portable Distribution Builder")
    parser.add_argument(
        "--edition",
        type=str,
        default="cpu",
        choices=["cuda", "dml", "cpu", "mac"],
        help="Target edition (cuda, dml, cpu, mac, default: cpu)",
    )
    parser.add_argument(
        "--python-version",
        type=str,
        default="3.14",
        help="Python version for the build environment (default: 3.14)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: dist/)",
    )
    parser.add_argument(
        "--skip-archive",
        action="store_true",
        help="Skip 7z archive creation (leave directory unpacked)",
    )
    args = parser.parse_args()

    build_package(
        edition=args.edition,
        python_version=args.python_version,
        output_dir=args.output_dir,
        skip_archive=args.skip_archive,
    )


if __name__ == "__main__":
    main()
