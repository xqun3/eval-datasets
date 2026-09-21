"""numeric_em -- exact numeric / literal match with tolerance (L1).

Used by G6 (data analysis, DABStep-style) where the gold is one exact value.
Handles: thousands separators, currency symbols, percent (0.23 == "23%"),
Chinese 万/亿 units, trailing units, lists of values, and non-numeric literal
answers (falls back to normalised string equality with alternatives ``|``).
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result
from ..utils.text import normalize_text, numbers_in

_ANSWER_TAG = re.compile(
    r"(?:final\s*answer|answer|答案|结果)\s*(?:is|=|:|：)?\s*(?P<v>.+)", re.I)
_CN_UNITS = (("亿", 1e8), ("万", 1e4), ("千", 1e3), ("百", 1e2))


def extract_answer_text(text: str) -> str:
    """Prefer an explicit 'Answer: ...' line, else the last non-empty line."""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    for ln in reversed(lines):
        m = _ANSWER_TAG.search(ln)
        if m:
            return m.group("v").strip()
    return lines[-1] if lines else ""


def parse_number(s: str) -> Optional[float]:
    if s is None:
        return None
    raw = str(s).strip()
    if not raw:
        return None
    mult = 1.0
    for unit, m in _CN_UNITS:
        if unit in raw:
            mult = m
            raw = raw.replace(unit, "")
            break
    pct = "%" in raw or "％" in raw
    nums = numbers_in(raw)
    if not nums:
        return None
    v = nums[0] * mult
    return v / 100.0 if pct else v


def _within(a: float, b: float, rel: float, abs_tol: float) -> bool:
    return abs(a - b) <= max(abs(b) * rel, abs_tol)


def numeric_em(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """gold.type == reference with ``value``; tolerance from env/gold."""
    t0 = time.time()
    env = env or {}
    gold_v = instance.gold["value"]
    target = gold_v.get("value")
    rel = float(env.get("rel_tol", gold_v.get("rel_tol", 1e-6)))
    abs_tol = float(env.get("abs_tol", gold_v.get("abs_tol", 1e-9)))

    resp = ModelResponse.coerce(response)
    cand_text = extract_answer_text(resp.text)

    detail: Dict[str, Any] = {"candidate": cand_text[:200], "target": target}
    ok = False
    mode = "literal"

    if isinstance(target, (int, float)) and not isinstance(target, bool):
        mode = "numeric"
        cand = parse_number(cand_text)
        if cand is None:
            cand = parse_number(resp.text)
        detail["parsed"] = cand
        ok = cand is not None and _within(cand, float(target), rel, abs_tol)
    elif isinstance(target, list):
        mode = "numeric_list"
        cands = numbers_in(cand_text) or numbers_in(resp.text)
        detail["parsed"] = cands
        ok = (len(cands) == len(target)
              and all(_within(c, float(t), rel, abs_tol) for c, t in zip(cands, target)))
    else:
        alts: List[str] = [a.strip() for a in str(target).split("|") if a.strip()]
        cnorm = normalize_text(cand_text)
        ok = any(normalize_text(a) == cnorm for a in alts)
        if not ok:
            # tolerate "the answer is X." wrappers
            ok = any(normalize_text(a) and normalize_text(a) in cnorm for a in alts)
            if ok:
                mode = "literal_contains"

    return new_checker_result(
        score=1.0 if ok else 0.0,
        passed=ok,
        layer="L1",
        sub_metrics={"exact_match": 1.0 if ok else 0.0, "mode": mode,
                     "rel_tol": rel, "abs_tol": abs_tol},
        violations=[],
        detail=detail,
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


register_checker(
    "numeric_em",
    layer="L1",
    gold_types=["reference"],
    description="Exact value match with numeric tolerance / unit + percent normalisation.",
    tags=["G6"],
)(numeric_em)
