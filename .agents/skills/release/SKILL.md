---
name: release
description: >-
  Release checklist and workflow for VCClient Forge. Use whenever the user asks
  to prepare a release, check release readiness, bump version numbers, tag a
  v2.0.78-forge.* release, draft release notes, or publish GitHub Releases.
---

# VCClient Forge Release Workflow

Follow this runbook sequentially when preparing or publishing a VCClient Forge release. Never run `git add`, `git commit`, `git tag`, `git push`, or publish a GitHub Release without explicit user approval.

## 1. Audit Readiness Since Last Release

1. Find the previous Forge tag and inspect commits since then:
   ```sh
   git tag -l "v*" --sort=-v:refname
   git log <prev-tag>..HEAD --oneline
   git status --short
   ```
2. Verify user-facing docs and launcher files match changes since `<prev-tag>`:
   - Bundled package docs: `docs/README.txt`, `docs/README_ja.txt`, `README.md`, `LICENSE`
   - Online/troubleshooting & developer docs: `docs/en/troubleshooting.md`, `README_dev.md`, `frontend/README.md`, `desktop/README.md`, `okf/implementation-roadmap.md`
   - Entry-point launchers copied by `scripts/build_package.py`: `start.bat`, `start.sh`, `MacStart.command`
3. Note any environment/requirement changes (CUDA driver minimums, OS dependencies, UI defaults) that belong in release notes.

## 2. Bump Version Across All Manifests

VCClient Forge versions follow `2.0.78-forge.<major>.<minor>.<patch>` with matching Git tags `v2.0.78-forge.<major>.<minor>.<patch>`.

1. Audit compatibility impact before confirming `<version>` (even if the user proposed one): check whether commits since `<prev-tag>` introduce irreversible data/layout changes (e.g., `model_dir` or `settings` incompatible with downgrades), major API overhauls, or significant new features, and confirm `<minor>` vs `<patch>` before editing manifests or tagging.
2. Confirm `v<version>` does not already exist (`git tag -l "v<version>"`).
3. Update all **4** version manifests to the exact `<version>` (no leading `v`):
   - `package.json`: `"version"` (also read at runtime by `backend/vcclient/const.py`, Vite `__APP_VERSION__` in `frontend/vite.config.ts`, and `scripts/build_package.py`)
   - `package-lock.json`: root `"version"` and `"packages[""].version"` (e.g. `npm version <version> --no-git-tag-version`)
   - `desktop/build/config.yml`: `info.version`
   - `desktop/build/windows/info.json`: `info["0409"].ProductVersion` (keep `fixed.file_version` as `"2.0.78.0"`)
4. Do **not** bump `backend/pyproject.toml` (`-forge.*` fails PEP 440 parsing, updates `backend/uv.lock`, and is unused at runtime/packaging), `frontend/package.json`, or `desktop/frontend/package.json`.
5. Confirm no old Forge version string remains in the 4 manifests:
   ```sh
   rg -F "<prev-version>" package.json package-lock.json desktop/build/config.yml desktop/build/windows/info.json
   ```

## 3. Run Local Validation Gates

Run checks from the repository root (report any environment-specific blocker honestly rather than treating skipped checks as passes):

```sh
npm run format:check
npm run lint
gofmt -l desktop
npm run check:frontend
npm run build:frontend
npm run test:desktop
npm run test:backend
npm run test:frontend
```

- `npm run build:frontend` ensures `frontend/dist` embeds the new `__APP_VERSION__`.
- `npm run test:frontend` uses Playwright (`PLAYWRIGHT_CHANNEL=msedge` or `chrome` if Chromium is not installed).
- *(Optional local package check)*: Run `npm run build -- --edition <standard|cuda>` and `npm run package -- --edition <standard|cuda> --output-dir <new_dir>` to verify the `< 2 GiB` archive cap (`scripts/build_package.py`) and `main(.exe) --help` without reusing an existing output directory.

## 4. Commit, Push & Confirm CI

1. Request explicit user approval, then stage only the release files (avoid `git add -A` so untracked local artifacts are excluded):
   ```sh
   git add package.json package-lock.json desktop/build/config.yml desktop/build/windows/info.json
   git commit -m "chore(release): bump version to <version>"
   ```
   (`.githooks/pre-commit` enforces `npm run format:check` and `gofmt -l desktop`.)
2. After user approval to push the branch (`git push origin forge`), verify `.github/workflows/ci.yml` passes across `ubuntu-24.04`, `ubuntu-26.04`, `windows-latest`, `macos-latest`, and `self-hosted-linux-arm64`.
3. *(Optional pre-tag dry run)*: Trigger `.github/workflows/release.yml` via `workflow_dispatch` on the branch (`gh workflow run release.yml --ref forge -R Maki-Daisuke/vcclient-forge`) to validate all 7 builds without publishing a GitHub Release. Always pass `-R Maki-Daisuke/vcclient-forge` to `gh` commands because the default repository context can point to upstream `w-okada/voice-changer`.

## 5. Tag, Trigger Release Build & Draft Release Notes

After CI passes and the user explicitly approves tagging and pushing:

```sh
git tag v<version>
git push origin v<version>
```

Pushing a `v*` tag triggers `.github/workflows/release.yml`, which builds, runs `main(.exe) --help` smoke checks, uploads 7-day workflow artifacts, and creates the GitHub Release via `softprops/action-gh-release@v3` with 7 `.7z` packages:

- `win-x64-standard`, `win-x64-cuda`
- `linux-x64-standard`, `linux-x64-cuda`
- `linux-arm64-standard`, `linux-arm64-cuda`
- `mac-arm64-standard`

**While the release workflow runs**, draft the release notes and present them to the user for review and wordsmithing so copy edits happen concurrently with the build:

- Ground the draft in `git log <prev-tag>..v<version>` and verified specs in `README.md` / `docs/README*.txt` (supported hardware, CUDA 13.x / driver R580+ notice, upgrade/migration steps, and known caveats) without unverified claims.
- Order Highlights by user-visible impact (lead with the headline user-facing feature rather than internal refactors) and group capabilities enabled by the same underlying change together instead of creating fragmented sections.
- Describe routine bug fixes by user-visible outcome (skip low-level internal implementation details), while explicitly calling out runtime prerequisites (e.g., drivers/system loaders), OS-specific root causes users encounter, and one-way/irreversible data migrations with backup guidance.
- Include the final changelog link (`.../compare/<prev-tag>...v<version>`).

## 6. Post-Build Verification & Finalize Release

1. Confirm all 7 matrix jobs in `.github/workflows/release.yml` succeed and all 7 `.7z` archives appear under Release `v<version>`.
2. After the workflow succeeds and the user approves the finalized release notes, update the GitHub Release body (e.g., via `gh release edit v<version> -R Maki-Daisuke/vcclient-forge --notes-file <path>`).
