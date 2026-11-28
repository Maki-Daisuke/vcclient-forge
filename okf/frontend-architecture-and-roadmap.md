---
type: architecture
title: "Next-Gen Frontend Architecture: Svelte 5, Native WebSocket, and Native Desktop Packaging"
description: "Server-Mode-first Svelte 5 UI replacement, native WebSocket notifications (/api/ws/status), and Client Mode audio streaming (/api/ws/audio)."
tags:
  [frontend, svelte, websocket, wails, i18n, performance, architecture, desktop]
timestamp: 2026-10-18T06:30:00Z
---

# Next-Gen Frontend Architecture: Svelte 5, Native WebSocket, and Native Desktop Packaging

**Transport decision (2026-11-19):** Replace Socket.IO (`python-socketio` and `socket.io-client`) with two purpose-specific native FastAPI WebSocket endpoints (`/api/ws/status` for realtime telemetry JSON frames and `/api/ws/audio` for raw `<f4` binary PCM audio streaming). This reverses the earlier 2026-11-09 decision to retain Socket.IO once old `web_front/` client compatibility was formally dropped, removing unneeded framing/tuple-packing overhead, `asyncio.run()` per-thread emissions, and third-party socket dependencies. The historical 2026-11-09 echo benchmark measurements below are preserved for reference.

## Current deployment

`npm run build:frontend` builds the Svelte UI into `frontend/dist`. FastAPI serves it at `/` and portable packages include the same build. Wails supervises the backend and navigates to this UI. The Svelte UI replaced the legacy `client/` source and `web_front/` bundle.

The UI uses Svelte 5 and TypeScript with a layout based on v2.1.4. Bits UI provides sliders and accessible dialogs, with standard HTML controls where suitable.

### Frontend API integration

- [Model catalog](../frontend/src/lib/catalog.svelte.ts) and [upload](../frontend/src/lib/model-upload.ts) use NanoID model IDs. Icon URLs include the icon revision. Dropped ZIP files are unpacked in the browser before uploading model and index files. Uploads, reordering, and display edits can run during conversion. The backend protects the active model from deletion.
- [Session state](../frontend/src/lib/session.svelte.ts) and the [API client](../frontend/src/lib/api.ts) coordinate persisted settings, device discovery, and active conversion. Device auto-selection recommends a target while stopped, and the UI stages the choice for Start. The client polls session state during startup, serializes live edits with a 100 ms throttle, and stops through `DELETE /api/session`, which finalizes an active recording.
- [Client audio](../frontend/src/lib/client-audio.svelte.ts) uses `AudioWorklet` and sends float32 mono PCM over `/api/ws/audio`. Reloading the UI can reconnect to an active Client Mode session. When a connection is superseded (`4001`), the previous client releases capture and the backend session continues.
- [Server Mode meters](../frontend/src/lib/audio-meters.svelte.ts) read `/api/ws/status`. Client Mode meters use Web Audio `AnalyserNode`s. The UI downloads the latest recording from `/api/recordings/latest`, and the [log viewer](../frontend/src/components/LogWindow.svelte) polls `/api/logs`.
- [UI preferences](../frontend/src/lib/ui.svelte.ts) and [browser audio settings](../frontend/src/lib/client-audio.svelte.ts) use local storage with fallbacks when storage is unavailable.

