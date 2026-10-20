from pydantic import BaseModel

ERROR_CODE_LOCAL_VOICE_CHANGER_INTERFACE_ACTIVE = 100
ERROR_CODE_LOCAL_AUDIO_DEVICE_QUERY_FAILED = 200
ERROR_CODE_LOCAL_INPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED = 201
ERROR_CODE_LOCAL_OUTPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED = 202
ERROR_CODE_LOCAL_MONITOR_DEVICE_SAMPLE_RATE_CHECK_FAILED = 203
ERROR_CODE_LOCAL_INPUT_DEVICE_CANNOT_BE_NONE = 204
ERROR_CODE_LOCAL_OUTPUT_DEVICE_CANNOT_BE_NONE = 205
ERROR_CODE_MODULE_NOT_FOUND = 300
ERROR_CODE_SAMPLE_NOT_FOUND = 400
ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED = 500
ERROR_CODE_RVC_INVALID_CONFIG_LEGNTH = 501
ERROR_CODE_RVC_INVALID_F0_VALUE = 502
ERROR_CODE_RVC_INVALID_TORCH_MODEL_VERSION_VALUE = 503
ERROR_CODE_RVC_UNKNOWN_EMBEDDER = 504
ERROR_CODE_RVC_INVALID_TORCH_MODEL = 505
ERROR_CODE_RVC_INVALID_ONNX_MODEL = 506
ERROR_CODE_RVC_INVALID_ONNX_MODEL_VERSION_VALUE = 507
ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE = 508
ERROR_CODE_RVC_MERGE_FAILED_FIRST_MODEL_NOT_FOUND = 509
ERROR_CODE_RVC_MERGE_FAILED_MODEL_NOT_FOUND = 510
ERROR_CODE_RVC_MERGE_FAILED_ALL_MODELS_NOT_SAME = 511
ERROR_CODE_RVC_MERGE_FAILED_INVALID_PARAM = 512
ERROR_CODE_RVC_MERGE_FAILED_UNSUPPORTED_MODEL_TYPE = 513
ERROR_CODE_RVC_MERGE_FAILED_WEIGHT_KEY_IS_NOT_MATCH = 514
ERROR_CODE_RVC_EXPORT_FAILED_UNSUPPORTED_MODEL_TYPE = 515
ERROR_CODE_RVC_EXPORT_FAILED_UNSUPPORTED_EMBEDDER_TYPE = 516
ERROR_CODE_UPDATE_SLOT_INFO_FAILED = 517
ERROR_CODE_SLOT_INDEX_NOT_FOUND = 518
ERROR_CODE_NO_BLANK_SLOT = 519
ERROR_CODE_IMPORT_MODEL_FAILED = 520
ERROR_CODE_FILENAME_TOO_LONG = 523
ERROR_CODE_SLOT_STATE_CONFLICT = 524
ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED = 600
ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED = 601
ERROR_CODE_RECORDING_FAILED = 700
ERROR_CODE_MODEL_UPDATE_FAILED = 701
ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED = 702

