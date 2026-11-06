"""Sync backend dependencies and switch editions for development."""

import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sync_backend(edition: str = "standard", python_version: str = "3.14") -> None:
    print(f"[BUILD:BACKEND] Syncing backend dependencies for edition '{edition}'...")
    res = subprocess.run(
        [
            "uv",
            "sync",
            "--project",
            "backend",
            "--extra",
            edition,
            "--python",
            python_version,
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"Failed to sync backend dependencies for edition '{edition}' (exit code: {res.returncode})"
        )
    print(f"[OK] Backend dependencies synced for edition '{edition}'")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync backend dependencies and switch editions"
    )
    parser.add_argument(
        "--edition",
        choices=["standard", "cuda"],
        default="standard",
        help="Target edition (standard, cuda, default: standard)",
    )
    parser.add_argument(
        "--python-version",
        default="3.14",
        help="Python version (default: 3.14)",
    )
    args = parser.parse_args()
    sync_backend(args.edition, args.python_version)


if __name__ == "__main__":
    main()