See the [developer guide](../README_dev.md#svelte-frontend-development) for commands and the [API reference](./api-reference.md) for request and response formats.

### Audio controls and defaults

- **Shared output gain in Server Mode.** The main and monitor output callbacks both use the same output gain. The UI exposes one output volume control for both. See the [native audio callbacks](../backend/vcclient/voice_changer/voice_change_manager/local_voice_changer_interface.py).
- **WASAPI shared mode from the UI.** If WASAPI exclusive mode was saved in an older configuration, the UI shows a notice and clears the setting on Start. It sends `wasapi_exclusive_enabled: false` when starting a native session. A failed settings update blocks startup. See the [browser regression test](../frontend/tests/wasapi.spec.ts).
- **Browser microphone processing in Client Mode.** Echo cancellation, noise suppression, and automatic gain control default to off. The UI stores the user's selections in browser local storage and applies them when opening the microphone. See the [browser audio handler](../frontend/src/lib/client-audio.svelte.ts).

### Hands-on checks during the Svelte migration

During the migration, hands-on checks covered native audio playback, importing a model from a ZIP and converting audio with it, and using browser echo cancellation, noise suppression, and automatic gain control with a real microphone. These observations apply to the builds used during the migration. See the [v0.4.0 migration record](https://github.com/Maki-Daisuke/vcclient-forge/blob/v2.0.78-forge.0.4.0/okf/frontend-architecture-and-roadmap.md).

## 1. Anatomy of the Legacy Frontend Bottlenecks

Historical inspection of the retired legacy `web_front/index.js` bundle identified the following problems in the pitch and index settings paths. These findings motivated redesigning settings interaction and synchronization. Slider lockups had been reported, and while the lockup itself was not reproduced in a browser during that investigation, the request and state-update behavior below was directly observed in the legacy bundle.

1. **Per-Change Writes and Reloads (Missing Coalescing)**:
   Pitch and index slider `onChange` handlers mutate the shared slot object and call `updateServerSlotInfo()` for each change event, without debounce or coalescing. The REST client issues a `PUT /api/slot-manager/slots/{slot_index}`; after the write succeeds, the state hook starts a `GET /api/slot-manager/slots` to reload the slot list. Thus each successful edit triggers both a write and a reload, rather than one synchronization of the latest value after a burst of edits. Request rate follows input events, not literally every pixel of pointer movement.

2. **Direct Mutation without Independent Draft State**:
   The slider `value` is derived from the shared slot object, and its element tree is memoized with that object's reference as a dependency. Changing a property directly does not trigger a React state update or invalidate that memoization. The inspected components have no independent local draft state; normal UI refresh depends on the reloaded slot list propagating through React state. This couples visual feedback to server synchronization and is consistent with the reported poor responsiveness, but is not a reproduced deadlock diagnosis.

3. **Uncoordinated Asynchronous Updates**:
   The pitch/index handlers do not await `updateServerSlotInfo()`; the downstream hook and REST client await the PUT. There is no write serialization or stale-read protection in the inspected path, and the subsequent list reload is started without awaiting it. Overlapping writes/reloads can therefore complete out of order and replace newer displayed state with an older snapshot. `await` itself does not block the UI thread or serialize separate input events.

   A mock-fetch probe using the actual bundled `RestClient` confirmed that 20 calls can issue 20 PUT requests before any response arrives, with distinct edit snapshots in their bodies. This verifies the absence of serialization/coalescing at that layer, not the real-world request rate or a browser lockup.

4. **Monolithic Bundle Footprint & Direct Array Indexing**:
   Bundled via Webpack 5 into a single ~2.6MB minified `index.js`, lacking source code. The UI directly accesses slot arrays via indexing (`serverSlotInfos[i]`), forcing the backend to generate padded dummy slots and preventing clean REST/JSON API modernization.

---

## 2. Why Backend Features Need a New UI

Backend/API changes alone do not deliver usable features: users need a UI that can operate them. The minified legacy frontend (`web_front/index.js`) was coupled to existing endpoints and slot-array conventions, and the original `web_front` source for v2.0.78-beta was not released. Keeping it as the only UI would have left new backend capabilities inaccessible or required preserving legacy bundle quirks.

Forge replaced `web_front/` with the Svelte 5 UI (`frontend/`) and deprecated legacy client compatibility, migrating real-time telemetry and Client Mode audio streaming from Socket.IO to native FastAPI WebSockets (`/api/ws/status` and `/api/ws/audio`).

---

## 3. Audio Transport and Protocol Evaluation

### 3.1 Why Keep "Client Mode" Web Audio Ingestion?

While Forge prioritizes **Server Mode** (native OS audio devices) for low latency, browser-based audio streaming (Client Mode) remains an invaluable capability:

- **Cross-Platform Portability**: Web Audio capture remains available without installing Forge's native audio backend on the client device.
- **Instant Fallback**: A reliable safety net when host audio drivers (WASAPI/CoreAudio/PortAudio) fail or conflict.

Client Mode is developed incrementally and is not a prerequisite for replacing the old UI.

### 3.2 Historical Socket.IO Transport (Replaced 2026-11-19)

Previously, the audio and telemetry transport relied on `python-socketio` and `python-engineio` (`vcserver_socketio.py`). In that implementation:

- Incoming binary samples passed through `struct.unpack` into Python values and were copied into NumPy; output used `struct.pack` with expanded sample arguments.
- Socket.IO/Engine.IO added event metadata, placeholder framing, unused `[timestamp, true, ...]` wrappers, and third-party dependencies beyond the PCM payload.
- Event emission created ephemeral loops via `asyncio.run()` on audio/worker threads.

### Local Binary Echo Experiment (2026-11-09)

The isolated benchmark in [`misc/benchmark_audio_echo.py`](../misc/benchmark_audio_echo.py)
compares a raw WebSocket binary echo with a Socket.IO binary-event echo. Both
use the same loopback FastAPI/uvicorn server process and Python aiohttp client
foundation; Socket.IO additionally uses python-socketio. No inference, audio
device, browser, resampling, or legacy `request_message` handler is involved.
Only one request is outstanding, every echoed payload is checked byte-for-byte,
and connection setup is excluded. Runs alternate protocol order after warmup.

On Windows 11 (build 26300), AMD Ryzen 9 7950X, Python 3.14.8, aiohttp 3.14.5,
python-socketio 5.17.0, python-engineio 4.14.0, uvicorn 0.54.0 and FastAPI
0.143.0, with 48 kHz mono float32 payloads, four rounds and 1,000 measurements
per case per round without pacing produced these pooled RTTs in milliseconds:

| Audio per message | Protocol | p50 | p95 | p99 | max |
| --- | --- | ---: | ---: | ---: | ---: |
| 50 ms | WebSocket | 0.102 | 0.153 | 0.224 | 0.326 |
| 50 ms | Socket.IO | 0.310 | 0.394 | 0.489 | 0.883 |
| 100 ms | WebSocket | 0.108 | 0.150 | 0.195 | 0.452 |
| 100 ms | Socket.IO | 0.318 | 0.397 | 0.502 | 0.737 |
| 200 ms | WebSocket | 0.118 | 0.172 | 0.232 | 0.400 |
| 200 ms | Socket.IO | 0.332 | 0.443 | 0.574 | 1.413 |

With a target interval of 100 ms, 100 ms payloads, two rounds and 50 measured
echoes per round, WebSocket p50/p95/p99/max were 0.389/0.499/0.584/0.732 ms;
Socket.IO values were 0.759/1.037/1.177/1.219 ms. This short paced run does not
characterize rare stalls. All measured replies in both runs matched the sent
bytes; the benchmark aborts on timeout or mismatch.

Reproduce from the repository root (the aiohttp overlay is temporary):

```sh
uv run --project backend --with aiohttp python misc/benchmark_audio_echo.py --count 1000 --warmup 100 --rounds 4
uv run --project backend --with aiohttp python misc/benchmark_audio_echo.py --count 50 --warmup 5 --rounds 2 --sizes 4800 --pace-ms 100
```

These results include each client library's scheduling and encoding, not just
protocol framing. They do not measure a browser/Wails client, real audio or
the former Socket.IO conversion handler, and do not establish end-to-end audio
latency or behavior under inference load. While Socket.IO was briefly retained in 2026-11-09, the project finalized the transition to direct FastAPI WebSockets on 2026-11-19 once legacy UI/client compatibility was dropped.

### Tailscale Binary Echo Experiment (2026-11-09)

Using the same client and benchmark procedure, a user-provided benchmark server
was measured over Tailscale; `tailscale ping` reported a direct path via a LAN
address. The server's hardware, runtime versions, and load were not measured.
Four rounds of 1,000 echoes per case produced these pooled RTTs in milliseconds:

| Audio per message | Protocol | p50 | p95 | p99 | max |
| --- | --- | ---: | ---: | ---: | ---: |
| 50 ms | WebSocket | 0.968 | 1.628 | 2.059 | 20.378 |
| 50 ms | Socket.IO | 1.118 | 1.692 | 2.078 | 2.674 |
| 100 ms | WebSocket | 1.189 | 1.731 | 2.049 | 2.500 |
| 100 ms | Socket.IO | 1.273 | 1.955 | 2.275 | 3.299 |
| 200 ms | WebSocket | 1.593 | 1.971 | 2.206 | 2.834 |
| 200 ms | Socket.IO | 1.785 | 2.324 | 2.559 | 11.841 |

In a separate run using 100 ms payloads and a target interval of 100 ms,
100 echoes per protocol produced p50/p95/p99/max of 2.596/3.017/3.210/3.419 ms
for WebSocket and 2.816/3.322/3.447/3.551 ms for Socket.IO. These small samples
do not characterize rare stalls. The paced values were higher than the
continuous-run values; this measurement did not identify the reason. All echoes
in the reported runs matched their payloads; timeouts and mismatches abort a run.

The script accepts `--url http://HOST:PORT` to use an existing benchmark server
instead of starting a local one. Results include the network and both machines'
processing; they are not measurements of actual browser audio or inference.

### 3.3 Current Direct WebSocket Transport (`/api/ws/status` and `/api/ws/audio`)

In [`vcserver_websocket.py`](../backend/vcclient/server/vcserver_websocket.py), Socket.IO and `python-engineio` have been removed in favor of two purpose-separated native FastAPI WebSocket endpoints mounted under `/api/`:

- **`/api/ws/status`** (Server -> Client JSON text frames): `AudioMeters` subscribes to `{"type": "realtime_output_status" | "realtime_process_status", "data": {...}}` single-encoded JSON messages, avoiding double `JSON.parse` overhead. Events from worker/audio threads are scheduled cleanly onto the FastAPI/Uvicorn asyncio loop via `call_soon_threadsafe` into a bounded drop-oldest queue, and `AudioMeters` uses a 1-second reconnect timer on unexpected disconnect while active.
- **`/api/ws/audio`** (Client <-> Server raw `<f4` float32 binary PCM): `ClientAudio` streams `Float32Array` chunks directly via `WebSocket.send()` without timestamp/bulk wrapper metadata or `struct.pack`/`struct.unpack` tuple expansion. The backend reads PCM into NumPy, submits it for bulk conversion, and sends converted PCM back to the browser.
- Both endpoints share Vite's `/api` dev/preview proxy (`ws: true`), Playwright's `/api/` mocking guards, and `VCServer.stop()`'s `WebSocketHub.close_all()` shutdown sweep. The server resets browser stream buffers when a new socket replaces an existing one. See the [WebSocket contract](./api-reference.md#9-websocket-endpoints-apiws).

---

## 4. Architectural Pivot: Svelte 5 + Vite

The framework decision followed the settings investigation, rather than preceding it:

1. The legacy implementation uses React, but bypasses React's state-update model by mutating shared objects and relying on server reloads for visual feedback. Keeping that interaction design would preserve the problem regardless of framework.
2. The new UI therefore needs a fresh interaction/state/synchronization design. React could implement that design correctly, but the legacy UI's use of React is not a requirement to choose React again.
3. For this local audio-control application, Forge chooses **Svelte 5 + Vite** as a lightweight fit for reactive settings, localized meter updates, and desktop packaging. The aim is a smaller, simpler frontend, not a claim that React is inherently unsuitable or that Svelte automatically fixes synchronization bugs.

This is a deliberate framework choice after deciding to redesign the UI, rather than a like-for-like React rewrite. Bundle size, CPU/memory usage, and responsiveness will still be measured in this application.

| Dimension                   | Legacy Frontend (`web_front` / `client`)   | Next-Gen Forge Frontend (`frontend/`)                                               |
| --------------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------- |
| **Framework**               | React 18/19 SPA                            | **Svelte 5** (Runes: `$state`, `$derived`, `$effect`)                               |
| **Rendering Engine**        | Virtual DOM (Varying diffing overhead)     | **No Virtual DOM** (Direct DOM updates)                                             |
| **Audio Meter Performance** | Frequent updates can cause broad rerenders | Localized updates, measured at the display refresh rate                             |
| **Bundler**                 | Webpack 5 (~2.6MB bundle)                  | **Vite**, with build time and bundle size measured in this project                  |
| **State Management**        | UI values closely coupled to API responses | **SSOT Reactive Store** with optimistic updates, debounced sync, and ordered writes |

### Settings Redesign: Decouple Interaction from REST Synchronization

This is a redesign prompted by the verified legacy behavior in Section 1, not merely a recommendation to adopt a reactive store. Pitch/index change handlers mutate shared slot state and start an asynchronous update without awaiting it. The downstream code awaits a REST PUT, then starts a GET to reload the slot list; the displayed value has no independent local draft state. This creates per-change request traffic and makes normal visual updates depend on server synchronization. Failed or out-of-order synchronization is a plausible contributor to the reported unresponsive sliders, not a browser-reproduced root cause. The underlying problem is the coupling of interaction and synchronization, not the use of `await` or React itself.

**Decision: UI interaction must not depend on a REST roundtrip.** Replacing React with Svelte, or adding a store around the same request-per-change handlers, would preserve the underlying design problem. Component handlers update local draft settings synchronously; a separate settings coordinator owns communication, ordering, and recovery.

```text
[Slider / Settings Component]
    | immediate local edit; no REST await
    v
[Reactive Draft Settings] --------> [Render Slider Immediately]
    |
    | latest pending values
    v
[Settings Coordinator: Debounce + Coalesce + Serialize]
    |                             ^
    | REST settings write         | acknowledgement / error
    v                             |
[Python Backend: Confirmed Settings]-+
```

The shared frontend settings model gives components one consistent view, but distinguishes **the user's current draft** from **the backend's confirmed settings**. Server acknowledgements must not overwrite newer local edits or gate slider movement.

- **Interaction**: No REST calls or waits for server completion in slider change handlers. Local feedback remains available while a save is pending or has failed.
- **Synchronization**: Debounce intermediate edits (initial target: 100 ms), coalesce pending changes to their latest values, and serialize settings writes through one coordinator rather than queuing every input event.
- **Final Value**: Flush the latest pending value on interaction completion, including keyboard interaction. If a write is already in flight, send it next rather than starting a concurrent write.
- **Acknowledgements**: Track local edit generations; reconcile server-normalized values only when they correspond to the current edit. A stale acknowledgement cannot replace a newer draft.
- **Recovery**: Show pending/error state and support retry or explicit reload of confirmed settings. A failed save must not silently discard edits or disable the slider.
- **Application**: Keep scalar changes separate from model/profile changes. Apply changes at inference chunk boundaries and avoid recompilation for ordinary scalar updates.
- **Acceptance**: Simulate rapid dragging, slow responses, stale acknowledgements, and failed saves. Slider movement must remain immediate, writes must be bounded/coalesced, and the latest value must reach the backend after successful synchronization. Also verify keyboard completion and model changes during conversion.

---

## 5. Community Translation Assets

VCClient has accumulated translations across **13 languages** (`ar`, `de`, `el`, `en`, `es`, `fr`, `it`, `ja`, `ko`, `la`, `ms`, `ru`, `zh`), created by community contributors over several years.

### Direct Translation Asset Portability

Inspection of `web_front/assets/i18n/*/translation.json` demonstrated that:

- The translation assets are **pure key-value JSON dictionaries** (e.g., `"model_slot_edit": "編集"`).
- Upstream used `react-i18next`, which is merely a thin React adapter around the framework-agnostic **`i18next`** core engine.
- Forge imports the dictionaries through its [Svelte UI state](../frontend/src/lib/ui.svelte.ts) and uses English fallback.
- **Completed asset migration**: All 13 community translation dictionaries and required image/license assets were moved into `frontend/src/` (`frontend/src/lib/i18n/*/translation.json`) before removing `web_front/`.

## Remaining work

See the [implementation roadmap](./implementation-roadmap.md) for sustained streaming validation and evaluation of mixed native/browser routing.
