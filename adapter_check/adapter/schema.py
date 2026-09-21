"""TaskInstance schema -- strict implementation of SCHEMA_v0.1.md (frozen).

No field may be added, removed or renamed here. Anything an adapter wants to
record beyond these fields goes into the *sidecar manifest*, never into the
instance.

Python >= 3.8, standard library only (no pydantic / jsonschema available in the
target environment -- see README "验证记录").
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------
# frozen enums (SCHEMA_v0.1.md §0, §1)
# --------------------------------------------------------------------------
CATEGORIES = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "S")
DIFFICULTIES = ("L1", "L2", "L3")
LANGS = ("zh", "en", "mixed")
SPLITS = ("dev", "test", "canary")
GOLD_TYPES = ("executable", "factlist", "rubric", "trace", "reference")
LAYERS = ("L1", "L2", "L3")

CONTEXT_KEYS = ("files", "db_schema", "kb_docs", "env")

ID_RE = re.compile(r"^(G(?:[1-9]|10)|S)-[A-Z0-9_]+-\d{4}$")
TOOL_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")

# source ::= prod_log_* | expert_authored | adversarial
#          | public:<dataset>@<version> | synthetic:<pipeline>@<run_id>
SOURCE_PUBLIC_RE = re.compile(r"^public:[A-Za-z0-9][A-Za-z0-9_.\-/]*@[A-Za-z0-9][A-Za-z0-9_.\-+]*$")
SOURCE_SYNTH_RE = re.compile(r"^synthetic:[A-Za-z0-9][A-Za-z0-9_.\-/]*@[A-Za-z0-9][A-Za-z0-9_.\-+]*$")
SOURCE_PRODLOG_RE = re.compile(r"^prod_log_[A-Za-z0-9_\-]+$")
SOURCE_LITERALS = ("expert_authored", "adversarial")


class SchemaError(ValueError):
    """Raised when an instance violates SCHEMA_v0.1.md."""


# --------------------------------------------------------------------------
# dataclass
# --------------------------------------------------------------------------
@dataclass
class TaskInstance:
    id: str
    category: str
    subtype: str
    difficulty: str
    lang: str
    context: Dict[str, Any]
    tools_available: List[str]
    prompt: str
    gold: Dict[str, Any]
    checker: str
    must_not: List[str]
    source: str
    split: str

    # -- serialisation ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Ordered dict in exactly the schema's field order."""
        d = asdict(self)
        return {k: d[k] for k in FIELD_ORDER}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TaskInstance":
        unknown = set(d) - set(FIELD_ORDER)
        if unknown:
            raise SchemaError("unknown field(s): %s" % sorted(unknown))
        missing = [f for f in FIELD_ORDER if f not in d]
        if missing:
            raise SchemaError("missing field(s): %s" % missing)
        return cls(**{k: d[k] for k in FIELD_ORDER})

    # -- validation -------------------------------------------------------
    def validate(self) -> List[str]:
        return validate_instance(self.to_dict())

    def raise_for_errors(self) -> "TaskInstance":
        errs = self.validate()
        if errs:
            raise SchemaError("%s: %s" % (self.id, "; ".join(errs)))
        return self


FIELD_ORDER = [
    "id", "category", "subtype", "difficulty", "lang", "context",
    "tools_available", "prompt", "gold", "checker", "must_not", "source",
    "split",
]


# --------------------------------------------------------------------------
# validators
# --------------------------------------------------------------------------
def _is_str(x: Any) -> bool:
    return isinstance(x, str)


