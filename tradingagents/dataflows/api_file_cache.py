"""Simple JSON-on-disk cache for HTTP API responses (Alpha Vantage, FRED batches)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def _cache_root() -> Path:
    try:
        from tradingagents.dataflows.config import get_config

        return Path(get_config().get("data_cache_dir", os.path.expanduser("~/.tradingagents/cache")))
    except Exception:
        return Path(os.path.expanduser("~/.tradingagents/cache"))


def cache_subdir(name: str) -> Path:
    d = _cache_root() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def stable_hash(key_parts: tuple) -> str:
    raw = json.dumps(key_parts, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def cache_get_json(subdir: str, key: str, ttl_seconds: int) -> Optional[Any]:
    path = cache_subdir(subdir) / f"{key}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if time.time() - float(payload.get("_cached_at", 0)) > ttl_seconds:
            return None
        return payload.get("data")
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None


def cache_set_json(subdir: str, key: str, data: Any) -> None:
    path = cache_subdir(subdir) / f"{key}.json"
    payload = {"_cached_at": time.time(), "data": data}
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    tmp.replace(path)
