"""Benchmark v0.1 adapter layer.

Public surface:
    from adapter import AdapterConfig, get_adapter, run_check, TaskInstance
"""
from __future__ import annotations

__version__ = "0.1.0"

from .schema import (  # noqa: F401
    TaskInstance,
    ModelResponse,
    SchemaError,
    validate_instance,
    validate_checker_result,
    new_checker_result,
    CATEGORIES,
    GOLD_TYPES,
)
from .base import Adapter, AdapterConfig, ConversionStats, CANARY_UUID  # noqa: F401
from .registry import (  # noqa: F401
    register_adapter,
    register_checker,
    get_adapter,
    get_checker,
    list_adapters,
    list_checkers,
    adapter_items,
    checker_items,
)
from .checkers import run_check  # noqa: F401  (registers all builtin checkers)
from . import adapters as _adapters  # noqa: F401  (registers all builtin adapters)

__all__ = [
    "TaskInstance", "ModelResponse", "SchemaError", "validate_instance",
    "validate_checker_result", "new_checker_result", "Adapter", "AdapterConfig",
    "ConversionStats", "CANARY_UUID", "register_adapter", "register_checker",
    "get_adapter", "get_checker", "list_adapters", "list_checkers",
    "adapter_items", "checker_items", "run_check", "CATEGORIES", "GOLD_TYPES",
]
