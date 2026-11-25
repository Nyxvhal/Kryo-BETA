"""
ytcookies.py — cookies YouTube для yt-dlp.

Зачем это нужно. YouTube всё чаще отвечает «Sign in to confirm you're not a
bot»: домашний адрес, VPN, дата-центр — и поток не отдаётся никому, кто не
похож на залогиненный браузер. Единственное, что эту проверку снимает
надёжно, — cookies живой сессии. yt-dlp умеет читать их из файла
(`--cookies`) или прямо из браузера (`--cookies-from-browser`).

Модуль даёт одну точку входа для обоих путей:

  * `save(raw)`     — принимает что угодно: готовый файл Netscape, экспорт
                      Cookie-Editor (JSON), заголовок «Cookie: a=1; b=2» или
                      просто «a=1; b=2» — и пишет один файл в формате Netscape;
  * `path()`        — путь к файлу для аргумента `--cookies` (учитывает и
                      старые места: youtube_cookies.txt рядом с программой);
  * `browser()`     — выбранный браузер для `--cookies-from-browser`;
  * `state()`       — что показать в настройках: есть ли cookies, сколько их,
                      когда обновлены, виден ли признак входа (SAPISID).

Файл лежит в папке данных приложения правами только текущего пользователя:
cookies — это доступ к аккаунту, разбрасывать их нельзя.
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
import time

from .paths import app_dir, data_dir

log = logging.getLogger("kryonyx.ytcookies")

FILE = "youtube_cookies.txt"
META = "youtube_cookies.json"
# Старые места: файл, положенный рядом с программой руками. Их не трогаем,
# только читаем — у кого так настроено, у того и продолжит работать.
LEGACY = ("youtube_cookies.txt", "cookies.txt")
# Браузеры, из которых yt-dlp умеет забирать cookies сам.
BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi",
            "chromium", "safari", "whale")
# Признак того, что в cookies есть вход в аккаунт, а не просто сессия гостя.
SIGNED_IN = ("SAPISID", "__Secure-3PAPISID", "SID", "__Secure-1PSID")

_HEADER = ("# Netscape HTTP Cookie File\n"
           "# Written by Kryo. Do not edit by hand.\n")


# --------------------------------------------------------------------------- #
# пути
# --------------------------------------------------------------------------- #
def own_path() -> str:
    """Файл, которым управляет приложение."""
    return os.path.join(data_dir(), FILE)


def _meta_path() -> str:
    return os.path.join(data_dir(), META)


def path() -> str | None:
    """Файл cookies для `--cookies` или None."""
    mine = own_path()
    if os.path.isfile(mine) and os.path.getsize(mine) > len(_HEADER):
        return mine
    for folder in (app_dir(), os.getcwd()):
        for name in LEGACY:
            candidate = os.path.join(folder, name)
            if os.path.isfile(candidate):
                return candidate
    return None


# --------------------------------------------------------------------------- #
# разбор того, что вставил пользователь
# --------------------------------------------------------------------------- #
_PAIR = re.compile(r"\s*([^=;,\s]+)\s*=\s*([^;]*)")


def _from_header(raw: str) -> list[tuple[str, str]]:
    """«Cookie: a=1; b=2» или просто «a=1; b=2» → пары."""
    text = raw.strip()
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1]
    out: list[tuple[str, str]] = []
    for chunk in text.split(";"):
        found = _PAIR.match(chunk)
        if not found:
            continue
        name, value = found.group(1).strip(), found.group(2).strip()
        if name and value:
            out.append((name, value))
    return out


# Куки считаются «нашими», если домен принадлежит YouTube или Google: вход в
# аккаунт лежит именно там. Остальное (чужие сайты) отбрасывается при записи.
_OURS = ("youtube.com", "google.com", "youtube-nocookie.com", "googlevideo.com")
_AUTH = ("SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID", "__Secure-3PSID",
         "__Secure-1PAPISID", "__Secure-3PAPISID")


def _looks_netscape(raw: str) -> bool:
    for line in raw.splitlines():
        line = line.strip()
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        return len(line.split("\t")) >= 6
    return False


def _ours(domain: str | None) -> bool:
    if not domain:
        return True                       # заголовок Cookie: домена нет, берём как есть
    host = domain.lstrip(".").lower()
    return any(host == d or host.endswith("." + d) or ("." + d + ".") in ("." + host + ".")
               for d in _OURS) or host.startswith(("google.", "www.google."))


def _entries(raw: str) -> tuple[str, list[dict]]:
    """Текст в любом формате → (формат, [{domain,name,value,expires,path,secure,http}])."""
    text = (raw or "").strip()
    if not text:
        return "empty", []
    if text[:1] in "[{":
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        items = data.get("cookies") if isinstance(data, dict) else data
        if isinstance(items, list):
            out = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                value = str(item.get("value") or "").strip()
                if not (name and value):
                    continue
                exp = item.get("expirationDate", item.get("expires"))
                try:
                    exp = int(float(exp)) if exp not in (None, "", -1) else 0
                except (TypeError, ValueError):
                    exp = 0
                out.append({"domain": str(item.get("domain") or "").strip() or None,
                            "name": name, "value": value, "expires": exp,
                            "path": str(item.get("path") or "/"),
                            "secure": bool(item.get("secure", True)),
                            "http": bool(item.get("httpOnly"))})
            return "json", out
    if _looks_netscape(text):
        out = []
        for line in text.splitlines():
            line = line.rstrip("\r\n")
            http = line.startswith("#HttpOnly_")
            if http:
                line = line[len("#HttpOnly_"):]
            elif not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            try:
                exp = int(parts[4] or 0)
            except ValueError:
                exp = 0
            out.append({"domain": parts[0], "name": parts[5], "value": parts[6],
                        "expires": exp, "path": parts[2] or "/",
                        "secure": parts[3].upper() == "TRUE", "http": http})
        return "netscape", out
    return "header", [{"domain": None, "name": n, "value": v, "expires": 0,
                       "path": "/", "secure": True, "http": False}
                      for n, v in _from_header(text)]


def _expired(entry: dict) -> bool:
    return 0 < entry["expires"] < time.time()


def analyze(raw: str) -> dict:
    """Проверка вставленного текста до записи: те ли это куки и годятся ли."""
    fmt, items = _entries(raw)
    mine = [e for e in items if _ours(e["domain"])]
    foreign = sorted({(e["domain"] or "").lstrip(".") for e in items if not _ours(e["domain"])})
    alive = [e for e in mine if not _expired(e)]
    names = {e["name"] for e in alive}
    auth = [n for n in _AUTH if n in names]
    problems: list[str] = []
    if not items:
        problems.append("empty")
    elif not mine:
        problems.append("wrong_site")
    else:
        if not auth:
            problems.append("expired" if any(e["name"] in _AUTH for e in mine) else "not_signed_in")
        if "LOGIN_INFO" not in names:
            problems.append("no_login_info")
        if len(mine) < 5:
            problems.append("few")
    if foreign and mine:
        problems.append("foreign")
    fatal = {"empty", "wrong_site", "not_signed_in", "expired"}
    return {"format": fmt, "total": len(items), "youtube": len(mine), "foreign": foreign[:8],
            "auth": auth, "login_info": "LOGIN_INFO" in names, "problems": problems,
            "ok": not (fatal & set(problems))}


def _emit(items: list[dict]) -> str:
    """Записи → файл Netscape. У заголовочных кук домена нет — кладём на оба."""
    far = int(time.time()) + 365 * 24 * 3600
    rows, seen = [_HEADER], set()
    for e in items:
        domains = [e["domain"]] if e["domain"] else [".youtube.com", ".google.com"]
        for domain in domains:
            if (domain, e["name"], e["path"]) in seen:
                continue
            seen.add((domain, e["name"], e["path"]))
            exp = e["expires"] if e["expires"] > 0 else far
            sub = "TRUE" if domain.startswith(".") else "FALSE"
            prefix = "#HttpOnly_" if e["http"] else ""
            rows.append(f"{prefix}{domain}\t{sub}\t{e['path']}\t"
                        f"{'TRUE' if e['secure'] else 'FALSE'}\t{exp}\t{e['name']}\t{e['value']}\n")
    return "".join(rows)


def _count(text: str) -> int:
    return len(_entries(text)[1])


def _names(text: str) -> set[str]:
    return {e["name"] for e in _entries(text)[1] if not _expired(e)}


def parse(raw: str) -> str:
    """Любой из поддерживаемых форматов → содержимое файла Netscape.
    Чужие сайты отбрасываются; если своих нет — это не те куки."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("paste the cookies first")
    fmt, items = _entries(raw)
    if not items:
        raise ValueError("could not find any cookies in this text")
    mine = [e for e in items if _ours(e["domain"])]
    if not mine:
        raise ValueError("these are not YouTube cookies: " +
                         ", ".join(sorted({(e["domain"] or "").lstrip(".") for e in items})[:4]))
    return _emit(mine)


