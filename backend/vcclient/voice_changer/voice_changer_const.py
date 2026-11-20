import tempfile
from pathlib import Path
from typing import Literal, TypeAlias

SettingsDir = Path("./settings")
SettingsDir.mkdir(parents=True, exist_ok=True)
ConfigFile = SettingsDir / "vc_conf.json"

ModelDir = Path("model_dir")
ModelDir.mkdir(parents=True, exist_ok=True)

ModuleDir = Path("modules")

SLOT_PARAM_FILE = "params.json"
MAX_SLOT_INDEX = 199
GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE = -100

OpenVinoCacheDir = Path(tempfile.gettempdir()) / "vcclient" / "openvino_cache"
OpenVinoCacheDir.mkdir(parents=True, exist_ok=True)

CoreMLCacheDir = Path(tempfile.gettempdir()) / "vcclient" / "coreml_cache"
CoreMLCacheDir.mkdir(parents=True, exist_ok=True)

VoiceChangerInputMode: TypeAlias = Literal["server", "client"]
AudioDeviceType: TypeAlias = Literal["audioinput", "audiooutput"]

VoiceChangerType: TypeAlias = Literal["RVC", "RESERVED_FOR_SAMPLE", "BROKEN"]

InferencerType: TypeAlias = Literal[
    "onnxRVC",
    "onnxRVCNono",
]

RVCInferencerOnnxVersion: TypeAlias = Literal["v1", "v1.1", "v2", "v2.1", "v2.2", "v3.0"]

EmbedderType: TypeAlias = Literal[
    "hubert_base_l9fp",
    "hubert_base_l12",
    "contentvec",
    "hubert_base_japanese_l9fp",
    "hubert_base_japanese_l12",
    "whisper",
    "applio_japanese_hubert_base_l12",
    "applio_chinese_hubert_base_l12",
    "applio_korean_hubert_base_l12",
]

PitchEstimatorType: TypeAlias = Literal[
    "harvest",
    "dio",
    "rmvpe",
    "fcpe",
]

CROSSFADE_SEC: float = 0.05
SOLA_SEARCH_FRAME_SEC: float = 0.012
REALTIME_PROCESS_STATUS_SEND_INTERVAL_SEC: float = 1.0
REALTIME_OUTPUT_STATUS_SEND_INTERVAL_SEC: float = 0.2
