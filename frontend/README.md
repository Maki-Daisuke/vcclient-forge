# Forge UI preview

Svelte 5 + TypeScript + Vite development UI based on the v2.1.4 layout.
Bits UI supplies sliders and accessible dialogs; standard HTML supplies simple
buttons, selects, and checkboxes. The model list, configured selection, metadata,
portraits, and current settings are read from the existing backend GET APIs.
Server Mode now supports model/device selection while stopped, start/stop, and
live passthrough, input/output gain, pitch, index, noise-gate, and filter adjustment through existing PUT/POST APIs.
WASAPI exclusive mode is unavailable in the new UI. Before starting Server Mode,
the UI disables the saved exclusive-mode setting using the existing configuration API.
The audio button switches between Start and Stop based on the confirmed backend state.
If the audio state cannot be read, Stop remains available.
The Start/Stop, Passthrough, and Record buttons appear above the audio meters.
Recording can be armed before starting audio in either mode, including with passthrough.
Starting audio starts recording; stopping audio saves and downloads the take, then
returns to the armed state. The Record button can also start or stop recording
during audio. Arming is local to the page and is cleared on a browser reload.
In Server Mode recording starts after audio start is confirmed, so its initial audio may not
be included. Client Mode arms backend recording before opening the microphone.
After stopping, a nonempty output WAV is downloaded; an empty recording shows a notice.
The backend stores input.wav, output.wav, and optionally monitor.wav at fixed paths,
overwriting prior recordings. Audio is held in memory until recording stops.
Passthrough may be toggled while recording. Failed recording saves are reported;
the backend's recording state can become inconsistent after a save error, so a
retry is not guaranteed to recover audio. Client Mode recording in this UI has not yet been verified with real audio.
Client Mode captures a browser microphone and streams float32 audio through the
existing Socket.IO API. Its output is played by Web Audio. The browser requests
microphone permission on Start or when loading the device list; output selection
requires browser support for AudioContext.setSinkId. The browser's audio context
uses the backend input sample rate, and Web Audio resamples the returned output as
needed. Client Mode supports passthrough and recording through the existing configuration API.
The recording is backend output, before the browser's output gain. Client Mode
also displays the backend input buffer and conversion time when process analysis and
performance monitoring are enabled. Client Mode start/stop uses the existing native stop endpoint to
stop the shared conversion worker. The backend retains a partial input chunk across
worker restarts, so a short fragment can persist across sessions. The user confirmed
hearing converted audio in Client Mode; device combinations and recovery remain to
be validated.
Client Mode input and output gains are applied locally with Web Audio and saved in
browser local storage separately from Server Mode gains. When browser automatic gain
control is enabled, the manual input gain is disabled and bypassed. In Client Mode,
Web Audio analyser nodes measure input and output RMS after the respective gains.
The output buffer graph shows scheduled audio remaining on the AudioContext timeline,
not the buffers in the OS or audio device. The UI samples these values every 100 ms
and clears them when client audio stops.
While Server Mode audio is active and backend input/output analysis is enabled,
the UI subscribes to the existing Socket.IO `/test` namespace and displays the
input/output RMS levels. The meter bars use a logarithmic -60 to 0 dBFS scale;
fixed dBFS ticks indicate the scale. The subscription closes on stop and clears stale or
disconnected values. The buffer graph and labels consume the existing output and
process status events independently, convert sample counts to seconds using
current backend sample rates, and retain at most 100 points per stream. The
graph clears on stop, disconnect, stale data, or the Clear button. Input buffer
requires backend process analysis and performance monitoring to be enabled;
output buffer requires input/output analysis. The UI displays the latest sampled chunk
conversion time in seconds, independently of buffer data. It requires process
analysis and performance monitoring and clears when stale or stopped. Gate-closed
or passthrough chunks can produce low values. A live backend notification was
observed in the UI.
No backend notification settings or audio callbacks are changed.
The UI was also checked against a running backend during audio conversion; the
displayed values and bars updated, and the user confirmed the meters displayed.
Callback overhead has not been measured. Buffer display is covered by mocked
browser events; both values and graph lines were also observed in the UI against
a live backend during conversion.
The model list contains the selected model's portrait, details, and voice controls.
Audio devices, volume, noise suppression, and inference controls are grouped into
independent expandable sections. Server Mode and Client Mode can be selected while
audio is stopped. Device sample-rate controls are not displayed; existing saved
rates are retained until a different device is selected, which resets that rate to Auto.
When the backend reports a Windows audio host (such as WASAPI, MME, or Windows
DirectSound), device selectors initially show WASAPI devices. “Show legacy devices”
reveals all hosts. A selected hidden device remains visible as a disabled option
until the filter is cleared, without changing the saved selection. The existing API
does not report the backend OS; when its audio hosts do not identify Windows, all
devices are displayed.
The device reload button rescans the backend while audio is stopped. If a selected
device's index no longer has the same name and host after the rescan, the UI asks
for a new selection before starting; names and host APIs cannot distinguish devices
with identical metadata. A failed rescan likewise requires selection confirmation.
The preferred inference device uses the backend compute-device list and can be changed
while audio is stopped in either mode. The full configuration is read and preserved when
saving. The UI reads the configuration back and, when a model is selected, checks
the reported pipeline device ID. This does not verify the actual execution providers. Device
list failures do not prevent other controls from loading; Reload retries the list.
The user confirmed device switching with the live backend; conversion after switching
has not yet been confirmed.
Chunk, extra frame, and crossfade durations use logarithmic sliders with
display ranges of 0.05–5, 0.01–10, and 0.01–0.15 seconds respectively; crossfade
also allows zero. Values
outside these display ranges remain visible and are indicated separately; these
ranges do not enforce backend limits.
All three can be adjusted while audio is stopped in either mode. The client shows a preview
while dragging and saves on release; chunk belongs to the selected model, while
extra frame and crossfade are configuration settings. The backend limits the
effective crossfade to the chunk duration. Client Mode changes have not yet been verified with real audio.
Each filter's cutoff slider is available only when that filter is enabled.
Sections start closed, and their open/closed state is stored in the browser's
local storage. It is separate for each browser or webview and origin; if storage
is unavailable or invalid, sections start closed.

