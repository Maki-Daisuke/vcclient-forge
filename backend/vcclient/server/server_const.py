import os
import sys
from pathlib import Path

from pydantic import BaseModel

from vcclient.utils.is_running_on_colab import is_running_on_colab


class VoiceChangerParams(BaseModel):
    vc_model_dir: str


def get_frontend_path() -> Path:
    if is_running_on_colab():
        colab_path = Path(sys._MEIPASS) / "frontend" / "dist"
        if colab_path.exists():
            return colab_path
        return Path(sys._MEIPASS) / "web_front"

    # server_const.py -> server -> vcclient -> backend -> PROJECT_ROOT
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    frontend_dist = project_root / "frontend" / "dist"
    if frontend_dist.exists():
        return frontend_dist

    # Fallbacks for alternative execution contexts
    cwd_dist = Path("frontend/dist")
    if cwd_dist.exists():
        return cwd_dist

    cwd_web_front = Path("web_front")
    if cwd_web_front.exists():
        return cwd_web_front

    return frontend_dist


TMP_DIR = "tmp_dir"

os.makedirs(TMP_DIR, exist_ok=True)

UPLOAD_DIR_STR = "upload_dir"

UPLOAD_DIR = Path(UPLOAD_DIR_STR)

UPLOAD_DIR.mkdir(exist_ok=True)

SSL_KEY_DIR = Path("ssl_key")
