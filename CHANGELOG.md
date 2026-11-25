# Source revision v73

Fixes, an optional Rust shell and a plan for NCNN.

- Menus opened from a button (⋮ and friends) are anchored to it and never cover it: below or above, scrolling inside a short window; right-click menus open at the pointer and flip at the edges; arrows / Home / End / Esc with focus returned (`Menu73`, core.js).
- Search: the artist prefix of upload titles is stripped, the famous song wins among same-named ones (Top result and play counts weigh more), symbol titles ("∞") are trusted when the catalogue ranks them early, concert dates mark live uploads, cover channels drop unless asked, version tags after a dash are not artists, per-source trust (`search_rank72.py`). The UI no longer re-sorts server-ranked rows by title only; one recording from several sources is one row; "Show more" appends below without reshuffling or duplicates; a failed catalogue sub-query is retried and a degraded answer is not cached; skeletons stay until tracks arrive. "All" shows the songs right after the top result (8 + "Show all tracks").
- Player buttons: a sweep of every control of the player bar, its menu, Now Playing and the queue (58/58 in `tests/browser_v73/buttons.cjs`). Shuffle/Repeat during Wave were silently disabled; they now explain why and offer to turn Wave off. One time tooltip over the clip seek bar instead of two.
- Button motion: pointer ripple, eased press/hover (transform/opacity only), like pop, play/pause swap, next/prev nudges, locked shake; off with Settings → Animations and reduced motion (`ui-v73.js`, `polish-v73.css`).
- Performance (`perf-v73.js`): one clip seek in flight (newest wins) and seeks are not stalls, so Play/"Buffering" stop flickering — 2 s of scrubbing went from 568 to 255 ms of layout and 68 % to 47 % main thread; ambient light at most 30 redraws/s (12 on economy) and none mid-seek; a dropped-frames watchdog lightens the room for the session (with Undo). Settings tab switches without forced layouts and without rebuilding the ~3 500-node theme gallery: Themes → Sound → Themes 764–819 → 449 ms main thread, style recalc 213 → 86 ms.
- Mini player moves again: fractional WebView2 deltas (0.67 px at 150 %) were truncated to 0 and pywebview 5.x scaled twice; the window now moves with `SetWindowPos` and a sub-pixel carry, by the whole card (4 px threshold keeps button clicks).
- Optional Rust shell `desktop-rs/` (tao + wry): native window, splash, mini player, Save As and window state; starts the unchanged Python backend (`--server-only`) with a per-launch token for `/api/shell/*` (hello, save-plan, save, quit), a Windows job object and a clean stop. Clippy-clean for Windows, 15 core tests, end-to-end backend test, 26 bridge checks in Chromium; not yet run on a real Windows desktop. Tray, thumbnail buttons, exe icon and single instance are not ported.
- AI: `docs/AI_NCNN_MIGRATION_PLAN.md` proposes replacing PyTorch/CUDA with portable realesrgan/rife-ncnn-vulkan engines downloaded on demand (10–17 MB instead of 2.5–3 GB), with a Vulkan probe, an off switch and a licence table; prototypes in `research/ai-ncnn/` (not wired in). The AI code and dependencies are unchanged pending approval.
- 24 avatar/notice files with Cyrillic names restored.

See docs/RELEASE_V73.md and docs/VERIFICATION_V73.json.

# Source revision v72

Cinema+, sound quality you can see, honest search, optional AI enhancement, a calmer installer.

