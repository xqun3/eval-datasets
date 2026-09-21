#!/usr/bin/env python3
"""把 TaskInstance 渲染成模型能答、判分器能判的提示词。

核心问题
--------
判分器要的不只是一段文本。`doc_recall_at_k` 要 `citations` 列表，
`state_diff` 要 `tool_calls` + `final_state`，`numeric_em` 要能抠出一个数。
模型默认不会按这些形状输出，所以每个判分器都得配一份**输出契约**，
再由 parsing.py 反解。

一条红线：**契约里不能泄露答案**。
可以告诉模型「从下面 20 篇里选 5 篇」（任务设定），
不能告诉它「正确答案有 3 篇」（gold 信息）。
`gold.value.k` 属于前者——它是任务的一部分，不是答案。
每处从 gold 取值的地方都在下面标了注释，方便复查。
"""

import json
from typing import Any, Dict, List, Optional, Tuple

# 单条 prompt 的上下文预算（字符）。超了就截断并在提示里明说被截断了，
# 不要假装完整——模型看不到后半段却被当成"它没找到"是评测的系统性误差。
DEFAULT_CONTEXT_BUDGET = 60000

BASE_SYSTEM = (
    "你是一个严谨的助手。按用户要求作答，不要编造事实。"
    "如果要求了输出格式，严格遵守该格式，不要附加额外说明。"
)


# --------------------------------------------------------------------------
# 上下文渲染
# --------------------------------------------------------------------------
def render_kb_docs(docs: List[Dict[str, Any]], budget: int) -> Tuple[str, bool]:
    """候选文档池。**必须打乱吗？不必——但顺序不能泄露答案。**

    dataset 里 kb_docs 的 role 字段标了 positive/hard_negative。
    这里刻意只渲染 doc_id / title / text，把 role 丢掉；
    渲染顺序沿用文件内顺序（build_instances.py 已做过打散）。
    """
    parts = []
    used = 0
    truncated = False
    for d in docs:
        block = "[%s] %s\n%s" % (d.get("doc_id"), d.get("title") or "",
                                 d.get("text") or "")
        if used + len(block) > budget:
            truncated = True
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts), truncated


