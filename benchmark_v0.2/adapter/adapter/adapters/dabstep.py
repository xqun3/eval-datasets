"""DABStep (Adyen/HF) -> G6 / reference / numeric_em.

Raw record (``adyen/DABstep`` tasks split)::

    {"task_id": 12, "question": "...", "guidance": "Answer must be a number
      rounded to 2 decimals...", "level": "easy|hard",
     "answer": "1234.56", "file_ids": ["payments.csv"]}

The data files are CSV/markdown docs shipped with the benchmark; we reference
them through ``context.files`` (path + content_ref blob), never inline.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..base import Adapter, AdapterConfig, blob_ref
from ..registry import register_adapter
from ..schema import TaskInstance

_NUMERIC = re.compile(r"^[-+]?[\d,]*\.?\d+%?$")


def coerce_answer(raw: str):
    """Numbers stay numbers (tolerance applies); everything else is a literal."""
    s = str(raw).strip()
    if _NUMERIC.match(s.replace(" ", "")):
        v = s.replace(",", "").rstrip("%")
        try:
            f = float(v)
            return f / 100.0 if s.endswith("%") else f
        except ValueError:
            return s
    return s


@register_adapter("dabstep")
class DabstepAdapter(Adapter):
    dataset = "dabstep"
    version = "2025-03"
    category = "G6"
    subtype = "DATA_ANALYSIS"
    gold_type = "reference"
    checker = "numeric_em"
    license = "Apache-2.0 (code); data per Adyen terms -- see manifest"
    commercial_use = "conditional"
    homepage = "https://huggingface.co/spaces/adyen/DABstep"
    base_must_not = ("泄露PII", "编造文档ID")
    manual_annotation = (
        "DABStep 只给最终值，不给推导步骤；我方 G6「口径错误率」需要中间口径标注"
        "（分母定义/时间窗/过滤条件），需人工补 1-2 条，约 2 分钟/题。"
    )
    lossy_notes = (
        "guidance(答案格式说明) 被并入 prompt，但原集用它做严格格式判分，"
        "我方降级为 numeric_em 的容差匹配，格式细节（小数位、千分位）不再单独扣分；"
        "level(easy/hard) 原标签保留在 manifest，difficulty 由启发式覆盖。"
    )

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G6 heuristic: declared level + number of referenced files + question length."""
        lvl = str(raw_record.get("level", "")).lower()
        nfiles = inst_kwargs.get("n_files", 0)
        if lvl == "hard" or nfiles >= 3:
            return "L3"
        if lvl == "easy" and nfiles <= 1:
            return "L1"
        return "L2"

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        q = (raw_record.get("question") or "").strip()
        ans = raw_record.get("answer")
        if not q or ans is None or str(ans).strip() == "":
            return None
        if str(ans).strip().lower() in ("not applicable", "n/a"):
            return None                       # filtered: unanswerable rows

        guidance = (raw_record.get("guidance") or raw_record.get("guidelines") or "").strip()
        file_ids: List[str] = [str(f) for f in (raw_record.get("file_ids") or [])]
        files = [{"path": "dabstep/%s" % f,
                  "content_ref": blob_ref("dabstep::%s" % f),
                  "mime": "text/csv" if f.endswith(".csv") else "text/markdown"}
                 for f in file_ids]

        prompt = q if not guidance else "%s\n\n答案格式要求：%s" % (q, guidance)
        gold = {
            "type": "reference",
            "value": {
                "doc_ids": ["dabstep/%s" % f for f in file_ids],
                "must_cite": [],
                "value": coerce_answer(ans),
                "rel_tol": float(cfg.options.get("rel_tol", 1e-4)),
                "abs_tol": float(cfg.options.get("abs_tol", 1e-6)),
            },
        }
        return self.build(
            raw_record, cfg,
            subtype="DATA_ANALYSIS",
            prompt=prompt,
            gold=gold,
            context={"files": files, "db_schema": None, "kb_docs": []},
            difficulty=self.infer_difficulty(raw_record, {"n_files": len(file_ids)}),
            lang="en" if not cfg.lang else cfg.lang,
            manifest_extra={"orig_level": raw_record.get("level"),
                            "n_files": len(file_ids),
                            "answer_is_numeric": isinstance(gold["value"]["value"], float)},
        )
