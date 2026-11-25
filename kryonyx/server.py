"""
server.py — локальный HTTP API для интерфейса плеера.

Работает на 127.0.0.1, без авторизации и без внешней базы: это приложение
одного пользователя на его же компьютере.
"""

from __future__ import annotations

import asyncio
import difflib
import math
import unicodedata
import json
import logging
import os
import re
import shutil
import time
from typing import Any
from urllib.parse import urlparse, unquote

import aiohttp
from aiohttp import web

from . import (__version__, audiocache, avatars, doctor, extplugins, extras,
               integrations, library, logs, convert, lyrics as lyrics_mod,
               netproxy, plugins, providers, recommend, selftest, storage, streaming,
               youtube, ytcookies, ytdlp_bin, ytlibs, ytmusic, clipcache)
from . import karaoke_jobs, clipstream, audiovault, avatarshop, clipcatalog
from .paths import web_dir

log = logging.getLogger(__name__)
routes = web.RouteTableDef()

def _background(app, coroutine):
    """Track detached work so cleanup drains it before shared HTTP closes."""
    tasks = app.setdefault('background_tasks', set())
    task = asyncio.create_task(coroutine)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task

_http: aiohttp.ClientSession | None = None


_http_gen = -1


async def http() -> aiohttp.ClientSession:
    global _http, _http_gen
    if _http is not None and not _http.closed and _http_gen != netproxy.generation:
        await _http.close()         # прокси сменили: старые соединения не нужны
        _http = None
    if _http is None or _http.closed:
        _http_gen = netproxy.generation
        _http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=30),
            headers={"User-Agent": "KryonyxMusic/" + __version__},
            **netproxy.session_kwargs(),
        )
    return _http


def ok(data: Any) -> web.Response:
    return web.json_response(data, dumps=lambda x: json.dumps(x, ensure_ascii=False))


def fail(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _int(request: web.Request, name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(request.query.get(name, default))))
    except (TypeError, ValueError):
        return default


async def _body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


_YOUTUBE_IMAGE_HOSTS = ("ytimg.com", "ggpht.com", "googleusercontent.com")


def _youtube_image_url(value: str) -> bool:
    """Allow only HTTPS image CDN URLs; never turn this into an open proxy."""
    try:
        parsed = urlparse(value)
        port = parsed.port
    except (TypeError, ValueError):
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return (
        parsed.scheme == "https"
        and port in (None, 443)
        and any(host == root or host.endswith("." + root)
                for root in _YOUTUBE_IMAGE_HOSTS)
    )


@routes.get("/api/image/youtube")
async def api_youtube_image(request: web.Request) -> web.StreamResponse:
    """Fallback for WebViews that cannot load YouTube CDN images directly."""
    url = (request.query.get("url") or "").strip()
    if not _youtube_image_url(url):
        return fail("Unsupported image URL", 400)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124 Safari/537.36"
        ),
        "Referer": "https://music.youtube.com/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    try:
        async with (await http()).get(url, headers=headers, allow_redirects=True) as resp:
            if resp.status != 200 or not _youtube_image_url(str(resp.url)):
                return fail("Image is unavailable", 502)
            content_type = (resp.headers.get("Content-Type") or "").split(";", 1)[0]
            if not content_type.startswith("image/"):
                return fail("Remote response is not an image", 502)
            limit = 8 * 1024 * 1024
            parts: list[bytes] = []
            size = 0
            async for chunk in resp.content.iter_chunked(64 * 1024):
                size += len(chunk)
                if size > limit:
                    return fail("Image is too large", 413)
                parts.append(chunk)
            body = b"".join(parts)
            return web.Response(
                body=body,
                content_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.debug("[image] youtube %s: %s", url, exc)
        return fail("Image could not be loaded", 502)


# --------------------------------------------------------------------------- #
# сохранение обложек и аватарок на диск
# --------------------------------------------------------------------------- #
_IMAGE_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
              "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif",
              "image/bmp": ".bmp"}
_BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def covers_dir() -> str:
    """Папка для сохранённых обложек: «Изображения/Kryo Covers»,
    а если её нет или туда нельзя писать — папка данных приложения."""
    from .paths import data_dir
    candidates = []
    if os.name == "nt":
        profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        candidates.append(os.path.join(profile, "Pictures"))
    candidates.append(os.path.join(os.path.expanduser("~"), "Pictures"))
    for base in candidates:
        if os.path.isdir(base):
            target = os.path.join(base, "Kryo Covers")
            try:
                os.makedirs(target, exist_ok=True)
                if os.access(target, os.W_OK):
                    return target
            except OSError:
                pass
    target = os.path.join(data_dir(), "covers")
    os.makedirs(target, exist_ok=True)
    return target


def _cover_name(name: str) -> str:
    name = _BAD_NAME.sub(" ", str(name or "")).strip(" .")
    name = re.sub(r"\s+", " ", name)[:120].strip(" .")
    return name or time.strftime("cover-%Y%m%d-%H%M%S")


def _public_image_url(url: str, request: web.Request) -> bool:
    """Только http(s) и не адреса внутри своей сети (кроме самого сервера)."""
    import ipaddress
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if parsed.netloc.lower() == (request.host or "").lower():
        return True                 # наша же картинка (/api/...)
    if host == "localhost" or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


async def _grab_image(url: str, request: web.Request) -> tuple[bytes, str] | None:
    import base64
    if url.startswith("data:image/"):
        head, _, data = url.partition(",")
        kind = head[5:].split(";", 1)[0].lower()
        if ";base64" not in head or kind not in _IMAGE_EXT:
            return None
        try:
            body = base64.b64decode(data, validate=False)
        except ValueError:
            return None
        return (body, kind) if body else None
    if url.startswith("/"):
        url = f"{request.scheme}://{request.host}{url}"
    if not _public_image_url(url, request):
        return None
    headers = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/124 Safari/537.36"),
               "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
    if _youtube_image_url(url):
        headers["Referer"] = "https://music.youtube.com/"
    try:
        timeout = aiohttp.ClientTimeout(total=25, sock_connect=10, sock_read=20)
        async with (await http()).get(url, headers=headers, allow_redirects=True,
                                      timeout=timeout) as resp:
            if resp.status != 200:
                return None
            kind = (resp.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if not kind.startswith("image/"):
                return None
            limit = 25 * 1024 * 1024
            parts: list[bytes] = []
            size = 0
            async for chunk in resp.content.iter_chunked(64 * 1024):
                size += len(chunk)
                if size > limit:
                    return None
                parts.append(chunk)
            body = b"".join(parts)
            # Заглушка YouTube «нет картинки» весит около килобайта.
            if len(body) < 1500 and _youtube_image_url(url):
                return None
            return (body, kind) if body else None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log.debug("[cover] %s: %s", url, exc)
        return None


def _sniff_ext(body: bytes, kind: str) -> str:
    if body[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    if body[:4] == b"GIF8":
        return ".gif"
    return _IMAGE_EXT.get(kind, ".jpg")


@routes.post("/api/image/save")
async def api_image_save(request: web.Request) -> web.Response:
    # Old clients must not silently write into Pictures or the app data directory.
    return fail("Choose a save location using Save As", 409)


@routes.post("/api/image/export")
async def api_image_export(request: web.Request) -> web.Response:
    """Fetch artwork without writing a user file. The caller must choose Save As."""
    _karaoke_origin(request)
    body = await _body(request)
    urls = body.get("urls")
    if not isinstance(urls, list) or not urls or len(urls) > 12 or any(not isinstance(u, str) for u in urls):
        return fail("No image URL", 400)
    for url in urls:
        got = await _grab_image(url, request)
        if not got:
            continue
        try:
            import io
            from PIL import Image, ImageOps
            data, _kind = got
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 32000000:
                    continue
                output = io.BytesIO()
                ImageOps.exif_transpose(image).convert('RGBA').save(output, format='PNG')
                return web.Response(body=output.getvalue(), content_type='image/png',
                    headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})
        except (ValueError, OSError, Image.DecompressionBombError):
            continue
    return fail("Image could not be loaded", 502)


def _write_bytes(path: str, data: bytes) -> None:
    tmp = path + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


@routes.post("/api/image/reveal")
async def api_image_reveal(request: web.Request) -> web.Response:
    """Открыть папку с обложками (и выделить файл на Windows)."""
    body = await _body(request)
    folder = covers_dir()
    path = str(body.get("path") or "")
    target = path if path and os.path.isfile(path) and \
        os.path.dirname(os.path.abspath(path)) == os.path.abspath(folder) else ""
    try:
        if os.name == "nt":
            import subprocess
            if target:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])
            else:
                os.startfile(folder)            # type: ignore[attr-defined]
        else:
            import subprocess
            import sys as _sys
            opener = "open" if _sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, folder], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception as exc:
        return fail(f"Could not open the folder: {exc}", 500)
    return ok({"folder": folder})


# --------------------------------------------------------------------------- #
# статус
# --------------------------------------------------------------------------- #
# ---------------------------------------------------------------- native shell
# Optional Rust window (desktop-rs). Every endpoint needs the per-launch token
# the shell passed in KRYONYX_SHELL_TOKEN; see shell_bridge.py.
def _shell_base(request: web.Request) -> str:
    sock = request.transport.get_extra_info("sockname") if request.transport else None
    port = sock[1] if isinstance(sock, tuple) and len(sock) > 1 else (request.url.port or 8765)
    return f"http://127.0.0.1:{port}"


async def _shell_body(request: web.Request):
    from . import shell_bridge
    if not shell_bridge.allowed(request.headers.get(shell_bridge.HEADER)):
        return None, fail("forbidden", 403)
    try:
        body = await request.json()
    except Exception:
        return None, fail("bad request")
    if not isinstance(body, dict):
        return None, fail("bad request")
    return body, None


@routes.get("/api/shell/hello")
async def api_shell_hello(request: web.Request) -> web.Response:
    from . import shell_bridge
    if not shell_bridge.allowed(request.headers.get(shell_bridge.HEADER)):
        return fail("forbidden", 403)
    return ok(await asyncio.to_thread(shell_bridge.hello))


@routes.post("/api/shell/save-plan")
async def api_shell_save_plan(request: web.Request) -> web.Response:
    from . import shell_bridge
    body, error = await _shell_body(request)
    if error is not None:
        return error
    try:
        return ok(await asyncio.to_thread(shell_bridge.plan, body.get("kind"), body.get("payload"),
                                          _shell_base(request)))
    except Exception as exc:  # the same plain messages as DesktopApi.save_*
        log.warning("shell save plan failed: %s", exc)
        return fail(str(exc) if isinstance(exc, ValueError) else "Could not prepare the file")


@routes.post("/api/shell/save")
async def api_shell_save(request: web.Request) -> web.Response:
    from . import shell_bridge
    body, error = await _shell_body(request)
    if error is not None:
        return error
    try:
        return ok(await asyncio.to_thread(shell_bridge.write, body.get("kind"), body.get("payload"),
                                          body.get("path"), _shell_base(request)))
    except Exception as exc:
        log.warning("shell save failed: %s", exc)
        return fail(str(exc) if isinstance(exc, ValueError) else "Could not save the file. Check the source and destination.")


def _shell_quit_later(loop) -> None:
    # After the answer has gone out: main._serve then runs runner.cleanup()
    # (jobs, caches, database) and the process exits with code 0.
    loop.call_later(0.15, loop.stop)


@routes.post("/api/shell/quit")
async def api_shell_quit(request: web.Request) -> web.Response:
    """The native shell is closing: stop cleanly instead of being killed."""
    from . import shell_bridge
    if not shell_bridge.allowed(request.headers.get(shell_bridge.HEADER)):
        return fail("forbidden", 403)
    log.info("the native shell asked the backend to stop")
    _shell_quit_later(asyncio.get_running_loop())
    return ok({"stopping": True})


@routes.get("/api/health")
async def api_health(request: web.Request) -> web.Response:
    data = plugins.state()
    return ok({"ok": True, "version": __version__, **providers.status(),
               "stats": storage.stats(),
               "streams": streaming.stats(),
               "plugins": {"installed": len(data["installed"]),
                           "enabled": len(plugins.enabled_ids()),
                           "total": len(plugins.catalog()),
                           "custom": len(extplugins.loaded_ids())},
               "local": doctor.summary()})


# --------------------------------------------------------------------------- #
# журнал
# --------------------------------------------------------------------------- #
@routes.get("/api/logs")
async def api_logs(request: web.Request) -> web.Response:
    return ok({
        "items": logs.records(
            level=request.query.get("level") or "",
            limit=_int(request, "limit", 300, 20, 1000),
            after=_int(request, "after", 0, 0, 10_000_000),
            query=request.query.get("q") or "",
        ),
        "counts": logs.counts(),
        "levels": list(logs.LEVELS),
    })


@routes.get("/api/logs/text")
async def api_logs_text(request: web.Request) -> web.Response:
    body = logs.text(request.query.get("level") or "",
                     _int(request, "limit", 1000, 20, 1000))
    return web.Response(text=body, content_type="text/plain", charset="utf-8")


@routes.delete("/api/logs")
async def api_logs_clear(request: web.Request) -> web.Response:
    return ok({"removed": logs.clear()})


# --------------------------------------------------------------------------- #
# каталог плагинов
# --------------------------------------------------------------------------- #
@routes.get("/api/plugins")
async def api_plugins(request: web.Request) -> web.Response:
    return ok(await asyncio.to_thread(plugins.listing, providers.ytdlp_ready()))


@routes.post("/api/plugins/{pid}/install")
async def api_plugin_install(request: web.Request) -> web.Response:
    pid = request.match_info["pid"]
    try:
        await asyncio.to_thread(plugins.install, pid)
    except KeyError:
        return fail("Unknown plugin", 404)
    providers.clear_caches()
    recommend.invalidate()
    return ok(plugins.listing(providers.ytdlp_ready()))


@routes.post("/api/plugins/{pid}/uninstall")
async def api_plugin_uninstall(request: web.Request) -> web.Response:
    pid = request.match_info["pid"]
    try:
        await asyncio.to_thread(plugins.uninstall, pid)
    except KeyError:
        return fail("Unknown plugin", 404)
    except ValueError:
        return fail("This plugin ships with the app and cannot be removed", 409)
    providers.clear_caches()
    recommend.invalidate()
    return ok(plugins.listing(providers.ytdlp_ready()))


@routes.post("/api/plugins/{pid}/toggle")
async def api_plugin_toggle(request: web.Request) -> web.Response:
    data = await _body(request)
    pid = request.match_info["pid"]
    try:
        await asyncio.to_thread(plugins.set_enabled, pid, bool(data.get("enabled", True)))
    except KeyError:
        return fail("Unknown plugin", 404)
    if pid == "discord":
        # Включили или выключили плагин — статус появляется/снимается сразу.
        try:
            await integrations.refresh_presence()
        except Exception as exc:
            log.debug("[discord] could not refresh the presence: %s", exc)
    providers.clear_caches()
    recommend.invalidate()
    return ok(plugins.listing(providers.ytdlp_ready()))


@routes.put("/api/plugins/{pid}/config")
async def api_plugin_config(request: web.Request) -> web.Response:
    data = await _body(request)
    pid = request.match_info["pid"]
    try:
        await asyncio.to_thread(plugins.configure, pid, data)
    except KeyError:
        return fail("Unknown plugin", 404)
    if pid == "jamendo":
        library.set_jamendo_client(plugins.config("jamendo").get("client_id"))
    if pid == "discord":
        # Настройки статуса применяются сразу: перерисовываем карточку.
        try:
            await integrations.refresh_presence()
        except Exception as exc:
            log.debug("[discord] could not refresh the presence: %s", exc)
    providers.clear_caches()
    return ok(plugins.listing(providers.ytdlp_ready()))


@routes.post("/api/plugins/reset")
async def api_plugins_reset(request: web.Request) -> web.Response:
    await asyncio.to_thread(plugins.reset)
    providers.clear_caches()
    recommend.invalidate()
    return ok(plugins.listing(providers.ytdlp_ready()))


@routes.post("/api/plugins/selftest")
async def api_plugins_selftest(request: web.Request) -> web.Response:
    """Живая проверка: каждый плагин делает один настоящий запрос."""
    data = await _body(request)
    ids = [str(i) for i in (data.get("ids") or []) if str(i) in plugins.BY_ID]
    force = bool(data.get("force"))
    only_enabled = bool(data.get("only_enabled", True)) and not force
    return ok(await selftest.check_all(ids or None, only_enabled=only_enabled,
                                       force=force))


@routes.post("/api/plugins/{pid}/selftest")
async def api_plugin_selftest(request: web.Request) -> web.Response:
    data = await _body(request)
    try:
        return ok(await selftest.check(request.match_info["pid"],
                                       force=bool(data.get("force"))))
    except ValueError as exc:
        return fail(str(exc), 404)


# --------------------------------------------------------------------------- #
# свои плагины и свои библиотеки
# --------------------------------------------------------------------------- #
@routes.get("/api/plugins/custom")
async def api_custom(request: web.Request) -> web.Response:
    return ok(await asyncio.to_thread(extplugins.status))


@routes.post("/api/plugins/custom/reload")
async def api_custom_reload(request: web.Request) -> web.Response:
    """Перечитывает папки плагинов и библиотек. Перезапуск не нужен."""
    data = await asyncio.to_thread(extplugins.load_all)
    providers.clear_caches()
    recommend.invalidate()
    return ok({**data, "catalog": plugins.listing(providers.ytdlp_ready())})


@routes.post("/api/plugins/custom/upload")
async def api_custom_upload(request: web.Request) -> web.Response:
    """Приём файла плагина (.py или .zip) из интерфейса."""
    name, payload = "", b""
    try:
        reader = await request.multipart()
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "file":
                name = part.filename or ""
                payload = await part.read(decode=False)
    except Exception as exc:
        return fail(f"the file was not read: {exc}", 400)
    if not name or not payload:
        return fail("no file was sent", 400)
    try:
        data = await asyncio.to_thread(extplugins.install_file, name, payload)
    except ValueError as exc:
        return fail(str(exc), 400)
    except Exception as exc:
        return fail(str(exc), 500)
    providers.clear_caches()
    return ok({**data, "catalog": plugins.listing(providers.ytdlp_ready())})


@routes.post("/api/plugins/custom/example")
async def api_custom_example(request: web.Request) -> web.Response:
    """Кладёт в папку готовый пример плагина — с него удобно начинать."""
    try:
        data = await asyncio.to_thread(
            extplugins.install_file, "example.py",
            extplugins.example_text().encode("utf-8"))
    except Exception as exc:
        return fail(str(exc), 500)
    providers.clear_caches()
    return ok({**data, "catalog": plugins.listing(providers.ytdlp_ready())})


@routes.delete("/api/plugins/custom/{pid}")
async def api_custom_remove(request: web.Request) -> web.Response:
    try:
        data = await asyncio.to_thread(extplugins.remove, request.match_info["pid"])
    except KeyError:
        return fail("this plugin is not loaded", 404)
    except ValueError as exc:
        return fail(str(exc), 409)
    providers.clear_caches()
    recommend.invalidate()
    return ok({**data, "catalog": plugins.listing(providers.ytdlp_ready())})


@routes.post("/api/plugins/libs")
async def api_libs_install(request: web.Request) -> web.Response:
    """Установка своей библиотеки Python в папку пользователя (pip --target)."""
    data = await _body(request)
    raw = data.get("packages") or data.get("name") or ""
    specs = raw if isinstance(raw, list) else str(raw).split()
    try:
        result = await asyncio.to_thread(extplugins.install_lib, specs)
    except ValueError as exc:
        return fail(str(exc), 400)
    except RuntimeError as exc:
        return fail(str(exc), 502)
    return ok(result)


@routes.delete("/api/plugins/libs/{name}")
async def api_libs_remove(request: web.Request) -> web.Response:
    try:
        return ok(await asyncio.to_thread(extplugins.remove_lib,
                                          request.match_info["name"]))
    except KeyError:
        return fail("there is no such library in your folder", 404)
    except ValueError as exc:
        return fail(str(exc), 409)


# --------------------------------------------------------------------------- #
# «запустится ли здесь»: локальная проверка устройства
# --------------------------------------------------------------------------- #
@routes.get("/api/doctor")
async def api_doctor(request: web.Request) -> web.Response:
    return ok(await asyncio.to_thread(doctor.report))


@routes.get("/api/doctor/text")
async def api_doctor_text(request: web.Request) -> web.StreamResponse:
    return web.Response(text=await asyncio.to_thread(doctor.text),
                        content_type="text/plain", charset="utf-8")


# --------------------------------------------------------------------------- #
# перенос плейлистов: Spotify, YouTube, SoundCloud
# --------------------------------------------------------------------------- #
# Account music metadata stays local and separate from real listening history.
@routes.post('/api/account-profile/preview')
async def api_account_preview(request):
    from . import account_import
    _karaoke_origin(request)
    try:
        service=request.query.get('service','generic')
        filename=unquote(request.headers.get('X-File-Name','export.json'))
        raw=await request.read()
        return ok(await asyncio.to_thread(account_import.stage,bytes(raw),filename,service))
    except (ValueError,TypeError,RecursionError) as exc:return fail(str(exc),400)

