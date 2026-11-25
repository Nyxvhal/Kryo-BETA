"""Capture live WebP theme previews from the current Kryo UI and write manifest.json."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from PIL import Image
from playwright.sync_api import sync_playwright

from kryonyx import __version__, recommend, server

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "kryonyx/web/img/theme-ui"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _start_server(tmp_dir: str):
    rows = [
        {
            "id": "mix1",
            "title": "For you",
            "kind": "tracks",
            "items": [
                {
                    "id": f"local:preview_{i}",
                    "source": "local",
                    "title": f"Midnight Echoes {i+1}",
                    "artist": "Kryo Demo",
                    "duration": 210,
                    "thumbnail": "/img/avatars/kryonyx-core.png",
                }
                for i in range(8)
            ],
        }
    ]

    async def fake_build_rows(limit_rows=12, exclude_ids=None):
        recommend._cache[f"rows:{limit_rows}"] = (time.monotonic() + 600, rows)
        recommend._cache["rows"] = (time.monotonic() + 600, rows)
        recommend._save_rows(rows)
        return rows

    ready = threading.Event()
    holder = {}

    def runner():
        async def _main():
            app = server.build_app()
            r = web.AppRunner(app)
            await r.setup()
            site = web.TCPSite(r, "127.0.0.1", 0)
            await site.start()
            holder["port"] = site._server.sockets[0].getsockname()[1]
            ready.set()
            while not holder.get("stop"):
                await asyncio.sleep(0.1)
            await r.cleanup()

        asyncio.run(_main())

    p1 = patch("kryonyx.paths.data_dir", return_value=tmp_dir)
    p2 = patch("kryonyx.paths.cache_dir", return_value=tmp_dir)
    p3 = patch("kryonyx.recommend.cache_dir", return_value=tmp_dir)
    p4 = patch("kryonyx.recommend.build_rows", side_effect=fake_build_rows)
    p5 = patch("kryonyx.extras.fill_thumbnails", new=AsyncMock())
    for p in (p1, p2, p3, p4, p5):
        p.start()
    recommend._cache.clear()
    recommend._disk_invalidated = False
    t = threading.Thread(target=runner, daemon=True)
    t.start()
    ready.wait(timeout=10)
    return holder, (p1, p2, p3, p4, p5), t


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        holder, patches, thread = _start_server(tmp)
        url = f"http://127.0.0.1:{holder['port']}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1100, "height": 740}, reduced_motion="reduce")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("() => document.body.classList.contains('ui-v33') && document.querySelectorAll('#rows .card').length >= 4", timeout=15000)
                page.evaluate("""() => {
                    closeModals(); App.go('home'); setLang('en');
                    S.noAnim = true; S.wallSrc = ''; S.atmo = false; S.rail = false; S.compact = false;
                    S.panelOpacity33 = 85; S.customCss = ''; S.tune = {}; saveSettings = () => {};
                    const track = { id: 'local:preview', source: 'local', title: 'Theme preview', artist: 'Kryo · Demo', duration: 210, thumbnail: '/img/avatars/kryonyx-core.png' };
                    Player.current = track; Player.queue = [track]; Player.index = 0; Player.paintTrack();
                }""")

                themes = page.evaluate("""() => Object.entries(THEME_LIBRARY)
                    .filter(([, v]) => v.group !== 'hidden')
                    .map(([id, t]) => ({ id, name: t.name, file: id.replace(/[^a-z0-9_-]/gi, '-') + '.webp' }))""")

                expected_files = {t["file"] for t in themes}
                assert len(expected_files) == len(themes), "Duplicate theme preview filenames"

                # Remove orphaned preview files not in THEME_LIBRARY
                removed_orphans = []
                for f in list(OUT_DIR.iterdir()):
                    if f.is_file() and f.suffix.lower() in (".webp", ".png") and f.name not in expected_files:
                        f.unlink()
                        removed_orphans.append(f.name)

                manifest_entries = []
                captured_at = datetime.now(timezone.utc).isoformat()
                for idx, theme in enumerate(themes):
                    applied = page.evaluate("""(id) => {
                        useTheme(id);
                        document.activeElement?.blur();
                        $('toast')?.classList.remove('on');
                        const cs = getComputedStyle(document.documentElement);
                        return { theme: S.theme, bg: cs.getPropertyValue('--bg').trim(), accent: cs.getPropertyValue('--accent').trim() };
                    }""", theme["id"])
                    assert applied["theme"] == theme["id"], f"Failed to apply {theme['id']}"
                    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                    png_bytes = page.screenshot(type="png")
                    with Image.open(io.BytesIO(png_bytes)) as img:
                        resized = img.resize((880, 592), Image.Resampling.LANCZOS)
                        out_path = OUT_DIR / theme["file"]
                        resized.save(out_path, format="WEBP", quality=82, method=4)
                    sha = hashlib.sha256((OUT_DIR / theme["file"]).read_bytes()).hexdigest()
                    manifest_entries.append({
                        "id": theme["id"],
                        "name": theme["name"],
                        "file": theme["file"],
                        "bg": applied["bg"],
                        "accent": applied["accent"],
                        "sha256": sha,
                        "gui_version": __version__,
                        "captured_at": captured_at,
                    })
                    if (idx + 1) % 50 == 0 or idx + 1 == len(themes):
                        print(f"Captured {idx + 1}/{len(themes)}")

                manifest = {
                    "gui_version": __version__,
                    "captured_at": captured_at,
                    "viewport": {"width": 1100, "height": 740},
                    "output": {"width": 880, "height": 592, "format": "webp"},
                    "total": len(manifest_entries),
                    "removed_orphans": removed_orphans,
                    "themes": manifest_entries,
                }
                (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                browser.close()
                print(f"DONE: {len(manifest_entries)} theme previews updated, {len(removed_orphans)} orphans removed.")
        finally:
            holder["stop"] = True
            thread.join(timeout=3)
            for p in patches:
                p.stop()


if __name__ == "__main__":
    main()
