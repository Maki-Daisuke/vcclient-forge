---
title: "VCClient Forge HTTP & WebSocket API Reference"
version: "0.1.0"
okf_version: "0.2"
description: "Current HTTP REST, multipart, WebSocket, and static file API specification implemented by the VCClient Forge Python backend."
---

# VCClient Forge HTTP & WebSocket API Reference

> **Implementation Status Notice (Current Implemented API)**:
> This document specifies the HTTP REST, multipart, WebSocket, and static asset endpoints **currently implemented** by the Python backend (`backend/vcclient/server/`). For the **planned** decoupled session and side-effect-free storage architecture (not yet implemented), see [Snapshot-Driven Conversion Engine & Decoupled Storage/Device APIs](./snapshot-driven-pipeline-and-stateless-control-api.md).

---

## 1. Server Overview & Conventions

- **Default Host & Port**: Launching via [`backend/main.py`](../backend/main.py) binds `0.0.0.0:18888` by default (`--host`, `--port`). Direct instantiation of `VCServer()` ([`vcserver.py`](../backend/vcclient/server/vcserver.py)) defaults to `127.0.0.1` and selects an unused ephemeral port via `portpicker`.
- **Caching**: `NoCacheMiddleware` ([`vcserver_rest_api.py`](../backend/vcclient/server/vcserver_rest_api.py)) sets `Cache-Control: no-store` on all HTTP responses.
- **Interactive Client Model**: Backend state and file transactions assume a single interactive client; concurrent multi-tab mutations are not supported.
- **Schema UI**: Swagger UI is served at `GET /docs` against `GET /openapi.json` (`redoc_url=None`).

---

## 2. Error Handling & Response Envelopes

### 2.1 FastAPI Exception Wrapper (`register_api_exception_handlers`)

All `StarletteHTTPException` / `HTTPException` errors raised under `/api/*` pass through `register_api_exception_handlers()` in [`vcserver_rest_api.py`](../backend/vcclient/server/vcserver_rest_api.py):

- If `exc.detail` parses as JSON (for example serialized `VCClientErrorInfo`), the response preserves it verbatim: `{"detail": "<json-string>"}`.
- Otherwise `detail` is wrapped into a JSON-encoded string:

```json
{
  "detail": "{\"code\": \"ERR_HTTP_EXCEPTION\", \"message\": \"Model does not exist\"}"
}
```

- `"NOT_SUPPORTED"` is used for `code` **only** when `status_code == 404` and `str(exc.detail) == "Not Found"` (unmatched `/api/*` routes). Other HTTP errors (including `404` `"Model does not exist"` from `DELETE /api/slot-manager/slots/{index}` and `405` `"Method Not Allowed"`) use `"ERR_HTTP_EXCEPTION"`.
- Unknown `/api/*` fallback (`unknown_api`): HTTP requests receive `404` with `NOT_SUPPORTED`; WebSocket handshakes close immediately with code `1008`.

### 2.2 Route Validation Wrapper (`ValidationErrorLoggingRoute`)

[`ValidationErrorLoggingRoute`](../backend/vcclient/server/validation_error_logging_route.py) is attached to all REST routers **except** `RestAPILocalVoiceChangerInterface`:

| Condition | HTTP Status | `detail` Payload |
| --- | --- | --- |
| FastAPI `RequestValidationError` | `422` | JSON string with code `ERR_HTTP_EXCEPTION`; its `message` is the string representation of `{"errors": [...], "body": "<preview>"}` |
| `VCClientError` | `422` | JSON string of `VCClientErrorInfo`: `{"code": int, "reason": str, "action": str, "detail": str \| null}` |
| Unhandled `Exception` | `422` | JSON string with code `ERR_HTTP_EXCEPTION`; its `message` is the string representation of `{"errors": str(exc), "body": "<preview>"}` |

For these error previews, `body` is `""` for `multipart/*` or stream errors;
otherwise it contains up to 4096 bytes decoded as UTF-8 with `errors="replace"`.
The common exception handler converts the route wrapper's detail dictionaries
to strings; the `message` itself is not a JSON object.

