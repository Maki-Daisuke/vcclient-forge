# Forge UI preview

Svelte 5 + TypeScript + Vite development UI based on the v2.1.4 layout.
Bits UI supplies sliders and accessible dialogs; standard HTML supplies simple
buttons, selects, and checkboxes. The model list, configured selection, metadata,
and portraits are read from the backend. Loading, empty, failure, and retry states
are supported. Audio, model selection, upload/save, and device controls are still
disabled. Dialog navigation, section expansion, themes, and language selection
work locally; there is no microphone access or audio connection.

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

The UI reads the model catalog at mount and on **Reload**; it does not poll or
subscribe to changes made by other clients. A stopped backend displays an error
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
they do not require the Python backend. They cover read-only requests, sparse
slot IDs, metadata/selection, loading and error recovery, invalid responses,
timeout, portrait fallback, disabled audio controls, no device access, dialog
focus/nesting, themes, and all 13 languages at a narrow viewport:

```sh
npm --prefix frontend exec -- playwright install chromium
npm run test:frontend
```

To use an installed browser, set `PLAYWRIGHT_CHANNEL` to `msedge` or `chrome`.
For example, in PowerShell: `$env:PLAYWRIGHT_CHANNEL = 'msedge'`.

`src/lib/api.ts` owns GET requests, validates the fields used by the UI, and maps
backend responses and icon paths to the display types in `src/lib/catalog.ts`.
It reads only `/api/slot-manager/slots` and
`/api/configuration-manager/configuration`; no settings writes are implemented.
`src/lib/catalog.svelte.ts` owns per-app loading/error/ready state, cancellation,
timeout, retry, and selection by ID. Components render this state and call
`reload()` rather than fetching or constructing backend DTOs. Failed refreshes
clear the previous data so it is not mistaken for current information.

`src/lib/preview.ts` contains only immutable audio-control display fixtures.
`src/lib/ui.svelte.ts` owns per-app language/theme state through Svelte context
and an i18next instance. It imports the original community dictionaries with
English fallback, interpolation, and Arabic RTL layout. Added preview messages
have Japanese and English translations. Dialog open state belongs to Bits UI;
section expansion belongs to native `details` elements.

When functionality is added, introduce editable draft and confirmed settings
with a coordinator for debounced/coalesced, serialized writes and error/retry
handling. Components must not construct backend configuration payloads or call
REST directly. Keep this read-only milestone distinct from native conversion
and the future WebSocket migration described in `okf/`.
