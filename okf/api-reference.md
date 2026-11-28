---
title: "VCClient Forge HTTP & WebSocket API Reference"
version: "0.2.0"
okf_version: "0.2"
description: "HTTP REST, multipart, WebSocket, and UI serving specification implemented by the VCClient Forge Python backend."
---

# VCClient Forge HTTP & WebSocket API Reference

> **Implemented Control Plane (`backend/vcclient/server/`)**:
> This document specifies the Domain HTTP REST, multipart, and WebSocket API currently implemented by the Python backend. Architectural rationale, subsystem boundaries, and concurrency guarantees are documented in [Snapshot-Driven Conversion Engine & Decoupled Storage/Device APIs](./snapshot-driven-pipeline-and-stateless-control-api.md).

---

## 1. Server Overview & Conventions

- **Default Host & Port**: Launching via [`backend/main.py`](../backend/main.py) binds `0.0.0.0:18888` by default (`--host`, `--port`). Direct instantiation of `VCServer()` ([`vcserver.py`](../backend/vcclient/server/vcserver.py)) defaults to `127.0.0.1` and picks an unused ephemeral port.
- **Caching**: `NoCacheMiddleware` ([`vcserver_rest_api.py`](../backend/vcclient/server/vcserver_rest_api.py)) sets `Cache-Control: no-store` on all HTTP responses.
- **Schema UI**: Swagger UI is served at `GET /docs` against `GET /openapi.json` (`redoc_url=None`).
- **Optimistic Concurrency (`ETag` / `If-Match`)**: Mutable resources (`/api/session`, `/api/settings`, `/api/models/{model_id}`, `/api/models/order`, `/api/models/{model_id}/icon`) return a strong `ETag` header computed via [`compute_etag()`](../backend/vcclient/server/api_common.py). Passing `If-Match` verifies the tag (accepting `*`, comma-separated lists, or weak tags `W/"..."`) and rejects mismatches with `409 Conflict` (`etag_mismatch`, `details.current_etag`). Omitting `If-Match` executes under server locks in arrival order.

---

## 2. Unified Error Envelope

All `/api/*` HTTP errors pass through [`DomainApiRoute`](../backend/vcclient/server/api_common.py) or `register_api_exception_handlers()` ([`vcserver_rest_api.py`](../backend/vcclient/server/vcserver_rest_api.py)) and return:

```json
{
  "code": "session_rebuild_required",
  "message": "Session must be stopped before changing rebuild-required fields.",
  "details": {
    "conflicting_fields": ["model_id", "chunk_sec"]
  }
}
```

- **`DomainApiError`**: Returns its configured HTTP status, `code`, `message`, and `details`.
- **`RequestValidationError`**: Returns `422` with `code: "validation_error"` and encoded validation errors in `details.errors` (decoding raw `bytes` with UTF-8 replacement to avoid encoding failures on invalid binary multipart inputs).
- **`VCClientError`**: Returns `422` with `code: "vcclient_error"`, `message: exc.info.reason`, and `details` from `VCClientErrorInfo`.
- **Unhandled exceptions**: Return `500` with `code: "internal_error"`.
- **Starlette HTTP exceptions under `/api` and `/api/*`**: Unmatched `/api/*` routes (`unknown_api` fallback) return `404` (`code: "not_found"`); unsupported methods return `405` (`code: "method_not_allowed"`); other HTTP errors return `code: "http_error"`. WebSocket handshakes to unknown `/api/*` paths close immediately with code `1008`.
- **Non-`/api` paths**: Unknown non-API routes use FastAPI's default HTTP exception handler (`404 {"detail": "Not Found"}`).

Representative `code` values: `validation_error`, `not_found`, `method_not_allowed`, `etag_mismatch`, `session_starting`, `session_active`, `session_rebuild_required`, `session_start_failed`, `model_not_found`, `model_in_use`, `model_import_failed`, `icon_not_found`, `catalog_mismatch`, `invalid_compute_device`, `invalid_audio_device`, `invalid_filter_cutoff`, `recording_not_found`, `recording_in_progress`, `log_not_found`, `compute_auto_select_failed`, `vcclient_error`, `internal_error`.

---

## 3. Endpoint Summary

