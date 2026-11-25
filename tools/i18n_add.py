"""i18n_add.py — добавляет переводы в web/js/i18n.js.

На входе JSON вида {"ru": {"English string": "Перевод", ...}, "de": {...}}.
Существующие ключи не трогаются, новые дописываются в конец нужного пакета.

    python tools/i18n_add.py new.json
"""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "kryonyx", "web", "js", "i18n.js")


def quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def main() -> None:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    body = open(TARGET, encoding="utf-8").read()
    report = []
    for lang, pairs in data.items():
        head = f"\n  {lang}: {{"
        start = body.index(head) + len(head)
        # конец пакета: строка "\n  }," на том же уровне вложенности
        end = body.index("\n  },", start)
        chunk = body[start:end]
        have = {v for _, v in re.findall(r"(['\"])((?:\\.|(?!\1).)*)\1\s*:", chunk)}
        lines = []
        for english, translated in pairs.items():
            if english.replace("'", "\\'") in have or english in have:
                continue
            if not translated:
                continue
            lines.append(f"    {quote(english)}: {quote(translated)},")
        if not lines:
            report.append(f"{lang}: нечего добавлять")
            continue
        addition = "\n    /* дополнено tools/i18n_add.py */\n" + "\n".join(lines) + "\n"
        body = body[:end] + addition + body[end:]
        report.append(f"{lang}: +{len(lines)}")
    open(TARGET, "w", encoding="utf-8").write(body)
    print("\n".join(report))


if __name__ == "__main__":
    main()
