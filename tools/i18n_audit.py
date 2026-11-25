"""i18n_audit.py — что ещё не переведено.

Собирает все строки интерфейса (вызовы t(), разметка index.html, каталог
плагинов, темы, список новинок) и сверяет их со словарями в web/js/i18n.js.
Печатает пропуски по каждому языку.

    python tools/i18n_audit.py              # сводка
    python tools/i18n_audit.py ru           # что не хватает в русском
    python tools/i18n_audit.py --json out.json
"""

from __future__ import annotations

import glob
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "kryonyx", "web")

# Строки, которые переводить не нужно: имена, адреса, коды.
SKIP = re.compile(
    r"^(?:https?://|KRX1|Kryonyx|yt-dlp|ffmpeg|aiohttp|SQLite|Discord|Spotify|"
    r"SoundCloud|YouTube|Bandcamp|Mixcloud|Jamendo|Audius|Deezer|Discogs|"
    r"LRCLIB|Last\.fm|ListenBrainz|Maloja|Mastodon|MusicBrainz|OLED|"
    r"English|Espa|Portug|Deutsch|Fran|Italiano|T\u00fcrk|Polski|\u0423\u043a\u0440|\u4e2d\u6587|\u65e5\u672c\u8a9e)",
    re.I)


def flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def collect() -> set[str]:
    out: set[str] = set()
    files = [f for f in glob.glob(os.path.join(WEB, "js", "*.js"))
             if "i18n" not in os.path.basename(f)]
    call = re.compile(r"\b(?:t|tf|tr|label|tParts)\(\s*(['\"])((?:\\.|(?!\1).)*)\1", re.S)
    for path in files:
        body = open(path, encoding="utf-8").read()
        for _, value in call.findall(body):
            out.add(value.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t"))
        # t({ ok: 'Works', ... }) — словарь состояний
        for block in re.findall(r"t\(\{(.*?)\}", body, re.S):
            out.update(re.findall(r"['\"]([^'\"]{2,})['\"]", block))
        # NEWS, HOTKEYS и заметки тем лежат обычными массивами, без t()
        for name in ("NEWS", "HOTKEYS", "THEME_GROUPS"):
            found = re.search(rf"const {name} = \[(.*?)\n\];", body, re.S)
            if found:
                out.update(v.replace("\\'", "'")
                           for v in re.findall(r"'((?:\\.|[^'])+)'", found.group(1)))
        for value in re.findall(r"note:\s*'((?:\\.|[^'])+)'", body):
            out.add(value.replace("\\'", "'"))

    markup = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    for tag in ("script", "style", "svg"):
        markup = re.sub(rf"<{tag}.*?</{tag}>", "", markup, flags=re.S)
    for attr in ("placeholder", "title", "aria-label"):
        out.update(re.findall(attr + r'="([^"]+)"', markup))
    for value in re.findall(r">([^<>{}]+)<", markup):
        out.add(html.unescape(value))

    sys.path.insert(0, ROOT)
    from kryonyx import plugins as catalog
    for plugin in catalog.CATALOG:
        out.add(plugin["description"])
        for field in plugin["settings"]:
            for key in ("label", "hint", "placeholder", "guide_title"):
                if field.get(key):
                    out.add(field[key])
            out.update(field.get("guide") or [])
            if (field.get("link") or {}).get("label"):
                out.add(field["link"]["label"])
    for _, name in catalog.CATEGORIES:
        out.add(name)

    clean = set()
    for value in out:
        value = flatten(value)
        if len(value) < 2 or not re.search(r"[A-Za-z]{2}", value):
            continue
        if SKIP.match(value) or re.fullmatch(r"[.#][\w-]+", value) or value == "· H / Esc":
            continue
        clean.add(value)
    # Explicitly audited dynamic keys complement the conservative HTML scanner.
    for relative in ('research/v12/i18n-ui-keys.json','research/v13/i18n-new-keys.json','research/v15/i18n-keys.json','research/tiktok-v39-ui-keys.json'):
        with open(os.path.join(ROOT,relative),encoding='utf-8') as handle:
            clean.update(json.load(handle))
    clean.update({"Player", "Hide extra interface", "Mute", "Unmute", "Translation timed out. Please retry."})
    return clean


def packs() -> dict[str, dict]:
    script = (
        "const fs=require('fs');const vm=require('vm');"
        "const path=require('path');const base=path.dirname(process.argv[1]);"
        "const html=fs.readFileSync(path.join(base,'../index.html'),'utf8');"
        r"const files=[...html.matchAll(/src=\"\/js\/(i18n[^\"?]*\.js)(?:\?[^\"]*)?\"/g)].map(m=>m[1]);"
        "const src=files.map(f=>fs.readFileSync(path.join(base,f),'utf8')).join('\\n');"
        "const box=vm.createContext({window:{},navigator:{language:'en'},"
        "document:{documentElement:{},body:null},NodeFilter:{SHOW_TEXT:4},"
        "S:{},addEventListener(){}});"
        "vm.runInContext(src+';globalThis.__P=PACKS;',box);"
        "process.stdout.write(JSON.stringify(box.__P));"
    )
    raw = subprocess.run(["node", "-e", script, os.path.join(WEB, "js", "i18n.js")],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(raw)


def main() -> None:
    # Normalize both sides identically. Protocol examples, template tokens and
    # keyboard chord notation are data, not translatable prose.
    strings = {flatten(html.unescape(s)) for s in collect()}
    strings = {s for s in strings if not re.match(r"^(?:# Netscape HTTP Cookie File|accept: \*/\*|Ctrl \+ Alt \+|\{\w+\}$)", s)}
    data = packs()
    report: dict[str, list[str]] = {}
    for lang, pack in data.items():
        keys = {flatten(k) for k in pack}
        lower = {k.lower() for k in keys}
        missing = sorted(s for s in strings
                         if s not in keys and s.lower() not in lower)
        report[lang] = missing

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--json" in sys.argv:
        target = sys.argv[sys.argv.index("--json") + 1]
        json.dump({"strings": sorted(strings), "missing": report},
                  open(target, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"written: {target}")
        return

    print(f"строк интерфейса: {len(strings)}\n")
    for lang in sorted(report):
        done = len(strings) - len(report[lang])
        print(f"  {lang}: {done}/{len(strings)} ({100 * done / max(1, len(strings)):.1f}%)")
    for lang in args:
        print(f"\n--- {lang}: не хватает {len(report.get(lang, []))} ---")
        for value in report.get(lang, []):
            print("  ", value)
    if "--check" in sys.argv and any(report.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
