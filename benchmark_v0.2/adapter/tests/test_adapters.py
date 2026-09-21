"""Every registered adapter must convert its fixture into valid instances."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter as pkg  # noqa: E402
from adapter.base import AdapterConfig, CANARY_UUID, detect_lang, slugify  # noqa: E402
from adapter.registry import adapter_items, get_adapter, get_checker, has_checker  # noqa: E402
from adapter.adapters.beir import BM25Lite  # noqa: E402
from adapter.adapters.bird_sql import sql_complexity  # noqa: E402
from adapter.adapters.ifeval import translate  # noqa: E402
from adapter.adapters.tau2_bench import is_write_tool  # noqa: E402
from adapter.schema import validate_instance  # noqa: E402
from adapter.utils.io import read_json, read_jsonl  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "adapter", "fixtures")


def load_aux(name):
    p = os.path.join(FIX, "%s_aux.json" % name)
    return read_json(p) if os.path.exists(p) else {}


def convert_all(name, **cfg_kw):
    cls = get_adapter(name)
    cfg = AdapterConfig(aux=load_aux(name), **cfg_kw)
    a = cls(cfg)
    rows = list(a.run(read_jsonl(os.path.join(FIX, "%s.jsonl" % name)), cfg))
    return a, rows


class TestAllAdapters(unittest.TestCase):
    def test_at_least_six_adapters(self):
        self.assertGreaterEqual(len(adapter_items()), 6)

    def test_every_adapter_has_a_fixture(self):
        for name, _cls in adapter_items():
            self.assertTrue(os.path.exists(os.path.join(FIX, "%s.jsonl" % name)),
                            "missing fixture for %s" % name)

    def test_every_adapter_converts_and_validates(self):
        for name, _cls in adapter_items():
            a, rows = convert_all(name)
            self.assertGreater(len(rows), 0, "%s produced nothing" % name)
            for inst in rows:
                errs = validate_instance(inst.to_dict())
                self.assertEqual(errs, [], "%s -> %s: %s" % (name, inst.id, errs))

    def test_source_is_public_dataset_at_version(self):
        for name, _cls in adapter_items():
            _a, rows = convert_all(name)
            for inst in rows:
                self.assertTrue(inst.source.startswith("public:"), inst.source)
                self.assertIn("@", inst.source)

    def test_checker_is_registered_and_supports_gold_type(self):
        for name, _cls in adapter_items():
            _a, rows = convert_all(name)
            for inst in rows:
                self.assertTrue(has_checker(inst.checker), inst.checker)
                spec = get_checker(inst.checker)
                self.assertTrue(spec.supports(inst.gold["type"]),
                                "%s: %s !supports %s" % (name, inst.checker,
                                                         inst.gold["type"]))

    def test_ids_unique_within_an_adapter(self):
        for name, _cls in adapter_items():
            _a, rows = convert_all(name)
            ids = [r.id for r in rows]
            self.assertEqual(len(ids), len(set(ids)), name)

    def test_manifest_has_a_row_per_instance(self):
        for name, _cls in adapter_items():
            a, rows = convert_all(name)
            m = a.manifest()
            self.assertEqual(len(m["rows"]), len(rows), name)
            self.assertIn("license", m)
            self.assertIn(m["commercial_use"], ("yes", "no", "conditional", "unknown"))
            self.assertEqual(m["stats"]["converted"], len(rows))

    def test_split_and_canary_marker(self):
        _a, rows = convert_all("simpleqa", split="canary")
        self.assertTrue(all(r.split == "canary" for r in rows))
        self.assertTrue(all(CANARY_UUID in r.prompt for r in rows))
        _a2, rows2 = convert_all("simpleqa", split="dev")
        self.assertTrue(all(CANARY_UUID not in r.prompt for r in rows2))

    def test_extra_must_not_injected(self):
        _a, rows = convert_all("simpleqa", extra_must_not=["自定义禁令"])
        self.assertTrue(all("自定义禁令" in r.must_not for r in rows))

    def test_limit_and_seq_start(self):
        _a, rows = convert_all("simpleqa", limit=1, seq_start=42)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].id.endswith("-0042"))

    def test_difficulty_override(self):
        _a, rows = convert_all("simpleqa", difficulty_override="L3")
        self.assertTrue(all(r.difficulty == "L3" for r in rows))


class TestBirdSql(unittest.TestCase):
    def test_non_select_filtered(self):
        a, rows = convert_all("bird_sql")
        self.assertEqual(a.stats.filtered, 1)          # the DELETE row
        self.assertEqual(len(rows), 3)

    def test_gold_shape(self):
        _a, rows = convert_all("bird_sql")
        g = rows[0].gold
        self.assertEqual(g["type"], "executable")
        self.assertIn("tests", g["value"])
        self.assertIn("ref_solution", g["value"])
        self.assertIn("timeout_s", g["value"])

    def test_ddl_attached_and_prompt_has_schema(self):
        _a, rows = convert_all("bird_sql")
        self.assertIn("CREATE TABLE", rows[0].context["db_schema"]["ddl"])
        self.assertIn("CREATE TABLE", rows[0].prompt)
        self.assertTrue(rows[0].context["db_schema"]["snapshot_ref"].startswith("blob://sha256:"))

    def test_order_by_sets_order_sensitive(self):
        _a, rows = convert_all("bird_sql")
        by_order = {r.id: r.gold["value"]["tests"][0]["order_sensitive"] for r in rows}
        self.assertIn(True, by_order.values())
        self.assertIn(False, by_order.values())

    def test_difficulty_heuristic(self):
        self.assertEqual(sql_complexity("SELECT a FROM t")["joins"], 0)
        c = sql_complexity("SELECT x FROM a JOIN b ON 1 JOIN c ON 1 GROUP BY x")
        self.assertEqual(c["joins"], 2)
        self.assertEqual(c["group_by"], 1)
        self.assertEqual(sql_complexity("SELECT RANK() OVER (ORDER BY a) FROM t")["window"], 1)

    def test_missing_db_raises(self):
        cls = get_adapter("bird_sql")
        cfg = AdapterConfig(aux={"dbs": {}})
        a = cls(cfg)
        with self.assertRaises(KeyError):
            list(a.run(read_jsonl(os.path.join(FIX, "bird_sql.jsonl")), cfg))

    def test_endtoend_gold_sql_actually_passes_its_own_checker(self):
        _a, rows = convert_all("bird_sql")
        for r in rows:
            res = pkg.run_check(r, {"text": r.gold["value"]["ref_solution"]})
            self.assertEqual(res["score"], 1.0, r.id)


class TestBigCodeBench(unittest.TestCase):
    def test_stdlib_only_option_filters_third_party(self):
        a, rows = convert_all("bigcodebench", options={"stdlib_only": True})
        self.assertEqual(len(rows), 2)
        self.assertEqual(a.stats.filtered, 1)

    def test_canonical_solution_passes_exec_tests(self):
        _a, rows = convert_all("bigcodebench", options={"stdlib_only": True})
        for r in rows:
            res = pkg.run_check(r, {"text": r.gold["value"]["ref_solution"]})
            self.assertEqual(res["score"], 1.0, r.id)


class TestSimpleQA(unittest.TestCase):
    def test_single_fact_mapping(self):
        _a, rows = convert_all("simpleqa")
        facts = rows[0].gold["value"]["facts"]
        self.assertEqual(len(facts), 1)
        self.assertTrue(facts[0]["required"])

    def test_empty_question_filtered(self):
        a, _rows = convert_all("simpleqa")
        self.assertEqual(a.stats.filtered, 1)

    def test_aliases_become_alternatives(self):
        _a, rows = convert_all("chinese_simpleqa")
        self.assertIn("|", rows[0].gold["value"]["facts"][0]["text"])

    def test_zh_detection(self):
        _a, rows = convert_all("chinese_simpleqa")
        self.assertTrue(all(r.lang == "zh" for r in rows))

    def test_distinct_subtype_avoids_id_collision(self):
        _a, en = convert_all("simpleqa")
        _b, zh = convert_all("chinese_simpleqa")
        self.assertFalse(set(r.id for r in en) & set(r.id for r in zh))


class TestFrames(unittest.TestCase):
    def test_placeholder_facts_are_optional(self):
        _a, rows = convert_all("frames")
        r = rows[0]
        self.assertTrue(r.gold["value"]["facts"][0]["required"])
        self.assertTrue(all(not f["required"] for f in r.gold["value"]["facts"][1:]))

    def test_manual_annotation_flagged_in_manifest(self):
        a, _rows = convert_all("frames")
        m = a.manifest()
        self.assertTrue(m["manual_annotation_required"])
        self.assertTrue(all(row["needs_manual_annotation"] for row in m["rows"]))
        self.assertTrue(all(row["annotation_state"] == "pending_fact_split" for row in m["rows"]))

    def test_hops_drive_difficulty(self):
        _a, rows = convert_all("frames")
        diffs = {r.id: r.difficulty for r in rows}
        self.assertIn("L3", diffs.values())
        self.assertIn("L1", diffs.values())


class TestBeir(unittest.TestCase):
    def test_query_without_positives_filtered(self):
        a, rows = convert_all("beir")
        self.assertEqual(a.stats.filtered, 1)
        self.assertEqual(len(rows), 3)

    def test_positives_always_in_pool(self):
        _a, rows = convert_all("beir")
        for r in rows:
            pool = {d["doc_id"] for d in r.context["kb_docs"]}
            for d in r.gold["value"]["doc_ids"]:
                self.assertIn(d, pool)

    def test_hard_negatives_preferred_over_random(self):
        _a, rows = convert_all("beir", options={"pool_size": 4, "hard_negatives": 3})
        r = rows[0]
        roles = [d["role"] for d in r.context["kb_docs"]]
        self.assertIn("hard_negative", roles)
        # for the vitamin-D query, d2/d3 (same topic) must beat the unrelated d10
        pool = {d["doc_id"] for d in r.context["kb_docs"]}
        self.assertIn("d2", pool)

    def test_pool_size_respected(self):
        _a, rows = convert_all("beir", options={"pool_size": 5})
        for r in rows:
            self.assertLessEqual(len(r.context["kb_docs"]), 5)

    def test_downsampling_recorded_in_manifest(self):
        a, _rows = convert_all("beir", options={"pool_size": 5})
        for row in a.manifest()["rows"]:
            self.assertEqual(row["downsampled_from"], 12)
            self.assertLessEqual(row["pool_size"], 5)

    def test_graded_relevance_carried(self):
        _a, rows = convert_all("beir")
        self.assertTrue(any(r.gold["value"]["graded"] for r in rows))

    def test_bm25_ranks_topically_related_first(self):
        aux = load_aux("beir")
        bm = BM25Lite(aux["corpus"])
        q = "vitamin D respiratory infection"
        self.assertGreater(bm.score(q, "d1"), bm.score(q, "d10"))

    def test_gold_positives_pass_the_checker(self):
        _a, rows = convert_all("beir")
        for r in rows:
            res = pkg.run_check(r, {"citations": r.gold["value"]["doc_ids"]})
            self.assertEqual(res["score"], 1.0, r.id)


class TestDabstep(unittest.TestCase):
    def test_not_applicable_filtered(self):
        a, rows = convert_all("dabstep")
        self.assertEqual(a.stats.filtered, 1)
        self.assertEqual(len(rows), 3)

    def test_numeric_and_literal_answers(self):
        _a, rows = convert_all("dabstep")
        vals = [r.gold["value"]["value"] for r in rows]
        self.assertIn(184320.55, vals)
        self.assertIn("NexPay", vals)
        pct = [v for v in vals if isinstance(v, float) and v < 1]
        self.assertAlmostEqual(pct[0], 0.0247, places=9)   # "2.47%" -> fraction

    def test_files_referenced_not_inlined(self):
        _a, rows = convert_all("dabstep")
        f = rows[0].context["files"][0]
        self.assertTrue(f["content_ref"].startswith("blob://sha256:"))
        self.assertNotIn("content", f)

    def test_gold_value_passes_checker(self):
        _a, rows = convert_all("dabstep")
        for r in rows:
            res = pkg.run_check(r, {"text": "Answer: %s" % r.gold["value"]["value"]})
            self.assertEqual(res["score"], 1.0, r.id)


class TestTau2(unittest.TestCase):
    def test_read_only_task_filtered(self):
        a, rows = convert_all("tau2_bench")
        self.assertEqual(a.stats.filtered, 1)
        self.assertEqual(len(rows), 2)

    def test_trace_gold_shape(self):
        _a, rows = convert_all("tau2_bench")
        v = rows[0].gold["value"]
        self.assertIn("final_state", v)
        self.assertIn("valid_sequences", v)
        self.assertIn("forbidden_calls", v)

    def test_unused_write_tools_become_forbidden(self):
        _a, rows = convert_all("tau2_bench")
        r = rows[0]
        self.assertIn("retail.cancel_order", r.gold["value"]["forbidden_calls"])
        self.assertNotIn("retail.update_order_address", r.gold["value"]["forbidden_calls"])
        self.assertNotIn("retail.get_order", r.gold["value"]["forbidden_calls"])

    def test_tools_available_dotted(self):
        _a, rows = convert_all("tau2_bench")
        self.assertTrue(all("." in t for r in rows for t in r.tools_available))

    def test_is_write_tool(self):
        self.assertTrue(is_write_tool("crm.update_user"))
        self.assertTrue(is_write_tool("crm.cancel_order"))
        self.assertFalse(is_write_tool("crm.get_user"))

    def test_extra_sequences_option(self):
        _a, rows = convert_all(
            "tau2_bench",
            options={"extra_sequences": {"retail_001": [["retail.update_order_address"]]}})
        self.assertEqual(len(rows[0].gold["value"]["valid_sequences"]), 2)

    def test_reference_trace_passes_checker(self):
        _a, rows = convert_all("tau2_bench")
        r = rows[0]
        resp = {"text": "Updated to 88 Century Ave, Shanghai",
                "final_state": {"orders": [{"id": "W1001", "user_id": "user_7",
                                            "status": "pending",
                                            "address": "88 Century Ave, Shanghai"}]},
                "tool_calls": [{"name": n} for n in r.gold["value"]["valid_sequences"][0]]}
        res = pkg.run_check(r, resp)
        self.assertEqual(res["score"], 1.0)
        self.assertTrue(res["passed"])


class TestIFEval(unittest.TestCase):
    def test_constraints_translated_to_dsl(self):
        _a, rows = convert_all("ifeval")
        mc = rows[0].gold["value"]["must_cover"]
        self.assertIn("ifeval:no_commas:", mc)
        self.assertIn("ifeval:word_count_at_least:300", mc)

    def test_untranslatable_row_filtered_and_recorded(self):
        a, rows = convert_all("ifeval")
        self.assertEqual(a.stats.filtered, 1)          # the farsi-only row
        untrans = [r["untranslated_constraints"] for r in a.manifest()["rows"]]
        self.assertIn(["detectable_format:number_highlighted_sections"], untrans)

    def test_checker_is_l1_not_l3(self):
        _a, rows = convert_all("ifeval")
        for r in rows:
            self.assertEqual(r.checker, "format_compliance")
            self.assertEqual(get_checker(r.checker).layer, "L1")

    def test_rubric_dims_still_schema_valid(self):
        _a, rows = convert_all("ifeval")
        self.assertAlmostEqual(sum(d["weight"] for d in rows[0].gold["value"]["dims"]), 1.0)

    def test_translate_unknown_returns_none(self):
        self.assertIsNone(translate("language:response_language", {"language": "fa"}))
        self.assertEqual(translate("punctuation:no_comma", {}), "ifeval:no_commas:")


class TestHelpers(unittest.TestCase):
    def test_slugify_ascii(self):
        self.assertEqual(slugify("sql query"), "SQL_QUERY")
        self.assertEqual(slugify(""), "MISC")

    def test_slugify_registered_chinese_subtype(self):
        self.assertEqual(slugify("复杂宽表统计"), "WIDE_TABLE_STATS")

    def test_slugify_unregistered_chinese_is_stable_and_unique(self):
        a = slugify("复杂 宽表-统计")
        b = slugify("另一个中文子类")
        self.assertTrue(a.startswith("SUB_"))
        self.assertNotEqual(a, b)                      # no MISC collision
        self.assertEqual(a, slugify("复杂 宽表-统计"))   # deterministic

    def test_detect_lang(self):
        self.assertEqual(detect_lang("hello world"), "en")
        self.assertEqual(detect_lang("你好世界"), "zh")
        self.assertEqual(detect_lang("这是一个 mixed 中文 sentence with 很多 english words here"),
                         "mixed")


if __name__ == "__main__":
    unittest.main()
