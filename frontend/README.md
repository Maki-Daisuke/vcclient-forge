# Forge UI preview

Svelte 5 + TypeScript + Vite appearance preview based on the v2.1.4 layout.
Bits UI supplies sliders and accessible dialogs; standard HTML supplies simple
buttons, selects, and checkboxes. All audio, model selection, upload/save, and
device controls are disabled. Dialog navigation, section expansion, themes, and
language selection work locally. Nothing connects to the Python backend or asks
for microphone access.

Run commands from the repository root:

```sh
npm --prefix frontend ci
npm run dev:frontend
npm run check:frontend
npm run build:frontend:preview
```

The dev URL is printed by Vite (normally `http://127.0.0.1:5173`). Standalone output
goes to `frontend/preview-dist`; `npm --prefix frontend run preview` serves it.
`npm run build:frontend` still prepares the legacy Python-served `frontend/dist`.
The preview is not yet selected by the desktop host or portable packages.

Browser checks run against the built preview, cover disabled audio controls,
absence of backend/device access, dialog focus and nested dialogs, themes, and
all 13 languages at a narrow viewport:

```sh
npm --prefix frontend exec -- playwright install chromium
npm run test:frontend
```

To use an installed browser, set `PLAYWRIGHT_CHANNEL` to `msedge` or `chrome`.
For example, in PowerShell: `$env:PLAYWRIGHT_CHANNEL = 'msedge'`.

`src/lib/preview.ts` contains immutable display fixtures, not backend DTOs.
`src/lib/ui.svelte.ts` owns per-app language/theme state through Svelte context
and an i18next instance. It imports the original community dictionaries with
English fallback, interpolation, and Arabic RTL layout. Added preview messages
have Japanese and English translations. Dialog open state belongs to Bits UI;
section expansion belongs to native `details` elements.

When functionality is added, introduce editable draft and confirmed settings
with a coordinator for debounced/coalesced, serialized writes and error/retry
handling. Components must not construct backend configuration payloads or call
REST directly. Keep this appearance milestone distinct from native conversion
and the future WebSocket migration described in `okf/`.
