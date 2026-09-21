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


SRC_DIR = {}          # instance_id -> 该实例所在目录（文件路径的解析根）


def load_all():
    out = []
    for name in sorted(os.listdir(DATASET)):
        d = os.path.join(DATASET, name)
        p = os.path.join(d, "instances.jsonl")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    SRC_DIR[r["id"]] = d
                    out.append(r)
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

    def test_context_files_on_disk_actually_reach_the_prompt(self):
        """磁盘上有的文件必须真的进 prompt。

        回归：context.files[].path 是相对门类目录的（"context/payments.csv"），
        以前统一按 dataset/ 解析，G6 的 7 个文件全被判成「不在本地」。模型
        在零数据的情况下被要求做数据分析，按题面要求答了 "Not Applicable"，
        判 0 分。判分系统自己没喂数据，却把账记在模型头上。
        """
        checked = 0
        for raw in load_all():
            files = (raw.get("context") or {}).get("files") or []
            if not files:
                continue
            root = SRC_DIR[raw["id"]]
            on_disk = [f["path"] for f in files
                       if os.path.exists(os.path.join(root, f["path"]))]
            if not on_disk:
                continue
            built = prompting.build_prompt(TaskInstance.from_dict(raw), root=root)
            notes = " ".join(built["meta"].get("file_notes") or [])
            for p in on_disk:
                self.assertNotIn("%s 不在本地" % p, notes,
                                 "%s: %s 在磁盘上却没进 prompt" % (raw["id"], p))
                self.assertIn(p, built["user"],
                              "%s: %s 没有出现在 prompt 里" % (raw["id"], p))
                checked += 1
        self.assertGreater(checked, 0, "没有任何带 context.files 的实例被检查到")

    def test_big_file_is_marked_as_sampled(self):
        """G6 的 23MB payments.csv 只能给抽样，必须明说，不能假装完整。

        注意这里**不再**接受「不在本地」—— 原版把缺失也算通过，等于给
        路径解析 bug 开了绿灯。文件在磁盘上，就必须是「截断」而不是「缺失」。
        """
        raw = next(r for r in load_all() if r["category"] == "G6")
        root = SRC_DIR[raw["id"]]
        built = prompting.build_prompt(TaskInstance.from_dict(raw), root=root)
        notes = built["meta"].get("file_notes") or []
        self.assertTrue(any("截断" in n for n in notes),
                        "大文件没有被标记为抽样: %s" % notes)


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


class TestAnthropicTemperatureDeprecation(unittest.TestCase):
    """新版 Claude（opus-4-8）拒收 temperature，客户端要能摘参重试并留痕。"""

    def _model(self, err=None):
        """伪服务端：只要 payload 里带 temperature 就 400，跟真 Vertex 一致。"""
        m = clients.VertexAnthropicModel("claude-opus-4-8",
                                         project="p", location="global")
        m._token = lambda: "tok"          # 不碰真 ADC
        self.seen = []
        boom = err or ("HTTP 400 {\"error\":{\"message\":"
                       "\"`temperature` is deprecated for this model.\"}}")

        def fake_post(url, headers, payload):
            self.seen.append(payload)
            if "temperature" in payload or err:
                m.usage.errors += 1       # 真 _post 抛之前也会记一笔
                raise clients.ModelError(boom)
            return {"body": {"content": [{"type": "text", "text": "ok"}],
                             "usage": {"input_tokens": 3, "output_tokens": 1},
                             "stop_reason": "end_turn"},
                    "latency_s": 0.01}

        m._post = fake_post
        return m

    def test_retries_without_temperature_and_records_it(self):
        m = self._model()
        out = m.generate("", "hi")
        self.assertEqual(out["text"], "ok")
        self.assertIn("temperature", self.seen[0])      # 第一次试着传了
        self.assertNotIn("temperature", self.seen[1])   # 第二次摘掉了
        self.assertEqual(m.dropped_params, ["temperature"])
        # 探测用的那次 400 不该算成模型故障
        self.assertEqual(m.usage.errors, 0)

    def test_does_not_retry_forever(self):
        """摘过一次之后就不再传，后续请求只发一次。"""
        m = self._model()
        m.generate("", "hi")
        self.seen.clear()
        m.generate("", "hi again")
        self.assertEqual(len(self.seen), 1)
        self.assertNotIn("temperature", self.seen[0])

    def test_other_400_still_raises(self):
        """别的 400 不能被这条自适应顺手吞掉。"""
        m = self._model(err="HTTP 400 {\"error\":{\"message\":\"bad model\"}}")
        with self.assertRaises(clients.ModelError):
            m.generate("", "hi")
        self.assertEqual(m.dropped_params, [])


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