> **Router Exception**: [`vcserver_rest_api_local_voice_changer_interface.py`](../backend/vcclient/server/vcserver_rest_api_local_voice_changer_interface.py) does not use `ValidationErrorLoggingRoute`; `RuntimeError` or `VCClientError` raised in `post_start` propagates as HTTP `500`.

### 2.3 Common `VCClientError` Numeric Codes ([`exception.py`](../backend/vcclient/exception.py))

| Code | Meaning |
| --- | --- |
| `100` | Native local voice changer interface is active; cannot change `voice_changer_input_mode`. |
| `200`–`205` | Audio device query failure, invalid sample rate, or missing device selection on active update. |
| `300` | Required model module not found. |
| `500`–`508` | RVC model metadata estimation/validation error or unknown voice changer type. |
| `518` | Slot index out of range or no blank slot available (`MAX_SLOT_INDEX = 199`). |
| `520` | Model import failed. |
| `523` | Model filename exceeds 80 characters. |
| `524` | Slot state conflict (updating/editing an empty or non-RVC slot, or importing into an occupied slot). |
| `600`, `601` | Audio input or output device is not selected (`-1`). |
| `700`–`702` | Recording failed (`700`), model update failed (`701`), pipeline not initialized (`702`). |

---

## 3. Endpoint Summary

| Group | Method / Protocol | Path | Request Type | Response |
| --- | --- | --- | --- | --- |
| Slots | `GET` | `/api/slot-manager/slots` | Query (`reload`) | `SlotInfoMember[]` |
| Slots | `GET` | `/api/slot-manager/slots/{index}` | Query (`reload`) | `SlotInfoMember` |
| Slots | `POST` | `/api/slot-manager/slots` | `multipart/form-data` | `SlotInfoMember` |
| Slots | `PATCH` | `/api/slot-manager/slots/{index}` | `multipart/form-data` | `SlotInfoMember` |
| Slots | `PUT` | `/api/slot-manager/slots/{index}` | `application/json` | `null` |
| Slots | `DELETE` | `/api/slot-manager/slots/{index}` | — | `{"current_slot_index": int}` |
| Slots | `POST` | `/api/slot-manager/operation/organize` | `application/json` | `{"current_slot_index": int}` |
| Configuration | `GET` | `/api/configuration-manager/configuration` | Query (`reload`) | `VoiceChangerConfiguration` |
| Configuration | `PUT` | `/api/configuration-manager/configuration` | `application/json` | `null` |
| Voice Changer | `GET` | `/api/voice-changer-manager/information` | — | `VoiceChangerManagerInfo` |
| Local Audio | `GET` | `/api/local-voice-changer-interface/information` | — | `LocalVoiceChangerInterfaceInfo` |
| Local Audio | `POST` | `/api/local-voice-changer-interface/operation/start` | — | `null` |
| Local Audio | `POST` | `/api/local-voice-changer-interface/operation/stop` | — | `null` |
| Devices | `GET` | `/api/audio-device-manager/input_devices` | Query (`reload`) | `AudioDevice[]` |
| Devices | `GET` | `/api/audio-device-manager/output_devices` | Query (`reload`) | `AudioDevice[]` |
| Devices | `GET` | `/api/gpu-device-manager/devices` | Query (`reload`) | `DeviceConfig[]` |
| WebSocket | `WS` | `/api/ws/status` | Server -> Client text JSON | Realtime telemetry events |
| WebSocket | `WS` | `/api/ws/audio` | Bidirectional binary `<f4` PCM | Converted audio frames |
| Non-API / UI | `GET` | `/output.wav`, `/vcclient.log`, `/model_dir/{path}`, `/docs`, `/openapi.json`, `/` | — | Recordings, logs, slot assets, docs, SPA |

---

## 4. Slot Management (`/api/slot-manager/*`)

Implemented in [`vcserver_rest_api_slot_manager.py`](../backend/vcclient/server/vcserver_rest_api_slot_manager.py) and [`slot_manager.py`](../backend/vcclient/voice_changer/slot_manager/slot_manager.py).

- **Valid Slot Range**: `0 <= index < 199` (`MAX_SLOT_INDEX = 199`). Out-of-range path or form `slot_index` values return HTTP `400`.

### 4.1 `GET /api/slot-manager/slots`

