"""format_compliance -- programmatic constraint checking (L1).

IFEval-style "verifiable instructions" are *not* rubric questions: they can be
decided by code. Since SCHEMA_v0.1.md freezes gold.type to five shapes, we keep
them inside a rubric gold and encode the machine-checkable part as a DSL inside
``must_cover``:

    "ifeval:word_count_at_least:100"
    "ifeval:json_format"
    "ifeval:no_commas"
    ...

Plain (non-prefixed) ``must_cover`` entries stay semantic and are handed to
rubric_judge instead. Anything with an ``ifeval:`` prefix that this module does
not implement is counted in ``sub_metrics.unsupported`` -- never silently
treated as satisfied.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..registry import register_checker
from ..schema import ModelResponse, new_checker_result

PREFIX = "ifeval:"


def _words(text: str) -> List[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


def _c_word_count_at_least(text: str, arg: str) -> bool:
    return len(_words(text)) >= int(arg)


def _c_word_count_at_most(text: str, arg: str) -> bool:
    return len(_words(text)) <= int(arg)


def _c_sentence_count_at_least(text: str, arg: str) -> bool:
    return len([s for s in re.split(r"[.!?。！？]\s*", text) if s.strip()]) >= int(arg)


def _c_json_format(text: str, arg: str) -> bool:
    body = text.strip()
    m = re.search(r"```(?:json)?\n(.*?)```", body, re.S)
    if m:
        body = m.group(1).strip()
    try:
        json.loads(body)
        return True
    except Exception:
        return False


def _c_no_commas(text: str, arg: str) -> bool:
    return "," not in text and "，" not in text


def _c_all_lowercase(text: str, arg: str) -> bool:
    return text == text.lower()


def _c_all_uppercase(text: str, arg: str) -> bool:
    return text == text.upper()


def _c_bullet_count(text: str, arg: str) -> bool:
    n = len(re.findall(r"(?m)^\s*(?:[-*+]|\d+\.)\s+", text))
    return n == int(arg)


def _c_contains(text: str, arg: str) -> bool:
    return arg.lower() in text.lower()


def _c_not_contains(text: str, arg: str) -> bool:
    return arg.lower() not in text.lower()


def _c_start_with(text: str, arg: str) -> bool:
    return text.strip().lower().startswith(arg.lower())


def _c_end_with(text: str, arg: str) -> bool:
    return text.strip().lower().endswith(arg.lower())


def _c_wrapped_in_quotes(text: str, arg: str) -> bool:
    t = text.strip()
    return len(t) >= 2 and t[0] in '"“' and t[-1] in '"”'


def _c_title_in_brackets(text: str, arg: str) -> bool:
    return bool(re.search(r"<<[^<>]+>>", text))


def _c_sections_at_least(text: str, arg: str) -> bool:
    return len(re.findall(r"(?m)^#{1,6}\s+\S", text)) >= int(arg)


def _c_no_markdown(text: str, arg: str) -> bool:
    return not re.search(r"(?m)^#{1,6}\s|\*\*|```", text)


def _c_placeholder_at_least(text: str, arg: str) -> bool:
    return len(re.findall(r"\[[^\[\]]+\]", text)) >= int(arg)


CONSTRAINTS: Dict[str, Callable[[str, str], bool]] = {
    "word_count_at_least": _c_word_count_at_least,
    "word_count_at_most": _c_word_count_at_most,
    "sentence_count_at_least": _c_sentence_count_at_least,
    "json_format": _c_json_format,
    "no_commas": _c_no_commas,
    "all_lowercase": _c_all_lowercase,
    "all_uppercase": _c_all_uppercase,
    "bullet_count": _c_bullet_count,
    "contains": _c_contains,
    "not_contains": _c_not_contains,
    "start_with": _c_start_with,
    "end_with": _c_end_with,
    "wrapped_in_quotes": _c_wrapped_in_quotes,
    "title_in_brackets": _c_title_in_brackets,
    "sections_at_least": _c_sections_at_least,
    "no_markdown": _c_no_markdown,
    "placeholder_at_least": _c_placeholder_at_least,
}


def parse_constraint(entry: str) -> Optional[Tuple[str, str]]:
    if not entry.startswith(PREFIX):
        return None
    body = entry[len(PREFIX):]
    name, _sep, arg = body.partition(":")
    return name.strip(), arg.strip()


def format_compliance(instance, response, env: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fraction of machine-checkable constraints satisfied."""
    t0 = time.time()
    resp = ModelResponse.coerce(response)
    text = resp.text or ""
    must_cover = list((instance.gold.get("value") or {}).get("must_cover") or [])

    checked, passed_n, failed, unsupported, semantic = 0, 0, [], [], []
    for entry in must_cover:
        parsed = parse_constraint(entry)
        if parsed is None:
            semantic.append(entry)
            continue
        name, arg = parsed
        fn = CONSTRAINTS.get(name)
        if fn is None:
            unsupported.append(entry)
            continue
        checked += 1
        try:
            ok = bool(fn(text, arg))
        except Exception as exc:  # bad arg in the gold, surface it
            ok = False
            failed.append("%s (error: %s)" % (entry, exc))
            continue
        if ok:
            passed_n += 1
        else:
            failed.append(entry)

    score = (passed_n / float(checked)) if checked else 1.0
    return new_checker_result(
        score=score,
        passed=(checked > 0 and passed_n == checked),
        layer="L1",
        sub_metrics={"constraints_checked": checked,
                     "constraints_passed": passed_n,
                     "unsupported": unsupported,
                     "semantic_deferred": len(semantic)},
        violations=[],
        detail={"failed": failed, "semantic_must_cover": semantic},
        cost={"tokens": 0, "usd": 0.0, "wall_s": round(time.time() - t0, 4)},
    )


register_checker(
    "format_compliance",
    layer="L1",
    gold_types=["rubric"],
    description="IFEval-style verifiable constraints encoded as ifeval:<name>:<arg> in must_cover.",
    tags=["G4", "S"],
)(format_compliance)
