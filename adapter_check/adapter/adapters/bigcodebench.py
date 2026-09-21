"""BigCodeBench -> G7 / executable / exec_tests.

Raw record (HF ``bigcode/bigcodebench``)::

    {"task_id": "BigCodeBench/0", "complete_prompt": "...docstring form...",
     "instruct_prompt": "...NL instruction form...",
     "canonical_solution": "    return ...",
     "test": "import unittest\\nclass TestCases(unittest.TestCase): ...",
     "entry_point": "task_func", "libs": "['pandas','numpy']"}

We take the *instruct* variant (closest to the office-automation framing in
research_G6G7.md §2.2) and keep the unittest body verbatim.
"""
from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional

from ..base import Adapter, AdapterConfig
from ..registry import register_adapter
from ..schema import TaskInstance

STDLIB_SAFE = {
    "os", "sys", "re", "json", "math", "random", "itertools", "functools",
    "collections", "datetime", "csv", "string", "statistics", "pathlib",
    "unittest", "typing", "hashlib", "io", "textwrap", "decimal", "heapq",
}


def parse_libs(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            v = ast.literal_eval(raw)
            if isinstance(v, (list, tuple)):
                return [str(x) for x in v]
        except (ValueError, SyntaxError):
            return [p.strip() for p in raw.split(",") if p.strip()]
    return []


def build_ref_solution(raw_record: Dict[str, Any], entry: str) -> Optional[str]:
    """拼出**可独立运行**的参考解法。

    BigCodeBench 的 ``canonical_solution`` 只是函数体，而且是带缩进的：

        "    permutations = list(itertools.permutations(numbers))\\n    ..."

    import 语句、``def task_func(...)`` 签名和 docstring 全都在
    ``complete_prompt`` 里。官方评测的做法就是 prompt + completion 拼接后执行，
    单独拿 canonical_solution 去 compile 必然是 IndentationError
    ——闭环自检里表现为 ``syntax_ok=0.0``，三条真实样本全军覆没。

    fixture 里手写的 canonical_solution 是自包含的（含 def 行），所以这个坑
    在 191/198 个单测里一直没暴露，直到接上真实数据才现形。因此这里按「解法里
    是否已经有 entry_point 的 def」来判断要不要拼接，两种形态都能吃下。
    """
    sol = raw_record.get("canonical_solution") or ""
    if not sol.strip():
        return None
    if re.search(r"(?m)^\s*def\s+%s\b" % re.escape(entry), sol):
        return sol                                  # 已经是完整程序
    head = (raw_record.get("complete_prompt") or "").rstrip("\n")
    return ("%s\n%s" % (head, sol)) if head else sol


@register_adapter("bigcodebench")
class BigCodeBenchAdapter(Adapter):
    dataset = "bigcodebench"
    version = "v0.1.4"
    category = "G7"
    subtype = "CODE_FUNCTION"
    gold_type = "executable"
    checker = "exec_tests"
    license = "Apache-2.0"
    commercial_use = "yes"
    homepage = "https://github.com/bigcode-project/bigcodebench"
    base_must_not = ("执行破坏性 shell 命令", "泄露密钥")
    lossy_notes = (
        "原始 complete_prompt(docstring 补全式)被丢弃，只保留 instruct_prompt；"
        "官方要求固定版本 Docker 镜像，我方 exec_tests 只用当前解释器 + subprocess，"
        "第三方库版本漂移会造成假失败 —— 因此 cfg.options['stdlib_only']=True 时"
        "会过滤掉依赖第三方库的题目（fixture 即走这条路径）。"
    )

    def infer_difficulty(self, raw_record, inst_kwargs) -> str:
        """G7-Code heuristic: library count + test-case count + solution length."""
        libs = inst_kwargs.get("libs") or parse_libs(raw_record.get("libs"))
        third_party = [l for l in libs if l not in STDLIB_SAFE]
        n_tests = inst_kwargs.get("n_tests", 0)
        sol_lines = len((raw_record.get("canonical_solution") or "").strip().splitlines())
        if len(third_party) >= 3 or n_tests >= 6 or sol_lines >= 25:
            return "L3"
        if len(third_party) >= 1 or n_tests >= 3 or sol_lines >= 10:
            return "L2"
        return "L1"

    def convert(self, raw_record: Dict[str, Any], cfg: AdapterConfig) -> Optional[TaskInstance]:
        test_code = (raw_record.get("test") or "").strip()
        instruction = (raw_record.get("instruct_prompt")
                       or raw_record.get("complete_prompt") or "").strip()
        if not test_code or not instruction:
            return None
        libs = parse_libs(raw_record.get("libs"))
        third_party = [l for l in libs if l not in STDLIB_SAFE]
        if cfg.options.get("stdlib_only") and third_party:
            return None                      # filtered: needs pinned container

        n_tests = len(re.findall(r"(?m)^\s*def\s+test_\w+", test_code))
        entry = raw_record.get("entry_point") or "task_func"

        prompt = (
            "请实现下面的 Python 函数（函数名必须是 `%s`），"
            "只输出完整可运行的 Python 代码：\n\n%s" % (entry, instruction)
        )
        gold = {
            "type": "executable",
            "value": {
                "tests": [{"kind": "unittest", "code": test_code, "name": "official"}],
                "ref_solution": build_ref_solution(raw_record, entry),
                "timeout_s": float(cfg.options.get("timeout_s", 30)),
                "prelude": raw_record.get("prelude", ""),
            },
        }
        return self.build(
            raw_record, cfg,
            subtype="CODE_FUNCTION",
            prompt=prompt,
            gold=gold,
            difficulty=self.infer_difficulty(raw_record, {"libs": libs, "n_tests": n_tests}),
            lang="en" if not cfg.lang else cfg.lang,
            manifest_extra={"entry_point": entry, "libs": libs,
                            "third_party_libs": third_party, "n_test_cases": n_tests},
        )
