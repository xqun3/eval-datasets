"""Frozen Task Instance schema.

The field set below is FROZEN: no field may be added, removed or renamed.
Implemented with stdlib ``dataclasses`` + hand written validation because the
target environment has no ``pydantic`` (see README, "依赖与环境").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# enumerations (frozen)
# --------------------------------------------------------------------------

CATEGORIES: Tuple[str, ...] = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "S")
DIFFICULTIES: Tuple[str, ...] = ("L1", "L2", "L3")
LANGS: Tuple[str, ...] = ("zh", "en", "mixed")
SPLITS: Tuple[str, ...] = ("dev", "test", "canary")
GOLD_TYPES: Tuple[str, ...] = ("executable", "factlist", "rubric", "trace", "reference")

#: category -> the single legal ``gold.type`` for that category.
#: ``S`` (safety) may use any of the five shapes.
CATEGORY_GOLD_TYPE: Dict[str, str] = {
    "G1": "factlist",
    "G2": "reference",
    "G3": "factlist",
    "G4": "rubric",
    "G5": "rubric",
    "G6": "reference",
    "G7": "executable",
    "G8": "factlist",
    "G9": "trace",
    "G10": "rubric",
}

ID_RE = re.compile(r"^(G[1-9]|G10|S)-([A-Z0-9]+(?:_[A-Z0-9]+)*)-(\d{4})$")

#: verifier layers used by CheckerResult
LAYERS: Tuple[str, ...] = ("L1", "L2", "L3")

TASK_FIELD_ORDER: Tuple[str, ...] = (
    "id",
    "category",
    "subtype",
    "difficulty",
    "lang",
    "context",
    "tools_available",
    "prompt",
    "gold",
    "checker",
    "must_not",
    "source",
    "split",
)

CONTEXT_FIELD_ORDER: Tuple[str, ...] = ("files", "db_schema", "kb_docs", "env")


class SchemaError(ValueError):
    """Raised when a payload cannot be parsed into a :class:`TaskInstance`."""


class ValidationError(ValueError):
    """Raised by :meth:`TaskInstance.validate` when ``strict=True``."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


# --------------------------------------------------------------------------
# dataclasses
# --------------------------------------------------------------------------


@dataclass
class Context:
    """``context`` sub-object. Field names frozen."""

    files: List[Any] = field(default_factory=list)
    db_schema: Optional[Any] = None
    kb_docs: List[Any] = field(default_factory=list)
    env: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files": list(self.files),
            "db_schema": self.db_schema,
            "kb_docs": list(self.kb_docs),
            "env": self.env,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Context":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise SchemaError("context must be an object")
        unknown = set(data) - set(CONTEXT_FIELD_ORDER)
        if unknown:
            raise SchemaError("context has unknown field(s): {}".format(sorted(unknown)))
        return cls(
            files=list(data.get("files") or []),
            db_schema=data.get("db_schema"),
            kb_docs=list(data.get("kb_docs") or []),
            env=data.get("env"),
        )


@dataclass
class Gold:
    """``gold`` sub-object: ``{"type": <one of GOLD_TYPES>, "value": <any>}``."""

    type: str
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "value": self.value}

    @classmethod
    def from_dict(cls, data: Any) -> "Gold":
        if not isinstance(data, dict):
            raise SchemaError("gold must be an object")
        unknown = set(data) - {"type", "value"}
        if unknown:
            raise SchemaError("gold has unknown field(s): {}".format(sorted(unknown)))
        if "type" not in data:
            raise SchemaError("gold.type is required")
        return cls(type=data["type"], value=data.get("value"))


