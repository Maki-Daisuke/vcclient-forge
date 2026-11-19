import sys
from pathlib import Path


def get_frontend_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "frontend" / "dist"

    # server_const.py -> server -> vcclient -> backend -> PROJECT_ROOT
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    frontend_dist = project_root / "frontend" / "dist"
    if frontend_dist.exists():
        return frontend_dist

    # Fallbacks for alternative execution contexts
    cwd_dist = Path("frontend/dist")
    if cwd_dist.exists():
        return cwd_dist

    return frontend_dist
