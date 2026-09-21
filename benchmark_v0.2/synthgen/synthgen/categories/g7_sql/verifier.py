"""G7 verifier: execute the candidate SQL and compare result sets.

Equivalence rules implemented here (each has a unit test in
``tests/test_g7_sql.py``):

* 列序无关 -- columns are aligned by name, or by searching permutations when
  the candidate renamed them
* 行序无关 -- unless the gold SQL has a top level ``ORDER BY``
* 浮点容差 -- absolute + relative tolerance (default 1e-6)
* NULL 处理 -- ``NULL`` equals only ``NULL`` (never 0 / '' / False)
* 重复行 -- multiset comparison, de-duplicating an answer loses points

Safety: destructive statements are caught twice -- by a static scan *and* by a
sqlite3 authorizer that denies every write at the engine level.
"""

from __future__ import annotations

import re
import sqlite3
import time
from itertools import permutations
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...registry import CHECKERS
from ...schema import TaskInstance, make_checker_result

# --------------------------------------------------------------------------
# SQL text utilities
# --------------------------------------------------------------------------

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING_LIT = re.compile(r"'(?:[^']|'')*'")
_FENCE = re.compile(r"^\s*```(?:sql)?\s*|\s*```\s*$", re.I)

DESTRUCTIVE_KEYWORDS = (
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "ATTACH",
    "DETACH",
    "TRUNCATE",
    "REPLACE",
    "VACUUM",
    "PRAGMA",
    "CREATE",
    "REINDEX",
)


def strip_sql_noise(sql: str) -> str:
    """Remove markdown fences, comments and string literals (for static scans)."""
    text = _FENCE.sub("", sql or "")
    text = _BLOCK_COMMENT.sub(" ", text)
    text = _LINE_COMMENT.sub(" ", text)
    return _STRING_LIT.sub("''", text)


def clean_sql(sql: str) -> str:
    """Strip markdown fences / trailing semicolons -- keeps the executable text."""
    text = _FENCE.sub("", (sql or "").strip())
    return text.strip().rstrip(";").strip()


def scan_destructive(sql: str) -> List[str]:
    """Return the destructive keywords present outside strings/comments."""
    scrubbed = strip_sql_noise(sql).upper()
    hits = []
    for kw in DESTRUCTIVE_KEYWORDS:
        if re.search(r"\b{}\b".format(kw), scrubbed):
            hits.append(kw)
    return hits


def scan_privacy(sql: str, privacy_cols: Sequence[str]) -> List[str]:
    scrubbed = strip_sql_noise(sql).lower()
    return [c for c in privacy_cols if re.search(r"\b{}\b".format(re.escape(c.lower())), scrubbed)]


def has_top_level_order_by(sql: str) -> bool:
    """True when the statement's outermost query carries an ORDER BY."""
    text = strip_sql_noise(sql).upper()
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith("ORDER", i):
            if re.match(r"ORDER\s+BY\b", text[i:]):
                before = text[i - 1] if i else " "
                if not before.isalnum() and before != "_":
                    return True
        i += 1
    return False


def count_statements(sql: str) -> int:
    scrubbed = strip_sql_noise(sql).strip().rstrip(";")
    return len([s for s in scrubbed.split(";") if s.strip()])


# --------------------------------------------------------------------------
# value / row comparison
# --------------------------------------------------------------------------


def values_equal(a: Any, b: Any, tol: float = 1e-6) -> bool:
    """Tolerant scalar equality with strict NULL semantics."""
    if a is None or b is None:
        return a is None and b is None
    a_num = isinstance(a, (int, float)) and not isinstance(a, bool)
    b_num = isinstance(b, (int, float)) and not isinstance(b, bool)
    if a_num and b_num:
        fa, fb = float(a), float(b)
        if fa == fb:
            return True
        diff = abs(fa - fb)
        return diff <= tol or diff <= tol * max(abs(fa), abs(fb))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if a_num != b_num:
        return False
    return a == b


def rows_equal(r1: Sequence[Any], r2: Sequence[Any], tol: float = 1e-6) -> bool:
    if len(r1) != len(r2):
        return False
    return all(values_equal(x, y, tol) for x, y in zip(r1, r2))


