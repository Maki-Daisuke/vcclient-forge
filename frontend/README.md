# Forge UI

Svelte 5 + TypeScript + Vite UI based on the v2.1.4 layout.
Bits UI supplies sliders and accessible dialogs; standard HTML supplies simple controls.

## Development & Test Commands

Run commands from the repository root:

```sh
npm --prefix frontend ci
npm run dev:frontend
npm run check:frontend
npm run build:frontend:preview
npm run test:frontend
```

Vite forwards `/api` (HTTP and WebSockets) to `http://127.0.0.1:18888` in dev and preview (`frontend/vite.config.ts`). Override the target with `VCCLIENT_BACKEND_URL`:

```powershell
$env:VCCLIENT_BACKEND_URL = 'http://127.0.0.1:18889'
npm run dev:frontend
```

`npm run build:frontend` builds the production SPA into `frontend/dist`, served by FastAPI for desktop and portable packages. Standalone preview builds go to `frontend/preview-dist`.

Playwright browser checks (`npm run test:frontend`, or `PLAYWRIGHT_CHANNEL=msedge`) mock all `/api/*` HTTP requests and WebSocket connections via `frontend/tests/` fixtures without opening native audio hardware.

## Backend API Integration

- **Models (`src/lib/catalog.svelte.ts`, `src/lib/model-upload.ts`)**: Reads and mutates models by NanoID (`GET /api/models`, `POST /api/models`, `PUT/DELETE /api/models/{id}`, `PUT/DELETE /api/models/{id}/icon`, `PUT /api/models/order`), displaying portraits via `/api/models/{id}/icon?v={iconRevision}`. ZIP drag-and-drop extracts model/index files in the browser before multipart upload.
- **Settings & Session (`src/lib/session.svelte.ts`, `src/lib/api.ts`)**: Loads persisted defaults from `GET /api/settings`, runtime state from `GET /api/session`, and hardware lists from `GET /api/devices/audio` (`POST /api/devices/audio/reload`) and `GET /api/devices/compute`.
- **Start / Stop & Live Controls**: `PUT /api/session` starts conversion (polling `/api/session` through `starting -> running`) or applies live DSP/pitch/index/recording updates while running; `DELETE /api/session` stops conversion and finalizes any active recording. Live slider writes are throttled at 100 ms and serialized per coordinator queue.
- **Client Mode Audio (`src/lib/client-audio.svelte.ts`)**: Captures browser microphone input via Web Audio `AudioWorklet` and streams `<f4` mono PCM over `WS /api/ws/audio`. Reconnects automatically on page reload if a Client Mode session is active (`4001 superseded` releases local capture without stopping the backend session).
- **Telemetry, Recordings & Logs**: Server Mode meters subscribe to `WS /api/ws/status`; Client Mode meters sample Web Audio `AnalyserNode`s. Finished recordings download from `/api/recordings/latest` (`output.wav`); log viewer polls `/api/logs`.
- **I18n & Preferences (`src/lib/ui.svelte.ts`)**: Bundles 13 community translation dictionaries, theme selection, browser audio processing toggles, and accordion state in browser `localStorage` with safe fallbacks when storage is unavailable.
