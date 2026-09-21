#!/usr/bin/env python3
"""把真实 LLM judge 接进判分器 —— 生成可直接塞进 run_check 的 env。

判分器早就留好了两个钩子，只是一直没人接：

    env["judge"]      = fn(prompt, answer, dims, must_cover) -> {维度名: 1..5}
                        用在 rubric_judge.py:62
    env["fact_judge"] = fn(fact_text, answer) -> Optional[bool]
                        用在 fact_recall.py，返回 None 表示弃权、回落规则匹配

本模块提供这两个函数的真实实现。用法：

    from metrics.judge.runner import make_env
    env = make_env()                      # 按环境变量装配
    result = run_check(inst, resp, env=env)

弃权语义很重要
--------------
fact_judge 返回 None 而不是 False。judge 说不准的时候，让规则匹配去兜底，
比让 judge 拍一个 False 要安全 —— 后者会凭空扣掉模型的分。
"""

import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from judge import client as _client   # noqa: E402
from judge import prompts as _prompts  # noqa: E402

_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出里抠出 JSON。抠不出来返回 None，由调用方决定怎么办。

    不做「猜一个默认值」的兜底：judge 输出格式坏了是需要被看见的事故，
    不是可以静悄悄填 3 分带过的小问题。
    """
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


class JudgeRunner(object):
    def __init__(self, cl: Optional[_client.BaseClient] = None,
                 strict: bool = False):
        """strict=True 时，judge 输出解析失败直接抛错而不是弃权。

        批量评测建议 strict=False（个别坏样本不该让整轮挂掉），
        但必须看 stats()["parse_failures"]，失败率高说明模型不适合当 judge。
        """
        self.client = cl or _client.from_env()
        self.strict = strict
        self.parse_failures = 0
        self.abstained = 0

    # ---------------- rubric ----------------
    def rubric(self, prompt: str, answer: str, dims: List[Dict[str, Any]],
               must_cover: List[str]) -> Dict[str, float]:
        msgs = _prompts.rubric_messages(prompt, answer, dims, must_cover)
        raw = self.client.chat(msgs)
        data = parse_json(raw)
        if not data or "scores" not in data:
            self.parse_failures += 1
            # 一律抛错。以前这里返回 {}，上层 rubric_judge 会把每个维度
            # 取成默认 1.0，于是「judge 没说话」变成了「模型得 0 分」——
            # 判分系统的故障被记成了被测模型的失败。抛出去，让 rubric_judge
            # 记成缺测（score=None）。strict=False 仍然不会让整轮挂掉，
            # 因为 rubric_judge 会接住这个异常。
            raise _client.JudgeError(
                "judge 输出无法解析为含 scores 的 JSON（长度 %d）: %r"
                % (len(raw or ""), (raw or "")[:200]))
        out: Dict[str, float] = {}
        for d in dims or []:
            name = d.get("name")
            v = (data.get("scores") or {}).get(name)
            if v is None:
                continue
            try:
                out[name] = float(max(1.0, min(5.0, float(v))))
            except (TypeError, ValueError):
                continue
        return out

    # ---------------- fact ----------------
    def fact(self, fact_text: str, answer: str) -> Optional[bool]:
        msgs = _prompts.fact_messages(fact_text, answer)
        raw = self.client.chat(msgs)
        data = parse_json(raw)
        if not data or "verdict" not in data:
            self.parse_failures += 1
            if self.strict:
                raise _client.JudgeError("fact judge 输出无法解析: %r" % raw[:200])
            self.abstained += 1
            return None            # 弃权 -> fact_recall 回落到规则匹配
        v = str(data["verdict"]).strip().lower()
        if v in ("yes", "true", "1"):
            return True
        if v in ("no", "false", "0"):
            return False
        self.abstained += 1
        return None

    # ---------------- pairwise ----------------
    def pairwise(self, prompt: str, answer_a: str, answer_b: str,
                 dims: List[Dict[str, Any]]) -> Dict[str, Any]:
        """真正的双向换位：把两个答案放进同一条 prompt，跑 A/B 与 B/A 各一次。

        这是 SCHEMA §3 要求的 position bias 消除。对照组是
        rubric_judge.pairwise_judge 的旧实现 —— 它分别 pointwise 打分再相减，
        rev 恒等于 -fwd，换位在算术上不可能产生任何差异。

        两次结论不一致 -> consistent=False。这本身就是有价值的信号：
        说明这道题上 judge 受位置影响，该条比较应当作废而不是取平均。
        """
        fwd = self._one_pairwise(prompt, answer_a, answer_b, dims)
        rev = self._one_pairwise(prompt, answer_b, answer_a, dims)
        # rev 里的 A 是原来的 B，翻译回来
        rev_norm = {"A": "B", "B": "A", "tie": "tie"}.get(rev["winner"], "tie")

        if fwd["winner"] == rev_norm:
            winner, consistent = fwd["winner"], True
        else:
            winner, consistent = "tie", False
        return {"winner": winner, "consistent": consistent,
                "forward": fwd, "reverse": rev,
                "note": ("两次换位结论不一致，该条比较受位置影响，应作废"
                         if not consistent else "")}

    def _one_pairwise(self, prompt, a, b, dims) -> Dict[str, Any]:
        msgs = _prompts.pairwise_messages(prompt, a, b, dims)
        raw = self.client.chat(msgs)
        data = parse_json(raw) or {}
        w = str(data.get("winner", "tie")).strip().upper()
        if w not in ("A", "B"):
            w = "tie"
        return {"winner": w, "reason": data.get("reason", "")}

    # ---------------- 统计 ----------------
    def stats(self) -> Dict[str, Any]:
        s = {"client": self.client.name,
             "parse_failures": self.parse_failures,
             "abstained": self.abstained,
             "is_stub": isinstance(self.client, _client.StubClient)}
        s.update(self.client.cost())
        return s


def make_env(cl: Optional[_client.BaseClient] = None,
             strict: bool = False) -> Dict[str, Any]:
    """产出可直接传给 run_check 的 env。

    ⚠️ 如果 client 是 StubClient，这里**不**注入 env["judge"] ——
    让 rubric_judge 自己回落到 heuristic_judge，从而保留
    sub_metrics.stub=True 的诚实标记。注入一个假 judge 会让 stub 标记消失，
    报表就看不出这批分数是假的了。这是本模块最重要的一个判断。
    """
    runner = JudgeRunner(cl, strict=strict)
    env: Dict[str, Any] = {"_judge_runner": runner}
    if isinstance(runner.client, _client.StubClient):
        _client.sys_warn("client 是离线桩，不注入 env['judge']，"
                         "让判分器保留 stub=True 标记")
        return env
    env["judge"] = runner.rubric
    env["fact_judge"] = runner.fact
    env["pairwise_judge"] = runner.pairwise
    return env


if __name__ == "__main__":
    # 冒烟：不需要网络，走 StubClient
    r = JudgeRunner(_client.StubClient())
    dims = [{"name": "完整性", "weight": 0.6,
             "anchors": {"1": "要点基本没提", "5": "要点齐全"}},
            {"name": "结构", "weight": 0.4,
             "anchors": {"1": "一团文字", "5": "结论先行，分点说明"}}]
    print("rubric   ->", r.rubric("题干", "回答", dims, ["要点甲"]))
    print("fact     ->", r.fact("地球绕太阳转", "地球围绕太阳公转"))
    print("pairwise ->", json.dumps(r.pairwise("题干", "答案A", "答案B", dims),
                                    ensure_ascii=False))
    print("stats    ->", r.stats())
    print("make_env ->", sorted(make_env(_client.StubClient()).keys()))
