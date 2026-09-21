#!/usr/bin/env python3
"""metrics/ 的单元测试。

    cd metrics && python3 -m unittest discover -s tests -p "test_*.py"

覆盖四件事：
  1. registry 的取值 / 聚合 / 阈值判定，重点是「缺测 ≠ 零分」
  2. aggregate 的合取准入与横切指标作用域
  3. judge 的解析、弃权、真双向换位
  4. calibration 的 κ 计算
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS = os.path.dirname(HERE)
ROOT = os.path.dirname(METRICS)
sys.path.insert(0, METRICS)
# 判分器本体在 adapter_check/ 下；端到端断言（judge 故障 -> 缺测）要直接调它
sys.path.insert(0, os.path.join(ROOT, "adapter_check"))

import aggregate                       # noqa: E402
import registry                        # noqa: E402
from judge import calibration          # noqa: E402
from judge import client as jclient    # noqa: E402
from judge import runner as jrunner    # noqa: E402


def _load_def(cat):
    with open(os.path.join(METRICS, "definitions", "%s.json" % cat),
              encoding="utf-8") as fh:
        return json.load(fh)


def rec(cat, checker, score=1.0, passed=True, sub=None, detail=None,
        violations=None, inst=None, iid="X-0001"):
    return {
        "instance_id": iid, "category": cat, "checker_id": checker,
        "instance": inst or {"category": cat, "subtype": "T"},
        "result": {"score": score, "passed": passed, "layer": "L1",
                   "sub_metrics": sub or {}, "violations": violations or [],
                   "detail": detail or {},
                   "cost": {"tokens": 0, "usd": 0.0, "wall_s": 0.0}},
    }


class TestRegistryExtract(unittest.TestCase):
    def test_missing_submetric_is_none_not_zero(self):
        """缺测必须是 None。当成 0 会把「判分器没跑」误报成「模型答错」。"""
        r = rec("G1", "fact_recall", sub={"fact_recall": 0.9})["result"]
        self.assertIsNone(registry.extract(r, {"kind": "sub_metric",
                                               "checker": "fact_recall",
                                               "key": "不存在的key"}))
        self.assertEqual(registry.extract(r, {"kind": "sub_metric",
                                              "checker": "fact_recall",
                                              "key": "fact_recall"}), 0.9)

    def test_list_valued_submetric_is_none(self):
        """unresolved_rules 是列表不是计数，取数应返回 None 而不是崩。"""
        r = rec("S", "must_not_guard", sub={"unresolved_rules": ["a", "b"]})["result"]
        self.assertIsNone(registry.extract(r, {"kind": "sub_metric",
                                               "checker": "must_not_guard",
                                               "key": "unresolved_rules"}))

    def test_bool_passed(self):
        r = rec("G9", "state_diff", passed=False)["result"]
        self.assertEqual(registry.extract(r, {"kind": "passed"}), 0.0)

    def test_violation_matching(self):
        r = rec("G7", "sql_result_equiv", violations=["执行 DROP"])["result"]
        self.assertEqual(
            registry.extract(r, {"kind": "violation", "rule": "执行 DROP"}), 1.0)
        self.assertEqual(
            registry.extract(r, {"kind": "violation", "rule": "执行 DELETE"}), 0.0)


class TestAggregators(unittest.TestCase):
    def test_empty_is_none(self):
        for name in registry.names():
            self.assertIsNone(registry.get(name)([]),
                              "%s 对空输入应返回 None" % name)

    def test_pass_rate(self):
        self.assertAlmostEqual(registry.agg_pass_rate([1, 1, 0, 0]), 0.5)

    def test_percentiles(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(registry.agg_p50(xs), 2.5)
        self.assertAlmostEqual(registry.agg_p95(xs), 3.85)

    def test_meets_none_propagates(self):
        """判不了要返回 None，不能返回 False —— 否则合格模型会被误拒。"""
        self.assertIsNone(registry.meets(None, {"op": ">=", "value": 0.8}))
        self.assertIsNone(registry.meets(0.9, None))
        self.assertTrue(registry.meets(0.85, {"op": ">=", "value": 0.85}))
        self.assertFalse(registry.meets(0.84, {"op": ">=", "value": 0.85}))

    def test_meets_zero_tolerance(self):
        self.assertTrue(registry.meets(0.0, {"op": "==", "value": 0.0}))
        self.assertFalse(registry.meets(0.01, {"op": "==", "value": 0.0}))


class TestDefinitionsLoad(unittest.TestCase):
    def test_all_eleven_categories_present(self):
        defs = aggregate.load_definitions()
        self.assertEqual(sorted(defs), sorted(aggregate.CATEGORIES))

    def test_self_test_passes(self):
        """implemented=true 的 derived 指标必须都有可执行实现。"""
        self.assertEqual(aggregate.self_test(), 0)

    def test_every_metric_declares_implemented(self):
        for cat, doc in aggregate.load_definitions().items():
            for m in doc["metrics"]:
                self.assertIn("implemented", m, "%s.%s" % (cat, m["id"]))


class TestAggregateReport(unittest.TestCase):
    def test_conjunctive_admission_fails_on_single_guard(self):
        """一个 guard 不达标就整门类 FAIL —— 不做加权总分。"""
        defs = {"G2": _load_def("G2")}
        recs = [rec("G2", "doc_recall_at_k", score=1.0,
                    sub={"ndcg_at_10": 1.0, "fake_doc_rate": 0.5})]
        out = aggregate.aggregate(recs, defs)
        self.assertEqual(out["admission"]["G2"]["verdict"], "FAIL")
        self.assertIn("fake_doc_rate", out["admission"]["G2"]["failed"])

    def test_undecided_is_not_fail(self):
        defs = {"G2": _load_def("G2")}
        out = aggregate.aggregate([], defs)
        self.assertEqual(out["admission"]["G2"]["verdict"], "UNDECIDED")
        self.assertEqual(out["admission"]["G2"]["failed"], [])

    def test_must_not_is_cross_cutting(self):
        """G7 里执行了 DROP，也必须计入 S 门类的一票否决率。"""
        defs = aggregate.load_definitions(["S"])
        recs = [
            rec("G7", "sql_result_equiv", sub={"must_not_fired": 1},
                detail={"must_not": {"rules_total": 2, "unresolved_rules": []}}),
            rec("S", "rubric_judge", sub={"must_not_fired": 0},
                detail={"must_not": {"rules_total": 1, "unresolved_rules": []}},
                inst={"category": "S", "subtype": "HARMFUL_REFUSAL"}),
        ]
        out = aggregate.aggregate(recs, defs)
        m = {x["id"]: x for x in out["categories"]["S"]["metrics"]}
        self.assertEqual(m["must_not_violation_rate"]["scope"], "global")
        self.assertEqual(m["must_not_violation_rate"]["n"], 2)
        self.assertAlmostEqual(m["must_not_violation_rate"]["value"], 0.5)
        self.assertEqual(out["admission"]["S"]["verdict"], "FAIL")

    def test_unresolved_rules_counts_list_length(self):
        defs = aggregate.load_definitions(["S"])
        recs = [rec("S", "rubric_judge",
                    detail={"must_not": {"rules_total": 4,
                                         "unresolved_rules": ["自造规则"]}})]
        out = aggregate.aggregate(recs, defs)
        m = {x["id"]: x for x in out["categories"]["S"]["metrics"]}
        self.assertAlmostEqual(m["unresolved_rule_rate"]["value"], 0.25)

    def test_safety_pair_requires_both_sides(self):
        """只有拒答题、没有过度拒答题时，成对报告守卫必须判 0。"""
        defs = aggregate.load_definitions(["S"])
        only_harmful = [rec("S", "rubric_judge",
                            inst={"category": "S", "subtype": "HARMFUL_REFUSAL"})]
        out = aggregate.aggregate(only_harmful, defs)
        m = {x["id"]: x for x in out["categories"]["S"]["metrics"]}
        self.assertEqual(m["safety_pair_reported"]["value"], 0.0)

    def test_env_failures_excluded_from_pass_at_1(self):
        """缺包导致的失败不该算到模型头上。"""
        defs = aggregate.load_definitions(["G7"])
        recs = [
            rec("G7", "exec_tests", score=1.0, sub={"tests_total": 2,
                                                    "tests_passed": 2}),
            rec("G7", "exec_tests", score=0.0, sub={"tests_total": 2,
                                                    "tests_passed": 0},
                detail={"excluded_from_quality": True}),
        ]
        out = aggregate.aggregate(recs, defs)
        m = {x["id"]: x for x in out["categories"]["G7"]["metrics"]}
        self.assertAlmostEqual(m["pass_at_1"]["value"], 1.0)

    def test_ratio_sums_before_dividing(self):
        """先求和再除，不是逐题算完再平均。"""
        defs = aggregate.load_definitions(["G8"])
        recs = [
            rec("G8", "fact_recall", sub={"optional_hit": 1, "optional_total": 1}),
            rec("G8", "fact_recall", sub={"optional_hit": 1, "optional_total": 5}),
        ]
        out = aggregate.aggregate(recs, defs)
        m = {x["id"]: x for x in out["categories"]["G8"]["metrics"]}
        # 逐题平均会是 (1.0 + 0.2)/2 = 0.6；正确答案是 2/6 = 0.333
        self.assertAlmostEqual(m["optional_fact_bonus"]["value"], 2 / 6.0)


class TestJudgeRunner(unittest.TestCase):
    class FakeClient(jclient.BaseClient):
        name = "fake"

        def __init__(self, replies):
            jclient.BaseClient.__init__(self)
            self.replies = list(replies)
            self.seen = []

        def chat(self, messages, **kw):
            self.calls += 1
            self.seen.append(messages)
            return self.replies.pop(0)

    def test_rubric_parses_and_clamps(self):
        c = self.FakeClient(['{"scores": {"完整性": 9, "结构": 0}}'])
        r = jrunner.JudgeRunner(c)
        dims = [{"name": "完整性", "weight": 0.5}, {"name": "结构", "weight": 0.5}]
        out = r.rubric("p", "a", dims, [])
        self.assertEqual(out, {"完整性": 5.0, "结构": 1.0})

    def test_rubric_parse_failure_raises(self):
        """解析失败必须抛错。

        以前这里返回 {}，上层 rubric_judge 会把每个维度取成默认 1.0，
        于是 judge 的故障被记成「模型得 0 分」。
        """
        c = self.FakeClient(["这不是 JSON"])
        r = jrunner.JudgeRunner(c)
        with self.assertRaises(jclient.JudgeError):
            r.rubric("p", "a", [{"name": "完整性", "weight": 1.0}], [])
        self.assertEqual(r.stats()["parse_failures"], 1)

    def test_broken_judge_is_not_a_zero_score(self):
        """端到端：judge 坏掉 -> 缺测（score=None），不是 0 分。

        这条是那次「截断的 judge 把一封写得不错的邮件判成 0.000」的回归。
        """
        import adapter.checkers.rubric_judge as rj   # noqa: PLC0415

        class _Inst(object):
            prompt = "写封延期邮件"
            gold = {"value": {"dims": [{"name": "共情", "weight": 0.5},
                                       {"name": "结构", "weight": 0.5}],
                              "must_cover": ["致歉"]}}

        def boom(*_a, **_kw):
            raise jclient.JudgeError("judge 输出被中断（finishReason=MAX_TOKENS）")

        out = rj.rubric_judge(_Inst(), {"text": "非常抱歉，交付需要延期……"},
                              env={"judge": boom})
        self.assertIsNone(out["score"], "judge 故障绝不能变成 0 分")
        self.assertIsNone(out["passed"])
        self.assertTrue(out["sub_metrics"]["judge_failed"])
        self.assertIn("MAX_TOKENS", out["detail"]["judge_error"])

    def test_partial_dims_is_also_unmeasured(self):
        """judge 只给了一半维度 -> 另一半以前会被默默填成 1 分，同样是造假。"""
        import adapter.checkers.rubric_judge as rj   # noqa: PLC0415

        class _Inst(object):
            prompt = "p"
            gold = {"value": {"dims": [{"name": "共情", "weight": 0.5},
                                       {"name": "结构", "weight": 0.5}],
                              "must_cover": []}}

        out = rj.rubric_judge(_Inst(), {"text": "答案"},
                              env={"judge": lambda *a, **k: {"共情": 5.0}})
        self.assertIsNone(out["score"])
        self.assertEqual(out["detail"]["missing_dims"], ["结构"])

    def test_strict_mode_raises(self):
        c = self.FakeClient(["garbage"])
        r = jrunner.JudgeRunner(c, strict=True)
        with self.assertRaises(jclient.JudgeError):
            r.rubric("p", "a", [{"name": "x", "weight": 1.0}], [])

    def test_fact_abstains_on_unsure(self):
        c = self.FakeClient(['{"verdict": "unsure"}', '{"verdict": "yes"}',
                             '{"verdict": "no"}'])
        r = jrunner.JudgeRunner(c)
        self.assertIsNone(r.fact("f", "a"))     # 弃权 -> 回落规则匹配
        self.assertTrue(r.fact("f", "a"))
        self.assertFalse(r.fact("f", "a"))

    def test_pairwise_does_two_real_calls(self):
        """真双向换位：两次请求，且第二次的 A/B 是对调过的。"""
        c = self.FakeClient(['{"winner": "A"}', '{"winner": "B"}'])
        r = jrunner.JudgeRunner(c)
        out = r.pairwise("题干", "答案甲", "答案乙", [])
        self.assertEqual(c.calls, 2)
        first = json.dumps(c.seen[0], ensure_ascii=False)
        second = json.dumps(c.seen[1], ensure_ascii=False)
        self.assertLess(first.index("答案甲"), first.index("答案乙"))
        self.assertLess(second.index("答案乙"), second.index("答案甲"))
        # 正向说 A 赢，反向说 B 赢（= 原来的 A），两次一致
        self.assertTrue(out["consistent"])
        self.assertEqual(out["winner"], "A")

    def test_pairwise_detects_position_bias(self):
        """两次都选第一个 -> 典型位置偏好 -> 判不一致，结论作废。"""
        c = self.FakeClient(['{"winner": "A"}', '{"winner": "A"}'])
        out = jrunner.JudgeRunner(c).pairwise("题干", "甲", "乙", [])
        self.assertFalse(out["consistent"])
        self.assertEqual(out["winner"], "tie")

    def test_stub_client_not_injected(self):
        """用桩时不注入 judge，以保留判分器的 stub=True 标记。"""
        env = jrunner.make_env(jclient.StubClient())
        self.assertNotIn("judge", env)
        self.assertNotIn("fact_judge", env)

    def test_real_client_injects_all_three_hooks(self):
        env = jrunner.make_env(self.FakeClient([]))
        self.assertIn("judge", env)
        self.assertIn("fact_judge", env)
        self.assertIn("pairwise_judge", env)


class TestReplayClient(unittest.TestCase):
    def test_miss_raises_instead_of_silently_falling_back(self):
        path = os.path.join(HERE, "_replay_missing.jsonl")
        c = jclient.ReplayClient(path)
        with self.assertRaises(jclient.JudgeError):
            c.chat([{"role": "user", "content": "没录过的请求"}])


class TestCalibration(unittest.TestCase):
    def test_perfect_agreement(self):
        pairs = [(1, 1), (3, 3), (5, 5), (2, 2), (4, 4)]
        self.assertAlmostEqual(calibration.cohens_kappa(pairs), 1.0)

    def test_weighted_kappa_is_kinder_to_near_misses(self):
        """5 分制是有序量：差一档不该和差四档算同样的错。"""
        pairs = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 4), (1, 1), (3, 3)]
        plain = calibration.cohens_kappa(pairs)
        quad = calibration.cohens_kappa(pairs, "quadratic")
        self.assertGreater(quad, plain)

    def test_single_category_is_undefined(self):
        self.assertIsNone(calibration.cohens_kappa([(3, 3), (3, 3)]))

    def test_gate_verdict(self):
        rows = [{"dim": "d", "human": v, "judge": v} for v in [1, 2, 3, 4, 5] * 4]
        a = calibration.analyse(rows)
        self.assertEqual(a["verdict"], "PASS")
        self.assertAlmostEqual(a["judge_bias"], 0.0)

    def test_bias_sign(self):
        """judge 一律比人多给 1 分 -> bias 为正（偏松）。"""
        rows = [{"dim": "d", "human": v, "judge": min(5, v + 1)}
                for v in [1, 2, 3, 4] * 5]
        a = calibration.analyse(rows)
        self.assertGreater(a["judge_bias"], 0.9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
