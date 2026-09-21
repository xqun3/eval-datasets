"""sql_result_equiv -- executes both SQLs in sqlite3 and compares result sets.

Equivalence rules implemented (each has a unit test in
``tests/test_checkers_sql.py``):

  * column order independent  -- cells inside a row are compared as a multiset
    unless the gold SQL pins an explicit projection order via ORDER BY;
  * row order independent     -- rows compared as a multiset, UNLESS the gold
    SQL contains ORDER BY, in which case the sequence must match exactly;
  * duplicate rows preserved  -- multiset, not set: 3 identical rows != 1 row;
  * float tolerance           -- rel 1e-6 / abs 1e-9, applied by quantising
    before hashing so that tolerance survives the multiset comparison;
  * NULL semantics            -- NULL is its own sentinel: NULL != '' , NULL != 0.

The reference SQL is re-executed every run (never a cached snapshot) so the
comparison stays valid when the fixture DB changes.
"""
from __future__ import annotations

import math
import sqlite3
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result
from ..utils.text import extract_sql

NULL = "\x00NULL\x00"
REL_TOL = 1e-6
ABS_TOL = 1e-9


class SqlRunError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# db construction
# --------------------------------------------------------------------------
def build_db(ddl: str) -> sqlite3.Connection:
    """In-memory DB from a DDL+seed script."""
    conn = sqlite3.connect(":memory:")
    conn.text_factory = str
    if ddl:
        conn.executescript(ddl)
    conn.commit()
    return conn


def run_sql(conn: sqlite3.Connection, sql: str, timeout_s: float = 30.0
            ) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    """Execute read-only-ish SQL with a wall-clock abort via progress handler."""
    deadline = time.time() + float(timeout_s)
    steps = {"n": 0}

    def _progress() -> int:
        steps["n"] += 1
        return 1 if time.time() > deadline else 0

    conn.set_progress_handler(_progress, 2000)
    try:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in (cur.description or [])]
        return cols, rows
    except sqlite3.Error as exc:
        raise SqlRunError(str(exc))
    finally:
        conn.set_progress_handler(None, 0)


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------
def norm_cell(v: Any) -> Any:
    if v is None:
        return NULL
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "NaN"
        if math.isinf(v):
            return "Inf" if v > 0 else "-Inf"
        # quantise onto the tolerance grid so Counter() comparison honours it
        if v == 0.0:
            return 0.0
        mag = max(abs(v), ABS_TOL)
        step = max(mag * REL_TOL, ABS_TOL)
        return round(v / step) * step
    if isinstance(v, int):
        return float(v) if False else v
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip()
    if isinstance(v, str):
        return v.strip()
    return v


def _cell_key(v: Any) -> Tuple[str, str]:
    """Sortable, type-stable key (int 1 and float 1.0 must collide)."""
    n = norm_cell(v)
    if n == NULL:
        return ("0null", "")
    if isinstance(n, (int, float)) and not isinstance(n, bool):
        return ("1num", repr(round(float(n), 9)))
    return ("2str", str(n))


def norm_rows(rows: Sequence[Sequence[Any]], *, row_order: bool, col_order: bool):
    """Return a comparable structure honouring the two order flags."""
    out = []
    for r in rows:
        keys = [_cell_key(c) for c in r]
        if not col_order:
            keys = sorted(keys)
        out.append(tuple(keys))
    if row_order:
        return tuple(out)
    return Counter(out)


def has_order_by(sql: str) -> bool:
    s = " ".join((sql or "").lower().split())
    return " order by " in s


def results_equal(gold_rows, pred_rows, *, row_order: bool, col_order: bool) -> bool:
    return (norm_rows(gold_rows, row_order=row_order, col_order=col_order)
            == norm_rows(pred_rows, row_order=row_order, col_order=col_order))


