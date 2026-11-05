# Reused upstream assets

This preview reuses the 13 community translation dictionaries and the placeholder
`human.png` from `web_front/ui/2.1.4/assets`, distributed with
[w-okada/voice-changer](https://github.com/w-okada/voice-changer).

Copyright (c) 2025 Wataru Okada. Preserve the original notices and the repository's
MIT [LICENSE](../LICENSE) when redistributing these assets. The tracked upstream
asset directory remains the source of these files during the preview phase;
Vite bundles the imported assets into the standalone preview.

The new Svelte components are written independently, using the upstream UI as a
layout reference. Upstream JavaScript bundles and their dependency license lists
are not part of the new preview build. New dependencies retain their own licenses
in their installed npm packages.