| Group | Protocol / Method | Path | Request | Response |
| --- | --- | --- | --- | --- |
| Session | `GET` | `/api/session` | — | `200` `SessionState` (`ETag`) |
| Session | `PUT` | `/api/session` | JSON `SessionSnapshot`, optional `If-Match` | `202` (`starting`) or `200` (`running`) `SessionState` (`ETag`) |
| Session | `DELETE` | `/api/session` | Optional `If-Match` | `200` `SessionState` (`ETag`) |
| Models | `GET` | `/api/models` | — | `200` `Model[]` |
| Models | `POST` | `/api/models` | `multipart/form-data` | `201` `Model` (`ETag`) |
| Models | `PUT` | `/api/models/order` | JSON `ModelOrder`, optional `If-Match` | `200` `ModelOrder` (`ETag`) |
| Models | `GET` | `/api/models/{model_id}` | — | `200` `Model` (`ETag`) |
| Models | `PUT` | `/api/models/{model_id}` | JSON `ModelUpdate`, optional `If-Match` | `200` `Model` (`ETag`) |
| Models | `DELETE` | `/api/models/{model_id}` | Optional `If-Match` | `204 No Content` |
| Models | `GET` | `/api/models/{model_id}/icon` | — | `200` `image/*` (`ETag`) |
| Models | `PUT` | `/api/models/{model_id}/icon` | `multipart/form-data` or `image/*`, optional `If-Match` | `200` `Model` (`ETag`) |
| Models | `DELETE` | `/api/models/{model_id}/icon` | Optional `If-Match` | `200` `Model` (`ETag`) |
| Settings | `GET` | `/api/settings` | — | `200` `UserSettings` (`ETag`) |
| Settings | `PUT` | `/api/settings` | JSON `UserSettings`, optional `If-Match` | `200` `UserSettings` (`ETag`) |
| Devices | `GET` | `/api/devices/audio` | — | `200` `AudioDevicesResponse` |
| Devices | `POST` | `/api/devices/audio/reload` | — | `200` `AudioDevicesResponse` |
| Devices | `GET` | `/api/devices/compute` | — | `200` `DeviceConfig[]` |
| Devices | `POST` | `/api/devices/compute/reload` | — | `200` `DeviceConfig[]` |
| Devices | `POST` | `/api/devices/compute/auto-select` | — | `200` `ComputeDeviceRecommendation` |
| Recordings | `GET` | `/api/recordings/latest` | — | `200` `audio/wav` |
| Logs | `GET` | `/api/logs` | — | `200` `text/plain` |
| WebSocket | `WS` | `/api/ws/status` | Server -> Client JSON | Telemetry frames |
| WebSocket | `WS` | `/api/ws/audio` | Bidirectional `<f4` PCM binary | Converted audio frames |
| Docs / UI | `GET` | `/docs`, `/openapi.json`, `/` | — | Swagger UI, OpenAPI schema, SPA |

---

## 4. Session Lifecycle (`/api/session`)

Implemented in [`vcserver_rest_api_session.py`](../backend/vcclient/server/vcserver_rest_api_session.py) and [`session_manager/`](../backend/vcclient/voice_changer/session_manager/session_manager.py).

- **`SessionState`**: `status` (`"stopped" | "starting" | "running"`), `snapshot` (`SessionSnapshot | null`), `locked_fields` (`LOCKED_SESSION_FIELDS`), `input_sample_rate` / `output_sample_rate` / `monitor_sample_rate` (`int | null`), and `last_error` (`ApiErrorResponse | null`).
- **`SessionSnapshot` defaults & fields**:
  - Model & inference: `model_id` (`str`), `pitch_shift` (`0`), `index_ratio` (`0.0`), `chunk_sec` (`0.5`), `pitch_estimator` (`"rmvpe" | "fcpe"`), `extra_frame_sec` (`0.5`), `compute_device_id` (`0`).
  - Audio routing: `input_mode` (`"client" | "server"`), `audio_input_device_index` (`-1`), `audio_output_device_index` (`-1`), `audio_monitor_device_index` (`-1`), `audio_input_device_sample_rate` (`-1`), `audio_output_device_sample_rate` (`-1`), `audio_monitor_device_sample_rate` (`-1`), `wasapi_exclusive_enabled` (`false`).
  - DSP, recording & telemetry: `input_gain` (`2.0`), `output_gain` (`1.0`), `enable_high_pass_filter` (`true`), `high_pass_filter_cutoff` (`100.0`), `enable_low_pass_filter` (`true`), `low_pass_filter_cutoff` (`12000.0`), `noise_gate` (`-35.0`), `pass_through` (`false`), `recording` (`false`), `enable_performance_monitor` (`true`), `realtime_process_status_enabled` (`true`), `realtime_output_status_enabled` (`true`).
  - Legacy aliases accepted on input: `gpu_device_id_int`, `voice_changer_input_mode`, `wasapi_exclude_emabled`, `wasapi_exclusive`, `audio_input_device_gain`, `audio_output_device_gain`, `recording_started`.
