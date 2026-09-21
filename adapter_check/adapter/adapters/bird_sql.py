"""BIRD-SQL (Mini-Dev) -> G7 / executable / sql_result_equiv.

Raw record (BIRD dev / mini_dev_sqlite JSON, one object per question)::

    {"question_id": 12, "db_id": "california_schools",
     "question": "...", "evidence": "外部知识提示",
     "SQL": "SELECT ...", "difficulty": "simple|moderate|challenging"}

The DDL/seed of each database is NOT in the question file -- real BIRD ships
``<db_id>/<db_id>.sqlite``. We therefore take a *db catalog* through
``cfg.aux["dbs"]`` : ``{db_id: {"dialect": "sqlite", "ddl": "...", "snapshot_ref": ...}}``.
For fixtures the catalog is ``fixtures/bird_sql_dbs.json``; for the real run it
is generated once by dumping ``.schema`` + sampled rows from the sqlite files.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ..base import Adapter, AdapterConfig, blob_ref, detect_lang
from ..registry import register_adapter
from ..schema import TaskInstance

_JOIN_RE = re.compile(r"(?i)\bjoin\b")
_WINDOW_RE = re.compile(r"(?i)\bover\s*\(")
_SETOP_RE = re.compile(r"(?i)\b(union|intersect|except)\b")
_AGG_RE = re.compile(r"(?i)\b(count|sum|avg|min|max)\s*\(")
_CTE_RE = re.compile(r"(?i)\bwith\b[\s\S]*\bas\s*\(")


def nesting_depth(sql: str) -> int:
    """Max depth of parenthesised SELECT (sub-query nesting)."""
    depth, best = 0, 0
    tokens = re.split(r"(\(|\))", sql or "")
    for t in tokens:
        if t == "(":
            depth += 1
            best = max(best, depth)
        elif t == ")":
            depth = max(0, depth - 1)
    sub = len(re.findall(r"(?i)\(\s*select", sql or ""))
    return max(sub, 0) if sub else 0


def sql_complexity(sql: str) -> Dict[str, int]:
    return {
        "joins": len(_JOIN_RE.findall(sql or "")),
        "subqueries": len(re.findall(r"(?i)\(\s*select", sql or "")),
        "window": 1 if _WINDOW_RE.search(sql or "") else 0,
        "setops": len(_SETOP_RE.findall(sql or "")),
        "aggs": len(_AGG_RE.findall(sql or "")),
        "cte": 1 if _CTE_RE.search(sql or "") else 0,
        "group_by": 1 if re.search(r"(?i)\bgroup\s+by\b", sql or "") else 0,
        "having": 1 if re.search(r"(?i)\bhaving\b", sql or "") else 0,
    }


@register_adapter("bird_sql")
class BirdSqlAdapter(Adapter):
    dataset = "bird-sql-minidev"
    version = "v2-2024-06"
    category = "G7"
    subtype = "SQL_QUERY"
    gold_type = "executable"
    checker = "sql_result_equiv"
    license = "CC BY-SA 4.0 (data); MIT (code)"
    commercial_use = "conditional"   # SA copyleft propagates to derivatives
    homepage = "https://bird-bench.github.io/"
    base_must_not = ("执行 DROP", "执行 DELETE", "执行任何写操作")
    manual_annotation = ""
    lossy_notes = (
        "原始 evidence(外部知识) 被并入 prompt，模型可见，与 BIRD 官方 with-knowledge 设定一致；"
        "BIRD 的 difficulty 三档(simple/moderate/challenging)被结构启发式覆盖，原标签保留在 manifest；"
        "VES(效率分)未进入 score，仅作为 wrapper checker 可选项。"
    )

    # ---- pipeline -------------------------------------------------------
    def prepare(self, cfg: AdapterConfig) -> None:
        self.dbs: Dict[str, Any] = dict(cfg.aux.get("dbs") or {})

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G7-SQL heuristic: JOIN count / nesting depth / window functions."""
        c = inst_kwargs.get("complexity") or sql_complexity(raw_record.get("SQL", ""))
        if c["window"] or c["joins"] >= 3 or c["subqueries"] >= 2 or c["setops"] or c["cte"]:
            return "L3"
        if c["joins"] >= 1 or c["subqueries"] >= 1 or c["group_by"] or c["having"]:
            return "L2"
        return "L1"

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        sql = (raw_record.get("SQL") or raw_record.get("query") or "").strip()
        question = (raw_record.get("question") or "").strip()
        db_id = raw_record.get("db_id")
        if not sql or not question or not db_id:
            return None                      # filtered: incomplete row
        if not re.match(r"(?is)^\s*(with|select)\b", sql):
            return None                      # filtered: not SELECT-only

        db = self.dbs.get(db_id)
        if not db:
            raise KeyError("no DDL for db_id=%r in cfg.aux['dbs']" % db_id)

        evidence = (raw_record.get("evidence") or "").strip()
        prompt_parts = ["数据库 `%s` 的结构如下：" % db_id, "```sql", db["ddl"].strip(), "```"]
        if evidence:
            prompt_parts.append("已知信息：%s" % evidence)
        prompt_parts.append("请用一条 SQLite 查询回答：%s" % question)
        prompt_parts.append("只输出 SQL，不要解释。")
        prompt = "\n".join(prompt_parts)

        complexity = sql_complexity(sql)
        gold = {
            "type": "executable",
            "value": {
                "tests": [{
                    "kind": "sql",
                    "gold_sql": sql,
                    "order_sensitive": bool(re.search(r"(?i)\border\s+by\b", sql)),
                    "column_order_sensitive": False,
                }],
                "ref_solution": sql,
                "timeout_s": float(cfg.options.get("timeout_s", 30)),
            },
        }
        context = {
            "files": [],
            "db_schema": {
                "dialect": db.get("dialect", "sqlite"),
                "ddl": db["ddl"],
                "snapshot_ref": db.get("snapshot_ref") or blob_ref(db["ddl"]),
            },
            "kb_docs": [],
        }
        return self.build(
            raw_record, cfg,
            subtype="SQL_QUERY",
            prompt=prompt,
            gold=gold,
            context=context,
            # lang follows the natural-language question, not the DDL-heavy prompt
            lang=cfg.lang or detect_lang(question + " " + evidence),
            difficulty=self.infer_difficulty(raw_record, {"complexity": complexity}),
            manifest_extra={
                "db_id": db_id,
                "orig_difficulty": raw_record.get("difficulty"),
                "complexity": complexity,
                "has_evidence": bool(evidence),
            },
        )
