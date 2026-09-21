"""Dual registry: adapters (dataset -> converter) and checkers (id -> judge fn).

Both are plain dicts guarded by decorators, so registering is a one-liner and
nothing is discovered by magic beyond the explicit imports in
``adapter/adapters/__init__.py`` and ``adapter/checkers/__init__.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .schema import GOLD_TYPES, LAYERS

# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------
_ADAPTERS: Dict[str, type] = {}


def register_adapter(name: str) -> Callable[[type], type]:
    """Class decorator: ``@register_adapter("bird_sql")``."""

    def deco(cls: type) -> type:
        key = name.strip()
        if not key:
            raise ValueError("adapter name must be non-empty")
        if key in _ADAPTERS and _ADAPTERS[key] is not cls:
            raise ValueError("adapter %r already registered by %s" % (key, _ADAPTERS[key]))
        cls.name = key  # type: ignore[attr-defined]
        _ADAPTERS[key] = cls
        return cls

    return deco


def get_adapter(name: str) -> type:
    try:
        return _ADAPTERS[name]
    except KeyError:
        raise KeyError("unknown adapter %r; known: %s" % (name, sorted(_ADAPTERS)))


def list_adapters() -> List[str]:
    return sorted(_ADAPTERS)


def adapter_items() -> List[Tuple[str, type]]:
    return sorted(_ADAPTERS.items())


# --------------------------------------------------------------------------
# checkers
# --------------------------------------------------------------------------
@dataclass
class CheckerSpec:
    id: str
    fn: Callable[..., Dict[str, Any]]
    layer: str
    gold_types: Tuple[str, ...]
    description: str = ""
    third_party: Optional[str] = None  # e.g. "BIRD VES", "tau2 reward"
    tags: List[str] = field(default_factory=list)

    def supports(self, gold_type: str) -> bool:
        return "*" in self.gold_types or gold_type in self.gold_types


_CHECKERS: Dict[str, CheckerSpec] = {}


def register_checker(
    checker_id: str,
    layer: str,
    gold_types,
    description: str = "",
    third_party: Optional[str] = None,
    tags: Optional[List[str]] = None,
):
    """Function decorator.

    ``gold_types`` accepts ``"*"`` (any) or an iterable of gold.type values.
    """

    def deco(fn):
        if layer not in LAYERS:
            raise ValueError("layer %r not in %s" % (layer, list(LAYERS)))
        gts: Tuple[str, ...]
        if gold_types == "*":
            gts = ("*",)
        else:
            gts = tuple(gold_types)
            bad = [g for g in gts if g not in GOLD_TYPES]
            if bad:
                raise ValueError("unknown gold_types %s" % bad)
        if checker_id in _CHECKERS and _CHECKERS[checker_id].fn is not fn:
            raise ValueError("checker %r already registered" % checker_id)
        _CHECKERS[checker_id] = CheckerSpec(
            id=checker_id,
            fn=fn,
            layer=layer,
            gold_types=gts,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            third_party=third_party,
            tags=list(tags or []),
        )
        return fn

    return deco


def get_checker(checker_id: str) -> CheckerSpec:
    try:
        return _CHECKERS[checker_id]
    except KeyError:
        raise KeyError("unknown checker %r; known: %s" % (checker_id, sorted(_CHECKERS)))


def has_checker(checker_id: str) -> bool:
    return checker_id in _CHECKERS


def list_checkers() -> List[str]:
    return sorted(_CHECKERS)


def checker_items() -> List[Tuple[str, CheckerSpec]]:
    return sorted(_CHECKERS.items())


def wrap_third_party(
    checker_id: str,
    layer: str,
    gold_types,
    inner: Callable[..., Any],
    to_result: Callable[[Any], Dict[str, Any]],
    description: str = "",
    third_party: Optional[str] = None,
):
    """Adapt a foreign scorer (BIRD VES, tau2 reward, ...) to our signature.

    ``inner(instance, response, env)`` may return anything; ``to_result``
    normalises it into a CheckerResult. Registered like any builtin, so the
    rest of the stack cannot tell the difference.
    """

    def _wrapped(instance, response, env=None):
        raw = inner(instance, response, env)
        return to_result(raw)

    _wrapped.__name__ = "third_party_%s" % checker_id
    _wrapped.__doc__ = description or ("third-party wrapper for %s" % third_party)
    return register_checker(
        checker_id, layer, gold_types, description=description, third_party=third_party
    )(_wrapped)
