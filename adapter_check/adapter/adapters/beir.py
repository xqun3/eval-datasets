"""BEIR-style retrieval sets (SciFact / NFCorpus / T2Ranking) ->
G2 / reference / doc_recall_at_k.

BEIR is three files, not one: ``corpus.jsonl`` (``_id``/``title``/``text``),
``queries.jsonl`` (``_id``/``text``) and ``qrels/*.tsv``
(``query-id doc-id score``). Our CLI streams ONE file, so:

    --in   queries.jsonl
    --aux  {"corpus": {doc_id: {...}}, "qrels": {query_id: {doc_id: score}}}

**Corpus down-sampling** (the interesting part). A 5M-doc corpus cannot go into
``context.kb_docs``. We build a per-query pool of
``pool_size`` (default 50) documents:

    1. ALL positives from qrels (never dropped),
    2. then *hard negatives* -- highest lexical-overlap non-relevant docs,
       scored by a stdlib BM25-lite (idf-weighted token overlap),
    3. then random-but-deterministic fillers (seeded by query id) to reach
       the pool size.

Keeping hard negatives is what preserves discriminative power; uniform random
sampling would inflate Recall@5 for everyone.
"""
from __future__ import annotations

import hashlib
import math
import random
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from ..base import Adapter, AdapterConfig
from ..registry import register_adapter
from ..schema import TaskInstance
from ..utils.text import tokenize


class BM25Lite:
    """Tiny idf-weighted overlap scorer (stdlib only, deterministic)."""

    def __init__(self, corpus: Dict[str, Dict[str, Any]]):
        self.docs: Dict[str, List[str]] = {}
        df: Counter = Counter()
        for did, doc in corpus.items():
            toks = tokenize((doc.get("title", "") + " " + doc.get("text", "")))
            self.docs[did] = toks
            for t in set(toks):
                df[t] += 1
        n = max(1, len(corpus))
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.avgdl = (sum(len(v) for v in self.docs.values()) / float(n)) or 1.0

    def score(self, query: str, doc_id: str, k1: float = 1.2, b: float = 0.75) -> float:
        q = tokenize(query)
        toks = self.docs.get(doc_id, [])
        if not toks:
            return 0.0
        tf = Counter(toks)
        dl = len(toks)
        s = 0.0
        for t in set(q):
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf.get(t, 0.0) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / self.avgdl))
        return s


@register_adapter("beir")
class BeirAdapter(Adapter):
    dataset = "beir-scifact"
    version = "v1.0.0"
    category = "G2"
    subtype = "DOC_RETRIEVAL"
    gold_type = "reference"
    checker = "doc_recall_at_k"
    license = "CC BY-SA 4.0 (SciFact); per-subset, see manifest"
    commercial_use = "conditional"
    homepage = "https://github.com/beir-cellar/beir"
    base_must_not = ("编造文档ID",)
    lossy_notes = (
        "语料被下采样到 per-query pool（默认 50 篇，含全部正例 + 高词面重合硬负例），"
        "因此 Recall@k 是 pool 内的值，绝对数值高于全量语料上的真实检索难度，"
        "只能横向比模型、不能与官方 leaderboard 数字直接比较；"
        "BEIR 多子集许可证不一致，逐子集写在 manifest.license 里。"
    )

    def prepare(self, cfg: AdapterConfig) -> None:
        self.corpus: Dict[str, Dict[str, Any]] = dict(cfg.aux.get("corpus") or {})
        self.qrels: Dict[str, Dict[str, float]] = {
            str(k): {str(d): float(s) for d, s in v.items()}
            for k, v in (cfg.aux.get("qrels") or {}).items()
        }
        self.pool_size = int(cfg.options.get("pool_size", 50))
        self.hard_neg = int(cfg.options.get("hard_negatives", 20))
        self._bm25 = BM25Lite(self.corpus) if self.corpus else None

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G2 heuristic: #positives and lexical gap between query and positives."""
        n_pos = inst_kwargs.get("n_pos", 1)
        best = inst_kwargs.get("best_pos_score", 0.0)
        if n_pos >= 3 or best < 1.0:
            return "L3"
        if n_pos == 2 or best < 4.0:
            return "L2"
        return "L1"

    def sample_pool(self, qid: str, query: str, positives: List[str]) -> Tuple[List[str], Dict[str, str]]:
        """positives + hard negatives + deterministic fillers."""
        pool = [d for d in positives if d in self.corpus]
        origin = {d: "positive" for d in pool}
        others = [d for d in self.corpus if d not in set(pool)]
        if self._bm25 is not None:
            scored = sorted(((self._bm25.score(query, d), d) for d in others), reverse=True)
            for _s, d in scored[: self.hard_neg]:
                if len(pool) >= self.pool_size:
                    break
                pool.append(d)
                origin[d] = "hard_negative"
        rng = random.Random(int(hashlib.sha1(str(qid).encode()).hexdigest()[:8], 16))
        rest = [d for d in others if d not in origin]
        rng.shuffle(rest)
        for d in rest:
            if len(pool) >= self.pool_size:
                break
            pool.append(d)
            origin[d] = "filler"
        return pool, origin

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        qid = str(raw_record.get("_id") or raw_record.get("id") or "").strip()
        query = (raw_record.get("text") or raw_record.get("query") or "").strip()
        if not qid or not query:
            return None
        rel = self.qrels.get(qid) or {}
        positives = [d for d, s in sorted(rel.items()) if s > 0]
        if not positives:
            return None                       # filtered: no judged positive

        pool, origin = self.sample_pool(qid, query, positives)
        kb_docs = []
        for d in pool:
            doc = self.corpus[d]
            kb_docs.append({"doc_id": d,
                            "title": doc.get("title", ""),
                            "text": doc.get("text", ""),
                            "role": origin[d]})

        best = max((self._bm25.score(query, d) for d in positives if d in self.corpus),
                   default=0.0) if self._bm25 else 0.0
        gold = {
            "type": "reference",
            "value": {
                "doc_ids": positives,
                "must_cite": positives if len(positives) <= 3 else [],
                "value": None,
                "graded": {d: float(s) for d, s in rel.items() if s > 0},
                "k": int(cfg.options.get("k", 5)),
            },
        }
        prompt = ("在给定文档库中检索并返回与下列查询最相关的文档 ID（按相关性降序，最多 %d 个）：\n%s"
                  % (int(cfg.options.get("k", 5)), query))
        return self.build(
            raw_record, cfg,
            subtype="DOC_RETRIEVAL",
            prompt=prompt,
            gold=gold,
            context={"files": [], "db_schema": None, "kb_docs": kb_docs},
            difficulty=self.infer_difficulty(
                raw_record, {"n_pos": len(positives), "best_pos_score": best}),
            manifest_extra={"query_id": qid, "n_positives": len(positives),
                            "pool_size": len(pool),
                            "hard_negatives": sum(1 for v in origin.values()
                                                  if v == "hard_negative"),
                            "fillers": sum(1 for v in origin.values() if v == "filler"),
                            "downsampled_from": len(self.corpus)},
        )
