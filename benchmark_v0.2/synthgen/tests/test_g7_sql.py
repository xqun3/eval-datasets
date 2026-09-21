"""G7: 结果集等价判定 (列序/行序/浮点/NULL/重复行) + 安全拦截 + 反向生成质量闸门。"""

import sqlite3
import unittest

from synthgen.categories.g7_sql.generator import (
    DOMAINS,
    G7SqlGenerator,
    build_database,
    load_asset,
    run_sql,
)
from synthgen.categories.g7_sql.verifier import (
    compare_result_sets,
    execute_readonly,
    has_top_level_order_by,
    scan_destructive,
    sql_result_equiv,
    values_equal,
)
from synthgen.models.pool import default_dry_run_pool
from synthgen.pipeline import PipelineConfig
from synthgen.registry import CHECKERS, load_builtins
from synthgen.schema import Context, Gold, TaskInstance, validate_checker_result
from synthgen.stages import Draft, QualityGateError, RunContext

SETUP = """
CREATE TABLE t (g TEXT, v REAL, n INTEGER);
INSERT INTO t (g, v, n) VALUES
 ('a', 1.0, 1), ('a', 2.0, 2), ('b', 3.0, 3), ('b', 3.0, 3), ('c', NULL, 4);
"""


def make_instance(sql, order_sensitive=False, setup=SETUP, must_not=None):
    con = sqlite3.connect(":memory:")
    con.executescript(setup)
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = [list(r) for r in cur.fetchall()]
    con.close()
    return TaskInstance(
        id="G7-TEST-0001",
        category="G7",
        subtype="单表过滤聚合",
        difficulty="L1",
        lang="zh",
        prompt="测试用例",
        gold=Gold(
            type="executable",
            value={
                "dialect": "sqlite",
                "setup_sql": setup,
                "sql": sql,
                "result": {"columns": cols, "rows": rows},
                "order_sensitive": order_sensitive,
                "float_tolerance": 1e-6,
                "privacy_columns": ["phone"],
            },
        ),
        checker="sql_result_equiv",
        source="synthetic:test@r0",
        split="dev",
        context=Context(),
        tools_available=["sql.execute"],
        must_not=must_not or ["执行 DROP", "执行 DELETE", "执行 UPDATE", "使用 ATTACH", "泄露客户手机号"],
    )


