"""Stable, cross-process hashing helpers.

``hash()`` in CPython is salted per process, so every reproducibility-critical
hash in synthgen goes through :func:`stable_hash`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize ``obj`` deterministically (sorted keys, no ascii escaping)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def stable_hash(obj: Any) -> str:
    """Return the full sha256 hex digest of the canonical JSON form of ``obj``."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def short_hash(obj: Any, length: int = 10) -> str:
    """Return a shortened :func:`stable_hash`."""
    if length <= 0:
        raise ValueError("length must be positive")
    return stable_hash(obj)[:length]


def stable_int(obj: Any, bits: int = 63) -> int:
    """Map ``obj`` to a deterministic non-negative integer (useful to seed RNGs)."""
    digest = hashlib.sha256(canonical_json(obj).encode("utf-8")).digest()
    return int.from_bytes(digest, "big") % (1 << bits)
