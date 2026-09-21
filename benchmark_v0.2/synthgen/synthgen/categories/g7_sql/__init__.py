"""G7 -- executable SQL analytics tasks over a real in-memory sqlite3 database."""

from . import generator, verifier  # noqa: F401  (import for registration side effects)

__all__ = ["generator", "verifier"]
