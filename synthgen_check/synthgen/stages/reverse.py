"""Stage 4 -- reverse_generate, and Stage 5 -- cross_model_generate.

reverse_generate: 先构造 gold, 再倒推 prompt。The category generator owns the
domain logic; this stage only wires it into the pipeline and converts quality
gate failures into rejections.

cross_model_generate: a *generation side* model (provider A) attempts the task.
This is a solvability / discrimination probe, and its output is what
``deterministic_recheck`` later scores. The verifier provider must differ from
this model's provider -- asserted here and again in independent_verify.
"""

from __future__ import annotations

from typing import List

from ..models.base import system, user
from ..registry import GENERATORS
from . import Draft, QualityGateError, RunContext, Stage


class ReverseGenerateStage(Stage):
    """Build gold first, then derive the natural-language prompt from it."""

    name = "reverse_generate"

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        for d in drafts:
            if not d.alive:
                continue
            gen = GENERATORS.get(d.category)
            try:
                instance = gen.build(d, ctx)
            except QualityGateError as exc:
                d.reject(self.name, exc.reason)
                d.meta["gate_detail"] = exc.detail
                ctx.bump("reverse.gate_rejected")
                ctx.bump("gate.{}".format(exc.reason))
                continue
            d.instance = instance
            d.note(self.name)
            ctx.bump("reverse.built")
        return drafts


class CrossModelGenerateStage(Stage):
    """Have the ``generator`` role attempt the task (cross-model probe)."""

    name = "cross_model_generate"

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        gen_client = ctx.pool.get("generator")
        verifier_client = ctx.pool.get("verifier")
        # 红线断言: 生成模型与验证模型不同源
        ctx.pool.assert_verifier_differs(gen_client, verifier_client)
        ctx.pool.assert_cross_provider()

        for d in drafts:
            if not d.alive or d.instance is None:
                continue
            gen = GENERATORS.get(d.category)
            hint = gen.reference_candidate(d.instance)
            broken = gen.broken_candidate(d.instance)
            resp = gen_client.complete(
                [
                    system("你是被测模型，请完成下面的任务。"),
                    user(d.instance.prompt),
                ],
                task="solve",
                gold_hint=hint,
                broken_hint=broken,
            )
            ctx.add_cost(resp.tokens, resp.usd, resp.wall_s)
            d.meta["candidate"] = {
                "text": resp.text,
                "provider": resp.provider,
                "model": resp.model,
                "role": "generator",
            }
            d.meta["cross_model"] = {
                "generator_provider": gen_client.provider,
                "generator_model": gen_client.model,
                "verifier_provider": verifier_client.provider,
                "verifier_model": verifier_client.model,
                "same_provider": gen_client.provider == verifier_client.provider,
            }
            d.note(self.name, resp.provider)
            ctx.bump("cross_model.attempted")
        return drafts
