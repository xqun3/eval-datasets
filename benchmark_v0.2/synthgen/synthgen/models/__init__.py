"""LLM client abstraction, deterministic stub client and the ModelPool."""

from .base import LLMClient, LLMResponse, Message, system, user  # noqa: F401
from .stub import StubLLMClient  # noqa: F401
from .pool import (  # noqa: F401
    ROLES,
    CrossModelViolation,
    ModelPool,
    PoolConfigError,
    default_dry_run_pool,
)

__all__ = [
    "LLMClient",
    "LLMResponse",
    "Message",
    "system",
    "user",
    "StubLLMClient",
    "ROLES",
    "CrossModelViolation",
    "ModelPool",
    "PoolConfigError",
    "default_dry_run_pool",
]
