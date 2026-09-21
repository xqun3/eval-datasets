#!/usr/bin/env python3
"""LLM 客户端抽象。判分逻辑不直接碰 HTTP，只认这个接口。

为什么要抽象一层
----------------
judge 有三种运行形态，判分器不应该关心用的是哪种：
  1. StubClient    —— 离线、确定性，跑通管线用，分数无意义
  2. HttpClient    —— 真实 LLM，OpenAI 兼容的 /chat/completions
  3. ReplayClient  —— 回放录好的响应，让 judge 结果可复现

第 3 种不是可有可无的。LLM judge 有随机性，同一份答案两次跑分不同，
评测结论就不可复现。要么 temperature=0 + 缓存，要么录制回放。

本模块只依赖标准库（urllib），与项目「零第三方依赖」的约束一致。
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class JudgeError(RuntimeError):
    pass


class BaseClient(object):
    """统一接口：chat(messages) -> 文本。

    实现方必须保证：网络/解析失败抛 JudgeError，**不要**返回一个假分数。
    静默降级成默认分是评测里最危险的事 —— 报表看起来正常，数字全是编的。
    """

    name = "base"

    def chat(self, messages: List[Dict[str, str]], **kw) -> str:
        raise NotImplementedError

    # 统计：judge 是有成本的，必须能报出来。
    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.usd = 0.0
        self.wall_s = 0.0

    def cost(self) -> Dict[str, Any]:
        return {"calls": self.calls,
                "tokens": self.prompt_tokens + self.completion_tokens,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "usd": round(self.usd, 6),
                "wall_s": round(self.wall_s, 3)}


class StubClient(BaseClient):
    """离线桩：根据输入哈希产出确定性的「分数」。

    ⚠️ 它的输出不是质量判断，只用来验证接线。任何使用它产出的结果都必须
    带上 stub 标记（rubric_judge 已经这么做了，见 sub_metrics.stub）。
    """

    name = "stub"

    def chat(self, messages: List[Dict[str, str]], **kw) -> str:
        self.calls += 1
        blob = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        h = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        # 固定返回 3 分：不高不低，让人一眼看出这是桩而不是真分数
        return json.dumps({"scores": {}, "overall": 3, "reason": "stub:%s" % h[:8]})


class ReplayClient(BaseClient):
    """回放：按请求内容的哈希查表返回录好的响应。

    录制用 record=True 包一层真实 client；回放时 miss 直接抛错，
    不静默 fallback —— 悄悄换成别的 judge 会让复现结果与原始结果不可比。
    """

    name = "replay"

    def __init__(self, path: str, upstream: Optional[BaseClient] = None,
                 record: bool = False):
        BaseClient.__init__(self)
        self.path = path
        self.upstream = upstream
        self.record = record
        self.table: Dict[str, str] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        self.table[d["key"]] = d["response"]

    @staticmethod
    def _key(messages) -> str:
        blob = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def chat(self, messages: List[Dict[str, str]], **kw) -> str:
        self.calls += 1
        key = self._key(messages)
        if key in self.table:
            return self.table[key]
        if not (self.record and self.upstream):
            raise JudgeError("回放表里没有这条请求（key=%s...）。"
                             "要么录制不全，要么 prompt 模板变了——"
                             "后者意味着旧结果已不可比，不要混用" % key[:12])
        resp = self.upstream.chat(messages, **kw)
        self.table[key] = resp
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "messages": messages,
                                 "response": resp}, ensure_ascii=False) + "\n")
        return resp


class HttpClient(BaseClient):
    """OpenAI 兼容的 /chat/completions 客户端。

    默认 temperature=0：judge 必须可复现。想看 judge 的方差请显式传 n>1，
    而不是靠调高温度。
    """

    name = "http"

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None,
                 timeout_s: float = 60.0, retries: int = 3,
                 usd_per_1k_prompt: float = 0.0, usd_per_1k_completion: float = 0.0):
        BaseClient.__init__(self)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or os.environ.get("JUDGE_API_KEY") or ""
        self.timeout_s = timeout_s
        self.retries = retries
        self.p_rate = usd_per_1k_prompt
        self.c_rate = usd_per_1k_completion

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0,
             max_tokens: int = 1024) -> str:
        payload = json.dumps({"model": self.model, "messages": messages,
                              "temperature": temperature,
                              "max_tokens": max_tokens}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer %s" % self.api_key
        url = self.base_url + "/chat/completions"

        last = None
        for attempt in range(self.retries):
            t0 = time.time()
            try:
                req = urllib.request.Request(url, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout_s) as fh:
                    body = json.loads(fh.read().decode("utf-8"))
                self.wall_s += time.time() - t0
                self.calls += 1
                usage = body.get("usage") or {}
                pt = int(usage.get("prompt_tokens") or 0)
                ct = int(usage.get("completion_tokens") or 0)
                self.prompt_tokens += pt
                self.completion_tokens += ct
                self.usd += pt / 1000.0 * self.p_rate + ct / 1000.0 * self.c_rate
                return body["choices"][0]["message"]["content"]
            except (urllib.error.URLError, urllib.error.HTTPError,
                    KeyError, ValueError) as exc:
                self.wall_s += time.time() - t0
                last = exc
                # 指数退避。HF 那边 502/429 是常态，这里同理。
                if attempt < self.retries - 1:
                    time.sleep(1.5 ** attempt)
        raise JudgeError("judge 请求失败 %d 次: %s" % (self.retries, last))


def from_env() -> BaseClient:
    """按环境变量装配 client。没配就返回 StubClient 并打印醒目提示。

        JUDGE_BASE_URL   例如 http://localhost:8000/v1
        JUDGE_MODEL      模型名
        JUDGE_API_KEY    可选
        JUDGE_REPLAY     回放文件路径，配了就套一层 ReplayClient
        JUDGE_RECORD=1   回放 miss 时向上游真实请求并录制
    """
    base = os.environ.get("JUDGE_BASE_URL")
    model = os.environ.get("JUDGE_MODEL")
    replay = os.environ.get("JUDGE_REPLAY")

    if base and model:
        client: BaseClient = HttpClient(base, model)
    else:
        if replay and not os.environ.get("JUDGE_RECORD"):
            return ReplayClient(replay)
        sys_warn("未配置 JUDGE_BASE_URL / JUDGE_MODEL，使用离线桩。"
                 "本次 judge 分数无效，只能验证管线是否通。")
        return StubClient()

    if replay:
        return ReplayClient(replay, upstream=client,
                            record=bool(os.environ.get("JUDGE_RECORD")))
    return client


def sys_warn(msg: str) -> None:
    import sys
    sys.stderr.write("[judge] %s\n" % msg)
