from __future__ import annotations

import hashlib
import re
import unicodedata


def safe_slug(text: str, max_len: int = 32) -> str:
    """ASCII-ish slug for display filenames; keeps CJK if present but path-safe."""
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = text.strip().replace(" ", "_")
    text = re.sub(r"_+", "_", text)
    if not text:
        return "unknown"
    # Prefer pure ascii fragment when possible
    if text.isascii():
        return text[:max_len]
    # Fallback: short readable prefix + hash (stable across encodings)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    prefix = re.sub(r"[^A-Za-z0-9_-]", "", text)[:12]
    if not prefix:
        return digest
    return f"{prefix}_{digest}"[:max_len]


def stable_key(agent: str, session_id: str) -> str:
    """Stable storage key that is always ASCII (avoids GBK/UTF-8 filename mojibake)."""
    raw = f"{unicodedata.normalize('NFC', agent or '')}\x00{unicodedata.normalize('NFC', session_id or '')}".encode("utf-8")
    digest = hashlib.sha1(raw).hexdigest()[:16]
    return f"{safe_slug(agent or 'unknown', 24)}__{digest}"


def truncate(text: str, n: int = 18) -> str:
    text = text or ""
    if len(text) <= n:
        return text
    return text[: max(0, n - 1)] + "…"
