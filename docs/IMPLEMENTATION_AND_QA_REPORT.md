# Implementation and QA Report

## 1. Summary of Findings & Fixes

### 1.1. Avatar Catalog Cleanup (Block 11)
- **Root cause:** `kryonyx/avatars.json` contained 490 entries, including 251 entries across `Music artists` (90), `YouTube and creators` (86), and `Streamers` (75), plus `collection-249-одноклассники` (1) and 5 Poppy Playtime chapters (`collection-021-poppy-playtime`, `collection-525`–`528`), along with their PNG, WebP thumbnail, SVG, and notice files.
- **Fix:** Removed all 257 target entries from `kryonyx/avatars.json` (leaving 233 entries across 11 categories), deleted all 771 corresponding image files and 257 notice files, updated collection labels in `kryonyx/web/js/experience-v8.js`, and verified safe fallback to `DEFAULT_AVATAR` (`kryonyx-core`) in `kryonyx/avatars.py`.
- **Manifest & Test:** `docs/REMOVED_ASSETS_MANIFEST.md`, `tests/test_avatar_cleanup.py`.

### 1.2. English-Only Installer, Legal Alignment & Documentation Cleanup (Blocks 3 & 12)
- **Fix:** Removed Russian language and `legal_ru` branches from `build/installer.iss`, `installer/bootstrap.py`, and `installer/wizard.html`; removed `docs/ru` from `build/KryonyxMusic.spec`; rewrote `README.md` and `START_HERE.txt` in English; removed `docs/ru/`, `docs/RELEASE_*.md`, `docs/KRYO_*.md`, `docs/VERIFICATION_*.json`, `docs/AI_NCNN_MIGRATION_PLAN.md`, and `docs/OFFLINE_TRANSLATION.md`; removed `[Русский](docs/ru/...)` links from root legal docs; updated `tools/collect_licenses.py` to separate `runtime` vs `build-only` Python packages.
- **Player Russian UI:** Preserved in `kryonyx/web/js/i18n.js` and `PACKS.ru`.
- **Audit:** `docs/LICENSE_AUDIT.md`.

### 1.3. Cover Card Geometry (Block 4)
- **Root cause:** `<button class="card">` in `kryonyx/web/css/app.css` lacked flex column top-alignment (`display: flex; flex-direction: column; align-items: stretch; justify-content: flex-start`), causing stretched cards in `ui-v31` grid rows to vertically center `.art` differently from neighbors; `kryonyx/web/css/home-v31.css` also applied `transform: translateY(-3px)` on `.card:hover`.
- **Fix:** Enforced flex column top-alignment on `.card`, `width: 100%; flex: 0 0 auto; aspect-ratio: 1 / 1` on `.card .art`, and removed `translateY(-3px)` on `.card:hover`.

### 1.4. Next-Track Prefetch & Instant Transition (Block 5)
- **Root cause:** Toggling `shuffle` or `repeat` in `kryonyx/web/js/app.js` and queue edits in `kryonyx/web/js/player.js` (`addNext`, `addLast`, `removeAt`, `move`, `reshuffle`, `unshuffle`) did not consistently bump `queueRevision` and trigger `prefetchNext()`; `Player` also lacked diagnostic prefetch states (`idle`, `queued`, `resolving`, `downloading`, `ready`, `cancelled`, `failed`, `stale`) and had a microtask race where an aborted request settling after a newer failed request could overwrite `prefetchState` to `stale`. `tests/test_prefetch_v30.cjs` also miscounted `cancel=1` requests as track loads.
- **Fix:** Added `queueRevision++` + `prefetchNext()` calls across queue/shuffle/repeat mutations, added `Player.setPrefetchState()` with race-safe `key` guard, and updated `tests/test_prefetch_v30.cjs` to separate track-load requests from `cancel=1` requests.

### 1.5. Recommendations Refresh Button (Critical Block)
- **Root cause:**
  1. `recommend.invalidate()` cleared in-memory `_cache` but left `home_rows.json` on disk active, so `cached_rows()` still returned stale disk rows.
  2. `server.py:api_recommend` read `saved = recommend.cached_rows()` *before* calling `recommend.invalidate()`, returning old cached rows on `fresh=1`.
  3. `recommend.build_rows()` did not rotate liked seeds by `_generation` or accept `exclude_ids` to deprioritize already-shown tracks on manual refresh.
  4. `home-v31.js` cleared `this.busy = false` before `poll33()` finished and did not pass `exclude` IDs or preserve scroll position cleanly.
- **Fix:** Added `_disk_invalidated` and `current_generation()` in `kryonyx/recommend.py`, rotated liked seeds by `_generation` and deprioritized `exclude_ids` with small-library fallback, reordered `api_recommend` in `kryonyx/server.py`, and updated `kryonyx/web/js/home-v31.js` and `kryonyx/web/js/app.js` (`#bRefresh`) for atomic updates, scroll preservation, and `AbortController` race protection.
- **Tests:** `tests/test_recommend_refresh.py`, `tests/browser_e2e_kryo.py`.

### 1.6. 12-Language UI Localization (Block 7)
- **Root cause:** 158 keys were missing across non-English `PACKS` (`ru`: 3, `uk`: 83, `es/pt/de/fr/it/tr/pl`: 154, `zh/ja`: 155).
- **Fix:** Added `kryonyx/web/js/i18n-v86.js` (loaded after `i18n-v73.js` in `kryonyx/web/index.html`) covering all missing keys + `Updating in background…` across all 11 non-English languages.
- **Audit & Test:** `docs/LOCALIZATION_AUDIT.md`, `tests/test_i18n_coverage.cjs` (`I18N_COVERAGE_PASS languages=12 keys=3099`).

