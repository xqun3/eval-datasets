"""fact_recall / numeric_em / state_diff / rubric_judge / format_compliance / exec_tests."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapter.checkers.exec_tests import exec_tests  # noqa: E402
from adapter.checkers.fact_recall import fact_recall  # noqa: E402
from adapter.checkers.format_compliance import format_compliance  # noqa: E402
from adapter.checkers.numeric_em import numeric_em, parse_number  # noqa: E402
from adapter.checkers.rubric_judge import pairwise_judge, rubric_judge  # noqa: E402
from adapter.checkers.state_diff import sequence_matches, state_diff  # noqa: E402
from adapter.schema import TaskInstance  # noqa: E402


def inst(category, subtype, gold, checker, prompt="do it", tools=None, ctx=None):
    return TaskInstance(
        id="%s-%s-0001" % (category, subtype), category=category, subtype=subtype,
        difficulty="L2", lang="en",
        context=ctx or {"files": [], "db_schema": None, "kb_docs": []},
        tools_available=tools or [], prompt=prompt, gold=gold, checker=checker,
        must_not=[], source="public:x@1", split="dev",
    ).raise_for_errors()


# --------------------------------------------------------------------- facts
def fact_inst(facts, ref="x"):
    return inst("G1", "SHORT_FACT_QA",
                {"type": "factlist", "value": {"facts": facts, "ref_answer": ref}},
                "fact_recall")


class TestFactRecall(unittest.TestCase):
    def test_single_fact_hit(self):
        i = fact_inst([{"id": "f1", "text": "Michio Sugeno", "required": True}])
        r = fact_recall(i, {"text": "The award went to Michio Sugeno in 2010."})
        self.assertEqual(r["score"], 1.0)
        self.assertTrue(r["passed"])
        self.assertEqual(r["layer"], "L2")

    def test_miss(self):
        i = fact_inst([{"id": "f1", "text": "Michio Sugeno", "required": True}])
        r = fact_recall(i, {"text": "I am not sure."})
        self.assertEqual(r["score"], 0.0)

    def test_alternatives_pipe(self):
        i = fact_inst([{"id": "f1", "text": "刘慈欣|Liu Cixin", "required": True}])
        self.assertEqual(fact_recall(i, {"text": "作者是 Liu Cixin。"})["score"], 1.0)
        self.assertEqual(fact_recall(i, {"text": "作者是刘慈欣。"})["score"], 1.0)

    def test_partial_recall(self):
        i = fact_inst([{"id": "f1", "text": "alpha", "required": True},
                       {"id": "f2", "text": "beta", "required": True}])
        r = fact_recall(i, {"text": "only alpha here"})
        self.assertEqual(r["score"], 0.5)
        self.assertFalse(r["passed"])

    def test_optional_facts_excluded_from_denominator(self):
        i = fact_inst([{"id": "f1", "text": "alpha", "required": True},
                       {"id": "f2", "text": "beta", "required": False}])
        r = fact_recall(i, {"text": "alpha only"})
        self.assertEqual(r["score"], 1.0)
        self.assertEqual(r["sub_metrics"]["optional_hit"], 0)

    def test_numeric_fact_tolerance(self):
        i = fact_inst([{"id": "f1", "text": "8848.86", "required": True}])
        self.assertEqual(fact_recall(i, {"text": "It is 8848.860 metres."})["score"], 1.0)

    def test_fullwidth_normalisation(self):
        i = fact_inst([{"id": "f1", "text": "2008年", "required": True}])
        self.assertEqual(fact_recall(i, {"text": "是 ２００８ 年"})["score"], 1.0)

    def test_injected_judge_overrides_rule(self):
        i = fact_inst([{"id": "f1", "text": "alpha", "required": True}])
        r = fact_recall(i, {"text": "nothing"}, env={"fact_judge": lambda f, a: True})
        self.assertEqual(r["score"], 1.0)
        self.assertEqual(r["sub_metrics"]["judge_used"], 1)
        self.assertFalse(r["sub_metrics"]["judge_stub"])

    def test_abstaining_judge_falls_back(self):
        i = fact_inst([{"id": "f1", "text": "alpha", "required": True}])
        r = fact_recall(i, {"text": "alpha"}, env={"fact_judge": lambda f, a: None})
        self.assertEqual(r["score"], 1.0)
        self.assertEqual(r["sub_metrics"]["judge_used"], 0)


# ------------------------------------------------------------------- numeric
def num_inst(value, **kw):
    v = {"doc_ids": [], "must_cite": [], "value": value}
    v.update(kw)
    return inst("G6", "DATA_ANALYSIS", {"type": "reference", "value": v}, "numeric_em")


class TestNumericEM(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(numeric_em(num_inst(184320.55), {"text": "184320.55"})["score"], 1.0)

    def test_answer_tag_and_thousands(self):
        r = numeric_em(num_inst(184320.55), {"text": "work...\nFinal answer: 184,320.55"})
        self.assertEqual(r["score"], 1.0)

    def test_tolerance(self):
        self.assertEqual(numeric_em(num_inst(1.0, rel_tol=1e-3),
                                    {"text": "1.0005"})["score"], 1.0)
        self.assertEqual(numeric_em(num_inst(1.0, rel_tol=1e-9),
                                    {"text": "1.0005"})["score"], 0.0)

    def test_percent(self):
        self.assertEqual(numeric_em(num_inst(0.0247), {"text": "2.47%"})["score"], 1.0)

    def test_cn_unit(self):
        self.assertEqual(numeric_em(num_inst(12000.0), {"text": "答案：1.2万"})["score"], 1.0)

    def test_literal_answer(self):
        self.assertEqual(numeric_em(num_inst("NexPay"), {"text": "Answer: NexPay"})["score"], 1.0)
        self.assertEqual(numeric_em(num_inst("NexPay"), {"text": "Answer: SwiftPay"})["score"], 0.0)

    def test_literal_alternatives(self):
        self.assertEqual(numeric_em(num_inst("NexPay|Nex Pay"),
                                    {"text": "nex pay"})["score"], 1.0)

    def test_list_answer(self):
        self.assertEqual(numeric_em(num_inst([1.0, 2.0]), {"text": "1 and 2"})["score"], 1.0)
        self.assertEqual(numeric_em(num_inst([1.0, 2.0]), {"text": "1, 2, 3"})["score"], 0.0)

    def test_parse_number_helpers(self):
        self.assertEqual(parse_number("1,234"), 1234.0)
        self.assertEqual(parse_number("50%"), 0.5)
        self.assertIsNone(parse_number("abc"))


# --------------------------------------------------------------------- trace
def trace_inst(final_state, sequences=None, forbidden=None, comm=None, ignore=None):
    return inst("G9", "MULTITURN_TOOL_OPS",
                {"type": "trace",
                 "value": {"final_state": final_state,
                           "valid_sequences": sequences or [],
                           "forbidden_calls": forbidden or [],
                           "communicate_info": comm or [],
                           "ignore_fields": ignore or []}},
                "state_diff", tools=["crm.get", "crm.update"])


class TestStateDiff(unittest.TestCase):
    GOLD = {"orders": [{"id": "W1", "address": "88 Century Ave", "updated_at": "2026-01-01"}]}

    def test_autoincrement_and_timestamps_ignored(self):
        i = trace_inst(self.GOLD)
        actual = {"orders": [{"id": "W999", "address": "88 Century Ave",
                              "updated_at": "2026-09-19T12:00:00Z"}]}
        r = state_diff(i, {"final_state": actual})
        self.assertEqual(r["sub_metrics"]["state_match"], 1.0)

    def test_real_difference_detected(self):
        i = trace_inst(self.GOLD)
        actual = {"orders": [{"id": "W1", "address": "Old Street"}]}
        r = state_diff(i, {"final_state": actual})
        self.assertEqual(r["score"], 0.0)
        self.assertTrue(r["detail"]["diffs"])

    def test_row_insert_order_irrelevant(self):
        gold = {"t": [{"k": 1}, {"k": 2}]}
        i = trace_inst(gold)
        r = state_diff(i, {"final_state": {"t": [{"k": 2}, {"k": 1}]}})
        self.assertEqual(r["sub_metrics"]["state_match"], 1.0)

    def test_untouched_tables_ignored(self):
        i = trace_inst({"t": [{"k": 1}]})
        r = state_diff(i, {"final_state": {"t": [{"k": 1}], "other": [{"junk": 1}]}})
        self.assertEqual(r["sub_metrics"]["state_match"], 1.0)

    def test_multiple_valid_paths(self):
        i = trace_inst({"t": []}, sequences=[["a.x", "a.y"], ["a.y", "a.x"]])
        r = state_diff(i, {"final_state": {"t": []},
                           "tool_calls": [{"name": "a.y"}, {"name": "a.x"}]})
        self.assertEqual(r["sub_metrics"]["sequence_match"], 1.0)
        self.assertEqual(r["sub_metrics"]["matched_sequence_index"], 1)

    def test_extra_read_calls_tolerated(self):
        i = trace_inst({"t": []}, sequences=[["a.x", "a.y"]])
        r = state_diff(i, {"final_state": {"t": []},
                           "tool_calls": [{"name": "a.x"}, {"name": "a.read"},
                                          {"name": "a.y"}]})
        self.assertEqual(r["sub_metrics"]["sequence_match"], 1.0)

    def test_forbidden_call_zeroes(self):
        i = trace_inst({"t": []}, forbidden=["crm.delete"])
        r = state_diff(i, {"final_state": {"t": []},
                           "tool_calls": [{"name": "crm.delete"}]})
        self.assertEqual(r["score"], 0.0)
        self.assertTrue(r["violations"])

    def test_communicate_info(self):
        i = trace_inst({"t": []}, comm=["88 Century Ave"])
        good = state_diff(i, {"final_state": {"t": []}, "text": "changed to 88 Century Ave"})
        bad = state_diff(i, {"final_state": {"t": []}, "text": "done"})
        self.assertEqual(good["sub_metrics"]["communicate_recall"], 1.0)
        self.assertEqual(bad["sub_metrics"]["communicate_recall"], 0.0)
        self.assertGreater(good["score"], bad["score"])

    def test_sequence_matches_helper(self):
        self.assertEqual(sequence_matches(["a"], []), (True, -1))
        self.assertEqual(sequence_matches(["a", "b"], [["a", "b"]])[0], True)
        self.assertEqual(sequence_matches(["b", "a"], [["a", "b"]])[0], False)


# -------------------------------------------------------------------- rubric
DIMS = [{"name": "完整性", "weight": 0.5, "anchors": {"1": "缺失", "5": "完整"}},
        {"name": "结构", "weight": 0.5, "anchors": {"1": "混乱", "5": "清晰"}}]


def rubric_inst(must_cover):
    return inst("G4", "FORMAT_CONSTRAINED_WRITING",
                {"type": "rubric", "value": {"dims": DIMS, "must_cover": must_cover}},
                "rubric_judge")


class TestRubricJudge(unittest.TestCase):
    def test_stub_is_flagged(self):
        r = rubric_judge(rubric_inst(["预算"]), {"text": "预算说明"})
        self.assertTrue(r["sub_metrics"]["stub"])
        self.assertIn("stub", r["detail"]["warning"])
        self.assertEqual(r["layer"], "L3")

    def test_coverage_moves_score(self):
        i = rubric_inst(["预算", "排期"])
        good = rubric_judge(i, {"text": "## 预算\n- 100万\n## 排期\n- Q1"})
        bad = rubric_judge(i, {"text": "无关内容"})
        self.assertGreater(good["score"], bad["score"])
        self.assertEqual(good["sub_metrics"]["must_cover_coverage"], 1.0)

    def test_injected_judge_used(self):
        i = rubric_inst([])
        r = rubric_judge(i, {"text": "x"},
                         env={"judge": lambda p, a, d, m: {"完整性": 5, "结构": 5}})
        self.assertEqual(r["sub_metrics"]["rubric_mean_5"], 5.0)
        self.assertEqual(r["score"], 1.0)
        self.assertFalse(r["sub_metrics"]["stub"])

    def test_pairwise_is_symmetric(self):
        i = rubric_inst(["预算"])
        out = pairwise_judge(i, {"text": "预算 100万"}, {"text": "无关"})
        self.assertEqual(out["winner"], "a")
        rev = pairwise_judge(i, {"text": "无关"}, {"text": "预算 100万"})
        self.assertEqual(rev["winner"], "b")
        self.assertAlmostEqual(out["margin"], -rev["margin"], places=9)

    def test_pairwise_admits_it_is_not_debiased(self):
        """没有比较型 judge 时，不许假装做了 position bias 消除。

        旧实现算 net=(fwd-rev)/2 而 rev 恒等于 -fwd，等于什么都没做却
        看起来做了。现在必须显式报 False 并带 warning。
        """
        i = rubric_inst(["预算"])
        out = pairwise_judge(i, {"text": "预算 100万"}, {"text": "无关"})
        self.assertFalse(out["position_bias_controlled"])
        self.assertIn("warning", out)

    def test_pairwise_uses_injected_comparative_judge(self):
        i = rubric_inst(["预算"])
        calls = []

        def fake_pw(prompt, a, b, dims):
            calls.append((a, b))
            return {"winner": "B", "consistent": True}

        out = pairwise_judge(i, {"text": "预算 100万"}, {"text": "无关"},
                             env={"pairwise_judge": fake_pw})
        # 比较型 judge 的结论优先于 pointwise 差值：pointwise 会选 a，这里选 b
        self.assertEqual(out["winner"], "b")
        self.assertTrue(out["position_bias_controlled"])
        self.assertTrue(out["orders_agree"])
        self.assertEqual(len(calls), 1)

    def test_pairwise_reports_order_disagreement(self):
        """两次换位结论打架时，结论应作废为 tie 而不是取平均。"""
        i = rubric_inst(["预算"])

        def flaky_pw(prompt, a, b, dims):
            return {"winner": "A", "consistent": False}

        out = pairwise_judge(i, {"text": "预算 100万"}, {"text": "无关"},
                             env={"pairwise_judge": flaky_pw})
        self.assertFalse(out["orders_agree"])


# ------------------------------------------------------------------- ifeval
class TestFormatCompliance(unittest.TestCase):
    def test_word_count(self):
        i = rubric_inst(["ifeval:word_count_at_least:5"])
        self.assertEqual(format_compliance(i, {"text": "one two three four five"})["score"], 1.0)
        self.assertEqual(format_compliance(i, {"text": "too short"})["score"], 0.0)

    def test_no_commas(self):
        i = rubric_inst(["ifeval:no_commas:"])
        self.assertEqual(format_compliance(i, {"text": "no commas here"})["score"], 1.0)
        self.assertEqual(format_compliance(i, {"text": "yes, commas"})["score"], 0.0)
        self.assertEqual(format_compliance(i, {"text": "中文，逗号"})["score"], 0.0)

    def test_json_format(self):
        i = rubric_inst(["ifeval:json_format:"])
        self.assertEqual(format_compliance(i, {"text": '{"a": 1}'})["score"], 1.0)
        self.assertEqual(format_compliance(i, {"text": "```json\n{\"a\": 1}\n```"})["score"], 1.0)
        self.assertEqual(format_compliance(i, {"text": "not json"})["score"], 0.0)

    def test_lowercase_and_end_phrase(self):
        i = rubric_inst(["ifeval:all_lowercase:", "ifeval:end_with:thanks for reading"])
        self.assertEqual(format_compliance(i, {"text": "hello thanks for reading"})["score"], 1.0)
        r = format_compliance(i, {"text": "Hello thanks for reading"})
        self.assertEqual(r["score"], 0.5)

    def test_unsupported_constraint_is_reported_not_passed(self):
        i = rubric_inst(["ifeval:speak_farsi:"])
        r = format_compliance(i, {"text": "whatever"})
        self.assertEqual(r["sub_metrics"]["constraints_checked"], 0)
        self.assertEqual(r["sub_metrics"]["unsupported"], ["ifeval:speak_farsi:"])
        self.assertFalse(r["passed"])

    def test_semantic_entries_deferred(self):
        i = rubric_inst(["提到预算", "ifeval:no_commas:"])
        r = format_compliance(i, {"text": "no commas"})
        self.assertEqual(r["sub_metrics"]["semantic_deferred"], 1)
        self.assertEqual(r["score"], 1.0)

    def test_bullets_and_sections(self):
        i = rubric_inst(["ifeval:bullet_count:2", "ifeval:sections_at_least:1"])
        text = "# Title\n- a\n- b\n"
        self.assertEqual(format_compliance(i, {"text": text})["score"], 1.0)


# --------------------------------------------------------------------- code
def code_inst(test_code):
    return inst("G7", "CODE_FUNCTION",
                {"type": "executable",
                 "value": {"tests": [{"kind": "unittest", "code": test_code}],
                           "ref_solution": None, "timeout_s": 20}},
                "exec_tests")


TEST_CODE = ("import unittest\n\nclass T(unittest.TestCase):\n"
             "    def test_x(self):\n        self.assertEqual(task_func('a b a'), {'a': 2, 'b': 1})\n")


class TestExecTests(unittest.TestCase):
    def test_correct_code_passes(self):
        good = ("def task_func(text):\n    d = {}\n    for w in text.split():\n"
                "        d[w] = d.get(w, 0) + 1\n    return d\n")
        r = exec_tests(code_inst(TEST_CODE), {"text": "```python\n%s```" % good})
        self.assertEqual(r["score"], 1.0)
        self.assertTrue(r["passed"])

    def test_wrong_code_fails(self):
        bad = "def task_func(text):\n    return {}\n"
        r = exec_tests(code_inst(TEST_CODE), {"text": bad})
        self.assertEqual(r["score"], 0.0)
        self.assertFalse(r["detail"]["per_test"][0]["ok"])

    def test_syntax_error_reported(self):
        r = exec_tests(code_inst(TEST_CODE), {"text": "def task_func(:\n"})
        self.assertEqual(r["sub_metrics"]["syntax_ok"], 0.0)
        self.assertIn("SyntaxError", r["detail"]["error"])

    def test_infinite_loop_times_out(self):
        i = code_inst(TEST_CODE)
        i.gold["value"]["timeout_s"] = 2
        r = exec_tests(i, {"text": "def task_func(text):\n    while True:\n        pass\n"})
        self.assertEqual(r["score"], 0.0)
        self.assertTrue(r["detail"]["per_test"][0]["timeout"])


if __name__ == "__main__":
    unittest.main()
