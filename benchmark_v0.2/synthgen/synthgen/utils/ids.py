"""Task-instance id helpers: ``<CATEGORY>-<SUBTYPE_SLUG>-<4 digits>``."""

from __future__ import annotations

import re
import unicodedata

_ASCII_KEEP = re.compile(r"[^A-Za-z0-9]+")

# Transliteration table for the Chinese subtype names shipped with the builtin
# categories. Unknown CJK characters fall back to a short deterministic hash so
# the id stays inside the frozen ``[A-Z0-9_]`` slug alphabet.
_SUBTYPE_SLUGS = {
    "复杂宽表统计": "WIDE_TABLE_STATS",
    "单表过滤聚合": "SINGLE_TABLE_AGG",
    "多表关联分组": "JOIN_GROUPBY",
    "窗口函数分析": "WINDOW_ANALYTICS",
    "故障处置工单流": "INCIDENT_TICKET_FLOW",
    "发布回归工单流": "RELEASE_REGRESSION_FLOW",
    "权限受限工单流": "RESTRICTED_ROLE_FLOW",
}


def slugify_subtype(subtype: str) -> str:
    """Turn a (possibly Chinese) subtype label into an ``[A-Z0-9_]`` slug."""
    if subtype in _SUBTYPE_SLUGS:
        return _SUBTYPE_SLUGS[subtype]
    normalized = unicodedata.normalize("NFKD", subtype)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _ASCII_KEEP.sub("_", ascii_only).strip("_").upper()
    if not slug:
        from .hashing import short_hash  # local import to avoid a cycle at import time

        slug = "X" + short_hash(subtype, 7).upper()
    return slug


def make_id(category: str, subtype: str, seq: int) -> str:
    """Build a schema-legal task id. ``seq`` is zero padded to 4 digits."""
    if not 0 <= seq <= 9999:
        raise ValueError("seq must fit in 4 digits (0-9999)")
    return "{}-{}-{:04d}".format(category, slugify_subtype(subtype), seq)
