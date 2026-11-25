"""Public Spotify metadata provider.

Spotify does not expose full audio to third-party players.  This module uses
the same public web-player endpoints as open.spotify.com for catalogue
metadata, then Kryonyx resolves playback through the enabled open streaming
providers (YouTube, SoundCloud, Audius, etc.).

The protocol implementation is independent Python code built on the public
web-player endpoints and their persisted-query identifiers.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlencode, urlparse

from . import library

log = logging.getLogger("kryonyx.spotify")

TOKEN_URL = "https://open.spotify.com/api/token"
SERVER_TIME_URL = "https://open.spotify.com/api/server-time"
PATHFINDER_URL = "https://api-partner.spotify.com/pathfinder/v2/query"
REMOTE_SECRETS_URL = (
    "https://raw.githubusercontent.com/xyloflake/spot-secrets-go/"
    "refs/heads/main/secrets/secretDict.json"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/131 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://open.spotify.com",
    "Referer": "https://open.spotify.com/",
}

HASHES = {
    "searchArtists": "0e6f9020a66fe15b93b3bb5c7e6484d1d8cb3775963996eaede72bac4d97e909",
    "searchAlbums": "a71d2c993fc98e1c880093738a55a38b57e69cc4ce5a8c113e6c5920f9513ee2",
    "searchTracks": "bc1ca2fcd0ba1013a0fc88e6cc4f190af501851e3dafd3e1ef85840297694428",
    "searchPlaylists": "fc3a690182167dbad20ac7a03f842b97be4e9737710600874cb903f30112ad58",
    "queryArtistOverview": "1ac33ddab5d39a3a9c27802774e6d78b9405cc188c6f75aed007df2a32737c72",
    "queryArtistDiscographyAll": "5e07d323febb57b4a56a42abbf781490e58764aa45feb6e3dc0591564fc56599",
    "getAlbum": "97dd13a1f28c80d66115a13697a7ffd94fe3bebdb94da42159456e1d82bfee76",
    "fetchPlaylist": "e578eda4f77aae54294a48eac85e2a42ddb203faf6ea12b3fddaec5aa32918a3",
    "fetchPlaylistContents": "c56c706a062f82052d87fdaeeb300a258d2d54153222ef360682a0ee625284d9",
}

# Spotify rotates these web-player TOTP seeds.  Remote seeds are used when all
# bundled versions expire, so an application update is not required.
_SEEDS = (
    (61, ',7/*F("rLJ2oxaKL^f+E1xvP@N'),
    (60, 'OmE{ZA.J^":0FG\\Uz?[@WW'),
    (59, "{iOFn;4}<1PFYKPV?5{%u14]M>/V0hDH"),
)

_token: tuple[str, float] | None = None
_token_version: int | None = None
_official_token_cache: tuple[str, float] | None = None
_failed_seeds: set[int] = set()
_remote_seeds: tuple[dict[str, list[int]], float] | None = None
_token_lock = asyncio.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def _cache_put(key: str, value: Any, ttl: float = 300.0):
    # Пустой ответ не кэшируем: иначе одна неудачная выдача «залипала» на
    # пять минут и любой следующий поиск возвращал ноль за 0 мс.
    if not value:
        return value
    if len(_cache) > 300:
        _cache.clear()
    _cache[key] = (time.monotonic() + ttl, value)
    return value


def _decode(values: list[int]) -> bytes:
    text = "".join(chr(value ^ ((index % 33) + 9))
                   for index, value in enumerate(values))
    return text.encode("utf-8")


def _totp(secret: bytes, clock: int, period: int) -> str:
    counter = int(clock // period).to_bytes(8, "big")
    digest = hmac.new(secret, counter, hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return str(number % 1_000_000).zfill(6)


async def _json_get(url: str, *, headers: dict | None = None,
                    timeout: float = 12.0) -> Any:
    import aiohttp
    session = await library.http()
    async with session.get(url, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Spotify HTTP {resp.status}")
        return await resp.json(content_type=None)


async def _remote() -> dict[str, list[int]]:
    global _remote_seeds
    if _remote_seeds and _remote_seeds[1] > time.monotonic():
        return _remote_seeds[0]
    data = await _json_get(REMOTE_SECRETS_URL)
    value = data if isinstance(data, dict) else {}
    _remote_seeds = (value, time.monotonic() + 3600)
    return value


async def _seed_candidates():
    for version, encoded in _SEEDS:
        if version not in _failed_seeds:
            yield version, _decode([ord(ch) for ch in encoded])
    try:
        remote = await _remote()
    except Exception as exc:
        log.debug("[spotify] remote TOTP seeds: %s", exc)
        remote = {}
    for raw_version in sorted(remote, key=lambda x: int(x), reverse=True):
        version = int(raw_version)
        if version not in _failed_seeds and isinstance(remote[raw_version], list):
            yield version, _decode(remote[raw_version])


_EMBED_PAGE = "https://open.spotify.com/embed/track/0VjIjW4GlUZAMYd2vXMi3b"
_TOKEN_RE = re.compile(r'"accessToken":"([^"]+)"')
_TOKEN_EXP_RE = re.compile(r'"accessTokenExpirationTimestampMs":(\d+)')


async def _page_get(url: str, timeout: float = 15.0) -> str:
    import aiohttp
    session = await library.http()
    headers = {**HEADERS, "Accept": "text/html,application/xhtml+xml"}
    async with session.get(url, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Spotify HTTP {resp.status}")
        return await resp.text()


async def _embed_token() -> tuple[str, float]:
    """Анонимный токен веб-плеера со страницы встраиваемого плеера.

    Ручка `/api/token` теперь отвечает «Unauthorized request» всем, кто не
    браузер: TOTP-подпись её больше не открывает. Зато страница embed
    отдаётся всем и уже содержит готовый гостевой токен — тот самый, которым
    сам Spotify обращается к своему Pathfinder. Ни client id, ни секрета, ни
    аккаунта для этого не нужно.
    """
    html = await _page_get(_EMBED_PAGE)
    found = _TOKEN_RE.search(html)
    if not found:
        raise RuntimeError("Spotify guest token is not on the page")
    expires = _TOKEN_EXP_RE.search(html)
    deadline = (float(expires.group(1)) / 1000) if expires else (time.time() + 1800)
    return found.group(1), deadline


async def _access_token(force: bool = False) -> str:
    global _token, _token_version
    if force:
        # Отвергнутый токен
        # заодно отвергает версию подписи, которая его выдала. У гостевого
        # токена версии нет — он просто берётся заново.
        if _token_version is not None:
            _failed_seeds.add(_token_version)
        _token = None
        _token_version = None
    if not force and _token and _token[1] - time.time() > 30:
        return _token[0]
    async with _token_lock:
        if not force and _token and _token[1] - time.time() > 30:
            return _token[0]
        # Сначала гостевой токен со страницы embed: он работает без ключей и
        # приходит одним запросом. TOTP-путь остаётся ниже как запасной.
        try:
            token, deadline = await _embed_token()
        except Exception as exc:
            log.info("[spotify] guest token: %s", exc)
        else:
            _token = (token, deadline)
            _token_version = None
            return token
        server = await _json_get(SERVER_TIME_URL, headers=HEADERS)
        server_time = int((server or {}).get("serverTime") or time.time())
        async for version, secret in _seed_candidates():
            query = urlencode({
                "reason": "init",
                "productType": "web-player",
                "totp": _totp(secret, int(time.time()), 30),
                "totpVer": version,
                "totpServer": _totp(secret, server_time, 900),
            })
            try:
                data = await _json_get(f"{TOKEN_URL}?{query}", headers=HEADERS)
            except Exception:
                _failed_seeds.add(version)
                continue
            token = str((data or {}).get("accessToken") or "")
            expires = float((data or {}).get("accessTokenExpirationTimestampMs") or 0) / 1000
            if token:
                _token = (token, expires or time.time() + 300)
                _token_version = version
                _failed_seeds.clear()
                return token
            _failed_seeds.add(version)
        raise RuntimeError("Spotify web token is unavailable")


async def _query(operation: str, variables: dict, retry: bool = True) -> dict:
    import aiohttp
    token = await _access_token()
    body = {
        "operationName": operation,
        "variables": variables,
        "extensions": {"persistedQuery": {
            "version": 1, "sha256Hash": HASHES[operation]}},
    }
    session = await library.http()
    headers = {**HEADERS, "Content-Type": "application/json",
               "Authorization": f"Bearer {token}"}
    async with session.post(PATHFINDER_URL, json=body, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=18)) as resp:
        if resp.status == 401 and retry:
            await resp.read()
            await _access_token(True)
            return await _query(operation, variables, False)
        if resp.status != 200:
            raise RuntimeError(f"Spotify Pathfinder HTTP {resp.status}")
        data = await resp.json(content_type=None)
    if isinstance(data, dict) and data.get("errors"):
        raise RuntimeError(str(data["errors"][0].get("message") or "Spotify query failed"))
    return data if isinstance(data, dict) else {}


def _search_vars(query: str, limit: int) -> dict:
    return {
        "searchTerm": query, "limit": limit, "offset": 0,
        "numberOfTopResults": limit, "includeAudiobooks": False,
        "includeArtistHasConcertsField": False, "includePreReleases": False,
    }


def _id(uri: str) -> str:
    return str(uri or "").rsplit(":", 1)[-1]


def _url(kind: str, uri: str) -> str:
    ident = _id(uri)
    return f"https://open.spotify.com/{kind}/{ident}" if ident else ""


def _image(node: Any) -> str:
    if isinstance(node, list):
        valid = [src for src in node if isinstance(src, dict) and src.get("url")]
        if not valid:
            return ""
        return str(max(valid, key=lambda src: (src.get("width") or 0)
                       * (src.get("height") or 0)).get("url") or "")
    if not isinstance(node, dict):
        return ""
    sources = node.get("sources") or []
    if not sources and isinstance(node.get("items"), list):
        sources = [src for item in node["items"] if isinstance(item, dict)
                   for src in (item.get("sources") or [])]
    valid = [src for src in sources if isinstance(src, dict) and src.get("url")]
    if not valid:
        return ""
    return str(max(valid, key=lambda src: (src.get("width") or 0)
                   * (src.get("height") or 0)).get("url") or "")


def _credentials() -> tuple[str, str]:
    """Свои ключи Spotify больше не используются: плагин — только источник
    метаданных и работает анонимно. Поля Client ID и
    Client Secret убраны из настроек, поэтому официальный путь всегда выключен."""
    return "", ""


async def _official_token(force: bool = False) -> str:
    global _official_token_cache
    client_id, secret = _credentials()
    if not client_id or not secret:
        raise RuntimeError("Spotify needs a Client ID and Client Secret in Plugins")
    if (not force and _official_token_cache
            and _official_token_cache[1] - time.time() > 30):
        return _official_token_cache[0]
    import aiohttp
    session = await library.http()
    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    async with session.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": "Basic " + auth},
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Spotify authorization failed (HTTP {resp.status})")
        data = await resp.json(content_type=None)
    token = str((data or {}).get("access_token") or "")
    if not token:
        raise RuntimeError("Spotify did not return an access token")
    _official_token_cache = (
        token, time.time() + int((data or {}).get("expires_in") or 3600))
    return token


async def _api_get(path: str, params: dict | None = None, retry: bool = True) -> dict:
    import aiohttp
    token = await _official_token()
    session = await library.http()
    async with session.get(
        "https://api.spotify.com/v1/" + path.lstrip("/"),
        params=params,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        timeout=aiohttp.ClientTimeout(total=18),
    ) as resp:
        if resp.status == 401 and retry:
            await resp.read()
            await _official_token(True)
            return await _api_get(path, params, False)
        if resp.status != 200:
            raise RuntimeError(f"Spotify API HTTP {resp.status}")
        data = await resp.json(content_type=None)
    return data if isinstance(data, dict) else {}


def _artist_name(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    return str((node.get("profile") or {}).get("name") or node.get("name") or "")


def _artists(node: Any) -> list[dict]:
    if not isinstance(node, dict):
        return []
    values = node.get("items") or []
    return [item for item in values if isinstance(item, dict)]


def _track(node: dict) -> dict | None:
    if not isinstance(node, dict) or node.get("__typename") == "NotFound":
        return None
    uri = str(node.get("uri") or "")
    title = str(node.get("name") or "").strip()
    if not uri or not title:
        return None
    album = node.get("albumOfTrack") or {}
    artist_items = _artists(node.get("artists"))
    first = artist_items[0] if artist_items else {}
    duration = ((node.get("duration") or node.get("trackDuration") or {})
                .get("totalMilliseconds"))
    return {
        "id": "sp:" + base64.urlsafe_b64encode(uri.encode()).decode().rstrip("="),
        "title": title,
        "artist": ", ".join(filter(None, (_artist_name(a) for a in artist_items)))
                  or "Spotify",
        "artists": [{"name": _artist_name(a), "url": _url("artist", str(a.get("uri") or "")) or None, "source": "spotify"} for a in artist_items if _artist_name(a)],
        "album": album.get("name"),
        "duration": int(duration / 1000) if duration else None,
        "thumbnail": _image(album.get("coverArt")),
        "source": "spotify",
        "url": _url("track", uri),
        "author_id": first.get("uri") or None,
        "author_url": _url("artist", str(first.get("uri") or "")) or None,
    }


def _official_track(node: dict) -> dict | None:
    if not isinstance(node, dict):
        return None
    ident = str(node.get("id") or "")
    title = str(node.get("name") or "").strip()
    if not ident or not title:
        return None
    uri = str(node.get("uri") or f"spotify:track:{ident}")
    album = node.get("album") or {}
    artist_items = [a for a in (node.get("artists") or []) if isinstance(a, dict)]
    first = artist_items[0] if artist_items else {}
    duration = node.get("duration_ms")
    return {
        "id": "sp:" + base64.urlsafe_b64encode(uri.encode()).decode().rstrip("="),
        "title": title,
        "artist": ", ".join(str(a.get("name") or "") for a in artist_items
                            if a.get("name")) or "Spotify",
        "artists": [{"name": a["name"], "url": (a.get("external_urls") or {}).get("spotify") or (f"https://open.spotify.com/artist/{a['id']}" if a.get("id") else _url("artist", str(a.get("uri") or "")) or None), "source": "spotify"} for a in artist_items if a.get("name")],
        "album": album.get("name"),
        "duration": int(duration / 1000) if duration else None,
        "thumbnail": _image(album.get("images") or []),
        "source": "spotify",
        "url": ((node.get("external_urls") or {}).get("spotify")
                or f"https://open.spotify.com/track/{ident}"),
        "author_id": first.get("id") or None,
        "author_url": ((first.get("external_urls") or {}).get("spotify")
                       or (f"https://open.spotify.com/artist/{first['id']}"
                           if first.get("id") else None)),
    }


async def search(query: str, limit: int = 25, offset: int = 0) -> list[dict]:
    if not query.strip():
        return []
    key = f"tracks:{query.lower()}:{limit + offset}"
    hit = _cache_get(key)
    if hit is None:
        client_id, secret = _credentials()
        rows = []
        if client_id and secret:
            data = await _api_get("search", {
                "q": query, "type": "track", "limit": min(50, limit + offset),
                "offset": 0,
            })
            for item in ((data.get("tracks") or {}).get("items") or []):
                mapped = _official_track(item)
                if mapped:
                    rows.append(mapped)
        else:
            # Keep compatibility with the anonymous web protocol if
            # Spotify enables it again; current deployments normally use the
            # official credentials path above.
            data = await _query("searchTracks", _search_vars(query, limit + offset))
            wrappers = (((data.get("data") or {}).get("searchV2") or {})
                        .get("tracksV2") or {}).get("items") or []
            for wrapper in wrappers:
                mapped = _track(((wrapper or {}).get("item") or {}).get("data") or {})
                if mapped:
                    rows.append(mapped)
        hit = _cache_put(key, rows)
    return list(hit)[offset:offset + limit]


async def artists(query: str, limit: int = 12) -> list[dict]:
    if not query.strip():
        return []
    client_id, secret = _credentials()
    if client_id and secret:
        data = await _api_get("search", {
            "q": query, "type": "artist", "limit": min(50, limit), "offset": 0})
        out = []
        for artist in ((data.get("artists") or {}).get("items") or []):
            ident = str(artist.get("id") or "")
            if ident and artist.get("name"):
                out.append({
                    "id": "spotify:artist:" + ident,
                    "name": artist["name"], "source": "spotify",
                    "url": ((artist.get("external_urls") or {}).get("spotify")
                            or f"https://open.spotify.com/artist/{ident}"),
                    "thumbnail": _image(artist.get("images") or []),
                })
        return out[:limit]
    data = await _query("searchArtists", _search_vars(query, limit))
    wrappers = (((data.get("data") or {}).get("searchV2") or {})
                .get("artists") or {}).get("items") or []
    out = []
    for wrapper in wrappers:
        artist = (wrapper or {}).get("data") or {}
        uri = str(artist.get("uri") or "")
        name = _artist_name(artist)
        if uri and name:
            visuals = artist.get("visuals") or {}
            out.append({
                "id": uri, "name": name, "source": "spotify",
                "url": _url("artist", uri),
                "thumbnail": _image((visuals.get("avatarImage") or {})),
            })
    return out[:limit]


def _artist_uri(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("spotify:artist:"):
        return value
    if "open.spotify.com" in value:
        parts = [part for part in urlparse(value).path.split("/") if part]
        if "artist" in parts:
            at = parts.index("artist")
            if at + 1 < len(parts):
                return "spotify:artist:" + parts[at + 1]
    return "spotify:artist:" + value if value else ""


async def artist_page(name: str, value: str, limit: int = 40) -> dict:
    uri = _artist_uri(value)
    if not uri:
        matches = await artists(name, 1)
        uri = str((matches[0] if matches else {}).get("id") or "")
    if not uri:
        return {"name": name or "Artist", "url": value, "source": "spotify",
                "picture": None, "tracks": [], "partial": False}
    client_id, secret = _credentials()
    if client_id and secret:
        ident = _id(uri)
        artist, top = await asyncio.gather(
            _api_get(f"artists/{ident}"),
            _api_get(f"artists/{ident}/top-tracks", {"market": "US"}),
        )
        tracks = [mapped for mapped in
                  (_official_track(item) for item in (top.get("tracks") or []))
                  if mapped]
        return {
            "name": artist.get("name") or name or "Artist",
            "url": ((artist.get("external_urls") or {}).get("spotify")
                    or f"https://open.spotify.com/artist/{ident}"),
            "source": "spotify", "picture": _image(artist.get("images") or []) or None,
            "tracks": tracks[:limit], "partial": False,
            "genres": artist.get("genres") or [],
        }
    data = await _query("queryArtistOverview", {"uri": uri, "locale": ""})
    artist = (data.get("data") or {}).get("artistUnion") or {}
    top = (((artist.get("discography") or {}).get("topTracks") or {}).get("items") or [])
    tracks = []
    for item in top:
        mapped = _track((item or {}).get("track") or {})
        if mapped:
            tracks.append(mapped)
    visuals = artist.get("visuals") or {}
    picture = _image(visuals.get("avatarImage") or {})
    if not picture:
        picture = _image(((artist.get("headerImage") or {}).get("data") or {}))
    return {
        "name": _artist_name(artist) or name or "Artist",
        "url": _url("artist", uri), "source": "spotify",
        "picture": picture or None, "tracks": tracks[:limit], "partial": False,
        "bio": ((artist.get("profile") or {}).get("biography") or {}).get("text"),
    }


def ready() -> bool:
    # The anonymous web-player TOTP flow is used; credentials are only
    # an optional official-API fallback, not a requirement for the library.
    return library.AIOHTTP_OK
