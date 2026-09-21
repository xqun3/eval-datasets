"""Pipeline orchestration: stage wiring, quality gates, retry, run_id, stats."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .models.pool import ModelPool, default_dry_run_pool
from .registry import GENERATORS, load_builtins
from .schema import TaskInstance
from .stages import Draft, RunContext, Stage
from .stages.decontam import DecontaminateStage
from .stages.dedup import DedupStage
from .stages.difficulty import DifficultyRetagStage, DifficultyTagStage
from .stages.emit import EmitStage, SampleForHumanReviewStage
from .stages.recheck import DeterministicRecheckStage
from .stages.reverse import CrossModelGenerateStage, ReverseGenerateStage
from .stages.seed import SeedStage
from .stages.variation import VariationStage
from .utils.hashing import short_hash


@dataclass
class PipelineConfig:
    """All knobs of one generation run."""

    category: str = "G7"
    n: int = 5
    seed: int = 0
    lang: str = "zh"
    split: str = "auto"
    difficulty: str = "auto"
    dry_run: bool = True
    max_attempts: int = 3
    dedup_threshold: float = 0.85
    verify_threshold: float = 0.7
    review_rate: float = 0.2
    distractor_rate: float = 0.35
    decontam_corpus: Optional[str] = None
    exclude_providers: List[str] = field(default_factory=list)
    model_config: Dict[str, Any] = field(default_factory=dict)
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    run_id: str
    pipeline_name: str
    items: List[TaskInstance]
    stats: Dict[str, Any]
    rejects: List[Dict[str, Any]]
    review_sample: List[Dict[str, Any]]
    cost: Dict[str, float]
    pool: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pipeline": self.pipeline_name,
            "n_items": len(self.items),
            "stats": self.stats,
            "cost": self.cost,
            "pool": self.pool,
            "rejects": self.rejects,
            "review_sample": self.review_sample,
        }


class Pipeline:
    """Runs the 11 canonical stages with quality gates and bounded retries."""

    def __init__(self, config: PipelineConfig, pool: Optional[ModelPool] = None) -> None:
        load_builtins()
        self.config = config
        if config.category not in GENERATORS:
            raise KeyError(
                "no generator registered for category {!r}; available: {}".format(
                    config.category, GENERATORS.names()
                )
            )
        self.generator = GENERATORS.get(config.category)
        self.pipeline_name = getattr(self.generator, "pipeline_name", config.category.lower())
        if pool is None:
            pool = ModelPool.from_config(
                config.model_config or None,
                dry_run=config.dry_run,
                seed=config.seed,
                exclude_providers=config.exclude_providers,
            )
        self.pool = pool
        # 红线断言在流水线构造时就跑一次, 失败就不要开工
        self.pool.assert_cross_provider()
        self.run_id = config.run_id or self._make_run_id()

        self.seed_stage = SeedStage(config.category, config.n, config.seed, config.lang, config.split)
        self.dedup_stage = DedupStage(threshold=config.dedup_threshold)
        self.stages: List[Stage] = [
            VariationStage(distractor_rate=config.distractor_rate),
            DifficultyTagStage(config.difficulty),
            ReverseGenerateStage(),
            DifficultyRetagStage(),
            CrossModelGenerateStage(),
            DeterministicRecheckStage(),
            self.dedup_stage,
            DecontaminateStage(corpus_path=config.decontam_corpus),
        ]
        # independent_verify sits between cross_model_generate and recheck
        from .stages.verify import IndependentVerifyStage

        self.stages.insert(5, IndependentVerifyStage(threshold=config.verify_threshold))
        self.review_stage = SampleForHumanReviewStage(rate=config.review_rate)
        self.emit_stage = EmitStage()

    # -- identity ----------------------------------------------------------
    def _make_run_id(self) -> str:
        """Deterministic run id: same config + seed -> same run id."""
        return "r" + short_hash(
            {
                "category": self.config.category,
                "n": self.config.n,
                "seed": self.config.seed,
                "lang": self.config.lang,
                "split": self.config.split,
                "difficulty": self.config.difficulty,
                "dry_run": self.config.dry_run,
                "pipeline": self.pipeline_name,
                "providers": self.pool.provider_names(),
            },
            10,
        )

    def stage_names(self) -> List[str]:
        return (
            [self.seed_stage.name]
            + [s.name for s in self.stages]
            + [self.review_stage.name, self.emit_stage.name]
        )

    # -- execution ---------------------------------------------------------
    def run(self) -> PipelineResult:
        cfg = self.config
        ctx = RunContext(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            pool=self.pool,
            config=cfg,
            stats={},
        )
        accepted: List[Draft] = []
        rejects: List[Draft] = []
        next_seq = 0
        wanted = cfg.n

        for attempt in range(1, cfg.max_attempts + 1):
            need = wanted - len(accepted)
            if need <= 0:
                break
            ctx.bump("attempts.round_{}".format(attempt))
            drafts = self.seed_stage.make_drafts(next_seq, need, attempt=attempt)
            next_seq += need
            for stage in self.stages:
                drafts = stage.run(ctx, drafts)
            alive = [d for d in drafts if d.alive]
            rejects.extend(d for d in drafts if not d.alive)
            accepted.extend(alive)
            ctx.bump("accepted_after_round_{}".format(attempt), len(alive))

        accepted = accepted[:wanted]
        self.review_stage.run(ctx, accepted)
        self.emit_stage.run(ctx, accepted)
        rejects.extend(d for d in accepted if not d.alive)
        final = [d for d in accepted if d.alive and d.instance is not None]

        stats = self._build_stats(ctx, final, rejects, wanted)
        return PipelineResult(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            items=[d.instance for d in final],
            stats=stats,
            rejects=[
                {
                    "seq": d.seq,
                    "attempt": d.attempt,
                    "stage": d.reject_stage,
                    "reason": d.reject_reason,
                    "subtype": d.subtype,
                    "difficulty": d.difficulty,
                }
                for d in rejects
            ],
            review_sample=ctx.artifacts.get("review_sample", []),
            cost=dict(ctx.cost),
            pool=self.pool.describe(),
        )

    def _build_stats(
        self, ctx: RunContext, final: Sequence[Draft], rejects: Sequence[Draft], wanted: int
    ) -> Dict[str, Any]:
        by_difficulty: Dict[str, int] = {}
        by_split: Dict[str, int] = {}
        by_subtype: Dict[str, int] = {}
        solved = 0
        verify_scores: List[float] = []
        for d in final:
            inst = d.instance
            by_difficulty[inst.difficulty] = by_difficulty.get(inst.difficulty, 0) + 1
            by_split[inst.split] = by_split.get(inst.split, 0) + 1
            by_subtype[inst.subtype] = by_subtype.get(inst.subtype, 0) + 1
            if d.meta.get("candidate_solved"):
                solved += 1
            iv = d.meta.get("independent_verify")
            if iv:
                verify_scores.append(iv["score"])
        reject_reasons: Dict[str, int] = {}
        for d in rejects:
            key = "{}::{}".format(d.reject_stage, d.reject_reason.split(" (")[0])
            reject_reasons[key] = reject_reasons.get(key, 0) + 1
        return {
            "run_id": self.run_id,
            "pipeline": self.pipeline_name,
            "requested": wanted,
            "emitted": len(final),
            "shortfall": max(0, wanted - len(final)),
            "rejected": len(rejects),
            "yield_rate": round(len(final) / float(wanted), 4) if wanted else 0.0,
            "by_difficulty": by_difficulty,
            "by_split": by_split,
            "by_subtype": by_subtype,
            "candidate_solve_rate": round(solved / float(len(final)), 4) if final else 0.0,
            "avg_independent_verify_score": (
                round(sum(verify_scores) / len(verify_scores), 4) if verify_scores else 0.0
            ),
            "reject_reasons": reject_reasons,
            "stage_counters": dict(sorted(ctx.stats.items())),
            "stages": self.stage_names(),
            "human_review_sampled": len(ctx.artifacts.get("review_sample", [])),
        }