# --------------------------------------------------------------------------- #
# запись и состояние
# --------------------------------------------------------------------------- #
def _write_meta(data: dict) -> None:
    try:
        with open(_meta_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except OSError:
        pass


def _read_meta() -> dict:
    try:
        with open(_meta_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(raw: str, source: str = "manual") -> dict:
    """Сохраняет cookies и возвращает новое состояние."""
    body = parse(raw)
    target = own_path()
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    os.replace(tmp, target)
    try:                                   # cookies — это доступ к аккаунту
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    _write_meta({"at": time.time(), "source": source, "count": _count(body)})
    log.info("[cookies] saved %d cookies (%s)", _count(body), source)
    return state()


def clear() -> dict:
    for target in (own_path(), _meta_path()):
        try:
            os.remove(target)
        except OSError:
            pass
    return state()


def from_headers(headers: dict | str) -> dict | None:
    """Cookies из заголовков входа в YouTube Music — чтобы yt-dlp тоже ожил.

    Один вход закрывает сразу две задачи: личные рекомендации и бот-проверку
    при получении звука.
    """
    raw = ""
    if isinstance(headers, dict):
        for key, value in headers.items():
            if str(key).lower() == "cookie":
                raw = str(value)
                break
    else:
        raw = str(headers or "")
    if not raw.strip():
        return None
    try:
        return save(raw, source="ytmusic")
    except Exception as exc:                            # не ломаем сам вход
        log.warning("[cookies] could not reuse the YouTube Music cookies: %s", exc)
        return None


def browser() -> str:
    """Браузер для `--cookies-from-browser` («» — не задан)."""
    try:
        from . import storage
        value = str(storage.get_settings().get("ytCookieBrowser") or "").strip().lower()
    except Exception:
        value = ""
    return value if value in BROWSERS else ""


def set_browser(name: str) -> str:
    name = (name or "").strip().lower()
    if name and name not in BROWSERS:
        raise ValueError("unknown browser: " + name)
    from . import storage
    storage.save_settings({"ytCookieBrowser": name})
    return name


def state() -> dict:
    target = path()
    text = ""
    if target:
        try:
            with open(target, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
    meta = _read_meta()
    names = _names(text)
    return {
        "present": bool(text.strip()),
        "own": bool(target and os.path.samefile(target, own_path())
                    if target and os.path.isfile(own_path()) else False),
        "path": target or own_path(),
        "count": _count(text),
        "signed_in": any(name in names for name in SIGNED_IN),
        "login_info": "LOGIN_INFO" in names,
        "expired": bool(text.strip()) and not any(n in names for n in _AUTH),
        "updated_at": int(meta.get("at") or (os.path.getmtime(target) if target else 0)),
        "source": meta.get("source") or ("file" if target else ""),
        "browser": browser(),
        "browsers": list(BROWSERS),
    }
