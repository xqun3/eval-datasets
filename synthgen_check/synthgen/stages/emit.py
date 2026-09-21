"""Stage 10 -- sample_for_human_review, and Stage 11 -- emit.

emit renumbers accepted drafts so the 4-digit sequence in the id is contiguous
per ``(category, subtype)``, stamps ``source`` with the run id, and runs the
final schema validation. Anything that fails validation here is rejected rather
than written out -- an invalid instance must never reach the JSONL.
"""

from __future__ import annotations

from typing import Dict, List

from ..utils.ids import make_id
from . import Draft, RunContext, Stage


class SampleForHumanReviewStage(Stage):
    """Deterministically flag a fraction of accepted drafts for human review."""

    name = "sample_for_human_review"

    def __init__(self, rate: float = 0.2, min_items: int = 1) -> None:
        self.rate = rate
        self.min_items = min_items

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        alive = [d for d in drafts if d.alive and d.instance is not None]
        if not alive:
            return drafts
        scored = sorted(alive, key=lambda d: (d.rng("review").random(), d.seq))
        target = max(self.min_items, int(round(len(alive) * self.rate))) if self.rate > 0 else 0
        target = min(target, len(alive))
        picked = scored[:target]
        picked_ids = {id(d) for d in picked}
        for d in alive:
            flagged = id(d) in picked_ids
            d.meta["human_review"] = {
                "sampled": flagged,
                "reason": "random_sample_rate={}".format(self.rate) if flagged else "",
            }
            if flagged:
                ctx.bump("human_review.sampled")
        # NOTE: ids are still provisional here (EmitStage renumbers them), so the
        # sample rows themselves are materialized at emit time.
        return drafts


class EmitStage(Stage):
    """Renumber ids, stamp ``source``, validate, and collect the final items."""

    name = "emit"

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        counters: Dict[str, int] = ctx.artifacts.setdefault("_id_counters", {})
        emitted = []
        for d in sorted((x for x in drafts if x.alive and x.instance), key=lambda x: x.seq):
            inst = d.instance
            key = "{}|{}".format(inst.category, inst.subtype)
            counters[key] = counters.get(key, 0) + 1
            inst.id = make_id(inst.category, inst.subtype, counters[key])
            inst.source = ctx.source_for(d.meta.get("pipeline_name"))
            errors = inst.validate()
            if errors:
                d.reject(self.name, "schema_invalid")
                d.meta["schema_errors"] = errors
                ctx.bump("emit.schema_invalid")
                counters[key] -= 1
                continue
            d.note(self.name, inst.id)
            ctx.bump("emit.accepted")
            emitted.append(d)
        ctx.artifacts.setdefault("emitted", []).extend(emitted)

        # materialize the human-review sample now that ids are final
        review = ctx.artifacts.setdefault("review_sample", [])
        for d in emitted:
            if (d.meta.get("human_review") or {}).get("sampled"):
                review.append(
                    {
                        "id": d.instance.id,
                        "category": d.instance.category,
                        "difficulty": d.instance.difficulty,
                        "prompt": d.instance.prompt,
                        "gold_type": d.instance.gold.type,
                        "independent_verify_score": (
                            d.meta.get("independent_verify") or {}
                        ).get("score"),
                    }
                )
        return drafts
