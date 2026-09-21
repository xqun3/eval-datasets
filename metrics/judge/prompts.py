#!/usr/bin/env python3
"""Judge 提示词模板。

三类 judge
----------
  rubric   —— 按维度给 1..5 分（G4 / G5 / G10 / S）
  fact     —— 判断某个事实点是否被回答覆盖（G1 / G3 / G8 的 fact_recall 兜底）
  pairwise —— 两个答案二选一（做 position bias 消除时用）

设计约束
--------
1. **要求结构化输出**。让模型写自由文本再去正则抽分，是幻觉的温床。
2. **先给理由再给分**。反过来会让模型先锚定一个分再编理由。
3. **锚点必须贴进 prompt**。实例的 dims[].anchors 里写了 1 分和 5 分长什么样，
   不给锚点，不同题之间的分数不可比。
4. **pairwise 必须把两个答案放进同一条 prompt**。分别 pointwise 打分再相减，
   与顺序天然无关，换位是无效动作 —— 这正是 rubric_judge.pairwise_judge
   当前的 bug（rev 恒等于 -fwd）。
"""

from typing import Any, Dict, List

RUBRIC_SYSTEM = """你是严格的评审员。你的任务是按给定维度给回答打分。

规则：
- 每个维度独立打 1 到 5 的整数分，参照该维度给出的锚点描述。
- 先写简短理由，再给分。不要先给分。
- 只依据回答本身，不要脑补回答里没有的内容。
- 回答为空、答非所问、或明显偷懒的，该维度给 1 分。
- 严禁因为回答长就给高分。
- 最后只输出一个 JSON 对象，不要输出任何其它文字。"""

RUBRIC_USER = """<题目>
{prompt}
</题目>

<待评回答>
{answer}
</待评回答>

<评分维度>
{dims}
</评分维度>
{must_cover_block}
请逐维度评分，输出格式（**scores 必须放在最前面**，reasons 每条不超过 30 字）：
{{"scores": {{"<维度名>": <1-5整数>}}, "reasons": {{"<维度名>": "<一句话理由>"}}}}"""

MUST_COVER_BLOCK = """
<必须覆盖的要点>
以下要点如果回答没有涉及，相关维度应显著扣分（表述不必逐字一致，意思到即可）：
{items}
</必须覆盖的要点>
"""

FACT_SYSTEM = """你判断一个事实点是否被回答覆盖。

规则：
- 只看「意思是否表达到了」，不要求逐字一致。
- 回答里说了相反的意思 -> 未覆盖。
- 回答含糊其辞、模棱两可 -> 未覆盖。
- 拿不准就输出 "unsure"，不要猜。判不了比判错好。
- 只输出一个 JSON 对象。"""

FACT_USER = """<事实点>
{fact}
</事实点>

<回答>
{answer}
</回答>

输出格式：{{"reason": "<一句话>", "verdict": "yes" | "no" | "unsure"}}"""

PAIRWISE_SYSTEM = """你比较两个回答哪个更好。

规则：
- 按给定维度综合判断，不要只看长度或排版。
- 位置不代表优劣，A 在前只是排版顺序。
- 两个都差或都好且难分高下，输出 "tie"。
- 先写理由，再给结论。
- 只输出一个 JSON 对象。"""

PAIRWISE_USER = """<题目>
{prompt}
</题目>

<回答 A>
{answer_a}
</回答 A>

<回答 B>
{answer_b}
</回答 B>

<评判维度>
{dims}
</评判维度>

输出格式：{{"reason": "<两句话以内>", "winner": "A" | "B" | "tie"}}"""


def _fmt_dims(dims: List[Dict[str, Any]]) -> str:
    lines = []
    for d in dims or []:
        anchors = d.get("anchors") or {}
        low = anchors.get("1") or anchors.get(1) or ""
        high = anchors.get("5") or anchors.get(5) or ""
        lines.append("- %s（权重 %s）\n    1 分：%s\n    5 分：%s"
                     % (d.get("name"), d.get("weight"), low, high))
    return "\n".join(lines) if lines else "- 综合质量（权重 1.0）"


def rubric_messages(prompt: str, answer: str, dims: List[Dict[str, Any]],
                    must_cover: List[str]) -> List[Dict[str, str]]:
    block = ""
    if must_cover:
        block = MUST_COVER_BLOCK.format(
            items="\n".join("- %s" % m for m in must_cover))
    return [
        {"role": "system", "content": RUBRIC_SYSTEM},
        {"role": "user", "content": RUBRIC_USER.format(
            prompt=prompt or "", answer=answer or "（空回答）",
            dims=_fmt_dims(dims), must_cover_block=block)},
    ]


def fact_messages(fact: str, answer: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": FACT_SYSTEM},
        {"role": "user", "content": FACT_USER.format(
            fact=fact or "", answer=answer or "（空回答）")},
    ]


def pairwise_messages(prompt: str, answer_a: str, answer_b: str,
                      dims: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """注意：调用方需要用 (a,b) 和 (b,a) 各调一次，才算真正双向换位。"""
    return [
        {"role": "system", "content": PAIRWISE_SYSTEM},
        {"role": "user", "content": PAIRWISE_USER.format(
            prompt=prompt or "", answer_a=answer_a or "（空回答）",
            answer_b=answer_b or "（空回答）", dims=_fmt_dims(dims))},
    ]