def multiset_overlap(ref: List[List[Any]], cand: List[List[Any]], tol: float = 1e-6) -> int:
    """Size of the multiset intersection (greedy pairing, tolerance aware)."""
    unused = list(range(len(cand)))
    matched = 0
    for row in ref:
        for pos, idx in enumerate(unused):
            if rows_equal(row, cand[idx], tol):
                matched += 1
                unused.pop(pos)
                break
    return matched


def _permute(rows: List[List[Any]], order: Sequence[int]) -> List[List[Any]]:
    return [[row[i] for i in order] for row in rows]


def align_columns(
    ref_cols: Sequence[str], cand_cols: Sequence[str]
) -> Optional[List[int]]:
    """Return the permutation of candidate columns matching ``ref_cols`` by name."""
    if len(ref_cols) != len(cand_cols):
        return None
    lower_ref = [c.lower() for c in ref_cols]
    lower_cand = [c.lower() for c in cand_cols]
    if sorted(lower_ref) != sorted(lower_cand) or len(set(lower_cand)) != len(lower_cand):
        return None
    return [lower_cand.index(c) for c in lower_ref]


def compare_result_sets(
    ref_cols: Sequence[str],
    ref_rows: List[List[Any]],
    cand_cols: Sequence[str],
    cand_rows: List[List[Any]],
    order_sensitive: bool = False,
    tol: float = 1e-6,
    max_permutation_cols: int = 6,
) -> Dict[str, Any]:
    """Compare two result sets and return metrics + a 0-1 score."""
    detail: Dict[str, Any] = {
        "ref_rows": len(ref_rows),
        "cand_rows": len(cand_rows),
        "ref_cols": list(ref_cols),
        "cand_cols": list(cand_cols),
        "order_sensitive": order_sensitive,
    }
    if len(ref_cols) != len(cand_cols):
        return {
            "score": 0.0,
            "exact": False,
            "column_match": 0.0,
            "row_precision": 0.0,
            "row_recall": 0.0,
            "row_f1": 0.0,
            "order_ok": False,
            "reason": "column_count_mismatch",
            "detail": detail,
        }

    orders: List[Tuple[str, Sequence[int]]] = []
    by_name = align_columns(ref_cols, cand_cols)
    if by_name is not None:
        orders.append(("by_name", by_name))
    orders.append(("identity", list(range(len(ref_cols)))))
    if by_name is None and len(ref_cols) <= max_permutation_cols:
        for perm in permutations(range(len(ref_cols))):
            orders.append(("permutation", list(perm)))

    best: Optional[Dict[str, Any]] = None
    for how, order in orders:
        permuted = _permute(cand_rows, order)
        inter = multiset_overlap(ref_rows, permuted, tol)
        precision = inter / float(len(permuted)) if permuted else (1.0 if not ref_rows else 0.0)
        recall = inter / float(len(ref_rows)) if ref_rows else (1.0 if not permuted else 0.0)
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        multiset_ok = inter == len(ref_rows) == len(permuted)
        order_ok = True
        if order_sensitive:
            order_ok = len(ref_rows) == len(permuted) and all(
                rows_equal(a, b, tol) for a, b in zip(ref_rows, permuted)
            )
        exact = bool(multiset_ok and order_ok)
        score = 1.0 if exact else (f1 * 0.5 if (multiset_ok and not order_ok) else f1 * 0.8)
        cand = {
            "score": round(score, 6),
            "exact": exact,
            "column_match": 1.0 if how == "by_name" else (0.5 if how == "permutation" else 1.0),
            "row_precision": round(precision, 6),
            "row_recall": round(recall, 6),
            "row_f1": round(f1, 6),
            "order_ok": order_ok,
            "reason": "ok" if exact else ("row_order_mismatch" if multiset_ok else "row_set_mismatch"),
            "detail": dict(detail, column_alignment=how, column_order=list(order)),
        }
        if best is None or cand["score"] > best["score"]:
            best = cand
        if best["score"] >= 1.0:
            break
    assert best is not None
    return best


# --------------------------------------------------------------------------
# sandboxed execution
# --------------------------------------------------------------------------


class SqlExecutionError(RuntimeError):
    pass