- Clip menu ⚙ is a tabbed panel (Video · Screen · Colour · Ambient · AI · Keys): exact speed 0.25–2× ([ / ] keys), "Pitch follows speed" (on by default, like a record; off keeps the natural voice), audio delay −300…+300 ms, loop, fit / fill screen, open clips in viewing mode, hide-controls delay, brightness / contrast / saturation for the clip only, a shortcut list.
- Video size in viewing mode: dragging the slider (or a 70/80/90/100 % chip) only previews a frame outline; the size is applied on release with a 0.42 s eased resize, the menu stays anchored to its button.
- Player bar: a quality pill shows what really plays (codec · kbps · cached or streaming). Its popover switches Best / Balanced (≤160 kbps) / Data saver (≤80 kbps) for the current track at the same position, plus speed chips with "pitch follows speed", crossfade and loudness normalisation.
- Quality tiers: every cached track remembers the tier, codec and bitrate it was fetched with; a higher mode replaces a lower copy on the next play (the lower copy stays as the offline fallback); `/api/stream/info`, `/api/stream/requality`.
- Search: songs, videos and the general "top result" query run in parallel; ranking uses the core title (credits, promo and remaster tags removed), YouTube Music position, play counts, the top result and the result type; copies of one recording collapse into one row; covers / sped up / live are penalised unless asked for (`kryonyx/search_rank72.py`).
- Optional AI module (`setup-ai.bat auto|cpu|cu118|cu126|cu128` → `.ai-venv`): Real-ESRGAN for wallpapers ("Enhance with AI" or "Keep as is" after choosing an image) and clips (×2, 1080p, 1440p, 4K), RIFE for ×2 frames. Separate worker process, one job at a time, cancellable, cached; weights downloaded on demand over HTTPS with size and SHA-256 checks. The UI always warns that a powerful PC (NVIDIA, ≥6 GB VRAM) is needed; on CPU it is very slow.
- Lag: no backdrop blur on the closed veil and on invisible card pills, off-screen Home cards skip rendering, the progress bar repaints only when it moves a device pixel, the cover-palette frame loop now ends (it ran 60×/s all session).
- Polish: keyboard-only focus rings, eased press/hover, queue row buttons on the title line and an upward "move up" arrow, a single settings search field with a soft focus halo.
- Installer: redesigned animated wizard (aurora, progress ring, EQ, sliding step pill, finish burst) that animates only transform/opacity — idle main-thread work went from ~120 style recalcs per 2 s to none; invalid `font` shorthands fixed; compact layout for small windows; animations pause when hidden and honour reduced motion.

See docs/RELEASE_V72.md and docs/VERIFICATION_V72.json.

# Source revision v71

Cinema: the clip room rebuilt, a viewing mode, smooth ambient, an installer that updates.

- Clip room rebuilt (`css/cinema-v71.css`, `js/cinema-v71.js`); the stacked clips-v4 / video-v57 / watch-v59 layers are no longer linked. One header (back, brand, search, cookies, close), sections and categories in one toolbar, a calmer watch page (actions under the title, "Up next" with an autoplay switch, "Now playing" badge), real download progress, always-dark surface with the theme accent, single-column narrow layout.
- Viewing mode: T (or the button) hides every piece of UI, including the window title bar; only the clip and its blurred background remain. Controls appear on mouse movement; Esc or T exits (the first Esc never closes the clip). Video size 60–100 % and a separate background switch in the ⚙ menu; works in fullscreen.
- Ambient background drawn per video frame (`requestVideoFrameCallback`) and blurred inside a small canvas instead of a full-window CSS filter: in the same headless test the watch page went from 10–12 fps / GPU 98 % / ambient 9.6 fps / ~70 dropped video frames per 5 s to 60 fps / 35 % / 25 fps (= video) / 0.
- Player: audio/video drift of 40–300 ms is corrected by nudging the audio rate (≤5 %) instead of seeking; hidden Now-screen animations paused; film grain without mix-blend-mode (off in OLED).
- Installer: update detection from the engine's uninstall entry (folder, version, options; "Update" button), free-space check, polite close of a running Kryonyx (Restart Manager as backstop, `*.pyd` included), real progress from the engine log with a file counter, specific errors per engine exit code with the log one click away, `_internal` replaced cleanly, shortcuts for disabled options removed, labelled stepper, single-instance guard, WebView2 download prompt, clean environment for the launched app, one version from `kryonyx/__init__.py` for app, engine and setup names, private bridge attributes.

See docs/RELEASE_V71.md and docs/VERIFICATION_V71.json.

# Source revision v70

Polish: OLED by default, honest recommendations.