While native audio is stopped, the upload dialog accepts an RVC `.pth` or `.onnx`
model and an optional `.index` file. It also accepts a ZIP selected by file picker
or drag and drop. ZIP contents are inspected in the browser; if several models are
present the user selects one, and an optional index can be selected separately.
Password-protected archives are not supported. The selected files are decompressed
in browser memory before upload, so large archives require sufficient memory.
Files are uploaded in 4 MiB chunks using unique
temporary names and registered in an automatically selected empty slot. The
backend converts `.pth` to ONNX during import. The list is refreshed after success.
Import may take time; other settings and audio start are disabled while it runs.
If the registration response is lost, reload and inspect the list before retrying.
An interrupted upload can leave temporary files because the existing API has no
cleanup operation. Browser tests mock uploads; the user confirmed an upload to the
real backend, but did not specify the model format or whether an index was included.
The user confirmed importing a model from a ZIP and using it for voice conversion;
the ZIP's model format and index presence were not specified.

While native audio is stopped, the selected model can be deleted from its edit
dialog after confirmation. Deletion clears the selection and compacts the
remaining model directories. The model selection screen can reorder cards by
dragging; Apply writes the new order. Reload and upload are hidden while
reordering, which is currently restricted to stopped audio. A backend journal recovers interrupted
directory moves on the next startup. Browser tests use a mocked backend.
Do not use multiple tabs to operate the application at the same time.

While audio is stopped, the edit dialog can save the selected model's name and
icon using the existing slot and uploader APIs. Supported icons are PNG, JPEG,
WebP, GIF, AVIF, and BMP. Name and icon updates are separate operations: a
failure can leave one change applied, so the UI retains the draft and refreshes
the model when possible. Existing uploader APIs can leave temporary files after
interrupted uploads, and replacing an icon does not remove the previous file.
Browser tests mock the APIs. The user confirmed that the display changed after
editing; the specific fields and persistence after restart were not specified.

Run commands from the repository root:

```sh
npm --prefix frontend ci
npm run dev:frontend
npm run check:frontend
npm run build:frontend:preview
```

Run `npm start` in a separate terminal to start the Python backend for real model
information (normal backend startup may download required model assets).
Vite forwards `/api`, `/model_dir`, and `/output.wav` to `http://127.0.0.1:18888` in both dev and
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
timeout, portrait fallback, native selection/start/stop, gain/model coalescing, full
configuration/slot preservation, failed writes and retries, no browser device access, dialog
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
gains, input mode, configured audio devices/GPU IDs, filters and cutoffs, noise gate threshold, extra context, and
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
state. Browser-only preferences are not provided by these GETs and
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
Gain and noise-gate drags send at most once per 100 ms while requests are available; pointer release,
key release, and focus loss flush the latest value. A slow request retains only the
latest pending edits. Failed saves retain drafts and require explicit retry or discard.
Reload/start are blocked while edits are pending; Stop waits for an in-flight write.