@routes.post('/api/account-profile/apply')
async def api_account_apply(request):
    from . import account_import
    _karaoke_origin(request)
    data=await _body(request)
    try:
        result=await asyncio.to_thread(account_import.apply,data.get('token'),data.get('selected'))
        recommend.invalidate()
        return ok(result)
    except (ValueError,TypeError) as exc:return fail(str(exc),400)

@routes.get('/api/account-profile')
async def api_account_get(request):
    from . import account_import
    return ok({'profiles':await asyncio.to_thread(account_import.summary),'preferences':recommend.preferences()})

@routes.delete('/api/account-profile/{service}')
async def api_account_delete(request):
    from . import account_import
    _karaoke_origin(request)
    try:
        await asyncio.to_thread(account_import.remove,request.match_info['service'])
        recommend.invalidate()
        return ok({'profiles':await asyncio.to_thread(account_import.summary)})
    except ValueError as exc:return fail(str(exc),400)

@routes.post('/api/account-profile/{service}/match')
async def api_account_match(request):
    from . import account_import
    _karaoke_origin(request)
    try:
        profile=next((x for x in await asyncio.to_thread(account_import.profiles) if x['service']==request.match_info['service']),None)
        if not profile or not profile['favorites']:return fail('No imported favorites to match',400)
        source={'name':'Imported favorites','service':profile['service'],'type':'playlist','items':profile['favorites']}
        return ok(convert.start_import(source,recommend._user_sources()))
    except ValueError as exc:return fail(str(exc),400)


@routes.get("/api/convert/services")
async def api_convert_services(request: web.Request) -> web.Response:
    return ok({"items": list(convert.SERVICES), "max_items": convert.MAX_ITEMS})


@routes.post("/api/convert")
async def api_convert_start(request: web.Request) -> web.Response:
    data = await _body(request)
    sources = [s for s in (data.get("sources") or []) if isinstance(s, str)]
    try:
        return ok(convert.start(str(data.get("url") or ""), sources or None))
    except ValueError as exc:
        return fail(str(exc))


@routes.post("/api/transfer/preview")
async def api_transfer_preview(request: web.Request) -> web.Response:
    from . import playlist_transfer
    data = await _body(request)
    try:
        source = playlist_transfer.parse(data.get("content", ""), str(data.get("filename", "")), str(data.get("service", "generic")))
        return ok({k: v for k, v in source.items() if k != "items"} | {"items": source["items"][:30]})
    except (ValueError, RecursionError) as exc:
        return fail(str(exc))


@routes.post("/api/transfer/start")
async def api_transfer_start(request: web.Request) -> web.Response:
    from . import playlist_transfer
    data = await _body(request)
    try:
        source = playlist_transfer.parse(data.get("content", ""), str(data.get("filename", "")), str(data.get("service", "generic")))
        sources = [s for s in (data.get("sources") or []) if isinstance(s, str)]
        return ok(convert.start_import(source, sources or None))
    except (ValueError, RecursionError) as exc:
        return fail(str(exc))


@routes.get("/api/convert/{job}")
async def api_convert_job(request: web.Request) -> web.Response:
    state = convert.job(request.match_info["job"])
    if not state:
        return fail("Job not found", 404)
    return ok(convert._public(state))


@routes.post("/api/convert/{job}/save")
async def api_convert_save(request: web.Request) -> web.Response:
    data = await _body(request)
    skip = [int(i) for i in (data.get("skip") or []) if str(i).lstrip("-").isdigit()]
    overrides = data.get("overrides") if isinstance(data.get("overrides"), dict) else {}
    try:
        result = await asyncio.to_thread(
            convert.save, request.match_info["job"],
            (data.get("name") or "").strip() or None,
            include_weak=bool(data.get("include_weak", True)),
            playlist_id=int(data["playlist_id"]) if data.get("playlist_id") else None,
            skip=skip,
            overrides=overrides,
        )
    except (ValueError, TypeError) as exc:
        return fail(str(exc))
    return ok(result)


@routes.post("/api/convert/{job}/cancel")
async def api_convert_cancel(request: web.Request) -> web.Response:
    """Останавливает длинный перенос: подобранное остаётся в задаче."""
    try:
        return ok(await convert.cancel(request.match_info["job"]))
    except ValueError as exc:
        return fail(str(exc), 404)


# --------------------------------------------------------------------------- #
# интеграции
# --------------------------------------------------------------------------- #
@routes.get("/api/integrations")
async def api_integrations(request: web.Request) -> web.Response:
    return ok({"items": integrations.status()})


@routes.post("/api/integrations/{pid}/test")
async def api_integration_test(request: web.Request) -> web.Response:
    pid = request.match_info["pid"]
    if pid not in integrations.INTEGRATIONS:
        return fail("Unknown integration", 404)
    try:
        return ok(await integrations.test(pid))
    except Exception as exc:
        return ok({"ok": False, "message": str(exc)})


@routes.post("/api/integrations/mastodon/share")
async def api_mastodon_share(request: web.Request) -> web.Response:
    data = await _body(request)
    track = data.get("track") if isinstance(data.get("track"), dict) else None
    if not track:
        return fail("A track is required")
    try:
        return ok(await integrations.mastodon_share(track, data.get("text") or ""))
    except Exception as exc:
        return fail(str(exc), 502)


@routes.post("/api/nowplaying")
async def api_now_playing(request: web.Request) -> web.Response:
    """«Сейчас играет»: Discord Rich Presence и Last.fm."""
    data = await _body(request)
    track = data.get("track") if isinstance(data.get("track"), dict) else None
    sent = await integrations.now_playing(
        track, float(data.get("position") or 0), bool(data.get("paused")),
        loading=bool(data.get("loading")),
        speed=float(data.get("speed") or 1.0),
        duration=float(data.get("duration") or 0))
    return ok({"sent": sent})


# --------------------------------------------------------------------------- #
# метаданные и подборки от плагинов
# --------------------------------------------------------------------------- #
@routes.get("/api/meta")
async def api_meta(request: web.Request) -> web.Response:
    title = (request.query.get("title") or "").strip()
    artist = (request.query.get("artist") or "").strip()
    if not title:
        return fail("A title is required")
    return ok(await extras.metadata(artist, title))


@routes.get("/api/discovery")
async def api_discovery(request: web.Request) -> web.Response:
    rows = await extras.discovery_rows(_int(request, "limit", 16, 6, 30))
    return ok({"rows": rows})


# --------------------------------------------------------------------------- #
# поиск
# --------------------------------------------------------------------------- #
@routes.get("/api/search")
async def api_search(request: web.Request) -> web.Response:
    query = (request.query.get("q") or "").strip()
    if not query:
        return ok({"tracks": [], "authors": []})
    sources = [s for s in (request.query.get("sources") or "").split(",") if s]
    limit = _int(request, "limit", 40, 10, 100)
    page = _int(request, "page", 0, 0, 20)
    allow_go_plus = request.query.get("go_plus") == "1"

    result = await providers.search(
        query,
        sources=sources or providers.ALL_SOURCES,
        limit=limit,
        page=page,
        allow_go_plus=allow_go_plus,
        # Альбомы и плейлисты нужны ровно один раз на запрос: когда экран
        # поиска догружает треки постранично, полки уже нарисованы.
        with_collections=page == 0 and request.query.get("collections") != "0",
    )
    await extras.fill_thumbnails(result.get("tracks"))
    if page == 0:
        await asyncio.to_thread(storage.log_search, query)
    return ok(result)


@routes.get("/api/search/extra")
async def api_search_extra(request: web.Request) -> web.Response:
    """Альбомы, плейлисты и исполнители по запросу — отдельно от треков.

    Раньше они ехали в ответе на поиск треков, и первая страница песен ждала
    каталог (уточнение числа треков у синглов — до 14 с). Теперь экран поиска
    запрашивает их параллельно и рисует полки, как только они пришли.
    """
    query = (request.query.get("q") or "").strip()
    if not query:
        return ok({"albums": [], "playlists": [], "authors": []})
    limit = _int(request, "limit", 20, 4, 40)

    async def artists() -> list:
        try:
            return await asyncio.wait_for(ytmusic.artists(query, 12), 8.0)
        except Exception as exc:
            log.debug("[search] artists %r: %s", query, exc)
            return ytmusic.IncompleteSearchResults()

    found, authors = await asyncio.gather(
        providers.search_collections(query, limit), artists())
    result = {
        "albums": found.get("albums") or [],
        "playlists": found.get("playlists") or [],
        "authors": authors or [],
    }
    if found.get("degraded") or getattr(authors, "degraded", False):
        result["degraded"] = True
    return ok(result)


@routes.get("/api/suggest")
async def api_suggest(request: web.Request) -> web.Response:
    query = (request.query.get("q") or "").strip()
    if len(query) < 2:
        recent = await asyncio.to_thread(storage.recent_searches, 8)
        return ok({"queries": recent, "authors": [], "recent": True})

    local = await asyncio.to_thread(storage.recent_searches, 4, query)
    rich = request.query.get("rich") == "1"
    async def quick_tracks():
        if not rich: return []
        try:
            sources = [s for s in request.query.get("sources", "").split(",") if s in providers.ALL_SOURCES]
            data = await asyncio.wait_for(providers.search(query, sources=sources or recommend._user_sources(), limit=6, with_collections=False), 5.0)
            await extras.fill_thumbnails(data.get("tracks"))
            return data.get("tracks") or []
        except Exception: return []
    remote, authors, tracks = await asyncio.gather(
        asyncio.wait_for(providers.suggest(query, 10), 5.0),
        asyncio.wait_for(providers.suggest_authors(query, 6), 6.0) if request.query.get("authors") != "0" else _empty(),
        quick_tracks(),
        return_exceptions=True,
    )
    queries = list(local)
    if isinstance(remote, list):
        for item in remote:
            if item.lower() not in [q.lower() for q in queries]:
                queries.append(item)
    return ok({
        "queries": queries[:10],
        "authors": authors if isinstance(authors, list) else [],
        "tracks": tracks if isinstance(tracks, list) else [],
        "history": local,
    })


async def _empty() -> list:
    return []


@routes.get("/api/collection")
async def api_collection(request: web.Request) -> web.Response:
    """Содержимое альбома или плейлиста: карточка и готовый список треков."""
    ident = (request.query.get("id") or "").strip()
    if not ident:
        return fail("A collection id is required")
    if not providers.is_collection(ident):
        return fail("This is not an album or a playlist")
    try:
        limit = int(request.query["limit"]) if "limit" in request.query else None
        if limit is not None and limit < 1:
            return fail("A track list is required")
        data = await providers.collection(ident, limit)
    except (ValueError, TypeError):
        return fail("A track list is required")
    except Exception as exc:
        return fail(str(exc), 502)
    await extras.fill_thumbnails(data.get("tracks"))
    return ok(data)


@routes.get("/api/author")
async def api_author(request: web.Request) -> web.Response:
    name = (request.query.get("name") or "").strip()
    url = (request.query.get("url") or "").strip() or None
    source = (request.query.get("source") or "").strip() or None
    if not name and not url:
        return fail("A name or url is required")
    data = await providers.author(name, url=url, source=source,
                                 limit=_int(request, "limit", 40, 10, 100))
    await extras.fill_thumbnails(data.get("tracks"))
    return ok(data)