- **Query**: `reload: bool = False`. When `true`, rescans `model_dir/`.
- **Response (`200`)**: Array of `SlotInfoMember` covering `0..min(max_existing_index + 1, 198)` (minimum length `1`, returning blank slot `0` when no slots exist). Empty directories/missing `params.json` yield `voice_changer_type: null`; unparseable `params.json` yields `voice_changer_type: "BROKEN"`.

### 4.2 `GET /api/slot-manager/slots/{index}`

- **Query**: `reload: bool = False`.
- **Responses**: `200` (`SlotInfoMember`), `400` (`index` out of range).

### 4.3 `POST /api/slot-manager/slots`

Imports a new RVC model into a vacant slot in a single request (`multipart/form-data`).

| Field | Kind | Required | Constraints / Default |
| --- | --- | --- | --- |
| `model_file` | File | Yes | `.pth` or `.onnx`, non-empty |
| `name` | Form string | Yes | Non-empty after `.strip()` |
| `voice_changer_type` | Form string | No | Default `"RVC"`; only `"RVC"` is accepted |
| `index_file` | File | No | `.index`, non-empty |
| `icon_file` | File | No | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.avif`, `.bmp`; non-empty; `Content-Type` (if set) must start with `image/` or equal `application/octet-stream` |
| `slot_index` | Form int | No | `0 <= slot_index < 199`; assigns lowest blank slot when omitted |
| `embedder` | Form string | No | `EmbedderType`; overrides auto-detected embedder when supplied |

- **Execution & Cleanup**:
  1. Validates `voice_changer_type`, `name`, and optional `slot_index`.
  2. Acquires `LocalVoiceChangerInterface.lifecycle_lock` briefly and rejects with `409` if native audio (`local_voice_changer_enabled` or `stream_running`) or WebSocket/bulk conversion (`VoiceChanger.peek_instance().is_convert_chunk_bulk_started()`) is active.
  3. Saves uploads into a per-request `tempfile.TemporaryDirectory()` using generated `<prefix>_<12hex><suffix>` names (`model_`, `index_`, `icon_`).
  4. Runs `SlotManager.set_new_slot(..., remove_src=True)`: copies files into `model_dir/<slot>/`, exports `.pth` to `.onnx` via offline CPU PyTorch if needed, runs RVC metadata estimation, persists `params.json`, reloads `SlotManager`, and removes temporary files automatically on completion or error.
- **Responses**: `200` (created `SlotInfoMember`), `400` (invalid parameters/file type/MIME/empty file/out-of-range), `409` (audio active), `422` (`RequestValidationError`, occupied slot `524`, or model import/validation `VCClientError`).

### 4.4 `PATCH /api/slot-manager/slots/{index}`

Updates a ready RVC model's display `name` and/or `icon_file` (`multipart/form-data`) without reloading the inference pipeline.

| Field | Kind | Required | Constraints |
| --- | --- | --- | --- |
| `name` | Form string | No* | Non-empty after `.strip()` |
| `icon_file` | File | No* | Same image suffix, MIME, and non-empty checks as `POST` |

\* At least one of `name` or `icon_file` must be provided.

- **Execution & Rollback**: Validates `index` and fields before touching `model_dir/<index>/`, enforces stopped audio (`409`), stages any new icon in `tempfile.TemporaryDirectory()`, copies the new icon into `model_dir/<index>/`, calls `SlotManager.save_slot_info()` (does **not** trigger `VoiceChanger.check_and_update_pipeline()`), rolls back both in-memory `slot_info` fields and copied icon file if saving fails, and unlinks the replaced prior icon file inside the slot directory only after `params.json` is saved. `params.json` is written directly, so a failed write does not guarantee that the previous file contents remain intact.
- **Responses**: `200` (updated `SlotInfoMember`), `400` (missing/empty fields, invalid suffix/MIME, out-of-range), `409` (audio active), `422` (`VCClientError` `524` if slot is empty or not `RVCSlotInfo`).

### 4.5 `PUT /api/slot-manager/slots/{index}`

Updates an RVC slot's runtime inference settings (`application/json`).

- **Body**: Full `RVCSlotInfo` JSON DTO (`detect_slot_info` requires `voice_changer_type == "RVC"`).
- **Behavior & Side Effects**:
  - Validates path `{index}` (`400`), then calls `SlotManager.update_slot_info(slot_info)` and `VoiceChanger.get_instance().check_and_update_pipeline()`.
  - `update_slot_info` resolves the target slot from `slot_info.slot_index` in the request body and raises `VCClientError` `524` -> `422` if empty.
  - Does **not** enforce a backend active-audio `409` check; the frontend gates structural edits (`pitch_estimator`, `chunk_sec`) client-side and stages them until start.
- **Response**: `200` (`null`).

### 4.6 `DELETE /api/slot-manager/slots/{index}` & `POST /api/slot-manager/operation/organize`

Both routes share `_organize_models()` (`lifecycle_lock`) and [`ModelTransaction`](../backend/vcclient/voice_changer/slot_manager/reorder_transaction.py):

- **`DELETE /api/slot-manager/slots/{index}`**:
  - Deletes slot `{index}` and compacts remaining occupied slots sequentially to `0..N-1`.
  - Returns `400` if `{index}` is out of range; `404` (`ERR_HTTP_EXCEPTION`, `"Model does not exist"`) if `{index}` is not occupied.
- **`POST /api/slot-manager/operation/organize`**:
  - **Body (`application/json`)**: `{"order": [int, ...]}` (reorder-only; must contain every currently occupied slot index with no omissions or duplicates). Extra legacy fields such as `delete_selected` are ignored by Pydantic, so passing a reduced `order` returns `409` (`"Model list changed; reload before trying again"`).
- **Shared Locking & Pipeline Update Behavior**:
  1. Acquires `LocalVoiceChangerInterface.lifecycle_lock`.
  2. Rejects with `409` if native audio is enabled/running (`"Audio must be stopped before organizing models"`), bulk conversion is running (`VoiceChanger.peek_instance()` -> `"Audio conversion is still running"`), active pipeline is non-RVC (`"Unsupported active model pipeline"`), or any slot is `"RESERVED_FOR_SAMPLE"` (`"A model import is in progress"`). Uses `VoiceChanger.peek_instance()` so deleting or reordering a broken selected slot does not fail trying to load models when uninitialized.
  3. Runs `ModelTransaction(ModelDir, ConfigFile).apply()` (journaled in `model_dir/.model-order-transaction/` for startup crash recovery): moves slot directories, updates `slot_index` inside each `params.json`, and updates `current_slot_index` in `settings/vc_conf.json` (setting `-1` if the selected slot was deleted).
  4. Reloads `SlotManager`, updates `configuration.current_slot_index`, and updates `voice.vc_pipeline` / `voice.vc_info` if `VoiceChanger` is instantiated (`vc_pipeline` is cleared when `new_selected == -1`; `vc_pipeline.slot_index` is updated when `RVCPipeline`).
- **Success Response (`200`)**: `{"current_slot_index": int}` (`-1` when no slot is selected).

### 4.7 Slot Schemas & Enumerations

Defined in [`slot_manager_data_types.py`](../backend/vcclient/voice_changer/data_types/slot_manager_data_types.py) and [`voice_changer_const.py`](../backend/vcclient/voice_changer/voice_changer_const.py):

- **`SlotInfo` (base / empty / broken)**: `slot_index: int = -1`, `voice_changer_type: "RVC" | "RESERVED_FOR_SAMPLE" | "BROKEN" | null = null`, `name: str = ""`, `icon_file: str | null = null`.
- **`ReservedForSampleSlotInfo`** (extends `SlotInfo`): `voice_changer_type: "RESERVED_FOR_SAMPLE"`, `progress: float`.
- **`RVCSlotInfo`** (extends `SlotInfo`):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `voice_changer_type` | `"RVC"` | `"RVC"` | Slot discriminator |
| `model_file` | `string \| null` | `null` | Basename or relative path within slot directory |
| `index_file` | `string \| null` | `null` | Optional `.index` file within slot directory |
| `is_onnx` | `boolean` | `false` | `true` for ONNX models |
| `inferencer_type` | `"onnxRVC" \| "onnxRVCNono"` | `"onnxRVC"` | Validator normalizes strings containing `"Nono"` to `"onnxRVCNono"`, others to `"onnxRVC"` |
| `sample_rate` | `integer` | `-1` | Model target sample rate (Hz) |
| `is_f0` | `boolean` | `true` | Pitch-guided model flag |
| `embedder` | `EmbedderType` | `"hubert_base_l12"` | Feature extractor model |
| `pitch_estimator` | `PitchEstimatorType` | `"rmvpe"` | Validator normalizes values other than `"rmvpe"` / `"fcpe"` to `"rmvpe"` |
| `version` | `string` | `""` | Detected RVC version (`"v1"`, `"v2.1"`, etc.) |
| `chunk_sec` | `number` | `0.5` | Inference chunk duration in seconds |
| `pitch_shift` | `integer` | `0` | Semitone pitch shift |
| `index_ratio` | `number` | `0` | FAISS index blend ratio (`0.0`–`1.0`) |

- **Allowed Literal Types**:
  - `EmbedderType`: `"hubert_base_l9fp"`, `"hubert_base_l12"`, `"contentvec"`, `"hubert_base_japanese_l9fp"`, `"hubert_base_japanese_l12"`, `"whisper"`, `"applio_japanese_hubert_base_l12"`, `"applio_chinese_hubert_base_l12"`, `"applio_korean_hubert_base_l12"`.
  - `PitchEstimatorType`: `"harvest"`, `"dio"`, `"rmvpe"`, `"fcpe"` (stored slots normalize to `"rmvpe"` or `"fcpe"`).
  - `InferencerType`: `"onnxRVC"`, `"onnxRVCNono"`.
  - `RVCInferencerOnnxVersion`: `"v1"`, `"v1.1"`, `"v2"`, `"v2.1"`, `"v2.2"`, `"v3.0"`.

---

## 5. Configuration Management (`/api/configuration-manager/*`)

Implemented in [`vcserver_rest_api_configuration_manager.py`](../backend/vcclient/server/vcserver_rest_api_configuration_manager.py) and [`configuration_manager.py`](../backend/vcclient/voice_changer/configuration_manager/configuration_manager.py).

### 5.1 `GET /api/configuration-manager/configuration`

- **Query**: `reload: bool = False`. When `true`, reloads `settings/vc_conf.json`, resolves/normalizes `gpu_device_id_int` through `get_device()` (persisting if adjusted), and resets transient `recording_started` and `pass_through` to `false`.
- **Response (`200`)**: `VoiceChangerConfiguration` JSON.

### 5.2 `PUT /api/configuration-manager/configuration`

- **Body (`application/json`)**: `VoiceChangerConfiguration`. Because Pydantic fills omitted fields with defaults, clients should read the current DTO via `GET`, merge edits, and `PUT` the complete object.
- **Side Effects & Behavior**:
  1. Normalizes `gpu_device_id_int` via `get_device()`.
  2. Rejects `voice_changer_input_mode` changes while `LocalVoiceChangerInterface.stop_flag is False` (`VCClientError` `100` -> `422`).
  3. Transitions on `recording_started` invoke `VoiceChanger.get_instance().start_recording()` or `stop_recording()`.
  4. If audio device indices, device sample rates, or `wasapi_exclusive_enabled` change, validates explicitly selected device/sample-rate pairs (`201`–`203`), even when native audio is stopped. If `local_voice_changer_enabled` is `True`, also validates non-`-1` input/output devices (`204`, `205`), stops native audio before the sample-rate checks, and calls `setup()` and `start()` in `finally`.
  5. Preserves current runtime `input_sample_rate`, `output_sample_rate`, and `monitor_sample_rate` (client-supplied values for those three fields are overwritten by current in-memory values).
  6. Writes `settings/vc_conf.json` excluding `pass_through` and `recording_started`.
  7. Calls `VoiceChanger.get_instance().check_and_update_pipeline()`.
- **Response (`200`)**: `null`.

### 5.3 `VoiceChangerConfiguration` Schema ([`data_types.py`](../backend/vcclient/voice_changer/data_types/data_types.py))

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `current_slot_index` | `integer` | `0` | Selected slot index (`-1` when none selected) |
| `voice_changer_input_mode` | `"server" \| "client"` | `"client"` | Audio transport mode |
| `pass_through` | `boolean` | `false` | Bypass conversion (not persisted) |
| `recording_started` | `boolean` | `false` | Server-side recording toggle (not persisted) |
| `enable_performance_monitor` | `boolean` | `true` | Enables `realtime_process_status` metrics with `realtime_process_status_enabled` |
| `enable_high_pass_filter` | `boolean` | `true` | Input/conversion high-pass filter toggle |
| `high_pass_filter_cutoff` | `number` | `100` | High-pass cutoff frequency (Hz) |
| `enable_low_pass_filter` | `boolean` | `true` | Output low-pass filter toggle |
| `low_pass_filter_cutoff` | `number` | `12000` | Low-pass cutoff frequency (Hz) |
| `audio_input_device_index` | `integer` | `-1` | Server Mode PortAudio input index (`-1` = unselected) |
| `audio_output_device_index` | `integer` | `-1` | Server Mode PortAudio output index (`-1` = unselected) |
| `audio_monitor_device_index` | `integer` | `-1` | Server Mode PortAudio monitor index (`-1` = disabled) |
| `wasapi_exclusive_enabled` | `boolean` | `false` | WASAPI exclusive flag (accepts legacy `wasapi_exclude_emabled` on read via Pydantic `AliasChoices`) |
| `audio_input_device_sample_rate` | `integer` | `-1` | Input device sample rate (`-1` = device default) |
| `audio_output_device_sample_rate` | `integer` | `-1` | Output device sample rate (`-1` = device default) |
| `audio_monitor_device_sample_rate` | `integer` | `-1` | Monitor device sample rate (`-1` = device default) |
| `audio_input_device_gain` | `number` | `2` | Server Mode input gain multiplier |
| `audio_output_device_gain` | `number` | `1` | Server Mode output gain multiplier |
| `realtime_process_status_enabled` | `boolean` | `true` | Controls `realtime_process_status` emission (fixed `1.0` s interval constant) |
| `realtime_output_status_enabled` | `boolean` | `true` | Controls `realtime_output_status` emission (fixed `0.2` s interval constant) |
| `noise_gate` | `number` | `-35` | Gate threshold in dB (`<= -100` bypasses gate) |
| `extra_frame_sec` | `number` | `0.5` | Extra context window length (s) |
| `gpu_device_id_int` | `integer` | `0` | Compute device catalog index (`0` = CPU) |
| `input_sample_rate` | `integer` | `48000` | Runtime input sample rate (read-only across `PUT`) |
| `output_sample_rate` | `integer` | `48000` | Runtime output sample rate (read-only across `PUT`) |
| `monitor_sample_rate` | `integer` | `48000` | Runtime monitor sample rate (read-only across `PUT`) |

---

## 6. Voice Changer & Native Audio Control

### 6.1 `GET /api/voice-changer-manager/information`

Implemented in [`vcserver_rest_api_voice_changer.py`](../backend/vcclient/server/vcserver_rest_api_voice_changer.py). Calls `VoiceChanger.get_instance().get_voice_changer_information()`, which checks whether the model needs reloading. If a pipeline exists, it also checks the pitch estimator, sample rates, and filters before returning pipeline information; otherwise it returns the current `vc_info` without those checks.

- **Response (`200`, `VoiceChangerManagerInfo`)**:
  - `local_voice_changer_interface_active`: `boolean`
  - `voice_changer_information` (`VoiceChangerInformation` in [`voice_changer_data_types.py`](../backend/vcclient/voice_changer/data_types/voice_changer_data_types.py)):
    - `slot_index` (`int`), `override_embedder` (`EmbedderType | null`), `pitch_estimator_type` (`PitchEstimatorType | null`), `gpu_device_index` (`int`), `input_sample_rate` (`int`), `output_sample_rate` (`int`), `monitor_sample_rate` (`int`), `vc_input_sample_rate` (`int`), `vc_output_sample_rate` (`int`), `resample_ratio_in` / `resample_ratio_out` / `resample_ratio_monitor` / `resample_ratio_pass_through_in_out` / `resample_ratio_pass_through_in_monitor` (`float`), `enable_high_pass_filter` (`bool`), `high_pass_filter_cutoff` (`float`), `enable_low_pass_filter` (`bool`), `low_pass_filter_cutoff` (`float`), `chunk_sec` (`float`), `voice_changer_type` (`VoiceChangerType | null`), `bulk_process_start_flag` (`bool`), `recording_start_flag` (`bool`), `monitor_enabled` (`bool`), and `pipeline_info` (`RVCPipelineInfo | PipelineInfo | null`).
  - **`RVCPipelineInfo`**: `slot_index`, `input_sample_rate`, `output_sample_rate`, `chunk_sec`, `slot_info` (`RVCSlotInfo` dict or `null`), plus `embedder_info` (`embedder_type`, `model_file`, `device_id`, ONNX provider lists/options), `pitch_estimator_info` (`pitch_estimator_type`, `model_file`, `device_id`, ONNX provider lists/options), and `inferencer_info` (`inferencer_type`, `model_file`, `device_id`, ONNX provider lists/options).

### 6.2 `GET /api/local-voice-changer-interface/information`

Implemented in [`vcserver_rest_api_local_voice_changer_interface.py`](../backend/vcclient/server/vcserver_rest_api_local_voice_changer_interface.py). Does **not** call `VoiceChanger.get_instance()`.

- **Response (`200`)**: `{"local_voice_changer_interface_active": bool}` (`true` when `local_voice_changer_enabled is True`).

### 6.3 `POST /api/local-voice-changer-interface/operation/start`

- Requests Server Mode native audio by setting `local_voice_changer_enabled = True`. The main loop subsequently performs device setup and starts streaming; a `200` response does not confirm that the stream has started successfully.
- Requires `voice_changer_input_mode == "server"` and selected `audio_input_device_index` / `audio_output_device_index` (`!= -1`). Because this router omits `ValidationErrorLoggingRoute`, `RuntimeError` or `VCClientError` (`600`, `601`) produces HTTP `500`.
- **Response (`200`)**: `null`.

### 6.4 `POST /api/local-voice-changer-interface/operation/stop`

- Sets `local_voice_changer_enabled = False` and calls `VoiceChanger.get_instance().stop_convert_chunk_bulk()` (also stops the shared conversion worker used by Client Mode).
- **Response (`200`)**: `null`.

---

## 7. Audio & Compute Device Discovery

### 7.1 `GET /api/audio-device-manager/input_devices` & `GET /api/audio-device-manager/output_devices`

Implemented in [`vcserver_rest_api_audio_device_manager.py`](../backend/vcclient/server/vcserver_rest_api_audio_device_manager.py).

- **Query**: `reload: bool = False`. When `true` on **either** endpoint, resets PortAudio and refreshes both input and output device lists.
- **Response (`200`, `list[AudioDevice]`)**: `kind` (`"audioinput" | "audiooutput"`), `index` (`int`), `name` (`str`), `host_api` (`str`), `max_input_channels` (`int`), `max_output_channels` (`int`), `default_samplerate` (`int`).

### 7.2 `GET /api/gpu-device-manager/devices`

Implemented in [`vcserver_rest_api_gpu_device_manager.py`](../backend/vcclient/server/vcserver_rest_api_gpu_device_manager.py) and [`device/data_types.py`](../backend/vcclient/device/data_types.py). See [DeviceConfig & Catalog Index Architecture](./device-config-and-unified-hardware-descriptor.md) for catalog design details.

- **Query**: `reload: bool = False`. When `true`, re-probes platform hardware and rebuilds the catalog.
- **Response (`200`, `list[DeviceConfig]`)**: Sequential catalog where `id = 0` is always host CPU:
  - `id` (`int`), `canonical_id` (`str`, e.g. `"cpu"`, `"cuda:0"`, `"dml:0"`, `"openvino:gpu:0"`), `provider` (`"cpu" | "cuda" | "directml" | "openvino" | "coreml"`), `device_index` (`int`), `device_type` (`"CPU" | "GPU" | "NPU"`), `name` (`str`), `adapter_ram` (`int`, bytes), `metadata` (`object`), plus computed compatibility fields `device_id_int` (`id`) and `device_id` (`canonical_id`).

---

## 8. WebSocket Endpoints (`/api/ws/*`)

Implemented in [`vcserver_websocket.py`](../backend/vcclient/server/vcserver_websocket.py). Both share [`websocketUrl()`](../frontend/src/lib/api.ts) path resolution and Vite `/api` proxy support (`ws: true`).

### 8.1 `WS /api/ws/status` (Server -> Client Telemetry)

- **Behavior**: Accepts connection with a per-client bounded queue (`STATUS_QUEUE_MAXSIZE = 32`, dropping oldest queued message when full). Any incoming client messages are ignored (read loop exists to detect disconnects). Closed with code `1001` on server shutdown.
- **Message Format (JSON text frames)**: `{"type": "<event_type>", "data": {...}}`.
  - **`realtime_output_status`** (emitted in Server Mode when `realtime_output_status_enabled` is `true`):
    - `realtimeOutputStatusSendIntervalSec` (`float`), `realtimeOutputStatusSendInterval` (`float`, computed as `REALTIME_OUTPUT_STATUS_SEND_INTERVAL_SEC / 0.01`), `outputBufferSize` (`int`, queued sample count), `inputRms` (`float`), `outputRms` (`float`).
  - **`realtime_process_status`** (emitted when both `realtime_process_status_enabled` and `enable_performance_monitor` are `true`):
    - `PerformanceData` serialized with aliases: `inputBufferSize` (`float`), `inputSize` (`float`), `inputSec` (`float`), `outputSize` (`float`), `outputSec` (`float`), `elapsedTime` (`float`), `input_volume_db` (`float`), `output_volume_db` (`float`), `dataNum` (`int`).

### 8.2 `WS /api/ws/audio` (Client Mode Streaming PCM)

- **Wire Format**: Bidirectional binary WebSocket frames containing little-endian 32-bit IEEE 754 float mono PCM (`<f4` / `Float32Array`). Empty frames or frames whose byte length is not a multiple of 4 are ignored.
- **Lifecycle**: Lazily calls `VoiceChanger.get_instance().start_convert_chunk_bulk()` on the first received frame, runs `convert_chunk_bulk()`, and sends back converted `<f4` PCM frames (empty conversion outputs are omitted). Disconnecting the socket does **not** stop the conversion worker; call `POST /api/local-voice-changer-interface/operation/stop` to stop it.

---

## 9. Static Assets, Recordings, Logs & Docs

Registered in [`vcserver_rest_api.py`](../backend/vcclient/server/vcserver_rest_api.py):

| Route | Source | Response / Notes |
| --- | --- | --- |
| `GET /output.wav` | `SERVER_IO_RECORDING_FILE_OUT` (`output.wav`) | `audio/wav` `FileResponse` (or `404` JSON if file does not exist) |
| `GET /vcclient.log` | `LOG_FILE` (`vcclient.log`) | `text/plain` `FileResponse` (or `404` JSON if file does not exist) |
| `GET /model_dir/{path}` | `ModelDir` (`model_dir/`) | `StaticFiles` mount serving slot icons and model directory files |
| `GET /docs`, `GET /openapi.json` | FastAPI OpenAPI | Custom Swagger UI HTML and OpenAPI schema |
| `GET /` | `get_frontend_path()` (`frontend/dist`) | `StaticFiles` SPA root (`html=True`, `check_dir=False`) |

---

## 10. Removed Legacy Endpoints

| Removed Endpoint / Protocol | Replacement |
| --- | --- |
| `POST /api/uploader/upload_file_chunk`, `POST /api/uploader/concat_uploaded_file_chunk` | `POST /api/slot-manager/slots` (`multipart/form-data`) / `PATCH /api/slot-manager/slots/{index}` (`multipart/form-data`) |
| `POST /api/slot-manager/slots/operation/set_icon_file` | `PATCH /api/slot-manager/slots/{index}` (`multipart/form-data`) |
| `delete_selected` body field on `POST /api/slot-manager/operation/organize` | `DELETE /api/slot-manager/slots/{index}` |
| `/socket.io/` | `WS /api/ws/status` and `WS /api/ws/audio` |