ERROR_MESSAGES = {
    ERROR_CODE_LOCAL_VOICE_CHANGER_INTERFACE_ACTIVE: {
        "reason": "Local voice changer interface is active.",
        "action": "Please stop it before changing the mode.",
    },
    ERROR_CODE_LOCAL_AUDIO_DEVICE_QUERY_FAILED: {
        "reason": "Failed to query_devices.",
        "action": "Check device status of Operating System.",
    },
    ERROR_CODE_LOCAL_INPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED: {
        "reason": "Invalid audio input device configuration (maybe sample rate).",
        "action": "Please check audio device setting",
    },
    ERROR_CODE_LOCAL_OUTPUT_DEVICE_SAMPLE_RATE_CHECK_FAILED: {
        "reason": "Invalid audio output device configuration (maybe sample rate).",
        "action": "Please check audio device setting",
    },
    ERROR_CODE_LOCAL_MONITOR_DEVICE_SAMPLE_RATE_CHECK_FAILED: {
        "reason": "Invalid audio monitor device configuration (maybe sample rate).",
        "action": "Please check audio device setting",
    },
    ERROR_CODE_LOCAL_OUTPUT_DEVICE_CANNOT_BE_NONE: {
        "reason": "Please check audio device setting",
        "action": "Please check audio device setting",
    },
    ERROR_CODE_MODULE_NOT_FOUND: {
        "reason": "Module is not found in registerd modules.",
        "action": "Please check module status. Or initialize appliation maybe solve this problem.",
    },
    ERROR_CODE_SAMPLE_NOT_FOUND: {
        "reason": "Sample is not found in registerd samples.",
        "action": "Please check sample status. Or initialize appliation maybe solve this problem.",
    },
    ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED: {
        "reason": "Failed to estimate RVC model.",
        "action": "Please check model file extension. Model file must be a .pth or .onnx file",
    },
    ERROR_CODE_RVC_INVALID_CONFIG_LEGNTH: {
        "reason": "Invalid rvc model config length.",
        "action": "Please check the model file.",
    },
    ERROR_CODE_RVC_INVALID_F0_VALUE: {
        "reason": "Invalid rvc model f0 value.",
        "action": "Please check the model file.",
    },
    ERROR_CODE_RVC_INVALID_TORCH_MODEL_VERSION_VALUE: {
        "reason": "Invalid torch model version value.",
        "action": "Please check the model file.",
    },
    ERROR_CODE_RVC_UNKNOWN_EMBEDDER: {"reason": "Unknown embedder.", "action": "Please check the model file."},
    ERROR_CODE_RVC_INVALID_TORCH_MODEL: {"reason": "Invalid rvc model.", "action": "Please check the model file."},
    ERROR_CODE_RVC_INVALID_ONNX_MODEL: {"reason": "Invalid onnx model.", "action": "Please check the model file."},
    ERROR_CODE_RVC_INVALID_ONNX_MODEL_VERSION_VALUE: {
        "reason": "Invalid onnx model version value.",
        "action": "Please check the model file.",
    },
    ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE: {
        "reason": "Unknown voice changer type.",
        "action": "Please check the model file.",
    },
    ERROR_CODE_RVC_MERGE_FAILED_FIRST_MODEL_NOT_FOUND: {
        "reason": "Failed to merge models. First model is not found.",
        "action": "Please check the selected model files.",
    },
    ERROR_CODE_RVC_MERGE_FAILED_MODEL_NOT_FOUND: {
        "reason": "Failed to merge models. Model is not found.",
        "action": "Please check the selected model files.",
    },
    ERROR_CODE_RVC_MERGE_FAILED_ALL_MODELS_NOT_SAME: {
        "reason": "Failed to merge models. All models are not same type.",
        "action": "Please check the selected model files.",
    },
    ERROR_CODE_RVC_MERGE_FAILED_INVALID_PARAM: {
        "reason": "Failed to merge models. Invalid parameter.",
        "action": "Please check the selected model files.",
    },
    ERROR_CODE_RVC_MERGE_FAILED_UNSUPPORTED_MODEL_TYPE: {
        "reason": "Failed to merge models. Unsupported model type.",
        "action": "Please check the selected model files.",
    },
    ERROR_CODE_RVC_MERGE_FAILED_WEIGHT_KEY_IS_NOT_MATCH: {
        "reason": "Failed to merge models. Weight key is not match.",
        "action": "Please check the selected model files.",
    },
    ERROR_CODE_RVC_EXPORT_FAILED_UNSUPPORTED_MODEL_TYPE: {
        "reason": "Failed to export model. Unsupported model type.",
        "action": "Please check the selected model files.",
    },
    ERROR_CODE_UPDATE_SLOT_INFO_FAILED: {
        "reason": "Failed to update slot info.",
        "action": "Internal error. Please contact to support team.",
    },
    ERROR_CODE_SLOT_INDEX_NOT_FOUND: {
        "reason": "Slot index is not found in registerd slots.",
        "action": "Please check slot status. Or initialize appliation maybe solve this problem.",
    },
    ERROR_CODE_NO_BLANK_SLOT: {"reason": "No blank slot.", "action": "Please delete some slots."},
    ERROR_CODE_IMPORT_MODEL_FAILED: {"reason": "Failed to import model.", "action": "Please check logs."},
    ERROR_CODE_FILENAME_TOO_LONG: {
        "reason": "Failed to import model because filename is too long.",
        "action": "Please rename file.",
    },
    ERROR_CODE_SLOT_STATE_CONFLICT: {
        "reason": "Slot state does not allow this operation.",
        "action": "Refresh the slot list and retry with a slot in the expected state.",
    },
    ERROR_CODE_AUDIO_INPUT_DEVICE_NOT_SELECTED: {
        "reason": "Audio input device is not selected.",
        "action": "Please select audio input device.",
    },
    ERROR_CODE_AUDIO_OUTPUT_DEVICE_NOT_SELECTED: {
        "reason": "Audio output device is not selected.",
        "action": "Please select audio output device.",
    },
    ERROR_CODE_RECORDING_FAILED: {
        "reason": "Recording failed.",
        "action": "Please check audio device setting and start converting.",
    },
    ERROR_CODE_MODEL_UPDATE_FAILED: {
        "reason": "Model update failed.",
        "action": "Please check model file and start converting.",
    },
    ERROR_CODE_PIPELINE_IS_NOT_INITIALIZED: {
        "reason": "Pipeline is not initialized.",
        "action": "Check other log which cause this situation.",
    },
}

UNKNOWN_ERROR_MESSAGES = {
    "reason": "Local voice changer interface is active.",
    "action": "Please stop it before changing the mode.",
}


class VCClientErrorInfo(BaseModel):
    code: int
    reason: str
    action: str
    detail: str | None = None


class VCClientError(Exception):
    def __init__(self, code: int, detail: str | None = None):
        err_msg = ERROR_MESSAGES.get(code, UNKNOWN_ERROR_MESSAGES)
        self.info = VCClientErrorInfo(code=code, reason=err_msg["reason"], action=err_msg["action"], detail=detail)
        super().__init__(self.info.model_dump_json())