def _validate_context(ctx: Any, errs: List[str]) -> None:
    if not isinstance(ctx, dict):
        errs.append("context must be an object")
        return
    unknown = set(ctx) - set(CONTEXT_KEYS)
    if unknown:
        errs.append("context has unknown key(s): %s" % sorted(unknown))

    files = ctx.get("files", [])
    if files is not None:
        if not isinstance(files, list):
            errs.append("context.files must be a list")
        else:
            for i, f in enumerate(files):
                if not isinstance(f, dict):
                    errs.append("context.files[%d] must be an object" % i)
                    continue
                if not _is_str(f.get("path", "")):
                    errs.append("context.files[%d].path must be str" % i)
                ref = f.get("content_ref")
                if ref is not None and not (_is_str(ref) and ref.startswith("blob://")):
                    errs.append("context.files[%d].content_ref must be blob://sha256:..." % i)

    db = ctx.get("db_schema")
    if db is not None:
        if not isinstance(db, dict):
            errs.append("context.db_schema must be an object or null")
        else:
            if not _is_str(db.get("dialect", "")):
                errs.append("context.db_schema.dialect must be str")
            if not _is_str(db.get("ddl", "")):
                errs.append("context.db_schema.ddl must be str")
            ref = db.get("snapshot_ref")
            if ref is not None and not (_is_str(ref) and ref.startswith("blob://")):
                errs.append("context.db_schema.snapshot_ref must be blob://sha256:...")

    kb = ctx.get("kb_docs", [])
    if kb is not None:
        if not isinstance(kb, list):
            errs.append("context.kb_docs must be a list")
        else:
            seen = set()
            for i, d in enumerate(kb):
                if not isinstance(d, dict):
                    errs.append("context.kb_docs[%d] must be an object" % i)
                    continue
                did = d.get("doc_id")
                if not _is_str(did) or not did:
                    errs.append("context.kb_docs[%d].doc_id must be a non-empty str" % i)
                elif did in seen:
                    errs.append("context.kb_docs duplicate doc_id %r" % did)
                else:
                    seen.add(did)

    env = ctx.get("env")
    if env is not None and not isinstance(env, dict):
        errs.append("context.env must be an object or null")


def _validate_gold(gold: Any, errs: List[str]) -> None:
    if not isinstance(gold, dict):
        errs.append("gold must be an object")
        return
    unknown = set(gold) - {"type", "value"}
    if unknown:
        errs.append("gold has unknown key(s): %s" % sorted(unknown))
    gtype = gold.get("type")
    if gtype not in GOLD_TYPES:
        errs.append("gold.type must be one of %s, got %r" % (list(GOLD_TYPES), gtype))
        return
    v = gold.get("value")
    if not isinstance(v, dict):
        errs.append("gold.value must be an object for type %s" % gtype)
        return

    if gtype == "executable":
        if not isinstance(v.get("tests"), list) or not v["tests"]:
            errs.append("gold.value.tests must be a non-empty list")
        if "ref_solution" in v and v["ref_solution"] is not None and not _is_str(v["ref_solution"]):
            errs.append("gold.value.ref_solution must be str or null")
        ts = v.get("timeout_s")
        if not isinstance(ts, (int, float)) or isinstance(ts, bool) or ts <= 0:
            errs.append("gold.value.timeout_s must be a positive number")

    elif gtype == "factlist":
        facts = v.get("facts")
        if not isinstance(facts, list) or not facts:
            errs.append("gold.value.facts must be a non-empty list")
        else:
            ids = set()
            for i, f in enumerate(facts):
                if not isinstance(f, dict):
                    errs.append("gold.value.facts[%d] must be an object" % i)
                    continue
                fid = f.get("id")
                if not _is_str(fid) or not fid:
                    errs.append("gold.value.facts[%d].id must be a non-empty str" % i)
                elif fid in ids:
                    errs.append("gold.value.facts duplicate id %r" % fid)
                else:
                    ids.add(fid)
                if not _is_str(f.get("text", "")) or not f.get("text"):
                    errs.append("gold.value.facts[%d].text must be a non-empty str" % i)
                if not isinstance(f.get("required"), bool):
                    errs.append("gold.value.facts[%d].required must be bool" % i)
        if "ref_answer" in v and v["ref_answer"] is not None and not _is_str(v["ref_answer"]):
            errs.append("gold.value.ref_answer must be str or null")

    elif gtype == "rubric":
        dims = v.get("dims")
        if not isinstance(dims, list) or not dims:
            errs.append("gold.value.dims must be a non-empty list")
        else:
            total = 0.0
            for i, d in enumerate(dims):
                if not isinstance(d, dict):
                    errs.append("gold.value.dims[%d] must be an object" % i)
                    continue
                if not _is_str(d.get("name", "")) or not d.get("name"):
                    errs.append("gold.value.dims[%d].name must be a non-empty str" % i)
                w = d.get("weight")
                if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
                    errs.append("gold.value.dims[%d].weight must be a positive number" % i)
                else:
                    total += float(w)
                anchors = d.get("anchors")
                if not isinstance(anchors, dict) or not anchors:
                    errs.append("gold.value.dims[%d].anchors must be a non-empty object" % i)
                else:
                    for k in anchors:
                        if not _is_str(k) or not k.isdigit():
                            errs.append("gold.value.dims[%d].anchors key %r must be a digit string" % (i, k))
            if dims and abs(total - 1.0) > 1e-6:
                errs.append("gold.value.dims weights must sum to 1.0 (got %.4f)" % total)
        mc = v.get("must_cover", [])
        if not isinstance(mc, list) or any(not _is_str(x) for x in mc):
            errs.append("gold.value.must_cover must be a list[str]")

    elif gtype == "trace":
        if not isinstance(v.get("final_state"), dict):
            errs.append("gold.value.final_state must be an object")
        seqs = v.get("valid_sequences")
        if not isinstance(seqs, list):
            errs.append("gold.value.valid_sequences must be a list of sequences")
        else:
            for i, s in enumerate(seqs):
                if not isinstance(s, list):
                    errs.append("gold.value.valid_sequences[%d] must be a list" % i)
        fc = v.get("forbidden_calls", [])
        if not isinstance(fc, list) or any(not _is_str(x) for x in fc):
            errs.append("gold.value.forbidden_calls must be a list[str]")

    elif gtype == "reference":
        ids = v.get("doc_ids")
        if not isinstance(ids, list) or any(not _is_str(x) for x in ids):
            errs.append("gold.value.doc_ids must be a list[str]")
        mc = v.get("must_cite", [])
        if not isinstance(mc, list) or any(not _is_str(x) for x in mc):
            errs.append("gold.value.must_cite must be a list[str]")
        if isinstance(ids, list) and isinstance(mc, list):
            extra = [x for x in mc if x not in ids]
            if extra:
                errs.append("gold.value.must_cite entries missing from doc_ids: %s" % extra)
        if "value" not in v:
            errs.append("gold.value.value key must be present for type reference (may be null)")


