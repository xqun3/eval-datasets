"""JSONL read/write helpers (UTF-8, no ascii escaping so Chinese stays readable)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, Iterator, List


def iter_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("{}:{}: invalid JSON ({})".format(path, lineno, exc)) from exc


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    return list(iter_jsonl(path))


def write_jsonl(path: str, rows: Iterable[Any]) -> int:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    count = 0
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            payload = row.to_dict() if hasattr(row, "to_dict") else row
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=False))
            fh.write("\n")
            count += 1
    return count
