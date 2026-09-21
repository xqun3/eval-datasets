"""Stage 7 -- deterministic_recheck (layer L1/L2, no model involved).

Two things happen here:

1. *self-consistency*: the registered checker scores the gold's own reference
   answer. Anything below 1.0 means the task is internally broken -> reject.
2. *discrimination*: the cross-model candidate produced in stage 5 is scored
   with the same checker. Its score is recorded (and a deliberately broken
   answer is scored too) so the dataset carries an honest difficulty signal.
"""

from __future__ import annotations

from typing import List

from ..registry import CHECKERS, GENERATORS
from ..schema import validate_checker_result
from . import Draft, RunContext, Stage


class DeterministicRecheckStage(Stage):
    """Execute the deterministic checker; reject internally inconsistent gold."""

    name = "deterministic_recheck"

    def __init__(self, require_self_score: float = 1.0, check_discrimination: bool = True) -> None:
        self.require_self_score = require_self_score
        self.check_discrimination = check_discrimination

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        for d in drafts:
            if not d.alive or d.instance is None:
                continue
            inst = d.instance
            checker = CHECKERS.get(inst.checker)
            gen = GENERATORS.get(d.category)

            self_result = checker(inst, gen.reference_candidate(inst))
            shape_errors = validate_checker_result(self_result)
            if shape_errors:
                d.reject(self.name, "checker_result_shape_invalid")
                d.meta["checker_shape_errors"] = shape_errors
                ctx.bump("recheck.shape_invalid")
                continue
            d.meta["recheck_self"] = self_result
            if self_result["score"] < self.require_self_score or self_result["violations"]:
                d.reject(self.name, "gold_self_check_failed")
                ctx.bump("recheck.self_failed")
                continue

            if self.check_discrimination:
                broken = gen.broken_candidate(inst)
                broken_result = checker(inst, broken)
                d.meta["recheck_broken"] = broken_result
                if broken_result["score"] >= self.require_self_score:
                    d.reject(self.name, "no_discrimination_broken_answer_also_passes")
                    ctx.bump("recheck.no_discrimination")
                    continue

            cand = d.meta.get("candidate")
            if cand:
                cand_result = checker(inst, cand["text"])
                d.meta["recheck_candidate"] = cand_result
                d.meta["candidate_solved"] = bool(cand_result["passed"])
                ctx.bump("recheck.candidate_solved" if cand_result["passed"] else "recheck.candidate_failed")

            d.note(self.name)
            ctx.bump("recheck.passed")
        return drafts
