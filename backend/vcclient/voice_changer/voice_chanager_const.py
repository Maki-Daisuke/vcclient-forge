from pathlib import Path
from typing import Literal, TypeAlias, get_args

SettingsDir = Path("./settings")
SettingsDir.mkdir(parents=True, exist_ok=True)
ConfigFile = SettingsDir / "vc_conf.json"

ModelDir = Path("model_dir")
ModelDir.mkdir(parents=True, exist_ok=True)

StaticModelDir = Path("static_model_dir")
StaticModelDir.mkdir(parents=True, exist_ok=True)

ModuleDir = Path("modules")

SLOT_PARAM_FILE = "params.json"
GET_GPU_DEVICE_ID_IS_NOT_AVAILABLE = -100

AudioSampleRates = [8000, 16000, 24000, 32000, 44100, 48000, 96000]

VoiceChangerInputMode: TypeAlias = Literal["server", "client"]
AudioDeviceType: TypeAlias = Literal["audioinput", "audiooutput"]
AudioDevicePurpose: TypeAlias = Literal["audioinput", "audiooutput", "monitoroutput"]

VoiceChangerType: TypeAlias = Literal["RVC", "RESERVED_FOR_SAMPLE", "BROKEN"]
VoiceChangerTypes: list[VoiceChangerType] = ["RVC"]

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

PitchEstimatorTypes: list[PitchEstimatorType] = list(get_args(PitchEstimatorType))

ChunkSecs: list[float] = [
    0.05,
    0.08,
    0.1,
    0.12,
    0.15,
    0.2,
    0.25,
    0.3,
    0.35,
    0.4,
    0.45,
    0.5,
    0.6,
    0.7,
    0.8,
    0.9,
    1,
    1.1,
    1.2,
    1.3,
    1.4,
    1.5,
    2,
    3,
    4,
    5,
]

ExtraSec: list[float] = [0.08, 0.16, 0.34, 0.68, 1.36, 2.73, 3, 4, 5, 6, 7, 8, 9, 10]