### 1.7. Visualizer Removal, Karaoke Controls, Translation & Timing Editor (Blocks 6, 8, 9)
- **Visualizer Removal:** Replaced `viz.js` / `visualizer-v32.js` in `kryonyx/web/index.html` with the no-render `visualizer-removed-v52.js` compatibility facade, removed visualizer CSS/settings/mixer controls and `'viz'` mode options (`app.js`, `repair-v33.js`, `experience-v9.js`), and guarded `scene-v46.js` and `performance-v47.js`.
- **Top-Right Karaoke Bar & Separate Queue:** Removed the eye chrome-hide icon (`#sceneRestore30`, `#albumRestore78`, `#nCtl`); moved Lyrics Translation (`#sceneTranslate87` with distinct `#i-translate` icon), Timing & Karaoke (`#karaokeMenuButton45` with `#i-clock` icon), Shuffle (`#sceneShuffle87`), and Repeat (`#sceneRepeat87`) into `#sceneTools30` at the top-right; kept Queue (`#albumQueue78`) separate in `#albumActions78`.
- **Button States, Motion & Softened Edges:** Synchronized `#sceneShuffle87`, `#sceneRepeat87`, `#sceneTranslate87`, and `#karaokeMenuButton45` `.on` / `aria-pressed` / `#i-repeat1` states across `player.js`, `repair-v33.js`, and `Motion73` (`ui-v73.js`); added visible active pill highlights, spring press scaling, and rounded corners (`border-radius: 999px` on `.ib`/`.chip`, `12px–18px` on inputs/menus/cards) across `polish-v73.css`, `reference-scene-v24.css`, `upgrade-v30.css`, `repair-v33.css`, and `interface-v45.css`.
- **Rewritten Lyric Translation:** Rewrote `kryonyx/lyric_translate.py` and `kryonyx/web/js/lyrics-translate-v22.js` with built-in async translation + fallback providers, script-aware auto-detection, memory/disk caching, partial failure recovery, cancellation support, and per-track restoration across all Karaoke modes.
- **Timing Editor:** Enabled `#karaokeEdit45` for both JSON v2 documents and plain LRC lyrics (`version: 2` fallback in `karaoke-editor.js`), added `Now` line boundary capture buttons and `Tap · T` access inside `#karaokeMenu45`.

### 1.8. Performance & Prefetch Enhancements
- **Zero Continuous GPU Blur:** Removed the infinite `filter: blur(10px); animation: drift` on `body::before` (`app.css`), disabled per-line `.lyr-l` blur during karaoke scroll (`app.css`), enforced `backdrop-filter: none` across chrome/overlays (`perf-v72.css`), and lowered `FluidCover24` resolution/FPS targets (`fluid-cover-v29.js`).
- **Next-Track Preloading:** Added `playing` and `canplaythrough` triggers, cancellable `/api/prefetch?status=1` polling, and idle browser `<audio preload="auto">` stream warming (`_warmNextAudio`) in `player.js`.

### 1.9. Theme Previews (Block 10)
- **Root cause:** 4 v82 themes (`tide82`, `dusk82`, `mineral82`, `morning82`) were missing `.webp` previews, and 81 orphaned `.webp` files remained in `kryonyx/web/img/theme-ui/`.
- **Fix:** Created `tools/update_theme_previews.py` and regenerated live WebP screenshots (880×592) from the current UI for all **137** visible themes in `THEME_LIBRARY`, removed **81** orphans, and generated `kryonyx/web/img/theme-ui/manifest.json`.

## 2. Verification Results

- **Python (`py -3.14 -m pytest -q tests/test_argos_v82.py tests/test_avatar_cleanup.py tests/test_recommend_refresh.py tests/test_karaoke.py tests/test_karaoke_review.py tests/test_critical_stability_kryo.py tests/test_custom_avatars_v13.py`):** `75 passed, 3 skipped, 124 warnings, 9 subtests passed` (including live online `en -> ru` translation verification).
- **Node syntax & unit suites:**
  - `node --check` across all modified `.js` files: passed (exit 0).
  - `tests/test_karaoke_editor.cjs`: `16 editor and fidelity assertions passed`.
  - `tests/test_karaoke_timing.cjs`: `11 timing tests passed`.
  - `tests/test_karaoke_renderer.cjs`: `LINE_RENDERER_PASS 9`.
  - `tests/test_prefetch_v30.cjs`: `PREFETCH_V30_PASS 11`.
  - `tests/test_i18n_coverage.cjs`: `I18N_COVERAGE_PASS languages=12 keys=3100`.
- **Browser E2E (`py -3.14 -u tests/browser_e2e_kryo.py`, headless Chrome):** verified card geometry, recommendations refresh, 12-language switching, visualizer & eye icon removal, top-right karaoke bar + separate Queue, button active states, timing editor access, live karaoke translation (`en -> ru`), zero active backdrop blurs, avatar store (`233`), and all `137` theme previews.
- **Windows Release Build:** Built `dist\Kryo\Kryo.exe`, `dist\Kryo-1.0.0-engine.exe`, and `dist\Kryo-1.0.0-setup.exe` in `C:\Users\hatsu.EGRTG\Desktop\kryonyx\music` (`ISCC.exe` exit code 0).

## 3. Release Notes & Compliance Reminders

1. **Third-party Artwork & FFmpeg Redistribution (`docs/LICENSE_AUDIT.md`):** Built-in third-party avatars (`kryonyx/avatars.json`) and `Kryo.png` remain marked `not_cleared` in `ARTWORK_RIGHTS.md` for public binary redistribution; bundled `ffmpeg` (`9.0.2` via `imageio-ffmpeg`) is GPLv3 (`--enable-gpl --enable-version3`). See `docs/GITHUB_RELEASE_GUIDE.md`.
