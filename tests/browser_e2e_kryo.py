"""Live headless Chrome E2E verification for Kryo UI fixes."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from playwright.sync_api import sync_playwright

from kryonyx import avatars, recommend, server

ROOT = Path(__file__).resolve().parent.parent
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _start_server(tmp_dir: str):
    rows_v1 = [
        {
            "id": "mix1",
            "title": "For you",
            "kind": "tracks",
            "items": [
                {"id": f"yt:t1_{i}", "source": "yt", "title": f"Track One {i}", "artist": f"Artist {i}", "duration": 180}
                for i in range(8)
            ],
        }
    ]
    rows_v2 = [
        {
            "id": "mix2",
            "title": "Fresh picks",
            "kind": "tracks",
            "items": [
                {"id": f"yt:t2_{i}", "source": "yt", "title": f"Track Two {i}", "artist": f"Artist B{i}", "duration": 200}
                for i in range(8)
            ],
        }
    ]
    refresh_count = {"n": 0}

    async def fake_build_rows(limit_rows=12, exclude_ids=None):
        refresh_count["n"] += 1
        excluded = set(exclude_ids or [])
        data = rows_v2 if "yt:t1_0" in excluded else rows_v1
        recommend._cache[f"rows:{limit_rows}"] = (time.monotonic() + 600, data)
        recommend._cache["rows"] = (time.monotonic() + 600, data)
        recommend._save_rows(data)
        return data

    ready = threading.Event()
    port_holder = {}

    def runner():
        async def _main():
            app = server.build_app()
            runner_obj = web.AppRunner(app)
            await runner_obj.setup()
            site = web.TCPSite(runner_obj, "127.0.0.1", 0)
            await site.start()
            port_holder["port"] = site._server.sockets[0].getsockname()[1]
            port_holder["runner"] = runner_obj
            ready.set()
            while not port_holder.get("stop"):
                await asyncio.sleep(0.1)
            await runner_obj.cleanup()

        asyncio.run(_main())

    p_data = patch("kryonyx.paths.data_dir", return_value=tmp_dir)
    p_cache = patch("kryonyx.paths.cache_dir", return_value=tmp_dir)
    p_rcache = patch("kryonyx.recommend.cache_dir", return_value=tmp_dir)
    p_build = patch("kryonyx.recommend.build_rows", side_effect=fake_build_rows)
    p_thumbs = patch("kryonyx.extras.fill_thumbnails", new=AsyncMock())
    p_data.start()
    p_cache.start()
    p_rcache.start()
    p_build.start()
    p_thumbs.start()
    recommend._cache.clear()
    recommend._disk_invalidated = False

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    ready.wait(timeout=10)
    return port_holder, (p_data, p_cache, p_rcache, p_build, p_thumbs), t


def main():
    if not Path(CHROME_PATH).is_file():
        raise RuntimeError(f"Chrome not found at {CHROME_PATH}")

    with tempfile.TemporaryDirectory() as tmp:
        port_holder, patches, thread = _start_server(tmp)
        url = f"http://127.0.0.1:{port_holder['port']}"
        console_errors = []
        bad_responses = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.on("pageerror", lambda err: console_errors.append(f"pageerror: {err}"))
                page.on("response", lambda res: bad_responses.append(f"{res.status} {res.url}") if res.status >= 400 else None)
                page.on("console", lambda msg: console_errors.append(f"console.error: {msg.text}") if msg.type == "error" and "Failed to load resource: the server responded with a status of 404" not in msg.text else None)

                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("() => document.body.classList.contains('ui-v33') && document.querySelectorAll('#rows .card').length >= 4", timeout=15000)

                # 1. Cover card geometry (idle, playing, hover)
                geom = page.evaluate("""() => {
                    const cards = [...document.querySelectorAll('#rows .card')].slice(0, 6);
                    cards[1].classList.add('playing');
                    cards[2].focus();
                    const rects = cards.map(c => {
                        const r = c.querySelector('.art').getBoundingClientRect();
                        return { top: r.top, width: r.width, height: r.height };
                    });
                    const sameRowTop = rects.filter(r => Math.abs(r.top - rects[0].top) <= 1.5).length;
                    const squareCount = rects.filter(r => Math.abs(r.width - r.height) <= 1.5).length;
                    return { total: rects.length, sameRowTop, squareCount, rects };
                }""")
                assert geom["squareCount"] == geom["total"], f"Non-square cards: {geom}"
                assert geom["sameRowTop"] >= 3, f"Misaligned card tops: {geom}"
                print("E2E_PASS card_geometry", geom["total"])

                # 2. Recommendations Refresh button
                before_ids = page.evaluate("() => [...document.querySelectorAll('#rows .card')].map(c => c.dataset.id)")
                page.click("#homeRefresh31")
                page.wait_for_function(
                    "(prev) => { const ids = [...document.querySelectorAll('#rows .card')].map(c => c.dataset.id); return ids.length >= 4 && ids[0] !== prev && !document.getElementById('homeRefresh31').disabled; }",
                    arg=before_ids[0],
                    timeout=10000,
                )
                after_ids = page.evaluate("() => [...document.querySelectorAll('#rows .card')].map(c => c.dataset.id)")
                assert before_ids[0] != after_ids[0], (before_ids, after_ids)
                print("E2E_PASS recommendations_refresh", before_ids[0], "->", after_ids[0])

                # 3. All 12 languages UI switch
                langs = ["en", "ru", "es", "pt", "de", "fr", "it", "tr", "pl", "uk", "zh", "ja"]
                for lang in langs:
                    ok = page.evaluate("(l) => { setLang(l); return document.documentElement.lang === l && !document.body.innerText.includes('undefined'); }", lang)
                    assert ok, f"Language switch failed for {lang}"
                page.evaluate("() => setLang('en')")
                print("E2E_PASS i18n_12_languages")

                # 4. Visualizer removed, Eye removed, Top-Right Karaoke bar, Queue separate, Button visuals, Timing & Translation
                karaoke_audit = page.evaluate("""() => {
                    Player.current = { id: 'yt:demo1', source: 'yt', title: 'Test Song', artist: 'Test Artist', duration: 120 };
                    Player.queue = [Player.current, { id: 'yt:demo2', source: 'yt', title: 'Next Song', artist: 'Next Artist', duration: 140 }];
                    Player.index = 0;
                    Karaoke.trackId = 'yt:demo1';
                    Karaoke.lines = [
                        { time: 1.0, text: 'Hello world' },
                        { time: 4.5, text: 'Music is life' },
                    ];
                    Karaoke.synced = true;
                    Karaoke.document = null;
                    Karaoke.render();
                    App.openNow();
                    const modes = [...document.querySelectorAll('#sceneMode33 option')].map(o => o.value);
                    const tools = [...document.querySelectorAll('#sceneTools30 > *')].map(n => n.id);
                    const hasAlbumActions = !!document.getElementById('albumActions78') || !!document.getElementById('albumQueue78');
                    const albumLyricsBorder = getComputedStyle(document.getElementById('albumLyrics24')).borderTopWidth;
                    const trUse = document.querySelector('#sceneTranslate87 use')?.getAttribute('href');
                    const timingUse = document.querySelector('#karaokeMenuButton45 use')?.getAttribute('href');
                    const radiusBtn = getComputedStyle(document.getElementById('sceneTranslate87')).borderRadius;
                    const blurs = [...document.querySelectorAll('*')].filter(el => {
                        const cs = getComputedStyle(el);
                        const bf = cs.backdropFilter || cs.webkitBackdropFilter || 'none';
                        return bf !== 'none' && cs.display !== 'none' && cs.visibility !== 'hidden';
                    }).length;
                    return {
                        hasVizStage: !!document.getElementById('vizStage'),
                        vizOn: !!(typeof Viz !== 'undefined' && Viz.on),
                        hasEyeTop: !!document.getElementById('sceneRestore30'),
                        hasEyeLeft: !!document.getElementById('nCtl'),
                        modes, tools, hasAlbumActions, albumLyricsBorder, trUse, timingUse, radiusBtn, blurs,
                    };
                }""")
                assert not karaoke_audit["hasVizStage"] and not karaoke_audit["vizOn"], karaoke_audit
                assert "viz" not in karaoke_audit["modes"], karaoke_audit
                assert not karaoke_audit["hasEyeTop"] and not karaoke_audit["hasEyeLeft"], karaoke_audit
                assert not karaoke_audit["hasAlbumActions"], karaoke_audit
                assert karaoke_audit["albumLyricsBorder"] == "0px", karaoke_audit
                for expected_id in ("sceneTranslate87", "karaokeMenuButton45", "sceneShuffle87", "sceneRepeat87"):
                    assert expected_id in karaoke_audit["tools"], karaoke_audit
                assert karaoke_audit["trUse"] == "#i-translate", karaoke_audit
                assert karaoke_audit["timingUse"] == "#i-clock", karaoke_audit
                assert karaoke_audit["blurs"] == 0, f"Active backdrop blurs remain: {karaoke_audit}"
                print("E2E_PASS karaoke_layout_and_zero_blur", karaoke_audit["tools"], karaoke_audit["radiusBtn"])

                # 4b. Shuffle & Repeat active toggle state + icons
                page.evaluate("() => { S.shuffle = false; S.repeat = 'off'; Player.paintState(); }")
                shuf_before = page.evaluate("() => ({ shuf: !!S.shuffle, on: document.getElementById('sceneShuffle87').classList.contains('on'), pressed: document.getElementById('sceneShuffle87').getAttribute('aria-pressed') })")
                assert not shuf_before["on"] and shuf_before["pressed"] == "false", shuf_before
                page.click("#sceneShuffle87")
                shuf_on = page.evaluate("() => ({ shuf: !!S.shuffle, on: document.getElementById('sceneShuffle87').classList.contains('on'), pressed: document.getElementById('sceneShuffle87').getAttribute('aria-pressed') })")
                assert shuf_on["shuf"] and shuf_on["on"] and shuf_on["pressed"] == "true", shuf_on

                page.click("#sceneRepeat87")
                rep_all = page.evaluate("() => ({ repeat: S.repeat, on: document.getElementById('sceneRepeat87').classList.contains('on'), href: document.querySelector('#sceneRepeat87 use')?.getAttribute('href') })")
                assert rep_all["repeat"] == "all" and rep_all["on"] and rep_all["href"] == "#i-repeat", rep_all
                page.click("#sceneRepeat87")
                rep_one = page.evaluate("() => ({ repeat: S.repeat, on: document.getElementById('sceneRepeat87').classList.contains('on'), href: document.querySelector('#sceneRepeat87 use')?.getAttribute('href') })")
                assert rep_one["repeat"] == "one" and rep_one["on"] and rep_one["href"] == "#i-repeat1", rep_one
                page.click("#sceneRepeat87")
                rep_off = page.evaluate("() => ({ repeat: S.repeat, on: document.getElementById('sceneRepeat87').classList.contains('on'), href: document.querySelector('#sceneRepeat87 use')?.getAttribute('href') })")
                assert rep_off["repeat"] == "off" and not rep_off["on"] and rep_off["href"] == "#i-repeat", rep_off
                print("E2E_PASS button_active_states")

                # 4c. Timing menu & LRC timing editor accessible
                page.click("#karaokeMenuButton45")
                page.wait_for_function("() => !document.getElementById('karaokeMenu45').hidden && !document.getElementById('karaokeEdit45').disabled", timeout=5000)
                page.click("#karaokeEdit45")
                page.wait_for_function("() => document.getElementById('mKaraokeEditor')?.classList.contains('on')", timeout=5000)
                page.click("#keClose")
                print("E2E_PASS karaoke_timing_editor_from_menu")

                # 4d. Real end-to-end lyric translation in Karaoke
                page.click("#sceneTranslate87")
                page.wait_for_function("() => !document.getElementById('translationPanel33').hidden", timeout=5000)
                page.select_option("#lt22Target", "ru")
                page.click("#lt22Run")
                page.wait_for_function(
                    "() => document.querySelectorAll('#lyrics .lyric-translated22').length >= 2 && document.querySelector('#lyrics .lyric-translated22').textContent.trim().length > 0",
                    timeout=15000,
                )
                tr_texts = page.evaluate("() => [...document.querySelectorAll('#lyrics .lyric-translated22')].map(n => n.textContent.trim())")
                assert len(tr_texts) >= 2 and all(tr_texts), tr_texts
                print("E2E_PASS karaoke_live_translation", tr_texts)
                page.click("#translationClose33")
                page.evaluate("() => $('nClose').click()")

                # 5. Avatar store (233 entries, removed categories absent)
                page.evaluate("() => ExperienceV8.openStore()")
                page.wait_for_function("() => document.querySelectorAll('#ui8StoreGrid .ui8-avatar-card').length > 0", timeout=10000)
                store_info = page.evaluate("""() => ({
                    total: Avatars.items.length,
                    cats: [...new Set(Avatars.items.map(i => i.category))],
                    hasPoppy: Avatars.items.some(i => i.id.includes('poppy-playtime')),
                    hasOk: Avatars.items.some(i => i.id === 'collection-249-одноклассники'),
                })""")
                assert store_info["total"] == 233, store_info
                for forbidden in ("Streamers", "Music artists", "YouTube and creators"):
                    assert forbidden not in store_info["cats"], store_info
                assert not store_info["hasPoppy"] and not store_info["hasOk"], store_info
                print("E2E_PASS avatar_store_233")

                # 6. Theme preview files exist for all visible themes in THEME_LIBRARY
                theme_check = page.evaluate("""() => Object.entries(THEME_LIBRARY)
                    .filter(([, v]) => v.group !== 'hidden')
                    .map(([id]) => ({ id, file: id.replace(/[^a-z0-9_-]/gi, '-') + '.webp' }))""")
                missing_previews = [
                    t["file"] for t in theme_check
                    if not (ROOT / "kryonyx/web/img/theme-ui" / t["file"]).is_file()
                ]
                assert not missing_previews, f"Missing theme previews: {missing_previews[:10]}"
                print("E2E_PASS theme_previews_present", len(theme_check))

                non_doc_bad = [r for r in bad_responses if "/api/karaoke/document" not in r]
                assert not console_errors and not non_doc_bad, f"Errors: {console_errors} bad={non_doc_bad}"
                browser.close()
        finally:
            port_holder["stop"] = True
            thread.join(timeout=3)
            for pt in patches:
                pt.stop()


if __name__ == "__main__":
    main()
