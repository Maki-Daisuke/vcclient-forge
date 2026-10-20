import sys
from pathlib import Path

TERMINATE_FLAG = False
HERE = Path(__file__).parent.absolute()


def get_version() -> str:
    with open(HERE / "version.txt", "r", encoding="utf-8") as f:
        return f.read().strip()


APP_NAME = "VCClient CUI"
VERSION = get_version()
LOGGER_NAME = "vcclient"
LOGGER_NAME_LOCAL_AUDIO_DEVICE = "local_audio_device"
LOG_FILE = Path("vcclient.log")
LOG_FILE_LOCAL_AUDIO_DEVICE = Path("vcclient_local_audio_device.log")
SERVER_IO_RECORDING_FILE_IN = "input.wav"
SERVER_IO_RECORDING_FILE_OUT = "output.wav"
TOAST_TIMEOUT = 0.7
MAX_SLOT_FOR_CUI = 10

NATIVE_CLIENT_FILE_WIN = (
    Path(sys._MEIPASS, "native_client", "voice-changer-native-client.exe")
    if hasattr(sys, "_MEIPASS")
    else Path("native_client", "voice-changer-native-client.exe")
)
NATIVE_CLIENT_FILE_MAC = Path("voice-changer-native-client.app", "Contents", "MacOS", "voice-changer-native-client")
