"""Pluggable pipeline stages.

Stage order (the canonical synthesis pipeline)::

    seed -> variation -> difficulty_tag -> reverse_generate -> cross_model_generate
         -> independent_verify -> deterministic_recheck -> dedup -> decontaminate
         -> sample_for_human_review -> emit

Module mapping (two stages share a module to keep the tree flat):
    seed.py       SeedStage
    variation.py  VariationStage
    difficulty.py DifficultyTagStage
    reverse.py    ReverseGenerateStage, CrossModelGenerateStage
    verify.py     IndependentVerifyStage
    recheck.py    DeterministicRecheckStage
    dedup.py      DedupStage
    decontam.py   DecontaminateStage
    emit.py       SampleForHumanReviewStage, EmitStage
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models.pool import ModelPool
from ..schema import TaskInstance


class QualityGateError(Exception):
    """Raised by a generator/stage when a draft fails a quality gate.

    The pipeline catches it, marks the draft rejected and (optionally) retries
    with a fresh sub-seed ("打回重试").
    """

    def __init__(self, reason: str, detail: Optional[Dict[str, Any]] = None) -> None:
        self.reason = reason
        self.detail = detail or {}
        super().__init__(reason)


@dataclass
class Draft:
    """A task instance in flight through the pipeline."""

    seq: int
    category: str
    seed: int
    subtype: str = ""
    difficulty: str = "L1"
    lang: str = "zh"
    split: str = "dev"
    attempt: int = 1
    instance: Optional[TaskInstance] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    rejected: bool = False
    reject_stage: str = ""
    reject_reason: str = ""
    stage_log: List[str] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return not self.rejected

    def reject(self, stage: str, reason: str) -> "Draft":
        self.rejected = True
        self.reject_stage = stage
        self.reject_reason = reason
        self.stage_log.append("{}:REJECT({})".format(stage, reason))
        return self

    def note(self, stage: str, msg: str = "ok") -> None:
        self.stage_log.append("{}:{}".format(stage, msg))

    def rng(self, salt: str = "") -> random.Random:
        from ..utils.hashing import stable_int

        return random.Random(stable_int([self.seed, self.seq, self.attempt, salt]))


@dataclass
class RunContext:
    """Everything a stage may need: run identity, model pool, stats sink."""

    run_id: str
    pipeline_name: str
    pool: ModelPool
    config: Any
    stats: Dict[str, Any] = field(default_factory=dict)
    cost: Dict[str, float] = field(default_factory=lambda: {"tokens": 0.0, "usd": 0.0, "wall_s": 0.0})
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def bump(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    def add_cost(self, tokens: int = 0, usd: float = 0.0, wall_s: float = 0.0) -> None:
        self.cost["tokens"] += tokens
        self.cost["usd"] += usd
        self.cost["wall_s"] += wall_s

    def source_for(self, pipeline_name: Optional[str] = None) -> str:
        return "synthetic:{}@{}".format(pipeline_name or self.pipeline_name, self.run_id)


class Stage:
    """Base class for all stages. Subclasses override :meth:`run`."""

    name = "stage"

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:  # pragma: no cover
        raise NotImplementedError

    def __call__(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        return self.run(ctx, drafts)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return "<Stage {}>".format(self.name)
