"""
netproxy.py — прокси / VPN для всех сетевых запросов приложения.

Три режима (Настройки → Библиотеки → Прокси / VPN):

  * off     — напрямую, как раньше;
  * system  — настройки системы: прокси из Windows/macOS/переменных окружения.
              Подходит, когда VPN-клиент (или корпоративная сеть) сам выставил
              системный прокси. Полноценный VPN на уровне системы
              (WireGuard, OpenVPN, Cloudflare WARP и т.п.) работает и без
              настройки: он ведёт весь трафик, в том числе наш;
  * custom  — свой прокси: http://, https://, socks5:// или socks4://,
              можно с логином: socks5://user:pass@host:1080. Так подключается
              и VPN, который открывает локальный прокси (127.0.0.1:порт).

Один и тот же выбор применяется ко всему, что ходит в сеть:
  * aiohttp-сессии (поиск, Piped/Invidious, innertube, поток клипа);
  * yt-dlp (бинарник и встроенная библиотека) — через `--proxy`;
  * ytmusicapi и pytubefix — через их параметр proxies.
Адреса 127.0.0.1/localhost никогда не проксируются: окно приложения говорит
с локальным сервером напрямую.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from .paths import data_dir

log = logging.getLogger("kryonyx.netproxy")

FILE = "network_proxy.json"
MODES = ("off", "system", "custom")
SCHEMES = ("http", "https", "socks5", "socks5h", "socks4", "socks4a")

_conf: dict[str, Any] | None = None
_touched = False        # были ли мы в custom: только тогда off чистит окружение
generation = 0          # растёт при каждой смене настроек: сессии пересоздаются


def _path() -> str:
    return os.path.join(data_dir(), FILE)


def _load() -> dict[str, Any]:
    global _conf
    if _conf is None:
        try:
            with open(_path(), encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            raw = {}
        mode = str(raw.get("mode") or "off")
        _conf = {"mode": mode if mode in MODES else "off",
                 "url": str(raw.get("url") or "").strip()}
    return _conf


def normalize(value: str) -> str:
    """'host:port' -> 'http://host:port'; проверяет схему и порт."""
    text = (value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in SCHEMES:
        raise ValueError("Use http://, https://, socks5:// or socks4://")
    if not parts.hostname:
        raise ValueError("The proxy address has no host")
    try:
        port = parts.port
    except ValueError:
        raise ValueError("The proxy port is not a number") from None
    if not port:
        raise ValueError("Add the proxy port, for example 127.0.0.1:1080")
    auth = ""
    if parts.username:
        auth = quote(unquote(parts.username), safe="")
        if parts.password:
            auth += ":" + quote(unquote(parts.password), safe="")
        auth += "@"
    host = parts.hostname if ":" not in parts.hostname else f"[{parts.hostname}]"
    return f"{scheme}://{auth}{host}:{port}"


def _system_url() -> str:
    """Прокси ОС (реестр Windows, scutil на macOS, переменные окружения)."""
    try:
        found = urllib.request.getproxies()
    except Exception:
        return ""
    for key in ("https", "all", "http", "socks"):
        value = str(found.get(key) or "").strip()
        if value:
            try:
                return normalize(value if "://" in value else "http://" + value)
            except ValueError:
                continue
    return ""


def mode() -> str:
    return _load()["mode"]


def url() -> str:
    """Прокси, который сейчас нужно использовать, или пустая строка."""
    conf = _load()
    if conf["mode"] == "custom":
        return conf["url"]
    if conf["mode"] == "system":
        return _system_url()
    return ""


def display(value: str) -> str:
    """Адрес без пароля — для показа в окне и журнале."""
    try:
        parts = urlsplit(value)
        if parts.username:
            return value.replace(parts.netloc, "***@" + parts.netloc.rsplit("@", 1)[-1])
    except Exception:
        pass
    return value


def apply_env() -> None:
    """Выставляет переменные окружения для всего, что читает их само.

    requests (ytmusicapi, pytubefix), urllib и бинарник yt-dlp, запущенный
    дочерним процессом, подхватывают прокси отсюда. Локальные адреса
    исключаем всегда.
    """
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
            "http_proxy", "https_proxy", "all_proxy")
    global _touched
    if _load()["mode"] == "custom" and _load()["url"]:
        _touched = True
        for key in keys:
            os.environ[key] = _load()["url"]
    elif _load()["mode"] == "off" and _touched:
        # Выключили то, что сами выставили, — не трогая чужое окружение.
        for key in keys:
            os.environ.pop(key, None)
    local = "127.0.0.1,localhost,::1"
    for key in ("NO_PROXY", "no_proxy"):
        have = os.environ.get(key, "")
        if "127.0.0.1" not in have:
            os.environ[key] = (have + "," if have else "") + local


def configure(new_mode: str, new_url: str = "") -> dict[str, Any]:
    """Сохраняет выбор и сбрасывает всё, что держит старое соединение."""
    global _conf, generation, _touched
    new_mode = (new_mode or "off").strip().lower()
    if "***@" in (new_url or "") and _load()["url"]:
        new_url = _load()["url"]          # окно не знает пароля: оставляем прежний
    if new_mode not in MODES:
        raise ValueError("Unknown proxy mode")
    cleaned = normalize(new_url) if new_mode == "custom" else (
        normalize(new_url) if (new_url or "").strip() else "")
    if new_mode == "custom" and not cleaned:
        raise ValueError("Enter the proxy address first")
    _touched = _touched or _load()["mode"] == "custom"
    _conf = {"mode": new_mode, "url": cleaned}
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_conf, fh)
    try:
        os.chmod(tmp, 0o600)        # в адресе может быть пароль
    except OSError:
        pass
    os.replace(tmp, _path())
    generation += 1
    apply_env()
    log.info("[proxy] mode=%s %s", new_mode, display(url()) or "-")
    return state()


def state() -> dict[str, Any]:
    conf = _load()
    effective = url()
    return {
        "mode": conf["mode"],
        "url": display(conf["url"]) if conf["url"] else "",
        "has_password": bool(conf["url"] and urlsplit(conf["url"]).password),
        "effective": display(effective),
        "system_found": bool(_system_url()),
        "socks_ready": socks_ready(),
    }


# --------------------------------------------------------------------------- #
# для aiohttp
# --------------------------------------------------------------------------- #
def socks_ready() -> bool:
    try:
        import aiohttp_socks  # noqa: F401
        return True
    except Exception:
        return False


def session_kwargs() -> dict[str, Any]:
    """Аргументы для aiohttp.ClientSession: коннектор прокси или trust_env."""
    proxy = url()
    if not proxy:
        return {"trust_env": _load()["mode"] == "system"}
    try:
        from aiohttp_socks import ProxyConnector
        return {"connector": ProxyConnector.from_url(proxy, rdns=True)}
    except ImportError:
        if proxy.lower().startswith(("http://", "https://")):
            # Без aiohttp-socks http-прокси достаётся через окружение.
            apply_env()
            return {"trust_env": True}
        log.warning("[proxy] aiohttp-socks is not installed: %s is ignored",
                    display(proxy))
        return {}
    except Exception as exc:
        log.warning("[proxy] cannot use %s: %s", display(proxy), exc)
        return {}


def ytdlp_args() -> tuple[str, ...]:
    proxy = url()
    return ("--proxy", proxy) if proxy else ()


def requests_proxies() -> dict[str, str] | None:
    proxy = url()
    return {"http": proxy, "https": proxy} if proxy else None


async def probe() -> dict[str, Any]:
    """Проверка боем: сколько занимает ответ YouTube через выбранный путь."""
    import aiohttp
    started = time.monotonic()
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=15), **session_kwargs()
    ) as session:
        async with session.get("https://www.youtube.com/generate_204") as resp:
            status = resp.status
        ip = ""
        try:
            async with session.get("https://api.ipify.org") as resp:
                ip = (await resp.text()).strip()[:64]
        except Exception:
            pass
    return {"ok": status in (200, 204), "status": status,
            "ms": int((time.monotonic() - started) * 1000), "ip": ip}


# при импорте подхватываем сохранённый выбор: env нужен сразу
try:
    apply_env()
except Exception:                                   # pragma: no cover
    pass
