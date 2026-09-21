"""Stage 9 -- decontaminate: keep public-benchmark / leaked text out of the set.

Two mechanisms, both offline:
  * a *blocklist* of n-grams (loaded from a plain text file, one phrase per line)
  * n-gram overlap against a reference corpus file (one document per line)
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence, Set

from ..utils.ngram import char_ngrams, jaccard, normalize_text
from . import Draft, RunContext, Stage

#: shipped defaults: phrases that indicate a public benchmark leaked in
DEFAULT_BLOCKLIST = (
    "spider benchmark",
    "wikisql",
    "bird-sql",
    "gsm8k",
    "humaneval",
    "mmlu",
    "swe-bench",
    "请忽略之前的所有指令",
)


class DecontaminateStage(Stage):
    """Reject drafts that overlap the blocklist or a known corpus."""

    name = "decontaminate"

    def __init__(
        self,
        blocklist: Sequence[str] = DEFAULT_BLOCKLIST,
        corpus_path: Optional[str] = None,
        threshold: float = 0.6,
        ngram: int = 5,
    ) -> None:
        self.blocklist = [normalize_text(b) for b in blocklist if b.strip()]
        self.threshold = threshold
        self.ngram = ngram
        self.corpus: List[Set[str]] = []
        self.corpus_path = corpus_path
        if corpus_path:
            self.load_corpus(corpus_path)

    def load_corpus(self, path: str) -> int:
        if not os.path.exists(path):
            raise FileNotFoundError("decontamination corpus not found: {}".format(path))
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self.corpus.append(char_ngrams(line, self.ngram))
        return len(self.corpus)

    def contamination(self, text: str):
        """Return ``(reason, score)`` when contaminated, else ``None``."""
        norm = normalize_text(text)
        for phrase in self.blocklist:
            if phrase and phrase in norm:
                return "blocklist:{}".format(phrase), 1.0
        if self.corpus:
            grams = char_ngrams(text, self.ngram)
            best = 0.0
            for doc in self.corpus:
                sim = jaccard(grams, doc)
                if sim > best:
                    best = sim
            if best >= self.threshold:
                return "corpus_overlap", best
        return None

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        for d in drafts:
            if not d.alive or d.instance is None:
                continue
            hit = self.contamination(d.instance.prompt)
            if hit:
                d.reject(self.name, "contaminated:{} ({:.2f})".format(hit[0], hit[1]))
                ctx.bump("decontam.dropped")
                continue
            d.note(self.name)
            ctx.bump("decontam.kept")
        return drafts
