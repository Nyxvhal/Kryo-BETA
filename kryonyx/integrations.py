"""
integrations.py — внешние сервисы, подключаемые пользователем.

Скробблеры (Last.fm, ListenBrainz, Maloja), «Сейчас играет» в
Discord и отправка трека в Mastodon. Каждая интеграция — это плагин из каталога
со своими полями; здесь живут подключение, проверка и отправка.

Discord работает напрямую через локальный IPC Rich Presence, без сторонних
пакетов: сокет discord-ipc-0 в профиле пользователя (Windows — именованный
канал), рукопожатие и SET_ACTIVITY.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import struct
import threading
import time
import uuid
from typing import Any

from . import extras, plugins

log = logging.getLogger(__name__)

# Идентификаторы интеграций = id плагинов в каталоге.
SCROBBLERS = ("lastfm", "listenbrainz", "maloja")
INTEGRATIONS = (*SCROBBLERS, "discord", "mastodon")

# Приложение Discord, под которым показывается статус. Имя и значок этого
# приложения видно в карточке. Это значение по умолчанию: в настройках
# плагина можно указать свой Application ID и подписать карточку как угодно.
DISCORD_APP_ID = "1554171655645827222"


def discord_app_id() -> str:
    """Application ID из настроек плагина, иначе встроенный.

    Discord принимает только числовой snowflake, поэтому всё лишнее (пробелы,
    случайно скопированная ссылка) отбрасываем: с мусором рукопожатие молча
    не проходит, и пользователь видит пустой профиль без объяснений.
    """
    raw = str(plugins.config("discord").get("app_id") or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits if 17 <= len(digits) <= 21 else DISCORD_APP_ID


def _line(value: Any, fallback: str, limit: int) -> str:
    """Строка для Rich Presence: Discord принимает только 2..128 символов.

    Односимвольное название («7», «X») раньше валило весь кадр, и в профиле
    оставалось голое «Играет в Kryo» без трека.
    """
    text = str(value or "").strip() or fallback
    if len(text) < 2:
        text = f"{text} "
    return text[:limit]


# --------------------------------------------------------------------------- #
# Discord Rich Presence
# --------------------------------------------------------------------------- #
class DiscordRPC:
    """Клиент Discord IPC: подключение, проверка рукопожатия, показ трека.

    Отличия от прошлой версии (всё это и ломало «Сейчас играет»):
      * ответ на рукопожатие действительно читается — соединение считается
        живым только после кадра READY, а не сразу после write();
      * ответы Discord постоянно вычитываются фоновой задачей, иначе канал
        переполняется и SET_ACTIVITY зависает;
      * большая картинка — обложка трека (ссылка https), а не ассет
        приложения, поэтому в профиле видно именно трек;
      * обновления притормаживаются: Discord режет частые SET_ACTIVITY.
    """

    OP_HANDSHAKE = 0
    OP_FRAME = 1
    OP_CLOSE = 2
    OP_PING = 3
    OP_PONG = 4

    # Discord принимает примерно 5 обновлений за 20 с. Держим этот лимит
    # «ведром токенов»: короткая серия (смена трека, старт после загрузки,
    # перемотка) уходит мгновенно, а средний темп остаётся в рамках.
    MIN_INTERVAL = 4.0          # период восстановления одного токена
    BURST = 4                   # сколько кадров подряд можно отправить сразу

    def __init__(self) -> None:
        self._reader: Any = None
        self._writer: Any = None
        self._pipe: Any = None            # Windows: файловый объект канала
        self._pump: asyncio.Task | None = None
        self.connected = False
        self.app_id = DISCORD_APP_ID
        self.user: str = ""
        self.last_error: str = ""
        self._lock = asyncio.Lock()
        self._last_sent = 0.0
        self._tokens = float(self.BURST)
        self._tokens_at = time.monotonic()
        self._last_payload: str = ""
        self._retry_after = 0.0
        self._flush: asyncio.Task | None = None
        self._waiters: dict[str, asyncio.Future] = {}
        self._degrade = 0            # сколько частей кадра пришлось убрать
        self._write_lock = threading.Lock()
        self._silent = 0             # сколько кадров подряд остались без ответа
        self.last_frame: dict | None = None     # что реально ушло в Discord
        self.last_answer: str = ""              # что Discord ответил
        self.last_frame_at: float = 0.0         # когда кадр приняли
        self.last_note: str = ""                # почему карточка снята

    # ------------------------------------------------------------- адреса --
    @staticmethod
    def _paths() -> list[str]:
        if os.name == "nt":
            # Раньше мы вслепую перебирали discord-ipc-0..9 и в логах оставалась
            # бесполезная ошибка от последнего имени. Теперь сначала смотрим,
            # какие каналы реально есть в системе.
            try:
                names = [n for n in os.listdir(r"\\.\pipe")
                         if "discord-ipc-" in n.lower()]
            except OSError:
                names = []
            if names:
                return [rf"\\.\pipe\{name}" for name in sorted(names)]
            return [rf"\\.\pipe\discord-ipc-{i}" for i in range(10)]
        base = (os.getenv("XDG_RUNTIME_DIR") or os.getenv("TMPDIR")
                or os.getenv("TMP") or "/tmp").rstrip("/")
        roots = [base, f"{base}/app/com.discordapp.Discord",
                 f"{base}/app/com.discordapp.DiscordCanary",
                 f"{base}/snap.discord-canary", f"{base}/snap.discord",
                 f"{base}/.flatpak/dev.vencord.Vesktop/xdg-run"]
        return [f"{root}/discord-ipc-{i}" for root in roots for i in range(10)]

    # ----------------------------------------------------------- передача --
    def _pack(self, op: int, payload: dict) -> bytes:
        data = json.dumps(payload).encode("utf-8")
        return struct.pack("<II", op, len(data)) + data

    async def _send(self, op: int, payload: dict) -> None:
        packet = self._pack(op, payload)
        if self._writer is not None:
            self._writer.write(packet)
            await self._writer.drain()
        elif self._pipe is not None:
            def write() -> None:
                with self._write_lock:
                    self._pipe.write(packet)
                    self._pipe.flush()
            await asyncio.to_thread(write)
        else:
            raise RuntimeError("Discord IPC is not connected")

    async def _read_frame(self, timeout: float | None = 4.0) -> tuple[int, dict]:
        """Один кадр от Discord. Нужен и для READY, и для очистки канала.

        timeout=None — ждать сколько угодно: так читает фоновый насос, ему
        обрывать чтение по таймеру нельзя (можно порвать кадр пополам).
        """
        if self._reader is not None:
            if timeout is None:
                head = await self._reader.readexactly(8)
                op, size = struct.unpack("<II", head)
                body = await self._reader.readexactly(size) if size else b""
                return op, self._decode(body)
            head = await asyncio.wait_for(self._reader.readexactly(8), timeout)
            op, size = struct.unpack("<II", head)
            body = await asyncio.wait_for(self._reader.readexactly(size), timeout) if size else b""
        elif self._pipe is not None:
            head = await asyncio.wait_for(
                asyncio.to_thread(self._read_exact, 8), timeout)
            op, size = struct.unpack("<II", head)
            body = await asyncio.wait_for(
                asyncio.to_thread(self._read_exact, size), timeout) if size else b""
        else:
            raise RuntimeError("Discord IPC is not connected")
        return op, self._decode(body)

    @staticmethod
    def _decode(body: bytes) -> dict:
        try:
            data = json.loads(body.decode("utf-8", "replace")) if body else {}
        except Exception:
            data = {}
        return data if isinstance(data, dict) else {}

    def _read_exact(self, size: int) -> bytes:
        """Канал Windows может отдать кусок меньше запрошенного — добираем."""
        buf = b""
        while len(buf) < size:
            chunk = self._pipe.read(size - len(buf))
            if not chunk:
                raise RuntimeError("Discord closed the pipe")
            buf += chunk
        return buf

    def _win_roundtrip(self, packet: bytes, nonce: str,
                       timeout: float) -> dict | None:
        """Windows: пишем кадр и тут же читаем ответ по тому же дескриптору.

        Возвращает ответ Discord, None — если ответа с нашим nonce не было.
        """
        pipe = self._pipe
        if pipe is None:
            raise RuntimeError("Discord IPC is not connected")
        with self._write_lock:
            pipe.write(packet)
            pipe.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                head = self._read_exact(8)
                op, size = struct.unpack("<II", head)
                data = self._decode(self._read_exact(size) if size else b"")
                if op == self.OP_PING:
                    pipe.write(self._pack(self.OP_PONG, data))
                    pipe.flush()
                    continue
                if op == self.OP_CLOSE:
                    raise RuntimeError(str(data.get("message") or "closed"))
                if not nonce or data.get("nonce") == nonce:
                    return data
                # чужой кадр (например, событие) — читаем дальше
            return None

    async def _exchange(self, payload: dict, nonce: str) -> dict | None:
        """Отправить кадр и получить ответ. None — ответа не было."""
        if self._pipe is not None:
            return await asyncio.to_thread(
                self._win_roundtrip, self._pack(self.OP_FRAME, payload), nonce, 3.0)
        waiter: asyncio.Future = asyncio.get_running_loop().create_future()
        self._waiters[nonce] = waiter
        await self._send(self.OP_FRAME, payload)
        try:
            return await asyncio.wait_for(waiter, 2.5)
        except asyncio.TimeoutError:
            self._waiters.pop(nonce, None)
            return None

    async def _pump_loop(self) -> None:
        """Вычитывает ответы Discord, иначе канал забивается и запись встаёт."""
        try:
            while self.connected:
                op, data = await self._read_frame(timeout=None)

                if op == self.OP_PING:
                    await self._send(self.OP_PONG, data)
                elif op == self.OP_CLOSE:
                    raise RuntimeError(str(data.get("message") or "closed"))
                else:
                    # Ответ на наш SET_ACTIVITY приходит с тем же nonce —
                    # раньше он просто выбрасывался, и мы не знали, что
                    # Discord отверг кадр.
                    waiter = self._waiters.pop(str(data.get("nonce") or ""), None)
                    if waiter is not None and not waiter.done():
                        waiter.set_result(data)
                    if data.get("evt") == "ERROR":
                        log.debug("[discord] frame error: %s", data.get("data"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("[discord] connection lost: %s", exc)
            self.connected = False
            await self.close()

    async def connect(self, app_id: str = "") -> bool:
        wanted = (app_id or "").strip() or discord_app_id()
        async with self._lock:
            if self.connected:
                # Пользователь сменил Application ID — старое соединение
                # держит прошлое приложение, поэтому переподключаемся.
                if wanted == self.app_id:
                    return True
                log.info("[discord] application id changed: %s -> %s",
                         self.app_id, wanted)
                await self.close()
                self._retry_after = 0.0
            if time.monotonic() < self._retry_after:
                return False
            self.app_id = wanted
            for path in self._paths():
                try:
                    if os.name == "nt":
                        self._pipe = await asyncio.to_thread(open, path, "r+b", 0)
                    else:
                        if not os.path.exists(path):
                            continue
                        self._reader, self._writer = await asyncio.open_unix_connection(path)
                    await self._send(self.OP_HANDSHAKE,
                                     {"v": 1, "client_id": str(self.app_id)})
                    op, data = await self._read_frame(timeout=5)
                    if data.get("evt") != "READY":
                        raise RuntimeError(str(data.get("message")
                                               or data.get("data") or "no READY"))
                    user = ((data.get("data") or {}).get("user") or {})
                    self.user = str(user.get("username") or user.get("global_name") or "")
                    self.connected = True
                    self.last_error = ""
                    self._last_payload = ""
                    self._degrade = 0
                    self._waiters.clear()
                    self._silent = 0
                    # На Windows канал открыт синхронно: висящий read блокирует
                    # write по тому же дескриптору, и первая же отправка
                    # SET_ACTIVITY зависала навсегда. Поэтому там работаем
                    # строго «запрос — ответ», без фонового чтения.
                    if self._pipe is None:
                        self._pump = asyncio.create_task(self._pump_loop())
                    log.info("[discord] connected via %s%s", path,
                             f" как {self.user}" if self.user else "")
                    return True
                except Exception as exc:
                    self.last_error = str(exc)
                    await self.close()
                    continue
            # Discord не запущен — не дёргаем канал на каждом треке.
            self._retry_after = time.monotonic() + 20
            self.last_error = self._explain(self.last_error)
            log.info("[discord] %s", self.last_error)
            return False

    @staticmethod
    def _explain(error: str) -> str:
        """Человеческая причина вместо «No such file or directory: ipc-9»."""
        text = (error or "").lower()
        if not error or "no such file" in text or "errno 2" in text \
                or "cannot find the file" in text or "не удается найти" in text:
            return ("Discord is not running (its local channel was not found). "
                    "Open the Discord desktop app — the browser version has no "
                    "Rich Presence.")
        if "permission" in text or "access is denied" in text or "errno 13" in text:
            return ("Discord refused the connection: it is running with "
                    "different rights. Start Discord and the player the same "
                    "way — both as a normal user or both as administrator.")
        if "no ready" in text or "invalid client" in text or "4000" in text:
            return ("Discord did not accept the handshake. Restart the Discord "
                    "desktop app and try again.")
        return error

    # ------------------------------------------------------------ картинки -
    @staticmethod
    def _artwork(track: dict) -> str:
        """Ссылка на обложку трека. Discord сам подтягивает внешние https-картинки."""
        thumb = str(track.get("thumbnail") or "").strip()
        if not thumb.startswith("http"):
            return ""
        # Квадратные обложки YouTube Music приятнее вытянутых кадров видео.
        if "lh3.googleusercontent.com" in thumb or "ytimg.com/ytc" in thumb:
            thumb = re.sub(r"=w\d+-h\d+", "=w600-h600", thumb)
        elif "i.ytimg.com/vi/" in thumb:
            # hqdefault есть у любого видео, в отличие от maxres/hq720.
            thumb = re.sub(r"/(?:default|mqdefault|sddefault)\.jpg",
                           "/hqdefault.jpg", thumb)
        return thumb[:480]

    @staticmethod
    def _track_url(track: dict) -> str:
        """Ссылка на трек у источника — для кнопки под карточкой.

        В очереди у трека хранится только id источника, готовой ссылки там
        обычно нет, поэтому для YouTube она собирается из id.
        """
        given = str(track.get("url") or track.get("webpage_url") or "").strip()
        if given.startswith("http"):
            return given
        ident = str(track.get("id") or "").strip()
        source = str(track.get("source") or "").strip().lower()
        if ident and source in ("", "youtube", "ytmusic"):
            return f"https://www.youtube.com/watch?v={ident}"
        return ""

    def _activity(self, track: dict, position: float, paused: bool,
                  loading: bool = False, speed: float = 1.0,
                  duration: float = 0.0) -> dict:
        """Карточка в стиле Spotify: обложка, трек, «by …», «on …», прогресс.

        Discord рисует строки так: details — первая, state — вторая, а
        timestamps.start/end дают полосу времени «прошло / всего». Обложка
        берётся с трека (assets.large_image), а не с приложения, иначе в
        профиле висел бы логотип плеера.
        """
        conf = plugins.config("discord")
        # Длительность из самого аудио точнее карточки поиска: у части треков
        # (SoundCloud, радиозаписи, длинные загрузки) метаданных просто нет,
        # и без неё Discord рисует голый счётчик вместо полосы времени.
        duration = int(duration or track.get("duration") or 0)
        title = _line(track.get("title"), "Unknown track", 120)
        artist = _line(track.get("artist"), "Unknown artist", 110)
        album = str(track.get("album") or "").strip()

        show_cover = plugins.flag("discord", "show_cover", True)
        show_album = plugins.flag("discord", "show_album", True)
        show_time = plugins.flag("discord", "show_time", True)

        # Подстановки для пользовательских шаблонов строк и кнопки.
        slots = {
            "title": title,
            "artist": artist,
            "album": album,
            "source": str(track.get("source") or "").strip(),
            "app": "Kryo",
            "url": self._track_url(track),
        }

        def fill(template: str) -> str:
            """Шаблон вида «{title} — {artist}». Неизвестные поля остаются
            пустыми, лишние разделители по краям убираются: иначе строка
            «{title} · {album}» у сингла без альбома кончалась точкой."""
            out = template
            for name, value in slots.items():
                out = out.replace("{" + name + "}", value)
            out = re.sub(r"\s*[·\-–—|]\s*$", "", out.strip())
            out = re.sub(r"^\s*[·\-–—|]\s*", "", out)
            return re.sub(r"\s{2,}", " ", out).strip()

        art = self._artwork(track) if show_cover else ""
        assets: dict[str, Any] = {}
        if art:
            assets["large_image"] = art
            # Подписи обложки больше нет совсем: Discord рисует её третьей
            # строкой карточки, а у большинства треков альбом называется так
            # же, как сам трек, — выходило «Babydoll», «Dominic Fike»,
            # «on Babydoll». Альбом теперь уходит во вторую строку, и только
            # когда он действительно другой.
        elif show_cover:
            # Обложки нет — тогда уж логотип приложения.
            assets["large_image"] = (conf.get("large_image") or "kryonyx")
            assets["large_text"] = "Kryo"
        # Подпись обложки задаётся шаблоном и по умолчанию отсутствует:
        # Discord рисует её третьей строкой, и у синглов выходило
        # «Babydoll / Dominic Fike / on Babydoll».
        caption = fill(str(conf.get("large_text") or ""))
        if caption and "large_image" in assets:
            assets["large_text"] = _line(caption, caption, 128)
        small = (conf.get("small_image") or "").strip()
        if small:
            assets["small_image"] = small
        if paused:
            assets["small_text"] = _line(fill(str(conf.get("paused_text") or ""))
                                         or "Paused", "Paused", 128)
        elif loading:
            assets["small_text"] = "Loading"

        # Как в карточке Spotify: первая строка — название трека, вторая —
        # только исполнители, без приставки «by». Альбом своей строки не имеет
        # (её занимает полоса времени), поэтому он живёт в подписи обложки.
        state = artist
        # Альбом дописываем к исполнителю, но не когда он повторяет название
        # трека: у синглов это сплошь «Babydoll · Babydoll».
        if album and show_album and album.casefold() != title.casefold():
            state = f"{state} · {album}"
        # Свои шаблоны перебивают обе строки целиком.
        details = fill(str(conf.get("line1") or "")) or title
        custom_state = fill(str(conf.get("line2") or ""))
        if custom_state:
            state = custom_state

        # Тип активности: «Слушает», «Играет», «Смотрит», «Соревнуется».
        kinds = {"playing": 0, "listening": 2, "watching": 3, "competing": 5}
        kind = kinds.get(str(conf.get("activity_type") or "listening").strip().lower(), 2)

        # ВАЖНО: в IPC SET_ACTIVITY кладём только те поля, которые точно
        # понимает десктопный клиент. Новые поля REST-API (status_display_type,
        # details_url) Discord здесь отвергает — и тогда карточка приходит
        # пустой: «Играет в Kryo» вообще без названия трека.
        activity: dict[str, Any] = {
            "type": kind,
            "details": _line(details, title, 128),
            "state": _line(state, artist, 128),
            "instance": False,
        }
        if assets:
            activity["assets"] = assets

        # Время в IPC SET_ACTIVITY — в миллисекундах эпохи. Именно так шлёт
        # Spotify: округление до целых секунд давало расхождение полосы
        # почти на секунду и выглядело как «отставание» от плеера.
        # На паузе и во время загрузки таймстемпы убираем — иначе полоса
        # ехала бы там, где звука ещё нет.
        if show_time and not paused and not loading:
            # Скорость воспроизведения: на 1.25x трек звучит на четверть
            # меньше реального времени, поэтому и полоса должна идти по
            # реальным секундам, иначе она отстаёт или убегает.
            rate = speed if speed and speed > 0 else 1.0
            start = (time.time() - max(0.0, position) / rate) * 1000.0
            if duration:
                activity["timestamps"] = {"start": round(start),
                                          "end": round(start + duration * 1000 / rate)}
            else:
                activity["timestamps"] = {"start": round(start)}

        # Кнопка под карточкой: по умолчанию её нет (вид «как у Spotify»),
        # но теперь её можно включить и подписать самому.
        if plugins.flag("discord", "show_button", False):
            link = fill(str(conf.get("button_url") or "{url}"))
            label = fill(str(conf.get("button_label") or "")) or "Listen"
            if link.startswith("http://") or link.startswith("https://"):
                activity["buttons"] = [{"label": label[:31], "url": link[:512]}]
        return activity

    @staticmethod
    def _simplify(activity: dict, step: int) -> dict:
        """Если Discord отверг кадр, убираем по одной «необязательной» части.

        Порядок такой же, как частота проблем: сначала обложка по ссылке (её
        принимают не все сборки), потом полоса времени, потом остаётся голый
        «Слушает: трек — исполнитель».
        """
        light = dict(activity)
        light.pop("buttons", None)
        if step >= 1:
            light.pop("assets", None)
        if step >= 2:
            light.pop("timestamps", None)
        if step >= 3:
            # Совсем старые сборки не знают type=2 («Слушает») и отвергают
            # кадр целиком. Лучше «Играет в …», но с названием трека.
            light.pop("type", None)
        return light

    async def set_activity(self, track: dict | None, position: float = 0.0,
                           paused: bool = False, *, force: bool = False,
                           loading: bool = False, speed: float = 1.0,
                           duration: float = 0.0) -> bool:
        # Ключ берём из настроек на каждом кадре: поменяли — переподключимся.
        if not await self.connect(discord_app_id()):
            return False

        # «Скрывать статус на паузе» — карточка просто снимается.
        if track is None:
            activity = None
            self.last_note = "no track is playing"
        elif paused and plugins.flag("discord", "hide_paused", False):
            activity = None
            # Именно здесь профиль пустеет, и Discord показывает вместо
            # карточки свою «обнаруженную игру» — пишем это прямо в статус.
            self.last_note = ("the card is hidden while paused "
                              "(the 'Hide the status while paused' switch)")
        else:
            activity = self._activity(track, position, paused, loading, speed,
                                      duration)
            self.last_note = "the track is still loading" if loading else ""

        # Признак состояния без «ползущего» времени: одинаковые кадры не шлём,
        # а частые — придерживаем, иначе Discord обрывает соединение.
        signature = json.dumps(
            [None if activity is None else
             [activity["details"], activity["state"], paused,
              (activity.get("assets") or {}).get("large_image"),
              bool((activity.get("timestamps") or {}).get("end")),
              bool(activity.get("timestamps")), loading, round(speed, 3),
              int(duration or 0)]],
            ensure_ascii=False)
        now = time.monotonic()
        # Пустой кадр повторять вообще незачем: раньше в журнал каждую минуту
        # капало «activity sent: cleared», хотя ничего не играло.
        if activity is None and signature == self._last_payload and not force:
            return True
        if not force and signature == self._last_payload and now - self._last_sent < 60:
            return True
        # Discord режет частые SET_ACTIVITY, поэтому кадр не выбрасываем, а
        # досылаем, когда пройдёт минимальный интервал: статус не «залипает»
        # на прошлом треке при быстрых переключениях и перемотке.
        # Копим токены со временем; пока они есть, кадр уходит без задержки.
        self._tokens = min(float(self.BURST),
                           self._tokens + (now - self._tokens_at) / self.MIN_INTERVAL)
        self._tokens_at = now
        if self._tokens < 1.0:
            # Лимит исчерпан: досылаем, как только накопится токен. Позиция
            # к тому моменту пересчитывается заново, так что полоса времени
            # не «отстаёт» — просто обновление приходит чуть позже.
            self._defer((1.0 - self._tokens) * self.MIN_INTERVAL + 0.05)
            return True
        self._tokens -= 1.0

        # Отправляем и ждём ответ: если клиент кадр не принял, пробуем тот же
        # кадр попроще, пока не останется «Слушает: трек — исполнитель».
        for step in range(self._degrade, 4):
            frame = activity if activity is None else self._simplify(activity, step)
            nonce = str(uuid.uuid4())
            payload = {"cmd": "SET_ACTIVITY", "nonce": nonce,
                       "args": {"pid": os.getpid(), "activity": frame}}
            try:
                answer = await asyncio.wait_for(self._exchange(payload, nonce), 6.0)
            except Exception as exc:
                self._waiters.pop(nonce, None)
                log.info("[discord] send failed: %s", exc)
                self.last_error = str(exc)
                await self.close()
                return False

            if answer is None:
                # Клиент промолчал. Пару раз это нормально, но если молчание
                # повторяется — кадр до него не доходит, пробуем проще.
                self._silent += 1
                answer = {}
                if self._silent >= 3 and step < 3:
                    log.info("[discord] no answer for %s frames, simplifying",
                             self._silent)
                    self._silent = 0
                    continue
            else:
                self._silent = 0

            self.last_frame = frame
            self.last_frame_at = time.time()
            self.last_answer = json.dumps(answer, ensure_ascii=False)[:300]
            if answer.get("evt") != "ERROR":
                log.info("[discord] activity sent: %s",
                         json.dumps(frame, ensure_ascii=False)[:300]
                         if frame else "cleared")
                if step and step != self._degrade:
                    log.info("[discord] the card was simplified (step %s): "
                             "the client did not accept some fields", step)
                self._degrade = step
                self._last_sent = now
                self._last_payload = signature
                self.last_error = ""
                return True

            reason = ((answer.get("data") or {}).get("message")
                      or answer.get("data") or "rejected")
            log.info("[discord] the card was rejected (%s), trying a simpler one", reason)
            self.last_error = str(reason)
            if activity is None:
                return False
        return False

    def _defer(self, delay: float) -> None:
        """Досылает актуальный кадр после паузы, если сейчас нельзя отправить."""
        if self._flush is not None and not self._flush.done():
            return

        async def run() -> None:
            try:
                await asyncio.sleep(max(0.05, delay))
                # Снимаем метку до отправки, чтобы следующий кадр снова
                # мог встать в очередь, пока этот ещё уходит.
                self._flush = None
                await refresh_presence()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("[discord] deferred update failed: %s", exc)

        try:
            self._flush = asyncio.create_task(run())
        except RuntimeError:
            self._flush = None

    def summary(self) -> str:
        """Что сейчас реально видно в профиле — одной строкой для настроек."""
        if not self.connected:
            return ""
        if not self.last_frame_at:
            return "connected, no card has been sent yet"
        ago = max(0, int(time.time() - self.last_frame_at))
        frame = self.last_frame
        if not frame:
            return f"the card was removed {ago} s ago" + (
                f": {self.last_note}" if self.last_note else "")
        kind = "Listening to" if frame.get("type") == 2 else "Playing"
        parts = [f"{kind}: {frame.get('details', '')} — {frame.get('state', '')}"]
        if frame.get("assets"):
            parts.append("artwork")
        if frame.get("timestamps"):
            parts.append("progress bar")
        return f"the card was sent {ago} s ago · " + " · ".join(parts)

    async def close(self) -> None:
        self.connected = False
        flush, self._flush = self._flush, None
        if flush is not None and not flush.done():
            flush.cancel()
        pump, self._pump = self._pump, None
        if pump is not None and not pump.done():
            pump.cancel()
        try:
            if self._writer is not None:
                self._writer.close()
        except Exception:
            pass
        try:
            if self._pipe is not None:
                self._pipe.close()
        except Exception:
            pass
        self._reader = self._writer = self._pipe = None


discord = DiscordRPC()


# --------------------------------------------------------------------------- #
# Mastodon
# --------------------------------------------------------------------------- #
async def mastodon_share(track: dict, text: str = "") -> dict:
    conf = plugins.config("mastodon")
    host = (conf.get("url") or "").strip().rstrip("/")
    token = (conf.get("token") or "").strip()
    if not host or not token:
        raise RuntimeError("Mastodon: server address and token are required")
    body = text or (f"🎧 Now playing: {track.get('artist', '')} — "
                    f"{track.get('title', '')}\n#nowplaying #Kryo")
    session = await extras.library.http()
    async with session.post(
        f"{host}/api/v1/statuses",
        json={"status": body[:480], "visibility": conf.get("visibility") or "public"},
        headers={"Authorization": f"Bearer {token}"},
    ) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Mastodon HTTP {resp.status}")
        data = await resp.json(content_type=None)
    return {"url": (data or {}).get("url")}


# --------------------------------------------------------------------------- #
# «сейчас играет»
# --------------------------------------------------------------------------- #
_last_state: tuple = ()
# Последний кадр: нужен, чтобы применить настройки сразу и поймать перемотку.
_last: dict = {"track": None, "position": 0.0, "paused": False, "at": 0.0,
               "loading": False, "speed": 1.0, "duration": 0.0}

# Насколько позиция может уехать от ожидаемой, прежде чем считать это перемоткой.
SEEK_TOLERANCE = 2.5


def _seeked(position: float, paused: bool) -> bool:
    """Перемотка = позиция не совпала с той, что должна была натикать сама."""
    if not _last["track"] or not _last["at"]:
        return False
    elapsed = 0.0 if _last["paused"] else max(0.0, time.time() - _last["at"])
    # За реальную секунду на 1.5x проигрывается полторы секунды трека.
    expected = float(_last["position"]) + elapsed * float(_last.get("speed") or 1.0)
    return abs(position - expected) > SEEK_TOLERANCE


# Длительности, которые плеер уже успел узнать. Первые кадры трека уходят с
# duration=0 (браузер ещё не раскодировал заголовок), и если потом опять
# придёт ноль — например, кадр собрали в момент переключения источника, —
# Discord потеряет полосу времени и покажет голый счётчик «♪ 0:03». Поэтому
# длительность помним по id трека и больше не теряем.
_durations: dict[str, float] = {}


def _keep_duration(track_id: str, duration: float) -> float:
    """Запомнить длительность трека и подставить её вместо нуля."""
    if not track_id:
        return duration
    if duration > 0:
        _durations[track_id] = duration
        # Словарь не должен расти бесконечно: храним только свежие треки.
        while len(_durations) > 256:
            _durations.pop(next(iter(_durations)))
        return duration
    return float(_durations.get(track_id) or 0.0)


async def now_playing(track: dict | None, position: float = 0.0,
                      paused: bool = False, loading: bool = False,
                      speed: float = 1.0, duration: float = 0.0) -> list[str]:
    global _last_state
    done: list[str] = []
    duration = _keep_duration(str((track or {}).get("id") or ""),
                              float(duration or 0))
    # Длительность входит в состояние: как только плеер её узнал, карточку
    # надо перерисовать — иначе полоса времени так и не появится.
    state = ((track or {}).get("id"), bool(paused), bool(loading), round(speed, 3),
             int(duration or 0))
    # Смена трека, пауза и перемотка — это новый кадр: без force Discord не
    # перерисует полосу времени, потому что текст остался тем же.
    changed = state != _last_state or _seeked(position, paused)
    _last_state = state
    _last.update(track=track, position=float(position or 0),
                 paused=bool(paused), at=time.time(),
                 loading=bool(loading), speed=float(speed or 1.0),
                 duration=float(duration or 0))
    if plugins.enabled("discord"):
        # Отдельная страховка: сбой статуса не должен ронять весь запрос
        # «сейчас играет» — скробблинг обязан отработать в любом случае.
        try:
            if await discord.set_activity(track, position, paused,
                                          force=changed, loading=loading,
                                          speed=speed, duration=duration):
                done.append("discord")
        except Exception as exc:
            log.info("[discord] status update failed: %s", exc)
    if changed:
        # По этой строке в журнале сразу видно, доходит ли до сервера смена
        # трека и берёт ли её Discord.
        log.info("[nowplaying] %s — %s | paused=%s | sent: %s",
                 (track or {}).get("artist", "—"), (track or {}).get("title", "—"),
                 paused, ", ".join(done) or "nobody")
    if track and plugins.enabled("lastfm"):
        try:
            if await extras.lastfm_now_playing(track):
                done.append("lastfm")
        except Exception as exc:
            log.debug("[lastfm] now playing: %s", exc)
    return done


async def refresh_presence() -> bool:
    """Перерисовать карточку Discord по текущим настройкам, без перезапуска.

    Вызывается сразу после сохранения настроек плагина: пользователь щёлкает
    переключатель и видит новый статус, не трогая воспроизведение.
    """
    track = _last["track"]
    if not plugins.enabled("discord"):
        # Плагин выключили — снимаем статус.
        if discord.connected:
            await discord.set_activity(None, force=True)
        return False
    if not track:
        return False
    position = float(_last["position"] or 0)
    speed = float(_last.get("speed") or 1.0)
    if not _last["paused"]:
        position += max(0.0, time.time() - float(_last["at"] or time.time())) * speed
    return await discord.set_activity(track, position, bool(_last["paused"]),
                                      force=True, loading=bool(_last.get("loading")),
                                      speed=speed,
                                      duration=float(_last.get("duration") or 0))


# --------------------------------------------------------------------------- #
# фоновое удержание статуса
# --------------------------------------------------------------------------- #
_keeper: asyncio.Task | None = None


async def _keeper_loop() -> None:
    """Раз в 15 с восстанавливает статус, если Discord запустили позже плеера.

    Раньше кадр уходил только по событиям плеера: включил музыку, потом
    открыл Discord — и в профиле пусто до следующего трека.
    """
    while True:
        await asyncio.sleep(15)
        try:
            if plugins.enabled("discord") and _last["track"] and not discord.connected:
                await refresh_presence()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("[discord] keeper: %s", exc)


def start_keeper() -> None:
    global _keeper
    if _keeper is None or _keeper.done():
        _keeper = asyncio.create_task(_keeper_loop())


async def stop_keeper() -> None:
    global _keeper
    task, _keeper = _keeper, None
    if task is not None and not task.done():
        task.cancel()
    await discord.close()


# --------------------------------------------------------------------------- #
# проверка подключения
# --------------------------------------------------------------------------- #
async def test(pid: str) -> dict:
    """Проверяет, что интеграция настроена и сервис отвечает."""
    conf = plugins.config(pid)
    if pid == "discord":
        discord._retry_after = 0.0
        app_id = discord_app_id()
        okay = await discord.connect(app_id)
        if not okay:
            return {"ok": False,
                    "message": discord.last_error or "Discord is not running"}
        if app_id != DISCORD_APP_ID:
            log.info("[discord] test with your own application %s", app_id)
        # Рукопожатие ещё ничего не доказывает: раньше проверка говорила
        # «подключено», а карточки в профиле не было. Теперь она реально
        # ставит кадр — текущий трек или демонстрационный.
        demo = _last["track"] or {"title": "Kryo", "artist": "Test card",
                                  "duration": 180}
        shown = await discord.set_activity(demo, 0.0, False, force=True)
        if not shown:
            return {"ok": False,
                    "message": discord.last_error
                    or "Discord did not accept the card"}
        who = f" as {discord.user}" if discord.user else ""
        return {"ok": True, "message": f"Connected{who}, the card is set"}

    if pid == "mastodon":
        host = (conf.get("url") or "").strip().rstrip("/")
        token = (conf.get("token") or "").strip()
        if not host or not token:
            return {"ok": False, "message": "Server address and token are required"}
        session = await extras.library.http()
        async with session.get(f"{host}/api/v1/accounts/verify_credentials",
                               headers={"Authorization": f"Bearer {token}"}) as resp:
            if resp.status >= 300:
                return {"ok": False, "message": f"HTTP {resp.status}"}
            data = await resp.json(content_type=None)
        return {"ok": True, "message": "@" + str((data or {}).get("acct") or "")}

    if pid == "listenbrainz":
        token = (conf.get("token") or "").strip()
        if not token:
            return {"ok": False, "message": "A token is required"}
        session = await extras.library.http()
        async with session.get("https://api.listenbrainz.org/1/validate-token",
                               headers={"Authorization": f"Token {token}"}) as resp:
            data = await resp.json(content_type=None) if resp.status < 400 else {}
        valid = bool((data or {}).get("valid"))
        return {"ok": valid,
                "message": (data or {}).get("user_name") or "Token was rejected"}

    if pid == "maloja":
        host = (conf.get("url") or "").strip().rstrip("/")
        if not host:
            return {"ok": False, "message": "A server address is required"}
        session = await extras.library.http()
        async with session.get(f"{host}/apis/mlj_1/serverinfo") as resp:
            okay = resp.status < 300
        return {"ok": okay, "message": "The server answers" if okay else "The server is silent"}

    if pid == "lastfm":
        conf_ok = all((conf.get("api_key"), conf.get("secret"), conf.get("session")))
        return {"ok": conf_ok,
                "message": "Keys are in place" if conf_ok else "Key, secret and session are required"}

    return {"ok": False, "message": "Unknown integration"}


def status() -> list[dict]:
    out = []
    for pid in INTEGRATIONS:
        plugin = plugins.BY_ID.get(pid)
        if not plugin:
            continue
        conf = plugins.config(pid)
        out.append({
            "id": pid,
            "name": plugin["name"],
            "author": plugin["author"],
            "installed": plugins.installed(pid),
            "enabled": plugins.enabled(pid),
            # Флажки не считаем «настройкой»: у них всегда есть значение.
            "configured": any((conf.get(f["key"]) or "").strip()
                              for f in plugin["settings"]
                              if f.get("type") != "checkbox")
            if [f for f in plugin["settings"] if f.get("type") != "checkbox"] else True,
            "kind": "scrobbling" if pid in SCROBBLERS else "integration",
            "live": discord.connected if pid == "discord" else None,
            "account": discord.user if pid == "discord" else None,
            "error": (discord.last_error if pid == "discord"
                      and not discord.connected else None),
            # Живая подсказка: что именно ушло в Discord последним кадром.
            "note": discord.summary() if pid == "discord" else None,
        })
    return out
