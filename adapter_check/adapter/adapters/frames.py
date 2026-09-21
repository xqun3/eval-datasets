"""FRAMES (google/frames-benchmark) -> G1 / factlist / fact_recall.

Raw record::

    {"Unnamed: 0": 0, "Prompt": "...multi-hop question...",
     "Answer": "1963", "wiki_links": "['https://en.wikipedia.org/wiki/A', ...]",
     "reasoning_types": "numerical reasoning | multiple constraints"}

**The honest part.** FRAMES gives ONE final short answer for a question that
requires 2-N hops. Our schema wants the *atomic fact list* -- the intermediate
facts a good answer must contain. That decomposition is NOT in the data and
cannot be derived mechanically.

What this adapter does:
  * emits the final answer as the single ``required`` fact (machine-derived);
  * emits one ``required: false`` placeholder fact per extra hop, whose text is
    the wiki entity name, so the annotation queue has a concrete anchor;
  * flags the row in the sidecar manifest with ``needs_manual_annotation`` and
    ``hops``, so the labelling cost is *counted*, not hidden.

Estimated human cost (stated in the design doc): ~3-5 min/question to write
2-4 atomic facts, i.e. roughly 40-70 questions per annotator-day.
"""
from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional

from ..base import Adapter, AdapterConfig
from ..registry import register_adapter
from ..schema import TaskInstance


def parse_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            v = ast.literal_eval(raw)
            if isinstance(v, (list, tuple)):
                return [str(x) for x in v]
        except (ValueError, SyntaxError):
            return [p.strip() for p in re.split(r"[|\n,]", raw) if p.strip()]
    return []


def wiki_title(url: str) -> str:
    tail = url.rstrip("/").split("/")[-1]
    return tail.replace("_", " ")


@register_adapter("frames")
class FramesAdapter(Adapter):
    dataset = "frames-benchmark"
    version = "2024-09"
    category = "G1"
    subtype = "MULTIHOP_FACT_QA"
    gold_type = "factlist"
    checker = "fact_recall"
    license = "Apache-2.0"
    commercial_use = "yes"
    homepage = "https://huggingface.co/datasets/google/frames-benchmark"
    base_must_not = ("泄露PII", "编造文档ID")
    manual_annotation = (
        "多跳中间事实点需人工拆点：每题写 2-4 条 atomic fact（约 3-5 分钟/题）。"
        "本 adapter 只能机械给出最终答案这一条 required fact，"
        "其余按 wiki 实体生成 optional 占位事实，必须人工改写后才能计入 FactRecall 分母。"
    )
    lossy_notes = (
        "wiki_links 只到条目级（文章级）而非段落级，达不到 must_cite 的金标要求，"
        "因此只写进 context.kb_docs 的 doc_id 占位，不构造 reference gold；"
        "reasoning_types 原标签仅存 manifest。"
    )

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G2/G1 multi-hop heuristic: hop count (= distinct wiki entities)."""
        hops = inst_kwargs.get("hops", 1)
        rtypes = inst_kwargs.get("reasoning_types", [])
        if hops >= 4 or "temporal" in " ".join(rtypes).lower():
            return "L3"
        if hops >= 2:
            return "L2"
        return "L1"

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        q = (raw_record.get("Prompt") or raw_record.get("prompt") or "").strip()
        a = str(raw_record.get("Answer") or raw_record.get("answer") or "").strip()
        if not q or not a:
            return None
        links = parse_list(raw_record.get("wiki_links"))
        rtypes = parse_list(raw_record.get("reasoning_types"))
        hops = max(1, len(links))

        facts: List[Dict[str, Any]] = [{"id": "f1", "text": a, "required": True}]
        for i, url in enumerate(links[: cfg.options.get("max_placeholder_facts", 4)], start=2):
            facts.append({
                "id": "f%d" % i,
                "text": wiki_title(url),
                "required": False,   # placeholder: NOT counted until a human rewrites it
            })

        kb_docs = [{"doc_id": "wiki:%s" % wiki_title(u), "title": wiki_title(u), "url": u}
                   for u in links]

        gold = {"type": "factlist",
                "value": {"facts": facts, "ref_answer": a}}
        return self.build(
            raw_record, cfg,
            subtype="MULTIHOP_FACT_QA",
            prompt=q,
            gold=gold,
            context={"files": [], "db_schema": None, "kb_docs": kb_docs},
            difficulty=self.infer_difficulty(raw_record, {"hops": hops, "reasoning_types": rtypes}),
            lang="en" if not cfg.lang else cfg.lang,
            manifest_extra={"hops": hops, "reasoning_types": rtypes,
                            "placeholder_facts": len(facts) - 1,
                            "annotation_state": "pending_fact_split"},
        )
