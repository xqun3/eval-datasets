"""端到端 dry-run: 全链路阶段、可复现性、质量闸门/重试、CLI 子命令。"""

import json
import os
import shutil
import unittest

from synthgen.cli import main
from synthgen.pipeline import Pipeline, PipelineConfig
from synthgen.schema import TaskInstance
from synthgen.utils.jsonl import read_jsonl

CANONICAL_STAGES = [
    "seed",
    "variation",
    "difficulty_tag",
    "reverse_generate",
    "cross_model_generate",
    "independent_verify",
    "deterministic_recheck",
    "dedup",
    "decontaminate",
    "sample_for_human_review",
    "emit",
]


class TestPipelineDryRun(unittest.TestCase):
    def run_pipeline(self, category="G7", n=5, seed=42, **kw):
        cfg = PipelineConfig(category=category, n=n, seed=seed, dry_run=True, **kw)
        return Pipeline(cfg).run()

    def test_all_canonical_stages_are_wired(self):
        pipe = Pipeline(PipelineConfig(category="G7", n=1, dry_run=True))
        for stage in CANONICAL_STAGES:
            self.assertIn(stage, pipe.stage_names(), stage)

    def test_g7_dry_run_emits_valid_instances(self):
        result = self.run_pipeline("G7", n=5)
        self.assertEqual(len(result.items), 5)
        for inst in result.items:
            self.assertEqual(inst.validate(), [])
            self.assertEqual(inst.category, "G7")
            self.assertEqual(inst.gold.type, "executable")
            self.assertTrue(inst.source.startswith("synthetic:g7_sql_reverse_v1@"))
            self.assertIn(result.run_id, inst.source)

    def test_g9_dry_run_emits_valid_instances(self):
        result = self.run_pipeline("G9", n=5)
        self.assertEqual(len(result.items), 5)
        for inst in result.items:
            self.assertEqual(inst.validate(), [])
            self.assertEqual(inst.gold.type, "trace")
            self.assertTrue(inst.source.startswith("synthetic:g9_tools_reverse_v1@"))

    def test_ids_are_unique_and_well_formed(self):
        for category in ("G7", "G9"):
            result = self.run_pipeline(category, n=6)
            ids = [i.id for i in result.items]
            self.assertEqual(len(ids), len(set(ids)))
            for task_id in ids:
                self.assertTrue(task_id.startswith(category + "-"))
                self.assertEqual(len(task_id.rsplit("-", 1)[1]), 4)

    def test_same_seed_is_byte_identical(self):
        a = self.run_pipeline("G7", n=4, seed=7)
        b = self.run_pipeline("G7", n=4, seed=7)
        self.assertEqual(a.run_id, b.run_id)
        self.assertEqual(
            [i.to_dict() for i in a.items], [i.to_dict() for i in b.items]
        )

    def test_different_seed_changes_the_data(self):
        a = self.run_pipeline("G7", n=4, seed=1)
        b = self.run_pipeline("G7", n=4, seed=2)
        self.assertNotEqual(a.run_id, b.run_id)
        self.assertNotEqual([i.prompt for i in a.items], [i.prompt for i in b.items])

    def test_stats_report_the_gates(self):
        result = self.run_pipeline("G7", n=5)
        stats = result.stats
        for key in (
            "requested", "emitted", "rejected", "yield_rate", "by_difficulty",
            "by_split", "reject_reasons", "stage_counters", "candidate_solve_rate",
        ):
            self.assertIn(key, stats)
        self.assertEqual(stats["emitted"], len(result.items))
        self.assertGreater(stats["stage_counters"].get("recheck.passed", 0), 0)
        self.assertGreater(stats["stage_counters"].get("independent_verify.passed", 0), 0)

    def test_pinned_split_and_difficulty(self):
        result = self.run_pipeline("G7", n=4, split="canary", difficulty="L1")
        self.assertEqual({i.split for i in result.items}, {"canary"})
        self.assertEqual({i.difficulty for i in result.items}, {"L1"})

    def test_human_review_sampling(self):
        result = self.run_pipeline("G9", n=5, review_rate=0.4)
        self.assertGreaterEqual(len(result.review_sample), 2)
        sampled_ids = {r["id"] for r in result.review_sample}
        self.assertTrue(sampled_ids.issubset({i.id for i in result.items}))

    def test_cost_is_tracked(self):
        result = self.run_pipeline("G7", n=3)
        self.assertGreater(result.cost["tokens"], 0)

    def test_exclude_providers_is_honoured(self):
        result = self.run_pipeline("G7", n=2, exclude_providers=["stub_beta"])
        self.assertNotIn("stub_beta", result.pool["providers"])
        self.assertIn("stub_beta", result.pool["excluded_providers"])

    def test_retry_round_counter_exists(self):
        result = self.run_pipeline("G9", n=6)
        self.assertIn("attempts.round_1", result.stats["stage_counters"])

    def test_unknown_category_fails_fast(self):
        with self.assertRaises(KeyError):
            Pipeline(PipelineConfig(category="G3", n=1, dry_run=True))