def _deny_writes_authorizer(action: int, arg1, arg2, dbname, source):
    allowed = {
        getattr(sqlite3, "SQLITE_SELECT", 21),
        getattr(sqlite3, "SQLITE_READ", 20),
        getattr(sqlite3, "SQLITE_FUNCTION", 31),
        getattr(sqlite3, "SQLITE_RECURSIVE", 33),
        getattr(sqlite3, "SQLITE_TRANSACTION", 22),
    }
    if action in allowed:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_readonly(setup_sql: str, sql: str, timeout_s: float = 5.0, row_limit: int = 5000):
    """Run ``sql`` against a throwaway in-memory db with writes denied."""
    con = sqlite3.connect(":memory:")
    try:
        con.executescript(setup_sql)
        deadline = time.time() + timeout_s

        def progress():
            return 1 if time.time() > deadline else 0

        con.set_progress_handler(progress, 10000)
        con.set_authorizer(_deny_writes_authorizer)
        try:
            cur = con.execute(sql)
            cols = [c[0] for c in (cur.description or [])]
            rows = [list(r) for r in cur.fetchmany(row_limit)]
            cur.close()
        except sqlite3.Error as exc:
            raise SqlExecutionError(str(exc))
        finally:
            con.set_authorizer(None)
            con.set_progress_handler(None, 0)
        return cols, rows
    finally:
        con.close()


# --------------------------------------------------------------------------
# the checker
# --------------------------------------------------------------------------


def _match_must_not(instance: TaskInstance, needle: str, fallback: str) -> str:
    for entry in instance.must_not:
        if needle.lower() in entry.lower():
            return entry
    return fallback


@CHECKERS.register("sql_result_equiv", layer="L2", category="G7")
def sql_result_equiv(instance: TaskInstance, candidate: Any, **kw: Any) -> Dict[str, Any]:
    """Score a candidate SQL answer against the gold reference result set."""
    started = time.time()
    gold = instance.gold.value or {}
    tol = float(gold.get("float_tolerance", 1e-6))
    order_sensitive = bool(gold.get("order_sensitive", False))
    ref = gold.get("result", {}) or {}
    ref_cols = list(ref.get("columns", []))
    ref_rows = [list(r) for r in ref.get("rows", [])]

    if isinstance(candidate, dict):
        candidate_sql = candidate.get("sql", "")
    else:
        candidate_sql = candidate or ""
    candidate_sql = clean_sql(str(candidate_sql))

    violations: List[str] = []
    detail: Dict[str, Any] = {"candidate_sql": candidate_sql}

    if not candidate_sql:
        return make_checker_result(
            0.0, False, "L1", {"parsed": 0.0}, [], {"error": "empty_candidate"},
            wall_s=time.time() - started,
        )

    # -- layer L1: static safety scan -------------------------------------
    destructive = scan_destructive(candidate_sql)
    for kw_hit in destructive:
        violations.append(_match_must_not(instance, kw_hit, "执行 {}".format(kw_hit)))
    leaked = scan_privacy(candidate_sql, gold.get("privacy_columns", []))
    if leaked:
        violations.append(_match_must_not(instance, "手机号", "泄露客户手机号"))
        detail["privacy_columns_hit"] = leaked
    if count_statements(candidate_sql) > 1:
        violations.append("多语句提交")

    if violations:
        detail["destructive_keywords"] = destructive
        return make_checker_result(
            0.0, False, "L1", {"safety": 0.0}, violations, detail, wall_s=time.time() - started
        )

    # -- layer L2: real execution -----------------------------------------
    try:
        cand_cols, cand_rows = execute_readonly(gold.get("setup_sql", ""), candidate_sql)
    except SqlExecutionError as exc:
        msg = str(exc)
        detail["error"] = msg
        if "not authorized" in msg.lower():
            violations.append("引擎层拦截的写操作")
        return make_checker_result(
            0.0, False, "L2", {"executable": 0.0}, violations, detail, wall_s=time.time() - started
        )

    cmp_result = compare_result_sets(
        ref_cols, ref_rows, cand_cols, cand_rows, order_sensitive=order_sensitive, tol=tol
    )
    detail.update(cmp_result["detail"])
    detail["reason"] = cmp_result["reason"]
    return make_checker_result(
        score=cmp_result["score"],
        passed=cmp_result["exact"],
        layer="L2",
        sub_metrics={
            "executable": 1.0,
            "exact": 1.0 if cmp_result["exact"] else 0.0,
            "row_precision": cmp_result["row_precision"],
            "row_recall": cmp_result["row_recall"],
            "row_f1": cmp_result["row_f1"],
            "column_match": cmp_result["column_match"],
            "order_ok": 1.0 if cmp_result["order_ok"] else 0.0,
        },
        violations=violations,
        detail=detail,
        wall_s=time.time() - started,
    )