- New profiles start in the black-and-white OLED theme (pure #000, white accent); boot splash and window background are black. Existing settings are untouched.
- Accent-button text follows the accent's luminance (fixes white-on-white buttons in Clips); OLED greys are neutral instead of lavender.
- Home: compact header with a time-of-day greeting, one toolbar (segmented kind and balance controls, "similar tracks" switch, source select), one-line scrollable categories, a dismissible welcome card with import shortcuts, loading skeletons, hover/focus card actions on mouse devices, letterbox-free YouTube thumbnails, quieter source badges, compact mobile header.
- Recommendations: cold start from YouTube Music charts and editorial playlists by region, quality gate against compilations/streams/fake artists, one card per song across versions, activity penalties, taste decay (120-day half-life), "On repeat", "More from artist" filtered by artist, related "Artists new to you", YouTube-twin radio for other sources, stable daily mix, chart-region setting.
- Robustness: UI modules start in isolation, JS errors reach the app log as `[ui]` lines (rate-limited), static files are revalidated (`Cache-Control: no-cache`) so updates never mix old and new UI files.
- Fixes: "Liked" shown as "liked" in English, two-language modules now use the shared dictionary for all 11 languages, consistent brand spelling, double focus ring in settings search, missing settings tab icons, search suggestions left open after navigation, coroutine leak on cancelled recommendation requests, recent-history ordering, skips without duration.
- Faster start: the theme gallery (~3 500 nodes) is built only when opened.

See docs/RELEASE_V70.md.

# Source revision v52

- Lumen navigation, discovery/library surfaces, responsive transport and settings hub.
- Cinema-style clip room with the existing progressive playback engine.
- Validated appearance presets, live controls, export/import/reset/undo.
- Visualizer runtime removed; existing karaoke engines and editors retained.
- No home ambience render loop; reduced-motion support and readable control contrast.
- Source label clipping/visibility and missing statistics fallbacks fixed.

See docs/RELEASE_V52.md and docs/VERIFICATION_V52.json.

# Source revision v51

- Cached logarithmic FFT maps, orbital geometry and spectrum gradients.
- Batched LED/spike rendering and bounded background/spectrum pixel work.
- ResizeObserver-driven canvas geometry instead of hot-path layout reads.
- Stable scene/title geometry and idempotent colour/beat style updates.
- Visibility/playback-aware marquees, modal coverage handling and observer cleanup.
- Auto/economy/quality rendering profiles; audio fidelity and media clock unchanged.
- Unit and real-WAV browser regression, reproducible constrained-device profiling.

See docs/RELEASE_V51.md for scope, controls and limitations.

# Source revision v50

Музыкальный профиль и персональные рекомендации

- Импорт музыкальных метаданных из JSON/CSV/XML/M3U и ограниченных ZIP.
- Предпросмотр и выбор категорий, замена профиля сервиса и безопасное удаление.
- Отдельные внешние сигналы для рекомендаций, радио и ежедневного микса.
- Баланс знакомого/нового, влияние импорта, причины рекомендаций и скрытие/отмена.
- Нормализация и дедупликация записей; защита кэша от устаревших задач.
- Проверки API, парсера, хранилища, ранжирования и адаптивного интерфейса.
- Подробности и честные ограничения: docs/RELEASE_V50.md.

# Source revision v49

- Unified link/file transfer, automatic public-service detection and saved manual refresh sources.
- Review destination selection, additive updates without duplicate track IDs and UTF-8 CSV export.
- Atomic batch saves, accurate duplicate counts and retry-safe concurrent saves.
- Non-overlapping progress polling, stale-response/cancellation guards and reconnect without restarting a job.
- 100-row review pagination, keyboard selection and resilient source preferences.
- Connected card surfaces, a home-screen transfer shortcut and three layout presets.
- Strict input host validation and tracking-free saved source URLs.

See docs/RELEASE_V49.md for support, reproduction instructions and limitations.

# Source revision v48

- Theme-safe hover states, square round controls, polished cards and forms.
- Persistent layout studio: navigation position/width, player docking/order, spacing, corners, window bounds UI.
- Cancellable immediate-local/rich-remote search suggestions with category filters and a bounded cache.
- Six-service metadata transfer hub, UTF-8 CSV/JSON/M3U/Apple XML parsing and review-before-save.
- Public Deezer metadata reader with fixed-host bounded pagination and explicit failures.
- Redesigned RU/EN installer with settings review and native-engine completion gating.
- Event-driven motion with cleanup and an optional economy background-render budget.

See docs/RELEASE_V48.md for service-specific support, formats, tests and limitations.

## v69 — Pulse installer and clip room

- Installer redesigned in the monochrome Pulse style: animated logo stage per step, word-by-word headings, directional transitions, header progress line. Logic, bridge, legal documents, errors and the real (non-simulated) progress are unchanged.
- Clip room fixes: seek slider no longer jumps back while dragging; time tooltip and buffered range on the seek bar; keyboard shortcuts keep working after clicking a control; double-click to fullscreen no longer toggles play/pause; controls hide again after mouse use; settings menu no longer truncates labels; buffering dims the frame.
- New motion: view transitions, staggered clip cards and up-next list, animated settings popover, pulsing center play button, action feedback.

## v47

- Visible-only transport updates, composited progress and bounded visualizer background rendering.
- Event-driven interface transitions respecting reduced-motion preferences.