class TestCli(unittest.TestCase):
    """CLI 走真实文件 IO。输出写在仓库内的临时目录, 不依赖系统 /tmp。"""

    tmp_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp")

    def setUp(self):
        self.tmp = os.path.join(self.tmp_root, self.id().rsplit(".", 1)[-1])
        os.makedirs(self.tmp, exist_ok=True)

    def tearDown(self):
        # best effort: 某些沙箱环境不允许删除, 失败也不影响断言
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_generate_validate_verify_stats_roundtrip(self):
        out = self.path("g7.jsonl")
        report = self.path("report.json")
        rc = main([
            "generate", "--category", "G7", "--n", "3", "--dry-run",
            "--seed", "42", "--out", out, "--report", report,
        ])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(out))
        rows = read_jsonl(out)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(TaskInstance.from_dict(row).validate(), [])

        with open(report, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["n_items"], 3)

        self.assertEqual(main(["validate", "--in", out, "--quiet"]), 0)
        self.assertEqual(main(["verify", "--in", out, "--quiet"]), 0)
        self.assertEqual(main(["stats", "--in", out]), 0)

    def test_generate_g9_and_verify_with_solutions(self):
        out = self.path("g9.jsonl")
        self.assertEqual(
            main(["generate", "--category", "G9", "--n", "3", "--dry-run", "--seed", "5", "--out", out]), 0
        )
        rows = read_jsonl(out)
        solutions = self.path("sol.jsonl")
        with open(solutions, "w", encoding="utf-8") as fh:
            for row in rows:
                # 故意提交一个破坏性调用, verify 必须判 0 并给出 violations
                fh.write(json.dumps({
                    "id": row["id"],
                    "solution": [{"tool": "jira.delete", "args": {"issue_id": "ISSUE-1"}}],
                }, ensure_ascii=False) + "\n")
        report = self.path("verify.jsonl")
        rc = main(["verify", "--in", out, "--solutions", solutions, "--out", report, "--quiet"])
        self.assertEqual(rc, 1)  # 非零退出码: 有样本没通过
        for line in read_jsonl(report):
            self.assertEqual(line["result"]["score"], 0.0)
            self.assertTrue(line["result"]["violations"])

    def test_validate_rejects_a_broken_file(self):
        bad = self.path("bad.jsonl")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": "nope"}) + "\n")
        self.assertEqual(main(["validate", "--in", bad, "--quiet"]), 1)

    def test_non_dry_run_without_config_is_refused(self):
        rc = main(["generate", "--category", "G7", "--n", "1", "--out", self.path("x.jsonl")])
        self.assertEqual(rc, 2)

    def test_registry_command(self):
        self.assertEqual(main(["registry"]), 0)


if __name__ == "__main__":
    unittest.main()
