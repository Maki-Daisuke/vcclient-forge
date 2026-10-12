import os
import sys
from pathlib import Path

from pydantic import BaseModel

from vcclient_dev.utils.is_running_on_colab import is_running_on_colab


class VoiceChangerParams(BaseModel):
    vc_model_dir: str


def get_frontend_path():

    frontend_path = "web_front" if not is_running_on_colab() else os.path.join(sys._MEIPASS, "web_front")

    return Path(frontend_path)


TMP_DIR = "tmp_dir"

os.makedirs(TMP_DIR, exist_ok=True)

UPLOAD_DIR_STR = "upload_dir"

UPLOAD_DIR = Path(UPLOAD_DIR_STR)

UPLOAD_DIR.mkdir(exist_ok=True)

SSL_KEY_DIR = Path("ssl_key")
