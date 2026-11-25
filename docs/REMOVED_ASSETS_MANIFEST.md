# Removed Assets Manifest

This manifest records the avatar catalog cleanup performed on `kryonyx/avatars.json`, `kryonyx/web/img/avatars/`, and `kryonyx/avatar-notices/`.

## Summary Counts

| Metric | Before | Removed | After |
| --- | ---: | ---: | ---: |
| Catalog entries (`kryonyx/avatars.json`) | 490 | 257 | 233 |
| Categories | 14 | 3 | 11 |
| `redesigned` collection entries | 402 | 257 | 145 |
| `original` collection entries | 68 | 0 | 68 |
| `signature` collection entries | 20 | 0 | 20 |
| Image files (`png` + `thumbs/*.webp` + `svg`) | 1,470 | 771 (257 × 3) | 699 (233 × 3) |
| Notice files (`kryonyx/avatar-notices/`) | 549 | 257 | 292 |

## Removed Categories (Whole Categories)

1. `Music artists` — **90** entries removed (`kryonyx/avatar-notices/redesigned/notices/artists/` removed).
2. `YouTube and creators` — **86** entries removed (`kryonyx/avatar-notices/redesigned/notices/creators/` removed).
3. `Streamers` — **75** entries removed (`kryonyx/avatar-notices/redesigned/notices/streamers/` removed).

## Individually Removed Entries

4. **Odnoklassniki** (`collection-249-одноклассники`, category `Social networks and communities`) — **1** entry removed, along with its PNG, WebP thumbnail, SVG, and notice file (`notices/socials/249-*.txt`).
5. **Poppy Playtime** (all 5 chapters, category `Games`) — **5** entries removed, along with their PNG, WebP thumbnail, SVG, and notice files (`notices/games/021-poppy-playtime.txt`, `525..528-poppy-playtime-chapter-*.txt`):
   - `collection-021-poppy-playtime`
   - `collection-525-poppy-playtime-chapter-2`
   - `collection-526-poppy-playtime-chapter-3`
   - `collection-527-poppy-playtime-chapter-4`
   - `collection-528-poppy-playtime-chapter-5`

## Remaining Categories (11 categories, 233 entries)

- `Games`: 93
- `Classic`: 68
- `Social networks and communities`: 44
- `Signature collection`: 20
- `Music apps`: 2
- `Communication`: 1
- `Game stores`: 1
- `Gaming platforms`: 1
- `Originals`: 1
- `Streaming platforms`: 1
- `Video platforms`: 1

## Migration & Fallback

- Saved profiles referencing any removed avatar ID safely fall back to `DEFAULT_AVATAR` (`kryonyx-core`) in `kryonyx/avatars.py:current()` without deleting or resetting user settings or custom avatars.
