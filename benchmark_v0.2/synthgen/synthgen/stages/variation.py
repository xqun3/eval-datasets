"""Stage 2 -- variation: diversify each seed spec before gold construction.

Uses the ``rewriter`` and ``distractor`` roles of the pool. In ``--dry-run``
both are deterministic stubs, so the variation text is reproducible.
"""

from __future__ import annotations

from typing import List

from ..models.base import system, user
from . import Draft, RunContext, Stage

BUSINESS_FLAVORS = [
    "季度经营分析会",
    "618 大促复盘",
    "月度对账",
    "客诉根因排查",
    "线上故障复盘",
    "渠道投放评估",
]
PERSONAS = ["数据分析师", "运营同学", "研发同学", "业务负责人", "值班 SRE"]


class VariationStage(Stage):
    """Attach a scenario flavor + optional distractor sentence to each draft."""

    name = "variation"

    def __init__(self, distractor_rate: float = 0.35) -> None:
        self.distractor_rate = distractor_rate

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        rewriter = ctx.pool.get("rewriter")
        distractor_model = ctx.pool.get("distractor")
        for d in drafts:
            if not d.alive:
                continue
            rng = d.rng("variation")
            flavor = rng.choice(BUSINESS_FLAVORS)
            persona = rng.choice(PERSONAS)
            resp = rewriter.complete(
                [
                    system("你是评测数据的场景改写助手。"),
                    user("为一个 {} 类任务生成场景背景，场景={}，提问人={}".format(d.category, flavor, persona)),
                ],
                task="paraphrase",
                prompt="{}场景下，{}需要一份数据支撑".format(flavor, persona),
            )
            ctx.add_cost(resp.tokens, resp.usd, resp.wall_s)
            distractor_text = ""
            if rng.random() < self.distractor_rate:
                dresp = distractor_model.complete(
                    [user("为场景 {} 生成一句无关但看似相关的干扰信息".format(flavor))],
                    task="distractor",
                )
                ctx.add_cost(dresp.tokens, dresp.usd, dresp.wall_s)
                distractor_text = dresp.text
            d.meta["variation"] = {
                "flavor": flavor,
                "persona": persona,
                "scene_line": resp.text,
                "distractor": distractor_text,
                "rewriter": resp.provider + ":" + resp.model,
            }
            d.note(self.name)
            ctx.bump("variation.applied")
            if distractor_text:
                ctx.bump("variation.distractor_injected")
        return drafts
