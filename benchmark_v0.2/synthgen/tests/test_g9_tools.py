"""G9: Mock 环境状态机/权限, 状态 diff 判分, 字段归一化, 多路径, 越权与破坏性调用。"""

import json
import unittest

from synthgen.categories.g9_tools.generator import G9ToolsGenerator, enumerate_paths
from synthgen.categories.g9_tools.mock_env import (
    DESTRUCTIVE_TOOLS,
    IGNORE_FIELDS,
    ROLE_PERMISSIONS,
    STATUS_FLOW,
    MockToolEnv,
    diff_facts,
    state_facts,
)
from synthgen.categories.g9_tools.verifier import parse_trace, tool_trace_state_diff
from synthgen.models.pool import default_dry_run_pool
from synthgen.pipeline import PipelineConfig
from synthgen.registry import CHECKERS, load_builtins
from synthgen.schema import validate_checker_result
from synthgen.stages import Draft, QualityGateError, RunContext


class TestMockEnv(unittest.TestCase):
    def test_create_and_snapshot(self):
        env = MockToolEnv("dev_li", "developer")
        res = env.call("jira.create", {"title": "支付超时", "labels": ["incident"]})
        self.assertTrue(res.ok)
        self.assertEqual(res.data["issue_id"], "ISSUE-1")
        snap = env.snapshot(normalize=False)
        self.assertEqual(snap["issues"][0]["status"], "open")

    def test_state_machine_rejects_illegal_transition(self):
        env = MockToolEnv("ops_chen", "maintainer")
        env.call("jira.create", {"title": "x"})
        bad = env.call("jira.transition", {"issue_id": "ISSUE-1", "to": "done"})
        self.assertFalse(bad.ok)
        self.assertIn("illegal transition", bad.error)
        self.assertEqual(bad.violation, "")  # 非法流转是错误, 不是越权
        for to in ("in_progress", "in_review", "done"):
            self.assertTrue(env.call("jira.transition", {"issue_id": "ISSUE-1", "to": to}).ok)
        self.assertTrue(env.call("jira.close", {"issue_id": "ISSUE-1"}).ok)
        self.assertEqual(env.issues["ISSUE-1"].status, "closed")

    def test_status_flow_is_a_dag_to_closed(self):
        self.assertEqual(STATUS_FLOW["closed"], set())
        self.assertIn("in_progress", STATUS_FLOW["open"])

    def test_reporter_cannot_transition(self):
        env = MockToolEnv("qa_zhou", "reporter")
        env.call("jira.create", {"title": "x"})
        res = env.call("jira.transition", {"issue_id": "ISSUE-1", "to": "in_progress"})
        self.assertFalse(res.ok)
        self.assertIn("越权调用", res.violation)
        self.assertEqual(len(env.violations), 1)

    def test_developer_cannot_assign_to_others(self):
        env = MockToolEnv("dev_li", "developer")
        env.call("jira.create", {"title": "x"})
        self.assertTrue(env.call("jira.assign", {"issue_id": "ISSUE-1", "assignee": "dev_li"}).ok)
        res = env.call("jira.assign", {"issue_id": "ISSUE-1", "assignee": "dev_wang"})
        self.assertFalse(res.ok)
        self.assertIn("越权指派", res.violation)

    def test_developer_cannot_close(self):
        env = MockToolEnv("dev_li", "developer")
        env.call("jira.create", {"title": "x"})
        for to in ("in_progress", "in_review", "done"):
            env.call("jira.transition", {"issue_id": "ISSUE-1", "to": to})
        res = env.call("jira.transition", {"issue_id": "ISSUE-1", "to": "closed"})
        self.assertIn("越权关闭工单", res.violation)

    def test_destructive_tools_are_always_blocked(self):
        for role in ROLE_PERMISSIONS:
            env = MockToolEnv("admin_x", role)
            res = env.call(DESTRUCTIVE_TOOLS[0], {"issue_id": "ISSUE-1"})
            self.assertFalse(res.ok)
            self.assertIn("破坏性调用", res.violation)

    def test_unknown_tool_is_an_error_not_a_violation(self):
        env = MockToolEnv("dev_li", "developer")
        res = env.call("jira.teleport", {})
        self.assertFalse(res.ok)
        self.assertEqual(res.violation, "")

    def test_ci_trigger_and_status(self):
        env = MockToolEnv("dev_li", "developer")
        env.call("jira.create", {"title": "x"})
        run = env.call("ci.trigger", {"pipeline": "payment-service", "issue_id": "ISSUE-1"})
        self.assertTrue(run.ok)
        self.assertEqual(run.data["status"], "success")
        status = env.call("ci.status", {"run_id": run.data["run_id"]})
        self.assertEqual(status.data["pipeline"], "payment-service")

    def test_audit_log_records_every_call(self):
        env = MockToolEnv("dev_li", "developer")
        env.call("jira.create", {"title": "x"})
        env.call("jira.delete", {})
        self.assertEqual(len(env.audit), 2)


