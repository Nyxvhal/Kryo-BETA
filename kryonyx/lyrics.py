"""
lyrics.py — синхронный текст для караоке.

Здесь живёт вся работа со временем: разбор LRC, слова внутри строки и
интерлюдии. Задача — карточка как в Apple Music, где строка не просто
загорается целиком, а заливается слово за словом.

Что умеет модуль:
  * новый формат LRCLIB (`lyricsfile`, version 1.0) — там у строки есть и
    начало, и настоящий конец, а при наличии — слова с собственным временем;
  * обычный LRC     — `[00:12.34] строка`;
  * расширенный LRC — `[00:12.34] <00:12.34>сло<00:12.90>во` (формат A2,
    его отдаёт часть записей LRCLIB и почти все караоке-редакторы);
  * подбор времени слов, когда в исходнике только время строки: длительность
    делится по длине слов, поэтому пословная заливка есть у любого текста;
  * конец строки и паузы между строками: по ним интерфейс рисует точки
    отсчёта перед вступлением и в проигрышах.
"""

from __future__ import annotations

import re

# [mm:ss.xx] в начале строки (может быть несколько на одну строку текста).
LINE_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
# <mm:ss.xx> перед словом — расширенный LRC.
WORD_RE = re.compile(r"<(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?>")

# Границы для оценки длительности строки, когда следующей строки нет рядом.
MIN_LINE = 1.1
MAX_LINE = 9.0
CHAR_TIME = 0.085               # секунд на символ при оценке
# Пауза, начиная с которой показываем точки отсчёта (вступление, проигрыш).
GAP_MIN = 3.0
# Символы, которые не удлиняют слово при раскладке времени.
TRAIL = " \t.,!?;:—–-\"'»«()[]"


# --------------------------------------------------------------------------- #
# реклама и подписи источника внутри текста
# --------------------------------------------------------------------------- #
# В базах текстов попадаются строки, которых в песне нет: редакторы LRC и
# сайты-сборники подписывают свою работу прямо в тексте — «--- www.LRCgenerator.com ---»,
# «Synced by …», «Lyrics from AZLyrics». В караоке такая строка занимает место
# настоящей, да ещё и подсвечивается как спетая. Выкидываем её.
#
# Правил два набора, и это важно:
#   * is_promo()  — безошибочные признаки (ссылка, имя сборника, копирайт).
#     Такую строку убираем везде, где бы она ни стояла;
#   * is_credit() — «Synced by …», «Создано …»: похоже на подпись, но
#     «made by» встречается и в песнях. Поэтому мягкие правила работают
#     только по краям текста, где подписи и живут.
_PROMO_TRIM = " \t-–—=*_~·•.<>[](){}\"'«»|/\\#"
_PROMO_URL = re.compile(
    r"(?:https?://|www\.)|"
    r"\b[\w-]+\.(?:com|net|org|ru|io|co|me|info|biz|tv|xyz|site|online|top|pro)\b",
    re.I)
# Названия сервисов: встречается где угодно в строке.
_PROMO_NAMES = (
    "lrcgenerator", "lrclib", "lrcget", "megalobiz", "rentanadviser",
    "lyricsify", "lyricstranslate", "azlyrics", "musixmatch", "genius.com",
    "syair.info", "chartlyrics", "zaycev", "amalgama", "karafun",
    "karaoke version", "kugou", "netease",
)
_PROMO_COPY = re.compile(r"^(?:\(c\)|\(p\)|©|℗|copyright)", re.I)
# «Сделано кем-то»: только если строка этим и исчерпывается.
_PROMO_CREDIT = re.compile(
    r"^(?:lrc|lyrics?|text|sync(?:ed|hronised|hronized)?|timing|timed|tagged|"
    r"transcri(?:bed|ption)|translat(?:ed|ion)|subtitles?|edited|uploaded|"
    r"submitted|provided|corrected|aligned|generated|created|made)\b"
    r"[^.!?]{0,40}?\b(?:by|from)\b.{0,40}$", re.I)