@routes.post('/api/wallpaper/resolve')
async def api_wallpaper_resolve(request):
    from . import wallpaper
    try:
        data=await _body(request)
        name=await asyncio.wait_for(wallpaper.resolve(data.get('url','')),25)
        return ok({'file':name})
    except (ValueError, OSError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return fail(str(exc) or 'Wallpaper request timed out',400)

@routes.get('/api/wallpaper/file/{name}')
async def api_wallpaper_file(request):
    from . import wallpaper
    name=request.match_info['name']
    if not re.fullmatch(r'[a-f0-9]{64}\.jpg',name):raise web.HTTPNotFound()
    target=wallpaper.directory()/name
    if not target.is_file():raise web.HTTPNotFound()
    return web.FileResponse(target,headers={'Cache-Control':'private, max-age=86400'})

# --------------------------------------------------------------------------- #
# рекомендации
# --------------------------------------------------------------------------- #
@routes.get("/api/recommend")
async def api_recommend(request: web.Request) -> web.Response:
    limit = _int(request, "rows", 12, 2, 16)
    # One shared background refresh; requests never wait for every source.
    task=request.app.get('recommend_refresh33')
    scope=recommend._scope()
    stale=False
    if task is not None and not task.done() and request.app.get('recommend_scope50')!=scope:
        obsolete=task
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        current=request.app.get('recommend_refresh33')
        task=current if current is not obsolete else None
        stale=True
    fresh=request.query.get('fresh')=='1'
    poll=request.query.get('poll')=='1'
    exclude_raw=(request.query.get('exclude') or '').strip()
    exclude_ids=[x.strip() for x in exclude_raw.split(',') if x.strip()][:80] if exclude_raw else None
    if fresh and (task is None or task.done()):
        recommend.invalidate()
        task=_background(request.app, _refresh_rows(limit, exclude_ids))
        request.app['recommend_refresh33']=task
        request.app['recommend_scope50']=scope
    saved=recommend.cached_rows()
    if (not poll or stale) and (not saved or stale):
        if task is None or task.done():
            task=_background(request.app, _refresh_rows(limit, exclude_ids))
            request.app['recommend_refresh33']=task
            request.app['recommend_scope50']=scope
    if not saved and task and not task.done():
        try:await asyncio.wait_for(asyncio.shield(task),2)
        except asyncio.TimeoutError:pass
        saved=recommend.cached_rows()
    else:saved=recommend.cached_rows() or saved
    rows=(saved or [])[:limit]
    for row in rows:await extras.fill_thumbnails(row.get('items'),lookup=False)
    is_refreshing = bool(task and not task.done())
    gen = getattr(recommend, 'current_generation', lambda: 0)()
    return ok({'rows':rows,'cached':not fresh and not poll and bool(rows),'refreshing':is_refreshing,'generation':gen})


async def _refresh_rows(limit: int, exclude_ids: list[str] | None = None) -> None:
    try:
        if exclude_ids:
            await recommend.build_rows(limit, exclude_ids=exclude_ids)
        else:
            await recommend.build_rows(limit)
    except Exception:
        pass


@routes.get("/api/mix")
async def api_mix(request: web.Request) -> web.Response:
    mix = await recommend.daily_mix(_int(request, "limit", 40, 10, 80))
    await extras.fill_thumbnails(mix.get("items"))
    return ok(mix)


@routes.post("/api/radio")
async def api_radio(request: web.Request) -> web.Response:
    data = await _body(request)
    seed = data.get("track") if isinstance(data.get("track"), dict) else None
    items = await recommend.radio(seed, _int(request, "limit", 20, 5, 50))
    await extras.fill_thumbnails(items)
    return ok({"items": items})


@routes.post('/api/wave')
async def api_wave61(request: web.Request) -> web.Response:
    _karaoke_origin(request)
    data = await _body(request)
    try:
        result = await asyncio.wait_for(recommend.wave_candidates(data.get('track'), data.get('exclude'), data.get('mode','balanced')), timeout=38)
        await extras.fill_thumbnails(result['items'], lookup=False)
        return ok(result)
    except ValueError as exc:
        return fail(str(exc), 400)
    except asyncio.TimeoutError:
        return fail('Wave selection timed out', 504)


@routes.post('/api/recommend/next')
async def api_recommend_next(request: web.Request) -> web.Response:
    _karaoke_origin(request)
    data = await _body(request)
    try:
        result = await recommend.next_picks(data.get('track'), data.get('exclude'), 24)
        await extras.fill_thumbnails(result['items'], lookup=False)
        return ok(result)
    except ValueError as exc:
        return fail(str(exc), 400)
    except asyncio.TimeoutError:
        return fail('Recommendations timed out', 504)
    except Exception:
        log.exception('Next recommendations unavailable')
        return fail('Recommendations are unavailable', 503)


@routes.get("/api/streams")
async def api_streams(request: web.Request) -> web.Response:
    """Первая фаза: кандидаты — источники, где может лежать этот трек."""
    track = {
        "id": (request.query.get("id") or "").strip() or None,
        "title": (request.query.get("title") or "").strip(),
        "artist": (request.query.get("artist") or "").strip(),
    }
    duration = request.query.get("duration")
    if duration and duration.isdigit():
        track["duration"] = int(duration)
    result = await streaming.resolve_candidates_for_track(
        track, limit=_int(request, "limit", 8, 2, 20),
        refresh=request.query.get("fresh") == "1",
    )
    return ok(result)


@routes.post("/api/streams/resolve")
async def api_stream_resolve(request: web.Request) -> web.Response:
    """Вторая фаза: прямая ссылка для выбранного кандидата."""
    data = await _body(request)
    candidate = data.get("candidate") if isinstance(data.get("candidate"), dict) else None
    if not candidate and data.get("id"):
        candidate = streaming.candidate_from_track(data)
    if not candidate or not candidate.get("id"):
        return fail("A candidate is required")
    resolved = await streaming.resolve_stream_for_candidate(candidate)
    if resolved is None:
        return fail("No streaming plugins are enabled", 409)
    return ok({"candidate": resolved, "ok": bool(resolved.get("stream"))
               and not resolved.get("failed")})


@routes.delete("/api/streams")
async def api_streams_forget(request: web.Request) -> web.Response:
    streaming.forget()
    return ok({"ok": True})


# --------------------------------------------------------------------------- #
# стрим
# --------------------------------------------------------------------------- #
# Сколько ссылок подряд имеем право попросить у источника, пока слушатель
# ещё ничего не услышал. Три — это исходная ссылка плюс два разных клиента
# плеера; дальше почти наверняка дело не в ссылке.
_STREAM_ATTEMPTS = 3
# Spotify/Deezer are metadata catalogues.  Several browser requests (stream,
# warm link and prefetch) can arrive together for one item, so keep one short
# resolved replacement and one lock per metadata id instead of searching the
# same song two or three times.
_metadata_media_cache: dict[str, tuple[float, str, dict]] = {}
_metadata_media_locks: dict[str, asyncio.Lock] = {}


def _metadata_media_lock(track_id: str) -> asyncio.Lock:
    lock = _metadata_media_locks.get(track_id)
    if lock is None:
        lock = _metadata_media_locks[track_id] = asyncio.Lock()
    return lock
# Кэши клипов. Положительный держим час, отрицательный — четверть часа:
# повторный заход на трек без клипа отвечает мгновенно, но через 15 минут
# поиск можно повторить (клип мог появиться).
_VIDEO_TTL = 3600.0
_VIDEO_MISS_TTL = 900.0
_VIDEO_LINK_TTL = 1500.0
_video_id_cache: dict[str, tuple[float, str]] = {}
_video_miss_cache: dict[str, float] = {}
_video_link_cache: dict[str, tuple[float, dict]] = {}
_video_locks: dict[str, asyncio.Lock] = {}
_video_warming: set[str] = set()
# Последняя причина, по которой клип не поехал: её показывает экран клипов,
# иначе человек видит только «не удалось воспроизвести» и не знает, что делать
# (чаще всего достаточно вставить cookies YouTube в настройках).
_video_errors: dict[str, str] = {}
# Короткая память об отказе: пока она жива, повторный запрос отвечает сразу,
# а не проходит всю лестницу качеств заново. Кнопка «Перечитать» идёт с
# refresh=True и эту память не спрашивает.
_VIDEO_FAIL_TTL = 45.0
_video_link_fail: dict[str, tuple[float, str]] = {}


class VideoMissing(RuntimeError):
    """Клипа для трека нет: отвечаем сразу, не заставляя ждать поиск заново."""


# Совмещённый файл «видео+звук» YouTube отдаёт только до 360p. Качество
# автоматически НЕ снижается: выше 360p клип собирается из двух дорожек
# (см. _hd_info), ниже — идёт одним файлом.
_PROGRESSIVE_MAX = 360


def _video_ladder(quality: int) -> list[int]:
    return [min(max(144, int(quality or 360)), _PROGRESSIVE_MAX)]


def _video_lock(key: str) -> asyncio.Lock:
    """Один поиск на ключ: три запроса с экрана клипов не плодят три поиска."""
    lock = _video_locks.get(key)
    if lock is None:
        lock = _video_locks[key] = asyncio.Lock()
    return lock


# Сколько времени экран клипов вообще имеет право искать и открывать поток.
# Раньше пределов не было: поиск ждал оба пути до их собственных таймаутов,
# а ссылка на дорожку могла перебирать клиентов плеера почти минуту — именно
# поэтому клип «искался бесконечно» и так и не начинался.
_VIDEO_SEARCH_BUDGET = 9.0
_VIDEO_LINK_BUDGET = 22.0
_ytdlp_warming = False
_ytdlp_warm_task = None


def _warm_ytdlp() -> None:
    """Догружает yt-dlp в фоне.

    Ждать скачивание бинарника в момент открытия клипа нельзя: на медленном
    канале это десятки секунд тишины. Публичные узлы работают и без него.
    """
    global _ytdlp_warming, _ytdlp_warm_task
    if _ytdlp_warming or ytdlp_bin.ready():
        return
    _ytdlp_warming = True

    async def job() -> None:
        global _ytdlp_warming
        try:
            await ytdlp_bin.ensure(await http())
        except Exception as exc:
            log.info("[video] yt-dlp is not ready yet: %s", exc)
        finally:
            _ytdlp_warming = False

    _ytdlp_warm_task = asyncio.create_task(job())


async def _video_candidates(query: str, own: str, deadline: float
                            ) -> tuple[list[dict], bool]:
    """Кандидаты на клип из четырёх независимых путей, идущих одновременно.

    Важно: искать нужно именно видео, а не песни каталога. Авто-треки
    «- Topic» (тип ATV в YouTube Music) имеют вместо картинки статичную
    обложку — именно поэтому экран клипов раньше показывал обложку. Раньше
    Piped искал с фильтром music_songs, то есть сам приносил такие треки.

      1. YouTube Music, фильтр «videos»: официальные клипы (OMV) с пометкой
         типа — самый быстрый и точный путь;
      2. «двойник» играющего трека: у песни каталога YouTube Music знает
         её официальный клип (counterpart), а у самого видео — его тип;
      3. ytsearch через yt-dlp;
      4. Piped/Invidious с фильтром videos.

    Возвращает (кандидаты, был_ли_сбой): сбой отличает «клипа нет» от «сеть
    не ответила», и второе не должно запоминаться как отсутствие клипа.
    """
    failed = False

    async def guarded(job) -> list[dict]:
        nonlocal failed
        try:
            return await job or []
        except Exception as exc:
            failed = True
            log.info("[video] a search path failed: %s", exc)
            return []

    async def twin() -> list[dict]:
        if not own:
            return []
        info = await ytmusic.counterpart(own)
        kind = info.get("kind") or ""
        if info.get("video"):
            return [{**info["video"], "twin": True}]
        if kind in ("OMV", "UGC"):
            # Сам трек — настоящее видео: это и есть клип.
            return [{"id": "yt:" + own, "title": "", "artist": "", "kind": kind,
                     "twin": True, "self": True}]
        return []

    async def via_binary() -> list[dict]:
        if not ytdlp_bin.ready():
            return []
        return await ytdlp_bin.search(query, 8) or []

    tasks = {
        asyncio.create_task(guarded(ytmusic.video_search(query, 10))),
        asyncio.create_task(guarded(twin())),
        asyncio.create_task(guarded(via_binary())),
        asyncio.create_task(guarded(youtube.search(query, 8, videos=True))),
    }
    found: dict[str, dict] = {}

    def take(rows: list[dict]) -> None:
        for row in rows:
            ident = str(row.get("id") or "").removeprefix("yt:")
            if not ident:
                continue
            old = found.get(ident)
            if old is None:
                found[ident] = dict(row)
            else:                      # то же видео из другого пути: сливаем знание
                for key, value in row.items():
                    if value and not old.get(key):
                        old[key] = value
    try:
        grace = None
        while tasks:
            left = deadline - time.monotonic()
            if grace is not None:
                left = min(left, grace - time.monotonic())
            if left <= 0:
                break
            done, tasks = await asyncio.wait(
                tasks, timeout=left, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                break
            for task in done:
                take(task.result())
            if found and grace is None:
                # Первый ответ есть. Остальные получают ещё чуть-чуть: у
                # быстрого пути может не быть самого клипа, а у соседнего есть.
                grace = time.monotonic() + 1.2
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    return list(found.values()), failed


_AUDIO_MARKS = ("(audio)", "[audio]", "official audio", "audio only", "full album",
                "(official audio)", "topic")


def _video_artwork(item: dict) -> bool:
    """Это не клип, а статичная обложка (авто-трек каталога YouTube Music)."""
    if item.get("kind") == "ATV":
        return True
    name = str(item.get("title") or "").casefold()
    author = (str(item.get("artist") or "") + " " + str(item.get("channel") or "")).casefold()
    if author.strip().endswith("- topic") or " - topic" in author:
        return True
    return any(mark in name for mark in _AUDIO_MARKS if mark != "topic")


_CLIP_NOISE = {
    "official", "music", "video", "videos", "clip", "mv", "m", "v", "hd", "hq", "4k",
    "uhd", "1080p", "720p", "remastered", "remaster", "version", "original",
    "feat", "ft", "featuring", "with", "the", "a", "and", "x", "vs", "prod",
    "explicit", "clean", "new", "full", "audio", "lyrics", "lyric", "officiel",
    "oficial", "клип", "официальный", "премьера", "premiere",
}


def _clip_tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", str(text or "").casefold())


def _clip_core(title: str) -> str:
    """Название без хвостов: (feat. …), [Remastered 2011], - Radio Edit."""
    core = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", str(title or ""))
    core = re.split(r"\s[-–—|]\s", core)[0]
    return core.strip() or str(title or "")


def _clip_match(item: dict, artist: str, title: str) -> float:
    """Насколько ролик — именно эта песня этого артиста (0…1).

    Раньше хватало совпасть артисту ИЛИ половине слов, а в счёте артист и
    пометка «official video» весили больше названия, — поэтому другой клип
    того же артиста с похожим названием легко побеждал нужный.
    """
    name = str(item.get("title") or "")
    author = " ".join(str(item.get(k) or "") for k in ("artist", "channel"))
    artist_toks = set(_clip_tokens(artist))
    want = [t for t in _clip_tokens(_clip_core(title)) if t not in _CLIP_NOISE]
    if not want:
        want = _clip_tokens(title)
    have_name = _clip_tokens(name)
    have = set(have_name)
    # Артист обязан встретиться в канале или в названии ролика.
    if artist_toks:
        pool = set(_clip_tokens(author)) | have
        if len(artist_toks & pool) < max(1, (len(artist_toks) + 1) // 2) \
                and artist.casefold().replace(" ", "") not in (author + name).casefold().replace(" ", ""):
            return 0.0
    if not want:
        return 0.5
    hit = sum(1 for t in want if t in have)
    cover = hit / len(want)
    # Лишние значимые слова в названии ролика: «Song 2» вместо «Song»,
    # «Song (Remix)», другая песня того же альбома.
    extra = [t for t in have_name if t not in want and t not in artist_toks
             and t not in _CLIP_NOISE and not re.fullmatch(r"(19|20)\d\d", t)]
    precision = len(want) / (len(want) + 0.5 * len(extra))
    core = " ".join(want)
    joined = " ".join(have_name)
    bonus = 0.15 if core and core in joined else 0.0
    return min(1.0, cover * 0.75 + precision * 0.25 + bonus) if cover else 0.0


def _video_score(item: dict, artist: str, title: str, words: set[str],
                 length: int = 0) -> int:
    name = str(item.get("title") or "").casefold()
    author = str(item.get("artist") or "").casefold()
    text = name + " " + author
    value = int(_clip_match(item, artist, title) * 400)  # название — главное
    kind = item.get("kind") or ""
    if kind == "OMV": value += 60
    elif kind == "ATV": value -= 500
    if item.get("twin"): value += 250
    if "official music video" in text: value += 40
    elif "official video" in text: value += 30
    elif "music video" in text: value += 20
    if artist and author == artist: value += 60
    elif artist and artist in author: value += 40
    if "official" in author or "vevo" in author: value += 15
    # Длительность отсекает петли на час, нарезки и ремиксы другой длины.
    seen = int(item.get("duration") or 0)
    if length and seen:
        gap = abs(seen - length)
        if gap <= max(8, length * 0.06): value += 60
        elif gap <= max(25, length * 0.15): value += 20
        elif gap > max(45, length * 0.35): value -= 200
    want = set(_clip_tokens(title))
    for bad in (" topic", "lyric", "visualizer", "slowed", "nightcore", "remix",
                "cover", "sped up", "instrumental", "live-action", "fan made",
                "fanmade", "reaction", "tutorial", "piano", "1 hour", "loop",
                "karaoke", "8d", "reverb", "acoustic", "live", "teaser", "trailer"):
        if bad in text and not set(_clip_tokens(bad)) <= want:
            value -= 90
    return value


def _video_relevant(item: dict, artist: str, title: str, length: int = 0) -> bool:
    """Ролик — точно эта песня: артист совпал и название почти целиком."""
    if item.get("self"):
        return True
    if item.get("twin") and not item.get("title"):
        return True
    score = _clip_match(item, artist, title)
    need = 0.55 if item.get("twin") else 0.72
    if score < need:
        return False
    seen = int(item.get("duration") or 0)
    if length and seen and not item.get("twin"):
        # Клип бывает длиннее трека (интро), но не в разы и не короче вдвое.
        if seen < length * 0.6 or seen > length * 2.2 + 60:
            return False
    return True


async def _video_id(track_id: str, title: str, artist: str, length: int = 0) -> str:
    """Ищет именно музыкальный клип, а не статичную обложку YouTube Music.

    Быстрый путь: кэш (и попаданий, и промахов) отвечает без сети. Если
    нашлись только авто-треки, честно говорим «клипа нет»: картинка под
    звук — это не то, что просили.
    """
    query = " ".join(x for x in (artist, title, "official music video") if x).strip()
    own = track_id[3:] if track_id.startswith("yt:") else ""
    key = f"{own}|{query or track_id}".casefold()
    cached = _video_id_cache.get(key)
    if cached and time.monotonic() - cached[0] < _VIDEO_TTL:
        return cached[1]
    missed = _video_miss_cache.get(key)
    if missed and time.monotonic() - missed < _VIDEO_MISS_TTL:
        raise VideoMissing("Clip not found")

    async with _video_lock(key):
        cached = _video_id_cache.get(key)
        if cached and time.monotonic() - cached[0] < _VIDEO_TTL:
            return cached[1]
        _warm_ytdlp()
        failed = False
        if query or own:
            found, failed = await _video_candidates(
                query, own, time.monotonic() + _VIDEO_SEARCH_BUDGET)
            wanted_artist = artist.split(",")[0].strip().casefold()
            wanted_title = title.casefold()
            wanted_words = {
                word for word in re.findall(r"[a-zа-я0-9]+", wanted_title)
                if len(word) > 2 and word not in {"feat", "ft"}
            }
            real = [item for item in found if not _video_artwork(item)
                    and _video_relevant(item, wanted_artist, title, length)]
            if real:
                picked = max(real, key=lambda item: _video_score(
                    item, wanted_artist, title, wanted_words, length))
                video_id = str(picked.get("id") or "").removeprefix("yt:")
                if video_id:
                    _video_id_cache[key] = (time.monotonic(), video_id)
                    # Экран клипов потом просит поток уже по id самого клипа:
                    # тот же ответ запоминаем и под ним, без второго поиска.
                    _video_id_cache[f"{video_id}|{query or track_id}".casefold()] = (
                        time.monotonic(), video_id)
                    _video_miss_cache.pop(key, None)
                    log.info("[video] %s — %s -> %s (%s)", artist, title,
                             video_id, picked.get("kind") or "video")
                    return video_id
            if found:
                log.info("[video] %s — %s: only cover-art tracks found", artist, title)
        if failed and not _video_miss_cache.get(key):
            # Сеть не ответила — это не «клипа нет». Повторим при следующем заходе.
            raise RuntimeError("The video search did not answer; check the network or the proxy")
        _video_miss_cache[key] = time.monotonic()
        raise VideoMissing("Clip not found")


async def _video_link_at(video_id: str, quality: int, *, refresh: bool = False,
                         attempt: int = 0, budget: float = 22.0) -> dict:
    """Прямая совмещённая дорожка нужного качества, с кэшем ссылки.

    Совмещённый progressive-файл весит в разы меньше, чем 1080p DASH, и
    браузер тянет его сам ровно теми кусками, которые нужны — это и есть
    экономия трафика «как в YouTube», без склейки через FFmpeg.
    """
    key = f"{video_id}@{quality}"
    if not refresh:
        cached = _video_link_cache.get(key)
        if cached and time.monotonic() - cached[0] < _VIDEO_LINK_TTL:
            return cached[1]
    async with _video_lock("link:" + key):
        cached = _video_link_cache.get(key)
        if cached and not refresh and time.monotonic() - cached[0] < _VIDEO_LINK_TTL:
            return cached[1]
        # Public frontends, the packaged yt-dlp and the built-in libraries
        # (yt_dlp, pytubefix) race each other.  On a
        # network where one path is blocked, it no longer delays the working
        # path.  Both return a progressive video+audio file, so the proxy can
        # hand the first bytes to <video> while the rest keeps downloading.
        tasks = {
            asyncio.create_task(youtube.video(video_id, quality)),
            asyncio.create_task(ytdlp_bin.video(video_id, quality, attempt=attempt)),
            asyncio.create_task(ytlibs.video(video_id, quality)),
        }
        errors: list[str] = []
        deadline = time.monotonic() + max(2.0, budget)
        try:
            while tasks:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise RuntimeError(errors[-1] if errors
                                       else "the source did not answer in time")
                done, tasks = await asyncio.wait(
                    tasks, timeout=left, return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    raise RuntimeError(errors[-1] if errors
                                       else "the source did not answer in time")
                for task in done:
                    try:
                        media = task.result()
                    except Exception as exc:
                        errors.append(str(exc))
                        continue
                    if not media.get("url"):
                        continue
                    for other in tasks:
                        other.cancel()
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    _video_link_cache[key] = (time.monotonic(), media)
                    return media
            raise RuntimeError(errors[-1] if errors else "Clip not found")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()


async def _video_link(video_id: str, quality: int, *, refresh: bool = False,
                      attempt: int = 0, budget: float = _VIDEO_LINK_BUDGET) -> dict:
    """Ссылка на клип со спуском по качеству прямо на сервере.

    Совмещённых дорожек выше 720p у YouTube почти нет, а на части клиентов
    плеера их нет и на 720p. Раньше спуск делал только экран клипов — каждая
    ступень стоила новый запрос из окна и ещё один показ «ищу клип». Теперь
    сервер проходит лестницу сам, в пределах общего бюджета.
    """
    fail_key = f"{video_id}@{quality}"
    if not refresh:
        failed = _video_link_fail.get(fail_key)
        if failed and time.monotonic() - failed[0] < _VIDEO_FAIL_TTL:
            _video_errors[video_id] = failed[1]
            raise RuntimeError(failed[1])
    deadline = time.monotonic() + max(3.0, budget)
    last: Exception | None = None
    for height in _video_ladder(quality):
        left = deadline - time.monotonic()
        if left <= 1.0 and last is not None:
            break
        try:
            media = await _video_link_at(video_id, height, refresh=refresh,
                                         attempt=attempt, budget=max(4.0, left))
            _video_link_fail.pop(fail_key, None)
            _video_errors.pop(video_id, None)
            return media
        except Exception as exc:
            last = exc
            log.info("[video] %s: %sp did not play: %s", video_id, height, exc)
    reason = str(last) if last else "Clip not found"
    _video_errors[video_id] = reason
    _video_link_fail[fail_key] = (time.monotonic(), reason)
    raise RuntimeError(reason)


_dash_cache: dict[str, tuple[float, dict]] = {}
_dash_bad: dict[str, set[str]] = {}      # источники, чьи ссылки отдали 403 при загрузке


async def _probe_track(session, track: dict) -> None:
    """Пробный запрос к дорожке: ссылка должна реально отдавать байты.
    Проверяются начало и середина файла — часть ссылок YouTube даёт 403
    на скачивание, хотя сама выдаётся без ошибок."""
    size = int(track.get("size") or 0)
    spots = [0] + ([size // 2] if size > 4 * 1024 * 1024 else [])
    for pos in spots:
        headers = {k: v for k, v in (track.get("headers") or {}).items()
                   if k.lower() not in ("range", "host", "content-length")}
        headers["Range"] = f"bytes={pos}-{pos + 1023}"
        async with session.get(track["url"], headers=headers,
                               timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"the link was refused (HTTP {resp.status})")
            await resp.content.read(256)


async def _check_pair(pair: dict) -> None:
    session = await http()
    await asyncio.gather(_probe_track(session, pair["video"]),
                         _probe_track(session, pair["audio"]))


async def _checked(pending) -> dict:
    pair = await pending
    await _check_pair(pair)
    return pair


async def _dash_pair(video_id: str, quality: int, refresh: bool = False) -> dict:
    """Две дорожки клипа (видео и звук) нужной высоты. Пути идут наперегонки:
    плеер YouTube напрямую, библиотека yt_dlp и бинарник yt-dlp."""
    key = f"{video_id}@{quality}"
    cached = _dash_cache.get(key)
    if cached and not refresh and time.monotonic() - cached[0] < _VIDEO_LINK_TTL:
        return cached[1]
    async with _video_lock("dash:" + key):
        cached = _dash_cache.get(key)
        if cached and not refresh and time.monotonic() - cached[0] < _VIDEO_LINK_TTL:
            return cached[1]
        if cached and refresh:
            if time.monotonic() - cached[0] < 12:
                return cached[1]         # соседнее окно уже обновило ссылку
            # Ссылка прошла пробу, но на загрузке дала 403: этот источник
            # отодвигаем и пробуем другой.
            _dash_bad.setdefault(key, set()).add(str(cached[1].get("source") or ""))
        bad = _dash_bad.get(key, set())
        makers = {
            "innertube": lambda: youtube.innertube_dash(video_id, quality, _check_pair),
            "ytlibs": lambda: ytlibs.dash(video_id, quality, _check_pair),
            "mirror": lambda: youtube.mirror_dash(video_id, quality, _check_pair),
            "plain": lambda: _checked(ytdlp_bin.dash_plain(video_id, quality)),
            "bin": lambda: _checked(ytdlp_bin.dash(video_id, quality,
                                                   attempt=1 if refresh else 0)),
        }
        names = [n for n in makers if n not in bad] or list(makers)
        if len(names) == len(makers):
            _dash_bad.pop(key, None)

        async def run(name: str) -> dict:
            pair = await makers[name]()
            pair["source"] = name
            return pair

        tasks = {asyncio.create_task(run(n)) for n in names}
        errors: list[str] = []
        deadline = time.monotonic() + 40
        try:
            while tasks:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                done, tasks = await asyncio.wait(
                    tasks, timeout=left, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    try:
                        pair = task.result()
                    except Exception as exc:
                        errors.append(str(exc))
                        continue
                    _dash_cache[key] = (time.monotonic(), pair)
                    return pair
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        log.info("[video] %s: no usable tracks at %sp: %s", video_id, quality, " | ".join(errors))
        wall = any(("not a bot" in e.lower() or "sign in to confirm" in e.lower()
                    or "confirm you" in e.lower()) for e in errors)
        if wall:
            reason = ytdlp_bin.BOT_HINT
        else:
            reason = next((e for e in reversed(errors) if "no separate" not in e),
                          errors[-1] if errors else "the source did not answer in time")
        raise RuntimeError(reason)


def _dash_resolver(video_id: str, quality: int):
    async def resolve(refresh: bool) -> dict:
        return await _dash_pair(video_id, quality, refresh)
    return resolve


async def _hd_info(video_id: str, quality: int, retry: bool) -> web.Response:
    """Клип выше 360p: готов — отдаём, иначе запускаем сборку и сообщаем ход."""
    saved = await asyncio.to_thread(clipcache.ready_hd, video_id, quality)
    if saved:
        return ok({"id": video_id, "height": saved[1], "ready": True, "cached": True,
                   "preparing": False, "progress": 1, "mime": "video/mp4",
                   "direct": True, "streaming": True, "reason": ""})
    job = clipcache.ensure_hd(await http(), video_id, quality,
                              _dash_resolver(video_id, quality), force=retry)
    for _ in range(8):                       # короткое ожидание: часто хватает
        if job.finished:
            break
        await asyncio.sleep(0.2)
    if job.state == "error":
        return fail(job.error or "The clip could not be prepared", 502)
    done = job.state == "done"
    return ok({"id": video_id, "height": job.height or quality, "ready": done,
               "cached": done, "preparing": not done, "stage": job.state,
               "progress": round(job.progress, 3), "mime": "video/mp4",
               "direct": True, "streaming": True, "reason": ""})


def _media_getter(video_id: str, quality: int):
    """Функция «дай свежую ссылку» для загрузчика и прокси клипов."""
    async def get(refresh: bool) -> dict:
        return await _video_link(video_id, quality, refresh=refresh,
                                 attempt=1 if refresh else 0,
                                 budget=14.0 if refresh else _VIDEO_LINK_BUDGET)
    return get


def _clip_preload() -> bool:
    try:
        return bool(storage.get_settings().get("clipPreload", True))
    except Exception:
        return True


async def _video_warm(track_id: str, title: str, artist: str, quality: int,
                      length: int = 0) -> None:
    """Находит клип, берёт ссылку и сразу качает файл на диск."""
    key = f"{track_id}@{quality}"
    if key in _video_warming:
        return
    _video_warming.add(key)
    try:
        video_id = await _video_id(track_id, title, artist, length)
        if quality > _PROGRESSIVE_MAX:
            if _clip_preload() and not await asyncio.to_thread(
                    clipcache.ready_hd, video_id, quality):
                clipcache.ensure_hd(await http(), video_id, quality,
                                    _dash_resolver(video_id, quality))
            return
        if await asyncio.to_thread(clipcache.ready_file, video_id, quality):
            return
        media = await _video_link(video_id, quality)
        if _clip_preload():
            clipcache.ensure(await http(), video_id, int(media.get("height") or 0),
                             _media_getter(video_id, quality))
    except Exception:
        pass
    finally:
        _video_warming.discard(key)


@routes.get("/api/video/info")
async def api_video_info(request: web.Request) -> web.Response:
    """Быстрый ответ «клип есть / клипа нет» плюс готовая прямая ссылка."""
    track_id = (request.query.get("id") or "").strip()
    if not track_id:
        return fail("track id is required")
    quality = _int(request, "quality", 720, 144, 2160)
    length = _int(request, "dur", 0, 0, 36000)
    try:
        video_id = await _video_id(
            track_id, request.query.get("title") or "",
            request.query.get("artist") or "", length)
    except VideoMissing:
        return fail("Clip not found", 404)
    except Exception as exc:
        return fail(str(exc), 502)
    if quality > _PROGRESSIVE_MAX:
        return await _hd_info(video_id, quality, request.query.get("retry") == "1")
    saved = await asyncio.to_thread(clipcache.ready_file, video_id, quality)
    if saved:
        # Клип уже на диске: ни поиска ссылки, ни сети — старт мгновенный.
        return ok({"id": video_id, "height": saved[1], "width": 0, "duration": None,
                   "mime": "video/mp4", "direct": True, "ready": True,
                   "cached": True, "reason": "", "streaming": True})
    media: dict = {}
    # Ссылку на дорожку ждём недолго и не до конца: её добирает фоновая
    # задача, а прокси возьмёт уже готовое из кэша. Окно перестаёт стоять
    # на «ищу клип» всё время, пока YouTube перебирает клиентов плеера.
    _video_errors.pop(video_id, None)
    task = _background(request.app, _video_link(video_id, quality))
    # Фоновая задача не должна ругаться «exception was never retrieved»:
    # её ошибку всё равно покажет прокси, когда попробует открыть поток.
    task.add_done_callback(lambda done: done.cancelled() or done.exception())
    try:
        media = await asyncio.wait_for(asyncio.shield(task), 8)
    except asyncio.TimeoutError:
        log.info("[video] %s: the link is still coming, starting the proxy", video_id)
    except Exception as exc:
        log.info("[video] direct link failed for %s: %s", video_id, exc)
    if media.get("url"):
        # Загрузка на диск стартует сразу: пока клип открывается, он уже качается.
        clipcache.ensure(await http(), video_id, int(media.get("height") or 0),
                         _media_getter(video_id, quality))
    return ok({
        "id": video_id,
        "height": int(media.get("height") or 0) or quality,
        "width": int(media.get("width") or 0),
        "duration": media.get("duration"),
        "mime": media.get("mime") or "video/mp4",
        "direct": True,
        "ready": bool(media.get("url")),
        "cached": False,
        "reason": _video_errors.get(video_id, ""),
        "streaming": True,
    })


@routes.get("/api/video/warm")
async def api_video_warm(request: web.Request) -> web.Response:
    """Греет клип в фоне: находит, берёт ссылку и качает файл на диск."""
    track_id = (request.query.get("id") or "").strip()
    if not track_id:
        return fail("track id is required")
    quality = _int(request, "quality", 720, 144, 2160)
    _background(request.app, _video_warm(
        track_id, request.query.get("title") or "",
        request.query.get("artist") or "", quality,
        _int(request, "dur", 0, 0, 36000)))
    return ok({"warming": True})


@routes.get("/api/video/cache")
async def api_video_cache(request: web.Request) -> web.Response:
    old=clipcache.status();new=await asyncio.to_thread(clipstream.cache_status)
    return ok({**old,"files":old["files"]+new["files"],"bytes":old["bytes"]+new["bytes"]})


@routes.delete("/api/video/cache")
async def api_video_cache_clear(request: web.Request) -> web.Response:
    _karaoke_origin(request)
    removed = await clipstream.clear_cache(request.app.get("clip_streams"))
    removed += await asyncio.to_thread(clipcache.clear)
    return ok({"removed": removed, **clipcache.status()})


def _range_bounds(header: str) -> tuple[int | None, int | None]:
    """(первый байт, последний байт) из заголовка Range; None — не задан."""
    match = re.match(r"bytes=(\d*)-(\d*)\s*$", (header or "").strip(), re.I)
    if not match:
        return None, None
    start = int(match.group(1)) if match.group(1) else None
    stop = int(match.group(2)) if match.group(2) else None
    return start, stop


@routes.get("/api/video/proxy")
async def api_video_proxy(request: web.Request) -> web.StreamResponse:
    """Клип для <video>: настоящий 206 с любой позиции, перемотка работает.

    Порядок такой:
      1. файл уже скачан — отдаём с диска (aiohttp сам разбирает Range);
      2. иначе стартует фоновая загрузка на диск, и ответ собирается из
         трёх источников по мере надобности: что скачано — с диска, что чуть
         впереди — после ожидания загрузчика, далёкая перемотка — отдельным
         Range-окном прямо из CDN.
    Ответ всегда честный: Content-Range и Content-Length посчитаны по
    настоящему размеру файла, даже если CDN проигнорировал Range и ответил 200.
    """
    track_id = (request.query.get("id") or "").strip()
    if not track_id:
        return fail("track id is required")
    quality = _int(request, "quality", 720, 144, 2160)
    try:
        video_id = await _video_id(
            track_id, request.query.get("title") or "",
            request.query.get("artist") or "", _int(request, "dur", 0, 0, 36000))
    except VideoMissing:
        return fail("Clip not found", 404)
    except Exception as exc:
        return fail(str(exc), 502)

    if quality > _PROGRESSIVE_MAX:
        saved = await asyncio.to_thread(clipcache.ready_hd, video_id, quality)
        if not saved:
            return fail("The clip is still being prepared", 409)
    else:
        saved = await asyncio.to_thread(clipcache.ready_file, video_id, quality)
    if saved:
        try:
            os.utime(saved[0])                 # свежие файлы чистятся последними
        except OSError:
            pass
        return web.FileResponse(saved[0], headers={
            "Content-Type": "video/webm" if saved[0].endswith(".webm") else "video/mp4",
            "Cache-Control": "no-store"})

    session = await http()
    get_media = _media_getter(video_id, quality)
    try:
        media = await get_media(False)
    except VideoMissing:
        return fail("Clip not found", 404)
    except Exception as exc:
        return fail(str(exc), 502)
    job = clipcache.ensure(session, video_id, int(media.get("height") or 0), get_media)

    # Нужен точный размер файла: без него нельзя честно ответить на Range.
    waited = time.monotonic()
    while job.total is None and not job.finished and time.monotonic() - waited < 12:
        await job.wait(0.4)
    total = job.total
    if total is None:
        try:
            probe = await clipcache.open_window(session, get_media, 0, 0)
            total = probe.total
            probe.release()
        except Exception as exc:
            return fail(str(exc), 502)
    if not total:
        return fail("The clip size is unknown", 502)

    raw_range = request.headers.get("Range", "")
    first, last = _range_bounds(raw_range)
    partial = bool(raw_range) and (first is not None or last is not None)
    if first is None and last is not None:           # bytes=-N: последние N байт
        first, last = max(0, total - last), total - 1
    first = 0 if first is None else first
    last = total - 1 if last is None else min(last, total - 1)
    if first >= total or first > last:
        return web.Response(status=416, headers={"Content-Range": f"bytes */{total}"})

    out = web.StreamResponse(status=206 if partial else 200)
    out.headers["Content-Type"] = media.get("mime") or "video/mp4"
    out.headers["Accept-Ranges"] = "bytes"
    out.headers["Cache-Control"] = "no-store"
    out.content_length = last - first + 1
    if partial:
        out.headers["Content-Range"] = f"bytes {first}-{last}/{total}"
    await out.prepare(request)
    if request.method == "HEAD":
        return out

    pos = first
    disk_ok = True
    idle = time.monotonic()
    try:
        while pos <= last:
            have = (job.total if job.done else (0 if job.error else job.written)) \
                if disk_ok else 0
            if pos < have:
                try:
                    data = await asyncio.to_thread(
                        clipcache.read_at, job.path(), pos,
                        min(256 * 1024, have - pos, last - pos + 1))
                except OSError:
                    data = b""
                if not data:
                    if job.done:               # файл переименовали под руками
                        await asyncio.sleep(0.05)
                        continue
                    disk_ok = False
                    continue
                await out.write(data)
                pos += len(data)
                idle = time.monotonic()
                continue
            if (disk_ok and not job.finished and pos - have <= clipcache.AHEAD
                    and time.monotonic() - idle < 15):
                await job.wait(1.0)
                continue
            # Далёкая перемотка (или загрузчик встал): окно прямо из CDN.
            win = await clipcache.open_window(
                session, get_media, pos, min(last, pos + clipcache.CHUNK - 1))
            moved = 0
            try:
                if win.resp.status == 416:
                    break
                async for chunk in win.chunks():
                    chunk = chunk[:last - pos + 1]
                    if not chunk:
                        break
                    await out.write(chunk)
                    pos += len(chunk)
                    moved += len(chunk)
                    if pos > last or (disk_ok and pos < job.written and not job.error):
                        break
            finally:
                win.release()
            if not moved:
                break
            idle = time.monotonic()
    except (ConnectionResetError, asyncio.CancelledError):
        raise
    except Exception as exc:
        log.info("[video] %s: the stream stopped at %s of %s: %s",
                 video_id, pos, total, exc)
    return out


@routes.get("/api/video/stream")
async def api_video_stream(request: web.Request) -> web.StreamResponse:
    """Запасной путь: склейка DASH-дорожек через FFmpeg, если нет progressive."""
    track_id = (request.query.get("id") or "").strip()
    if not track_id:
        return fail("track id is required")
    quality = _int(request, "quality", 720, 144, 2160)
    ffmpeg = shutil.which("ffmpeg")
    try:
        video_id = await _video_id(
            track_id, request.query.get("title") or "",
            request.query.get("artist") or "")
        if not ffmpeg:
            # Portable fallback: yt-dlp writes a combined progressive file to
            # stdout.  The response is prepared after the first chunk, not
            # after the whole clip, so playback and download run together.
            fmt = (
                f"best[ext=mp4][vcodec^=avc1][height<={quality}][acodec!=none]"
                f"/best[ext=mp4][height<={quality}][vcodec!=none][acodec!=none]"
                f"/best[height<={quality}][vcodec!=none][acodec!=none]/best"
            )
            proc = await ytdlp_bin.pipe_format(video_id, fmt)
            try:
                first = await asyncio.wait_for(proc.stdout.read(128 * 1024), timeout=30)
            except asyncio.TimeoutError:
                first = b""
            if not first:
                error = (await proc.stderr.read()).decode("utf-8", "replace").strip()
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
                return fail(error.splitlines()[-1] if error else "Video stream did not start", 502)
            response = web.StreamResponse(status=200, headers={
                "Content-Type": "video/mp4", "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            })
            await response.prepare(request)
            try:
                await response.write(first)
                while True:
                    chunk = await proc.stdout.read(256 * 1024)
                    if not chunk:
                        break
                    await response.write(chunk)
            except (ConnectionResetError, aiohttp.ClientConnectionError):
                pass
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            return response
        port = request.transport.get_extra_info("sockname")[1]
        base = f"http://127.0.0.1:{port}/api/video/part"
        common = f"id=yt:{video_id}&quality={quality}"
        kwargs = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-i", base + "?" + common + "&kind=video",
            "-i", base + "?" + common + "&kind=audio",
            "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "-f", "mp4", "pipe:1", **kwargs)
        try:
            first = await asyncio.wait_for(proc.stdout.read(256 * 1024), timeout=45)
        except asyncio.TimeoutError:
            first = b""
        if not first:
            error = (await proc.stderr.read()).decode("utf-8", "replace").strip()
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            return fail(error.splitlines()[-1] if error else "Video stream did not start", 502)
        response = web.StreamResponse(
            status=200, headers={"Content-Type": "video/mp4", "Cache-Control": "no-store"})
        await response.prepare(request)
        try:
            await response.write(first)
            while True:
                chunk = await proc.stdout.read(256 * 1024)
                if not chunk: break
                await response.write(chunk)
        except (ConnectionResetError, aiohttp.ClientConnectionError):
            pass
        finally:
            if proc.returncode is None: proc.kill()
            await proc.wait()
        return response
    except VideoMissing:
        return fail("Clip not found", 404)
    except Exception as exc:
        return fail(str(exc), 502)


@routes.get("/api/video/part")
async def api_video_part(request: web.Request) -> web.StreamResponse:
    """Внутренняя DASH-дорожка для потокового объединения через FFmpeg."""
    raw = (request.query.get("id") or "").strip()
    video_id = raw[3:] if raw.startswith("yt:") else raw
    quality = _int(request, "quality", 720, 144, 2160)
    kind = request.query.get("kind")
    if not video_id or kind not in ("video", "audio"):
        return fail("invalid video part", 400)
    fmt = ("bestaudio[ext=m4a]/bestaudio" if kind == "audio" else
           f"bestvideo[ext=mp4][vcodec^=avc1][height<={quality}]"
           f"/bestvideo[ext=mp4][height<={quality}]/bestvideo[height<={quality}]")
    proc = await ytdlp_bin.pipe_format(video_id, fmt)
    response = web.StreamResponse(
        status=200, headers={"Content-Type": "application/octet-stream",
                             "Cache-Control": "no-store"})
    await response.prepare(request)
    try:
        while True:
            chunk = await proc.stdout.read(256 * 1024)
            if not chunk: break
            await response.write(chunk)
    except (ConnectionResetError, aiohttp.ClientConnectionError):
        pass
    finally:
        if proc.returncode is None: proc.kill()
        await proc.wait()
    return response


async def _media_for(track_id: str, title: str = "", artist: str = "",
                     fallback: bool = False, *, refresh: bool = False,
                     attempt: int = 0) -> tuple[str, dict]:
    """v72: the resolved link remembers the quality mode it was chosen under,
    so the cached object is labelled with the tier it really has."""
    from . import audio_quality
    source_id, media = await _media_for_raw(track_id, title, artist, fallback,
                                            refresh=refresh, attempt=attempt)
    if isinstance(media, dict):
        media.setdefault("tier", audio_quality.mode())
        media.setdefault("source_id", source_id)
    return source_id, media


async def _media_for_raw(track_id: str, title: str = "", artist: str = "",
                         fallback: bool = False, *, refresh: bool = False,
                         attempt: int = 0) -> tuple[str, dict]:
    """(id источника, media) — прямая ссылка на аудио, с подменой источника."""
    metadata_only = track_id.startswith(("sp:", "dz:"))
    first_error: Exception | None = None

    # Metadata ids are expected to have no stream of their own.  Do not call
    # providers.resolve just to emit a warning before the normal replacement.
    if not metadata_only:
        try:
            media = await providers.resolve(track_id, refresh=refresh, attempt=attempt)
            if not refresh and providers.link_expired(media):
                log.info("[stream] %s: ссылка на грани срока, беру свежую", track_id)
                media = await providers.resolve(track_id, refresh=True, attempt=attempt + 1)
            return track_id, media
        except Exception as exc:
            first_error = exc
            log.warning("[stream] %s: %s", track_id, exc)

    if (fallback or metadata_only) and (title or artist):
        lock = _metadata_media_lock(track_id) if metadata_only else asyncio.Lock()
        async with lock:
            cached = _metadata_media_cache.get(track_id) if metadata_only and not refresh else None
            if cached and time.monotonic() - cached[0] < 300 \
                    and not providers.link_expired(cached[2]):
                return cached[1], cached[2]
            try:
                candidate = await streaming.playable(
                    {"id": track_id, "title": title, "artist": artist}, skip={track_id})
                if candidate and candidate.get("stream"):
                    stream = candidate["stream"]
                    media = {
                        "url": stream["url"], "headers": stream.get("headers") or {},
                        "size": stream.get("size"), "mime": stream.get("mimeType"),
                        "duration": stream.get("duration"),
                    }
                    if metadata_only:
                        _metadata_media_cache[track_id] = (
                            time.monotonic(), candidate["id"], media)
                    log.info("[stream] replacement %s -> %s (%s)",
                             track_id, candidate["id"],
                             (candidate.get("source") or {}).get("name"))
                    return candidate["id"], media
            except Exception as exc:
                log.warning("[stream] no replacement found: %s", exc)

    if metadata_only:
        name = "Spotify" if track_id.startswith("sp:") else "Deezer"
        raise RuntimeError(f"{name}: no playable replacement found in enabled libraries")
    raise RuntimeError(str(first_error or "stream unavailable"))


async def _ensure_file(track_id: str, title: str = "", artist: str = "",
                       fallback: bool = False) -> str:
    """Скачивает трек в кэш целиком (предзагрузка следующего и офлайн)."""
    if not audiovault.enabled():
        raise RuntimeError("Enable internal audio cache before saving tracks for replay")
    ready = audiocache.find(track_id)
    if ready:
        return ready

    async with audiocache.lock(track_id):
        ready = audiocache.find(track_id)
        if ready:
            return ready
        source_id, media = await _media_for(track_id, title, artist, fallback)
        # Та же защита, что и в живом стриме: протухшую ссылку меняем на новую,
        # иначе предзагрузка и «сохранить на устройство» падали молча.
        for attempt in range(_STREAM_ATTEMPTS):
            try:
                return await audiocache.download(await http(), track_id, media)
            except audiocache.SourceError as exc:
                if not exc.stale or attempt == _STREAM_ATTEMPTS - 1:
                    raise
                providers.invalidate_stream(source_id)
                source_id, media = await _media_for(
                    track_id, title, artist, fallback or attempt >= 1,
                    refresh=True, attempt=attempt + 1)
        raise RuntimeError("the source refused every link for this track")


# A single speculative successor; already-playing work is never cancelled.
_prefetch_task30: asyncio.Task | None = None
_prefetch_id30 = ""
_prefetch_lock30 = asyncio.Lock()
_prefetch_tasks30: set[asyncio.Task] = set()
_prefetch_status61: dict[str, dict] = {}


async def _prefetch_one30(track_id: str, title: str, artist: str, download: bool) -> None:
    try:
        if download and audiovault.enabled():
            await _ensure_file(track_id, title, artist)
            cached = bool(audiocache.find(track_id))
            _prefetch_status61[track_id] = {"state": "downloaded" if cached else "resolved", "cached": cached}
        else:
            await _media_for(track_id, title, artist)
            _prefetch_status61[track_id] = {"state": "resolved", "cached": False}
    except asyncio.CancelledError:
        _prefetch_status61[track_id] = {"state": "cancelled", "cached": False}
        raise
    except Exception as exc:
        _prefetch_status61[track_id] = {"state": "error", "cached": False}
        log.debug("Next-track warm-up failed: %s", type(exc).__name__)


@routes.get("/api/prefetch")
async def api_prefetch(request: web.Request) -> web.Response:
    async with _prefetch_lock30:
        return await _api_prefetch30(request)


async def _api_prefetch30(request: web.Request) -> web.Response:
    global _prefetch_task30, _prefetch_id30
    if request.query.get("cancel") == "1":
        _karaoke_origin(request)
        keep = "prefetch:" + request.query.get("current", "")
        obsolete = [task for task in _prefetch_tasks30 if not task.done() and task.get_name() != keep]
        for task in obsolete:
            task.cancel()
        await asyncio.gather(*obsolete, return_exceptions=True)
        return ok({"cancelled":len(obsolete)})
    track_id = (request.query.get("id") or "").strip()
    if not track_id or len(track_id) > 2048:
        return fail("track id is required")
    if request.query.get("status") == "1":
        if audiocache.find(track_id):
            return ok({"state": "downloaded", "cached": True})
        state = _prefetch_status61.get(track_id, {"state":"idle", "cached":False})
        # A bounded vault may evict or clear an earlier successful download.
        if state.get("state") == "downloaded":
            state = {"state":"error", "cached":False}
        return ok(state)
    obsolete = [task for task in _prefetch_tasks30 if not task.done()
                and task.get_name() not in {"prefetch:" + track_id,
                                            "prefetch:" + request.query.get("current", "")}]
    for task in obsolete:
        task.cancel()
    await asyncio.gather(*obsolete, return_exceptions=True)
    if track_id.startswith("rb:"):
        return ok({"ready": True, "cached": False, "live": True})
    if audiocache.find(track_id):
        return ok({"ready": True, "cached": True})
    if _prefetch_task30 and not _prefetch_task30.done():
        if _prefetch_id30 == track_id:
            return ok({"ready": False, "cached": False, "busy": True})
        if _prefetch_id30 != request.query.get("current"):
            _prefetch_task30.cancel()
            await asyncio.gather(_prefetch_task30, return_exceptions=True)
    _prefetch_id30 = track_id
    if len(_prefetch_status61) >= 32:
        for key in list(_prefetch_status61)[:16]:
            _prefetch_status61.pop(key, None)
    _prefetch_status61[track_id] = {"state":"preparing", "cached":False}
    _prefetch_task30 = asyncio.create_task(_prefetch_one30(
        track_id, (request.query.get("title") or "")[:512],
        (request.query.get("artist") or "")[:512], request.query.get("download") != "0"), name="prefetch:" + track_id)
    _prefetch_tasks30.add(_prefetch_task30)
    _prefetch_task30.add_done_callback(_prefetch_tasks30.discard)
    return ok({"ready": False, "cached": False, "busy": True})


def _kbps(value) -> int | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return int(round(v / 1000)) if v > 4000 else int(round(v))


_CODEC_NAMES = {"opus": "Opus", "mp4a": "AAC", "aac": "AAC", "mp3": "MP3", "vorbis": "Vorbis",
                "flac": "FLAC", "alac": "ALAC", "pcm": "PCM", "wav": "PCM"}


def _codec_label(codec, mime) -> str | None:
    text = str(codec or "").lower()
    for key, name in _CODEC_NAMES.items():
        if text.startswith(key):
            return name
    m = str(mime or "").lower()
    return {"audio/ogg": "Opus", "audio/webm": "Opus", "audio/mp4": "AAC", "audio/mpeg": "MP3",
            "audio/flac": "FLAC", "audio/wav": "PCM", "audio/x-wav": "PCM"}.get(m.split(";")[0])


@routes.get("/api/stream/info")
async def api_stream_info(request: web.Request) -> web.Response:
    """v72: what is really playing — codec, bitrate, cache tier. Never resolves
    a new link: it only reads what playback already obtained."""
    from . import audio_quality
    track_id = (request.query.get("id") or "").strip()
    if not track_id or len(track_id) > 2048:
        return fail("track id is required")
    try:
        duration = float(request.query.get("dur") or 0)
    except ValueError:
        duration = 0.0
    mode = audio_quality.mode()
    out = {"id": track_id, "mode": mode, "cached": False, "tier": None, "codec": None,
           "kbps": None, "estimated": False, "mime": None, "size": None, "satisfies": None}
    token = await asyncio.to_thread(audiocache.find, track_id)
    doc = await asyncio.to_thread(audiovault.info, token) if token else None
    if doc:
        out.update(cached=True, tier=doc.get("tier") or "best", mime=doc.get("mime"),
                   size=doc.get("size"), kbps=_kbps(doc.get("kbps")))
        out["codec"] = _codec_label(doc.get("codec"), doc.get("mime"))
        out["satisfies"] = audiovault.TIERS.get(out["tier"], 2) >= audiovault.TIERS[mode]
        if not out["kbps"] and duration > 1 and doc.get("size"):
            out["kbps"] = int(round(doc["size"] * 8 / duration / 1000)); out["estimated"] = True
        if out["satisfies"]:
            return ok(out)
    media = providers._stream_cache.get(track_id)
    if media is None:
        cached = _metadata_media_cache.get(track_id)
        media = cached[2] if cached else None
    if isinstance(media, dict):
        out.update(mime=media.get("mime"), tier=media.get("tier") or mode, live=True)
        out["codec"] = _codec_label(media.get("codec"), media.get("mime"))
        out["kbps"] = _kbps(media.get("bitrate"))
        out["estimated"] = False
        if not out["kbps"] and duration > 1 and media.get("size"):
            out["kbps"] = int(round(int(media["size"]) * 8 / duration / 1000)); out["estimated"] = True
    return ok(out)


@routes.post("/api/stream/requality")
async def api_stream_requality(request: web.Request) -> web.Response:
    """v72: apply the current quality mode to one track now. The resolved link is
    forgotten; a cached object of a lower tier is replaced by the next stream."""
    from . import audio_quality
    data = await _body(request)
    track_id = str(data.get("id") or "").strip()
    if not track_id or len(track_id) > 2048:
        return fail("track id is required")
    providers.invalidate_stream(track_id)
    _metadata_media_cache.pop(track_id, None)
    try:
        streaming._candidates.clear()
    except Exception:
        pass
    mode = audio_quality.mode()
    token = await asyncio.to_thread(audiocache.find, track_id)
    satisfied = bool(token) and await asyncio.to_thread(audiovault.tier_ok, token, mode)
    return ok({"id": track_id, "mode": mode, "cached": bool(token), "reload": not satisfied})


@routes.get("/api/stream")
async def api_stream(request: web.Request) -> web.StreamResponse:
    """Аудио для тега <audio>.

    Уже скачанный трек отдаётся с диска. Новый начинает играть сразу: байты
    идут от источника в браузер и попутно ложатся в кэш, ждать полной
    загрузки не нужно.
    """
    track_id = (request.query.get("id") or "").strip()
    if not track_id:
        return fail("track id is required")

    # Радиостанция — живой поток, кэшировать нечего.
    if track_id.startswith("rb:"):
        try:
            media = await providers.resolve(track_id)
        except Exception as exc:
            return fail(str(exc), 502)
        return web.HTTPFound(media["url"])

    await asyncio.to_thread(audiocache.touch_periodic)
    # Final network bytes may reach the browser before the SQLite commit.
    # Reuse the finishing object instead of resolving/downloading it twice.
    if audiocache.committing(track_id):
        async with audiocache.lock(track_id): pass
    path = await asyncio.to_thread(audiocache.find, track_id)
    lower = None
    # v72: an object cached under a lower quality mode is not served when a
    # higher one is selected — it is replaced by a fresh stream. It stays as the
    # offline fallback if the source cannot be reached.
    if path and request.query.get("q") != "any" and not await asyncio.to_thread(audiovault.tier_ok, path):
        lower, path = path, None
    if path:
        try:
            return await audiovault.serve(request, path)
        except web.HTTPNotFound:
            # The object may have been evicted after find(), before the read
            # transaction began. Resolve the source rather than failing playback.
            pass

    title = (request.query.get("title") or "").strip()
    artist = (request.query.get("artist") or "").strip()
    fallback = request.query.get("fb") == "1"
    fresh = request.query.get("fresh") == "1"
    range_header = request.headers.get("Range", "")

    try:
        source_id, media = await _media_for(track_id, title, artist, fallback,
                                            refresh=fresh)
    except Exception as exc:
        if lower:
            try:
                return await audiovault.serve(request, lower)
            except web.HTTPNotFound:
                # A lower-quality fallback can itself be evicted while the
                # network resolver is running. It no longer exists to serve.
                pass
        return fail(str(exc), 502)

    response = web.StreamResponse()
    started = False

    async def on_start(info: dict) -> None:
        nonlocal started
        response.set_status(206 if info.get("content_range") else info.get("status", 200))
        response.headers["Content-Type"] = info.get("mime") or "audio/mpeg"
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Kryonyx-Cache"] = "miss"
        if info.get("length"):
            response.content_length = info["length"]
        if info.get("content_range"):
            response.headers["Content-Range"] = info["content_range"]
        await response.prepare(request)
        started = True

    async def on_chunk(chunk: bytes) -> None:
        await response.write(chunk)

    async def pump() -> None:
        # Если этот трек уже кто-то тянет в кэш (предзагрузка следующего или
        # второе окно), просто проигрываем поток, не записывая файл второй раз.
        if audiocache.downloading(track_id):
            await audiocache.tee(await http(), track_id, media,
                                 range_header=range_header, cache=False,
                                 on_start=on_start, on_chunk=on_chunk)
        else:
            async with audiocache.lock(track_id):
                await audiocache.tee(await http(), track_id, media,
                                     range_header=range_header,
                                     on_start=on_start, on_chunk=on_chunk)

    # Ссылка может быть внешне живой, но уже закрытой на стороне источника:
    # YouTube отвечает на такую 403. Раньше это уходило в браузер как ошибка,
    # а плеер получал из кэша ту же самую ссылку — и так по кругу. Теперь
    # протухшая ссылка выбрасывается из кэша, и трек пересобирается заново
    # другим клиентом плеера. Пока ни один байт не ушёл слушателю, подмена
    # для него полностью незаметна.
    for attempt in range(_STREAM_ATTEMPTS):
        try:
            await pump()
            break
        except asyncio.CancelledError:
            raise
        except (ConnectionResetError, aiohttp.ClientConnectionError) as exc:
            # Браузер закрыл соединение: пользователь переключил трек или
            # перемотал. Это обычное дело, в журнал такое сыпать не нужно.
            log.debug("[stream] %s: listener disconnected (%s)", track_id, exc)
            return response
        except audiocache.SourceError as exc:
            retriable = (exc.stale and not started
                         and attempt < _STREAM_ATTEMPTS - 1)
            if not retriable:
                log.warning("[stream] %s interrupted: %s", track_id, exc)
                if not started:
                    return fail(str(exc), 502)
                return response
            log.info("[stream] %s: link is stale (%s), asking for a new one "
                     "(attempt %d)", track_id, exc.status, attempt + 2)
            providers.invalidate_stream(source_id)
            try:
                source_id, media = await _media_for(
                    track_id, title, artist,
                    # С третьей попытки разрешаем и подмену источника целиком.
                    fallback or attempt >= 1,
                    refresh=True, attempt=attempt + 1)
            except Exception as inner:
                log.warning("[stream] %s: no new link (%s)", track_id, inner)
                return fail(str(inner), 502)
        except Exception as exc:
            log.warning("[stream] %s interrupted: %s", track_id, exc)
            if not started:
                return fail(str(exc), 502)
            return response

    if not started:
        return fail("the source refused every link for this track", 502)
    await response.write_eof()
    return response


@routes.get("/api/cache/audio")
async def api_cache_audio(request: web.Request) -> web.Response:
    return ok(await asyncio.to_thread(audiocache.stats))


@routes.put("/api/cache/audio")
async def api_cache_audio_policy(request):
    d = await _body(request)
    try: return ok(await asyncio.to_thread(audiovault.configure, d.get("mode"), d.get("limit_mb")))
    except (ValueError, AttributeError) as exc: return fail(str(exc), 400)


@routes.delete("/api/cache/audio")
async def api_cache_audio_clear(request: web.Request) -> web.Response:
    return ok({"removed": await asyncio.to_thread(audiocache.clear)})


# --------------------------------------------------------------------------- #
# текст песни
# --------------------------------------------------------------------------- #
_lyrics_cache: dict[str, dict] = {}


_LYRIC_VERSIONS = {
    'remix': r'\b(?:remix|remixed|rework|bootleg|nightcore)\b',
    'cover': r'\b(?:cover|tribute)\b',
    'live': r'\b(?:live|concert)\b',
    'acoustic': r'\bacoustic\b',
    'instrumental': r'\b(?:instrumental|karaoke)\b',
    'sped': r'\b(?:sped[ -]?up|speed[ -]?up)\b',
    'slowed': r'\b(?:slowed|slow[ -]?down)\b',
    'extended': r'\bextended\b',
}

def _lyric_versions(value: str) -> frozenset[str]:
    value = (value or '').casefold()
    return frozenset(k for k, pattern in _LYRIC_VERSIONS.items() if re.search(pattern, value))

def _lyric_normalize(value: str) -> str:
    value = unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in value if not unicodedata.combining(c)), re.UNICODE))

def _lyrics_score(record: dict, title: str, artist: str,
                  seconds: float | None, recording_mbid: str = '') -> float:
    """Reject doubtful identities first; quality and sync only break close ties.

    LRCLIB's numeric record id is not a source recording id. Compare MBIDs only
    when both sides explicitly provide that same identifier namespace.
    """
    if not isinstance(record, dict):
        return -1000.0
    want_artist = _lyric_normalize(lyrics_mod.clean_artist(artist))
    got_artist = _lyric_normalize(lyrics_mod.clean_artist(str(record.get('artistName') or '')))
    if not want_artist or not got_artist:
        return -1000.0  # Cannot confidently select a recording without an artist.
    artist_match = difflib.SequenceMatcher(None, want_artist, got_artist).ratio()
    if artist_match < .90:
        return -1000.0
    candidate_title = str(record.get('trackName') or '')
    if _lyric_versions(title) != _lyric_versions(candidate_title):
        return -1000.0
    if record.get('instrumental') and 'instrumental' not in _lyric_versions(title):
        return -1000.0
    actual_id = str(record.get('recordingMbid') or record.get('recording_mbid') or '').strip().lower()
    if recording_mbid and actual_id and actual_id != recording_mbid.lower():
        return -1000.0
    def clean_name(value):
        value = lyrics_mod._tidy(lyrics_mod._drop_brackets(value, False))
        return _lyric_normalize(lyrics_mod._FEAT.sub('', value))
    got_name = clean_name(candidate_title)
    names = [clean_name(name) for name, who in lyrics_mod.query_variants(title, artist)
             if who and _lyric_normalize(lyrics_mod.clean_artist(who)) == want_artist]
    if not got_name or not names:
        return -1000.0
    title_match = max(difflib.SequenceMatcher(None, name, got_name).ratio() for name in names)
    if title_match < .85:
        return -1000.0
    try:
        duration = float(record.get('duration') or 0)
        requested = float(seconds or 0)
        if not math.isfinite(duration) or not math.isfinite(requested):
            return -1000.0
    except (TypeError, ValueError):
        return -1000.0
    delta = abs(duration-requested) if duration > 0 and requested > 0 else None
    if delta is not None and delta > max(12, requested * .08):
        return -1000.0
    # An exact artist/title outweighs any advantage from synchronized lyrics.
    value = artist_match * 180 + title_match * 180
    if actual_id and recording_mbid and actual_id == recording_mbid.lower():
        value += 80
    if delta is not None:
        value += max(0, 15-delta)
    if record.get('hasWordSync'): value += 4
    elif record.get('lyricsfile'): value += 3
    elif record.get('syncedLyrics'): value += 2
    text = str(record.get('plainLyrics') or record.get('syncedLyrics') or '')
    if len([row for row in text.splitlines() if row.strip()]) < 3:
        value -= 10
    return value


async def _lyrics_lookup(title: str, artist: str,
                         seconds: float | None, recording_mbid: str = '') -> dict:
    """Ищет запись в LRCLIB по всем разумным написаниям названия.

    Треки приходят с YouTube и SoundCloud, где название — это заголовок
    видео: «Marino - Rip Out Your Eyes (Official Lyrics Video)». В базе
    запись называется «Rip Out Your Eyes», и по сырому заголовку не
    находилось ничего. Поэтому lyrics.query_variants() раскладывает
    заголовок на варианты, и мы спрашиваем базу по каждому, а затем
    выбираем лучшую запись по общей оценке.
    """
    session = await http()
    variants = lyrics_mod.query_variants(title, artist)
    if not variants:
        return {}

    failures: list[str] = []

    async def fetch(path: str, query: dict) -> Any:
        try:
            async with session.get(f"https://lrclib.net/api/{path}", params=query,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status != 404:
                    failures.append(f"{path} HTTP {resp.status}")
        except Exception as exc:
            failures.append(f"{path}: {exc}")
            log.debug("[lyrics] %s failed: %s", path, exc)
        return None

    jobs: list[Any] = []
    # Точный запрос — только по первым вариантам: он требует полного
    # совпадения названия, и на длинном хвосте вариантов смысла не имеет.
    for index, (name, who) in enumerate(variants[:3]):
        params = {"track_name": name, "artist_name": who}
        if seconds and index == 0:
            params["duration"] = str(int(seconds))
        jobs.append(fetch("get", params))
        if seconds and index == 0:
            # Та же запись, но без длительности: у «(extended)» и ремастеров
            # она другая, а текст тот же.
            jobs.append(fetch("get", {"track_name": name, "artist_name": who}))
    # Поиск терпимее к написанию, поэтому берём больше вариантов.
    seen: set[str] = set()
    for name, who in variants[:5]:
        query = f"{who} {name}".strip()
        if query.lower() in seen:
            continue
        seen.add(query.lower())
        jobs.append(fetch("search", {"q": query}))

    answers = await asyncio.gather(*jobs)
    records: list[dict] = []
    for answer in answers:
        if isinstance(answer, dict):
            records.append(answer)
        elif isinstance(answer, list):
            records.extend(row for row in answer[:12] if isinstance(row, dict))

    if not records:
        log.info("[lyrics] nothing found for %r — %r (tried %s variants%s)",
                 artist, title, len(variants),
                 "; network: " + failures[0] if failures else "")
        return {}

    unique: dict[str, dict] = {}
    for row in records:
        key = str(row.get("id") or f"{row.get('artistName')}|{row.get('trackName')}|{row.get('duration')}")
        unique.setdefault(key, row)
    scored = [( _lyrics_score(row, title, artist, seconds, recording_mbid), row)
              for row in unique.values()]
    scored = [item for item in scored if item[0] > -1000]
    if not scored:
        log.info("[lyrics] no sufficiently reliable identity match (%s candidates)", len(unique))
        return {}
    top = max(scored, key=lambda item: item[0])[1]
    log.info("[lyrics] %r — %r -> %r — %r (synced=%s, %s candidates)",
             artist, title, top.get("artistName"), top.get("trackName"),
             bool(top.get("syncedLyrics") or top.get("lyricsfile")), len(unique))
    return top


async def _lyrics_by_id(record_id: str) -> dict:
    """Запись LRCLIB по её номеру: так работает выбор текста вручную."""
    session = await http()
    try:
        async with session.get(f"https://lrclib.net/api/get/{record_id}",
                               timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.info("[lyrics] record %s failed: %s", record_id, exc)
    return {}


@routes.get("/api/lyrics/search")
async def api_lyrics_search(request: web.Request) -> web.Response:
    """Поиск текста по нику исполнителя и названию песни.

    Автоподбор идёт по названию трека, и у заголовков с YouTube он иногда
    промахивается. Здесь пользователь задаёт и исполнителя, и название —
    ровно так, как песня подписана в базе, — и сам выбирает запись.
    """
    artist = (request.query.get("artist") or "").strip()
    title = (request.query.get("title") or "").strip()
    free = (request.query.get("q") or "").strip()
    if not (artist or title or free):
        return fail("An artist or a title is required")

    session = await http()

    async def fetch(query: dict) -> list[dict]:
        try:
            async with session.get("https://lrclib.net/api/search", params=query,
                                   timeout=aiohttp.ClientTimeout(total=9)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
                return [row for row in data if isinstance(row, dict)] \
                    if isinstance(data, list) else []
        except Exception as exc:
            log.debug("[lyrics] search failed: %s", exc)
            return []

    jobs = []
    # Поле q терпимо к написанию, пара track_name/artist_name — точнее.
    if free or artist or title:
        jobs.append(fetch({"q": free or f"{artist} {title}".strip()}))
    if title:
        query = {"track_name": title}
        if artist:
            query["artist_name"] = artist
        jobs.append(fetch(query))
    if artist and not title:
        jobs.append(fetch({"artist_name": artist}))

    seen: set[str] = set()
    items: list[dict] = []
    for found in await asyncio.gather(*jobs):
        for row in found:
            key = str(row.get("id") or f"{row.get('artistName')}|{row.get('trackName')}")
            if key in seen:
                continue
            seen.add(key)
            text = str(row.get("syncedLyrics") or row.get("plainLyrics") or "")
            items.append({
                "id": row.get("id"),
                "title": row.get("trackName") or "",
                "artist": row.get("artistName") or "",
                "album": row.get("albumName") or "",
                "duration": row.get("duration") or None,
                "synced": bool(row.get("syncedLyrics") or row.get("lyricsfile")),
                "instrumental": bool(row.get("instrumental")),
                "lines": len([row for row in text.splitlines() if row.strip()]),
            })
    # For manual search preserve all candidates but rank identity ahead of sync.
    if artist and title:
        items.sort(key=lambda row: _lyrics_score(
            {'artistName':row['artist'], 'trackName':row['title'],
             'duration':row['duration'], 'syncedLyrics':'x' if row['synced'] else '',
             'instrumental':row['instrumental']}, title, artist, None), reverse=True)
    else:
        items.sort(key=lambda row: (bool(row["synced"]), row["lines"]), reverse=True)
    return ok({"items": items[:25], "query": {"artist": artist, "title": title}})


@routes.get("/api/lyrics")
async def api_lyrics(request: web.Request) -> web.Response:
    track_id = request.query.get("track_id", "")
    saved = await asyncio.to_thread(karaoke_jobs.load_track, track_id) if track_id else None
    if saved:
        try: return ok(lyrics_mod.karaoke_payload(saved, request.query.get("variant", "")))
        except ValueError as exc: return fail(str(exc), 400)
    if track_id:
        legacy = karaoke_jobs.binding(track_id).with_suffix(".legacy.json")
        if legacy.exists():
            try: return ok(await asyncio.to_thread(lambda: json.loads(legacy.read_text(encoding="utf-8"))))
            except (OSError, ValueError): pass
    title = (request.query.get("title") or "").strip()
    artist = (request.query.get("artist") or "").strip()
    duration = request.query.get("duration")
    # Запись, выбранная вручную в «Найти текст»: она главнее автоподбора.
    picked = (request.query.get("lrc") or "").strip()
    if not title and not picked:
        return fail("A title is required")

    seconds: float | None = None
    try:
        parsed_duration = float(duration or 0)
        if math.isfinite(parsed_duration) and 0 < parsed_duration <= 86400:
            seconds = parsed_duration
    except (TypeError, ValueError):
        pass

    # Длительность — часть ключа. Без неё ответ для «того же» названия
    # переиспользовался для другого издания трека, и текст уезжал на
    # секунды: запись отбиралась под первую услышанную длину.
    bucket = int(seconds // 5) if seconds else -1
    recording_mbid = (request.query.get("recording_mbid") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", recording_mbid):
        recording_mbid = ""
    key = f"{track_id}|{artist}|{title}|{bucket}|{picked}|{recording_mbid}".lower()
    if key in _lyrics_cache:
        # Кэшируем весь ответ: раньше из кэша терялся признак синхронности,
        # и обычный текст приезжал помеченным как караоке.
        return ok(_lyrics_cache[key])

    # lyrics.ovh supplies no recording metadata, so it must never bypass the
    # automatic identity filter. It remains available as an explicit manual pick.
    ovh_query = None
    if picked.startswith('ovh:'):
        try:
            candidate = json.loads(picked[4:])
            if (isinstance(candidate, list) and len(candidate) == 2
                and all(isinstance(x, str) and 0 < len(x) <= 300 for x in candidate)):
                ovh_query = candidate
        except (ValueError, TypeError):
            pass
    record = (await _lyrics_by_id(picked) if picked and not picked.startswith('ovh:')
              else await _lyrics_lookup(title, artist, seconds, recording_mbid) if not picked
              else {})
    payload = lyrics_mod.build(
        (record or {}).get("syncedLyrics") or "",
        (record or {}).get("plainLyrics") or "",
        seconds,
        (record or {}).get("lyricsfile") or "",
    )
    payload["instrumental"] = bool((record or {}).get("instrumental"))
    payload["source"] = "lrclib" if payload["lines"] else ""
    payload["title"] = str((record or {}).get("trackName") or "")
    payload["artist"] = str((record or {}).get("artistName") or "")
    # Длина записи, с которой сняты метки: по ней плеер растягивает шкалу
    # под свой файл, если издание отличается на проценты.
    try:
        payload["duration"] = float((record or {}).get("duration") or 0) or None
    except (TypeError, ValueError):
        payload["duration"] = None

    # Запись заметно длиннее или короче нашего файла — это другая заливка
    # (вступление, склейка, живая версия). Метки у неё верные, но стоят не
    # там: плеер в таком случае ищет сдвиг по звуку шире обычного.
    payload["approx"] = bool(
        seconds and payload.get("duration")
        and abs(float(payload["duration"]) - seconds) > 12)

    if not payload["lines"] and ovh_query:
        # Only a manual, explicitly labelled unverified selection.
        rows = await extras.plain_lyrics(*ovh_query)
        # Запасной источник тоже подписывает себя внутри текста.
        rows = lyrics_mod.clean(rows)
        payload = {
            "lines": [{"time": None, "end": None, "words": [], "gap": 0.0,
                       **row} for row in rows],
            "synced": False, "words": False, "instrumental": False,
            "source": "lyrics.ovh" if rows else "", "title": "", "artist": "",
            "duration": None, "approx": False, "identity_verified": False,
        }

    if payload["lines"]:
        _lyrics_cache[key] = payload
        while len(_lyrics_cache) > 256:
            _lyrics_cache.pop(next(iter(_lyrics_cache)))
    return ok(payload)


# --------------------------------------------------------------------------- #
# плейлисты, лайки, история
# --------------------------------------------------------------------------- #
@routes.get("/api/playlists")
async def api_playlists(request: web.Request) -> web.Response:
    return ok({"items": await asyncio.to_thread(storage.list_playlists)})


@routes.post("/api/playlists")
async def api_playlist_create(request: web.Request) -> web.Response:
    data = await _body(request)
    name = str(data.get("name") or "").strip()
    if not name:
        return fail("A name is required")
    tracks = data.get("tracks", [])
    if not _valid_track_batch(tracks):
        return fail("A track list is required", 400)
    playlist = await asyncio.to_thread(storage.create_playlist, name, tracks)
    return ok(playlist)


def _valid_track_batch(tracks: Any) -> bool:
    return (isinstance(tracks, list)
            and all(isinstance(t, dict) and isinstance(t.get("id"), str)
                    and bool(t["id"].strip()) for t in tracks))


@routes.patch("/api/playlists/{pid}")
async def api_playlist_rename(request: web.Request) -> web.Response:
    data = await _body(request)
    pid = int(request.match_info["pid"])
    if data.get("name"):
        await asyncio.to_thread(storage.rename_playlist, pid, data["name"])
    if isinstance(data.get("order"), list):
        await asyncio.to_thread(storage.reorder_playlist, pid, data["order"])
    return ok({"ok": True})


@routes.delete("/api/playlists/{pid}")
async def api_playlist_delete(request: web.Request) -> web.Response:
    removed = await asyncio.to_thread(storage.delete_playlist, int(request.match_info["pid"]))
    return ok({"ok": removed})


@routes.get("/api/playlists/{pid}/tracks")
async def api_playlist_tracks(request: web.Request) -> web.Response:
    tracks = await asyncio.to_thread(storage.playlist_tracks, int(request.match_info["pid"]))
    if tracks is None:
        return fail("Playlist not found", 404)
    await extras.fill_thumbnails(tracks)
    return ok({"items": tracks})


@routes.post("/api/playlists/{pid}/tracks")
async def api_playlist_add(request: web.Request) -> web.Response:
    data = await _body(request)
    pid = int(request.match_info["pid"])
    if "tracks" in data:
        tracks = data["tracks"]
        if not _valid_track_batch(tracks):
            return fail("A track list is required", 400)
        added = await asyncio.to_thread(storage.add_many_to_playlist, pid, tracks)
        if added is None:
            return fail("Playlist not found", 404)
        return ok({"ok": True, "added": added})
    track = data.get("track") if isinstance(data.get("track"), dict) else data
    if not track.get("id"):
        return fail("A track is required")
    added = await asyncio.to_thread(storage.add_to_playlist, pid, track)
    return ok({"ok": added})


@routes.delete("/api/playlists/{pid}/tracks/{row_id}")
async def api_playlist_remove(request: web.Request) -> web.Response:
    removed = await asyncio.to_thread(
        storage.remove_from_playlist,
        int(request.match_info["pid"]), int(request.match_info["row_id"]),
    )
    return ok({"ok": removed})


# Explicit audio downloads are disabled. Automatic playback cache is separate.
@routes.get("/api/playlists/{pid}/offline")
@routes.post("/api/playlists/{pid}/offline")
async def api_playlist_offline(request: web.Request) -> web.Response:
    return fail("Audio track downloads are disabled", 403)


@routes.get("/api/playlists/{pid}/share")
async def api_playlist_share(request: web.Request) -> web.Response:
    """Код плейлиста: короткая строка, которую можно кинуть другу в чат."""
    pid = int(request.match_info["pid"])
    tracks = await asyncio.to_thread(storage.playlist_tracks, pid)
    if tracks is None:
        return fail("Playlist not found", 404)
    names = {p["id"]: p["name"] for p in await asyncio.to_thread(storage.list_playlists)}
    name = names.get(pid, "Playlist")
    return ok({"name": name, "count": len(tracks),
               "code": extras.pack_playlist(name, tracks)})


@routes.post("/api/playlists/share-list")
async def api_playlist_share_list(request: web.Request) -> web.Response:
    """Код для списка, которого нет в базе: лайки, микс, история."""
    data = await _body(request)
    tracks = data.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        return fail("A track list is required")
    name = (data.get("name") or "Playlist").strip() or "Playlist"
    clean = [t for t in tracks if isinstance(t, dict) and t.get("id")]
    return ok({"name": name, "count": len(clean),
               "code": extras.pack_playlist(name, clean)})


@routes.post("/api/playlists/decode")
async def api_playlist_decode(request: web.Request) -> web.Response:
    """Разобрать код, ничего не сохраняя.

    Нужно для окна выбора: пользователь сначала смотрит, какие треки пришли
    и куда их положить, и только потом подтверждает добавление.
    """
    data = await _body(request)
    code = str(data.get("code") or "").strip()
    if not code:
        return fail("A share code is required")
    try:
        name, tracks = extras.unpack_playlist(code)
    except Exception as exc:
        return fail(str(exc) or "This share code is not valid")
    if not tracks:
        return fail("The share code has no tracks")
    return ok({"name": name, "tracks": tracks, "count": len(tracks)})


@routes.post("/api/playlists/import")
async def api_playlist_import(request: web.Request) -> web.Response:
    """Импорт плейлиста: по коду целиком или выбранными треками.

    playlist_id — добавить в существующий плейлист; без него создаём новый.
    tracks — уже отобранные пользователем треки (галочки в окне выбора);
    без них берём всё, что лежит в коде.
    """
    data = await _body(request)
    code = str(data.get("code") or "").strip()
    chosen = data.get("tracks")
    name = ""
    if isinstance(chosen, list) and chosen:
        tracks = [t for t in chosen if isinstance(t, dict) and t.get("id")]
    elif code:
        try:
            name, tracks = extras.unpack_playlist(code)
        except Exception as exc:
            return fail(str(exc) or "This share code is not valid")
    else:
        return fail("A share code is required")
    if not tracks:
        return fail("The share code has no tracks")

    target = data.get("playlist_id")
    if target:
        known = await asyncio.to_thread(storage.list_playlists)
        playlist = next((p for p in known if p["id"] == int(target)), None)
        if not playlist:
            return fail("Playlist not found", 404)
    else:
        wanted = (data.get("name") or "").strip() or name or "Playlist"
        playlist = await asyncio.to_thread(storage.create_playlist, wanted)
    added = 0
    for track in tracks:
        if isinstance(track, dict) and await asyncio.to_thread(
                storage.add_to_playlist, playlist["id"], track):
            added += 1
    return ok({**playlist, "added": added, "total": len(tracks)})


@routes.get("/api/playlists/{pid}/export.m3u")
async def api_playlist_export(request: web.Request) -> web.Response:
    if not plugins.enabled("m3u"):
        return fail("The M3U Export plugin is turned off", 409)
    pid = int(request.match_info["pid"])
    tracks = await asyncio.to_thread(storage.playlist_tracks, pid)
    if tracks is None:
        return fail("Playlist not found", 404)
    names = {p["id"]: p["name"] for p in await asyncio.to_thread(storage.list_playlists)}
    base = str(request.url.origin())
    body = extras.playlist_m3u(names.get(pid, "Playlist"), tracks, base)
    return web.Response(
        text=body, content_type="audio/x-mpegurl", charset="utf-8",
        headers={"Content-Disposition": f'attachment; filename="playlist-{pid}.m3u8"'},
    )


@routes.get("/api/likes")
async def api_likes(request: web.Request) -> web.Response:
    items, ids = await asyncio.gather(
        asyncio.to_thread(storage.list_likes),
        asyncio.to_thread(storage.liked_ids),
    )
    await extras.fill_thumbnails(items)
    return ok({"items": items, "ids": ids})


@routes.post("/api/likes")
async def api_like_toggle(request: web.Request) -> web.Response:
    data = await _body(request)
    track = data.get("track") if isinstance(data.get("track"), dict) else data
    if not track.get("id"):
        return fail("A track is required")
    liked = await asyncio.to_thread(storage.toggle_like, track)
    recommend.invalidate()
    return ok({"liked": liked})


@routes.post('/api/track-stats')
async def api_track_stats(request):
    from . import trackstats
    _karaoke_origin(request)
    data=await _body(request);ids=data.get('ids')
    if not isinstance(ids,list) or len(ids)>24 or not all(isinstance(i,str) and len(i)<512 for i in ids):
        return fail('Expected up to 24 track ids',400)
    return ok({'items':await trackstats.batch(ids)})


@routes.post("/api/listen-counts")
async def api_listen_counts(request: web.Request) -> web.Response:
    data = await _body(request)
    ids = data.get("ids")
    if not isinstance(ids, list) or len(ids) > 500 or not all(isinstance(i, str) for i in ids):
        return fail("Expected up to 500 track ids", 400)
    counts = await asyncio.to_thread(storage.listen_counts, ids)
    return ok({"counts": counts})


@routes.get("/api/history")
async def api_history(request: web.Request) -> web.Response:
    items = await asyncio.to_thread(storage.history, _int(request, "limit", 100, 10, 300))
    await extras.fill_thumbnails(items)
    return ok({"items": items})


@routes.delete("/api/history")
async def api_history_clear(request: web.Request) -> web.Response:
    await asyncio.to_thread(storage.clear_history)
    recommend.invalidate()
    return ok({"ok": True})


@routes.post("/api/play")
async def api_play(request: web.Request) -> web.Response:
    """Телеметрия прослушивания — топливо для рекомендаций."""
    data = await _body(request)
    track = data.get("track")
    if not isinstance(track, dict) or not track.get("id"):
        return fail("A track is required")
    seconds = float(data.get("seconds") or 0)
    completed = bool(data.get("completed"))
    await asyncio.to_thread(
        storage.log_play, track, seconds, completed, bool(data.get("skipped")),
        str(data.get("session_id") or "")[:100] or None,
    )
    # Правило скробблинга как у Last.fm: половина трека или 4 минуты.
    if completed or seconds >= min(240, (track.get("duration") or 9999) / 2):
        _background(request.app, _scrobble_quiet(track, seconds))
    return ok({"ok": True})


async def _scrobble_quiet(track: dict, seconds: float) -> None:
    try:
        sent = await extras.scrobble(track, seconds)
        if sent:
            log.info("[scrobble] sent: %s", ", ".join(sent))
    except Exception as exc:
        log.debug("[scrobble] error: %s", exc)


# --------------------------------------------------------------------------- #
# настройки
# --------------------------------------------------------------------------- #
@routes.get("/api/settings")
async def api_settings(request: web.Request) -> web.Response:
    return ok(await asyncio.to_thread(storage.get_settings))


@routes.put("/api/settings")
async def api_settings_save(request: web.Request) -> web.Response:
    data = await _body(request)
    old_settings=storage.get_settings()
    previous=old_settings.get('audioQuality','best')
    result=await asyncio.to_thread(storage.save_settings,data)
    if any(old_settings.get(k)!=result.get(k) for k in ('recommend50','sources','search26Hidden','lang','region70')):recommend.invalidate()
    if result.get('audioQuality','best')!=previous:
        providers.clear_caches(); streaming._candidates.clear(); _metadata_media_cache.clear()
    return ok(result)


@routes.post("/api/settings/beacon")
async def api_settings_beacon(request: web.Request) -> web.Response:
    """navigator.sendBeacon умеет только POST — им закрываемое окно
    досылает последние настройки."""
    data = await _body(request)
    if data:
        await asyncio.to_thread(storage.save_settings, data)
    return ok({"ok": True})


@routes.post("/api/state/beacon")
async def api_state_beacon(request: web.Request) -> web.Response:
    data = await _body(request)
    key = str(data.get("key") or "player")[:80]
    if data.get("value") is not None:
        await asyncio.to_thread(storage.set_state, key, data.get("value"))
    return ok({"ok": True})


@routes.get("/api/state")
async def api_state(request: web.Request) -> web.Response:
    """Состояние плеера: очередь, текущий трек и позиция. Живёт в SQLite,
    поэтому переживает перезапуск и очистку хранилища WebView."""
    key = request.query.get("key") or "player"
    return ok({"key": key, "value": await asyncio.to_thread(storage.get_state, key)})


@routes.put("/api/state")
async def api_state_save(request: web.Request) -> web.Response:
    data = await _body(request)
    key = str(data.get("key") or "player")[:80]
    await asyncio.to_thread(storage.set_state, key, data.get("value"))
    return ok({"ok": True})


@routes.delete("/api/state")
async def api_state_clear(request: web.Request) -> web.Response:
    await asyncio.to_thread(storage.clear_state, request.query.get("key") or None)
    return ok({"ok": True})


@routes.delete("/api/settings")
async def api_settings_reset(request: web.Request) -> web.Response:
    await asyncio.to_thread(storage.reset_settings)
    return ok({"ok": True})


@routes.post("/api/cache/clear")
async def api_cache_clear(request: web.Request) -> web.Response:
    providers.clear_caches()
    recommend.invalidate()
    return ok({"ok": True})


@routes.get("/api/searches")
async def api_searches(request: web.Request) -> web.Response:
    return ok({"items": await asyncio.to_thread(storage.recent_searches, 12)})


@routes.delete("/api/searches")
async def api_searches_clear(request: web.Request) -> web.Response:
    """Без q — чистим историю поиска целиком, с q — только этот запрос."""
    query = (request.query.get("q") or "").strip()
    if query:
        await asyncio.to_thread(storage.forget_search, query)
        return ok({"ok": True, "removed": query})
    await asyncio.to_thread(storage.clear_searches)
    return ok({"ok": True})


# --------------------------------------------------------------------------- #
# маркер удачного запуска
# --------------------------------------------------------------------------- #
@routes.post("/api/boot/ok")
async def api_boot_ok(request: web.Request) -> web.Response:
    """Страница доложила, что интерфейс собрался.

    Пока маркер лежит в папке данных, следующий запуск считает прошлый
    неудачным и поднимается в облегчённом режиме. См. main._boot_flag().
    """
    from . import main as app_main
    await asyncio.to_thread(app_main._boot_clear)
    return ok({"ok": True})


# --------------------------------------------------------------------------- #
# аватарка приложения
# --------------------------------------------------------------------------- #
@routes.get("/api/avatars")
async def api_avatars(request: web.Request) -> web.Response:
    return ok(await asyncio.to_thread(avatars.state))


@routes.post("/api/avatars/custom")
async def api_custom_avatar_create(request):
    limit = avatars.custom_avatars.MAX_BYTES
    if request.content_length and request.content_length > limit:
        return fail("Avatar upload is too large", 413)
    content = bytearray()
    async for chunk in request.content.iter_chunked(65536):
        content.extend(chunk)
        if len(content) > limit:
            return fail("Avatar upload is too large", 413)
    try:
        item = await asyncio.to_thread(avatars.custom_avatars.create, avatars.data_dir(), bytes(content), request.query.get("name", ""))
        return ok({"item": item})
    except ValueError as exc:
        return fail(str(exc), 400)
    except OSError:
        return fail("Avatar storage is unavailable", 500)


@routes.get("/api/avatars/custom/{aid}/{kind}")
async def api_custom_avatar_asset(request):
    try:
        path = avatars.custom_avatars.asset(avatars.data_dir(), request.match_info["aid"], request.match_info["kind"])
        return web.FileResponse(path, headers={"X-Content-Type-Options":"nosniff", "Cache-Control":"private, max-age=86400"})
    except (ValueError, OSError):
        return fail("Custom avatar not found", 404)


@routes.delete("/api/avatars/custom/{aid}")
async def api_custom_avatar_delete(request):
    aid = request.match_info["aid"]
    def remove():
        with avatars.custom_avatars.LOCK:
            avatars.custom_avatars.directory(avatars.data_dir(), aid)
            if avatars.current() == aid:
                avatars.choose(avatars.DEFAULT_AVATAR)
            avatars.custom_avatars.remove(avatars.data_dir(), aid)
            return avatars.state()
    try:
        data = await asyncio.to_thread(remove)
        await asyncio.to_thread(avatars.set_window_icon, "Kryo")
        return ok(data)
    except ValueError as exc:
        return fail(str(exc), 404)
    except OSError:
        return fail("Avatar storage is unavailable", 500)


@routes.get("/api/avatarshop/download/{aid}")
async def api_avatar_download(request):
    try:
        fmt=request.query.get("format","png");p=avatarshop.asset(request.match_info["aid"],fmt)
        return web.FileResponse(p,headers={"Content-Disposition":f'attachment; filename="{p.name}"',"X-Content-Type-Options":"nosniff"})
    except ValueError as exc:return fail(str(exc),404)

@routes.get("/api/avatarshop/pack")
async def api_avatar_pack(request):
    try:
        collection=request.query.get("collection","all")
        p=await asyncio.to_thread(avatarshop.pack,collection)
        return web.FileResponse(p,headers={"Content-Disposition":f'attachment; filename="Kryo-Avatars-{collection}.zip"'})
    except ValueError as exc:return fail(str(exc),400)


@routes.post("/api/avatar")
async def api_avatar_set(request: web.Request) -> web.Response:
    data = await _body(request)
    aid = str((data or {}).get("id") or "").strip()
    try:
        result = await asyncio.to_thread(avatars.choose, aid)
    except ValueError as exc:
        return fail(str(exc), 400)
    # Иконку открытого окна меняем сразу: ждать перезапуска незачем.
    # avatars.choose applies the live window/tray before waiting for shell links.
    return ok(result)


# --------------------------------------------------------------------------- #
# статика
# --------------------------------------------------------------------------- #
@routes.get("/icon.png")
async def app_icon(request: web.Request) -> web.StreamResponse:
    """Иконка интерфейса — всегда выбранная аватарка."""
    return web.FileResponse(await asyncio.to_thread(avatars.web_icon),
                            headers={"Cache-Control": "no-cache"})


@routes.get("/")
async def index(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(f"{web_dir()}/index.html", headers={"Cache-Control": "no-cache"})


# v70: ошибки интерфейса попадают в журнал приложения (Настройки → Журнал),
# чтобы «что-то сломалось» можно было разобрать без консоли разработчика.
# Только текст ошибки и место в коде — никаких данных пользователя.
_client_errors70: list[float] = []


def _clip70(value: Any, size: int) -> str:
    return " ".join(str(value or "").split())[:size]


@routes.post("/api/client-error")
async def api_client_error(request: web.Request) -> web.Response:
    data = await _body(request)
    now = time.monotonic()
    _client_errors70[:] = [at for at in _client_errors70 if now - at < 60.0]
    if len(_client_errors70) >= 20:
        return ok({"logged": False})
    _client_errors70.append(now)
    message = _clip70(data.get("message"), 300)
    if not message:
        return ok({"logged": False})
    log.warning("[ui] %s | %s | %s", message, _clip70(data.get("source"), 160),
                _clip70(data.get("stack"), 700))
    return ok({"logged": True})


# v70: интерфейс обновляется вместе с приложением. Без Cache-Control WebView2
# мог по эвристике держать старые js/css после обновления — новая разметка
# встречалась со старыми скриптами. no-cache = всегда переспросить (ответ 304
# по ETag/Last-Modified почти ничего не стоит на localhost).
async def _ui_revalidate70(request: web.Request, response: web.StreamResponse) -> None:
    path = request.path
    if (path.endswith((".js", ".css", ".html")) and "Cache-Control" not in response.headers
            and not path.startswith("/api/")):
        response.headers["Cache-Control"] = "no-cache"


_LOCAL_PEERS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
_LOCAL_NAMES = {"127.0.0.1", "localhost", "[::1]", "::1"}


@web.middleware
async def local_only(request: web.Request, handler):
    """Пускаем только тот компьютер, на котором плеер запущен.

    Два рубежа. Первый — адрес клиента: всё, что пришло не с loopback,
    отбрасывается, даже если кто-то пробросил порт наружу. Второй — заголовок
    Host: он закрывает DNS rebinding, когда сторонний домен указывает на
    127.0.0.1 и чужая страница пытается дёргать наш API из браузера.
    """
    peer = (request.remote or "").strip()
    if peer not in _LOCAL_PEERS:
        return web.json_response(
            {"error": "Kryo отвечает только локально"}, status=403)
    raw = (request.headers.get("Host") or "").strip().lower()
    host = raw.split("]")[0] + "]" if raw.startswith("[") else raw.rsplit(":", 1)[0]
    if host and host not in _LOCAL_NAMES:
        return web.json_response(
            {"error": f"неожидаемый Host: {host}"}, status=403)
    return await handler(request)


async def _migrate_audio_cache(app):
    await asyncio.to_thread(audiovault.migrate_legacy)

def build_app() -> web.Application:
    app = web.Application(client_max_size=9 * 1024 * 1024,
                          middlewares=[local_only])
    app["background_tasks"] = set()
    app["translation_jobs"] = {}
    app["translation_cancellations"] = {}
    app["karaoke_jobs"] = karaoke_jobs.Jobs()
    app["clip_streams"] = None
    from .ai_jobs import AIJobs as AIJobs72
    app["ai_jobs72"] = AIJobs72()  # created up front: a started app must not gain new keys
    from .audio_share import Jobs as ShareJobs64
    app["audio_share64"] = ShareJobs64()
    async def _share_start64(app): await app["audio_share64"].start()
    app.on_startup.append(_share_start64)
    app.add_routes(routes)
    app.router.add_static("/", web_dir(), show_index=False, follow_symlinks=False)
    app.on_response_prepare.append(_ui_revalidate70)

    async def _cleanup(_app: web.Application) -> None:
        tasks = set(_prefetch_tasks30) | set(_app["background_tasks"]) | set(_app["translation_jobs"].values())
        if _ytdlp_warm_task and not _ytdlp_warm_task.done():
            tasks.add(_ytdlp_warm_task)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await clipcache.close_jobs()
        await _app["karaoke_jobs"].close()
        if _app.get("ai_jobs72") is not None:
            await _app["ai_jobs72"].close()
        await _app["audio_share64"].close()
        if _app.get("clip_streams"):
            await _app["clip_streams"].close()
        await ytdlp_bin.stop_auto()
        await integrations.stop_keeper()
        if _http and not _http.closed:
            await _http.close()
        await library.close()

    app.on_cleanup.append(_cleanup)
    app.on_startup.append(_migrate_audio_cache)
    return app


@routes.post("/api/youtube/update")
async def api_youtube_update(request: web.Request) -> web.Response:
    """Ручная проверка обновления (кнопка в настройках).

    Нужна только тем, кто хочет обновиться немедленно: обычно бинарник ставит
    и обновляет фоновая задача ytdlp_bin.start_auto().
    """
    good = await ytdlp_bin.ensure(await http(), force=True)
    providers.clear_caches()
    return ok({"ok": good, **ytdlp_bin.status(),
               "version": await ytdlp_bin.version()})


@routes.get("/api/youtube/status")
async def api_youtube_status(request: web.Request) -> web.Response:
    return ok({**ytdlp_bin.status(), "version": await ytdlp_bin.version(),
               "cookies": ytcookies.state()})


# --------------------------------------------------------------------------- #
# cookies YouTube
# --------------------------------------------------------------------------- #
@routes.get("/api/youtube/cookies")
async def api_yt_cookies(request: web.Request) -> web.Response:
    return ok(ytcookies.state())


@routes.put("/api/youtube/cookies")
async def api_yt_cookies_save(request: web.Request) -> web.Response:
    data = await _body(request)
    raw = str(data.get("cookies") or "")
    try:
        state = await asyncio.to_thread(ytcookies.save, raw)
    except ValueError as exc:
        return fail(str(exc), 400)
    except Exception as exc:
        return fail(str(exc), 500)
    providers.clear_caches()
    streaming.forget()
    return ok(state)


@routes.post("/api/youtube/cookies/check")
async def api_yt_cookies_check(request: web.Request) -> web.Response:
    """Проверка вставленного текста без записи: те ли это куки."""
    data = await _body(request)
    return ok(await asyncio.to_thread(ytcookies.analyze, str(data.get("cookies") or "")))


_OPEN_HOSTS = ("chromewebstore.google.com", "addons.mozilla.org", "microsoftedge.microsoft.com",
               "addons.opera.com", "www.youtube.com", "youtube.com")


@routes.post("/api/open-url")
async def api_open_url(request: web.Request) -> web.Response:
    """Открывает страницу в обычном браузере (только из белого списка)."""
    from urllib.parse import urlparse, unquote
    data = await _body(request)
    url = str(data.get("url") or "")
    parts = urlparse(url)
    if parts.scheme != "https" or parts.hostname not in _OPEN_HOSTS:
        return fail("this address cannot be opened from here", 400)
    import webbrowser
    await asyncio.to_thread(webbrowser.open, url)
    return ok({"opened": True})


@routes.delete("/api/youtube/cookies")
async def api_yt_cookies_clear(request: web.Request) -> web.Response:
    state = await asyncio.to_thread(ytcookies.clear)
    await _pause_clips_without_cookies(request)
    providers.clear_caches()
    streaming.forget()
    return ok(state)


@routes.post("/api/youtube/cookies/browser")
async def api_yt_cookies_browser(request: web.Request) -> web.Response:
    data = await _body(request)
    try:
        await asyncio.to_thread(ytcookies.set_browser, str(data.get("browser") or ""))
    except ValueError as exc:
        return fail(str(exc), 400)
    providers.clear_caches()
    await _pause_clips_without_cookies(request)
    return ok(ytcookies.state())


@routes.post("/api/youtube/cookies/test")
async def api_yt_cookies_test(request: web.Request) -> web.Response:
    """Проверка боем: просим у YouTube ссылку на известный ролик.

    Это единственный честный способ сказать «cookies работают»: сама
    бот-проверка появляется только в момент получения потока.
    """
    if not ytdlp_bin.ready():
        return fail("yt-dlp is still being installed, try again in a minute", 409)
    try:
        info = await ytdlp_bin.stream("dQw4w9WgXcQ")
    except Exception as exc:
        return fail(str(exc), 502)
    return ok({"ok": bool(info.get("url")), **ytcookies.state()})


# --------------------------------------------------------------------------- #
# прокси / VPN
# --------------------------------------------------------------------------- #
@routes.get("/api/network/proxy")
async def api_proxy_get(request: web.Request) -> web.Response:
    return ok(netproxy.state())


@routes.put("/api/network/proxy")
async def api_proxy_put(request: web.Request) -> web.Response:
    data = await _body(request)
    try:
        state = netproxy.configure(str(data.get("mode") or "off"),
                                   str(data.get("url") or ""))
    except ValueError as exc:
        return fail(str(exc), 400)
    ytmusic.reset()
    providers.clear_caches()
    streaming.forget()
    _video_link_cache.clear()
    _video_link_fail.clear()
    _video_miss_cache.clear()
    return ok(state)


@routes.post("/api/network/proxy/test")
async def api_proxy_test(request: web.Request) -> web.Response:
    """Проверка боем: ответ YouTube через выбранный путь и внешний адрес."""
    try:
        return ok({**await netproxy.probe(), **netproxy.state()})
    except Exception as exc:
        return fail(str(exc) or exc.__class__.__name__, 502)


async def start(host: str = "127.0.0.1", port: int = 8765) -> tuple[web.AppRunner, int]:
    storage.init()
    asyncio.get_running_loop().run_in_executor(None, clipcache.prune)
    logs.install()
    plugins.state(refresh=True)
    # Свои плагины и свои библиотеки: папки, sys.path, импорт, запись в каталог.
    await asyncio.to_thread(extplugins.init)
    library.set_jamendo_client(plugins.config("jamendo").get("client_id"))
    # Бинарник yt-dlp подтягивается в фоне: окно открывается сразу, а дальше
    # задача сама раз в час проверяет обновление и переживает отсутствие сети.
    ytdlp_bin.start_auto(http)
    # Discord мог быть запущен позже плеера — фоновая задача это переживает.
    integrations.start_keeper()
    runner = web.AppRunner(build_app(), access_log=None)
    await runner.setup()
    # Если порт занят (второй запуск), берём следующий свободный.
    last_error: Exception | None = None
    for candidate in range(port, port + 12):
        try:
            site = web.TCPSite(runner, host, candidate)
            await site.start()
            log.info("[server] http://%s:%d", host, candidate)
            return runner, candidate
        except OSError as exc:
            last_error = exc
    raise RuntimeError(f"could not bind port {port}: {last_error}")


# Optional local karaoke processing; the existing server and local-only guards remain.
def _karaoke_origin(request):
    origin = request.headers.get('Origin')
    if origin and origin != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden(text='Cross-origin processing is not permitted')

@routes.get('/api/karaoke/hardware')
async def karaoke_hardware(request):
    return ok(await request.app['karaoke_jobs'].hardware())

@routes.post('/api/karaoke/generate')
async def karaoke_generate(request):
    _karaoke_origin(request)
    owned = False
    audio_path = None
    vault_token = None
    try:
        if request.content_type.startswith('multipart/'):
            reader = await request.multipart()
            values = {}
            while True:
                part = await reader.next()
                if part is None: break
                if part.name == 'audio':
                    if audio_path: raise ValueError('Only one audio file is accepted')
                    ext = os.path.splitext(part.filename or '')[1].lower()
                    if ext not in ('.mp3','.wav','.flac','.m4a','.ogg','.opus','.mp4','.webm','.aac'):
                        raise ValueError('Unsupported audio extension')
                    import uuid
                    folder = karaoke_jobs.folder() / 'uploads'; folder.mkdir(exist_ok=True)
                    audio_path = str(folder / (uuid.uuid4().hex + ext)); owned = True
                    size = 0
                    with open(audio_path,'wb') as fh:
                        while chunk := await part.read_chunk(256*1024):
                            size += len(chunk)
                            if size > karaoke_jobs.MAX_AUDIO: raise ValueError('Audio exceeds 256 MiB')
                            await audiovault.run_blocking_owned(fh.write,chunk)
                    if not size: raise ValueError('Audio is empty')
                else:
                    body = bytearray()
                    while chunk := await part.read_chunk():
                        body.extend(chunk)
                        if len(body) > karaoke_jobs.MAX_TEXT: raise ValueError('Lyric field exceeds 2 MiB')
                    values[part.name] = body.decode('utf-8-sig')
        else:
            values = await _body(request) or {}
        if not isinstance(values,dict): raise ValueError('Expected processing options object')
        track_id = str(values.get('track_id') or '')
        if len(track_id) > 2048: raise ValueError('Track id is too long')
        if not audio_path:
            audio_path = await asyncio.to_thread(audiocache.find,track_id)
            if not audio_path: raise ValueError('Choose an audio file or finish caching the current track first')
            if audio_path.startswith("vault:"):
                vault_token = audio_path
                audio_path = await audiovault.run_blocking_owned(
                    audiovault.materialize, audio_path,
                    _cancel_cleanup=lambda path: os.remove(path) if path else None)
                owned = True
        reference = str(values.get('reference') or '')
        if len(reference.encode('utf-8')) > karaoke_jobs.MAX_TEXT: raise ValueError('Reference lyrics exceed 2 MiB')
        if reference:
            parsed = lyrics_mod.parse_subtitle(reference, str(values.get('reference_name') or ''))
            reference = '\n'.join(r['text'] for r in parsed['lines'])
            if not reference.strip(): raise ValueError('Reference lyrics are empty')
        options = {'audio':audio_path,'_vault_audio':bool(vault_token),'reference':reference,'track_id':track_id,
                   'model':values.get('model','small'),'language':values.get('language','auto'),
                   'device':values.get('device','auto'),'engine':values.get('engine','auto'),
                   'separate':str(values.get('separate','false')).lower() in ('true','1'),
                   'force':str(values.get('force','false')).lower() in ('true','1'),
                   'auto_bind':str(values.get('auto_bind','false')).lower() in ('true','1'),
                   'refine':str(values.get('refine','false')).lower() in ('true','1')}
        if options['model'] not in karaoke_jobs.MODELS or options['language'] not in karaoke_jobs.LANGUAGES: raise ValueError('Unsupported model or language')
        result = request.app['karaoke_jobs'].submit(options,owned)
        owned = False  # Ownership of a submitted input belongs to the job.
        return ok(result)
    except (ValueError,UnicodeError,OSError) as exc:
        return fail(str(exc),400)
    finally:
        if owned and audio_path:
            try:
                await audiovault.run_blocking_owned(os.remove,audio_path)
            except FileNotFoundError:
                pass

@routes.get('/api/karaoke/jobs/{jid}')
async def karaoke_job(request):
    value = request.app['karaoke_jobs'].status(request.match_info['jid'])
    return ok(value) if value else fail('Job not found',404)

@routes.delete('/api/karaoke/jobs/{jid}')
async def karaoke_job_cancel(request):
    _karaoke_origin(request)
    value = await request.app['karaoke_jobs'].cancel(request.match_info['jid'])
    return ok(value) if value else fail('Job not found',404)

@routes.get('/api/karaoke/jobs/{jid}/result')
async def karaoke_job_result(request):
    item = request.app['karaoke_jobs'].items.get(request.match_info['jid'])
    if not item or item['stage'] != 'done' or not item.get('result'): return fail('Result is not ready',404)
    return web.FileResponse(item['result'],headers={'Content-Disposition':'attachment; filename="track.karaoke.json"'})

@routes.get('/api/karaoke/document')
async def karaoke_get_document(request):
    doc = await asyncio.to_thread(karaoke_jobs.load_track,request.query.get('track_id',''))
    return ok(doc) if doc else fail('No saved Karaoke JSON',404)

@routes.put('/api/karaoke/document')
async def karaoke_put_document(request):
    _karaoke_origin(request)
    try:
        data = await _body(request) or {}
        if not data.get('track_id') or len(str(data['track_id']))>2048: raise ValueError('Track id is required')
        if data.get('source') is not None:
            if len(str(data['source']).encode('utf-8')) > karaoke_jobs.MAX_TEXT: raise ValueError('Lyric file exceeds 2 MiB')
            payload = lyrics_mod.parse_subtitle(str(data['source']),str(data.get('filename','')))
            if not payload.get('document'):
                # LRC/plain imports are stored independently; legacy renderer adapter below.
                await asyncio.to_thread(karaoke_jobs.atomic_json, karaoke_jobs.binding(str(data.get('track_id',''))).with_suffix('.legacy.json'),payload)
                return ok(payload)
            doc = payload['document']
        else: doc = data.get('document')
        await asyncio.to_thread(karaoke_jobs.save_track,str(data.get('track_id','')),doc)
        return ok(lyrics_mod.karaoke_payload(doc))
    except (ValueError,TypeError) as exc: return fail(str(exc),400)

@routes.delete('/api/karaoke/document')
async def karaoke_delete_document(request):
    _karaoke_origin(request)
    track_id = request.query.get('track_id','')
    await asyncio.to_thread(karaoke_jobs.binding(track_id).unlink,missing_ok=True)
    await asyncio.to_thread(karaoke_jobs.binding(track_id).with_suffix('.legacy.json').unlink,missing_ok=True)
    return ok({'ok':True})


# Clip Studio: private source URLs stay on the server; native A/V read the cache.
async def _clip_studio_manager(request):
    manager=request.app.get('clip_streams')
    if manager is None:
        async def identify(track_id,title,artist):
            if track_id.startswith('ytvideo:'):
                vid=track_id[8:]
                if not re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):raise ValueError('Invalid YouTube video ID')
                return vid
            return await _video_id(track_id,title,artist)
        async def resolve(video_id,quality,refresh):
            if quality<=_PROGRESSIVE_MAX:
                media=await _video_link(video_id,quality,refresh=refresh)
                return {'video':media,'audio':None,'container':'webm' if 'webm' in str(media.get('mime','')) else 'mp4'}
            return await _dash_pair(video_id,quality,refresh)
        manager=clipstream.Manager(await http(),identify,resolve)
        request.app['clip_streams']=manager
    return manager

def _clip_cookie_gate():
    state=ytcookies.state()
    if state.get('browser') or (state.get('present') and state.get('signed_in') and not state.get('expired')):
        return None
    return web.json_response({'error':'YouTube sign-in cookies are required for clips',
        'code':'youtube_cookies_required'},status=403)

async def _pause_clips_without_cookies(request):
    if _clip_cookie_gate() is None:return
    manager=request.app.get('clip_streams')
    if manager:
        await asyncio.gather(*(job.pause() for job in list(manager.sessions.values())
            if job.state not in ('done','error','cancelled','paused')),return_exceptions=True)

@routes.get('/api/clips/catalog')
async def clips_catalog(request):
    gate=_clip_cookie_gate()
    if gate is not None:return gate
    query=(request.query.get('q') or 'official music video').strip()
    if not 2<=len(query)<=200:return fail('Enter 2–200 characters')
    limit=_int(request,'limit',24,1,36)
    catalog=request.app.get('clips_catalog57')
    if catalog is None:
        async def search(q,n):
            rows=await ytmusic.video_search(q,n)
            return rows or await youtube.search(q,n,videos=True)
        catalog=clipcatalog.Catalog(search);request.app['clips_catalog57']=catalog
    state=ytcookies.state()
    identity=(state.get('updated_at',0),state.get('browser',''),state.get('count',0))
    try:return ok({'items':await catalog.get(query,limit,identity),'query':query})
    except asyncio.TimeoutError:return fail('Video search timed out; try again',504)
    except Exception:return fail('Video catalog unavailable; try again',502)

@routes.post('/api/clips/sessions')
async def clips_session_create(request):
    _karaoke_origin(request)
    body=await _body(request)
    if not isinstance(body,dict):return fail('Expected a JSON object')
    track=str(body.get('id') or '').strip()
    if not track or len(track)>2048:return fail('Choose a track or YouTube video')
    try:
        quality=int(body.get('quality',720))
        if quality not in (144,240,360,480,720,1080,1440,2160):raise ValueError('Unsupported quality')
        gate=_clip_cookie_gate()
        if gate is not None:return gate
        manager=await _clip_studio_manager(request)
        job=await manager.create(track,str(body.get('title') or '')[:500],str(body.get('artist') or '')[:500],quality,body.get('retry') is True)
        return ok(job.public())
    except (ValueError,TypeError):return fail('Invalid clip options or session limit reached')

@routes.get('/api/clips/sessions')
async def clips_sessions_list(request):
    manager=await _clip_studio_manager(request)
    return ok({'items':[x.public() for x in manager.sessions.values()]})

@routes.get('/api/clips/sessions/{sid}')
async def clips_session_status(request):
    manager=await _clip_studio_manager(request);job=manager.get(request.match_info['sid'])
    return ok(job.public()) if job else fail('Clip session not found',404)

@routes.post('/api/clips/sessions/{sid}/control')
async def clips_session_control(request):
    _karaoke_origin(request)
    manager=await _clip_studio_manager(request);job=manager.get(request.match_info['sid'])
    if not job:return fail('Clip session not found',404)
    body=await _body(request);action=body.get('action') if isinstance(body,dict) else None
    if action=='pause':await job.pause()
    elif action=='resume':
        gate=_clip_cookie_gate()
        if gate is not None:return gate
        if job.state in ('error','cancelled'):return fail('Retry this clip to restart a failed download',409)
        await job.resume()
    elif action=='cancel':await job.cancel()
    else:return fail('Unknown clip action')
    return ok(job.public())

@routes.get('/api/clips/sessions/{sid}/media/{kind}')
async def clips_session_media(request):
    gate=_clip_cookie_gate()
    if gate is not None:return gate
    manager=await _clip_studio_manager(request);job=manager.get(request.match_info['sid'])
    if not job:return fail('Clip session not found',404)
    source=job.sources.get(request.match_info['kind'])
    if not source:return fail('Clip track is not ready',409)
    return await source.serve(request)

@routes.get('/api/clips/sessions/{sid}/file')
async def clips_session_file(request):
    gate=_clip_cookie_gate()
    if gate is not None:return gate
    manager=await _clip_studio_manager(request);job=manager.get(request.match_info['sid'])
    if not job:return fail('Clip session not found',404)
    if not job.final or not job.final.exists():return fail('The complete clip is not ready yet',409)
    return web.FileResponse(job.final,headers={'Content-Type':'video/webm' if job.container=='webm' else 'video/mp4',
        'Content-Disposition':f'attachment; filename="clip-{clipcache._safe(job.video_id)}-{job.height}p.{job.container}"',
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@routes.post('/api/song-finder/text')
async def song_finder_text(request):
    _karaoke_origin(request)
    from . import songfinder
    data=await _body(request);query=str(data.get('query') or '').strip()
    if not 2<=len(query)<=600:return fail('Enter 2–600 characters',400)
    if songfinder._slots.locked():return fail('Song search is busy; try again shortly',429)
    async with songfinder._slots:
        try:items=await songfinder.candidates(query)
        except ValueError as exc:return fail(str(exc),502)
    return ok({'items':items,'mode':'text','requested_minimum':10,'found':len(items),'recognition':None})


@routes.post('/api/song-finder/tiktok')
async def song_finder_tiktok(request):
    _karaoke_origin(request)
    from . import songfinder, tiktokfinder
    import math
    data=await _body(request)
    if not isinstance(data,dict):return fail('Expected a JSON object',400)
    if data.get('consent') is not True:return fail('Consent to downloading TikTok audio and sending a fingerprint is required.',400)
    try:
        url=tiktokfinder.normalize_url(data.get('url'))
        raw=data.get('offset',0)
        if isinstance(raw,bool):raise ValueError('Invalid sample position')
        offset=float(raw)
        if not math.isfinite(offset) or not 0<=offset<=600:raise ValueError('TikTok sample start must be between 0 and 600 seconds.')
    except (ValueError,TypeError) as exc:return fail(str(exc),400)
    if songfinder._slots.locked():return fail('Song search is busy; try again shortly',429)
    async with songfinder._slots:
        try:return ok(await asyncio.wait_for(tiktokfinder.for_request(request,url,await http(),offset),180))
        except ValueError as exc:return fail(str(exc),422)
        except asyncio.TimeoutError:return fail('TikTok analysis timed out. Try another excerpt or upload the video.',504)
        except (aiohttp.ClientError,OSError):return fail(tiktokfinder.NETWORK,502)


@routes.post('/api/song-finder/file')
async def song_finder_file(request):
    _karaoke_origin(request)
    from . import songfinder
    import tempfile, math
    from pathlib import Path
    if request.query.get('consent')!='1':return fail('Consent to sending an acoustic fingerprint is required',400)
    if not request.content_type.startswith('multipart/'):return fail('A multipart media upload is required',400)
    try:offset=float(request.query.get('offset','0'))
    except ValueError:return fail('Invalid sample position',400)
    if not math.isfinite(offset) or not 0<=offset<=7200:return fail('Sample position must be between 0 and 7200 seconds',400)
    if songfinder._slots.locked():return fail('Song search is busy; try again shortly',429)
    async with songfinder._slots:
        # Streaming read with an independent limit, even for chunked transfer.
        with tempfile.TemporaryDirectory(prefix='kryonyx-identify-') as temp:
            try:
                reader=await request.multipart();part=await reader.next()
                if part is None or part.name!='file':return fail('A media file is required',400)
                suffix=Path(part.filename or '').suffix.lower()
                if suffix not in songfinder.EXTENSIONS:return fail('Unsupported audio or video file',400)
                uploaded=Path(temp)/('input'+suffix);total=0
                import aiofiles
                async with aiofiles.open(uploaded,'wb') as handle:
                    while True:
                        chunk=await part.read_chunk(65536)
                        if not chunk:break
                        total+=len(chunk)
                        if total>songfinder.MAX_UPLOAD:return fail('File exceeds 100 MB',413)
                        await handle.write(chunk)
                if total==0:return fail('The file is empty',400)
                sample=Path(temp)/'sample.wav'
                await asyncio.to_thread(songfinder.extract_sample,uploaded,sample,offset)
                identity=await songfinder.recognize(sample,await http())
                catalogue_error=None
                try:items=await songfinder.candidates(' '.join([identity['artist'],identity['title']]),identity) if identity else []
                except ValueError as exc:items=[];catalogue_error=str(exc)
                return ok({'items':items,'mode':'fingerprint','recognition':identity,'found':len(items),'requested_minimum':10,'catalogue_error':catalogue_error})
            except (ValueError,asyncio.TimeoutError) as exc:return fail(str(exc) or 'The recognition request timed out',422)
            except (aiohttp.ClientError,OSError):return fail('Could not complete recognition; check the file and network connection',502)


@routes.get('/api/recommend/quick')
async def recommend_quick(request):
    recent,likes=await asyncio.gather(asyncio.to_thread(storage.history,40),asyncio.to_thread(storage.list_likes,40))
    seen=set();items=[]
    for track in recent+likes:
        identity=(track.get('artist','').casefold(),track.get('title','').casefold())
        if track.get('id') in seen or identity in seen:continue
        seen.update((track.get('id'),identity));items.append(track)
    return ok({'items':items[:24],'basis':'local-history-and-likes'})


def _translation_id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value) is not None

@routes.post('/api/lyrics/translate')
async def lyrics_translate(request):
    _karaoke_origin(request)
    from . import lyric_translate
    data=await _body(request)
    if not isinstance(data,dict): return fail('Invalid request',400)
    rid=data.get('request_id')
    if rid is not None and not _translation_id(rid): return fail('Invalid request ID',400)
    cancelled=request.app['translation_cancellations']; jobs=request.app['translation_jobs']
    now=time.monotonic()
    for key,until in list(cancelled.items()):
        if until < now: cancelled.pop(key,None)
    if rid and rid in cancelled:
        cancelled.pop(rid,None)
        return fail('Translation cancelled',499)
    if rid and rid in jobs: return fail('Duplicate request ID',409)
    job=asyncio.create_task(lyric_translate.translate_offline(data.get('lines'),data.get('target'),data.get('source'),data.get('context')))
    if rid: jobs[rid]=job
    try:
        return ok(await job)
    except asyncio.CancelledError:
        if job.cancelled(): return fail('Translation cancelled',499)
        raise
    except lyric_translate.TranslationUnavailable as exc:
        return web.json_response({'error':str(exc),'error_code':exc.code},status=503)
    except ValueError as exc:return fail(str(exc),400)
    except asyncio.TimeoutError:return fail('Offline translation took too long.',504)
    finally:
        if rid and jobs.get(rid) is job: jobs.pop(rid,None)

@routes.post('/api/lyrics/translate/cancel')
async def lyrics_translate_cancel(request):
    _karaoke_origin(request)
    data=await _body(request)
    rid=data.get('request_id') if isinstance(data,dict) else None
    if not _translation_id(rid): return fail('Invalid request ID',400)
    jobs=request.app['translation_jobs']; cancelled=request.app['translation_cancellations']
    job=jobs.get(rid)
    if job:
        job.cancel()
        await asyncio.gather(job,return_exceptions=True)
    else:
        # Handle cancellation arriving before the translation request.
        if len(cancelled)>=256: cancelled.pop(next(iter(cancelled)))
        cancelled[rid]=time.monotonic()+30
    return ok({'cancelled':True})


@routes.post('/api/audio-share')
async def audio_share_create64(request):
    _karaoke_origin(request)
    from .audio_share import ShareError
    data=await _body(request)
    if data.get('consent') is not True:return fail('Confirm audio file preparation',400)
    try:return ok(request.app['audio_share64'].create(data.get('track'),_media_for,await http()))
    except ShareError as exc:return fail(str(exc),400)

@routes.get('/api/audio-share/{token}')
async def audio_share_status64(request):
    _karaoke_origin(request)
    from .audio_share import ShareError
    try:return ok(request.app['audio_share64'].get(request.match_info['token']))
    except ShareError as exc:return fail(str(exc),404)

@routes.delete('/api/audio-share/{token}')
async def audio_share_cancel64(request):
    _karaoke_origin(request)
    await request.app['audio_share64'].cancel(request.match_info['token'])
    return ok({'cancelled':True})

@routes.get('/api/audio-share/{token}/file')
async def audio_share_file64(request):
    _karaoke_origin(request)
    from .audio_share import completed,ShareError,portable_name
    from urllib.parse import quote
    try:
        path,name=completed(request.match_info['token'])
        if request.query.get('portable')=='1':name=portable_name(name)
        return web.FileResponse(path,headers={'Content-Type':'audio/mpeg','Content-Disposition':"attachment; filename*=UTF-8''"+quote(name),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    except ShareError as exc:return fail(str(exc),404)


# --------------------------------------------------------------------------- #
# v72: optional AI enhancement (Real-ESRGAN wallpapers/clips, RIFE smoothness)
# --------------------------------------------------------------------------- #
_AI_WALL_MODELS72 = {'photo': 'RealESRGAN_x4plus', 'fast': 'realesr-general-x4v3', 'art': 'realesr-animevideov3'}
_AI_CLIP_MODELS72 = {'general': 'realesr-general-x4v3', 'anime': 'realesr-animevideov3'}


def _ai72(request):
    return request.app['ai_jobs72']


def _ai_spec72(model_id):
    from . import ai_models
    spec = ai_models.MODELS[model_id]
    out = {'path': str(ai_models.path(model_id)), 'arch': spec['arch']}
    if spec.get('num_conv'):
        out['num_conv'] = spec['num_conv']
    return out


async def _ai_ready72(request, models):
    """None when the engine and weights are ready, else a 409 response."""
    from . import ai_models
    info = await _ai72(request).probe()
    if not info.get('installed'):
        return web.json_response({'error': 'AI module is not installed', 'code': 'engine', 'engine': info}, status=409)
    missing = [m for m in models if not await asyncio.to_thread(ai_models.present, m)]
    if missing:
        return web.json_response({'error': 'AI model is not downloaded', 'code': 'models', 'missing': missing}, status=409)
    return None


def _ai_setup_script72():
    from .paths import app_dir
    name = 'setup-ai.bat' if os.name == 'nt' else 'setup-ai.sh'
    path = os.path.join(app_dir(), name)
    return name, path if os.path.isfile(path) else None


@routes.get('/api/ai/status')
async def ai_status72(request):
    from . import ai_models
    jobs = _ai72(request)
    engine = await jobs.probe(request.query.get('refresh') == '1')
    name, script = _ai_setup_script72()
    return ok({'engine': engine, 'models': await asyncio.to_thread(ai_models.summary),
               'downloads': jobs.downloads.public(), 'jobs': jobs.list()[:12], 'busy': jobs.busy(),
               'setup': {'script': name, 'available': bool(script), 'launch': bool(script) and os.name == 'nt'}})


@routes.post('/api/ai/models')
async def ai_models_download72(request):
    _karaoke_origin(request)
    from . import ai_models
    data = await _body(request)
    ids = [str(x) for x in data.get('ids') or []]
    if data.get('feature'):
        ids += ai_models.NEEDS.get(str(data['feature']), [])
    try:
        return ok({'downloads': _ai72(request).downloads.start(ids, http)})
    except ValueError as exc:
        return fail(str(exc))


@routes.post('/api/ai/install')
async def ai_install72(request):
    """Opens the setup script in its own console window (Windows) — visible to the user."""
    _karaoke_origin(request)
    name, script = _ai_setup_script72()
    if not script:
        return fail('Setup script was not found next to the program', 404)
    if os.name != 'nt':
        return ok({'launched': False, 'command': 'sh ' + name})
    import subprocess
    # Own visible console (CREATE_NEW_CONSOLE); relative name + cwd avoids quoting issues with spaces.
    await asyncio.to_thread(subprocess.Popen, ['cmd', '/k', name], cwd=os.path.dirname(script),
                            creationflags=0x00000010)
    _ai72(request)._probe = None
    return ok({'launched': True})


@routes.post('/api/ai/wallpaper')
async def ai_wallpaper72(request):
    _karaoke_origin(request)
    from . import ai_jobs, wallpaper
    from PIL import Image
    import uuid
    query = request.query
    owned = None
    try:
        if request.content_type.startswith('image/'):
            body = await request.read()
            if not body or len(body) > wallpaper.MAX_BYTES:
                return fail('Image is too large (25 MB maximum)', 413)
            owned = ai_jobs.work_dir() / (uuid.uuid4().hex + '.img')
            await audiovault.run_blocking_owned(owned.write_bytes, body)
            source, original = owned, 'local'
            data = dict(query)
        else:
            data = {**dict(query), **(await _body(request))}
            name = str(data.get('file') or '')
            if not re.fullmatch(r'[a-f0-9]{64}\.jpg', name):
                return fail('Choose a wallpaper image first')
            source, original = wallpaper.directory() / name, name
            if not source.is_file():
                return fail('Wallpaper file was not found', 404)
        style = str(data.get('model') or 'fast')
        if style not in _AI_WALL_MODELS72:
            raise ValueError('Unknown AI model')
        model = _AI_WALL_MODELS72[style]
        blocked = await _ai_ready72(request, [model])
        if blocked is not None:
            if owned: owned.unlink(missing_ok=True)
            return blocked

        def measure():
            with Image.open(source) as im:
                if im.width * im.height > 40_000_000:
                    raise ValueError('Image exceeds 40 megapixels')
                return im.width, im.height
        width, height = await audiovault.run_blocking_owned(measure)
        target = max(1280, min(3840, int(float(data.get('target') or 2560))))
        longest = max(width, height)
        factor = min(4.0, target / longest) if longest < target else 1.0
        factor = min(factor, 3840 / longest) if longest * factor > 3840 else factor
        out_w, out_h = max(1, round(width * factor)), max(1, round(height * factor))
        jid_file = ai_jobs.work_dir() / (uuid.uuid4().hex + '.jpg')
        job = {'mode': 'image', 'input': str(source), 'output': str(jid_file), 'upscale': _ai_spec72(model),
               'out_w': out_w, 'out_h': out_h, 'device': 'auto', '_cleanup': [str(owned)] if owned else []}
        public = {'original': original, 'options': {'model': style, 'in_width': width, 'in_height': height,
                                                    'out_width': out_w, 'out_height': out_h, 'factor': round(factor, 2)}}
        result = _ai72(request).submit('wallpaper', job, public)
        owned = None  # The submitted job now owns the temporary input.
        return ok(result)
    except (ValueError, OSError, Image.DecompressionBombError) as exc:
        return fail(str(exc) or 'Could not read the image')
    except Exception:
        return fail('Could not read the image')
    finally:
        if owned:
            owned.unlink(missing_ok=True)


def _ai_clip_session72(request, sid):
    manager = request.app.get('clip_streams')
    return manager.get(sid) if manager else None


@routes.get('/api/ai/clip')
async def ai_clip_list72(request):
    from . import ai_jobs
    sid = str(request.query.get('session') or '')
    if not re.fullmatch(r'[a-f0-9]{24}', sid):
        return fail('Clip session is required')
    return ok({'items': await asyncio.to_thread(ai_jobs.clips_for, sid)})


@routes.post('/api/ai/clip')
async def ai_clip72(request):
    _karaoke_origin(request)
    from . import ai_jobs
    data = await _body(request)
    sid = str(data.get('session') or '')
    session = _ai_clip_session72(request, sid) if re.fullmatch(r'[a-f0-9]{24}', sid) else None
    if session is None:
        return fail('Open the clip first', 404)
    if not session.sources or not all(s.done for s in session.sources.values()):
        return fail('Wait until the clip finishes downloading', 409)
    upscale = str(data.get('upscale') or 'off')
    style = str(data.get('style') or 'general')
    smooth = data.get('smooth') is True
    if upscale not in ('off', 'x2', '1080', '1440', '2160') or style not in _AI_CLIP_MODELS72:
        return fail('Unsupported AI options')
    height = int(session.height or 0)
    target = None
    if upscale != 'off':
        if not height:
            return fail('Clip resolution is unknown', 409)
        target = min(2160, height * 2) if upscale == 'x2' else int(upscale)
        target = min(target, height * 4)
        if target <= height:
            return fail('The clip is already at this resolution or higher')
    if not target and not smooth:
        return fail('Choose a higher resolution, smoother motion or both')
    video = str(session.sources['video'].final)
    audio = str(session.sources['audio'].final) if 'audio' in session.sources else None
    options = {'upscale': upscale, 'height': target, 'style': style if target else None, 'smooth': smooth}
    key = await asyncio.to_thread(ai_jobs.clip_key, video, audio, options)
    if await asyncio.to_thread(ai_jobs.clip_result, key):
        manifest = await asyncio.to_thread(ai_jobs.clip_manifest, key) or {}
        return ok({'id': None, 'kind': 'clip', 'stage': 'done', 'finished': True, 'cached': True, 'key': key,
                   'url': f'/api/ai/result/{key}.mp4', 'session': sid, 'options': options,
                   'out_height': manifest.get('height'), 'out_fps': manifest.get('fps')})
    models = ([_AI_CLIP_MODELS72[style]] if target else []) + (['rife'] if smooth else [])
    blocked = await _ai_ready72(request, models)
    if blocked is not None:
        return blocked
    ffmpeg = clipcache.ffmpeg_exe()
    if not ffmpeg:
        return fail('FFmpeg is not available', 409)
    job = {'mode': 'video', 'input': video, 'audio': audio, 'output': str(ai_jobs.clips_dir() / (key + '.mp4')),
           'ffmpeg': ffmpeg, 'upscale': _ai_spec72(_AI_CLIP_MODELS72[style]) if target else None,
           'interpolate': _ai_spec72('rife') if smooth else None, 'height': target, 'device': 'auto',
           '_key': key, '_session': sid, '_options': options}
    try:
        return ok(_ai72(request).submit('clip', job, {'session': sid, 'options': options, 'key': key}))
    except ValueError as exc:
        return fail(str(exc), 429)


@routes.get('/api/ai/jobs')
async def ai_jobs_list72(request):
    return ok({'items': _ai72(request).list()})


@routes.get('/api/ai/jobs/{jid}')
async def ai_job72(request):
    value = _ai72(request).status(request.match_info['jid'])
    return ok(value) if value else fail('Job not found', 404)


@routes.delete('/api/ai/jobs/{jid}')
async def ai_job_cancel72(request):
    _karaoke_origin(request)
    value = await _ai72(request).cancel(request.match_info['jid'])
    return ok(value) if value else fail('Job not found', 404)


@routes.get('/api/ai/result/{name}')
async def ai_result72(request):
    from . import ai_jobs
    name = request.match_info['name']
    if not re.fullmatch(r'[a-f0-9]{32}\.mp4', name):
        raise web.HTTPNotFound()
    path = await asyncio.to_thread(ai_jobs.clip_result, name[:-4])
    if not path:
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={'Content-Type': 'video/mp4', 'Cache-Control': 'no-store',
                                           'X-Content-Type-Options': 'nosniff'})


@routes.delete('/api/ai/result/{name}')
async def ai_result_delete72(request):
    _karaoke_origin(request)
    from . import ai_jobs
    key = request.match_info['name'].removesuffix('.mp4')
    path = await asyncio.to_thread(ai_jobs.clip_result, key)
    if not path:
        return fail('Result not found', 404)
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except OSError:   # Windows: the file is still being streamed to the player
        return fail('The file is in use. Try again in a moment', 409)
    await asyncio.to_thread((ai_jobs.clips_dir() / (key + '.json')).unlink, missing_ok=True)
    return ok({'deleted': key})
