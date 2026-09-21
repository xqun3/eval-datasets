"""IFEval (google/instruction_following_eval) -> G4 / rubric / format_compliance.

Raw record::

    {"key": 1000, "prompt": "Write a 300+ word summary ... no commas ...",
     "instruction_id_list": ["punctuation:no_comma", "length_constraints:number_words"],
     "kwargs": [{}, {"relation": "at least", "num_words": 300}]}

IFEval is *programmatically verifiable*, so per SCHEMA §3 ("能用 L1 判的绝不上
L3") it must NOT become an LLM-judged rubric. But gold.type has only five
shapes and none of them is "constraint list". Resolution:

  * gold.type = "rubric" (the only shape that carries ``must_cover``),
  * every verifiable constraint is encoded as ``ifeval:<name>:<arg>`` inside
    ``must_cover``,
  * checker = ``format_compliance`` (L1), not ``rubric_judge`` (L3).

Any IFEval instruction id we cannot translate is dropped from ``must_cover``
and listed in the manifest under ``untranslated_constraints`` -- an untranslated
constraint must never look satisfied.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..base import Adapter, AdapterConfig
from ..registry import register_adapter
from ..schema import TaskInstance

DIMS = [
    {"name": "指令遵循", "weight": 0.6,
     "anchors": {"1": "忽略大部分约束", "3": "满足半数约束", "5": "全部可验证约束通过"}},
    {"name": "内容质量", "weight": 0.4,
     "anchors": {"1": "空洞或跑题", "3": "基本切题", "5": "切题且信息充分"}},
]


def translate(instruction_id: str, kw: Dict[str, Any]) -> Optional[str]:
    """IFEval instruction id + kwargs -> our ifeval: DSL string."""
    kw = kw or {}
    iid = instruction_id
    rel = str(kw.get("relation", "at least")).lower()

    if iid == "length_constraints:number_words":
        n = kw.get("num_words")
        if n is None:
            return None
        return "ifeval:word_count_%s:%d" % ("at_least" if "least" in rel else "at_most", int(n))
    if iid == "length_constraints:number_sentences":
        n = kw.get("num_sentences")
        return None if n is None else "ifeval:sentence_count_at_least:%d" % int(n)
    if iid == "punctuation:no_comma":
        return "ifeval:no_commas:"
    if iid == "change_case:english_lowercase":
        return "ifeval:all_lowercase:"
    if iid == "change_case:english_capital":
        return "ifeval:all_uppercase:"
    if iid == "detectable_format:number_bullet_lists":
        n = kw.get("num_bullets")
        return None if n is None else "ifeval:bullet_count:%d" % int(n)
    if iid == "detectable_format:json_format":
        return "ifeval:json_format:"
    if iid == "detectable_format:title":
        return "ifeval:title_in_brackets:"
    if iid == "detectable_format:multiple_sections":
        n = kw.get("num_sections")
        return None if n is None else "ifeval:sections_at_least:%d" % int(n)
    if iid == "detectable_format:number_placeholders":
        n = kw.get("num_placeholders")
        return None if n is None else "ifeval:placeholder_at_least:%d" % int(n)
    if iid == "keywords:existence":
        kws = kw.get("keywords") or []
        return "ifeval:contains:%s" % kws[0] if kws else None
    if iid == "keywords:forbidden_words":
        kws = kw.get("forbidden_words") or []
        return "ifeval:not_contains:%s" % kws[0] if kws else None
    if iid == "startend:end_checker":
        p = kw.get("end_phrase")
        return None if not p else "ifeval:end_with:%s" % p
    if iid == "startend:quotation":
        return "ifeval:wrapped_in_quotes:"
    if iid == "detectable_format:no_markdown":
        return "ifeval:no_markdown:"
    return None


@register_adapter("ifeval")
class IFEvalAdapter(Adapter):
    dataset = "ifeval"
    version = "2023-11"
    category = "G4"
    subtype = "FORMAT_CONSTRAINED_WRITING"
    gold_type = "rubric"
    checker = "format_compliance"
    license = "Apache-2.0"
    commercial_use = "yes"
    homepage = "https://github.com/google-research/google-research/tree/master/instruction_following_eval"
    base_must_not = ("泄露PII",)
    lossy_notes = (
        "IFEval 没有我方要求的 5 维 rubric —— 这里只给 2 维骨架且不被 format_compliance 使用，"
        "真正判分的是 must_cover 里的 ifeval: 约束（L1）；"
        "无法翻译的 instruction_id 被丢弃并记在 manifest.untranslated_constraints，"
        "所以转换后的约束数可能少于原题（prompt 文本仍保留全部要求，存在「题面要求 > 判分覆盖」的缺口）。"
    )

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G4 heuristic: number of simultaneous constraints."""
        n = inst_kwargs.get("n_constraints", 0)
        if n >= 4:
            return "L3"
        if n >= 2:
            return "L2"
        return "L1"

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        prompt = (raw_record.get("prompt") or "").strip()
        ids: List[str] = [str(x) for x in (raw_record.get("instruction_id_list") or [])]
        kwargs_list: List[Dict[str, Any]] = list(raw_record.get("kwargs") or [])
        if not prompt or not ids:
            return None
        while len(kwargs_list) < len(ids):
            kwargs_list.append({})

        must_cover, untranslated = [], []
        for iid, kw in zip(ids, kwargs_list):
            dsl = translate(iid, kw)
            if dsl:
                must_cover.append(dsl)
            else:
                untranslated.append(iid)
        if not must_cover:
            return None                       # filtered: nothing machine-checkable left

        gold = {"type": "rubric",
                "value": {"dims": [dict(d) for d in DIMS], "must_cover": must_cover}}
        return self.build(
            raw_record, cfg,
            subtype="FORMAT_CONSTRAINED_WRITING",
            prompt=prompt,
            gold=gold,
            difficulty=self.infer_difficulty(raw_record, {"n_constraints": len(must_cover)}),
            lang="en" if not cfg.lang else cfg.lang,
            manifest_extra={"instruction_ids": ids,
                            "translated_constraints": len(must_cover),
                            "untranslated_constraints": untranslated,
                            "coverage_ratio": round(len(must_cover) / float(len(ids)), 4)},
        )
