#!/usr/bin/env python3
"""runner/ 的单元测试。

    cd runner && python3 -m unittest discover -s tests -p "test_*.py"

重点覆盖两件容易出事的事：
  1. 输出契约**不得泄露答案** —— 这个错误一旦发生，所有分数都是虚高的，
     而且不会有任何报错，非常难发现
  2. 解析的回落路径要能被识别出来 —— 「能力差」和「不听格式」必须可区分
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.dirname(HERE)
ROOT = os.path.dirname(RUNNER)
sys.path.insert(0, RUNNER)
sys.path.insert(0, os.path.join(ROOT, "benchmark_v0.2", "adapter"))

import clients      # noqa: E402
import parsing      # noqa: E402
import prompting    # noqa: E402
from adapter.schema import TaskInstance   # noqa: E402

DATASET = os.path.join(ROOT, "dataset")


def load_all():
    out = []
    for name in sorted(os.listdir(DATASET)):
        p = os.path.join(DATASET, name, "instances.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(json.loads(line))
    return out


class TestNoAnswerLeak(unittest.TestCase):
    """契约或上下文里出现金标 = 所有分数虚高且无声无息。"""

    def setUp(self):
        self.raws = load_all()

    def test_gold_answer_never_in_prompt(self):
        leaked = []
        for raw in self.raws:
            inst = TaskInstance.from_dict(raw)
            built = prompting.build_prompt(inst, root=DATASET)
            blob = built["system"] + built["user"]
            gv = raw["gold"].get("value") or {}

            needles = []
            for key in ("ref_answer", "ref_solution"):
                if isinstance(gv.get(key), str) and len(gv[key]) > 30:
                    needles.append((key, gv[key][:60]))
            # doc_ids 是答案；k 不是
            for did in (gv.get("doc_ids") or [])[:3]:
                needles.append(("doc_ids", str(did)))

            for key, needle in needles:
                if key == "doc_ids":
                    # doc_id 必然出现在候选池里（那是题面），
                    # 只检查它没有出现在「输出要求」段里
                    tail = built["user"].split("<输出要求>")[-1]
                    if needle in tail:
                        leaked.append((raw["id"], key))
                elif needle in blob:
                    leaked.append((raw["id"], key))
        self.assertEqual(leaked, [], "以下实例的 prompt 泄露了金标: %s" % leaked)

    def test_kb_docs_role_not_leaked(self):
        """kb_docs 里标了 positive / hard_negative，绝不能渲染进 prompt。

        不能直接搜 "positive" —— 文档正文里就有 "positive correlation"
        这种词，会误报（第一版测试就栽在这）。改用哨兵值：
        塞一个正文绝不可能出现的 role，看它有没有被渲染出来。
        """
        sentinel = "ROLE_SENTINEL_d41d8cd98f"
        docs = [{"doc_id": "d1", "title": "t", "text": "body",
                 "role": sentinel}]
        body, _ = prompting.render_kb_docs(docs, budget=10000)
        self.assertNotIn(sentinel, body)
        self.assertIn("d1", body)      # doc_id 是题面，必须在

        # 真实实例上再确认一遍 hard_negative 这个不会自然出现的词
        for raw in self.raws:
            if not ((raw.get("context") or {}).get("kb_docs")):
                continue
            inst = TaskInstance.from_dict(raw)
            rendered = prompting.build_prompt(inst, root=DATASET)["user"]
            self.assertNotIn("hard_negative", rendered, raw["id"])


class TestPromptCoverage(unittest.TestCase):
    def test_every_checker_has_a_contract(self):
        used = {r["checker"] for r in load_all()}
        missing = used - set(prompting.CONTRACTS)
        self.assertEqual(missing, set(), "缺少输出契约: %s" % missing)

    def test_every_checker_has_a_parser(self):
        for checker in prompting.CONTRACTS:
            try:
                parsing.parse(checker, "x")
            except KeyError:
                self.fail("判分器 %r 有契约但没有解析规则" % checker)

    def test_builds_for_all_instances(self):
        for raw in load_all():
            inst = TaskInstance.from_dict(raw)
            built = prompting.build_prompt(inst, root=DATASET)
            self.assertTrue(built["user"].strip(), raw["id"])
            self.assertIn("<输出要求>", built["user"], raw["id"])

    def test_g9_lists_tools_and_marks_simulation(self):
        raw = next(r for r in load_all() if r["checker"] == "state_diff")
        built = prompting.build_prompt(TaskInstance.from_dict(raw), root=DATASET)
        for tool in raw["tools_available"]:
            self.assertIn(tool, built["user"])
        # G9 是假执行，必须标出来，否则报表会把规划能力当成执行能力
        self.assertTrue(built["meta"]["simulated_execution"])

    def test_big_file_is_marked_as_sampled(self):
        """G6 的 23MB payments.csv 只能给抽样，必须明说，不能假装完整。"""
        raw = next(r for r in load_all() if r["category"] == "G6")
        built = prompting.build_prompt(TaskInstance.from_dict(raw), root=DATASET)
        notes = built["meta"].get("file_notes") or []
        self.assertTrue(any("截断" in n or "不在本地" in n for n in notes),
                        "大文件没有被标记为抽样/缺失: %s" % notes)


class TestParsing(unittest.TestCase):
    def test_citations_json(self):
        out = parsing.parse("doc_recall_at_k", '{"citations": ["a1", "b2"]}')
        self.assertEqual(out["response"]["citations"], ["a1", "b2"])
        self.assertEqual(out["parse"]["how"], "json")

    def test_citations_bracket_fallback_is_marked(self):
        """内容救回来了，但必须记下没按契约输出。"""
        out = parsing.parse("doc_recall_at_k", "我选 [a1] 和 [b2] 这两篇。")
        self.assertEqual(out["response"]["citations"], ["a1", "b2"])
        self.assertTrue(out["parse"]["ok"])
        self.assertEqual(out["parse"]["how"], "bracket_fallback")

    def test_citations_total_failure(self):
        out = parsing.parse("doc_recall_at_k", "我不知道。")
        self.assertFalse(out["parse"]["ok"])
        self.assertEqual(out["response"]["citations"], [])

    def test_numeric_answer_line(self):
        out = parsing.parse("numeric_em", "过程略。\nAnswer: 42.5")
        self.assertEqual(out["response"]["text"], "Answer: 42.5")
        self.assertEqual(out["parse"]["how"], "answer_line")

    def test_numeric_chinese_label(self):
        out = parsing.parse("numeric_em", "答案：NL")
        self.assertEqual(out["response"]["text"], "Answer: NL")

    def test_numeric_last_number_fallback(self):
        out = parsing.parse("numeric_em", "先算 10，再算 20，所以是 30")
        self.assertEqual(out["response"]["text"], "Answer: 30")
        self.assertEqual(out["parse"]["how"], "last_number_fallback")

    def test_sql_fenced(self):
        out = parsing.parse("sql_result_equiv", "```sql\nSELECT 1;\n```")
        self.assertEqual(out["response"]["text"], "SELECT 1;")

    def test_sql_bare_fallback(self):
        out = parsing.parse("sql_result_equiv", "SELECT a FROM t")
        self.assertTrue(out["parse"]["ok"])
        self.assertEqual(out["parse"]["how"], "bare_sql_fallback")

    def test_code_fenced_prefers_python(self):
        text = "```text\nnot code\n```\n```python\ndef f():\n    return 1\n```"
        out = parsing.parse("exec_tests", text)
        self.assertIn("def f", out["response"]["text"])
        self.assertNotIn("not code", out["response"]["text"])

    def test_state_diff_json(self):
        text = json.dumps({"tool_calls": [{"name": "a.b", "arguments": {"x": 1}}],
                           "final_state": {"k": 1}, "text": "done"})
        out = parsing.parse("state_diff", text)
        self.assertEqual(out["response"]["tool_calls"][0]["name"], "a.b")
        self.assertEqual(out["response"]["final_state"], {"k": 1})

    def test_state_diff_accepts_bare_tool_names(self):
        out = parsing.parse("state_diff",
                            '{"tool_calls": ["a.b", "c.d"], "final_state": {}}')
        self.assertEqual([c["name"] for c in out["response"]["tool_calls"]],
                         ["a.b", "c.d"])

    def test_state_diff_failure(self):
        out = parsing.parse("state_diff", "我会先建工单然后通知大家。")
        self.assertFalse(out["parse"]["ok"])

    def test_empty_text_is_flagged(self):
        out = parsing.parse("fact_recall", "   ")
        self.assertFalse(out["parse"]["ok"])


class TestClients(unittest.TestCase):
    def test_build_rejects_bad_spec(self):
        with self.assertRaises(ValueError):
            clients.build("gemini-3.8-flash")
        with self.assertRaises(ValueError):
            clients.build("nosuch:model")

    def test_provider_tags(self):
        self.assertEqual(clients.build("google:m").provider, "google")
        self.assertEqual(clients.build("anthropic:m").provider, "anthropic")

    def test_openai_gateway_can_declare_real_vendor(self):
        """网关代理别家模型时，厂商身份要如实标注，否则消偏红线会被绕过。"""
        m = clients.OpenAICompatModel("m", provider_name="anthropic")
        self.assertEqual(m.provider, "anthropic")

    def test_same_provider_as_judge_is_rejected(self):
        m = clients.build("google:m")
        with self.assertRaises(clients.ModelError):
            clients.assert_not_same_provider(m, "google")
        clients.assert_not_same_provider(m, "anthropic")   # 不同厂商放行
        clients.assert_not_same_provider(m, None)          # 没配 judge 不拦

    def test_scripted_missing_answer_raises(self):
        m = clients.ScriptedModel({"known": "hi"})
        m.current_id = "unknown"
        with self.assertRaises(clients.ModelError):
            m.generate("", "")

    def test_usage_accumulates(self):
        m = clients.ScriptedModel({"a": "x" * 40})
        m.current_id = "a"
        m.generate("", "y" * 80)
        self.assertEqual(m.usage.calls, 1)
        self.assertGreater(m.usage.prompt_tokens, 0)


class TestCompareStats(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, RUNNER)
        import compare
        self.compare = compare

    def test_sign_test_needs_six_decisive_pairs(self):
        """全胜 5 场的双侧 p=0.0625，仍不显著；6 场才到 0.03125。"""
        self.assertAlmostEqual(self.compare.binom_two_sided(5, 0), 0.0625)
        self.assertAlmostEqual(self.compare.binom_two_sided(6, 0), 0.03125)
        self.assertLessEqual(self.compare.binom_two_sided(6, 0), self.compare.ALPHA)
        self.assertGreater(self.compare.binom_two_sided(5, 0), self.compare.ALPHA)

    def test_all_ties_gives_no_pvalue(self):
        self.assertIsNone(self.compare.binom_two_sided(0, 0))

    def test_model_error_is_missing_not_zero(self):
        r = {"status": "model_error", "result": {"score": None}}
        self.assertIsNone(self.compare.usable_score(r))
        ok = {"status": "ok", "result": {"score": 0.0}}
        self.assertEqual(self.compare.usable_score(ok), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