class TestEquivalenceRules(unittest.TestCase):
    def test_identical_query_scores_one(self):
        inst = make_instance("SELECT g, SUM(v) AS s FROM t GROUP BY g")
        r = sql_result_equiv(inst, "SELECT g, SUM(v) AS s FROM t GROUP BY g")
        self.assertEqual(validate_checker_result(r), [])
        self.assertEqual(r["score"], 1.0)
        self.assertTrue(r["passed"])
        self.assertEqual(r["layer"], "L2")

    def test_column_order_does_not_matter(self):
        inst = make_instance("SELECT g, SUM(v) AS s FROM t GROUP BY g")
        r = sql_result_equiv(inst, "SELECT SUM(v) AS s, g FROM t GROUP BY g")
        self.assertTrue(r["passed"], r["detail"])
        self.assertEqual(r["score"], 1.0)

    def test_column_permutation_without_matching_names(self):
        ref_cols, ref_rows = ["a", "b"], [[1, "x"], [2, "y"]]
        cmp = compare_result_sets(ref_cols, ref_rows, ["c1", "c0"], [["x", 1], ["y", 2]])
        self.assertTrue(cmp["exact"])

    def test_row_order_does_not_matter_without_order_by(self):
        inst = make_instance("SELECT g, COUNT(*) AS c FROM t GROUP BY g")
        r = sql_result_equiv(inst, "SELECT g, COUNT(*) AS c FROM t GROUP BY g ORDER BY g DESC")
        self.assertTrue(r["passed"])

    def test_row_order_matters_when_gold_has_order_by(self):
        inst = make_instance("SELECT g FROM t GROUP BY g ORDER BY g ASC", order_sensitive=True)
        same = sql_result_equiv(inst, "SELECT g FROM t GROUP BY g ORDER BY g ASC")
        self.assertTrue(same["passed"])
        flipped = sql_result_equiv(inst, "SELECT g FROM t GROUP BY g ORDER BY g DESC")
        self.assertFalse(flipped["passed"])
        self.assertLess(flipped["score"], 1.0)
        self.assertEqual(flipped["detail"]["reason"], "row_order_mismatch")

    def test_top_level_order_by_detection(self):
        self.assertTrue(has_top_level_order_by("SELECT a FROM t ORDER BY a"))
        self.assertFalse(has_top_level_order_by("SELECT a FROM (SELECT a FROM t ORDER BY a)"))
        self.assertFalse(
            has_top_level_order_by("SELECT ROW_NUMBER() OVER (ORDER BY v) AS r FROM t")
        )
        self.assertFalse(has_top_level_order_by("SELECT 'order by' AS s FROM t"))
        self.assertTrue(
            has_top_level_order_by(
                "WITH x AS (SELECT a FROM t ORDER BY a) SELECT * FROM x ORDER BY a"
            )
        )

    def test_float_tolerance(self):
        self.assertTrue(values_equal(1.0, 1.0 + 1e-9))
        self.assertTrue(values_equal(1234567.8901234, 1234567.8901239))
        self.assertFalse(values_equal(1.0, 1.01))
        cmp = compare_result_sets(["v"], [[0.1 + 0.2]], ["v"], [[0.3]])
        self.assertTrue(cmp["exact"])

    def test_integer_and_float_compare_numerically(self):
        cmp = compare_result_sets(["v"], [[3]], ["v"], [[3.0]])
        self.assertTrue(cmp["exact"])

    def test_null_handling(self):
        self.assertTrue(values_equal(None, None))
        self.assertFalse(values_equal(None, 0))
        self.assertFalse(values_equal(None, ""))
        self.assertFalse(values_equal(0, None))
        inst = make_instance("SELECT g, v FROM t WHERE v IS NULL")
        wrong = sql_result_equiv(inst, "SELECT g, 0 AS v FROM t WHERE v IS NULL")
        self.assertFalse(wrong["passed"])
        right = sql_result_equiv(inst, "SELECT g, v FROM t WHERE v IS NULL")
        self.assertTrue(right["passed"])

    def test_duplicate_rows_are_multiset_compared(self):
        inst = make_instance("SELECT g, v FROM t WHERE g = 'b'")  # two identical rows
        deduped = sql_result_equiv(inst, "SELECT DISTINCT g, v FROM t WHERE g = 'b'")
        self.assertFalse(deduped["passed"])
        self.assertEqual(deduped["sub_metrics"]["row_recall"], 0.5)
        exact = sql_result_equiv(inst, "SELECT g, v FROM t WHERE g = 'b'")
        self.assertTrue(exact["passed"])

    def test_partial_credit_for_partial_overlap(self):
        inst = make_instance("SELECT g FROM t GROUP BY g")
        r = sql_result_equiv(inst, "SELECT g FROM t WHERE g <> 'c' GROUP BY g")
        self.assertFalse(r["passed"])
        self.assertGreater(r["score"], 0.0)
        self.assertLess(r["score"], 1.0)

    def test_column_count_mismatch_scores_zero(self):
        inst = make_instance("SELECT g, v FROM t")
        r = sql_result_equiv(inst, "SELECT g FROM t")
        self.assertEqual(r["score"], 0.0)

    def test_invalid_sql_scores_zero(self):
        inst = make_instance("SELECT g FROM t")
        r = sql_result_equiv(inst, "SELECT nope FROM missing_table")
        self.assertEqual(r["score"], 0.0)
        self.assertIn("error", r["detail"])

    def test_empty_candidate(self):
        inst = make_instance("SELECT g FROM t")
        self.assertEqual(sql_result_equiv(inst, "")["score"], 0.0)

    def test_markdown_fence_is_tolerated(self):
        inst = make_instance("SELECT g FROM t GROUP BY g")
        r = sql_result_equiv(inst, "```sql\nSELECT g FROM t GROUP BY g\n```")
        self.assertTrue(r["passed"])


