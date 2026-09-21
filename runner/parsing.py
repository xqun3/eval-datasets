#!/usr/bin/env python3
"""模型输出文本 → 判分器要的 ModelResponse 字段。

设计原则：**解析失败要能被看见，不能静默降级。**

一个只会写散文、不会按 JSON 契约输出的模型，在 G2 上会拿 0 分。
这个 0 分到底是「检索能力差」还是「指令遵循差」，是两回事 ——
路由决策里前者该避开检索任务，后者该避开所有结构化任务。
所以每次解析都回一个 ``parse`` 记录，run_benchmark 会把它写进
``meta.parse``，报表可以据此拆分两类失败。
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

_FENCE_RE = re.compile(r"```(?:([a-zA-Z0-9_+-]+))?\s*\n(.*?)```", re.S)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.S)
_ANSWER_RE = re.compile(r"(?:^|\n)\s*(?:Answer|答案)\s*[:：]\s*(.+?)\s*$",
                        re.I | re.S)


def extract_fenced(text: str, langs: Tuple[str, ...]) -> Optional[str]:
    """取第一个匹配语言的代码块；没有带语言标注的就取第一个代码块。"""
    blocks = _FENCE_RE.findall(text or "")
    if not blocks:
        return None
    for lang, body in blocks:
        if lang and lang.lower() in langs:
            return body.strip()
    return blocks[0][1].strip()


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从回答里抠 JSON。先试整体，再试代码块，最后试最外层花括号。"""
    if not text:
        return None
    for candidate in (text.strip(),):
        try:
            v = json.loads(candidate)
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    fenced = extract_fenced(text, ("json",))
    if fenced:
        try:
            v = json.loads(fenced)
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    m = _JSON_OBJ_RE.search(text)
    if m:
        try:
            v = json.loads(m.group(0))
            if isinstance(v, dict):
                return v
        except ValueError:
            pass
    return None


def _as_str_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]
    if isinstance(v, str):
        return [v]
    return []


# --------------------------------------------------------------------------

def parse(checker: str, text: str) -> Dict[str, Any]:
    """返回 {"response": {...}, "parse": {"ok": bool, "how": str, "note": str}}。

    ``response`` 直接可以喂给 run_check。
    """
    text = text or ""

    if checker in ("fact_recall", "format_compliance", "rubric_judge"):
        # 纯文本，没有可失败的解析。空回答仍要标出来。
        return {"response": {"text": text},
                "parse": {"ok": bool(text.strip()), "how": "raw",
                          "note": "" if text.strip() else "空回答"}}

    if checker == "doc_recall_at_k":
        data = extract_json(text)
        if data and "citations" in data:
            cits = _as_str_list(data["citations"])
            return {"response": {"text": text, "citations": cits},
                    "parse": {"ok": True, "how": "json", "note": ""}}
        # 回落：抓 [id] 形式的方括号标号。
        # 这是**有意的宽容**——模型答对了文档却没按 JSON 格式输出，
        # 判它检索能力为 0 是错的。但要记下来是回落解析的。
        ids = re.findall(r"\[([A-Za-z0-9_\-]{1,40})\]", text)
        if ids:
            return {"response": {"text": text, "citations": ids},
                    "parse": {"ok": True, "how": "bracket_fallback",
                              "note": "未按 JSON 契约输出，从方括号标号回落解析"}}
        return {"response": {"text": text, "citations": []},
                "parse": {"ok": False, "how": "failed",
                          "note": "既没有 JSON 也没有可识别的 doc_id"}}

    if checker == "citation_groundedness":
        data = extract_json(text)
        if data:
            resp: Dict[str, Any] = {"text": data.get("text") or text,
                                    "citations": _as_str_list(data.get("citations"))}
            quotes = data.get("quotes")
            if quotes:
                resp["meta"] = {"quotes": quotes}
            return {"response": resp,
                    "parse": {"ok": True, "how": "json", "note": ""}}
        return {"response": {"text": text, "citations": []},
                "parse": {"ok": False, "how": "failed", "note": "未输出 JSON"}}

    if checker == "numeric_em":
        m = _ANSWER_RE.search(text)
        if m:
            val = m.group(1).strip().splitlines()[0].strip()
            # 判分器自己也做归一化，这里只把契约行还原成它认得的形状
            return {"response": {"text": "Answer: %s" % val},
                    "parse": {"ok": True, "how": "answer_line", "note": ""}}
        # 回落：取最后一个数字。宽容，但要标注。
        nums = re.findall(r"-?\d[\d,]*\.?\d*%?", text)
        if nums:
            return {"response": {"text": "Answer: %s" % nums[-1]},
                    "parse": {"ok": True, "how": "last_number_fallback",
                              "note": "未输出 Answer: 行，回落取最后一个数字"}}
        return {"response": {"text": text},
                "parse": {"ok": False, "how": "failed", "note": "找不到任何数值"}}

    if checker == "exec_tests":
        code = extract_fenced(text, ("python", "py"))
        if code:
            return {"response": {"text": code},
                    "parse": {"ok": True, "how": "fenced", "note": ""}}
        # 没有围栏但看起来像代码（有 def / import）也放行
        if re.search(r"^\s*(def|import|from|class)\s", text, re.M):
            return {"response": {"text": text},
                    "parse": {"ok": True, "how": "bare_code_fallback",
                              "note": "未使用代码围栏"}}
        return {"response": {"text": text},
                "parse": {"ok": False, "how": "failed", "note": "没找到代码"}}

    if checker == "sql_result_equiv":
        sql = extract_fenced(text, ("sql",))
        if sql:
            return {"response": {"text": sql},
                    "parse": {"ok": True, "how": "fenced", "note": ""}}
        if re.search(r"\bSELECT\b", text, re.I):
            return {"response": {"text": text},
                    "parse": {"ok": True, "how": "bare_sql_fallback",
                              "note": "未使用代码围栏"}}
        return {"response": {"text": text},
                "parse": {"ok": False, "how": "failed", "note": "没找到 SELECT"}}

    if checker == "state_diff":
        data = extract_json(text)
        if data and ("tool_calls" in data or "final_state" in data):
            calls = data.get("tool_calls") or []
            norm = []
            for c in calls:
                if isinstance(c, dict):
                    norm.append({"name": str(c.get("name") or ""),
                                 "arguments": c.get("arguments")
                                 or c.get("args") or {}})
                elif isinstance(c, str):
                    # 只给了工具名的简写形式
                    norm.append({"name": c, "arguments": {}})
            return {"response": {"text": data.get("text") or "",
                                 "tool_calls": norm,
                                 "final_state": data.get("final_state")},
                    "parse": {"ok": True, "how": "json", "note": ""}}
        return {"response": {"text": text, "tool_calls": [], "final_state": None},
                "parse": {"ok": False, "how": "failed",
                          "note": "未输出含 tool_calls / final_state 的 JSON"}}

    raise KeyError("没有为判分器 %r 定义解析规则" % checker)
