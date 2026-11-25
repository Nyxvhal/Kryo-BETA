"""Lyric translation service with concurrent chunking, caching, and fallback providers."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

LANGUAGES = {'ru', 'en', 'uk', 'de', 'fr', 'es', 'it', 'pt', 'tr', 'pl', 'ja', 'ko', 'zh-CN'}
MAX_LINES = 240
MAX_CHARS = 24000
_CONCURRENCY = 6
_DISK_CACHE_LIMIT = 64

# Used by API cancellation/busy tests and serialized heavy batch control.
_offline_slots = asyncio.Semaphore(1)
_memory_cache: dict[str, dict[str, Any]] = {}


class TranslationUnavailable(ValueError):
    def __init__(self, message: str, code: str = 'provider'):
        super().__init__(message)
        self.code = code


def validate(lines, target):
    if not isinstance(target, str) or target not in LANGUAGES:
        raise ValueError('Unsupported translation language')
    if not isinstance(lines, list) or not lines or len(lines) > MAX_LINES:
        raise ValueError('Choose 1–240 lyric lines')
    if any(not isinstance(x, str) or len(x) > 2000 or '\n' in x or '\r' in x for x in lines):
        raise ValueError('Each lyric line must be plain text up to 2000 characters')
    if sum(map(len, lines)) > MAX_CHARS:
        raise ValueError('Lyrics exceed 24000 characters')
    if not any(x.strip() for x in lines):
        raise ValueError('No lyric text to translate')


def fingerprint(lines) -> str:
    return hashlib.sha256(
        json.dumps(lines, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    ).hexdigest()


def _normalize_lang(code: str | None, sample_text: str, target: str) -> str:
    if isinstance(code, str):
        raw = code.strip()
        if raw in LANGUAGES:
            return raw
        low = raw.lower()
        if low.startswith('zh'):
            return 'zh-CN'
        base = low.split('-')[0]
        if base in LANGUAGES:
            return base
    # Script-based fallback so short choruses don't fail with an exotic detect code.
    if re.search(r'[\u3040-\u30ff]', sample_text):
        return 'ja'
    if re.search(r'[\uac00-\ud7af]', sample_text):
        return 'ko'
    if re.search(r'[\u4e00-\u9fff]', sample_text):
        return 'zh-CN'
    if re.search(r'[а-яА-ЯёЁіІїЇєЄ]', sample_text):
        return 'uk' if re.search(r'[іїєґІЇЄҐ]', sample_text) else ('ru' if target != 'ru' else 'uk')
    return 'en' if target != 'en' else 'es'


def _cache_path() -> Path | None:
    try:
        from .paths import cache_dir
        path = Path(cache_dir()) / 'lyric_translations_v2.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return None


def _load_disk_cache() -> dict[str, dict[str, Any]]:
    path = _cache_path()
    if not path or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_disk_cache(cache: dict[str, dict[str, Any]]) -> None:
    path = _cache_path()
    if not path:
        return
    try:
        trimmed = dict(list(cache.items())[-_DISK_CACHE_LIMIT:])
        path.write_text(json.dumps(trimmed, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass


def _parse_google_payload(data: Any) -> tuple[str, str | None]:
    if not isinstance(data, list) or not data or not isinstance(data[0], list):
        raise TranslationUnavailable('Malformed translation response', 'malformed')
    parts: list[str] = []
    for chunk in data[0]:
        if isinstance(chunk, list) and chunk and isinstance(chunk[0], str):
            parts.append(chunk[0])
    translated = ''.join(parts).strip()
    if not translated:
        raise TranslationUnavailable('Empty translation returned', 'malformed')
    detected = data[2] if len(data) > 2 and isinstance(data[2], str) else None
    return translated, detected


async def _translate_line_google(
    session: aiohttp.ClientSession, text: str, source: str, target: str
) -> tuple[str, str | None]:
    params = {
        'client': 'gtx',
        'sl': 'auto' if source == 'auto' else source,
        'tl': target,
        'dt': 't',
        'q': text,
    }
    async with session.get(
        'https://translate.googleapis.com/translate_a/single',
        params=params,
        timeout=aiohttp.ClientTimeout(total=12),
    ) as resp:
        if resp.status == 429:
            raise TranslationUnavailable('Translation rate limit reached', 'rate_limit')
        if resp.status >= 400:
            raise TranslationUnavailable(f'Translation HTTP {resp.status}', 'http')
        data = await resp.json(content_type=None)
        return _parse_google_payload(data)


async def _translate_line_mymemory(
    session: aiohttp.ClientSession, text: str, source: str, target: str
) -> tuple[str, str | None]:
    src = source if source != 'auto' else _normalize_lang(None, text, target)
    if src == target:
        src = 'en' if target != 'en' else 'ru'
    params = {'q': text, 'langpair': f'{src}|{target}'}
    async with session.get(
        'https://api.mymemory.translated.net/get',
        params=params,
        timeout=aiohttp.ClientTimeout(total=12),
    ) as resp:
        if resp.status == 429:
            raise TranslationUnavailable('Translation rate limit reached', 'rate_limit')
        if resp.status >= 400:
            raise TranslationUnavailable(f'Translation HTTP {resp.status}', 'http')
        data = await resp.json(content_type=None)
        translated = str((data or {}).get('responseData', {}).get('translatedText') or '').strip()
        if not translated:
            raise TranslationUnavailable('Empty fallback translation', 'malformed')
        return translated, src


async def _translate_unique_line(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    text: str,
    source: str,
    target: str,
) -> tuple[str, str | None, str | None]:
    async with sem:
        try:
            translated, detected = await _translate_line_google(session, text, source, target)
            return translated, detected, None
        except asyncio.CancelledError:
            raise
        except TranslationUnavailable as primary_exc:
            try:
                translated, detected = await _translate_line_mymemory(session, text, source, target)
                return translated, detected, None
            except asyncio.CancelledError:
                raise
            except TranslationUnavailable as fallback_exc:
                return '', None, fallback_exc.code or primary_exc.code
            except (aiohttp.ClientError, asyncio.TimeoutError):
                return '', None, primary_exc.code or 'network'
        except asyncio.TimeoutError:
            return '', None, 'timeout'
        except aiohttp.ClientError:
            try:
                translated, detected = await _translate_line_mymemory(session, text, source, target)
                return translated, detected, None
            except asyncio.CancelledError:
                raise
            except TranslationUnavailable as fallback_exc:
                return '', None, fallback_exc.code
            except (aiohttp.ClientError, asyncio.TimeoutError):
                return '', None, 'network'


async def _translate_argos_if_configured(lines, target, source, context=None):
    import sys
    from .paths import app_dir, resource_dir

    custom = os.environ.get('KRYONYX_TRANSLATE_PYTHON')
    local = Path(app_dir()) / '.translate-venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    python = custom or (str(local) if local.is_file() else None)
    if not python:
        return None
    worker = str(Path(resource_dir()) / 'argos_worker.py')
    if not Path(worker).is_file():
        return None
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    proc = await asyncio.create_subprocess_exec(
        python, worker,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
        **({'creationflags': 0x08000000} if os.name == 'nt' else {}),
    )
    try:
        out, _ = await asyncio.wait_for(
            proc.communicate(json.dumps({'lines': lines, 'source': source, 'target': target, 'context': context}, ensure_ascii=False).encode('utf-8')),
            180,
        )
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    data = json.loads(out.decode('utf-8'))
    if proc.returncode or data.get('error'):
        return None
    return data


async def translate_offline(lines, target, source, context=None):
    if _offline_slots.locked():
        raise TranslationUnavailable('Translator is busy; retry shortly.', 'busy')
    async with _offline_slots:
        return await _translate_job(lines, target, source, context)


async def _translate_job(lines, target, source, context=None):
    validate(lines, target)
    if not isinstance(source, str) or source not in LANGUAGES | {'auto'}:
        raise ValueError('Choose a supported source language')
    if source == target:
        raise ValueError('Choose different source and target languages')
    if context is not None:
        validate(context, target)

    fp = fingerprint(lines)
    cache_key = f'{fp}:{source}:{target}'
    cached = _memory_cache.get(cache_key)
    if cached:
        return cached

    disk_cache = _load_disk_cache()
    if cache_key in disk_cache:
        entry = disk_cache[cache_key]
        _memory_cache[cache_key] = entry
        return entry

    # Optional offline Argos path when an explicit .translate-venv is configured.
    try:
        argos_data = await _translate_argos_if_configured(lines, target, source, context)
    except Exception:
        argos_data = None

    if isinstance(argos_data, dict) and isinstance(argos_data.get('results'), list) and len(argos_data['results']) == len(lines):
        rows = argos_data['results']
        actual_source = _normalize_lang(argos_data.get('source'), '\n'.join(lines), target)
        failed = sum(r.get('status') == 'error' for r in rows)
        succeeded = sum(r.get('status') == 'ok' for r in rows)
        payload = {
            'schema_version': 1,
            'fingerprint': fp,
            'source': actual_source,
            'target': target,
            'provider': 'kryo-translate-v2',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'state': ('partial' if succeeded else 'error') if failed else 'complete',
            'results': rows,
            'translations': [r.get('translation', '') for r in rows],
            'machine_translation': True,
        }
        if payload['state'] == 'complete':
            _memory_cache[cache_key] = payload
            disk_cache[cache_key] = payload
            _save_disk_cache(disk_cache)
        return payload

    unique_texts: list[str] = []
    seen_texts: set[str] = set()
    for line in lines:
        trimmed = line.strip()
        if trimmed and trimmed not in seen_texts:
            seen_texts.add(trimmed)
            unique_texts.append(trimmed)

    sem = asyncio.Semaphore(_CONCURRENCY)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) KryoMusic/1.0'}
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [
            asyncio.create_task(_translate_unique_line(session, sem, txt, source, target))
            for txt in unique_texts
        ]
        try:
            outcomes = await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    by_text = dict(zip(unique_texts, outcomes))
    detected_counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []

    for i, orig in enumerate(lines):
        trimmed = orig.strip()
        if not trimmed:
            rows.append({'index': i, 'original': orig, 'translation': '', 'status': 'empty'})
            continue
        translated, detected, err_code = by_text[trimmed]
        if err_code or not translated.strip():
            rows.append({
                'index': i,
                'original': orig,
                'translation': '',
                'status': 'error',
                'error_code': err_code or 'provider',
            })
            continue
        if detected:
            detected_counts[detected] = detected_counts.get(detected, 0) + 1
        rows.append({
            'index': i,
            'original': orig,
            'translation': translated,
            'status': 'ok',
        })

    succeeded = sum(1 for r in rows if r['status'] == 'ok')
    failed = sum(1 for r in rows if r['status'] == 'error')
    if succeeded == 0 and failed > 0:
        first_err = next((r.get('error_code') for r in rows if r['status'] == 'error'), 'network')
        raise TranslationUnavailable('Could not translate lyrics online. Check internet connection.', first_err or 'network')

    raw_detected = max(detected_counts, key=detected_counts.get) if detected_counts else None
    actual_source = source if source != 'auto' else _normalize_lang(raw_detected, '\n'.join(unique_texts[:8]), target)

    payload = {
        'schema_version': 1,
        'fingerprint': fp,
        'source': actual_source,
        'target': target,
        'provider': 'kryo-translate-v2',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'state': ('partial' if succeeded else 'error') if failed else 'complete',
        'results': rows,
        'translations': [r['translation'] for r in rows],
        'machine_translation': True,
    }
    if payload['state'] == 'complete':
        _memory_cache[cache_key] = payload
        disk_cache[cache_key] = payload
        _save_disk_cache(disk_cache)
    return payload