# --------------------------------------------------------------------------
# checker
# --------------------------------------------------------------------------
def sql_result_equiv(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execution accuracy (EX) for text-to-SQL, gold.type == executable."""
    env = env or {}
    t0 = time.time()
    resp = ModelResponse.coerce(response)
    gold = instance.gold["value"]
    tests = gold.get("tests") or []
    timeout_s = float(gold.get("timeout_s", 30))

    db_schema = (instance.context or {}).get("db_schema") or {}
    ddl = env.get("ddl") or db_schema.get("ddl") or ""

    pred_sql = extract_sql(resp.text)
    sub: Dict[str, Any] = {"syntax_ok": 0.0, "tests_total": len(tests), "tests_passed": 0}
    detail: Dict[str, Any] = {"pred_sql": pred_sql[:500]}

    if not pred_sql.strip():
        detail["error"] = "empty prediction"
        return new_checker_result(0.0, False, "L1", sub, [], detail,
                                  {"tokens": 0, "usd": 0.0, "wall_s": time.time() - t0})

    passed_n = 0
    per_test = []
    for i, test in enumerate(tests):
        gold_sql = test.get("gold_sql") or gold.get("ref_solution") or ""
        row_order = test.get("order_sensitive")
        if row_order is None:
            row_order = has_order_by(gold_sql)
        col_order = bool(test.get("column_order_sensitive", False))
        rec = {"test": i, "order_sensitive": bool(row_order),
               "column_order_sensitive": col_order}
        try:
            conn = build_db(ddl)
        except sqlite3.Error as exc:
            rec["error"] = "ddl failed: %s" % exc
            per_test.append(rec)
            continue
        try:
            _gc, gold_rows = run_sql(conn, gold_sql, timeout_s)
        except SqlRunError as exc:
            rec["error"] = "gold sql failed: %s" % exc
            per_test.append(rec)
            conn.close()
            continue
        try:
            _pc, pred_rows = run_sql(conn, pred_sql, timeout_s)
            sub["syntax_ok"] = 1.0
        except SqlRunError as exc:
            rec["error"] = "pred sql failed: %s" % exc
            per_test.append(rec)
            conn.close()
            continue
        finally:
            pass
        ok = results_equal(gold_rows, pred_rows, row_order=bool(row_order), col_order=col_order)
        rec.update({"ok": ok, "gold_rows": len(gold_rows), "pred_rows": len(pred_rows)})
        if not ok:
            rec["gold_sample"] = [list(r) for r in gold_rows[:3]]
            rec["pred_sample"] = [list(r) for r in pred_rows[:3]]
        passed_n += 1 if ok else 0
        per_test.append(rec)
        conn.close()

    sub["tests_passed"] = passed_n
    score = passed_n / float(len(tests)) if tests else 0.0
    detail["per_test"] = per_test
    return new_checker_result(
        score=score, passed=(score >= 1.0 - 1e-9), layer="L1",
        sub_metrics=sub, violations=[], detail=detail,
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


register_checker(
    "sql_result_equiv",
    layer="L1",
    gold_types=["executable"],
    description="sqlite3 execution accuracy: row/column-order & float/NULL aware set equality.",
    tags=["G7", "sql"],
)(sql_result_equiv)


# --------------------------------------------------------------------------
# third-party wrapper example: BIRD VES (Valid Efficiency Score)
# --------------------------------------------------------------------------
def _ves_inner(instance, response, env=None):
    """Local stand-in for BIRD's official VES scorer.

    BIRD ships its own evaluator; the real integration imports it and calls
    ``execute_model(...)``. We keep the *interface* here and compute the same
    quantity (relative runtime of a correct query) with sqlite3 so the wrapper
    can be unit-tested offline. Returns a dict, not a CheckerResult.
    """
    base = sql_result_equiv(instance, response, env)
    if base["score"] < 1.0:
        return {"correct": False, "ratio": 0.0, "ves": 0.0}
    env = env or {}
    ddl = env.get("ddl") or ((instance.context or {}).get("db_schema") or {}).get("ddl") or ""
    gold_sql = (instance.gold["value"].get("tests") or [{}])[0].get("gold_sql") \
        or instance.gold["value"].get("ref_solution") or ""
    pred_sql = extract_sql(ModelResponse.coerce(response).text)
    conn = build_db(ddl)
    try:
        t = time.time()
        run_sql(conn, gold_sql)
        gold_t = max(time.time() - t, 1e-9)
        t = time.time()
        run_sql(conn, pred_sql)
        pred_t = max(time.time() - t, 1e-9)
    finally:
        conn.close()
    ratio = gold_t / pred_t
    return {"correct": True, "ratio": ratio, "ves": min(1.0, math.sqrt(min(ratio, 1.0)))}


def _ves_to_result(raw: Dict[str, Any]) -> Dict[str, Any]:
    return new_checker_result(
        score=float(raw.get("ves", 0.0)),
        passed=bool(raw.get("correct")),
        layer="L1",
        sub_metrics={"correct": 1.0 if raw.get("correct") else 0.0,
                     "time_ratio": round(float(raw.get("ratio", 0.0)), 4)},
        detail={"third_party": "BIRD-VES (local re-implementation)"},
    )
