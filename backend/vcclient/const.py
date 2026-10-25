import json
import sys
from pathlib import Path

TERMINATE_FLAG = False
HERE = Path(__file__).parent.absolute()


def get_version() -> str:
    candidates = [
        HERE / "package.json",
        HERE.parent.parent / "package.json",
        Path(sys.executable).parent / "package.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if "version" in data and isinstance(data["version"], str):
                    return data["version"].strip()
            except Exception:
                pass
    return "unknown"


VERSION = get_version()
LOGGER_NAME = "vcclient"
LOG_FILE = Path("vcclient.log")
SERVER_IO_RECORDING_FILE_IN = "input.wav"
SERVER_IO_RECORDING_FILE_OUT = "output.wav"
SERVER_IO_RECORDING_FILE_MONITOR = "monitor.wav"
TOAST_TIMEOUT = 0.7
