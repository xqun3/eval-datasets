"""synthgen -- a dependency-free synthetic evaluation-data generation skeleton.

Public surface:
    >>> from synthgen import TaskInstance, Pipeline, PipelineConfig
"""

from .schema import (  # noqa: F401
    CATEGORIES,
    CATEGORY_GOLD_TYPE,
    DIFFICULTIES,
    GOLD_TYPES,
    LANGS,
    SPLITS,
    Context,
    Gold,
    SchemaError,
    TaskInstance,
    ValidationError,
    make_checker_result,
    validate_checker_result,
)
from .registry import CHECKERS, GENERATORS, VERIFIERS, load_builtins  # noqa: F401
from .pipeline import Pipeline, PipelineConfig, PipelineResult  # noqa: F401

__version__ = "0.1.0"

__all__ = [
    "CATEGORIES",
    "CATEGORY_GOLD_TYPE",
    "DIFFICULTIES",
    "GOLD_TYPES",
    "LANGS",
    "SPLITS",
    "Context",
    "Gold",
    "SchemaError",
    "TaskInstance",
    "ValidationError",
    "make_checker_result",
    "validate_checker_result",
    "CHECKERS",
    "GENERATORS",
    "VERIFIERS",
    "load_builtins",
    "Pipeline",
    "PipelineConfig",
    "PipelineResult",
    "__version__",
]
