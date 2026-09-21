"""Frozen schema: field set, enums, id format, gold.type mapping, CheckerResult."""

import json
import unittest

from synthgen.schema import (
    CATEGORIES,
    CATEGORY_GOLD_TYPE,
    TASK_FIELD_ORDER,
    Context,
    Gold,
    SchemaError,
    TaskInstance,
    ValidationError,
    make_checker_result,
    validate_checker_result,
)


def sample_dict(**over):
    data = {
        "id": "G7-SQL-0132",
        "category": "G7",
        "subtype": "复杂宽表统计",
        "difficulty": "L3",
        "lang": "zh",
        "context": {"files": [], "db_schema": None, "kb_docs": [], "env": None},
        "tools_available": ["jira.create", "ci.trigger"],
        "prompt": "请统计...",
        "gold": {"type": "executable", "value": None},
        "checker": "sql_result_equiv",
        "must_not": ["泄露客户手机号", "执行 DROP"],
        "source": "synthetic:g7_sql_reverse_v1@r0001",
        "split": "dev",
    }
    data.update(over)
    return data


class TestFrozenFields(unittest.TestCase):
    def test_field_order_is_frozen(self):
        inst = TaskInstance.from_dict(sample_dict())
        self.assertEqual(list(inst.to_dict().keys()), list(TASK_FIELD_ORDER))
        self.assertEqual(len(TASK_FIELD_ORDER), 13)

    def test_context_subfields_frozen(self):
        inst = TaskInstance.from_dict(sample_dict())
        self.assertEqual(
            list(inst.to_dict()["context"].keys()), ["files", "db_schema", "kb_docs", "env"]
        )

    def test_unknown_field_rejected(self):
        with self.assertRaises(SchemaError):
            TaskInstance.from_dict(sample_dict(extra_field=1))

    def test_missing_field_rejected(self):
        data = sample_dict()
        del data["checker"]
        with self.assertRaises(SchemaError):
            TaskInstance.from_dict(data)

    def test_roundtrip_is_stable(self):
        data = sample_dict()
        once = TaskInstance.from_dict(data).to_dict()
        twice = TaskInstance.from_dict(once).to_dict()
        self.assertEqual(once, twice)
        json.dumps(once, ensure_ascii=False)  # must be JSON serializable


class TestValidation(unittest.TestCase):
    def test_valid_instance(self):
        self.assertEqual(TaskInstance.from_dict(sample_dict()).validate(), [])

    def test_bad_category(self):
        errors = TaskInstance.from_dict(sample_dict(category="G11", id="G7-SQL-0001")).validate()
        self.assertTrue(any("category" in e for e in errors))

    def test_category_enum_is_exactly_g1_to_g10_plus_s(self):
        self.assertEqual(
            list(CATEGORIES), ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "S"]
        )

    def test_bad_difficulty_lang_split(self):
        errors = TaskInstance.from_dict(
            sample_dict(difficulty="L4", lang="jp", split="train")
        ).validate()
        self.assertTrue(any("difficulty" in e for e in errors))
        self.assertTrue(any("lang" in e for e in errors))
        self.assertTrue(any("split" in e for e in errors))

    def test_id_format(self):
        for bad in ("G7-SQL-132", "g7-SQL-0132", "G7SQL0132", "G11-SQL-0132", "G7-sql-0132"):
            errors = TaskInstance.from_dict(sample_dict(id=bad)).validate()
            self.assertTrue(errors, "expected {!r} to be rejected".format(bad))
        for good in ("G7-SQL-0132", "G10-WIDE_TABLE_STATS-0001", "S-JAILBREAK-9999"):
            cat = good.split("-", 1)[0]
            gold = {"type": CATEGORY_GOLD_TYPE.get(cat, "rubric"), "value": None}
            errors = TaskInstance.from_dict(sample_dict(id=good, category=cat, gold=gold)).validate()
            self.assertEqual(errors, [], "{} -> {}".format(good, errors))

    def test_id_prefix_must_match_category(self):
        errors = TaskInstance.from_dict(
            sample_dict(id="G9-SQL-0132", category="G7")
        ).validate()
        self.assertTrue(any("不一致" in e for e in errors))

    def test_gold_type_must_match_category(self):
        mapping = {
            "G7": "executable", "G1": "factlist", "G3": "factlist", "G8": "factlist",
            "G4": "rubric", "G5": "rubric", "G10": "rubric", "G9": "trace",
            "G2": "reference", "G6": "reference",
        }
        self.assertEqual(CATEGORY_GOLD_TYPE, mapping)
        for cat, gold_type in mapping.items():
            ok = TaskInstance.from_dict(
                sample_dict(id="{}-X-0001".format(cat), category=cat, gold={"type": gold_type, "value": 1})
            )
            self.assertEqual(ok.validate(), [])
            wrong = "rubric" if gold_type != "rubric" else "trace"
            bad = TaskInstance.from_dict(
                sample_dict(id="{}-X-0001".format(cat), category=cat, gold={"type": wrong, "value": 1})
            )
            self.assertTrue(any("gold.type" in e for e in bad.validate()))

    def test_source_format(self):
        errors = TaskInstance.from_dict(sample_dict(source="handmade")).validate()
        self.assertTrue(any("source" in e for e in errors))
        errors = TaskInstance.from_dict(sample_dict(source="synthetic:pipeline")).validate()
        self.assertTrue(any("run_id" in e for e in errors))

    def test_strict_raises(self):
        with self.assertRaises(ValidationError):
            TaskInstance.from_dict(sample_dict(split="train")).validate(strict=True)


class TestCheckerResult(unittest.TestCase):
    def test_shape(self):
        result = make_checker_result(0.5, layer="L2", sub_metrics={"a": 1.0})
        self.assertEqual(
            sorted(result), ["cost", "detail", "layer", "passed", "score", "sub_metrics", "violations"]
        )
        self.assertEqual(sorted(result["cost"]), ["tokens", "usd", "wall_s"])
        self.assertEqual(validate_checker_result(result), [])

    def test_violations_force_failure(self):
        result = make_checker_result(1.0, passed=True, violations=["执行 DROP"])
        self.assertFalse(result["passed"])

    def test_score_is_clamped(self):
        self.assertEqual(make_checker_result(2.5)["score"], 1.0)
        self.assertEqual(make_checker_result(-1.0)["score"], 0.0)

    def test_bad_layer_rejected(self):
        with self.assertRaises(ValueError):
            make_checker_result(1.0, layer="L9")

    def test_validate_detects_missing_keys(self):
        self.assertTrue(validate_checker_result({"score": 1.0}))


if __name__ == "__main__":
    unittest.main()
