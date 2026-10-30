"""Validate and package existing application artifacts without building them."""

import argparse
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

MAX_ARCHIVE_BYTES = 2 * 1024**3
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))[
    "version"
].removeprefix("v")


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
        return f"win-{arch}"
    elif system == "darwin":
        return f"mac-{arch}"
    elif system == "linux":
        return f"linux-{arch}"
    return f"{system}-{arch}"


def run_cmd(
    cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> None:
    print(f"[RUN] {' '.join(str(c) for c in cmd)}")
    res = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if res.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {res.returncode}: {' '.join(str(c) for c in cmd)}"
        )


def find_7z_binary() -> str:
    for cmd in ("7z", "7za", "7zz"):
        p = shutil.which(cmd)
        if p:
            return p
    raise RuntimeError(
        "7-Zip executable ('7z', '7za', or '7zz') was not found in PATH."
    )


def get_build_dir(edition: str, python_version: str) -> Path:
    return (
        PROJECT_ROOT
        / "build"
        / "packaging"
        / f"{get_platform_tag()}-{edition}_{python_version}"
    )


def validate_artifacts(edition: str, python_version: str) -> tuple[Path, Path]:
    build_dir = get_build_dir(edition, python_version)
    frozen = build_dir / "dist" / "main"
    manifest = build_dir / "backend-manifest.json"
    missing: list[str] = []
    executable = frozen / ("main.exe" if platform.system() == "Windows" else "main")
    if not executable.is_file() or executable.stat().st_size == 0:
        missing.append(str(executable))
    if not (frozen / "_internal").is_dir():
        missing.append(str(frozen / "_internal"))
    if not manifest.is_file():
        missing.append(str(manifest))
    else:
        files = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            not isinstance(files, dict)
            or not files
            or not all(isinstance(size, int) and size >= 0 for size in files.values())
            or not any(name.startswith("_internal/") for name in files)
        ):
            raise ValueError(
                f"Invalid backend build manifest: {manifest}; run npm run build -- --edition {edition}"
            )
        for name, size in files.items():
            artifact = frozen / name
            if not artifact.resolve().is_relative_to(frozen.resolve()):
                raise ValueError(f"Invalid backend artifact path: {name}")
            if not artifact.is_file() or artifact.stat().st_size != size:
                missing.append(str(artifact))

    frontend = PROJECT_ROOT / "frontend" / "dist"
    source = PROJECT_ROOT / "web_front"
    required_frontend = {Path("index.html")}
    required_frontend.update(
        path.relative_to(source) for path in source.rglob("*") if path.is_file()
    )
    missing.extend(
        str(frontend / relative)
        for relative in sorted(required_frontend)
        if not (frontend / relative).is_file()
    )
    desktop_name = (
        "vcclient-forge.exe" if platform.system() == "Windows" else "vcclient-forge"
    )
    desktop = PROJECT_ROOT / "desktop" / "bin" / desktop_name
    if not desktop.is_file() or desktop.stat().st_size == 0:
        missing.append(str(desktop))
    for name in ("start.bat", "start.sh", "README.md", "LICENSE"):
        if not (PROJECT_ROOT / name).is_file():
            missing.append(str(PROJECT_ROOT / name))
    if missing:
        raise FileNotFoundError(
            "Missing or incomplete package artifacts:\n"
            + "\n".join(missing)
            + f"\nRun npm run build -- --edition {edition} before npm run package."
        )
    return frozen, desktop


def build_package(
    edition: str,
    python_version: str = "3.14",
    output_dir: Path | None = None,
    skip_archive: bool = False,
) -> Path:
    output_dir = (output_dir or PROJECT_ROOT / "dist").resolve()
    package_name = f"vcclient-{get_platform_tag()}-{edition}-v{VERSION}"
    package_dir = output_dir / package_name
    archive_path = output_dir / f"{package_name}.7z"
    if package_dir.exists() or archive_path.exists():
        raise FileExistsError(
            f"Package already exists; choose a new --output-dir: {package_dir}"
        )
    frozen, desktop_executable = validate_artifacts(edition, python_version)
    seven_zip = None if skip_archive else find_7z_binary()
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(frozen, package_dir, symlinks=True)

    print(">>> Copying validated distribution assets...")
    copy_targets = [
        "frontend/dist",
        "start.bat",
        "start.sh",
        "README.md",
        "LICENSE",
    ]

    for item in copy_targets:
        src = PROJECT_ROOT / item
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

    shutil.copy2(desktop_executable, package_dir / desktop_executable.name)

    if skip_archive:
        print(f"\n[OK] Package directory created at: {package_dir}")
        return package_dir

    assert seven_zip is not None
    print(f">>> Creating 7z archive via {seven_zip} (multi-threaded LZMA2)...")
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
            "-snl",
            f"-mmt={threads}",
            archive_path.name,
            package_name,
        ],
        cwd=output_dir,
    )

    archive_bytes = archive_path.stat().st_size
    if archive_bytes >= MAX_ARCHIVE_BYTES:
        raise RuntimeError(
            f"Archive must be smaller than 2 GiB: {archive_path} ({archive_bytes} bytes)"
        )
    size_mb = archive_bytes / (1024 * 1024)
    size_gib = archive_bytes / (1024 * 1024 * 1024)
    print("\n[OK] Build complete!")
    print(f"Archive: {archive_path}")
    print(f"Size:    {size_mb:.1f} MiB ({size_gib:.3f} GiB)\n")
    return archive_path


def main():
    parser = argparse.ArgumentParser(
        description="Validate and package an existing build"
    )
    parser.add_argument(
        "--edition",
        type=str,
        default="standard",
        choices=["standard", "cuda"],
        help="Target edition (standard, cuda, default: standard)",
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
