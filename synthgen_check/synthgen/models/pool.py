"""ModelPool -- role based model assignment + the cross-model red line.

红线: 生成与验证必须多模型交叉 + 第三方验证, 生成模型与验证模型不得同源。
This module is where that rule is *enforced at runtime*:

  * :meth:`ModelPool.assert_cross_provider` raises :class:`CrossModelViolation`
    whenever the verifier role resolves to the same ``provider`` as the
    generator role (or as any generation-side role).
  * the assertion also runs eagerly in :meth:`ModelPool.validate` (called from
    the constructor) and again on every ``get("verifier")`` lookup, so no code
    path can quietly bypass it.
  * ``exclude_providers`` removes vendors from the pool entirely -- used to keep
    the system-under-test's own vendor out of the generation side.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from .base import LLMClient
from .stub import StubLLMClient

#: roles the pipeline asks for. The first three are "generation side".
ROLES = ("generator", "rewriter", "distractor", "verifier")
GENERATION_ROLES = ("generator", "rewriter", "distractor")
VERIFICATION_ROLES = ("verifier",)


class PoolConfigError(ValueError):
    """Raised when a pool cannot satisfy the required roles."""


class CrossModelViolation(AssertionError):
    """Raised when generation and verification would share a provider."""


class ModelPool:
    """Holds clients and assigns one per role, enforcing provider disjointness."""

    def __init__(
        self,
        clients: Sequence[LLMClient],
        assignments: Optional[Dict[str, str]] = None,
        exclude_providers: Iterable[str] = (),
        require_roles: Sequence[str] = ROLES,
    ) -> None:
        self.exclude_providers = {p.strip() for p in exclude_providers if str(p).strip()}
        self.require_roles = tuple(require_roles)
        self._all_clients: List[LLMClient] = list(clients)
        self.clients: List[LLMClient] = [
            c for c in self._all_clients if c.provider not in self.exclude_providers
        ]
        dropped = [c for c in self._all_clients if c.provider in self.exclude_providers]
        self.excluded_clients: List[LLMClient] = dropped
        if not self.clients:
            raise PoolConfigError(
                "model pool is empty after applying exclude_providers={}".format(
                    sorted(self.exclude_providers)
                )
            )
        self.assignments: Dict[str, str] = dict(assignments or {})
        self._resolved: Dict[str, LLMClient] = {}
        self._auto_assign()
        self.validate()

    # -- construction helpers ---------------------------------------------
    def _client_by_key(self, key: str) -> Optional[LLMClient]:
        for c in self.clients:
            if key in (c.provider, c.model, "{}:{}".format(c.provider, c.model)):
                return c
        return None

    def _auto_assign(self) -> None:
        """Resolve explicit assignments, then fill the rest round-robin.

        Verifier is picked *last* and is forced onto a provider not used by any
        generation-side role whenever the pool makes that possible.
        """
        for role, key in self.assignments.items():
            if role not in ROLES:
                raise PoolConfigError("unknown role {!r}; allowed {}".format(role, list(ROLES)))
            client = self._client_by_key(key)
            if client is None:
                raise PoolConfigError(
                    "role {!r} requests {!r} which is not in the pool "
                    "(excluded={} available={})".format(
                        role, key, sorted(self.exclude_providers), self.provider_names()
                    )
                )
            self._resolved[role] = client

        providers = self.provider_names()
        gen_order = [r for r in GENERATION_ROLES if r in self.require_roles]

        # A provider is reserved for verification *before* the generation side is
        # filled, otherwise a round-robin over every vendor would leave nothing
        # for the third-party verifier.
        verifier_client = self._resolved.get("verifier")
        if verifier_client is None and "verifier" in self.require_roles:
            pinned = {self._resolved[r].provider for r in gen_order if r in self._resolved}
            free = [c for c in self.clients if c.provider not in pinned]
            if not free:
                raise PoolConfigError(
                    "no provider left for the verifier role: generation side is pinned to {} "
                    "and the pool only has {} (cross-model verification is mandatory)".format(
                        sorted(pinned), providers
                    )
                )
            verifier_client = free[-1]
            self._resolved["verifier"] = verifier_client

        reserved = verifier_client.provider if verifier_client is not None else None
        gen_clients = [c for c in self.clients if c.provider != reserved]
        if reserved is not None and not gen_clients:
            raise PoolConfigError(
                "pool only offers provider {!r} after exclusions ({}), so generation and "
                "verification would share a vendor; cross-model verification needs at least "
                "two distinct providers".format(reserved, sorted(self.exclude_providers))
            )
        gen_clients = gen_clients or list(self.clients)
        for idx, role in enumerate(gen_order):
            if role in self._resolved:
                continue
            self._resolved[role] = gen_clients[idx % len(gen_clients)]

        missing = [r for r in self.require_roles if r not in self._resolved]
        if missing:
            raise PoolConfigError("roles not assigned: {}".format(missing))

    # -- introspection -----------------------------------------------------
    def provider_names(self) -> List[str]:
        return sorted({c.provider for c in self.clients})

    def role_provider(self, role: str) -> str:
        return self.get(role, _check=False).provider

    def describe(self) -> Dict[str, Any]:
        return {
            "providers": self.provider_names(),
            "excluded_providers": sorted(self.exclude_providers),
            "roles": {
                role: self._resolved[role].describe() for role in sorted(self._resolved)
            },
        }

    # -- the red line ------------------------------------------------------
    def assert_cross_provider(self) -> None:
        """Assert verifier provider != any generation-side provider.

        This is the runtime form of the "生成模型与验证模型不同源" rule.
        """
        if "verifier" not in self._resolved:
            return
        verifier = self._resolved["verifier"]
        for role in GENERATION_ROLES:
            client = self._resolved.get(role)
            if client is None:
                continue
            if client.provider == verifier.provider:
                raise CrossModelViolation(
                    "cross-model red line violated: role {!r} provider {!r} "
                    "({}) equals verifier provider {!r} ({}); "
                    "生成模型与验证模型必须不同源".format(
                        role, client.provider, client.model, verifier.provider, verifier.model
                    )
                )

    def assert_verifier_differs(self, generator: LLMClient, verifier: LLMClient) -> None:
        """Pairwise form of the same rule, for ad-hoc client pairs."""
        if generator.provider == verifier.provider:
            raise CrossModelViolation(
                "cross-model red line violated: generator provider {!r} == verifier provider {!r}; "
                "生成模型与验证模型必须不同源".format(generator.provider, verifier.provider)
            )

    def validate(self) -> None:
        for provider in self.exclude_providers:
            for client in self.clients:
                if client.provider == provider:  # pragma: no cover - defensive
                    raise PoolConfigError("excluded provider {!r} still in pool".format(provider))
        self.assert_cross_provider()

    # -- access ------------------------------------------------------------
    def get(self, role: str, _check: bool = True) -> LLMClient:
        if role not in ROLES:
            raise PoolConfigError("unknown role {!r}; allowed {}".format(role, list(ROLES)))
        if role not in self._resolved:
            raise PoolConfigError("role {!r} is not assigned in this pool".format(role))
        if _check and role == "verifier":
            # enforced again on every access: no code path can bypass it
            self.assert_cross_provider()
        return self._resolved[role]

    # -- factories ---------------------------------------------------------
    @classmethod
    def from_config(
        cls,
        config: Optional[Dict[str, Any]] = None,
        dry_run: bool = True,
        seed: int = 0,
        exclude_providers: Iterable[str] = (),
    ) -> "ModelPool":
        """Build a pool from a plain dict (see README for the config format)."""
        config = dict(config or {})
        excl = set(exclude_providers) | set(config.get("exclude_providers", []))
        assignments = dict(config.get("roles", {}))
        specs = list(config.get("clients", []))

        clients: List[LLMClient] = []
        if dry_run or not specs:
            for i, spec in enumerate(specs or _DEFAULT_STUB_SPECS):
                clients.append(
                    StubLLMClient(
                        provider=spec["provider"],
                        model=spec.get("model", "stub-1"),
                        seed=seed + i,
                        quality=float(spec.get("quality", 0.9)),
                    )
                )
        else:
            raise PoolConfigError(
                "non-dry-run requires real LLMClient instances: build them yourself and pass "
                "them to ModelPool(clients=[...]) (see README '接入真实 LLM')"
            )
        return cls(clients, assignments=assignments, exclude_providers=excl)


_DEFAULT_STUB_SPECS = [
    {"provider": "stub_alpha", "model": "alpha-writer", "quality": 0.92},
    {"provider": "stub_beta", "model": "beta-rewriter", "quality": 0.88},
    {"provider": "stub_gamma", "model": "gamma-judge", "quality": 0.95},
]


def default_dry_run_pool(seed: int = 0, exclude_providers: Iterable[str] = ()) -> ModelPool:
    """Three stub vendors: alpha/beta generate, gamma verifies."""
    return ModelPool.from_config(None, dry_run=True, seed=seed, exclude_providers=exclude_providers)
