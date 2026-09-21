"""G9 verifier: replay the candidate tool trace and diff the resulting state.

Key properties (each covered by a unit test in ``tests/test_g9_tools.py``):

* **状态 diff 判完成率** -- the score is the fraction of expected state facts
  the candidate actually reproduced.
* **不可控字段归一化** -- auto ids / timestamps are normalized away by
  ``MockToolEnv.snapshot(normalize=True)``; the ignore list travels with the
  task in ``gold.value["ignore_fields"]``.
* **多条合法路径** -- any call sequence reaching the target state scores 1.0;
  the gold ships several equivalent paths and the checker reports which one
  (if any) the candidate reproduced call-for-call.
* **越权/破坏性调用** -- recorded in ``violations`` and the sample is forced
  to score 0.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence

from ...registry import CHECKERS
from ...schema import TaskInstance, make_checker_result
from .mock_env import IGNORE_FIELDS, MockToolEnv, diff_facts, state_facts


def parse_trace(candidate: Any) -> Optional[List[Dict[str, Any]]]:
    """Accept a list of calls, a JSON string, or ``{"calls": [...]}``."""
    if candidate is None:
        return None
    if isinstance(candidate, str):
        text = candidate.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            candidate = json.loads(text)
        except ValueError:
            return None
    if isinstance(candidate, dict):
        candidate = candidate.get("calls", candidate.get("trace"))
    if not isinstance(candidate, list):
        return None
    out = []
    for call in candidate:
        if not isinstance(call, dict) or "tool" not in call:
            return None
        out.append({"tool": call["tool"], "args": call.get("args", {}), "actor": call.get("actor")})
    return out


def run_trace_in_env(
    calls: Sequence[Dict[str, Any]], actor: str, role: str
) -> Dict[str, Any]:
    env = MockToolEnv(actor=actor, role=role)
    results = env.run_trace(calls)
    return {
        "env": env,
        "facts": state_facts(env.snapshot(normalize=True)),
        "violations": list(env.violations),
        "results": [r.to_dict() for r in results],
        "errors": [r.error for r in results if not r.ok and not r.violation],
    }


def _same_calls(a: Sequence[Dict[str, Any]], b: Sequence[Dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x.get("tool") != y.get("tool"):
            return False
    return True


@CHECKERS.register("tool_trace_state_diff", layer="L2", category="G9")
def tool_trace_state_diff(instance: TaskInstance, candidate: Any, **kw: Any) -> Dict[str, Any]:
    """Score a candidate tool-call trace by state diff against the target."""
    started = time.time()
    gold = instance.gold.value or {}
    actor = gold.get("actor", "dev_li")
    role = gold.get("role", "developer")
    expected_facts = {k: _tuplify(v) for k, v in (gold.get("target_facts") or {}).items()}
    gold_paths = gold.get("paths") or []

    calls = parse_trace(candidate)
    if calls is None:
        return make_checker_result(
            0.0, False, "L1", {"parsed": 0.0}, [], {"error": "candidate trace 无法解析为调用序列"},
            wall_s=time.time() - started,
        )

    run = run_trace_in_env(calls, actor, role)
    violations = list(run["violations"])
    actual_facts = {k: _tuplify(v) for k, v in run["facts"].items()}
    diff = diff_facts(expected_facts, actual_facts)

    path_matched = -1
    for i, path in enumerate(gold_paths):
        if _same_calls(path, calls):
            path_matched = i
            break

    completion = diff["completion"]
    extra_entities = max(
        0,
        int(actual_facts.get("_counts.issues", 0)) - int(expected_facts.get("_counts.issues", 0)),
    ) + max(
        0,
        int(actual_facts.get("_counts.ci_runs", 0)) - int(expected_facts.get("_counts.ci_runs", 0)),
    )

    score = completion
    passed = completion >= 1.0 and not violations and extra_entities == 0
    if violations:
        # 越权 / 破坏性调用 -> 直接 0 分
        score = 0.0
        passed = False

    return make_checker_result(
        score=score,
        passed=passed,
        layer="L2",
        sub_metrics={
            "state_completion": completion,
            "matched_facts": float(len(diff["matched"])),
            "missing_facts": float(len(diff["missing"])),
            "wrong_facts": float(len(diff["wrong"])),
            "extra_entities": float(extra_entities),
            "path_matched": float(path_matched),
            "calls": float(len(calls)),
            "failed_calls": float(len(run["errors"])),
        },
        violations=violations,
        detail={
            "diff": diff,
            "ignore_fields": list(gold.get("ignore_fields", IGNORE_FIELDS)),
            "call_errors": run["errors"],
            "n_gold_paths": len(gold_paths),
        },
        wall_s=time.time() - started,
    )


def _tuplify(value: Any) -> Any:
    """JSON round-trips tuples into lists; normalize so comparisons hold."""
    if isinstance(value, list):
        return tuple(_tuplify(v) for v in value)
    return value