# Та же подпись по-русски.
_PROMO_CREDIT_RU = re.compile(
    r"^(?:текст|перевод|синхрониз\w*|тайминг|субтитры)\b.{0,40}?"
    r"(?:\bот\b|\bавтор\w*|\bсайт\w*|:).{0,40}$", re.I)


def _core(text: str) -> str:
    return (text or "").strip().strip(_PROMO_TRIM).strip()


def is_promo(text: str) -> bool:
    """Строка — реклама или ссылка на источник, а не слова песни."""
    core = _core(text)
    if not core:
        return False                       # пустую строку решает вызывающий
    low = core.lower()
    if _PROMO_URL.search(low):
        return True
    if any(name in low for name in _PROMO_NAMES):
        return True
    return bool(len(core) <= 70 and _PROMO_COPY.match(low))


def is_credit(text: str) -> bool:
    """Строка похожа на подпись автора разметки («Synced by …»)."""
    core = _core(text)
    if not core or len(core) > 70:
        return False
    low = core.lower()
    return bool(_PROMO_CREDIT.match(low) or _PROMO_CREDIT_RU.match(low))


def clean(rows: list[dict]) -> list[dict]:
    """Убирает подписи источника: рекламу — везде, «… by …» — по краям.

    Край — две первые и две последние строки: дальше в середине песни такая
    формулировка почти наверняка часть текста.
    """
    rows = [row for row in rows if not is_promo(str(row.get("text") or ""))]
    for _ in range(2):                     # подписи бывают в две строки
        if rows and is_credit(str(rows[0].get("text") or "")):
            rows.pop(0)
        if rows and is_credit(str(rows[-1].get("text") or "")):
            rows.pop()
    return rows


def _stamp(mm: str, ss: str, frac: str | None) -> float:
    value = int(mm) * 60 + int(ss)
    if frac:
        value += int(frac.ljust(3, "0")) / 1000
    return round(value, 3)


def _split_words(text: str) -> list[str]:
    """Режем строку на слова, сохраняя пробелы в конце каждого куска."""
    return tokenize_text(text)


VOWELS = "aeiouyаеёиоуыэюяäöüåæøїієıâêîôû"


def _syllables(core: str) -> int:
    """Грубый счёт слогов: подряд идущие гласные считаем за одну."""
    count = 0
    previous = False
    for letter in core.lower():
        vowel = letter in VOWELS
        if vowel and not previous:
            count += 1
        previous = vowel
    return count


def _weight(word: str) -> float:
    """Вес слова при раскладке времени.

    Поётся не буква, а слог: «страсть» (1 слог, 7 букв) звучит короче, чем
    «обожаю» (4 слога, 6 букв). Поэтому основа веса — слоги, а длина слова
    добавляется лишь небольшой долей. Знаки препинания в конце дают паузу —
    заливка останавливается на запятой как в живом исполнении.
    """
    core = word.strip(TRAIL)
    if not core:
        return 1.0
    syllables = _syllables(core) or 1
    pause = 0.5 if word.strip() and word.strip()[-1] in ".,!?;:" else 0.0
    return syllables + len(core) * 0.12 + pause


# Сколько секунд в среднем поётся один слог. Нужно, чтобы слова не
# «растягивались» на всю паузу до следующей строки: голос замолкает раньше.
SYLLABLE_TIME = 0.32


def _spread(text: str, start: float, end: float) -> list[dict]:
    """Раскладывает время строки по словам пропорционально их длине."""
    words = _split_words(text)
    if not words:
        return []
    span = max(0.2, end - start)
    # Строка кончается там, где перестаёт звучать голос, а не там, где
    # начинается следующая. Если промежуток явно длиннее, чем можно спеть
    # этот текст, слова раскладываем по реальному темпу — иначе в режиме
    # «Диск» каждое слово выходило заметно позже, чем его слышно.
    singable = sum(_syllables(w.strip(TRAIL)) or 1 for w in words) * SYLLABLE_TIME
    if singable > 0.2:
        span = min(span, max(singable, 0.6))
    total = sum(_weight(w) for w in words)
    out: list[dict] = []
    at = start
    for word in words:
        share = span * _weight(word) / total
        out.append({"time": round(at, 3), "end": round(at + share, 3),
                    "text": word.strip(), "guessed": True})
        at += share
    out[-1]["end"] = round(min(end, at), 3)
    return out


