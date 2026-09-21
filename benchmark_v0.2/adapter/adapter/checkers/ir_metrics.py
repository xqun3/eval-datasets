"""IR checkers: doc_recall_at_k (+nDCG@k) and citation_groundedness (L2).

Both operate on gold.type == reference:

    {"doc_ids": [...], "must_cite": [...], "value": <exact answer or null>,
     "graded": {"doc_id": 3, ...}}   # optional graded relevance for nDCG

``doc_recall_at_k`` scores the *retrieval* side (what the model returned as a
ranked list -- ``response.citations`` or ``response.meta["ranking"]``).
``citation_groundedness`` scores the *generation* side: every cited doc must
exist in the snapshot (fake-doc rate must be 0, SCHEMA §0 G2) and every quoted
span must be findable verbatim in the cited document.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result
from ..utils.text import normalize_text


def _ranking(resp: ModelResponse) -> List[str]:
    r = resp.meta.get("ranking")
    if isinstance(r, list) and r:
        return [str(x) for x in r]
    return [str(x) for x in resp.citations]


def recall_at_k(ranked: List[str], relevant: List[str], k: int) -> float:
    if not relevant:
        return 1.0
    topk = set(ranked[:k])
    return len([d for d in set(relevant) if d in topk]) / float(len(set(relevant)))


def ndcg_at_k(ranked: List[str], graded: Dict[str, float], k: int) -> float:
    if not graded:
        return 0.0
    dcg = 0.0
    for i, doc in enumerate(ranked[:k]):
        rel = float(graded.get(doc, 0.0))
        if rel:
            dcg += (2 ** rel - 1) / math.log2(i + 2)
    ideal = sorted(graded.values(), reverse=True)[:k]
    idcg = sum((2 ** float(r) - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def doc_recall_at_k(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Recall@k (primary) + nDCG@k (sub) over the retrieved ranking."""
    t0 = time.time()
    env = env or {}
    k = int(env.get("k", (instance.gold["value"].get("k") or 5)))
    resp = ModelResponse.coerce(response)
    ranked = _ranking(resp)
    gold = instance.gold["value"]
    relevant = list(gold.get("doc_ids") or [])
    graded = {str(a): float(b) for a, b in (gold.get("graded") or {}).items()}
    if not graded:
        graded = {d: 1.0 for d in relevant}

    known = {d.get("doc_id") for d in (instance.context.get("kb_docs") or [])}
    fake = [d for d in ranked if known and d not in known]

    r = recall_at_k(ranked, relevant, k)
    n = ndcg_at_k(ranked, graded, max(k, 10))
    violations = ["返回了不存在的文档ID: %s" % ", ".join(fake[:5])] if fake else []
    score = 0.0 if fake else r
    return new_checker_result(
        score=score,
        passed=(score >= 0.85 and not fake),   # SCHEMA §0: G2 Recall@5 >= 0.85, fake-doc = 0
        layer="L2",
        sub_metrics={"recall_at_%d" % k: round(r, 6),
                     "ndcg_at_10": round(n, 6),
                     "fake_doc_rate": round(len(fake) / float(len(ranked)), 6) if ranked else 0.0,
                     "returned": len(ranked)},
        violations=violations,
        detail={"ranked": ranked[:20], "relevant": relevant, "fake": fake[:10], "k": k},
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


def citation_groundedness(instance, response, env: Optional[Dict[str, Any]] = None
                          ) -> Dict[str, Any]:
    """Every citation must exist AND every quoted span must be verbatim.

    Quotes are read from ``response.meta["quotes"] = {doc_id: [span, ...]}``.
    Score = 0.5 * must_cite coverage + 0.5 * span verifiability, hard-zeroed
    by any fabricated doc id.
    """
    t0 = time.time()
    resp = ModelResponse.coerce(response)
    gold = instance.gold["value"]
    must_cite = list(gold.get("must_cite") or [])
    docs = {d.get("doc_id"): (d.get("text") or d.get("content") or "")
            for d in (instance.context.get("kb_docs") or [])}
    cited = [str(c) for c in resp.citations]
    fake = [c for c in cited if c not in docs]

    covered = [m for m in must_cite if m in cited]
    cov = len(covered) / float(len(must_cite)) if must_cite else 1.0

    quotes = resp.meta.get("quotes") or {}
    total_q, ok_q, bad_spans = 0, 0, []
    for doc_id, spans in quotes.items():
        for span in (spans or []):
            total_q += 1
            body = normalize_text(docs.get(doc_id, ""))
            if normalize_text(span) and normalize_text(span) in body:
                ok_q += 1
            else:
                bad_spans.append({"doc_id": doc_id, "span": str(span)[:80]})
    span_score = (ok_q / float(total_q)) if total_q else 1.0

    violations = []
    if fake:
        violations.append("引用了不存在的文档: %s" % ", ".join(fake[:5]))
    if bad_spans:
        violations.append("引文无法在原文中定位: %d 处" % len(bad_spans))

    score = 0.0 if fake else 0.5 * cov + 0.5 * span_score
    return new_checker_result(
        score=score,
        passed=(not fake and cov >= 0.999 and span_score >= 0.999),
        layer="L2",
        sub_metrics={"must_cite_coverage": round(cov, 6),
                     "span_verifiable": round(span_score, 6),
                     "fake_doc_count": len(fake),
                     "quotes_checked": total_q},
        violations=violations,
        detail={"cited": cited[:20], "must_cite": must_cite, "bad_spans": bad_spans[:10]},
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


register_checker(
    "doc_recall_at_k",
    layer="L2",
    gold_types=["reference"],
    description="Recall@k primary + nDCG@10 sub-metric; fabricated doc id => score 0.",
    tags=["G2", "ir"],
)(doc_recall_at_k)

register_checker(
    "citation_groundedness",
    layer="L2",
    gold_types=["reference", "factlist"],
    description="Citations must resolve to snapshot docs and quoted spans must be verbatim.",
    tags=["G2", "G3"],
)(citation_groundedness)
