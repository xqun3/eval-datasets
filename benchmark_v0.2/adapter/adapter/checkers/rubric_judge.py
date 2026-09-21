"""rubric_judge -- L3 scorer for gold.type == rubric, with an OFFLINE stub.

The real judge is an LLM. Here it is a *deterministic, injectable* stub so the
whole pipeline runs with no network:

    env["judge"] = fn(prompt, response_text, dims, must_cover) -> {dim_name: 1..5}

When no judge is injected, ``heuristic_judge`` is used: it scores each
dimension from cheap observable signals (must_cover coverage, length band,
structure markers). It is explicitly NOT a quality measurement -- every result
carries ``sub_metrics.stub = True`` and ``detail.warning`` so no one mistakes a
stub score for a real L3 score.

Position-bias handling (SCHEMA §3: pairwise must swap both ways) cannot be done
here: pointwise scoring is order-independent, so there is nothing to swap. It
requires a comparative judge that sees both answers in one prompt -- inject it
as ``env["pairwise_judge"]`` (metrics/judge/runner.py). Without it,
``pairwise_judge`` below reports ``position_bias_controlled=False``.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result
from ..utils.text import normalize_text

STUB_WARNING = ("rubric_judge ran with the offline heuristic stub; "
                "scores are NOT a quality judgement, only a plumbing check")


def heuristic_judge(prompt: str, answer: str, dims: List[Dict[str, Any]],
                    must_cover: List[str]) -> Dict[str, float]:
    """Deterministic 1..5 per dimension from observable signals only."""
    a = answer or ""
    a_norm = normalize_text(a)
    covered = [m for m in (must_cover or []) if normalize_text(m) and normalize_text(m) in a_norm]
    cov = (len(covered) / float(len(must_cover))) if must_cover else 1.0
    n_chars = len(a)
    structured = sum(1 for mark in ("\n-", "\n*", "\n1.", "##", "|") if mark in a)

    base = 1.0 + 4.0 * cov
    out: Dict[str, float] = {}
    for d in dims:
        name = d["name"]
        s = base
        low = name.lower()
        if "结构" in name or "format" in low or "structure" in low:
            s = 1.0 + min(4.0, structured * 1.0 + 2.0 * cov)
        elif "完整" in name or "complete" in low or "coverage" in low:
            s = 1.0 + 4.0 * cov
        elif "简洁" in name or "concise" in low:
            s = 5.0 if 100 <= n_chars <= 1500 else (3.0 if n_chars else 1.0)
        elif not a.strip():
            s = 1.0
        out[name] = float(max(1.0, min(5.0, round(s, 2))))
    return out


def rubric_judge(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Weighted pointwise rubric score, normalised to [0,1] (raw 1..5 in sub).

    If the judge is unavailable (raises) or hands back an incomplete set of
    dimension scores, the result is **not measured** (score=None) rather than
    a floor score. Defaulting a missing dimension to 1.0 silently converts our
    own outage into "the model failed this category" -- see the truncated-judge
    incident: a well-written answer scored 0.0 with ``stub=False``, which is
    indistinguishable from a genuinely terrible answer.
    """
    t0 = time.time()
    env = env or {}
    judge: Callable[..., Dict[str, float]] = env.get("judge", heuristic_judge)
    is_stub = judge is heuristic_judge

    resp = ModelResponse.coerce(response)
    gv = instance.gold["value"]
    dims: List[Dict[str, Any]] = gv["dims"]
    must_cover: List[str] = list(gv.get("must_cover") or [])

    a_norm = normalize_text(resp.text)
    missed = [m for m in must_cover if normalize_text(m) and normalize_text(m) not in a_norm]
    cov = 1.0 - (len(missed) / float(len(must_cover))) if must_cover else 1.0

    def _unmeasured(reason: str, missing: Optional[List[str]] = None) -> Dict[str, Any]:
        return new_checker_result(
            score=None, passed=None, layer="L3",
            sub_metrics={"rubric_mean_5": None,
                         "per_dim": {},
                         "must_cover_coverage": round(cov, 6),
                         "stub": is_stub,
                         "judge_failed": True},
            violations=[],
            detail={"missed_must_cover": missed[:10],
                    "warning": STUB_WARNING if is_stub else None,
                    "judge": getattr(judge, "__name__", "injected"),
                    "judge_error": reason,
                    "missing_dims": missing or []},
            cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
        )

    # 判分器自己坏掉不该让整轮挂掉，但也绝不能记成模型的 0 分。
    try:
        raw = judge(instance.prompt, resp.text, dims, must_cover) or {}
    except Exception as exc:                      # noqa: BLE001 - 任何故障都算缺测
        return _unmeasured("judge raised %s: %s" % (type(exc).__name__, exc))

    missing = [d["name"] for d in dims if raw.get(d["name"]) is None]
    if missing:
        return _unmeasured("judge returned no score for %d/%d dimension(s)"
                           % (len(missing), len(dims)), missing)

    total, per_dim = 0.0, {}
    for d in dims:
        s = max(1.0, min(5.0, float(raw[d["name"]])))
        per_dim[d["name"]] = s
        total += s * float(d["weight"])

    score01 = (total - 1.0) / 4.0
    return new_checker_result(
        score=score01,
        passed=total >= 4.0,   # SCHEMA §0: G4/G10 rubric mean >= 4.0/5
        layer="L3",
        sub_metrics={"rubric_mean_5": round(total, 4),
                     "per_dim": per_dim,
                     "must_cover_coverage": round(cov, 6),
                     "stub": is_stub,
                     "judge_failed": False},
        violations=[],
        detail={"missed_must_cover": missed[:10],
                "warning": STUB_WARNING if is_stub else None,
                "judge": getattr(judge, "__name__", "injected")},
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


def pairwise_judge(instance, response_a, response_b, env: Optional[Dict[str, Any]] = None
                   ) -> Dict[str, Any]:
    """A/B comparison.

    SCHEMA §3 requires swapping both ways to cancel position bias. That is only
    meaningful if both answers sit in *one* prompt -- pointwise scoring is
    order-independent by construction, so "swapping" two independent pointwise
    scores cannot change anything.

    The previous implementation did exactly that and computed
    ``net = (fwd - rev) / 2`` where ``rev == -fwd`` by definition, i.e. ``net``
    was identically ``score_a - score_b``. It looked de-biased and wasn't.

    So: if a real comparative judge is injected via ``env["pairwise_judge"]``
    (see metrics/judge/runner.py::JudgeRunner.pairwise), we use it and report
    whether the two orderings agreed. Otherwise we fall back to the pointwise
    difference and say so explicitly -- ``position_bias_controlled=False``.
    """
    env = env or {}
    ra = rubric_judge(instance, response_a, env)
    rb = rubric_judge(instance, response_b, env)
    pointwise_margin = ra["score"] - rb["score"]

    pw = env.get("pairwise_judge")
    if pw is not None:
        gv = instance.gold["value"]
        verdict = pw(instance.prompt,
                     ModelResponse.coerce(response_a).text,
                     ModelResponse.coerce(response_b).text,
                     gv["dims"])
        winner = {"A": "a", "B": "b"}.get(verdict.get("winner"), "tie")
        return {"winner": winner,
                "margin": round(pointwise_margin, 6),
                "position_bias_controlled": True,
                "orders_agree": bool(verdict.get("consistent")),
                "judge_detail": verdict,
                "a": ra["sub_metrics"], "b": rb["sub_metrics"]}

    winner = ("a" if pointwise_margin > 1e-9
              else ("b" if pointwise_margin < -1e-9 else "tie"))
    return {"winner": winner,
            "margin": round(pointwise_margin, 6),
            "position_bias_controlled": False,
            "warning": ("pointwise difference only; SCHEMA §3 two-way swap is NOT "
                        "satisfied. Inject env['pairwise_judge'] for a real "
                        "comparative judgement."),
            "a": ra["sub_metrics"], "b": rb["sub_metrics"]}


register_checker(
    "rubric_judge",
    layer="L3",
    gold_types=["rubric"],
    description="Weighted 5-point rubric; offline deterministic stub unless env['judge'] given.",
    tags=["G4", "G5", "G10", "stub"],
)(rubric_judge)
