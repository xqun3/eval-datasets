"""Character n-gram utilities (works for Chinese text where word split is hard)."""

from __future__ import annotations

import re
from typing import Iterable, List, Set

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\s,.;:!?()\[\]{}<>\"'`~@#$%^&*_+=|\\/，。；：！？（）【】《》“”‘’、·—-]+")


def normalize_text(text: str) -> str:
    """Lowercase + strip punctuation/whitespace so n-grams are comparable."""
    if not text:
        return ""
    return _PUNCT_RE.sub("", text.lower())


def char_ngrams(text: str, n: int = 4) -> Set[str]:
    """Return the set of character n-grams of ``text`` after normalization."""
    norm = normalize_text(text)
    if n <= 0:
        raise ValueError("n must be positive")
    if len(norm) < n:
        return {norm} if norm else set()
    return {norm[i : i + n] for i in range(len(norm) - n + 1)}


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Exact Jaccard similarity between two iterables of tokens."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def token_ngrams(text: str, n: int = 3) -> List[str]:
    """Whitespace-token n-grams; mostly useful for English / code-ish text."""
    tokens = [t for t in _WS_RE.split(text.strip().lower()) if t]
    if len(tokens) < n:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]
