"""fact_recall -- atomic-fact recall for gold.type == factlist (L2).

Default matcher is purely rule based (no network, no model):

  * each fact's ``text`` may carry alternatives separated by ``|``
    ("Bo Xilai|薄熙来") -- matching any alternative counts as a hit;
  * matching is done on NFKC-normalised, punctuation-stripped text, so
    「１２３」 == "123" and "Sept. 3, 1972" == "sept 3 1972";
  * pure-numeric facts match with tolerance instead of substring, so
    "3.1400" satisfies "3.14";
  * ``required: false`` facts count towards a separate bonus metric only.

An LLM judge can be injected via ``env["fact_judge"]``:

    def fact_judge(fact_text: str, answer: str) -> Optional[bool]

returning None == abstain (falls back to the rule matcher). The default stub
always abstains, which is why the whole chain runs offline.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result
from ..utils.text import normalize_text, numbers_in

REL_TOL = 1e-6


def default_fact_judge(fact_text: str, answer: str) -> Optional[bool]:
    """Offline stub: never decides, always defers to the rule matcher."""
    return None


def _numeric_fact(fact_text: str) -> Optional[float]:
    nums = numbers_in(fact_text)
    stripped = normalize_text(fact_text).replace(" ", "")
    if len(nums) == 1 and all(c.isdigit() or c in ".,-+%" for c in stripped):
        return nums[0]
    return None


def _num_match(target: float, answer: str) -> bool:
    for n in numbers_in(answer):
        if abs(n - target) <= max(abs(target) * 1e-4, 1e-9):
            return True
    return False


def _squash(s: str) -> str:
    """Normalised with ALL whitespace removed -- Chinese answers insert spaces
    around numbers ("是 2008 年") that carry no meaning."""
    return normalize_text(s).replace(" ", "")


def rule_match(fact_text: str, answer_norm: str, answer_raw: str) -> bool:
    alts = [a.strip() for a in fact_text.split("|") if a.strip()]
    answer_squashed = _squash(answer_raw)
    for alt in alts:
        num = _numeric_fact(alt)
        if num is not None:
            if _num_match(num, answer_raw):
                return True
            continue
        n = normalize_text(alt)
        if n and n in answer_norm:
            return True
        sq = _squash(alt)
        if sq and sq in answer_squashed:
            return True
    return False


def fact_recall(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Atomic fact recall; score = matched_required / total_required."""
    t0 = time.time()
    env = env or {}
    judge: Callable[[str, str], Optional[bool]] = env.get("fact_judge", default_fact_judge)
    resp = ModelResponse.coerce(response)
    answer_raw = resp.text or ""
    answer_norm = normalize_text(answer_raw)

    facts: List[Dict[str, Any]] = instance.gold["value"]["facts"]
    required = [f for f in facts if f.get("required")]
    optional = [f for f in facts if not f.get("required")]

    hits, misses, judged = [], [], 0
    for f in facts:
        verdict = judge(f["text"], answer_raw)
        if verdict is None:
            ok = rule_match(f["text"], answer_norm, answer_raw)
            how = "rule"
        else:
            ok = bool(verdict)
            how = "judge"
            judged += 1
        (hits if ok else misses).append({"id": f["id"], "required": bool(f.get("required")),
                                         "how": how})

    req_hit = sum(1 for h in hits if h["required"])
    opt_hit = sum(1 for h in hits if not h["required"])
    score = req_hit / float(len(required)) if required else (1.0 if not misses else 0.0)

    sub = {
        "fact_recall": round(score, 6),
        "required_total": len(required),
        "required_hit": req_hit,
        "optional_total": len(optional),
        "optional_hit": opt_hit,
        "judge_used": judged,
        "judge_stub": judge is default_fact_judge,
    }
    return new_checker_result(
        score=score,
        passed=score >= 0.85,   # SCHEMA §0: G1 FactRecall >= 0.85
        layer="L2",
        sub_metrics=sub,
        violations=[],
        detail={"hits": hits, "misses": misses,
                "ref_answer": instance.gold["value"].get("ref_answer")},
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


register_checker(
    "fact_recall",
    layer="L2",
    gold_types=["factlist"],
    description="Atomic fact-point recall with injectable LLM judge (default: offline rule stub).",
    tags=["G1", "G3"],
)(fact_recall)
