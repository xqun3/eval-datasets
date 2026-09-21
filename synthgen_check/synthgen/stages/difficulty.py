"""Stage 3 -- difficulty_tag.

Assigns the *target* difficulty before generation (the category generator uses
it to pick a template) and re-tags afterwards from the measured complexity of
the produced gold, so the label always matches the artifact.
"""

from __future__ import annotations

from typing import List

from ..registry import GENERATORS
from . import Draft, RunContext, Stage

DEFAULT_MIX = (("L1", 0.3), ("L2", 0.4), ("L3", 0.3))


def pick_difficulty(value: float) -> str:
    acc = 0.0
    for name, ratio in DEFAULT_MIX:
        acc += ratio
        if value < acc:
            return name
    return DEFAULT_MIX[-1][0]


class DifficultyTagStage(Stage):
    """Pre-generation difficulty assignment."""

    name = "difficulty_tag"

    def __init__(self, difficulty: str = "auto") -> None:
        self.difficulty = difficulty

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        for d in drafts:
            if not d.alive:
                continue
            rng = d.rng("difficulty")
            d.difficulty = self.difficulty if self.difficulty != "auto" else pick_difficulty(rng.random())
            d.meta["difficulty_requested"] = d.difficulty
            d.note(self.name, d.difficulty)
            ctx.bump("difficulty.{}".format(d.difficulty))
        return drafts


class DifficultyRetagStage(Stage):
    """Post-generation re-tag: ask the generator to measure what it actually built."""

    name = "difficulty_retag"

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        for d in drafts:
            if not d.alive or d.instance is None:
                continue
            gen = GENERATORS.get(d.category)
            measure = getattr(gen, "measure_difficulty", None)
            if measure is None:
                continue
            measured = measure(d.instance)
            if measured and measured != d.instance.difficulty:
                d.meta["difficulty_retagged_from"] = d.instance.difficulty
                d.instance.difficulty = measured
                d.difficulty = measured
                ctx.bump("difficulty.retagged")
            d.note(self.name, d.instance.difficulty)
        return drafts
