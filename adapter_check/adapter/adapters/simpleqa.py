"""SimpleQA / Chinese SimpleQA -> G1 / factlist / fact_recall.

Raw record (openai/simple-evals ``simple_qa_test_set.csv`` -> jsonl)::

    {"metadata": "{'topic': 'Science', 'answer_type': 'Person', 'urls': [...]}",
     "problem": "Who received the IEEE Frank Rosenblatt Award in 2010?",
     "answer": "Michio Sugeno"}

Chinese SimpleQA (``OpenStellarTeam/Chinese-SimpleQA``) uses
``{"question": ..., "answer": ..., "primary_category": ...}`` -- both key sets
are accepted.

**This is the mechanical case**: a single short answer maps 1:1 onto a
one-element atomic-fact list. Nothing is hand-annotated. Multi-hop sets
(FRAMES) are the opposite case -- see ``frames.py``.
"""
from __future__ import annotations

import ast
from typing import Any, Dict, Optional

from ..base import Adapter, AdapterConfig, detect_lang
from ..registry import register_adapter
from ..schema import TaskInstance


def parse_metadata(md: Any) -> Dict[str, Any]:
    if isinstance(md, dict):
        return md
    if isinstance(md, str) and md.strip():
        try:
            v = ast.literal_eval(md)
            if isinstance(v, dict):
                return v
        except (ValueError, SyntaxError):
            return {}
    return {}


@register_adapter("simpleqa")
class SimpleQAAdapter(Adapter):
    dataset = "simpleqa"
    version = "2024-10"
    category = "G1"
    subtype = "SHORT_FACT_QA"
    gold_type = "factlist"
    checker = "fact_recall"
    license = "MIT"
    commercial_use = "yes"
    homepage = "https://github.com/openai/simple-evals"
    base_must_not = ("泄露PII",)
    lossy_notes = (
        "原始 answer 是单个短串，转成 facts 后只有 1 个 required 事实点，"
        "无法体现 FactRecall 的分母意义（等价于 EM）；"
        "原集的 urls 证据链没有进入 context.kb_docs（我方不下载外部网页），"
        "因此这批题只能做闭卷事实性，不能做引用可溯源。"
    )

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G1 heuristic: answer type + question length. Must be re-labelled by
        measured baseline pass-rate (design doc §5)."""
        md = inst_kwargs.get("md") or {}
        atype = str(md.get("answer_type", "")).lower()
        q = inst_kwargs.get("question", "")
        if atype in ("number", "date"):
            return "L2"
        if len(q) > 160:
            return "L3"
        return "L1" if atype in ("person", "place", "other") else "L2"

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        question = (raw_record.get("problem") or raw_record.get("question") or "").strip()
        answer = (raw_record.get("answer") or "").strip()
        if not question or not answer:
            return None
        md = parse_metadata(raw_record.get("metadata"))
        topic = md.get("topic") or raw_record.get("primary_category") or "general"

        aliases = raw_record.get("aliases") or []
        fact_text = "|".join([answer] + [str(a) for a in aliases])

        gold = {
            "type": "factlist",
            "value": {
                "facts": [{"id": "f1", "text": fact_text, "required": True}],
                "ref_answer": answer,
            },
        }
        lang = cfg.lang or detect_lang(question + answer)
        return self.build(
            raw_record, cfg,
            subtype=self.subtype,
            prompt=question,
            gold=gold,
            lang=lang,
            difficulty=self.infer_difficulty(raw_record, {"md": md, "question": question}),
            manifest_extra={"topic": topic, "answer_type": md.get("answer_type"),
                            "n_facts": 1, "evidence_urls": md.get("urls", [])},
        )


@register_adapter("chinese_simpleqa")
class ChineseSimpleQAAdapter(SimpleQAAdapter):
    dataset = "chinese-simpleqa"
    version = "2024-11"
    # distinct SUBTYPE_SLUG so ids stay unique when both G1 files are merged
    subtype = "SHORT_FACT_QA_ZH"
    license = "MIT"
    commercial_use = "yes"
    homepage = "https://huggingface.co/datasets/OpenStellarTeam/Chinese-SimpleQA"
    lossy_notes = SimpleQAAdapter.lossy_notes + " 中文集另有 6 大类 99 子类标签，仅存 manifest。"

    def convert(self, raw_record, cfg):
        inst = super().convert(raw_record, cfg)
        return inst
