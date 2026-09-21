"""doc_recall_at_k / citation_groundedness."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapter.checkers.ir_metrics import (  # noqa: E402
    citation_groundedness,
    doc_recall_at_k,
    ndcg_at_k,
    recall_at_k,
)
from adapter.schema import TaskInstance  # noqa: E402

KB = [{"doc_id": "d%d" % i, "title": "t%d" % i,
       "text": "the quick brown fox jumps over the lazy dog number %d" % i}
      for i in range(1, 7)]


def make_instance(doc_ids, must_cite=None, graded=None, k=5):
    return TaskInstance(
        id="G2-DOC_RETRIEVAL-0001", category="G2", subtype="DOC_RETRIEVAL",
        difficulty="L2", lang="en",
        context={"files": [], "db_schema": None, "kb_docs": KB},
        tools_available=[], prompt="find docs",
        gold={"type": "reference",
              "value": {"doc_ids": doc_ids, "must_cite": must_cite or [], "value": None,
                        "graded": graded or {}, "k": k}},
        checker="doc_recall_at_k", must_not=[], source="public:beir-scifact@v1.0.0",
        split="dev",
    ).raise_for_errors()


class TestMetricMath(unittest.TestCase):
    def test_recall_at_k(self):
        self.assertEqual(recall_at_k(["a", "b", "c"], ["a", "b"], 5), 1.0)
        self.assertEqual(recall_at_k(["a", "x", "y"], ["a", "b"], 5), 0.5)
        self.assertEqual(recall_at_k(["x", "y", "z", "a"], ["a"], 3), 0.0)
        self.assertEqual(recall_at_k([], [], 5), 1.0)

    def test_ndcg_rewards_ranking(self):
        graded = {"a": 3.0, "b": 1.0}
        good = ndcg_at_k(["a", "b", "c"], graded, 10)
        bad = ndcg_at_k(["c", "b", "a"], graded, 10)
        self.assertAlmostEqual(good, 1.0, places=6)
        self.assertLess(bad, good)

    def test_ndcg_empty(self):
        self.assertEqual(ndcg_at_k(["a"], {}, 10), 0.0)


class TestDocRecall(unittest.TestCase):
    def test_perfect_retrieval(self):
        inst = make_instance(["d1", "d2"])
        r = doc_recall_at_k(inst, {"citations": ["d1", "d2", "d3"]})
        self.assertEqual(r["score"], 1.0)
        self.assertTrue(r["passed"])
        self.assertEqual(r["layer"], "L2")

    def test_partial_recall_fails_threshold(self):
        inst = make_instance(["d1", "d2"])
        r = doc_recall_at_k(inst, {"citations": ["d1", "d5"]})
        self.assertEqual(r["sub_metrics"]["recall_at_5"], 0.5)
        self.assertFalse(r["passed"])

    def test_cutoff_k_respected(self):
        inst = make_instance(["d6"], k=2)
        r = doc_recall_at_k(inst, {"meta": {"ranking": ["d1", "d2", "d6"]}})
        self.assertEqual(r["sub_metrics"]["recall_at_2"], 0.0)

    def test_fake_doc_id_zeroes_score(self):
        inst = make_instance(["d1"])
        r = doc_recall_at_k(inst, {"citations": ["d1", "d999"]})
        self.assertEqual(r["score"], 0.0)
        self.assertTrue(r["violations"])
        self.assertGreater(r["sub_metrics"]["fake_doc_rate"], 0)

    def test_ranking_field_preferred_over_citations(self):
        inst = make_instance(["d4"])
        r = doc_recall_at_k(inst, {"citations": [], "meta": {"ranking": ["d4"]}})
        self.assertEqual(r["score"], 1.0)


class TestCitationGroundedness(unittest.TestCase):
    def test_all_good(self):
        inst = make_instance(["d1"], must_cite=["d1"])
        r = citation_groundedness(inst, {"citations": ["d1"],
                                         "meta": {"quotes": {"d1": ["quick brown fox"]}}})
        self.assertEqual(r["score"], 1.0)
        self.assertTrue(r["passed"])

    def test_fabricated_doc_zeroes(self):
        inst = make_instance(["d1"], must_cite=["d1"])
        r = citation_groundedness(inst, {"citations": ["d1", "nope"]})
        self.assertEqual(r["score"], 0.0)
        self.assertTrue(any("不存在" in v for v in r["violations"]))

    def test_unlocatable_quote_penalised(self):
        inst = make_instance(["d1"], must_cite=["d1"])
        r = citation_groundedness(inst, {"citations": ["d1"],
                                         "meta": {"quotes": {"d1": ["purple elephant"]}}})
        self.assertEqual(r["score"], 0.5)
        self.assertFalse(r["passed"])

    def test_missing_must_cite(self):
        inst = make_instance(["d1", "d2"], must_cite=["d1", "d2"])
        r = citation_groundedness(inst, {"citations": ["d1"]})
        self.assertEqual(r["sub_metrics"]["must_cite_coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