def validate_instance(d: Dict[str, Any]) -> List[str]:
    """Return a list of human-readable errors (empty == valid)."""
    errs: List[str] = []
    if not isinstance(d, dict):
        return ["instance must be an object"]

    unknown = set(d) - set(FIELD_ORDER)
    if unknown:
        errs.append("unknown field(s): %s" % sorted(unknown))
    for f in FIELD_ORDER:
        if f not in d:
            errs.append("missing field: %s" % f)
    if errs:
        return errs

    if not _is_str(d["id"]) or not ID_RE.match(d["id"]):
        errs.append("id %r must match <CATEGORY>-<SUBTYPE_SLUG>-<4 digits>" % d["id"])
    if d["category"] not in CATEGORIES:
        errs.append("category %r not in %s" % (d["category"], list(CATEGORIES)))
    elif _is_str(d["id"]) and not d["id"].startswith(d["category"] + "-"):
        errs.append("id prefix must equal category %r" % d["category"])
    if not _is_str(d["subtype"]) or not d["subtype"].strip():
        errs.append("subtype must be a non-empty str")
    if d["difficulty"] not in DIFFICULTIES:
        errs.append("difficulty %r not in %s" % (d["difficulty"], list(DIFFICULTIES)))
    if d["lang"] not in LANGS:
        errs.append("lang %r not in %s" % (d["lang"], list(LANGS)))

    _validate_context(d["context"], errs)

    ta = d["tools_available"]
    if not isinstance(ta, list) or any(not _is_str(x) for x in ta):
        errs.append("tools_available must be a list[str]")
    else:
        bad = [t for t in ta if not TOOL_RE.match(t)]
        if bad:
            errs.append("tools_available entries must be <server>.<tool>: %s" % bad)

    if not _is_str(d["prompt"]) or not d["prompt"].strip():
        errs.append("prompt must be a non-empty str")

    _validate_gold(d["gold"], errs)

    if not _is_str(d["checker"]) or not d["checker"].strip():
        errs.append("checker must be a non-empty str")

    mn = d["must_not"]
    if not isinstance(mn, list) or any(not _is_str(x) for x in mn):
        errs.append("must_not must be a list[str]")

    src = d["source"]
    if not _is_str(src):
        errs.append("source must be str")
    elif not (
        SOURCE_PUBLIC_RE.match(src)
        or SOURCE_SYNTH_RE.match(src)
        or SOURCE_PRODLOG_RE.match(src)
        or src in SOURCE_LITERALS
    ):
        errs.append(
            "source %r must be public:<dataset>@<version> / synthetic:<pipeline>@<run_id> / "
            "prod_log_* / expert_authored / adversarial" % src
        )

    if d["split"] not in SPLITS:
        errs.append("split %r not in %s" % (d["split"], list(SPLITS)))

    return errs


