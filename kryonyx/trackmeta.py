"""Conservative display cleanup. Playback identifiers and version labels stay intact."""
import html
import re
import unicodedata

_PROMO = re.compile(
    r"\s*[\[(](?:official\s+(?:music\s+)?(?:video|audio|lyric(?:s)?(?:\s+video)?|visuali[sz]er)|"
    r"(?:official\s+)?lyrics?\s+video|music\s+video|visuali[sz]er|official|m/?v|"
    r"премьера(?:\s+(?:клипа|трека|песни))?|video\s*klip|официальн(?:ое|ый)\s+(?:видео|клип)|4k|8k|hd)"
    r"(?:\s*[,/|-]?\s*(?:19|20)\d\d)?[\])]",
    re.I,
)
# «Артист, Гость – Песня» у клипа: префикс снимаем, только если он начинается
# с уже указанного исполнителя (имя не угадываем по названию).
_CREDIT_JOIN = re.compile(r"\s*(?:,|&|\+|\bx\b|\bfeat\.?|\bft\.?|\bfeaturing\b)\s*", re.I)
def text(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", html.unescape(str(value or "")))).strip()
def clean_track(track):
    out = dict(track)
    artist = text(track.get("artist"))
    title = text(track.get("title"))
    original = track.get("title")
    if artist:
        for sep in (" — ", " – ", " - "):
            prefix = artist + sep
            if title.casefold().startswith(prefix.casefold()):
                title = title[len(prefix):].strip()
                break
        else:
            for sep in (" — ", " – ", " - "):
                if sep not in title:
                    continue
                left, right = title.split(sep, 1)
                head = left.casefold()
                name = artist.casefold()
                if right.strip() and head.startswith(name) and len(left) <= 80 \
                        and _CREDIT_JOIN.match(left[len(artist):] or "x"):
                    title = right.strip()
                    break
    title = _PROMO.sub("", title).strip(" |") or text(original)
    if title != original:
        out.setdefault("original_title", original)
    out["title"], out["artist"] = title, artist
    return out


def artist_name_key(value):
    """Compare complete credited names, never substrings or song titles."""
    value = text(value).casefold()
    value = re.sub(r"\s*[-–—]\s*(?:topic|official(?:\s+(?:artist|channel))?)$", "", value)
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).strip()


def artist_profile_key(value):
    """Stable identity for supported provider profile URLs, ignoring query/tab."""
    from urllib.parse import urlparse, unquote
    try:
        parsed = urlparse(str(value or ""))
        host = (parsed.hostname or "").casefold()
        parts = [unquote(p) for p in parsed.path.split("/") if p]
        if host in {"youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"}:
            if len(parts) >= 2 and parts[0] == "channel":
                return ("youtube-channel", parts[1])  # channel IDs are case-sensitive
            if parts and parts[0].startswith("@"):
                return ("youtube-handle", parts[0].casefold())
        if host in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com"} and parts:
            return ("soundcloud", parts[0].casefold())
        if host == "open.spotify.com" and len(parts) >= 2 and parts[0] == "artist":
            return ("spotify", parts[1])
    except (ValueError, TypeError):
        pass
    return None


def artist_track_matches(track, name, profile_url=None, *, from_profile=False):
    """Accept credited collaborators, but never fill an artist page with recommendations.

    A direct profile endpoint is authoritative when it omits track credits.
    Search results require an exact credit or matching provider profile identity.
    When a stable identity conflicts, a same-name search hit is not enough.
    """
    target = artist_name_key(name)
    identity = artist_profile_key(profile_url)
    people = track.get("artists") or []
    if isinstance(people, dict):
        people = [people]
    people = [p for p in people if isinstance(p, dict)]
    refs = [artist_profile_key(p.get("url")) for p in people]
    owner = artist_profile_key(track.get("author_url"))
    if owner:
        refs.append(owner)
    author_id = str(track.get("author_id") or "")
    if author_id.startswith("UC"):
        refs.append(("youtube-channel", author_id))
    refs = [ref for ref in refs if ref]
    if identity and identity in refs:
        return True
    # Only comparable identities establish a conflict (handle and UC id may
    # refer to the same channel, but cannot be resolved offline).
    if identity and any(ref[0] == identity[0] for ref in refs):
        return False
    names = [artist_name_key(p.get("name")) for p in people if p.get("name")]
    credit = artist_name_key(track.get("artist"))
    if target and (target in names or target == credit):
        return True
    if target and not names:
        # Legacy flattened collaborator fields; never split structured band names.
        legacy = re.split(r"\s+(?:feat\.?|ft\.?|featuring|with|x)\s+|\s*[,;&]\s*", text(track.get("artist")), flags=re.I)
        if target in [artist_name_key(n) for n in legacy]:
            return True
    return bool(from_profile and not refs and not names and not credit)