class TestRescore(unittest.TestCase):
    """重判必须只动判分结果，绝不能改写模型侧的事实。

    这个工具存在的理由是：金标/判分器改了以后不该逼人再烧一遍 API。
    但它有个很容易犯的错 —— 重判时 ScriptedModel 会重新"生成"一次，
    于是 tokens / usd / latency 全被写成脚本化模型的假值，成本象限
    就被悄悄清零了。下面两条就是钉住这件事。
    """

    def setUp(self):
        import rescore
        self.rescore = rescore

    def _fake_record(self):
        return {
            "instance_id": "X-1",
            "category": "GX",
            "checker_id": "format_compliance",
            "model": "vertex-google/some-real-model",
            "instance": {},
            "status": "ok",
            "raw_text": "no commas here",
            "finish_reason": "stop",
            "judge_caveat": "同厂商 judge，仅供参考",
            "result": {
                "score": 0.0, "passed": False, "layer": "L1",
                "sub_metrics": {}, "violations": [], "detail": {},
                "cost": {"tokens": 4321, "prompt_tokens": 4000,
                         "completion_tokens": 321, "usd": 0.0123,
                         "latency_s": 9.87, "wall_s": 0.001},
            },
        }

    def _fresh_instance(self, must_cover):
        return {
            "id": "X-1", "category": "GX", "subtype": "S", "difficulty": "L1",
            "lang": "en", "prompt": "write something",
            "context": {"files": [], "db_schema": None, "kb_docs": []},
            "tools_available": [],
            "gold": {"type": "rubric",
                     "value": {"dims": [], "must_cover": must_cover}},
            "checker": "format_compliance", "must_not": [],
            "source": "expert_authored", "split": "dev",
        }

    def test_model_side_facts_survive_rescoring(self):
        rec = self._fake_record()
        new = self.rescore.rescore_record(
            rec, self._fresh_instance(["ifeval:no_commas:"]),
            DATASET, None, 4000)

        self.assertEqual(new["model"], "vertex-google/some-real-model")
        self.assertEqual(new["finish_reason"], "stop")
        self.assertEqual(new["judge_caveat"], "同厂商 judge，仅供参考")
        cost = new["result"]["cost"]
        self.assertEqual(cost["tokens"], 4321)
        self.assertEqual(cost["prompt_tokens"], 4000)
        self.assertEqual(cost["completion_tokens"], 321)
        self.assertEqual(cost["usd"], 0.0123)
        self.assertEqual(cost["latency_s"], 9.87)

    def test_rescore_uses_the_gold_on_disk_not_the_stored_snapshot(self):
        rec = self._fake_record()
        # 记录里存的旧金标是「必须有逗号」这种会失败的约束
        rec["instance"] = self._fresh_instance(["ifeval:word_count_at_least:99"])

        new = self.rescore.rescore_record(
            rec, self._fresh_instance(["ifeval:no_commas:"]),
            DATASET, None, 4000)
        # 用的是传进去的新金标，所以这次过了
        self.assertEqual(new["result"]["score"], 1.0)
        self.assertTrue(new["result"]["passed"])

    def test_judge_checkers_are_listed_so_they_can_be_skipped(self):
        # 不带 --judge 重判 rubric_judge，会把真 judge 的分换成桩分，
        # 比不重判更糟。所以这类 checker 必须在跳过名单里。
        self.assertIn("rubric_judge", self.rescore.JUDGE_CHECKERS)


