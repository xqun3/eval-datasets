"""A tiny, dependency-free MinHash + LSH banding implementation.

Only used for near-duplicate detection inside the dedup stage. Accuracy is
deliberately traded for having zero third-party dependencies.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Iterable, List, Sequence, Set, Tuple

_MAX_HASH = (1 << 32) - 1


def _hash_token(token: str, perm: int) -> int:
    payload = f"{perm}\x00{token}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=4).digest(), "big")


class MinHash:
    """MinHash signature over a set of string tokens."""

    __slots__ = ("num_perm", "signature")

    def __init__(self, tokens: Iterable[str] = (), num_perm: int = 64) -> None:
        self.num_perm = num_perm
        self.signature: List[int] = [_MAX_HASH] * num_perm
        for token in tokens:
            self.update(token)

    def update(self, token: str) -> None:
        for i in range(self.num_perm):
            h = _hash_token(token, i)
            if h < self.signature[i]:
                self.signature[i] = h

    def jaccard(self, other: "MinHash") -> float:
        if self.num_perm != other.num_perm:
            raise ValueError("cannot compare MinHash with different num_perm")
        same = sum(1 for a, b in zip(self.signature, other.signature) if a == b)
        return same / float(self.num_perm)

    def bands(self, num_bands: int = 16) -> List[Tuple[int, str]]:
        """Split the signature into LSH bands -> (band_index, band_digest)."""
        if self.num_perm % num_bands != 0:
            raise ValueError("num_perm must be divisible by num_bands")
        rows = self.num_perm // num_bands
        out: List[Tuple[int, str]] = []
        for b in range(num_bands):
            chunk = self.signature[b * rows : (b + 1) * rows]
            digest = hashlib.blake2b(
                ",".join(str(x) for x in chunk).encode("utf-8"), digest_size=8
            ).hexdigest()
            out.append((b, digest))
        return out


class MinHashIndex:
    """Incremental near-duplicate index: ``query`` then ``add``."""

    def __init__(self, threshold: float = 0.8, num_perm: int = 64, num_bands: int = 16) -> None:
        self.threshold = threshold
        self.num_perm = num_perm
        self.num_bands = num_bands
        self._buckets: Dict[Tuple[int, str], List[str]] = {}
        self._sigs: Dict[str, MinHash] = {}

    def add(self, key: str, tokens: Sequence[str]) -> MinHash:
        mh = MinHash(tokens, num_perm=self.num_perm)
        self._sigs[key] = mh
        for band in mh.bands(self.num_bands):
            self._buckets.setdefault(band, []).append(key)
        return mh

    def query(self, tokens: Sequence[str]) -> List[Tuple[str, float]]:
        """Return [(key, estimated_jaccard)] for candidates above threshold."""
        mh = MinHash(tokens, num_perm=self.num_perm)
        candidates: Set[str] = set()
        for band in mh.bands(self.num_bands):
            candidates.update(self._buckets.get(band, ()))
        hits = []
        for key in sorted(candidates):
            sim = mh.jaccard(self._sigs[key])
            if sim >= self.threshold:
                hits.append((key, sim))
        hits.sort(key=lambda kv: (-kv[1], kv[0]))
        return hits