- **`LOCKED_SESSION_FIELDS`**: `model_id`, `chunk_sec`, `pitch_estimator`, `extra_frame_sec`, `compute_device_id`, `input_mode`, `audio_input_device_index`, `audio_output_device_index`, `audio_monitor_device_index`, `audio_input_device_sample_rate`, `audio_output_device_sample_rate`, `audio_monitor_device_sample_rate`, `wasapi_exclusive_enabled`.
- **Lifecycle behavior**:
  - `GET /api/session`: Read-only; never constructs pipelines or touches audio devices.
  - `PUT /api/session` when `stopped`: Validates snapshot (model exists, `compute_device_id` in range, filter cutoffs ordered and below Nyquist, Server Mode input/output/monitor devices and sample rates supported), transitions to `"starting"` (`202`), starts the pipeline on a background thread (`_run_startup`). When the pipeline cache key matches, it resets and reuses the loaded pipeline; otherwise it builds and warms up a new one. Client Mode transitions to `"running"` once the conversion worker starts; Server Mode transitions to `"running"` when `notify_audio_started()` fires after audio streams open. Startup or audio-open errors transition back to `"stopped"` with `last_error` populated.
  - `PUT /api/session` when `starting`: Rejected with `409` (`session_starting`).
  - `PUT /api/session` when `running`: Validates snapshot; if any field in `LOCKED_SESSION_FIELDS` changed, rejects with `409` (`session_rebuild_required`, `details.conflicting_fields`); otherwise atomically swaps the active snapshot, updates filter coefficients and recording state, and returns `200`.
  - `DELETE /api/session`: Idempotent when `stopped` (`200`); rejected with `409` (`session_starting`) when `starting`; closes audio WebSockets (`1000`), stops local audio and conversion workers, finalizes active recording (`stop_recording()`), clears runtime session state, and returns `200`.

---

## 5. Model Catalog (`/api/models*`)

Implemented in [`vcserver_rest_api_models.py`](../backend/vcclient/server/vcserver_rest_api_models.py) and [`model_catalog/`](../backend/vcclient/voice_changer/model_catalog/model_catalog_manager.py). Models are addressed by immutable NanoID `id` under `model_dir/{sanitized_name} - {id}/`, with display order persisted in `model_dir/catalog.json`. All mutations are pure catalog/storage operations (no implicit pipeline rebuilds).

- **`GET /api/models`**: Returns ordered `list[Model]`.
- **`POST /api/models`** (`multipart/form-data`):
  - Fields: `name` (`Form`, non-blank), `model_file` (`File`, `.onnx` or `.pth`), `index_file` (`File | None`, `.index`), `icon_file` (`File | None`, `.png/.jpg/.jpeg/.webp/.gif/.avif/.bmp`), `embedder` (`EmbedderType | None`). `.pth` uploads are converted to ONNX on import. Returns `201 Model` with `ETag`.
- **`GET /api/models/{model_id}`**: Returns `200 Model` (`ETag`) or `404` (`model_not_found`).
- **`PUT /api/models/{model_id}`**: Accepts `ModelUpdate` (`name`, `pitch_shift` `[-24..24]`, `index_ratio` `[0.0..1.0]`, `chunk_sec` `[0.05..5.0]`, `pitch_estimator` `"rmvpe" | "fcpe"`). Parameter updates and renaming work while `running`; changing `name` while `model_id` is in a `starting` session or directory-locked returns `409` (`model_in_use`).
- **`DELETE /api/models/{model_id}`**: Removes the model folder and prunes `catalog.json` + matching `settings.model_id`; returns `204`. Returns `409` (`model_in_use`) if active in a session.
- **`GET /api/models/{model_id}/icon`**: Streams image bytes (`ETag`); returns `404` (`model_not_found` / `icon_not_found`) if missing.
- **`PUT /api/models/{model_id}/icon`**: Accepts `multipart/form-data` (`icon_file` or `file`) or raw `Content-Type: image/*`, replaces previous icon file, increments `icon_revision`, and returns `200 Model` (`ETag`).
- **`DELETE /api/models/{model_id}/icon`**: Removes the icon file (idempotent), increments `icon_revision` when removed, and returns `200 Model` (`ETag`).
- **`PUT /api/models/order`**: Accepts `ModelOrder` (`{"model_ids": string[]}`), validates against existing IDs (`409 catalog_mismatch`), writes only `model_dir/catalog.json` (safe while running), and returns `200 ModelOrder` (`ETag`).

---

## 6. Persisted Settings (`/api/settings`)

