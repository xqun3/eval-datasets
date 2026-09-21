"""Stage 8 -- dedup: exact hash + MinHash/n-gram near-duplicate removal."""

from __future__ import annotations

from typing import Dict, List, Sequence

from ..utils.hashing import stable_hash
from ..utils.minhash import MinHashIndex
from ..utils.ngram import char_ngrams, jaccard
from . import Draft, RunContext, Stage


def dedup_key(text: str) -> str:
    from ..utils.ngram import normalize_text

    return stable_hash(normalize_text(text))


class DedupStage(Stage):
    """Drop drafts whose prompt (+gold signature) duplicates an earlier one.

    The index is kept on the stage instance, so it also deduplicates across
    retry rounds within one pipeline run, and can be pre-seeded with an
    existing corpus via :meth:`prime`.
    """

    name = "dedup"

    def __init__(self, threshold: float = 0.85, ngram: int = 4, exact_only: bool = False) -> None:
        self.threshold = threshold
        self.ngram = ngram
        self.exact_only = exact_only
        self._exact: Dict[str, str] = {}
        self._index = MinHashIndex(threshold=threshold)
        self._tokens: Dict[str, Sequence[str]] = {}

    def prime(self, texts: Sequence[str], keys: Sequence[str] = ()) -> None:
        """Pre-load an existing corpus so new drafts are deduped against it."""
        for i, text in enumerate(texts):
            key = keys[i] if i < len(keys) else "corpus-{}".format(i)
            self._remember(key, text)

    def _remember(self, key: str, text: str) -> None:
        self._exact.setdefault(dedup_key(text), key)
        tokens = sorted(char_ngrams(text, self.ngram))
        self._tokens[key] = tokens
        self._index.add(key, tokens)

    def is_duplicate(self, text: str):
        """Return ``(dup_key, similarity)`` or ``None``."""
        ex = self._exact.get(dedup_key(text))
        if ex is not None:
            return ex, 1.0
        if self.exact_only:
            return None
        tokens = sorted(char_ngrams(text, self.ngram))
        for key, approx in self._index.query(tokens):
            exact_sim = jaccard(tokens, self._tokens[key])
            if exact_sim >= self.threshold:
                return key, exact_sim
        return None

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        for d in drafts:
            if not d.alive or d.instance is None:
                continue
            text = d.instance.prompt
            hit = self.is_duplicate(text)
            if hit:
                d.reject(self.name, "duplicate_of:{} (sim={:.2f})".format(hit[0], hit[1]))
                ctx.bump("dedup.dropped")
                continue
            # ids are still provisional at this point (emit renumbers), so the
            # dedup index is keyed by draft position instead
            self._remember("draft#{}.{}".format(d.attempt, d.seq), text)
            d.note(self.name)
            ctx.bump("dedup.kept")
        return drafts