# --------------------------------------------------------------------------
# CheckerResult
# --------------------------------------------------------------------------
def new_checker_result(
    score: float = 0.0,
    passed: bool = False,
    layer: str = "L1",
    sub_metrics: Optional[Dict[str, Any]] = None,
    violations: Optional[List[str]] = None,
    detail: Optional[Dict[str, Any]] = None,
    cost: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a CheckerResult exactly as specified in SCHEMA_v0.1.md §2."""
    if layer not in LAYERS:
        raise SchemaError("layer %r not in %s" % (layer, list(LAYERS)))
    score = float(max(0.0, min(1.0, score)))
    return {
        "score": score,
        "passed": bool(passed),
        "layer": layer,
        "sub_metrics": dict(sub_metrics or {}),
        "violations": list(violations or []),
        "detail": dict(detail or {}),
        "cost": dict(cost or {"tokens": 0, "usd": 0.0, "wall_s": 0.0}),
    }


CHECKER_RESULT_KEYS = ("score", "passed", "layer", "sub_metrics", "violations", "detail", "cost")


def validate_checker_result(r: Any) -> List[str]:
    errs: List[str] = []
    if not isinstance(r, dict):
        return ["CheckerResult must be a dict"]
    missing = [k for k in CHECKER_RESULT_KEYS if k not in r]
    if missing:
        errs.append("CheckerResult missing key(s): %s" % missing)
    extra = set(r) - set(CHECKER_RESULT_KEYS)
    if extra:
        errs.append("CheckerResult unknown key(s): %s" % sorted(extra))
    if errs:
        return errs
    if not isinstance(r["score"], float) or not (0.0 <= r["score"] <= 1.0):
        errs.append("score must be a float in [0,1]")
    if not isinstance(r["passed"], bool):
        errs.append("passed must be bool")
    if r["layer"] not in LAYERS:
        errs.append("layer must be L1/L2/L3")
    for k in ("sub_metrics", "detail", "cost"):
        if not isinstance(r[k], dict):
            errs.append("%s must be a dict" % k)
    if not isinstance(r["violations"], list):
        errs.append("violations must be a list")
    else:
        for c in ("tokens", "usd", "wall_s"):
            if isinstance(r["cost"], dict) and c not in r["cost"]:
                errs.append("cost missing key %s" % c)
    return errs


@dataclass
class ModelResponse:
    """What a checker receives as the model side.

    Deliberately small: `text` for natural-language / SQL / code answers,
    `tool_calls` for G9-style traces, `final_state` for the post-episode
    environment dump, `meta` for anything else (latency, usability failure).
    """
    text: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    final_state: Optional[Dict[str, Any]] = None
    citations: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def coerce(cls, r: Any) -> "ModelResponse":
        if isinstance(r, cls):
            return r
        if isinstance(r, str):
            return cls(text=r)
        if isinstance(r, dict):
            return cls(
                text=r.get("text", "") or "",
                tool_calls=list(r.get("tool_calls", []) or []),
                final_state=r.get("final_state"),
                citations=list(r.get("citations", []) or []),
                meta=dict(r.get("meta", {}) or {}),
            )
        raise SchemaError("cannot coerce %r into ModelResponse" % type(r))