Implemented in [`vcserver_rest_api_settings.py`](../backend/vcclient/server/vcserver_rest_api_settings.py) and [`settings_manager/`](../backend/vcclient/voice_changer/settings_manager/settings_manager.py). Persists `settings/vc_conf.json` without triggering pipelines or audio devices.

- **`GET /api/settings`**: Returns `200 UserSettings` (`ETag`).
- **`PUT /api/settings`**: Validates domain bounds (`compute_device_id`, positive gains, filter cutoffs/Nyquist, `noise_gate`, `extra_frame_sec`) before atomically writing `settings/vc_conf.json`, and returns `200 UserSettings` (`ETag`). Extra legacy fields are ignored on parse; legacy field aliases are accepted on input.

---

## 7. Device Discovery & Auto-Selection (`/api/devices/*`)

Implemented in [`vcserver_rest_api_devices.py`](../backend/vcclient/server/vcserver_rest_api_devices.py).

- **`GET /api/devices/audio`**: Returns cached `{"inputs": AudioDevice[], "outputs": AudioDevice[]}` without re-probing PortAudio (safe while active).
- **`POST /api/devices/audio/reload`**: Re-probes PortAudio devices; returns `409` (`session_active`) if a session is active.
- **`GET /api/devices/compute`**: Returns cached `list[DeviceConfig]` (`id = 0` is CPU). See [DeviceConfig & Catalog Index Architecture](./device-config-and-unified-hardware-descriptor.md).
- **`POST /api/devices/compute/reload`**: Re-probes ONNX compute devices; returns `409` (`session_active`) if a session is active.
- **`POST /api/devices/compute/auto-select`**: Runs `recommend_compute_device()` when stopped (`409 session_active` when active; `409 model_not_found` or `500 compute_auto_select_failed` on failure) and returns `{"compute_device_id": int, "device": DeviceConfig}` without mutating `/api/settings`.

---

## 8. Recordings & Logs

Registered on `domain_system_router` in [`vcserver_rest_api.py`](../backend/vcclient/server/vcserver_rest_api.py):

- **`GET /api/recordings/latest`**: Returns `output.wav` (`audio/wav`) when present; returns `409` (`recording_in_progress`) while recording is active or `404` (`recording_not_found`) when missing.
- **`GET /api/logs`**: Returns `vcclient.log` (`text/plain`) or `404` (`log_not_found`) when missing. `uvicorn.access` filters `/api/logs` requests in [`logger.py`](../backend/vcclient/logger.py).

---

## 9. WebSocket Endpoints (`/api/ws/*`)

Implemented in [`vcserver_websocket.py`](../backend/vcclient/server/vcserver_websocket.py):

- **`WS /api/ws/status`**: Broadcasts `{"type": "<event_type>", "data": {...}}` JSON text telemetry (`realtime_output_status`, `realtime_process_status`) through bounded per-client queues (`STATUS_QUEUE_MAXSIZE = 32`, dropping oldest on overflow). Closes with `1001` on server shutdown.
- **`WS /api/ws/audio`**: Bidirectional little-endian 32-bit float mono PCM (`<f4`). Accepted only while a Client Mode session is `"running"` (otherwise accepts and immediately closes with `1008`). Connecting a replacement socket supersedes and closes the previous socket with code `4001` (`"superseded"`), drains stale queued chunks (`reset_client_stream_buffers()`), and keeps the session running. `DELETE /api/session` closes the socket with code `1000`.

---

## 10. Removed Legacy Endpoints & Protocols

- `/api/slot-manager/*` (`RestAPISlotManager`) -> `/api/models*`
- `/api/configuration-manager/configuration` (`RestAPIConfigurationManager`) -> `/api/settings` & `/api/session`
- `/api/audio-device-manager/{input_devices,output_devices}` (`RestAPIAudioDeviceManager`) -> `/api/devices/audio`, `/api/devices/audio/reload`
- `/api/gpu-device-manager/devices` (`RestAPIGPUDeviceManager`) -> `/api/devices/compute`, `/api/devices/compute/reload`
- `/api/voice-changer-manager/information` (`RestAPIVoiceChanger`) -> `/api/session`
- `/api/local-voice-changer-interface/*` (`RestAPILocalVoiceChangerInterface`) -> `/api/session`
- `/output.wav`, `/vcclient.log`, raw `/model_dir/*` static mount -> `/api/recordings/latest`, `/api/logs`, `/api/models/{model_id}/icon`
- Legacy chunked upload routes (`/api/uploader/*`), `ValidationErrorLoggingRoute`, `VoiceChangerManagerInfo` / `LocalVoiceChangerInterfaceInfo`, `/socket.io/`, and unguarded `WS /api/ws/audio` worker auto-start.
