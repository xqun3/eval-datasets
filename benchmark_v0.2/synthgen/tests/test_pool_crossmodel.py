"""红线测试: 生成模型与验证模型不得同源 + exclude_providers。"""

import unittest

from synthgen.models.base import EchoClient, LLMClient, LLMResponse
from synthgen.models.pool import (
    GENERATION_ROLES,
    ROLES,
    CrossModelViolation,
    ModelPool,
    PoolConfigError,
    default_dry_run_pool,
)
from synthgen.models.stub import StubLLMClient
from synthgen.pipeline import Pipeline, PipelineConfig
from synthgen.stages import RunContext


def clients(*providers):
    return [EchoClient(p, "{}-m".format(p)) for p in providers]


class TestCrossModelAssertion(unittest.TestCase):
    def test_pool_auto_assignment_keeps_verifier_separate(self):
        pool = ModelPool(clients("openai", "anthropic", "google"))
        verifier = pool.get("verifier").provider
        for role in GENERATION_ROLES:
            self.assertNotEqual(pool.get(role).provider, verifier)
        pool.assert_cross_provider()  # must not raise

    def test_explicit_same_provider_raises_at_construction(self):
        with self.assertRaises(CrossModelViolation):
            ModelPool(
                clients("openai", "anthropic"),
                assignments={
                    "generator": "openai",
                    "rewriter": "openai",
                    "distractor": "openai",
                    "verifier": "openai",
                },
            )

    def test_single_provider_pool_cannot_satisfy_roles(self):
        with self.assertRaises(PoolConfigError):
            ModelPool(clients("openai"))

    def test_assert_cross_provider_raises_when_mutated(self):
        pool = ModelPool(clients("openai", "anthropic"))
        # simulate a caller sneaking the verifier onto the generator's vendor
        pool._resolved["verifier"] = pool.get("generator")
        with self.assertRaises(CrossModelViolation):
            pool.assert_cross_provider()

    def test_get_verifier_rechecks_every_access(self):
        pool = ModelPool(clients("openai", "anthropic"))
        pool._resolved["verifier"] = pool._resolved["generator"]
        with self.assertRaises(CrossModelViolation):
            pool.get("verifier")

    def test_pairwise_assertion(self):
        pool = ModelPool(clients("openai", "anthropic"))
        a, b = EchoClient("x"), EchoClient("x")
        with self.assertRaises(CrossModelViolation):
            pool.assert_verifier_differs(a, b)
        pool.assert_verifier_differs(a, EchoClient("y"))

    def test_violation_message_mentions_the_rule(self):
        pool = ModelPool(clients("openai", "anthropic"))
        pool._resolved["verifier"] = pool._resolved["generator"]
        with self.assertRaises(CrossModelViolation) as cm:
            pool.assert_cross_provider()
        self.assertIn("不同源", str(cm.exception))


class TestExcludeProviders(unittest.TestCase):
    def test_excluded_provider_is_removed_from_pool(self):
        pool = ModelPool(clients("openai", "anthropic", "google"), exclude_providers=["openai"])
        self.assertNotIn("openai", pool.provider_names())
        self.assertEqual(len(pool.excluded_clients), 1)
        for role in ROLES:
            self.assertNotEqual(pool.get(role).provider, "openai")

    def test_excluding_everything_fails_loudly(self):
        with self.assertRaises(PoolConfigError):
            ModelPool(clients("openai", "anthropic"), exclude_providers=["openai", "anthropic"])

    def test_exclusion_can_make_roles_unsatisfiable(self):
        with self.assertRaises(PoolConfigError):
            ModelPool(clients("openai", "anthropic"), exclude_providers=["anthropic"])

    def test_requesting_an_excluded_provider_is_an_error(self):
        with self.assertRaises(PoolConfigError):
            ModelPool(
                clients("openai", "anthropic", "google"),
                assignments={"generator": "openai"},
                exclude_providers=["openai"],
            )

    def test_dry_run_pool_has_three_stub_vendors(self):
        pool = default_dry_run_pool(seed=1)
        self.assertEqual(pool.provider_names(), ["stub_alpha", "stub_beta", "stub_gamma"])
        self.assertIsInstance(pool.get("generator"), StubLLMClient)
        self.assertNotEqual(pool.get("generator").provider, pool.get("verifier").provider)

    def test_dry_run_pool_honours_exclusion(self):
        pool = default_dry_run_pool(seed=1, exclude_providers=["stub_beta"])
        self.assertEqual(pool.provider_names(), ["stub_alpha", "stub_gamma"])


class TestPipelineEnforcement(unittest.TestCase):
    def test_pipeline_refuses_a_same_provider_pool(self):
        pool = ModelPool(clients("openai", "anthropic"))
        pool._resolved["verifier"] = pool._resolved["generator"]
        with self.assertRaises(CrossModelViolation):
            Pipeline(PipelineConfig(category="G7", n=1, dry_run=True), pool=pool)

    def test_cross_model_stage_records_provider_pair(self):
        result = Pipeline(PipelineConfig(category="G7", n=1, seed=7, dry_run=True)).run()
        roles = result.pool["roles"]
        self.assertNotEqual(roles["generator"]["provider"], roles["verifier"]["provider"])


class TestLLMClientContract(unittest.TestCase):
    def test_stub_is_deterministic(self):
        a = StubLLMClient("p", "m", seed=3)
        b = StubLLMClient("p", "m", seed=3)
        msg = [{"role": "user", "content": "统计一下订单"}]
        self.assertEqual(a.complete(msg, task="paraphrase").text, b.complete(msg, task="paraphrase").text)

    def test_stub_differs_across_seeds(self):
        a = StubLLMClient("p", "m", seed=1).complete([{"role": "user", "content": "x"}], task="judge").text
        b = StubLLMClient("p", "m", seed=2).complete([{"role": "user", "content": "x"}], task="judge").text
        self.assertNotEqual(a, b)

    def test_response_carries_provider_identity(self):
        resp = StubLLMClient("vendor_x", "model_y", seed=0).complete([{"role": "user", "content": "hi"}])
        self.assertIsInstance(resp, LLMResponse)
        self.assertEqual((resp.provider, resp.model), ("vendor_x", "model_y"))

    def test_custom_client_only_needs_three_things(self):
        class MyClient(LLMClient):
            provider = "my_vendor"
            model = "my-model-1"

            def complete(self, messages, **kw):
                return LLMResponse("ok", 1, self.provider, self.model)

        pool = ModelPool([MyClient(), EchoClient("other")])
        self.assertEqual(pool.get("generator").complete([]).text, "ok")


if __name__ == "__main__":
    unittest.main()
