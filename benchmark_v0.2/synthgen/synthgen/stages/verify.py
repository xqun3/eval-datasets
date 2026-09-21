"""Stage 6 -- independent_verify (第三方验证, model based, layer L3).

The verifier client MUST come from a provider that is not used anywhere on the
generation side. That is asserted here at runtime before any verifier call.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..models.base import system, user
from ..registry import VERIFIERS
from ..schema import TaskInstance, make_checker_result
from . import Draft, RunContext, Stage


@VERIFIERS.register("llm_consistency_judge", layer="L3")
def llm_consistency_judge(instance: TaskInstance, ctx: RunContext, **kw: Any) -> Dict[str, Any]:
    """Ask the third-party verifier model whether prompt and gold agree.

    Returns a CheckerResult-shaped dict (layer ``L3``).
    """
    verifier = ctx.pool.get("verifier")  # re-asserts the cross-provider rule
    payload = {
        "prompt": instance.prompt,
        "category": instance.category,
        "difficulty": instance.difficulty,
        "gold_type": instance.gold.type,
        "must_not": instance.must_not,
    }
    resp = verifier.complete(
        [
            system("你是独立第三方评审模型，只判断 prompt 与 gold 是否自洽、是否可解、是否含歧义。"),
            user(json.dumps(payload, ensure_ascii=False)),
        ],
        task="judge",
    )
    ctx.add_cost(resp.tokens, resp.usd, resp.wall_s)
    try:
        verdict = json.loads(resp.text)
    except (ValueError, TypeError):
        verdict = {"consistent": False, "score": 0.0, "issues": ["verifier 输出无法解析为 JSON"]}
    score = float(verdict.get("score", 0.0))
    return make_checker_result(
        score=score,
        passed=bool(verdict.get("consistent")) and score > 0.0,
        layer="L3",
        sub_metrics={"consistency": score},
        violations=[],
        detail={
            "issues": verdict.get("issues", []),
            "verifier_provider": verifier.provider,
            "verifier_model": verifier.model,
        },
        tokens=resp.tokens,
        usd=resp.usd,
        wall_s=resp.wall_s,
    )


class IndependentVerifyStage(Stage):
    """Run the third-party model verifier and gate on its score."""

    name = "independent_verify"

    def __init__(self, verifier_name: str = "llm_consistency_judge", threshold: float = 0.7) -> None:
        self.verifier_name = verifier_name
        self.threshold = threshold

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        # 红线: verifier 的 provider 不得等于任何生成侧角色的 provider
        ctx.pool.assert_cross_provider()
        verifier_fn = VERIFIERS.get(self.verifier_name)
        for d in drafts:
            if not d.alive or d.instance is None:
                continue
            result = verifier_fn(d.instance, ctx)
            d.meta["independent_verify"] = result
            if result["score"] < self.threshold or not result["passed"]:
                d.reject(self.name, "independent_verify_below_threshold")
                ctx.bump("independent_verify.rejected")
                continue
            d.note(self.name, "{:.2f}".format(result["score"]))
            ctx.bump("independent_verify.passed")
        return drafts