def _parse_enhanced(body: str) -> tuple[str, list[dict]]:
    """Достаёт слова с собственным временем из расширенного LRC."""
    marks = list(WORD_RE.finditer(body))
    if not marks:
        return LINE_RE.sub("", body).strip(), []
    words: list[dict] = []
    for index, mark in enumerate(marks):
        tail = body[mark.end(): marks[index + 1].start()
                    if index + 1 < len(marks) else len(body)]
        chunk = tail.strip()
        if not chunk:
            continue
        words.append({"time": _stamp(*mark.groups()), "end": None, "text": chunk})
    text = WORD_RE.sub("", body).strip()
    return re.sub(r"\s+", " ", text), words


def parse_lrc(source: str) -> list[dict]:
    """LRC (обычный и расширенный) → строки со словами, без конца строки."""
    lines: list[dict] = []
    for raw in (source or "").splitlines():
        stamps = LINE_RE.findall(raw)
        if not stamps:
            continue
        body = LINE_RE.sub("", raw)
        text, words = _parse_enhanced(body)
        if not text or is_promo(text):
            continue
        for mm, ss, frac in stamps:
            start = _stamp(mm, ss, frac)
            shift = start - words[0]["time"] if words else 0.0
            lines.append({
                "time": start,
                "text": text,
                # Одна и та же строка может стоять в нескольких местах песни —
                # копируем слова со сдвигом, чтобы припев тоже светился.
                "words": [{**w, "time": round(w["time"] + shift, 3)} for w in words],
            })
    lines.sort(key=lambda item: item["time"])
    return lines


