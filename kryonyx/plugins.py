"""
plugins.py — каталог плагинов Kryonyx Music.

Плагин здесь — это описание встроенной возможности (библиотека поиска,
источник метаданных, текстов, скробблер или подборка для главной), которую
можно установить, включить, выключить и настроить прямо из интерфейса.

Состояние хранится в таблице settings (SQLite), ключ `plugins`:

    {
      "installed": ["youtube", "soundcloud", ...],
      "disabled":  ["bandcamp"],
      "config":    {"discogs": {"token": "..."}}
    }

Ничего не скачивается из сети: код всех плагинов уже внутри приложения,
«установка» лишь включает его в работу. Так каталог остаётся безопасным.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from . import storage

log = logging.getLogger(__name__)

STATE_KEY = "plugins"

# --------------------------------------------------------------------------- #
# категории каталога плагинов
# --------------------------------------------------------------------------- #
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("all", "All"),
    ("streaming", "Streaming"),
    ("metadata", "Metadata"),
    ("lyrics", "Lyrics"),
    ("scrobbling", "Scrobbling"),
    ("integrations", "Integrations"),
    ("dashboard", "Dashboard"),
    ("playlists", "Playlists"),
    ("discovery", "Discovery"),
    ("other", "Other"),
)


def _p(pid: str, name: str, version: str, cats: list[str], desc: str, **extra) -> dict:
    """author — те, кто на самом деле делает сервис или библиотеку.

    plugin_author — кто написал сам плагин.
    credits — проекты и люди, чьим кодом или API мы пользуемся.
    """
    extra.pop("based_on", "")
    based_on = ""
    plugin_author = extra.pop("plugin_author", "Kryonyx Music")
    return {
        "id": pid,
        "name": name,
        "author": extra.pop("author", "Kryonyx Music"),
        "plugin_author": plugin_author,
        "credits": extra.pop("credits", []),
        "api": extra.pop("api", ""),
        "based_on": based_on,
        "version": version,
        "categories": cats,
        "description": desc,
        "core": extra.pop("core", False),
        "preinstalled": extra.pop("preinstalled", False),
        "source": extra.pop("source", None),       # id источника поиска, если есть
        "needs_ytdlp": extra.pop("needs_ytdlp", False),
        "settings": extra.pop("settings", []),
        "homepage": extra.pop("homepage", ""),
        **extra,
    }


# --------------------------------------------------------------------------- #
# каталог
# --------------------------------------------------------------------------- #
CATALOG: tuple[dict, ...] = (
    # ------------------------------------------------------------ стриминг --
    _p("youtube", "YouTube", "2.1.0", ["streaming", "metadata"],
       "Search and play the YouTube Music catalogue through the yt-dlp binary, "
       "Piped and Invidious nodes",
       author="Google LLC (YouTube)", core=True, preinstalled=True, source="youtube",
       homepage="https://music.youtube.com",
       api="Piped / Invidious public instances, ytmusicapi, yt-dlp",
       credits=[
           {"name": "Piped (TeamPiped)", "url": "https://github.com/TeamPiped/Piped"},
           {"name": "Invidious", "url": "https://github.com/iv-org/invidious"},
           {"name": "ytmusicapi (sigma67)", "url": "https://github.com/sigma67/ytmusicapi"},
           {"name": "yt-dlp contributors", "url": "https://github.com/yt-dlp/yt-dlp"},
       ]),
    _p("soundcloud", "SoundCloud", "1.4.0", ["streaming"],
       "Indie uploads, remixes and rare tracks; Go+ previews are filtered out",
       author="SoundCloud Global Limited & Co. KG",
       preinstalled=True, source="soundcloud", needs_ytdlp=True,
       homepage="https://soundcloud.com", api="yt-dlp SoundCloud extractor",
       credits=[{"name": "yt-dlp contributors", "url": "https://github.com/yt-dlp/yt-dlp"}]),
    _p("audius", "Audius", "1.2.0", ["streaming"],
       "Open decentralised streaming with direct mp3 links and no rate limits",
       author="Audius / OpenAudio Foundation",
       preinstalled=True, source="audius", homepage="https://audius.co",
       api="Audius Discovery Node API v1"),
    _p("bandcamp", "Bandcamp", "1.1.0", ["streaming", "metadata"],
       "Browse and play independent releases published by the artists themselves",
       author="Bandcamp, Inc.", preinstalled=True, source="bandcamp", needs_ytdlp=True,
       homepage="https://bandcamp.com", api="bcsearch_public_api, yt-dlp",
       credits=[{"name": "yt-dlp contributors", "url": "https://github.com/yt-dlp/yt-dlp"}]),
    _p("archive", "Internet Archive", "1.0.0", ["streaming"],
       "Live sets, archival recordings and netlabel releases with direct audio",
       author="Internet Archive", preinstalled=True, source="archive",
       homepage="https://archive.org", api="archive.org advancedsearch + metadata API"),
    _p("mixcloud", "Mixcloud", "1.0.0", ["streaming"],
       "DJ sets, radio shows and long mixes from Mixcloud",
       author="Mixcloud Ltd.", source="mixcloud", needs_ytdlp=True,
       homepage="https://mixcloud.com", api="api.mixcloud.com, yt-dlp",
       credits=[{"name": "yt-dlp contributors", "url": "https://github.com/yt-dlp/yt-dlp"}]),
    _p("jamendo", "Jamendo", "1.0.0", ["streaming"],
       "Creative Commons catalogue with direct mp3 streams; needs a free Client ID",
       author="Jamendo S.A.", source="jamendo", homepage="https://jamendo.com",
       api="Jamendo API v3.0",
       settings=[{"key": "client_id", "label": "Client ID", "type": "text",
                  "placeholder": "your client id", "required": True,
                  "hint": "Free key from developer.jamendo.com — the shared demo "
                          "key returns an empty catalogue"}]),
    _p("radio", "Internet Radio", "1.0.0", ["streaming", "discovery"],
       "50 000+ live stations from the Radio-Browser directory",
       author="Radio-Browser community (segler-alex)", source="radio",
       homepage="https://www.radio-browser.info", api="Radio-Browser JSON API",
       credits=[{"name": "radio-browser", "url": "https://github.com/segler-alex/radiobrowser-api-rust"}]),

    # ----------------------------------------------------------- метаданные --
    _p("spotify", "Spotify", "0.4.0", ["metadata", "playlists"],
       "Metadata source only: search for tracks, artists and covers, and import "
       "playlists. It plays nothing itself; audio and music videos always come "
       "from YouTube, SoundCloud or another open source",
       author="Spotify AB", preinstalled=True, source="spotify",
       homepage="https://open.spotify.com",
       api="open.spotify.com (anonymous, no account or keys)",
       ),
    _p("deezer", "Deezer", "1.1.0", ["metadata", "streaming"],
       "Search the Deezer catalogue with covers and albums; playback is matched to an open source",
       author="Deezer S.A.", preinstalled=True, source="deezer", homepage="https://deezer.com",
       api="api.deezer.com public search"),
    _p("musicbrainz", "MusicBrainz", "1.0.0", ["metadata"],
       "Open music encyclopaedia: release, label and Cover Art Archive images",
       author="MetaBrainz Foundation", homepage="https://musicbrainz.org",
       api="MusicBrainz WS/2 + Cover Art Archive",
       credits=[{"name": "Cover Art Archive", "url": "https://coverartarchive.org"}]),
    _p("discogs", "Discogs", "0.2.0", ["metadata"],
       "Fetch artist and album metadata from Discogs",
       author="Discogs (Zink Media, LLC)", homepage="https://discogs.com",
       api="Discogs database search API",
       settings=[{"key": "token", "label": "Personal token", "type": "password",
                  "placeholder": "Discogs token",
                  "hint": "Settings → Developers on discogs.com"}]),
    _p("wikipedia", "Wikipedia", "1.0.0", ["metadata"],
       "Short artist biography shown on the artist page",
       author="Wikimedia Foundation", homepage="https://wikipedia.org",
       api="Wikipedia REST v1 page summary"),

    # ---------------------------------------------------------------- текст --
    _p("lrclib", "LRCLIB", "1.3.0", ["lyrics"],
       "Time-synced lyrics for karaoke mode, free and without an account",
       author="tranxuanthang (LRCLIB)", core=True, preinstalled=True,
       homepage="https://lrclib.net", api="lrclib.net public API",
       credits=[{"name": "LRCLIB", "url": "https://github.com/tranxuanthang/lrclib"}]),
    _p("lyricsovh", "lyrics.ovh", "1.0.0", ["lyrics"],
       "Plain text lyrics used when no synced version exists",
       author="lyrics.ovh", preinstalled=True, homepage="https://lyrics.ovh",
       api="api.lyrics.ovh v1"),

    # ---------------------------------------------------------- скробблинг --
    _p("listenbrainz", "ListenBrainz", "1.0.0", ["scrobbling", "integrations"],
       "Submit listens to ListenBrainz with a single user token",
       author="MetaBrainz Foundation", homepage="https://listenbrainz.org",
       api="ListenBrainz API 1/submit-listens",
       settings=[{"key": "token", "label": "User token", "type": "password",
                  "placeholder": "listenbrainz token",
                  "hint": "Profile → Settings on listenbrainz.org"}]),
    _p("maloja", "Maloja", "1.0.0", ["scrobbling", "integrations"],
       "Scrobble to your own self-hosted Maloja server",
       author="krateng (Maloja)", homepage="https://github.com/krateng/maloja",
       api="Maloja mlj_1 newscrobble",
       settings=[{"key": "url", "label": "Server URL", "type": "text",
                  "placeholder": "https://maloja.example.com"},
                 {"key": "key", "label": "API key", "type": "password",
                  "placeholder": "maloja api key"}]),
    _p("lastfm", "Last.fm", "0.9.0", ["scrobbling", "metadata", "integrations"],
       "Scrobble plays to Last.fm using an API key and a session key",
       author="Last.fm (CBS Interactive)", homepage="https://last.fm",
       api="Last.fm API 2.0 track.scrobble",
       settings=[{"key": "api_key", "label": "API key", "type": "text"},
                 {"key": "secret", "label": "Shared secret", "type": "password"},
                 {"key": "session", "label": "Session key", "type": "password",
                  "hint": "Created once via last.fm/api/auth"}]),

    _p("discord", "Discord Rich Presence", "1.4.0", ["integrations"],
       "Show the track you are listening to in your Discord profile",
       author="Discord Inc. (IPC Rich Presence)", homepage="https://discord.com",
       api="Discord IPC SET_ACTIVITY (no extra packages)",
       settings=[{"key": "app_id", "label": "Application ID", "type": "text",
                  "required": False, "placeholder": "1234567890123456789",
                  "link": {"url": "https://discord.com/developers/applications",
                           "label": "Open the Discord Developer Portal"},
                  "guide_title": "How to create your own Discord application",
                  "guide": [
                      "Press the button below and sign in with your Discord account.",
                      "Click New Application, type a name and accept the terms.",
                      "The name of the application is exactly what Discord shows "
                      "in your profile above the track, so name it the way you "
                      "want it to be seen.",
                      "On the General Information page press Copy under "
                      "Application ID (it is a long number).",
                      "Paste that number into the field below — the card in "
                      "Discord switches over within a couple of seconds.",
                      "Optional: in Rich Presence → Art Assets upload a picture "
                      "and put its name into the Small image field.",
                  ],
                  "hint": "Leave it empty to use the built-in Kryo "
                          "application. Your own application lets you choose the "
                          "name and the logo shown on the card"},
                {"key": "activity_type", "label": "Status kind",
                 "type": "select", "default": "listening", "required": False,
                 "options": [{"value": "listening", "label": "Listening to"},
                             {"value": "playing", "label": "Playing"},
                             {"value": "watching", "label": "Watching"},
                             {"value": "competing", "label": "Competing in"}],
                 "hint": "The verb Discord writes before the card"},
                {"key": "line1", "label": "First line", "type": "text",
                 "required": False, "placeholder": "{title}",
                 "hint": "Template. Available: {title}, {artist}, {album}, "
                         "{source}, {app}. Empty means the track title"},
                {"key": "line2", "label": "Second line", "type": "text",
                 "required": False, "placeholder": "{artist}",
                 "hint": "Same templates. Empty means the artist, plus the "
                         "album when it differs from the title"},
                 {"key": "show_cover", "label": "Show track artwork",
                  "type": "checkbox", "default": True, "required": False,
                  "hint": "The cover of the current track, not the app logo"},
                {"key": "large_text", "label": "Artwork caption", "type": "text",
                 "required": False, "placeholder": "{album}",
                 "hint": "Shown when the cursor rests on the cover. Empty "
                         "means no caption at all"},
                 {"key": "show_album", "label": "Show the album",
                  "type": "checkbox", "default": True, "required": False,
                  "hint": "Adds 'on Album' to the second line and to the cover caption"},
                 {"key": "show_time", "label": "Show the progress bar",
                  "type": "checkbox", "default": True, "required": False,
                  "hint": "Elapsed and total time, exactly as in the Spotify card"},
                 {"key": "hide_paused", "label": "Hide the status while paused",
                  "type": "checkbox", "default": False, "required": False,
                  "hint": "On pause the card disappears instead of freezing"},
                {"key": "paused_text", "label": "Text while paused", "type": "text",
                 "required": False, "placeholder": "Paused",
                 "hint": "The little caption in the corner of the cover while "
                         "the track is on pause"},
                {"key": "show_button", "label": "Button under the card",
                 "type": "checkbox", "default": False, "required": False,
                 "hint": "A clickable link, for example to the track on YouTube"},
                {"key": "button_label", "label": "Button text", "type": "text",
                 "required": False, "placeholder": "Listen",
                 "hint": "Up to 31 characters, as Discord allows"},
                {"key": "button_url", "label": "Button link", "type": "text",
                 "required": False, "placeholder": "{url}",
                 "hint": "{url} is the link to the track at its source. "
                         "A fixed address also works"},
                 {"key": "small_image", "label": "Small image", "type": "text",
                  "required": False,
                  "hint": "Optional: asset name or image link for the corner badge"}]),
    _p("mastodon", "Mastodon", "1.0.0", ["integrations"],
       "Share the current track to your Mastodon server in one click",
       author="Mastodon gGmbH and the fediverse", homepage="https://joinmastodon.org",
       api="Mastodon REST /api/v1/statuses",
       settings=[{"key": "url", "label": "Server URL", "type": "text",
                  "placeholder": "https://mastodon.social"},
                 {"key": "token", "label": "Access token", "type": "password",
                  "hint": "Preferences → Development → New application (write:statuses)"},
                 {"key": "visibility", "label": "Visibility", "type": "text",
                  "required": False, "placeholder": "public"}]),

    # ------------------------------------------------------------- подборки --
    _p("audius-trending", "Audius Trending", "1.0.0", ["discovery", "dashboard"],
       "Adds a trending-on-Audius row to the home screen",
       author="Audius / OpenAudio Foundation", preinstalled=True,
       homepage="https://audius.co", api="Audius /v1/tracks/trending"),
    _p("deezer-charts", "Deezer Charts", "1.0.0", ["discovery", "dashboard"],
       "Adds a global chart row to the home screen, matched to playable audio",
       author="Deezer S.A.", homepage="https://deezer.com",
       api="api.deezer.com/chart"),
    _p("listenbrainz-dashboard", "ListenBrainz Dashboard", "0.1.0", ["discovery", "dashboard"],
       "Adds the most listened recordings of the week from ListenBrainz",
       author="MetaBrainz Foundation", homepage="https://listenbrainz.org",
       api="ListenBrainz sitewide statistics",),
    _p("bandcamp-dashboard", "Bandcamp Dashboard", "0.1.1", ["discovery", "dashboard"],
       "Adds Bandcamp notable releases to the home screen",
       author="Bandcamp, Inc.", homepage="https://bandcamp.com",
       api="Bandcamp homepage API",),
    _p("radio-top", "Top Stations", "1.0.0", ["discovery", "dashboard"],
       "Adds a row with the most played internet radio stations",
       author="Radio-Browser community (segler-alex)",
       homepage="https://www.radio-browser.info", api="Radio-Browser topclick"),

    # ------------------------------------------------------------ плейлисты --
    _p("spotify-import", "Spotify Import", "1.3.0", ["playlists", "other"],
       "Paste a Spotify track, album or playlist link and match every track to open audio",
       author="Spotify AB (public page metadata)", preinstalled=True,
       homepage="https://spotify.com",
       api="open.spotify.com/embed (public page data, no account)",
       plugin_author="Kryonyx Music"),
    _p("youtube-import", "YouTube Playlist Import", "1.0.0", ["playlists"],
       "Convert a YouTube or YouTube Music playlist into a Kryo playlist",
       author="Google LLC (YouTube)", preinstalled=True, needs_ytdlp=True,
       homepage="https://youtube.com",
       api="yt-dlp flat playlist, Piped and Invidious as a fallback",
       plugin_author="Kryonyx Music",
       credits=[{"name": "yt-dlp contributors", "url": "https://github.com/yt-dlp/yt-dlp"},
                {"name": "Piped (TeamPiped)", "url": "https://github.com/TeamPiped/Piped"},
                {"name": "Invidious", "url": "https://github.com/iv-org/invidious"}]),
    _p("soundcloud-import", "SoundCloud Set Import", "1.0.0", ["playlists"],
       "Convert a SoundCloud set or single track into a Kryo playlist",
       author="SoundCloud Global Limited & Co. KG", preinstalled=True,
       needs_ytdlp=True, homepage="https://soundcloud.com",
       api="yt-dlp, public page hydration data as a fallback",
       plugin_author="Kryonyx Music",
       credits=[{"name": "yt-dlp contributors", "url": "https://github.com/yt-dlp/yt-dlp"}]),
    _p("m3u", "M3U Export", "1.0.0", ["playlists"],
       "Export any playlist as an .m3u8 file for other players",
       author="Nullsoft (M3U format)", plugin_author="Kryonyx Music",
       api="M3U/M3U8 (Nullsoft format)"),
)

BUILTIN: tuple[dict, ...] = CATALOG
BUILTIN_IDS: frozenset[str] = frozenset(p["id"] for p in CATALOG)

# Свои плагины пользователя (extplugins.py) попадают в тот же каталог: карточка,
# переключатель, настройки и проверка у них общие со встроенными.
_external: dict[str, dict] = {}

BY_ID: dict[str, dict] = {p["id"]: p for p in CATALOG}
SOURCE_PLUGIN: dict[str, str] = {p["source"]: p["id"] for p in CATALOG if p.get("source")}

_lock = threading.Lock()
_cache: dict | None = None


def catalog() -> tuple[dict, ...]:
    """Встроенные плагины плюс свои. Везде ниже ходим только через него."""
    return (*BUILTIN, *_external.values())


def _reindex() -> None:
    items = catalog()
    BY_ID.clear()
    BY_ID.update({p["id"]: p for p in items})
    SOURCE_PLUGIN.clear()
    SOURCE_PLUGIN.update({p["source"]: p["id"] for p in items if p.get("source")})


def is_custom(pid: str) -> bool:
    return pid in _external


def register_external(entries: list[dict]) -> dict:
    """Записывает свои плагины в каталог.

    Файл в папке плагинов — это уже решение пользователя, поэтому новый
    плагин сразу считается установленным. Выключенным он остаётся, если его
    выключили раньше: состояние живёт в настройках и переживает перезагрузку
    каталога.
    """
    global _external
    fresh = {str(item["id"]): item for item in entries if item.get("id")}
    with _lock:
        _external = fresh
        _reindex()
    data = {**state(refresh=True)}
    known = set(data["installed"]) | set(data["disabled"])
    added = [pid for pid in fresh if pid not in known]
    if added:
        data["installed"] = [*data["installed"], *added]
        _save(data)
        log.info("[plugins] custom plugins are added to the catalogue: %s",
                 ", ".join(added))
    return data


# --------------------------------------------------------------------------- #
# состояние
# --------------------------------------------------------------------------- #
def _default_state() -> dict:
    return {
        "installed": [p["id"] for p in catalog() if p["preinstalled"] or p["core"]],
        "disabled": [],
        "config": {},
    }


def state(refresh: bool = False) -> dict:
    global _cache
    with _lock:
        if _cache is not None and not refresh:
            return _cache
        raw = {}
        try:
            raw = storage.get_settings().get(STATE_KEY) or {}
        except Exception as exc:  # база ещё не поднялась
            log.debug("[plugins] state unavailable: %s", exc)
        if not isinstance(raw, dict) or not raw.get("installed"):
            raw = _default_state()
        data = {
            "installed": [i for i in raw.get("installed", []) if i in BY_ID],
            "disabled": [i for i in raw.get("disabled", []) if i in BY_ID],
            "config": raw.get("config") if isinstance(raw.get("config"), dict) else {},
        }
        # ядро нельзя потерять ни при каких правках
        for plugin in catalog():
            if plugin["core"]:
                if plugin["id"] not in data["installed"]:
                    data["installed"].append(plugin["id"])
                if plugin["id"] in data["disabled"]:
                    data["disabled"].remove(plugin["id"])
        _cache = data
        return data


def _save(data: dict) -> dict:
    global _cache
    with _lock:
        _cache = data
    try:
        storage.save_settings({STATE_KEY: data})
    except Exception as exc:
        log.warning("[plugins] could not save state: %s", exc)
    return data


def installed(pid: str) -> bool:
    return pid in state()["installed"]


def enabled(pid: str) -> bool:
    data = state()
    return pid in data["installed"] and pid not in data["disabled"]


def config(pid: str) -> dict:
    value = state()["config"].get(pid)
    return value if isinstance(value, dict) else {}


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def field(pid: str, key: str) -> dict:
    for item in BY_ID.get(pid, {}).get("settings", []):
        if item.get("key") == key:
            return item
    return {}


def flag(pid: str, key: str, default: bool = False) -> bool:
    """Значение флажка плагина: пусто — значит берём значение по умолчанию."""
    raw = config(pid).get(key)
    if raw is None:
        return bool(field(pid, key).get("default", default))
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return bool(field(pid, key).get("default", default)) if text == "" else False
    return bool(field(pid, key).get("default", default))


def enabled_ids(category: str | None = None) -> list[str]:
    out = []
    for plugin in catalog():
        if category and category not in plugin["categories"]:
            continue
        if enabled(plugin["id"]):
            out.append(plugin["id"])
    return out


def enabled_sources() -> list[str]:
    """Источники поиска, доступные сейчас: плагин установлен и включён."""
    return [p["source"] for p in catalog()
            if p.get("source") and enabled(p["id"])]


# --------------------------------------------------------------------------- #
# операции каталога
# --------------------------------------------------------------------------- #
def install(pid: str) -> dict:
    if pid not in BY_ID:
        raise KeyError(pid)
    data = {**state()}
    data["installed"] = list(dict.fromkeys([*data["installed"], pid]))
    data["disabled"] = [i for i in data["disabled"] if i != pid]
    return _save(data)


def uninstall(pid: str) -> dict:
    plugin = BY_ID.get(pid)
    if not plugin:
        raise KeyError(pid)
    if plugin["core"]:
        raise ValueError("core plugin")
    data = {**state()}
    data["installed"] = [i for i in data["installed"] if i != pid]
    data["disabled"] = [i for i in data["disabled"] if i != pid]
    return _save(data)


def set_enabled(pid: str, value: bool) -> dict:
    plugin = BY_ID.get(pid)
    if not plugin:
        raise KeyError(pid)
    data = {**state()}
    if pid not in data["installed"]:
        data["installed"] = [*data["installed"], pid]
    if value or plugin["core"]:
        data["disabled"] = [i for i in data["disabled"] if i != pid]
    else:
        data["disabled"] = list(dict.fromkeys([*data["disabled"], pid]))
    return _save(data)


def configure(pid: str, values: dict) -> dict:
    if pid not in BY_ID:
        raise KeyError(pid)
    data = {**state()}
    conf = {**data["config"]}
    current = {**(conf.get(pid) or {})}
    for key, value in (values or {}).items():
        if isinstance(value, bool):
            # Флажки храним как "1"/"0": настройки лежат строками.
            current[str(key)[:60]] = "1" if value else "0"
        else:
            current[str(key)[:60]] = "" if value is None else str(value)[:400]
    conf[pid] = current
    data["config"] = conf
    return _save(data)


def reset() -> dict:
    return _save(_default_state())


# --------------------------------------------------------------------------- #
# выдача для интерфейса
# --------------------------------------------------------------------------- #
def _ready(plugin: dict) -> tuple[bool, str]:
    """Готов ли плагин к работе: заполнены ли обязательные настройки."""
    required = [f for f in plugin["settings"]
                if f.get("required", True) and f.get("type") != "checkbox"]
    if not required:
        return True, ""
    conf = config(plugin["id"])
    missing = [f["label"] for f in required if not (conf.get(f["key"]) or "").strip()]
    if missing:
        return False, "needs " + ", ".join(missing)
    return True, ""


def listing(ytdlp_ok: bool = True) -> dict:
    data = state()
    items = []
    for plugin in catalog():
        ready, note = _ready(plugin)
        conf = config(plugin["id"])
        items.append({
            **{k: v for k, v in plugin.items() if k != "settings"},
            # У флажков значение приходит в интерфейс уже булевым.
            "settings": [
                {**item,
                 "value": flag(plugin["id"], item["key"],
                               bool(item.get("default", False)))
                 if item.get("type") == "checkbox" else conf.get(item["key"], "")}
                for item in plugin["settings"]
            ],
            "installed": plugin["id"] in data["installed"],
            "enabled": enabled(plugin["id"]),
            "ready": ready and (ytdlp_ok or not plugin["needs_ytdlp"]),
            "note": note or ("" if ytdlp_ok or not plugin["needs_ytdlp"]
                             else "yt-dlp is unavailable"),
        })
    return {
        "plugins": items,
        "categories": [{"id": cid, "name": name} for cid, name in CATEGORIES],
        "installed_count": len(data["installed"]),
        "total": len(items),
    }
