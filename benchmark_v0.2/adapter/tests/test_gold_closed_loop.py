"""Gold closed-loop gate: every instance's own gold must score 1.0.

The point of this file is to catch *checker* bugs, not model bugs. If feeding a
task its own reference answer does not yield a perfect score, the task is
unsolvable and will silently drag down every model that ever sees it.

This deliberately iterates **all** instances of **all** registered adapters.
An earlier spot-check style test only exercised ``rows[0]`` of tau2_bench,
which is exactly why the telecom instance below went unnoticed.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adapter as pkg  # noqa: E402
from adapter.base import AdapterConfig  # noqa: E402
from adapter.checkers.exec_tests import _missing_modules  # noqa: E402
from adapter.registry import adapter_items, get_adapter  # noqa: E402
from adapter.utils.io import read_json, read_jsonl  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "adapter", "fixtures")

# Checkers whose gold carries no reference *text* to replay. IFEval's gold is a
# list of constraints ("at least 300 words", "no commas"); satisfying them needs
# real generation, so there is nothing to feed back.
NO_REPLAYABLE_GOLD = {"format_compliance", "rubric_judge"}


def load_aux(name):
    p = os.path.join(FIX, "%s_aux.json" % name)
    return read_json(p) if os.path.exists(p) else {}


def convert_all(name):
    cls = get_adapter(name)
    cfg = AdapterConfig(aux=load_aux(name))
    a = cls(cfg)
    return a, list(a.run(read_jsonl(os.path.join(FIX, "%s.jsonl" % name)), cfg))


def gold_response(inst):
    """Rebuild the answer the gold itself implies.

    Dispatch on ``inst.checker``, never on which keys ``gold.value`` happens to
    have: DABStep's gold carries both ``doc_ids`` and ``value``, so key-sniffing
    silently routes a citation answer into ``numeric_em`` and scores 0.
    """
    v = inst.gold["value"]
    ck = inst.checker

    if ck in ("sql_result_equiv", "exec_tests"):
        return {"text": v["ref_solution"]}
    if ck == "fact_recall":
        return {"text": v["ref_answer"]}
    if ck == "doc_recall_at_k":
        return {"citations": v["doc_ids"]}
    if ck == "numeric_em":
        return {"text": "Answer: %s" % v["value"]}
    if ck == "state_diff":
        seqs = v.get("valid_sequences") or [[]]
        info = v.get("communicate_info") or []
        return {"text": "done. " + " ".join(str(x) for x in info),
                "final_state": v["final_state"],
                "tool_calls": [{"name": n} for n in seqs[0]]}
    return None


class TestGoldClosedLoop(unittest.TestCase):
    def test_every_gold_scores_one(self):
        checked = skipped = 0
        for name, _cls in adapter_items():
            _a, rows = convert_all(name)
            for inst in rows:
                resp = gold_response(inst)
                if resp is None:
                    self.assertIn(
                        inst.checker, NO_REPLAYABLE_GOLD,
                        "%s: checker %r has no gold replay rule -- add one to "
                        "gold_response() or declare it in NO_REPLAYABLE_GOLD"
                        % (inst.id, inst.checker))
                    skipped += 1
                    continue

                res = pkg.run_check(inst, resp)

                # A host missing pandas/numpy is infrastructure, not a bad task.
                if res["sub_metrics"].get("env_only_failure"):
                    skipped += 1
                    continue

                self.assertEqual(
                    res["violations"], [],
                    "%s (%s): its own gold trips must_not %s -- the task is "
                    "unsolvable" % (inst.id, inst.checker, res["violations"]))
                self.assertAlmostEqual(
                    res["score"], 1.0, places=6,
                    msg="%s (%s): gold scored %.3f, expected 1.0; sub_metrics=%s"
                        % (inst.id, inst.checker, res["score"], res["sub_metrics"]))
                checked += 1

        self.assertGreater(checked, 15,
                           "only %d instances were closed-loop checked" % checked)

    def test_gold_terminal_state_with_pii_is_not_a_violation(self):
        """Regression: G9 telecom task whose gold final_state holds a phone no.

        ``must_not_guard`` must not treat the environment's observed state as
        something the model leaked, otherwise the task has an empty pass region.
        """
        _a, rows = convert_all("tau2_bench")
        target = [r for r in rows if "13800000000" in str(r.gold["value"]["final_state"])]
        self.assertTrue(target, "fixture no longer contains the PII terminal state")
        for inst in target:
            res = pkg.run_check(inst, gold_response(inst))
            self.assertEqual(res["violations"], [])
            self.assertEqual(res["score"], 1.0)

    def test_phone_number_in_prose_is_still_a_violation(self):
        """The narrowed scan must not blunt real leakage detection."""
        _a, rows = convert_all("tau2_bench")
        inst = [r for r in rows if "泄露客户手机号" in r.must_not][0]
        resp = gold_response(inst)
        resp["text"] = "done. the customer number is 13800000000"
        res = pkg.run_check(inst, resp)
        self.assertIn("泄露客户手机号", res["violations"])
        self.assertEqual(res["score"], 0.0)


class TestMissingModuleDetection(unittest.TestCase):
    def test_detects_module_not_found(self):
        out = {"stderr": "ModuleNotFoundError: No module named 'pandas'",
               "stdout": "", "result": {}}
        self.assertEqual(_missing_modules(out), ["pandas"])

    def test_reads_submodule_root(self):
        out = {"stderr": "", "stdout": "",
               "result": {"messages": ["ModuleNotFoundError: No module named 'numpy.linalg'"]}}
        self.assertEqual(_missing_modules(out), ["numpy"])

    def test_plain_assertion_failure_is_not_env_error(self):
        out = {"stderr": "AssertionError: 3 != 4", "stdout": "", "result": {}}
        self.assertEqual(_missing_modules(out), [])

    def test_env_failure_is_labelled_not_scored_as_wrong(self):
        """When a run dies purely on imports it must say so, not look wrong."""
        _a, rows = convert_all("bigcodebench")
        for inst in rows:
            res = pkg.run_check(inst, {"text": inst.gold["value"]["ref_solution"]})
            if res["sub_metrics"].get("env_only_failure"):
                self.assertTrue(res["detail"].get("excluded_from_quality"))
                self.assertTrue(res["detail"].get("missing_modules"))
                self.assertGreater(res["sub_metrics"]["env_errors"], 0)
            else:
                # Anything that is not an import failure must be a real pass.
                self.assertEqual(res["score"], 1.0,
                                 "%s failed for a non-environment reason: %s"
                                 % (inst.id, res["detail"]))


if __name__ == "__main__":
    unittest.main()