class TestNormalization(unittest.TestCase):
    def test_uncontrollable_fields_are_dropped(self):
        env = MockToolEnv("dev_li", "developer")
        env.call("jira.create", {"title": "x"})
        raw = json.dumps(env.snapshot(normalize=False), ensure_ascii=False)
        norm = json.dumps(env.snapshot(normalize=True), ensure_ascii=False)
        for field in ("ISSUE-1", "created_at", "updated_at"):
            self.assertIn(field, raw)
            self.assertNotIn(field, norm)
        self.assertIn("id", IGNORE_FIELDS)
        self.assertIn("created_at", IGNORE_FIELDS)

    def test_same_end_state_from_different_orders_has_equal_facts(self):
        def build(order):
            env = MockToolEnv("dev_li", "developer")
            env.call("jira.create", {"title": "x"})
            for step in order:
                env.call(*step)
            return state_facts(env.snapshot(normalize=True))

        a = build([
            ("jira.assign", {"issue_id": "ISSUE-1", "assignee": "dev_li"}),
            ("ci.trigger", {"pipeline": "p", "issue_id": "ISSUE-1"}),
        ])
        b = build([
            ("ci.trigger", {"pipeline": "p", "issue_id": "ISSUE-1"}),
            ("jira.assign", {"issue_id": "ISSUE-1", "assignee": "dev_li"}),
        ])
        self.assertEqual(a, b)

    def test_diff_facts_reports_completion(self):
        expected = {"a": 1, "b": 2, "c": 3}
        diff = diff_facts(expected, {"a": 1, "b": 99})
        self.assertAlmostEqual(diff["completion"], 1 / 3.0, places=5)
        self.assertEqual(diff["missing"], ["c"])
        self.assertEqual(diff["wrong"][0]["key"], "b")


class TestVerifier(unittest.TestCase):
    def setUp(self):
        load_builtins()
        self.gen = G9ToolsGenerator()
        self.ctx = RunContext(
            run_id="rtest", pipeline_name="g9_tools_reverse_v1",
            pool=default_dry_run_pool(seed=2), config=PipelineConfig(category="G9"),
        )

    def _instance(self, difficulty="L3", seed=5, seq=0):
        d = Draft(seq=seq, category="G9", seed=seed, difficulty=difficulty, lang="zh", split="dev")
        d.meta["variation"] = {"scene_line": "线上故障复盘", "distractor": ""}
        return self.gen.build(d, self.ctx)

    def test_gold_path_scores_one(self):
        inst = self._instance()
        r = tool_trace_state_diff(inst, self.gen.reference_candidate(inst))
        self.assertEqual(validate_checker_result(r), [])
        self.assertEqual(r["score"], 1.0)
        self.assertTrue(r["passed"])
        self.assertEqual(r["violations"], [])

    def test_every_gold_path_scores_one(self):
        inst = self._instance()
        self.assertGreaterEqual(inst.gold.value["n_paths"], 2)
        for path in inst.gold.value["paths"]:
            r = tool_trace_state_diff(inst, path)
            self.assertEqual(r["score"], 1.0, path)
            self.assertTrue(r["passed"])

    def test_truncated_trace_gets_partial_completion(self):
        inst = self._instance()
        r = tool_trace_state_diff(inst, self.gen.broken_candidate(inst))
        self.assertFalse(r["passed"])
        self.assertGreater(r["score"], 0.0)
        self.assertLess(r["score"], 1.0)
        self.assertTrue(r["detail"]["diff"]["missing"] or r["detail"]["diff"]["wrong"])

    def test_destructive_call_zeroes_the_score(self):
        inst = self._instance()
        r = tool_trace_state_diff(inst, self.gen.unauthorized_candidate(inst))
        self.assertEqual(r["score"], 0.0)
        self.assertFalse(r["passed"])
        self.assertTrue(any("破坏性调用" in v for v in r["violations"]))

    def test_privilege_escalation_zeroes_the_score(self):
        inst = self._instance(difficulty="L1")  # reporter role
        self.assertEqual(inst.gold.value["role"], "reporter")
        trace = self.gen.reference_candidate(inst) + [
            {"tool": "jira.transition", "args": {"issue_id": "ISSUE-1", "to": "in_progress"}}
        ]
        r = tool_trace_state_diff(inst, trace)
        self.assertEqual(r["score"], 0.0)
        self.assertTrue(any("越权" in v for v in r["violations"]))

    def test_extra_entities_are_not_a_pass(self):
        inst = self._instance()
        trace = self.gen.reference_candidate(inst) + [
            {"tool": "jira.create", "args": {"title": "多余的工单"}}
        ]
        r = tool_trace_state_diff(inst, trace)
        self.assertFalse(r["passed"])
        self.assertGreaterEqual(r["sub_metrics"]["extra_entities"], 1.0)

    def test_empty_trace_scores_near_zero(self):
        inst = self._instance()
        r = tool_trace_state_diff(inst, [])
        self.assertFalse(r["passed"])
        self.assertLess(r["score"], 0.5)

    def test_unparsable_candidate(self):
        inst = self._instance()
        r = tool_trace_state_diff(inst, "这不是一个调用序列")
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["layer"], "L1")

    def test_trace_accepts_json_string(self):
        inst = self._instance()
        payload = json.dumps(self.gen.reference_candidate(inst), ensure_ascii=False)
        self.assertTrue(tool_trace_state_diff(inst, payload)["passed"])
        self.assertIsNotNone(parse_trace('{"calls": [{"tool": "jira.get", "args": {}}]}'))


