"""Stage 1 -- seed: turn a request (category, n, seed) into seed specs."""

from __future__ import annotations

from typing import List

from ..registry import GENERATORS, load_builtins
from ..utils.hashing import stable_int
from . import Draft, RunContext, Stage

#: default split ratios used when the caller does not pin a split
DEFAULT_SPLIT_RATIOS = (("dev", 0.70), ("test", 0.25), ("canary", 0.05))


def pick_split(rnd_value: float) -> str:
    acc = 0.0
    for name, ratio in DEFAULT_SPLIT_RATIOS:
        acc += ratio
        if rnd_value < acc:
            return name
    return DEFAULT_SPLIT_RATIOS[-1][0]


class SeedStage(Stage):
    """Produce ``n`` seed drafts for a category, deterministically from ``seed``."""

    name = "seed"

    def __init__(self, category: str, n: int, seed: int, lang: str = "zh", split: str = "auto") -> None:
        load_builtins()
        self.category = category
        self.n = n
        self.seed = seed
        self.lang = lang
        self.split = split
        self.generator = GENERATORS.get(category)

    def make_drafts(self, start_seq: int, count: int, attempt: int = 1) -> List[Draft]:
        subtypes = list(self.generator.subtypes)
        out: List[Draft] = []
        for i in range(count):
            seq = start_seq + i
            item_seed = stable_int([self.seed, self.category, seq, attempt], bits=31)
            draft = Draft(
                seq=seq,
                category=self.category,
                seed=item_seed,
                lang=self.lang,
                attempt=attempt,
            )
            rng = draft.rng("seed")
            draft.subtype = subtypes[seq % len(subtypes)]
            draft.split = self.split if self.split != "auto" else pick_split(rng.random())
            draft.meta["seed_spec"] = {
                "category": self.category,
                "subtype": draft.subtype,
                "root_seed": self.seed,
                "item_seed": item_seed,
                "attempt": attempt,
            }
            draft.note(self.name)
            out.append(draft)
        return out

    def run(self, ctx: RunContext, drafts: List[Draft]) -> List[Draft]:
        if drafts:
            # re-entrant call (retry round): drafts already exist
            return drafts
        new = self.make_drafts(0, self.n)
        ctx.bump("seed.created", len(new))
        return new
