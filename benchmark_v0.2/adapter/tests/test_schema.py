"""SCHEMA_v0.1.md conformance tests."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapter.schema import (  # noqa: E402
    ModelResponse,
    SchemaError,
    TaskInstance,
    new_checker_result,
    validate_checker_result,
    validate_instance,
)

VALID = {
    "id": "G7-SQL_QUERY-0001",
    "category": "G7",
    "subtype": "SQL_QUERY",
    "difficulty": "L2",
    "lang": "zh",
    "context": {"files": [], "db_schema": {"dialect": "sqlite", "ddl": "CREATE TABLE t(a);",
                                           "snapshot_ref": None},
                "kb_docs": []},
    "tools_available": [],
    "prompt": "查询 t 的行数",
    "gold": {"type": "executable",
             "value": {"tests": [{"kind": "sql", "gold_sql": "SELECT COUNT(*) FROM t"}],
                       "ref_solution": "SELECT COUNT(*) FROM t", "timeout_s": 30}},
    "checker": "sql_result_equiv",
    "must_not": ["执行 DROP"],
    "source": "public:bird-sql-minidev@v2-2024-06",
    "split": "dev",
}


def mutate(**kw):
    d = copy.deepcopy(VALID)
    d.update(kw)
    return d


class TestInstanceValidation(unittest.TestCase):
    def test_valid_instance(self):
        self.assertEqual(validate_instance(VALID), [])

    def test_roundtrip(self):
        inst = TaskInstance.from_dict(VALID)
        self.assertEqual(inst.to_dict(), VALID)
        self.assertEqual(list(inst.to_dict().keys()), list(VALID.keys()))

    def test_unknown_field_rejected(self):
        d = mutate(extra_field=1)
        self.assertTrue(any("unknown field" in e for e in validate_instance(d)))
        with self.assertRaises(SchemaError):
            TaskInstance.from_dict(d)

    def test_missing_field_rejected(self):
        d = copy.deepcopy(VALID)
        del d["split"]
        self.assertTrue(any("missing field" in e for e in validate_instance(d)))

    def test_bad_id_format(self):
        for bad in ("g7-SQL-0001", "G7-SQL-1", "G11-SQL-0001", "G7-sql-0001", "SQL-0001"):
            self.assertTrue(validate_instance(mutate(id=bad)), bad)

    def test_id_prefix_must_match_category(self):
        errs = validate_instance(mutate(id="G1-SQL_QUERY-0001"))
        self.assertTrue(any("id prefix" in e for e in errs))

    def test_category_enum_closed(self):
        self.assertTrue(validate_instance(mutate(category="G11", id="G11-X-0001")))

    def test_difficulty_lang_split_enums(self):
        self.assertTrue(validate_instance(mutate(difficulty="easy")))
        self.assertTrue(validate_instance(mutate(lang="jp")))
        self.assertTrue(validate_instance(mutate(split="train")))

    def test_source_formats(self):
        ok = ["public:simpleqa@2024-10", "synthetic:pipe_a@run_17",
              "prod_log_20260801", "expert_authored", "adversarial"]
        for s in ok:
            self.assertEqual(validate_instance(mutate(source=s)), [], s)
        for bad in ["public:simpleqa", "simpleqa@2024", "public:@1", "public:x@", "whatever"]:
            self.assertTrue(validate_instance(mutate(source=bad)), bad)

    def test_tools_must_be_dotted(self):
        self.assertTrue(validate_instance(mutate(tools_available=["jira create"])))
        self.assertEqual(validate_instance(mutate(tools_available=["jira.create"])), [])

    def test_context_unknown_key(self):
        ctx = {"files": [], "db_schema": None, "kb_docs": [], "bogus": 1}
        self.assertTrue(validate_instance(mutate(context=ctx)))

    def test_kb_docs_duplicate_ids(self):
        ctx = {"files": [], "db_schema": None,
               "kb_docs": [{"doc_id": "a"}, {"doc_id": "a"}]}
        self.assertTrue(any("duplicate" in e for e in validate_instance(mutate(context=ctx))))


class TestGoldShapes(unittest.TestCase):
    def test_executable_requires_tests_and_timeout(self):
        g = {"type": "executable", "value": {"tests": [], "timeout_s": 30}}
        self.assertTrue(validate_instance(mutate(gold=g)))
        g = {"type": "executable", "value": {"tests": [{"kind": "sql"}], "timeout_s": 0}}
        self.assertTrue(validate_instance(mutate(gold=g)))

    def test_factlist(self):
        g = {"type": "factlist",
             "value": {"facts": [{"id": "f1", "text": "x", "required": True}],
                       "ref_answer": "x"}}
        self.assertEqual(validate_instance(mutate(gold=g, checker="fact_recall")), [])
        g2 = {"type": "factlist", "value": {"facts": [{"id": "f1", "text": "x"}]}}
        self.assertTrue(validate_instance(mutate(gold=g2)))

    def test_rubric_weights_must_sum_to_one(self):
        dims = [{"name": "a", "weight": 0.5, "anchors": {"1": "bad", "5": "good"}},
                {"name": "b", "weight": 0.4, "anchors": {"1": "bad", "5": "good"}}]
        g = {"type": "rubric", "value": {"dims": dims, "must_cover": []}}
        self.assertTrue(any("sum to 1.0" in e for e in validate_instance(mutate(gold=g))))
        dims[1]["weight"] = 0.5
        self.assertEqual(validate_instance(mutate(gold=g, checker="rubric_judge")), [])

    def test_rubric_anchor_keys_are_digits(self):
        dims = [{"name": "a", "weight": 1.0, "anchors": {"low": "bad"}}]
        g = {"type": "rubric", "value": {"dims": dims, "must_cover": []}}
        self.assertTrue(validate_instance(mutate(gold=g)))

    def test_trace(self):
        g = {"type": "trace", "value": {"final_state": {"t": []}, "valid_sequences": [["a.b"]],
                                        "forbidden_calls": []}}
        self.assertEqual(validate_instance(mutate(gold=g, checker="state_diff")), [])
        g_bad = {"type": "trace", "value": {"final_state": [], "valid_sequences": []}}
        self.assertTrue(validate_instance(mutate(gold=g_bad)))

    def test_reference_must_cite_subset_of_doc_ids(self):
        g = {"type": "reference", "value": {"doc_ids": ["d1"], "must_cite": ["d9"], "value": None}}
        self.assertTrue(any("must_cite" in e for e in validate_instance(mutate(gold=g))))
        g["value"]["must_cite"] = ["d1"]
        self.assertEqual(validate_instance(mutate(gold=g, checker="doc_recall_at_k")), [])

    def test_gold_type_closed(self):
        g = {"type": "freeform", "value": {}}
        self.assertTrue(validate_instance(mutate(gold=g)))


class TestCheckerResult(unittest.TestCase):
    def test_shape(self):
        r = new_checker_result(0.5, False, "L2", {"a": 1}, ["v"], {"d": 1})
        self.assertEqual(validate_checker_result(r), [])
        self.assertEqual(sorted(r.keys()),
                         sorted(["score", "passed", "layer", "sub_metrics", "violations",
                                 "detail", "cost"]))
        self.assertEqual(set(r["cost"]), {"tokens", "usd", "wall_s"})

    def test_score_clamped(self):
        self.assertEqual(new_checker_result(5.0)["score"], 1.0)
        self.assertEqual(new_checker_result(-1.0)["score"], 0.0)

    def test_bad_layer(self):
        with self.assertRaises(SchemaError):
            new_checker_result(1.0, True, "L9")


class TestModelResponse(unittest.TestCase):
    def test_coerce(self):
        self.assertEqual(ModelResponse.coerce("hi").text, "hi")
        r = ModelResponse.coerce({"text": "x", "tool_calls": [{"name": "a.b"}]})
        self.assertEqual(r.tool_calls[0]["name"], "a.b")
        self.assertIs(ModelResponse.coerce(r), r)
        with self.assertRaises(SchemaError):
            ModelResponse.coerce(42)


if __name__ == "__main__":
    unittest.main()