@dataclass
class TaskInstance:
    """One evaluation task instance. The 13 fields below are frozen."""

    id: str
    category: str
    subtype: str
    difficulty: str
    lang: str
    prompt: str
    gold: Gold
    checker: str
    source: str
    split: str
    context: Context = field(default_factory=Context)
    tools_available: List[str] = field(default_factory=list)
    must_not: List[str] = field(default_factory=list)

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Serialize with the canonical field order of the frozen schema."""
        payload = {
            "id": self.id,
            "category": self.category,
            "subtype": self.subtype,
            "difficulty": self.difficulty,
            "lang": self.lang,
            "context": self.context.to_dict(),
            "tools_available": list(self.tools_available),
            "prompt": self.prompt,
            "gold": self.gold.to_dict(),
            "checker": self.checker,
            "must_not": list(self.must_not),
            "source": self.source,
            "split": self.split,
        }
        return {k: payload[k] for k in TASK_FIELD_ORDER}

    @classmethod
    def from_dict(cls, data: Any) -> "TaskInstance":
        if not isinstance(data, dict):
            raise SchemaError("task instance must be a JSON object")
        unknown = set(data) - set(TASK_FIELD_ORDER)
        if unknown:
            raise SchemaError("unknown field(s) not allowed by frozen schema: {}".format(sorted(unknown)))
        missing = [f for f in TASK_FIELD_ORDER if f not in data]
        if missing:
            raise SchemaError("missing field(s): {}".format(missing))
        return cls(
            id=data["id"],
            category=data["category"],
            subtype=data["subtype"],
            difficulty=data["difficulty"],
            lang=data["lang"],
            context=Context.from_dict(data["context"]),
            tools_available=list(data["tools_available"] or []),
            prompt=data["prompt"],
            gold=Gold.from_dict(data["gold"]),
            checker=data["checker"],
            must_not=list(data["must_not"] or []),
            source=data["source"],
            split=data["split"],
        )

    # -- validation -------------------------------------------------------
    def validate(self, strict: bool = False) -> List[str]:
        """Return a list of human readable errors (empty == valid)."""
        errors: List[str] = []

        if not isinstance(self.id, str) or not ID_RE.match(self.id):
            errors.append("id 必须匹配 <CATEGORY>-<SUBTYPE_SLUG>-<4位序号>, got {!r}".format(self.id))
        if self.category not in CATEGORIES:
            errors.append("category 非法: {!r} (允许 {})".format(self.category, list(CATEGORIES)))
        elif isinstance(self.id, str) and ID_RE.match(self.id):
            if self.id.split("-", 1)[0] != self.category:
                errors.append("id 前缀 {!r} 与 category {!r} 不一致".format(self.id.split("-", 1)[0], self.category))
        if not isinstance(self.subtype, str) or not self.subtype.strip():
            errors.append("subtype 不能为空")
        if self.difficulty not in DIFFICULTIES:
            errors.append("difficulty 非法: {!r} (允许 {})".format(self.difficulty, list(DIFFICULTIES)))
        if self.lang not in LANGS:
            errors.append("lang 非法: {!r} (允许 {})".format(self.lang, list(LANGS)))
        if self.split not in SPLITS:
            errors.append("split 非法: {!r} (允许 {})".format(self.split, list(SPLITS)))
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            errors.append("prompt 不能为空")
        if not isinstance(self.checker, str) or not self.checker.strip():
            errors.append("checker 不能为空")
        if not isinstance(self.source, str) or not self.source.startswith("synthetic:"):
            errors.append("source 必须形如 synthetic:<pipeline>@<run_id>, got {!r}".format(self.source))
        elif "@" not in self.source:
            errors.append("source 缺少 @<run_id>: {!r}".format(self.source))

        if not isinstance(self.context, Context):
            errors.append("context 必须是 Context 对象")
        if not isinstance(self.tools_available, list) or any(
            not isinstance(t, str) for t in self.tools_available
        ):
            errors.append("tools_available 必须是字符串列表")
        if not isinstance(self.must_not, list) or any(not isinstance(m, str) for m in self.must_not):
            errors.append("must_not 必须是字符串列表")

        if not isinstance(self.gold, Gold):
            errors.append("gold 必须是 Gold 对象")
        else:
            if self.gold.type not in GOLD_TYPES:
                errors.append("gold.type 非法: {!r} (允许 {})".format(self.gold.type, list(GOLD_TYPES)))
            expected = CATEGORY_GOLD_TYPE.get(self.category)
            if expected and self.gold.type != expected:
                errors.append(
                    "category {} 的 gold.type 必须是 {!r}, got {!r}".format(
                        self.category, expected, self.gold.type
                    )
                )

        if strict and errors:
            raise ValidationError(errors)
        return errors

    def is_valid(self) -> bool:
        return not self.validate()


# --------------------------------------------------------------------------
# CheckerResult
# --------------------------------------------------------------------------

CHECKER_RESULT_FIELDS: Tuple[str, ...] = (
    "score",
    "passed",
    "layer",
    "sub_metrics",
    "violations",
    "detail",
    "cost",
)


def make_checker_result(
    score: float,
    passed: Optional[bool] = None,
    layer: str = "L2",
    sub_metrics: Optional[Dict[str, Any]] = None,
    violations: Optional[List[str]] = None,
    detail: Optional[Dict[str, Any]] = None,
    tokens: int = 0,
    usd: float = 0.0,
    wall_s: float = 0.0,
) -> Dict[str, Any]:
    """Build the unified CheckerResult dict every verifier must return."""
    if layer not in LAYERS:
        raise ValueError("layer must be one of {}".format(list(LAYERS)))
    score = float(max(0.0, min(1.0, score)))
    viol = list(violations or [])
    if passed is None:
        passed = score >= 1.0 and not viol
    if viol:
        passed = False
    return {
        "score": score,
        "passed": bool(passed),
        "layer": layer,
        "sub_metrics": dict(sub_metrics or {}),
        "violations": viol,
        "detail": dict(detail or {}),
        "cost": {"tokens": int(tokens), "usd": float(usd), "wall_s": float(wall_s)},
    }


def validate_checker_result(result: Any) -> List[str]:
    """Validate the shape of a CheckerResult produced by any verifier."""
    errors: List[str] = []
    if not isinstance(result, dict):
        return ["CheckerResult 必须是 dict"]
    missing = [f for f in CHECKER_RESULT_FIELDS if f not in result]
    if missing:
        errors.append("CheckerResult 缺少字段: {}".format(missing))
    extra = set(result) - set(CHECKER_RESULT_FIELDS)
    if extra:
        errors.append("CheckerResult 多出字段: {}".format(sorted(extra)))
    if "score" in result and not isinstance(result["score"], float):
        errors.append("score 必须是 float")
    elif "score" in result and not 0.0 <= result["score"] <= 1.0:
        errors.append("score 必须在 0.0-1.0")
    if "passed" in result and not isinstance(result["passed"], bool):
        errors.append("passed 必须是 bool")
    if "layer" in result and result["layer"] not in LAYERS:
        errors.append("layer 必须是 L1/L2/L3")
    for key in ("sub_metrics", "detail", "cost"):
        if key in result and not isinstance(result[key], dict):
            errors.append("{} 必须是 dict".format(key))
    if "violations" in result and not isinstance(result["violations"], list):
        errors.append("violations 必须是 list")
    cost = result.get("cost")
    if isinstance(cost, dict):
        for key in ("tokens", "usd", "wall_s"):
            if key not in cost:
                errors.append("cost 缺少 {}".format(key))
    return errors