The Passthrough button toggles the backend's `pass_through` configuration while
either mode is selected, including during audio. Its pressed state reflects
the current draft or last confirmed value; it is disabled if that value is unknown.
It shares the serialized configuration queue, readback, and retry/discard behavior.
The backend resets passthrough on restart and does not persist it in the settings
file. Changes by other clients are visible after reload or a subsequent confirmed
configuration write. Reading this field from the real backend was verified; browser
write tests mock the API, and audible passthrough has not been verified.

WASAPI exclusive mode is not shown as a setting. If a saved configuration has
exclusive mode enabled, the UI reports this and disables it before starting native
audio. Audio already running is not stopped or reconfigured. The existing API and
other clients may still enable exclusive mode. The stopped-state check is not atomic
with other clients.

Pitch and index ratio use GET/PUT/GET on `/api/slot-manager/slots/{id}`, preserving
the complete latest slot payload and validating that the response ID matches the
target. Model drafts are tied to a slot ID and share the gain coordinator's 100 ms
throttle, completion flush, serialization, and retry/discard behavior. When both
have pending edits, configuration and model writes alternate. Confirmed slot data
updates only that model in the catalog; no full model-list refresh is needed after
each edit. Pitch requires an f0 model; index adjustment requires a configured
index file. Unsupported controls remain disabled with an explanation. The backend
continues saving these settings to `model_dir/{id}/params.json`; new listening
validation for pitch/index adjustment is still pending. The real backend's slot
GET and displayed values were checked using a browser-only simulated model selection;
live model-setting PUTs and audible changes were not part of that check.

For an f0 model, RMVPE/FCPE can be changed in Server or Client Mode while audio is stopped.
The client checks the stopped state before the slot update, then confirms both the
saved slot and the active pipeline estimator. A failed update can still have saved
the slot before pipeline initialization failed. Retrying may not repair that state;
reselecting the model or restarting the backend may be needed.
The stopped-state check is not atomic with changes from other clients. Browser tests
use mocked APIs; real-backend switching and audible behavior have not been verified.

The noise-gate slider in Noise Suppression ranges from −100 to 0 dB in 1 dB steps.
The enable checkbox disables the gate by setting −100 dB; re-enabling restores the
last enabled value in this page, or −60 dB if none is available. Existing settings
below −100 dB appear disabled at −100 dB without being rewritten on load. The native
pipeline disables the gate at −100 dB or below. It uses the same
configuration write queue as gain, including throttling and retry/discard. The
displayed value has been checked against the real backend via GET. Configuration
writes have been covered by mocked browser requests; real-backend PUT and audible
noise-gate behavior have not yet been verified. The noise gate can be adjusted in
both Server and Client Mode, including while conversion is running.
Client Mode supports browser echo cancellation, noise suppression, and automatic
gain control. They are selected while audio is stopped and saved in browser local
storage; browser processing support varies by device. Requested browser processing
must be supported or starting audio fails. The user confirmed echo cancellation,
noise suppression, and automatic gain control with a real microphone.

High/low-pass switches and cutoffs are editable in Server and Client Mode when a usable model
is selected. Before a filter
update, the client reads the current full configuration and voice-changer
information, then checks that rates are available and both cutoffs are positive
and ordered below the effective low-pass limit. Invalid or unknown combinations
or model mismatches are retained as drafts with an error and are not sent. If
audio is not initialized, discard the edits and start audio before trying again.
Valid edits use the same
serialized full-configuration PUT and readback as the other controls. This is a
client-side check, not an atomic guarantee against changes by another client.
Real-backend GET display has been checked; real PUT and audible filter changes
remain to be tested. Passthrough bypasses both filters and the noise gate. Backend
APIs are unchanged.

To try native audio, start the backend, select a model card, open Audio Devices, switch
to Server Mode if necessary, and choose input/output devices (monitor is optional).
Device changes reset that device's sample rate to Auto. Wait for settings to be
confirmed, then press Start and adjust input/output volume while speaking. A disabled
Start button shows the specific missing prerequisite below it, such as selecting
a model card or replacing an unavailable device. Stop
before changing devices or models. Monitor volume currently follows output gain
in the backend; the independent monitor gain setting is not applied by its native
callback, so output and monitor share the single output-volume control.

The backend is unchanged. Full GET/PUT updates have no revision/atomic-merge
guarantee against another client; use one controlling UI. Requests time out after
30 seconds for writes/operations, with no automatic retry: a lost response does
not prove the server did not apply a change. Runtime GET reports the native enable
flag, not stream health or audible output. Live meters remain unavailable.
Automated tests use mocked APIs. The user confirmed
native audio playback from the new UI on 2026-11-06; subjective gain-adjustment
latency and longer sessions still need validation. Each configuration PUT still
writes the backend settings file. This does not complete the production cutover
or future WebSocket migration described in `okf/`.