# --------------------------------------------------------------------------- #
# новый формат LRCLIB: lyricsfile version 1.0
# --------------------------------------------------------------------------- #
# LRCLIB отдаёт рядом с LRC ещё и структурный файл: у каждой строки есть
# start_ms и end_ms, пустые строки размечают проигрыши, а в записях с
# пословной синхронизацией появляется вложенный список words. Это точнее LRC,
# где конец строки приходится угадывать, поэтому используем файл в первую
# очередь. Разбор свой и нарочно простой: формат плоский, а тянуть в сборку
# YAML-парсер ради шести ключей не стоит.
_KEY_RE = re.compile(r"^(\s*)(?:-\s+)?([A-Za-z_]+):\s*(.*)$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner
    return value


def _ms(value: str) -> float | None:
    try:
        return round(int(str(value).strip()) / 1000, 3)
    except (TypeError, ValueError):
        return None


def parse_lyricsfile(source: str) -> list[dict]:
    """Строки (и слова, если они есть) из lyricsfile LRCLIB."""
    rows = (source or "").splitlines()
    try:
        head = next(i for i, row in enumerate(rows) if row.strip() == "lines:")
    except StopIteration:
        return []

    out: list[dict] = []
    current: dict | None = None
    in_words = False
    for row in rows[head + 1:]:
        if not row.strip():
            continue
        # Следующий раздел файла (например plain: |-) — список строк закончился.
        if not row.startswith((" ", "-")) and row.rstrip().endswith(":"):
            break
        found = _KEY_RE.match(row)
        if not found:
            continue
        indent, key, value = len(found.group(1)), found.group(2), found.group(3)
        item = row.lstrip().startswith("- ")

        if key == "text" and item and indent <= 0:
            current = {"text": _unquote(value), "time": None, "end": None, "words": []}
            out.append(current)
            in_words = False
            continue
        if current is None:
            continue
        if key == "words":
            in_words = True
            continue
        if in_words and key == "text" and item:
            current["words"].append({"text": _unquote(value), "time": None, "end": None})
            continue
        target = current["words"][-1] if (in_words and current["words"]) else current
        if key == "start_ms":
            target["time"] = _ms(value)
        elif key == "end_ms":
            target["end"] = _ms(value)

    lines: list[dict] = []
    for row in out:
        if row["time"] is None:
            continue
        # Пустая строка в файле — это проигрыш: текста нет, но время занято.
        # Такие строки не показываем, их место само станет паузой (gap).
        if not row["text"].strip() or is_promo(row["text"]):
            continue
        row["words"] = [w for w in row["words"]
                        if w.get("text") and w.get("time") is not None]
        lines.append(row)
    lines.sort(key=lambda entry: entry["time"])
    return lines


def _estimate_end(line: dict, next_time: float | None) -> float:
    """Конец строки: до следующей, но не дольше разумного для её длины."""
    guess = line["time"] + min(MAX_LINE,
                               max(MIN_LINE, len(line["text"]) * CHAR_TIME))
    if next_time is None:
        return round(guess, 3)
    return round(min(next_time, max(line["time"] + MIN_LINE, guess)), 3)


def finish(lines: list[dict], duration: float | None = None) -> list[dict]:
    """Доводит строки до вида, нужного интерфейсу.

    Появляются `end` у строки и у каждого слова, подобранное время слов там,
    где его не было, и `gap` — пауза перед строкой (для точек отсчёта).
    """
    out: list[dict] = []
    for index, line in enumerate(lines):
        nxt = lines[index + 1]["time"] if index + 1 < len(lines) else (
            float(duration) if duration else None)
        # Настоящий конец строки из lyricsfile точнее любой оценки.
        given = line.get("end")
        end = round(float(given), 3) if given else _estimate_end(line, nxt)
        if nxt and end > nxt:
            end = round(nxt, 3)
        if end <= line["time"]:
            end = _estimate_end(line, nxt)
        words = [w for w in (line.get("words") or []) if w.get("text")]
        if words:
            for position, word in enumerate(words):
                word["end"] = round(float(word["end"]) if word.get("end") is not None else (
                    words[position + 1]["time"] if position + 1 < len(words)
                    else max(end, word["time"] + 0.45)), 3)
                # Расширенный LRC иногда ставит метки только на части строки.
                if word["end"] <= word["time"]:
                    word["end"] = round(word["time"] + 0.25, 3)
            end = max(end, words[-1]["end"])
        else:
            words = _spread(line["text"], line["time"], end)
        out.append({
            "time": round(line["time"], 3),
            "end": round(end, 3),
            "text": line["text"],
            "words": words,
        })

    for index, line in enumerate(out):
        previous_end = out[index - 1]["end"] if index else 0.0
        gap = round(line["time"] - previous_end, 3)
        line["gap"] = gap if gap >= GAP_MIN else 0.0
    return out


def build(synced: str = "", plain: str = "",
          duration: float | None = None, lyricsfile: str = "") -> dict:
    """Готовый ответ для /api/lyrics.

    Порядок источников: lyricsfile (точные границы строк и, если есть, слова),
    затем LRC, затем обычный текст.
    """
    rows = parse_lyricsfile(lyricsfile) if lyricsfile else []
    if not rows and synced:
        rows = parse_lrc(synced)
    # Подписи редактора LRC выкидываем до раскладки времени: иначе на них
    # уходит доля секунды песни, а в караоке они ещё и подсвечиваются.
    rows = clean(rows)
    lines = finish(rows, duration) if rows else []
    if lines:
        return {
            "lines": lines,
            "synced": True,
            # Слова из исходника ценнее подобранных — интерфейс это показывает.
            "words": any(not w.get("guessed")
                         for line in lines for w in line["words"]),
        }
    text_lines = [row["text"] for row in clean(
        [{"text": row.strip()} for row in (plain or "").splitlines() if row.strip()])]
    return {
        "lines": [{"time": None, "end": None, "text": row, "words": [], "gap": 0.0}
                  for row in text_lines],
        "synced": False,
        "words": False,
    }


# --------------------------------------------------------------------------- #
# названия треков → запросы к базе текстов
# --------------------------------------------------------------------------- #
# Треки приезжают с YouTube и SoundCloud, где название — это заголовок
# видео: «Marino - Rip Out Your Eyes (Official Lyrics Video)», «… | prod. by
# …», «… (sped up)». В базах текстов запись называется просто «Rip Out Your
# Eyes», поэтому поиск по сырому заголовку не находил НИЧЕГО. Здесь заголовок
# разбирается на варианты запроса: от самого точного к самому короткому.

# Служебные слова видео: скобка с таким содержимым к названию песни не относится.
_NOISE = (
    "official video", "official music video", "official audio",
    "official lyric video", "official lyrics video", "official visualizer",
    "official visualiser", "official", "music video", "lyric video",
    "lyrics video", "lyrics", "lyric", "audio only", "audio", "visualizer",
    "visualiser", "video", "hd", "hq", "4k", "8k", "explicit", "clean",
    "free download", "download", "out now", "premiere", "full album",
    "color coded", "sub español", "subtitulado", "с переводом", "перевод",
    "текст песни", "клип",
)
# А такие скобки менять нельзя: это другая запись песни.
_VERSION = (
    "remix", "extended", "sped up", "slowed", "acoustic", "live",
    "instrumental", "cover", "demo", "edit", "mix", "version", "remaster",
    "reverb", "nightcore", "vip", "bootleg", "radio", "club", "rework",
)
_BRACKET = re.compile(r"\s*[\(\[\{]([^\(\)\[\]\{\}]*)[\)\]\}]")
# «feat. X», «ft X», «с участием X» — до конца названия или до скобки.
_FEAT = re.compile(r"\s*(?:feat\.?|ft\.?|featuring|with|prod\.?(?:\s*by)?|"
                   r"с участием)\s+[^()\[\]]*$", re.I)
# Хвосты канала: «… | Official Video», «… // out now».
_TAIL = re.compile(r"\s*(?:\||//|—\s*$)")
# Приписки к имени канала.
_CHANNEL = re.compile(r"\s*(?:-\s*topic|vevo|official|music|records|"
                      r"recordings|entertainment|tv|channel)\s*$", re.I)


def _drop_brackets(text: str, keep_version: bool) -> str:
    """Убирает служебные скобки. keep_version — сохранить «(remix)» и подобные."""
    def repl(found: re.Match) -> str:
        inner = found.group(1).strip().lower()
        if not inner:
            return " "
        version = any(word in inner for word in _VERSION)
        if version:
            return found.group(0) if keep_version else " "
        if any(word in inner for word in _NOISE):
            return " "
        if inner.startswith(("prod", "feat", "ft ", "ft.", "dir", "©", "℗")):
            return " "
        # Скобка с непонятным содержимым: оставляем в точном варианте.
        return found.group(0) if keep_version else " "
    return _BRACKET.sub(repl, text)


def _tidy(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\"“”«»]", "", text)
    text = re.sub(r"\s*[-–—]\s*$", "", text)
    return re.sub(r"\s{2,}", " ", text).strip(" -–—,·:;")


def clean_artist(artist: str) -> str:
    """Имя исполнителя без приписок канала и без списка соавторов."""
    value = _tidy(_CHANNEL.sub("", _drop_brackets(artist or "", False)))
    # «A, B & C» и «A x B» — в базе запись обычно на первом исполнителе.
    value = re.split(r"\s*(?:,|&|\bx\b|\bvs\.?\b|\bfeat\.?\b|\bft\.?\b)\s*",
                     value, maxsplit=1)[0]
    return _tidy(value)


def query_variants(title: str, artist: str) -> list[tuple[str, str]]:
    """Варианты (название, исполнитель) для поиска текста, от точного к общему.

    Сырой заголовок идёт первым: если запись в базе названа именно так,
    находим её сразу. Дальше отрезаем служебные скобки, хвосты канала,
    «feat.» и приставку «Исполнитель - », и в самом конце пробуем одно
    короткое название без исполнителя.
    """
    title = (title or "").strip()
    artist = (artist or "").strip()
    if not title:
        return []
    performer = clean_artist(artist)

    # Хвост после «|» или «//» к названию песни не относится.
    head = _TAIL.split(title)[0] if _TAIL.search(title) else title
    # Длинное тире в заголовках YouTube значит то же, что дефис.
    head = re.sub(r"\s+[–—]\s+", " - ", head)
    exact = _tidy(_drop_brackets(head, True))        # «Rip Out Your Eyes (extended)»
    bare = _tidy(_drop_brackets(head, False))        # «Rip Out Your Eyes»
    bare = _tidy(_FEAT.sub("", bare)) or bare
    exact = _tidy(_FEAT.sub("", exact)) or exact

    out: list[tuple[str, str]] = [(title, artist)]

    def add(name: str, who: str) -> None:
        name, who = _tidy(name), _tidy(who)
        if not name or len(name) < 2:
            return
        if (name, who) not in out:
            out.append((name, who))

    for name in (exact, bare):
        add(name, performer)
        add(name, artist)
        # «Исполнитель - Песня»: в заголовках YouTube это норма.
        for source in (name,):
            if " - " not in source:
                continue
            left, right = source.split(" - ", 1)
            left, right = _tidy(left), _tidy(right)
            if not right:
                continue
            # Слева обычно исполнитель. Если он совпал с известным — тем лучше.
            add(right, performer or left)
            if left.lower() != (performer or "").lower():
                add(right, left)
    add(bare, "")
    return out

# Karaoke JSON v2 is a lossless interchange document; renderer adapters use
# `time` aliases, never overwrite the original start/end timestamps.
import copy
import json
import math
import xml.etree.ElementTree as ET


def karaoke_document(value: dict) -> dict:
    """Validate editable v2 data, retaining extension keys and nested metadata."""
    if not isinstance(value, dict) or value.get('version') != 2:
        raise ValueError('Expected Karaoke JSON version 2')
    doc = copy.deepcopy(value)
    total = 0

    def stamp(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > 86400:
            raise ValueError('Timestamps must be finite seconds in 0..86400')
        return float(v)

    def units(rows, parent=None, kind='lines'):
        nonlocal total
        if not isinstance(rows, list) or len(rows) > 20000:
            raise ValueError('Expected a bounded list of timing units')
        previous = -1.0
        for row in rows:
            total += 1
            if total > 100000 or not isinstance(row, dict) or not isinstance(row.get('text'), str):
                raise ValueError('Invalid or excessive lyric data')
            if len(row['text']) > 20000:
                raise ValueError('Lyric text is too long')
            a, b = stamp(row.get('start')), stamp(row.get('end'))
            if b < a or a < previous:
                raise ValueError('Timing units must be ordered with end >= start')
            if parent and (a < parent[0] - .001 or b > parent[1] + .001):
                raise ValueError('Child timings must lie inside their parent')
            previous = a
            if 'confidence' in row:
                c = row['confidence']
                if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c) or not 0 <= c <= 1:
                    raise ValueError('Confidence must lie in 0..1')
            if kind == 'words' and 'words' in row: raise ValueError('Words cannot contain words')
            for key in ('words', 'syllables'):
                if key in row: units(row[key], (a, b), key)
            if kind == 'syllables' and ('words' in row or 'syllables' in row):
                raise ValueError('Syllables cannot contain recursive timing units')
    units(doc.get('lines'))
    variants = doc.get('variants', [])
    if not isinstance(variants, list) or len(variants) > 20:
        raise ValueError('At most 20 lyric variants are supported')
    for variant in variants:
        if not isinstance(variant, dict): raise ValueError('Invalid variant')
        units(variant.get('lines'))
    for section in doc.get('sections', []):
        if not isinstance(section, dict) or stamp(section.get('end')) < stamp(section.get('start')):
            raise ValueError('Invalid vocal/instrumental section')
    return doc


def karaoke_payload(value: dict, variant: str = '') -> dict:
    doc = karaoke_document(value)
    chosen = doc
    if variant:
        chosen = next((v for v in doc.get('variants', []) if str(v.get('id')) == variant), None)
        if chosen is None: raise ValueError('Unknown lyric variant')
    rows = []
    for line in chosen['lines']:
        row = copy.deepcopy(line)
        row['time'] = row['start']
        for word in row.get('words', []):
            word['time'] = word['start']
            for syllable in word.get('syllables', []): syllable['time'] = syllable['start']
        row['gap'] = max(0, row['start'] - (rows[-1]['end'] if rows else 0))
        rows.append(row)
    from .karaoke_quality import assess
    return {'quality': assess(doc), 'lines': rows, 'synced': bool(rows), 'words': any(r.get('words') for r in rows),
            'version': 2, 'precise': True, 'source': 'karaoke-json', 'document': doc,
            'language': chosen.get('language', doc.get('language', 'und')),
            'duration': doc.get('duration'), 'variants': [{k: v.get(k) for k in ('id','label','language')} for v in doc.get('variants', [])]}


def tokenize_text(text: str) -> list[str]:
    """CJK fallback: Unicode codepoints, never fabricated acoustic timestamps.

    Model-aligned tokens are retained verbatim. This splitter is used only
    for legacy line-timed interpolation, marked guessed=True.
    """
    return re.findall(r'[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]|[^\s\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+\s*', text)


def _subtitle_time(value: str) -> float:
    value = value.strip().replace(',', '.')
    match = re.fullmatch(r'(\d+(?:\.\d+)?)(ms|s|m|h)', value)
    if match: return float(match[1]) * {'ms':.001,'s':1,'m':60,'h':3600}[match[2]]
    parts = value.split(':')
    if not 1 <= len(parts) <= 3: raise ValueError('Unsupported subtitle time')
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def parse_subtitle(source: str, filename: str = '') -> dict:
    """Import JSON v2, LRC/enhanced LRC, SRT, basic timed TTML or plain text."""
    source = source.lstrip('\ufeff')
    suffix = filename.lower().rsplit('.',1)[-1]
    if suffix == 'json' or source.lstrip().startswith('{'):
        return karaoke_payload(json.loads(source))
    if suffix in ('ttml','xml') or source.lstrip().startswith('<tt'):
        if '<!DOCTYPE' in source.upper() or '<!ENTITY' in source.upper():
            raise ValueError('XML entities/DOCTYPE are not allowed')
        root = ET.fromstring(source)
        rows = []
        for node in root.iter():
            if node.tag.rsplit('}',1)[-1] not in ('p','span') and any(k in node.attrib for k in ('begin','end','dur')):
                raise ValueError('Nested timed TTML containers are not supported; import Karaoke JSON instead')
        # Supports seconds/clock timing, timed p and inline spans. Nested timed
        # containers/frame/tick time bases are deliberately rejected.
        for node in root.iter():
            if node.tag.rsplit('}',1)[-1] != 'p': continue
            if 'begin' not in node.attrib: continue
            a = _subtitle_time(node.attrib['begin'])
            b = _subtitle_time(node.attrib['end']) if 'end' in node.attrib else a + _subtitle_time(node.attrib.get('dur','0s'))
            words=[]
            for span in node:
                if span.tag.rsplit('}',1)[-1] == 'span' and 'begin' in span.attrib:
                    x=a+_subtitle_time(span.attrib['begin'])
                    y=a+_subtitle_time(span.attrib['end']) if 'end' in span.attrib else x+_subtitle_time(span.attrib.get('dur','0s'))
                    words.append({'text':''.join(span.itertext()),'start':x,'end':y})
            rows.append({'text':''.join(node.itertext()),'start':a,'end':b,'words':words})
        return karaoke_payload({'version':2,'language':'und','lines':rows,'timing_source':'ttml'})
    if suffix == 'srt' or '-->' in source:
        rows=[]
        for block in re.split(r'\n\s*\n',source.strip()):
            lines=block.splitlines()
            for i,line in enumerate(lines):
                if '-->' not in line: continue
                left,right=line.split('-->',1)
                a,b=_subtitle_time(left),_subtitle_time(right.strip().split()[0])
                rows.append({'text':'\n'.join(lines[i+1:]),'start':a,'end':b})
                break
        return karaoke_payload({'version':2,'language':'und','lines':rows,'timing_source':'srt'})
    return build(source, source)
