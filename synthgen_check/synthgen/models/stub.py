"""Deterministic stub LLM client used by ``--dry-run``.

No network, no randomness beyond a seeded RNG: the same ``(seed, provider,
model, messages, task)`` always produces the same text, which is what makes
whole-pipeline runs byte-for-byte reproducible.
"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List

from ..utils.hashing import stable_int
from .base import LLMClient, LLMResponse, Message

_ZH_CONNECTORS = ["请", "麻烦", "需要你", "帮我"]
_ZH_SUFFIX = ["。", "，并给出结果。", "，注意口径一致。", "。"]


class StubLLMClient(LLMClient):
    """A fake but *deterministic* LLM.

    Behaviour is driven by the ``task`` keyword passed to :meth:`complete`:

    ``paraphrase``  -> lightly rewrites the Chinese prompt (variation stage)
    ``distractor``  -> emits a distractor sentence to append to the prompt
    ``solve``       -> returns the candidate solution handed in via ``gold_hint``
                       (optionally perturbed, to emulate a weaker generator)
    ``judge``       -> returns a JSON verdict consumed by independent_verify
    otherwise       -> a deterministic filler sentence
    """

    def __init__(self, provider: str, model: str = "stub-1", seed: int = 0, quality: float = 0.9) -> None:
        self.provider = provider
        self.model = model
        self.seed = seed
        self.quality = quality
        self.calls = 0

    # -- helpers -----------------------------------------------------------
    def _rng(self, messages: List[Message], task: str) -> random.Random:
        key = {
            "seed": self.seed,
            "provider": self.provider,
            "model": self.model,
            "task": task,
            "messages": messages,
        }
        return random.Random(stable_int(key))

    # -- LLMClient ---------------------------------------------------------
    def complete(self, messages: List[Message], **kw: Any) -> LLMResponse:
        self.calls += 1
        task = str(kw.get("task", "generic"))
        rng = self._rng(messages, task)
        last = messages[-1]["content"] if messages else ""
        handler = getattr(self, "_task_" + task, None)
        if handler is None:
            text = self._task_generic(last, rng, kw)
        else:
            text = handler(last, rng, kw)
        tokens = max(1, (len(last) + len(text)) // 4)
        return LLMResponse(
            text=text,
            tokens=tokens,
            provider=self.provider,
            model=self.model,
            usd=round(tokens * 1e-6, 8),
            wall_s=0.0,
            raw={"task": task, "stub": True},
        )

    # -- per-task behaviours ----------------------------------------------
    def _task_generic(self, last: str, rng: random.Random, kw: Dict[str, Any]) -> str:
        return "[stub:{}:{}] {}".format(self.provider, self.model, last[:80])

    def _task_paraphrase(self, last: str, rng: random.Random, kw: Dict[str, Any]) -> str:
        base = str(kw.get("prompt", last)).strip()
        head = rng.choice(_ZH_CONNECTORS)
        tail = rng.choice(_ZH_SUFFIX)
        body = base.rstrip("。\n ")
        return "{}{}{}".format(head, body, tail)

    def _task_distractor(self, last: str, rng: random.Random, kw: Dict[str, Any]) -> str:
        pool = [
            "（备注：报表口径以财务确认版本为准）",
            "（备注：上游系统存在少量重复写入，已在数据层去重）",
            "（备注：该需求由运营同学在周会上提出）",
            "（备注：历史归档数据不在本次范围内）",
        ]
        return rng.choice(pool)

    def _task_solve(self, last: str, rng: random.Random, kw: Dict[str, Any]) -> str:
        """Emulate a generator model attempting the task.

        ``gold_hint`` is the reference answer; with probability ``1-quality``
        the stub returns a deliberately broken answer so that the
        cross-model + deterministic-recheck gates have something to catch.
        """
        gold_hint = kw.get("gold_hint")
        if gold_hint is None:
            return self._task_generic(last, rng, kw)
        if rng.random() <= self.quality:
            return gold_hint if isinstance(gold_hint, str) else json.dumps(gold_hint, ensure_ascii=False)
        broken = kw.get("broken_hint")
        if broken is not None:
            return broken if isinstance(broken, str) else json.dumps(broken, ensure_ascii=False)
        return "-- stub could not solve"

    def _task_judge(self, last: str, rng: random.Random, kw: Dict[str, Any]) -> str:
        """Third-party verifier verdict as JSON (consumed by stages/verify.py)."""
        floor = float(kw.get("floor", 0.72))
        score = round(floor + (1.0 - floor) * rng.random(), 3)
        issues = []
        if score < floor + 0.05:
            issues.append("prompt 与 gold 的口径描述不够明确")
        return json.dumps(
            {
                "consistent": score >= 0.7,
                "score": score,
                "issues": issues,
                "reviewed_by": {"provider": self.provider, "model": self.model},
            },
            ensure_ascii=False,
        )
