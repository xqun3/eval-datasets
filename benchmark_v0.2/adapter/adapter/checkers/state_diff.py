"""state_diff -- terminal-state comparison for gold.type == trace (L1).

Gold shape:

    {"final_state": {"<table>": [ {row}, ... ] | {..} , ...},
     "valid_sequences": [ ["tool.a", "tool.b"], ["tool.b", "tool.a"] ],
     "forbidden_calls": ["crm.delete_customer"],
     "ignore_fields": ["id", "created_at"],      # optional, merged with defaults
     "communicate_info": ["订单号 W123"]}         # optional strings the agent must tell the user

Normalisation:
  * auto-increment ids and timestamps are dropped before comparison. Default
    ignore list = anything matching ``^id$|_id$|^uuid$|_at$|^ts$|timestamp|
    created|updated|modified``, overridable per instance;
  * list-valued tables are compared as multisets of normalised rows, so insert
    order does not matter;
  * floats compared with 1e-6 relative tolerance.

Scoring: state match is the gate (0 if final state differs). Among matching
runs, the optional action-sequence and communicate checks contribute
sub-metrics. Any forbidden call is an immediate 0 + violation, mirroring
SCHEMA §0 G9 "越权/破坏性误调用 = 0".
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result
from ..utils.text import normalize_text

DEFAULT_IGNORE = re.compile(
    r"(?i)^(id|uuid|guid|rowid|ts|seq)$|_id$|_at$|^created|^updated|^modified|timestamp|"
    r"^etag$|^version$"
)


def _norm_scalar(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, str):
        return normalize_text(v, drop_punct=False)
    return v


def normalize_value(v: Any, ignore: Sequence[str]) -> Any:
    if isinstance(v, dict):
        out = {}
        for k, val in v.items():
            if DEFAULT_IGNORE.search(str(k)) or str(k) in ignore:
                continue
            out[str(k)] = normalize_value(val, ignore)
        return out
    if isinstance(v, list):
        return [normalize_value(x, ignore) for x in v]
    return _norm_scalar(v)


def _freeze(v: Any) -> Any:
    if isinstance(v, dict):
        return tuple(sorted((k, _freeze(x)) for k, x in v.items()))
    if isinstance(v, list):
        return tuple(sorted((repr(_freeze(x)) for x in v)))
    return v


def states_equal(gold: Dict[str, Any], actual: Dict[str, Any], ignore: Sequence[str]
                 ) -> Tuple[bool, List[str]]:
    """Compare only the tables the gold pins (partial terminal state)."""
    diffs: List[str] = []
    for table, gold_rows in (gold or {}).items():
        if table not in (actual or {}):
            diffs.append("missing table/key: %s" % table)
            continue
        g = normalize_value(gold_rows, ignore)
        a = normalize_value(actual[table], ignore)
        if isinstance(g, list) and isinstance(a, list):
            if sorted(repr(_freeze(x)) for x in g) != sorted(repr(_freeze(x)) for x in a):
                diffs.append("%s: %d gold rows vs %d actual rows differ" % (table, len(g), len(a)))
        elif _freeze(g) != _freeze(a):
            diffs.append("%s: value mismatch" % table)
    return (not diffs), diffs


def call_names(resp: ModelResponse) -> List[str]:
    return [str(c.get("name", "")) for c in resp.tool_calls if c.get("name")]


def sequence_matches(actual: List[str], valid_sequences: List[List[str]]) -> Tuple[bool, int]:
    """A sequence is satisfied when it appears as a *subsequence* of the trace
    (extra read-only calls in between are tolerated)."""
    if not valid_sequences:
        return True, -1
    for idx, seq in enumerate(valid_sequences):
        it = iter(actual)
        if all(any(a == step for a in it) for step in seq):
            return True, idx
    return False, -1


def state_diff(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Terminal-state equality + multi-path action sequence + forbidden calls."""
    t0 = time.time()
    env = env or {}
    resp = ModelResponse.coerce(response)
    gv = instance.gold["value"]
    ignore = list(gv.get("ignore_fields") or []) + list(env.get("ignore_fields") or [])

    actual_state = resp.final_state if resp.final_state is not None else {}
    ok_state, diffs = states_equal(gv.get("final_state") or {}, actual_state, ignore)

    names = call_names(resp)
    ok_seq, seq_idx = sequence_matches(names, gv.get("valid_sequences") or [])

    forbidden = [f for f in (gv.get("forbidden_calls") or []) if f in names]
    comm = [c for c in (gv.get("communicate_info") or [])
            if normalize_text(c) and normalize_text(c) in normalize_text(resp.text)]
    comm_total = len(gv.get("communicate_info") or [])
    comm_score = (len(comm) / float(comm_total)) if comm_total else 1.0

    violations: List[str] = []
    if forbidden:
        violations.append("调用了禁止的工具: %s" % ", ".join(forbidden))

    if forbidden:
        score = 0.0
    elif not ok_state:
        score = 0.0
    else:
        score = 0.7 + 0.15 * (1.0 if ok_seq else 0.0) + 0.15 * comm_score

    return new_checker_result(
        score=score,
        passed=(score >= 0.999),
        layer="L1",
        sub_metrics={"state_match": 1.0 if ok_state else 0.0,
                     "sequence_match": 1.0 if ok_seq else 0.0,
                     "matched_sequence_index": seq_idx,
                     "communicate_recall": round(comm_score, 6),
                     "forbidden_calls_hit": len(forbidden),
                     "calls_made": len(names)},
        violations=violations,
        detail={"diffs": diffs[:10], "calls": names[:30],
                "ignore_fields": ignore},
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


register_checker(
    "state_diff",
    layer="L1",
    gold_types=["trace"],
    description="Terminal DB-state diff ignoring auto ids/timestamps, multi-path tolerant.",
    tags=["G9", "G8"],
)(state_diff)
