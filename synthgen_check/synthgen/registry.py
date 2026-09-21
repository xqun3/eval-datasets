"""Decorator based registries for generators / verifiers / checkers."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, List, Tuple

T = Callable[..., Any]


class Registry:
    """A tiny name -> object registry with a decorator interface."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: Dict[str, Any] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, **meta: Any) -> Callable[[T], T]:
        """Decorator. Classes are instantiated once (zero-arg ctor) and the
        *instance* is what ``get()`` returns; functions are stored as-is."""

        def deco(obj: T) -> T:
            value = obj() if isinstance(obj, type) else obj
            if name in self._items and type(self._items[name]) is not type(value):
                raise KeyError("{} {!r} already registered".format(self.kind, name))
            self._items[name] = value
            self._meta[name] = dict(meta)
            return obj

        return deco

    def add(self, name: str, obj: Any, **meta: Any) -> None:
        self.register(name, **meta)(obj)

    def get(self, name: str) -> Any:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(
                "unknown {} {!r}; available: {}".format(self.kind, name, self.names())
            ) from None

    def meta(self, name: str) -> Dict[str, Any]:
        self.get(name)
        return dict(self._meta.get(name, {}))

    def names(self) -> List[str]:
        return sorted(self._items)

    def items(self) -> Iterator[Tuple[str, Any]]:
        for name in self.names():
            yield name, self._items[name]

    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)


#: category generators, keyed by category code (e.g. ``"G7"``)
GENERATORS = Registry("generator")
#: model-assisted verifiers, keyed by name
VERIFIERS = Registry("verifier")
#: deterministic checkers, keyed by the ``checker`` field of a TaskInstance
CHECKERS = Registry("checker")

_LOADED = False


def load_builtins() -> None:
    """Import the builtin category packages so their decorators run."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from .categories import g7_sql, g9_tools  # noqa: F401  (import for side effects)
    from .stages import verify as _verify_stage  # noqa: F401  (registers llm_consistency_judge)


def registry_snapshot() -> Dict[str, List[str]]:
    load_builtins()
    return {
        "generators": GENERATORS.names(),
        "verifiers": VERIFIERS.names(),
        "checkers": CHECKERS.names(),
    }