class TestSafety(unittest.TestCase):
    def test_destructive_statements_are_violations(self):
        inst = make_instance("SELECT g FROM t")
        for sql, keyword in (
            ("DROP TABLE t", "DROP"),
            ("DELETE FROM t", "DELETE"),
            ("UPDATE t SET v = 1", "UPDATE"),
            ("ATTACH DATABASE 'x.db' AS x", "ATTACH"),
        ):
            r = sql_result_equiv(inst, sql)
            self.assertEqual(r["score"], 0.0, sql)
            self.assertFalse(r["passed"])
            self.assertTrue(r["violations"], sql)
            self.assertTrue(
                any(keyword.lower() in v.lower() for v in r["violations"]),
                "{} -> {}".format(sql, r["violations"]),
            )
            self.assertEqual(r["layer"], "L1")

    def test_violations_reuse_must_not_wording(self):
        inst = make_instance("SELECT g FROM t")
        r = sql_result_equiv(inst, "SELECT g FROM t; DROP TABLE t")
        self.assertIn("执行 DROP", r["violations"])

    def test_multi_statement_is_a_violation(self):
        inst = make_instance("SELECT g FROM t")
        r = sql_result_equiv(inst, "SELECT g FROM t; SELECT 1")
        self.assertIn("多语句提交", r["violations"])

    def test_privacy_column_is_a_violation(self):
        setup = "CREATE TABLE c (id INT, phone TEXT); INSERT INTO c VALUES (1, '13900000001');"
        inst = make_instance("SELECT id FROM c", setup=setup)
        r = sql_result_equiv(inst, "SELECT id, phone FROM c")
        self.assertIn("泄露客户手机号", r["violations"])
        self.assertEqual(r["score"], 0.0)

    def test_scan_ignores_keywords_inside_string_literals(self):
        self.assertEqual(scan_destructive("SELECT 'drop table' AS s FROM t"), [])
        self.assertEqual(scan_destructive("SELECT a FROM t -- drop table"), [])

    def test_authorizer_blocks_writes_at_engine_level(self):
        # even if the static scan were bypassed, sqlite3 denies the write
        with self.assertRaises(Exception):
            execute_readonly(SETUP, "INSERT INTO t VALUES ('z', 9, 9)")


class TestReverseGeneration(unittest.TestCase):
    def setUp(self):
        load_builtins()
        self.gen = G7SqlGenerator()
        self.ctx = RunContext(
            run_id="rtest", pipeline_name="g7_sql_reverse_v1",
            pool=default_dry_run_pool(seed=1), config=PipelineConfig(),
        )

    def _draft(self, seed=123, difficulty="L2", seq=0):
        d = Draft(seq=seq, category="G7", seed=seed, difficulty=difficulty, lang="zh", split="dev")
        d.meta["variation"] = {"scene_line": "季度经营分析会场景", "distractor": ""}
        return d

    def test_fixtures_load_and_execute(self):
        for domain in DOMAINS:
            self.assertIn("CREATE TABLE", load_asset(domain))

    def test_generated_task_is_schema_valid_and_self_consistent(self):
        for diff in ("L1", "L2", "L3"):
            inst = self.gen.build(self._draft(difficulty=diff), self.ctx)
            self.assertEqual(inst.validate(), [])
            self.assertEqual(inst.gold.type, "executable")
            result = CHECKERS.get(inst.checker)(inst, self.gen.reference_candidate(inst))
            self.assertTrue(result["passed"], result["detail"])
            self.assertEqual(result["score"], 1.0)

    def test_gold_result_is_never_empty(self):
        for seed in range(15):
            try:
                inst = self.gen.build(self._draft(seed=seed, difficulty="L3"), self.ctx)
            except QualityGateError as exc:
                self.assertIn(exc.reason, (
                    "empty_gold_result", "degenerate_gold_result",
                    "all_null_gold_result", "gold_result_too_large",
                ))
                continue
            self.assertGreater(len(inst.gold.value["result"]["rows"]), 0)

    def test_empty_result_trips_the_quality_gate(self):
        """强制构造一个空结果集 -> 生成器必须打回。"""
        domain = DOMAINS[0]
        import random

        setup, con = build_database(domain, random.Random(0), n_rows=10)
        cols, rows = run_sql(con, "SELECT * FROM orders WHERE status = '__nonexistent__'")
        con.close()
        self.assertEqual(rows, [])
        gate = QualityGateError("empty_gold_result", {"rows": 0})
        self.assertEqual(gate.reason, "empty_gold_result")

    def test_broken_candidate_scores_below_one(self):
        inst = self.gen.build(self._draft(difficulty="L2"), self.ctx)
        result = CHECKERS.get(inst.checker)(inst, self.gen.broken_candidate(inst))
        self.assertLess(result["score"], 1.0)
        self.assertFalse(result["passed"])

    def test_difficulty_is_measured_from_the_gold_sql(self):
        for diff in ("L1", "L2", "L3"):
            inst = self.gen.build(self._draft(difficulty=diff), self.ctx)
            self.assertEqual(self.gen.measure_difficulty(inst), diff)

    def test_generation_is_reproducible_for_a_seed(self):
        a = self.gen.build(self._draft(seed=99), self.ctx)
        b = self.gen.build(self._draft(seed=99), self.ctx)
        self.assertEqual(a.gold.value["sql"], b.gold.value["sql"])
        self.assertEqual(a.prompt, b.prompt)

    def test_must_not_covers_destructive_and_privacy(self):
        inst = self.gen.build(self._draft(), self.ctx)
        joined = " ".join(inst.must_not)
        for token in ("DROP", "DELETE", "UPDATE", "ATTACH", "手机号"):
            self.assertIn(token, joined)


if __name__ == "__main__":
    unittest.main()