class TestRouteDecide(unittest.TestCase):
    """加权路由决策。

    最容易出错的是归一化：四个维度刻度完全不同（0~1 的分数、秒、token 个数、
    美元），而且方向有正有反。用 min-max 归一化在只有两个模型时会退化成
    1 和 0，「贵 3%」和「贵 300%」长得一模一样 —— 所以这里用相对比值。
    """

    def setUp(self):
        import route_decide
        self.rd = route_decide

    def test_higher_better_keeps_magnitude(self):
        na, nb = self.rd.norm(0.8, 1.0, "quality")
        self.assertAlmostEqual(nb, 1.0)
        self.assertAlmostEqual(na, 0.8)

    def test_lower_better_is_inverted(self):
        # 延迟 2s vs 10s：快的拿 1.0，慢的拿 0.2
        na, nb = self.rd.norm(2.0, 10.0, "latency")
        self.assertAlmostEqual(na, 1.0)
        self.assertAlmostEqual(nb, 0.2)

    def test_min_max_degeneracy_is_avoided(self):
        """差 3% 和差 300% 必须给出不同的归一化结果。"""
        close = self.rd.norm(1.00, 1.03, "cost")
        far = self.rd.norm(1.00, 4.00, "cost")
        self.assertGreater(close[1], 0.9)
        self.assertLess(far[1], 0.3)

    def test_cost_uses_both_token_directions(self):
        recs = [{"category": "GX", "status": "ok",
                 "result": {"score": 1.0,
                            "cost": {"prompt_tokens": 1_000_000,
                                     "completion_tokens": 2_000_000,
                                     "latency_s": 1.0}}}]
        got = self.rd.per_category(recs, (3.0, 5.0))["GX"]
        # 1M * $3 + 2M * $5 = 3 + 10
        self.assertAlmostEqual(got["cost"], 13.0)

    def test_model_error_is_missing_not_zero(self):
        """请求失败不能当 0 分算进质量均值，否则等于拿对方的故障加分。"""
        recs = [{"category": "GX", "status": "ok",
                 "result": {"score": 1.0, "cost": {}}},
                {"category": "GX", "status": "model_error",
                 "result": {"score": None, "cost": {}}}]
        got = self.rd.per_category(recs, (0.0, 0.0))["GX"]
        self.assertAlmostEqual(got["quality"], 1.0)
        self.assertEqual(got["missing"], 1)

    def test_flip_point_solves_the_weight_that_changes_the_winner(self):
        # A 质量差、成本低；B 质量好、成本高
        dims = {"quality": {"na": 0.8, "nb": 1.0},
                "latency": {"na": 1.0, "nb": 1.0},
                "cost": {"na": 1.0, "nb": 0.0},
                "tokens_in": {"na": 1.0, "nb": 1.0},
                "tokens_out": {"na": 1.0, "nb": 1.0}}
        w = {"quality": 0.5, "latency": 0.0, "cost": 0.5,
             "tokens_in": 0.0, "tokens_out": 0.0}
        fp = self.rd.flip_point(dims, w, "cost")
        self.assertIsNotNone(fp)
        # 在翻转点上两边综合分应当相等
        rest = sum(v for k, v in w.items() if k != "cost")
        sa = (sum(w[k] * dims[k]["na"] for k in w if k != "cost")
              + fp * dims["cost"]["na"]) / (rest + fp)
        sb = (sum(w[k] * dims[k]["nb"] for k in w if k != "cost")
              + fp * dims["cost"]["nb"]) / (rest + fp)
        self.assertAlmostEqual(sa, sb, places=9)

    def test_gate_excludes_a_model_that_failed_admission(self):
        cat = {"GX": {"n": 1, "missing": 0, "quality": 1.0, "latency": 1.0,
                      "tokens_in": 1, "tokens_out": 1, "cost": 1.0}}
        # 质量只差一点点（0.9 vs 1.0）但便宜一万倍 —— 这才是门禁要防的场景
        cheap = {"GX": dict(cat["GX"], quality=0.9, cost=0.0001)}
        w = dict(self.rd.DEFAULT_WEIGHTS)
        # 不开门禁：成本优势足以盖过质量劣势，A 胜出
        off = self.rd.decide(cheap, cat, w, False,
                             {"GX": "FAIL"}, {"GX": "PASS"}, {})[0]
        self.assertEqual(off["winner"], "A")
        # 开门禁：准入 FAIL 直接出局，不许「便宜且快但答不对」胜出
        on = self.rd.decide(cheap, cat, w, True,
                            {"GX": "FAIL"}, {"GX": "PASS"}, {})[0]
        self.assertEqual(on["winner"], "B")

    def test_unusable_category_is_skipped_entirely(self):
        cat = {"G9": {"n": 1, "missing": 0, "quality": 0.0, "latency": 1.0,
                      "tokens_in": 1, "tokens_out": 1, "cost": 1.0}}
        rows = self.rd.decide(cat, cat, dict(self.rd.DEFAULT_WEIGHTS), False,
                              {"G9": "FAIL"}, {"G9": "FAIL"}, {"G9": "题目不可答"})
        self.assertIn("skip", rows[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
