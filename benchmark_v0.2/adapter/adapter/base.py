"""Adapter base class, AdapterConfig and the shared conversion pipeline."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .schema import (
    CATEGORIES,
    DIFFICULTIES,
    GOLD_TYPES,
    SPLITS,
    SchemaError,
    TaskInstance,
    validate_instance,
)

# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
@dataclass
class AdapterConfig:
    """Everything a conversion run needs that is *not* in the raw record."""

    dataset: str = ""              # overrides Adapter.dataset if set
    version: str = ""              # overrides Adapter.version if set
    split: str = "dev"             # dev | test | canary
    lang: Optional[str] = None     # force lang; None => adapter decides
    seq_start: int = 1
    limit: Optional[int] = None
    extra_must_not: List[str] = field(default_factory=list)
    difficulty_override: Optional[str] = None
    aux: Dict[str, Any] = field(default_factory=dict)   # db catalogs, corpora, qrels...
    options: Dict[str, Any] = field(default_factory=dict)  # per-adapter knobs
    canary_marker: Optional[str] = None  # canary string stamped into the prompt
    strict: bool = True            # raise on schema violation vs. skip+record

    def __post_init__(self) -> None:
        if self.split not in SPLITS:
            raise SchemaError("split %r not in %s" % (self.split, list(SPLITS)))
        if self.difficulty_override and self.difficulty_override not in DIFFICULTIES:
            raise SchemaError("difficulty_override %r not in %s"
                              % (self.difficulty_override, list(DIFFICULTIES)))


@dataclass
class ConversionStats:
    read: int = 0
    converted: int = 0
    filtered: int = 0
    errored: int = 0
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "read": self.read,
            "converted": self.converted,
            "filtered": self.filtered,
            "errored": self.errored,
            "errors": self.errors[:20],
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
_SLUG_RE = re.compile(r"[^A-Z0-9]+")

# canary sentinel -- any model that reproduces this string was trained on our
# held-out split. Kept out of `dev`/`test` writes by default.
CANARY_UUID = "BENCHV01-CANARY-4f2a9c17-DO-NOT-TRAIN"


# `id` must match [A-Z0-9_], but `subtype` is free text and is usually Chinese.
# Registered Chinese subtypes get a readable slug here; anything unregistered
# falls back to a stable hash so two different Chinese subtypes can never
# collide into one id namespace (they would both be "MISC" otherwise).
SUBTYPE_SLUG_ALIASES = {
    "复杂宽表统计": "WIDE_TABLE_STATS",
    "多跳事实问答": "MULTIHOP_FACT_QA",
    "会议纪要抽取": "MEETING_MINUTES",
    "周报撰写": "WEEKLY_REPORT",
    "故障根因定位": "ROOT_CAUSE",
    "工具编排": "TOOL_ORCHESTRATION",
}


def slugify(text: str, aliases: Optional[Dict[str, str]] = None) -> str:
    key = (text or "").strip()
    amap = dict(SUBTYPE_SLUG_ALIASES)
    amap.update(aliases or {})
    if key in amap:
        return amap[key]
    s = _SLUG_RE.sub("_", key.upper()).strip("_")
    if s:
        return s
    return ("SUB_" + sha1(key)[:6].upper()) if key else "MISC"


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def blob_ref(payload: str) -> str:
    """Content-addressed pointer used by context.files / db_schema.snapshot_ref."""
    return "blob://sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_lang(text: str) -> str:
    """zh / en / mixed by CJK character ratio (cheap, deterministic)."""
    if not text:
        return "en"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in text if ("a" <= ch.lower() <= "z"))
    if cjk == 0:
        return "en"
    if latin == 0:
        return "zh"
    ratio = cjk / float(cjk + latin)
    if ratio > 0.5:
        return "zh"
    if ratio < 0.05:
        return "en"
    return "mixed"


# --------------------------------------------------------------------------
# base adapter
# --------------------------------------------------------------------------
class Adapter:
    """Subclass contract.

    Required class attributes:
        dataset, version, category, subtype, gold_type, checker
    Required method:
        convert(raw_record, cfg) -> TaskInstance | None   (None == filtered out)

    Optional:
        license, commercial_use, homepage      -- sidecar manifest metadata
        base_must_not                          -- injected into every instance
        manual_annotation                      -- text describing residual human work
        prepare(cfg)                           -- called once before the run
    """

    name: str = ""             # set by @register_adapter
    dataset: str = ""
    version: str = ""
    category: str = "G1"
    subtype: str = "misc"
    gold_type: str = "factlist"
    checker: str = "fact_recall"
    license: str = "unknown"
    commercial_use: str = "unknown"   # yes | no | conditional | unknown
    homepage: str = ""
    base_must_not: Tuple[str, ...] = ()
    manual_annotation: str = ""
    lossy_notes: str = ""
    tools_available: Tuple[str, ...] = ()

    def __init__(self, cfg: Optional[AdapterConfig] = None) -> None:
        self.cfg = cfg or AdapterConfig()
        self._seq = self.cfg.seq_start
        self._seen_ids: set = set()
        self.stats = ConversionStats()
        self.manifest_rows: List[Dict[str, Any]] = []
        if self.category not in CATEGORIES:
            raise SchemaError("adapter %s: bad category %r" % (self.name, self.category))
        if self.gold_type not in GOLD_TYPES:
            raise SchemaError("adapter %s: bad gold_type %r" % (self.name, self.gold_type))

    # -- identity ---------------------------------------------------------
    def dataset_name(self) -> str:
        return self.cfg.dataset or self.dataset

    def dataset_version(self) -> str:
        return self.cfg.version or self.version

    def source(self) -> str:
        """`public:<dataset>@<version>` -- every row traces back to its origin."""
        return "public:%s@%s" % (self.dataset_name(), self.dataset_version())

    def next_id(self, subtype: Optional[str] = None) -> str:
        slug = slugify(subtype or self.subtype)
        iid = "%s-%s-%04d" % (self.category, slug, self._seq)
        self._seq += 1
        if iid in self._seen_ids:
            raise SchemaError("duplicate id generated: %s" % iid)
        self._seen_ids.add(iid)
        return iid

    # -- hooks ------------------------------------------------------------
    def prepare(self, cfg: AdapterConfig) -> None:
        """Optional one-shot setup (load aux corpora etc.)."""

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        raise NotImplementedError

    def infer_difficulty(self, raw_record: Dict[str, Any], inst_kwargs: Dict[str, Any]) -> str:
        """Heuristic difficulty. Override per category. Must be corrected later
        by measured baseline pass-rate (see adapter_design.md §5)."""
        return "L2"

    def raw_id(self, raw_record: Dict[str, Any]) -> str:
        for key in ("id", "_id", "task_id", "question_id", "key", "qid", "instance_id"):
            if key in raw_record and raw_record[key] is not None:
                return str(raw_record[key])
        return sha1(json.dumps(raw_record, sort_keys=True, ensure_ascii=False))[:12]

    # -- shared pipeline steps -------------------------------------------
    def build(
        self,
        raw_record: Dict[str, Any],
        cfg: AdapterConfig,
        *,
        subtype: str,
        prompt: str,
        gold: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        tools_available: Optional[List[str]] = None,
        checker: Optional[str] = None,
        must_not: Optional[List[str]] = None,
        difficulty: Optional[str] = None,
        lang: Optional[str] = None,
        manifest_extra: Optional[Dict[str, Any]] = None,
    ) -> TaskInstance:
        """Assemble + validate one instance and record its manifest row.

        This is the single place that applies: canary stamping, must_not
        injection, difficulty override, lang detection, id generation and
        schema validation. Adapters only do field mapping + gold construction.
        """
        ctx = context or {}
        ctx.setdefault("files", [])
        ctx.setdefault("db_schema", None)
        ctx.setdefault("kb_docs", [])

        if cfg.split == "canary":
            marker = cfg.canary_marker or CANARY_UUID
            prompt = "%s\n\n[%s]" % (prompt, marker)

        mn = list(self.base_must_not) + list(must_not or []) + list(cfg.extra_must_not)
        seen, dedup = set(), []
        for m in mn:
            if m not in seen:
                seen.add(m)
                dedup.append(m)

        diff = cfg.difficulty_override or difficulty or self.infer_difficulty(raw_record, {})
        lng = cfg.lang or lang or detect_lang(prompt)

        inst = TaskInstance(
            id=self.next_id(subtype),
            category=self.category,
            subtype=subtype,
            difficulty=diff,
            lang=lng,
            context=ctx,
            tools_available=list(tools_available if tools_available is not None
                                 else self.tools_available),
            prompt=prompt,
            gold=gold,
            checker=checker or self.checker,
            must_not=dedup,
            source=self.source(),
            split=cfg.split,
        )
        errs = validate_instance(inst.to_dict())
        if errs:
            raise SchemaError("%s (%s): %s" % (inst.id, self.name, "; ".join(errs)))

        row = {
            "instance_id": inst.id,
            "adapter": self.name,
            "raw_id": self.raw_id(raw_record),
            "source": inst.source,
            "split": inst.split,
            "license": self.license,
            "commercial_use": self.commercial_use,
            "homepage": self.homepage,
            "gold_type": inst.gold["type"],
            "checker": inst.checker,
            "difficulty_origin": "heuristic",
            "needs_manual_annotation": bool(self.manual_annotation),
            "manual_annotation": self.manual_annotation,
            "lossy_notes": self.lossy_notes,
        }
        if manifest_extra:
            row.update(manifest_extra)
        self.manifest_rows.append(row)
        return inst

    # -- driver -----------------------------------------------------------
    def run(self, records: Iterable[Dict[str, Any]], cfg: Optional[AdapterConfig] = None
            ) -> Iterator[TaskInstance]:
        cfg = cfg or self.cfg
        self.prepare(cfg)
        for rec in records:
            if cfg.limit is not None and self.stats.converted >= cfg.limit:
                break
            self.stats.read += 1
            try:
                inst = self.convert(rec, cfg)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed silently
                self.stats.errored += 1
                self.stats.errors.append("%s: %s: %s" % (self.raw_id(rec), type(exc).__name__, exc))
                if cfg.strict:
                    raise
                continue
            if inst is None:
                self.stats.filtered += 1
                continue
            self.stats.converted += 1
            yield inst

    # -- sidecar ----------------------------------------------------------
    def manifest(self, cfg: Optional[AdapterConfig] = None) -> Dict[str, Any]:
        cfg = cfg or self.cfg
        return {
            "manifest_version": "0.1",
            "adapter": self.name,
            "dataset": self.dataset_name(),
            "dataset_version": self.dataset_version(),
            "source": self.source(),
            "license": self.license,
            "commercial_use": self.commercial_use,
            "homepage": self.homepage,
            "category": self.category,
            "gold_type": self.gold_type,
            "checker": self.checker,
            "split": cfg.split,
            "canary_marker": (cfg.canary_marker or CANARY_UUID) if cfg.split == "canary" else None,
            "manual_annotation_required": self.manual_annotation or None,
            "lossy_notes": self.lossy_notes or None,
            "stats": self.stats.as_dict(),
            "rows": self.manifest_rows,
        }
