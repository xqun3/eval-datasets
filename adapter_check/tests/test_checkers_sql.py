"""sql_result_equiv: one test per documented equivalence rule."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapter.checkers.sql_equiv import (  # noqa: E402
    build_db,
    has_order_by,
    results_equal,
    run_sql,
    sql_result_equiv,
    _ves_inner,
    _ves_to_result,
)
from adapter.schema import TaskInstance  # noqa: E402

DDL = """
CREATE TABLE t (a INTEGER, b TEXT, c REAL);
INSERT INTO t (a, b, c) VALUES (1, 'x', 1.0), (2, 'y', 2.5), (2, 'y', 2.5), (3, NULL, NULL);
"""


def make_instance(gold_sql, order_sensitive=None, column_order_sensitive=False):
    test = {"kind": "sql", "gold_sql": gold_sql}
    if order_sensitive is not None:
        test["order_sensitive"] = order_sensitive
    if column_order_sensitive:
        test["column_order_sensitive"] = True
    return TaskInstance(
        id="G7-SQL_QUERY-0001", category="G7", subtype="SQL_QUERY", difficulty="L1",
        lang="en",
        context={"files": [], "db_schema": {"dialect": "sqlite", "ddl": DDL,
                                            "snapshot_ref": None}, "kb_docs": []},
        tools_available=[], prompt="q",
        gold={"type": "executable",
              "value": {"tests": [test], "ref_solution": gold_sql, "timeout_s": 10}},
        checker="sql_result_equiv", must_not=[], source="public:x@1", split="dev",
    ).raise_for_errors()


def score(gold_sql, pred_sql, **kw):
    inst = make_instance(gold_sql, **kw)
    return sql_result_equiv(inst, {"text": pred_sql})


class TestExecution(unittest.TestCase):
    def test_db_really_executes(self):
        conn = build_db(DDL)
        cols, rows = run_sql(conn, "SELECT COUNT(*) FROM t")
        self.assertEqual(rows, [(4,)])
        self.assertEqual(len(cols), 1)

    def test_identical_query_passes(self):
        r = score("SELECT a, b FROM t", "SELECT a, b FROM t")
        self.assertEqual(r["score"], 1.0)
        self.assertTrue(r["passed"])
        self.assertEqual(r["layer"], "L1")

    def test_syntax_error_fails_not_crashes(self):
        r = score("SELECT a FROM t", "SELEKT a FROM t")
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["sub_metrics"]["syntax_ok"], 0.0)
        self.assertIn("pred sql failed", r["detail"]["per_test"][0]["error"])

    def test_empty_prediction(self):
        r = score("SELECT a FROM t", "")
        self.assertEqual(r["score"], 0.0)

    def test_sql_extracted_from_markdown_fence(self):
        r = score("SELECT a FROM t", "好的：\n```sql\nSELECT a FROM t;\n```\n以上。")
        self.assertEqual(r["score"], 1.0)


class TestRowOrder(unittest.TestCase):
    def test_row_order_ignored_without_order_by(self):
        r = score("SELECT a FROM t", "SELECT a FROM t ORDER BY a DESC")
        self.assertEqual(r["score"], 1.0)

    def test_row_order_enforced_with_order_by_in_gold(self):
        r = score("SELECT a FROM t ORDER BY a ASC", "SELECT a FROM t ORDER BY a DESC")
        self.assertEqual(r["score"], 0.0)
        self.assertTrue(r["detail"]["per_test"][0]["order_sensitive"])

    def test_has_order_by_detection(self):
        self.assertTrue(has_order_by("select a from t order by a"))
        self.assertFalse(has_order_by("select a from t where b='order by'"[:24]))

    def test_explicit_order_flag_overrides(self):
        r = score("SELECT a FROM t ORDER BY a ASC", "SELECT a FROM t ORDER BY a DESC",
                  order_sensitive=False)
        self.assertEqual(r["score"], 1.0)


class TestColumnOrder(unittest.TestCase):
    def test_column_order_ignored_by_default(self):
        r = score("SELECT a, b FROM t", "SELECT b, a FROM t")
        self.assertEqual(r["score"], 1.0)

    def test_column_order_enforced_when_requested(self):
        r = score("SELECT a, b FROM t", "SELECT b, a FROM t", column_order_sensitive=True)
        self.assertEqual(r["score"], 0.0)


class TestDuplicatesNullsFloats(unittest.TestCase):
    def test_duplicate_rows_are_significant(self):
        r = score("SELECT b FROM t WHERE b='y'", "SELECT DISTINCT b FROM t WHERE b='y'")
        self.assertEqual(r["score"], 0.0)

    def test_duplicates_preserved_when_equal(self):
        r = score("SELECT b FROM t WHERE b='y'", "SELECT b FROM t WHERE b LIKE 'y'")
        self.assertEqual(r["score"], 1.0)

    def test_null_is_not_empty_string(self):
        self.assertFalse(results_equal([(None,)], [("",)], row_order=False, col_order=True))

    def test_null_is_not_zero(self):
        self.assertFalse(results_equal([(None,)], [(0,)], row_order=False, col_order=True))

    def test_null_equals_null(self):
        self.assertTrue(results_equal([(None,)], [(None,)], row_order=False, col_order=True))

    def test_null_rows_survive_real_query(self):
        r = score("SELECT a, c FROM t", "SELECT a, c FROM t")
        self.assertEqual(r["score"], 1.0)

    def test_float_tolerance_accepts_tiny_drift(self):
        self.assertTrue(results_equal([(1.0000000001,)], [(1.0,)],
                                      row_order=False, col_order=True))

    def test_float_tolerance_rejects_real_difference(self):
        self.assertFalse(results_equal([(1.01,)], [(1.0,)], row_order=False, col_order=True))

    def test_int_float_equivalence(self):
        self.assertTrue(results_equal([(2,)], [(2.0,)], row_order=False, col_order=True))

    def test_float_sum_drift_in_real_query(self):
        r = score("SELECT SUM(c) FROM t", "SELECT SUM(c) + 0.0000000001 FROM t")
        self.assertEqual(r["score"], 1.0)

    def test_string_whitespace_trimmed(self):
        self.assertTrue(results_equal([(" x ",)], [("x",)], row_order=False, col_order=True))


class TestVesWrapper(unittest.TestCase):
    def test_wrapper_normalises_to_checker_result(self):
        inst = make_instance("SELECT a FROM t")
        raw = _ves_inner(inst, {"text": "SELECT a FROM t"})
        res = _ves_to_result(raw)
        self.assertTrue(res["passed"])
        self.assertEqual(sorted(res.keys()),
                         sorted(["score", "passed", "layer", "sub_metrics", "violations",
                                 "detail", "cost"]))

    def test_wrapper_zero_when_incorrect(self):
        inst = make_instance("SELECT a FROM t")
        res = _ves_to_result(_ves_inner(inst, {"text": "SELECT b FROM t"}))
        self.assertEqual(res["score"], 0.0)
        self.assertFalse(res["passed"])


if __name__ == "__main__":
    unittest.main()