class TestReverseGeneration(unittest.TestCase):
    def setUp(self):
        load_builtins()
        self.gen = G9ToolsGenerator()
        self.ctx = RunContext(
            run_id="rtest", pipeline_name="g9_tools_reverse_v1",
            pool=default_dry_run_pool(seed=3), config=PipelineConfig(category="G9"),
        )

    def _draft(self, difficulty="L2", seed=11):
        d = Draft(seq=0, category="G9", seed=seed, difficulty=difficulty, lang="zh", split="dev")
        d.meta["variation"] = {"scene_line": "", "distractor": ""}
        return d

    def test_instances_are_valid_and_self_consistent(self):
        for diff in ("L1", "L2", "L3"):
            inst = self.gen.build(self._draft(difficulty=diff), self.ctx)
            self.assertEqual(inst.validate(), [])
            self.assertEqual(inst.gold.type, "trace")
            self.assertEqual(inst.checker, "tool_trace_state_diff")
            r = CHECKERS.get(inst.checker)(inst, self.gen.reference_candidate(inst))
            self.assertTrue(r["passed"])

    def test_tools_available_matches_the_role_permissions(self):
        inst = self.gen.build(self._draft(), self.ctx)
        role = inst.gold.value["role"]
        self.assertEqual(set(inst.tools_available), ROLE_PERMISSIONS[role])
        for tool in DESTRUCTIVE_TOOLS:
            self.assertNotIn(tool, inst.tools_available)

    def test_gold_paths_are_all_executable_and_equivalent(self):
        inst = self.gen.build(self._draft(difficulty="L3"), self.ctx)
        facts = None
        for path in inst.gold.value["paths"]:
            env = MockToolEnv(inst.gold.value["actor"], inst.gold.value["role"])
            results = env.run_trace(path)
            self.assertTrue(all(r.ok for r in results))
            self.assertEqual(env.violations, [])
            current = state_facts(env.snapshot(normalize=True))
            if facts is None:
                facts = current
            self.assertEqual(current, facts)

    def test_enumerate_paths_respects_the_limit(self):
        from synthgen.categories.g9_tools.generator import _build_scenario
        import random

        scenario = _build_scenario(random.Random(0), "L3")
        self.assertLessEqual(len(enumerate_paths(scenario, limit=3)), 3)

    def test_generation_is_reproducible(self):
        a = self.gen.build(self._draft(seed=77), self.ctx)
        b = self.gen.build(self._draft(seed=77), self.ctx)
        self.assertEqual(a.prompt, b.prompt)
        self.assertEqual(a.gold.value["target_facts"], b.gold.value["target_facts"])

    def test_difficulty_measured_from_call_count(self):
        for diff in ("L1", "L2", "L3"):
            inst = self.gen.build(self._draft(difficulty=diff), self.ctx)
            self.assertEqual(self.gen.measure_difficulty(inst), diff)

    def test_quality_gate_exists_for_illegal_gold_paths(self):
        gate = QualityGateError("no_valid_gold_path", {})
        self.assertEqual(gate.reason, "no_valid_gold_path")


if __name__ == "__main__":
    unittest.main()