def render_files(files: List[Dict[str, Any]], root: str,
                 budget: int) -> Tuple[str, List[str]]:
    """把 context.files 挂进 prompt。

    ⚠️ G6 的 payments.csv 有 23MB，塞不进任何上下文窗口。这里只给表头 +
    前若干行，并显式告诉模型「这是抽样，不是全量」。

    这意味着**没有执行沙箱时 G6 本质上做不了**——需要对 23MB 做聚合的题，
    看几十行样本是猜不出来的。metrics/definitions/G6.json 里
    exec_sandbox_available 这个护栏指标就是标记这件事的。
    """
    import os
    blocks = []
    notes = []
    per_file = max(2000, budget // max(1, len(files)))
    for f in files:
        path = os.path.join(root, f.get("path", ""))
        if not os.path.exists(path):
            notes.append("%s 不在本地（未下载）" % f.get("path"))
            continue
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(per_file)
        if size > len(head.encode("utf-8", "replace")):
            head += ("\n…（此文件共 %.1f MB，以上仅为开头 %d 字符的抽样，"
                     "不是全量数据）" % (size / 1e6, per_file))
            notes.append("%s 被截断（%.1f MB）" % (f.get("path"), size / 1e6))
        blocks.append("=== 文件: %s ===\n%s" % (f.get("path"), head))
    return "\n\n".join(blocks), notes


def render_context(inst, root: str, budget: int) -> Tuple[str, Dict[str, Any]]:
    ctx = getattr(inst, "context", None) or {}
    if not isinstance(ctx, dict):
        ctx = {"kb_docs": getattr(ctx, "kb_docs", None) or [],
               "files": getattr(ctx, "files", None) or [],
               "db_schema": getattr(ctx, "db_schema", None)}
    meta: Dict[str, Any] = {}
    chunks = []

    docs = ctx.get("kb_docs") or []
    if docs:
        body, truncated = render_kb_docs(docs, budget)
        chunks.append("<候选文档>\n%s\n</候选文档>" % body)
        meta["kb_docs"] = len(docs)
        if truncated:
            meta["kb_docs_truncated"] = True

    schema = ctx.get("db_schema")
    if schema:
        chunks.append("<数据库结构 dialect=%s>\n%s\n</数据库结构>"
                      % (schema.get("dialect"), schema.get("ddl")))
        meta["db_dialect"] = schema.get("dialect")

    files = ctx.get("files") or []
    if files:
        body, notes = render_files(files, root, budget)
        if body:
            chunks.append("<数据文件>\n%s\n</数据文件>" % body)
        if notes:
            meta["file_notes"] = notes

    return "\n\n".join(chunks), meta


# --------------------------------------------------------------------------
# 每个判分器的输出契约
# --------------------------------------------------------------------------
CONTRACTS: Dict[str, str] = {

    "fact_recall": (
        "直接给出答案，覆盖问题涉及的全部关键事实点。\n"
        "不要输出思考过程，不要复述问题。"
    ),

    "doc_recall_at_k": (
        "从上面的候选文档中选出最能回答问题的 {k} 篇。\n"
        "只输出一个 JSON 对象，不要输出任何其它文字：\n"
        '{{"citations": ["<doc_id>", "..."]}}\n'
        "doc_id 必须逐字取自候选文档的方括号标号。"
        "严禁编造候选池里没有的 doc_id。"
    ),

    "citation_groundedness": (
        "回答问题，并为每条论断标注出处。\n"
        "只输出一个 JSON 对象：\n"
        '{{"text": "<回答正文>", "citations": ["<doc_id>", "..."], '
        '"quotes": [{{"doc_id": "<doc_id>", "quote": "<原文中逐字摘录的片段>"}}]}}\n'
        "quote 必须能在对应文档里逐字找到，不得改写。"
    ),

    "numeric_em": (
        "计算并给出最终答案。\n"
        "最后一行必须是：Answer: <答案>\n"
        "答案只写值本身，不要带单位、千分位逗号或解释文字。"
    ),

    "format_compliance": (
        "严格满足题目中的**每一条**格式约束。\n"
        "只输出正文，不要输出任何前言、后记或对约束的复述。"
    ),

    "exec_tests": (
        "写出完整可运行的 Python 代码。\n"
        "只输出一个 ```python 代码块，包含所有必要的 import 和完整函数定义。\n"
        "不要输出测试代码、示例调用或解释文字。"
    ),

    "sql_result_equiv": (
        "写出一条 SQL 查询。\n"
        "只输出一个 ```sql 代码块，里面只有一条 SELECT 语句。\n"
        "不要输出解释文字。严禁任何写操作（INSERT/UPDATE/DELETE/DROP）。"
    ),

    "state_diff": (
        "你可以调用以下工具：\n{tools}\n\n"
        "规划并「执行」完成任务所需的工具调用，然后报告结果。\n"
        "只输出一个 JSON 对象：\n"
        '{{"tool_calls": [{{"name": "<工具名>", "arguments": {{...}}}}, ...], '
        '"final_state": {{...}}, "text": "<给用户的说明>"}}\n'
        "tool_calls 按实际执行顺序排列；final_state 描述全部调用完成后的系统状态；"
        "text 里要告诉用户你做了什么。只能使用上面列出的工具。"
    ),

    "rubric_judge": (
        "完整作答。结论先行，必要时分点说明。"
    ),
}

# state_diff 是唯一"假执行"的门类：没有真实工具运行时，只能让模型自述
# 它会怎么调、结果会是什么。这测的是**规划能力**，不是**执行能力**——
# 一个会规划但调用参数总是写错的模型，在这里拿满分。
SIMULATED = {"state_diff"}


def build_prompt(inst, root: str = ".",
                 budget: int = DEFAULT_CONTEXT_BUDGET) -> Dict[str, Any]:
    """返回 {"system", "user", "checker", "meta"}。"""
    checker = inst.checker
    contract = CONTRACTS.get(checker)
    if contract is None:
        raise KeyError("没有为判分器 %r 定义输出契约" % checker)

    fmt: Dict[str, Any] = {}
    if checker == "doc_recall_at_k":
        # 从 gold 取 k。k 是任务设定（"给我前 5 篇"），不是答案，
        # 因此不算泄露。gold.value.doc_ids 才是答案，绝不进 prompt。
        fmt["k"] = (inst.gold.get("value") or {}).get("k", 5)
    if checker == "state_diff":
        tools = getattr(inst, "tools_available", None) or []
        fmt["tools"] = "\n".join("  - %s" % t for t in tools) or "  （无）"

    ctx_text, meta = render_context(inst, root, budget)

    sections = []
    if ctx_text:
        sections.append(ctx_text)
    sections.append("<任务>\n%s\n</任务>" % inst.prompt)
    sections.append("<输出要求>\n%s\n</输出要求>" % contract.format(**fmt))

    meta.update({"checker": checker,
                 "simulated_execution": checker in SIMULATED})
    return {"system": BASE_SYSTEM,
            "user": "\n\n".join(sections),
            "checker": checker,
            "meta": meta}
