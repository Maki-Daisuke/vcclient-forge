# Forge UI preview

Svelte 5 + TypeScript + Vite development UI based on the v2.1.4 layout.
Bits UI supplies sliders and accessible dialogs; standard HTML supplies simple
buttons, selects, and checkboxes. The model list, configured selection, metadata,
portraits, and current settings are read from the existing backend GET APIs.
Server Mode now supports model/device selection while stopped, start/stop, and
live input/output gain adjustment through existing PUT/POST APIs. Upload, model
editing, Client Mode audio, and other settings controls remain disabled.
Audio runs on the backend's native devices; the browser does not capture audio.

Run commands from the repository root:

```sh
npm --prefix frontend ci
npm run dev:frontend
npm run check:frontend
npm run build:frontend:preview
```

Run `npm start` in a separate terminal to start the Python backend for real model
information (normal backend startup may download required model assets).
Vite forwards `/api` and `/model_dir` to `http://127.0.0.1:18888` in both dev and
preview. To use another backend, set `VCCLIENT_BACKEND_URL` before starting Vite:

```powershell
$env:VCCLIENT_BACKEND_URL = 'http://127.0.0.1:18889'
npm run dev:frontend
```

The UI reads the model catalog at mount and on **Reload**; it does not poll the
catalog or subscribe to changes made by other clients. A stopped backend displays an error
instead of sample models. Each load has an 8-second timeout and publishes the
slot list and current selection together only after both requests succeed.
This is not an atomic server snapshot if another client changes settings between
the two GET requests. Missing selected IDs are shown explicitly, never replaced
with the first model. Empty slots are filtered; pending/broken slots are labeled.
Slot numbers displayed to users are one-based; backend IDs remain zero-based.

The dev URL is printed by Vite (normally `http://127.0.0.1:5173`). Standalone output
goes to `frontend/preview-dist`; `npm --prefix frontend run preview` serves it.
`npm run build:frontend` still prepares the legacy Python-served `frontend/dist`.
The preview is not yet selected by the desktop host or portable packages.

Browser checks run against the built preview with intercepted API responses;
they do not require the Python backend or open native audio devices. They cover startup GETs, sparse
slot IDs, metadata/selection, loading and error recovery, invalid responses,
timeout, portrait fallback, native selection/start/stop, gain coalescing, full
configuration preservation, failed writes and retries, no browser device access, dialog
focus/nesting, themes, and all 13 languages at a narrow viewport:

```sh
npm --prefix frontend exec -- playwright install chromium
npm run test:frontend
```

To use an installed browser, set `PLAYWRIGHT_CHANNEL` to `msedge` or `chrome`.
For example, in PowerShell: `$env:PLAYWRIGHT_CHANNEL = 'msedge'`.

`src/lib/api.ts` owns REST requests, validates the fields used by the UI, and maps
backend responses and icon paths to display types in `src/lib/catalog.ts` and
`src/lib/settings.ts`.
It reads `/api/slot-manager/slots`, `/api/configuration-manager/configuration`,
and `/api/audio-device-manager/{input_devices,output_devices}`. Runtime state and
start/stop use `/api/local-voice-changer-interface/information` (GET) and
`/api/local-voice-changer-interface/operation/{start,stop}` (POST).
`src/lib/catalog.svelte.ts` owns per-app loading/error/ready state, cancellation,
timeout, retry, and selection by ID. Components render this state and call
`reload()` rather than fetching or constructing backend DTOs. Failed refreshes
clear the previous data so it is not mistaken for current information.

Configuration and model settings are published together using the existing
catalog load, with no extra API calls. The UI displays input/output/monitor
gains, input mode, configured audio devices/GPU IDs and device sample rates, WASAPI
exclusive mode, filters and cutoffs, noise gate threshold, extra context, and
analysis switches/intervals. The current model supplies pitch, index ratio,
pitch estimator, embedder, and chunk length. Native device lists are loaded
alongside the catalog, with independent loading/error state. Configured IDs are
matched to device names and hosts; the monitor uses the output list. Missing IDs
and unavailable lists retain the configured ID with an explanatory label.
Device failures do not hide successfully loaded settings/models. Reload refreshes
both lists without `reload=true`, avoiding PortAudio reinitialization. These are
native backend settings even when the configured input mode is Client Mode;
browser devices are not enumerated.

Unavailable fields display `—`; unknown checkbox values use an indeterminate
state. Formant and browser-only preferences are not provided by these GETs and
are not populated with guessed defaults. Unconnected controls remain disabled. Reload
refreshes both the catalog and settings, and failed loads clear previous values.

`src/lib/ui.svelte.ts` owns per-app language/theme state through Svelte context
and an i18next instance. It imports the original community dictionaries with
English fallback, interpolation, and Arabic RTL layout. Added preview messages
have Japanese and English translations. Dialog open state belongs to Bits UI;
section expansion belongs to native `details` elements.

`src/lib/session.svelte.ts` owns editable drafts, confirmed values, gain throttling,
serialized writes and audio operations, errors, explicit retry/discard, and runtime
status polling every two seconds. Each update fetches the full current configuration,
merges only edited fields, PUTs the full payload, then reads back to confirm. A silent
model rollback is treated as failure. The UI never constructs backend DTOs.
Gain drags send at most once per 100 ms while requests are available; pointer release,
key release, and focus loss flush the latest value. A slow request retains only the
latest pending edits. Failed saves retain drafts and require explicit retry or discard.
Reload/start are blocked while edits are pending; Stop waits for an in-flight write.

To try native audio, start the backend, select a model card, open Settings, switch
to Server Mode if necessary, and choose input/output devices (monitor is optional).
Device changes reset that device's sample rate to Auto. Wait for settings to be
confirmed, then press Start and adjust input/output volume while speaking. A disabled
Start button shows the specific missing prerequisite below it, such as selecting
a model card or replacing an unavailable device. Stop
before changing devices or models. Monitor volume currently follows output gain
in the backend; the independent monitor gain setting is not applied by its native
callback, so that slider shows linked output gain and remains disabled.

The backend is unchanged. Full GET/PUT updates have no revision/atomic-merge
guarantee against another client; use one controlling UI. Requests time out after
30 seconds for writes/operations, with no automatic retry: a lost response does
not prove the server did not apply a change. Runtime GET reports the native enable
flag, not stream health or audible output. Live meters remain unavailable.
Automated tests use mocked APIs (41 browser checks passed). The user confirmed
native audio playback from the new UI on 2026-11-06; subjective gain-adjustment
latency and longer sessions still need validation. Each configuration PUT still
writes the backend settings file. This does not complete the production cutover
or future WebSocket migration described in `okf/`.
