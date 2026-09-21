#!/usr/bin/env python3
"""被测模型（SUT）的客户端。注意与 metrics/judge/client.py 区分：

    metrics/judge/client.py   —— 评分的那个模型（judge）
    runner/clients.py         —— 被评分的那个模型（system under test）

两者必须能独立配置。benchmark_plan.md §消偏 有一条硬约束：
**Judge 模型不得为被测模型自身**，否则 rubric 题会 self-preference。
`assert_not_same_provider()` 就是用来在跑之前把这条卡住的。

只依赖标准库（urllib）。三个 provider 的差异只在 URL、鉴权头和 JSON 形状上，
所以没必要引 SDK。
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class ModelError(RuntimeError):
    pass


class Usage(object):
    """累计用量。这是整个项目里第一处真实的成本数据 ——

    判分器的 cost.tokens / cost.usd 槽位一直是 0，因为判分器拿不到模型侧的
    计数。只有 runner 能填。run_benchmark.py 会把它合并进 CheckerResult.cost，
    四象限里的成本象限才开始有东西。
    """

    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.usd = 0.0
        self.wall_s = 0.0
        self.errors = 0

    def add(self, pt: int, ct: int, usd: float, wall_s: float) -> None:
        self.calls += 1
        self.prompt_tokens += pt
        self.completion_tokens += ct
        self.usd += usd
        self.wall_s += wall_s

    def to_dict(self) -> Dict[str, Any]:
        return {"calls": self.calls,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "tokens": self.prompt_tokens + self.completion_tokens,
                "usd": round(self.usd, 6),
                "wall_s": round(self.wall_s, 3),
                "errors": self.errors}


class BaseModel(object):
    """统一接口。

    ``provider`` 是**厂商**身份（google / anthropic / openai），不是模型名 ——
    跨模型红线按厂商判，同厂商不同型号仍然算同源。
    """

    provider = "base"

    def __init__(self, model: str, temperature: float = 0.0,
                 max_tokens: int = 4096, timeout_s: float = 120.0,
                 retries: int = 3,
                 usd_per_1k_prompt: float = 0.0,
                 usd_per_1k_completion: float = 0.0):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.retries = retries
        self.p_rate = usd_per_1k_prompt
        self.c_rate = usd_per_1k_completion
        self.usage = Usage()
        # 被服务端拒收、只能摘掉的采样参数（如新版 Claude 的 temperature）。
        # 非空 = 这个模型没跑在我们指定的采样设置上，对比时要当成已知偏差。
        self.dropped_params: List[str] = []

    @property
    def tag(self) -> str:
        return "%s/%s" % (self.provider, self.model)

    def generate(self, system: str, user: str) -> Dict[str, Any]:
        """返回 {"text", "prompt_tokens", "completion_tokens", "usd", "latency_s"}。

        失败必须抛 ModelError，**不要**返回空串。空串会被判分器当成「模型答了
        但答得很差」，实际是「根本没答上」—— 两者在评测里必须区分。
        """
        raise NotImplementedError

    # ---- 通用 HTTP + 退避重试 ----
    def _post(self, url: str, headers: Dict[str, str],
              payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        last = None
        for attempt in range(self.retries):
            t0 = time.time()
            try:
                req = urllib.request.Request(url, data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout_s) as fh:
                    body = json.loads(fh.read().decode("utf-8"))
                return {"body": body, "latency_s": time.time() - t0}
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8")[:300]
                except Exception:
                    pass
                last = "HTTP %s %s" % (exc.code, detail)
                # 4xx 里只有 408/429 值得重试，其余重试也没用
                if exc.code not in (408, 429) and exc.code < 500:
                    break
            except (urllib.error.URLError, ValueError, KeyError) as exc:
                last = repr(exc)
            if attempt < self.retries - 1:
                time.sleep(2.0 ** attempt)
        self.usage.errors += 1
        raise ModelError("%s 请求失败: %s" % (self.tag, last))

    def _record(self, pt: int, ct: int, latency_s: float) -> Dict[str, Any]:
        usd = pt / 1000.0 * self.p_rate + ct / 1000.0 * self.c_rate
        self.usage.add(pt, ct, usd, latency_s)
        return {"prompt_tokens": pt, "completion_tokens": ct,
                "usd": usd, "latency_s": round(latency_s, 3)}


# --------------------------------------------------------------------------
# Google：Gemini API（generativelanguage）与 Vertex 的 :generateContent
# --------------------------------------------------------------------------
class GoogleModel(BaseModel):
    provider = "google"

    def __init__(self, model: str, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, **kw):
        BaseModel.__init__(self, model, **kw)
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY") or ""
        self.base_url = (base_url
                         or os.environ.get("GOOGLE_BASE_URL")
                         or "https://generativelanguage.googleapis.com/v1beta")

    def generate(self, system: str, user: str) -> Dict[str, Any]:
        url = "%s/models/%s:generateContent" % (self.base_url.rstrip("/"),
                                                self.model)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": self.temperature,
                                 "maxOutputTokens": self.max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        got = self._post(url, headers, payload)
        body = got["body"]
        cands = body.get("candidates") or []
        if not cands:
            # 安全过滤会导致空 candidates。这在 S 门类上是**预期行为**，
            # 但必须与「模型答了个空串」区分开，所以走 meta 而不是静默返回 ""。
            reason = (body.get("promptFeedback") or {}).get("blockReason")
            raise ModelError("%s 没有返回候选（blockReason=%s）。"
                             "S 门类上这通常是安全过滤，属于一种拒答，"
                             "应记为 blocked 而不是空回答" % (self.tag, reason))
        parts = ((cands[0].get("content") or {}).get("parts") or [])
        text = "".join(p.get("text", "") for p in parts)
        um = body.get("usageMetadata") or {}
        out = self._record(int(um.get("promptTokenCount") or 0),
                           int(um.get("candidatesTokenCount") or 0),
                           got["latency_s"])
        out["text"] = text
        out["finish_reason"] = cands[0].get("finishReason")
        return out


# --------------------------------------------------------------------------
# Anthropic：/v1/messages
# --------------------------------------------------------------------------
class AnthropicModel(BaseModel):
    provider = "anthropic"

    def __init__(self, model: str, api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 api_version: str = "2023-06-01", **kw):
        BaseModel.__init__(self, model, **kw)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
        self.base_url = (base_url or os.environ.get("ANTHROPIC_BASE_URL")
                         or "https://api.anthropic.com/v1")
        self.api_version = api_version

    def generate(self, system: str, user: str) -> Dict[str, Any]:
        url = "%s/messages" % self.base_url.rstrip("/")
        headers = {"Content-Type": "application/json",
                   "anthropic-version": self.api_version}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            payload["system"] = system

        got = self._post(url, headers, payload)
        body = got["body"]
        text = "".join(b.get("text", "") for b in (body.get("content") or [])
                       if b.get("type") == "text")
        um = body.get("usage") or {}
        out = self._record(int(um.get("input_tokens") or 0),
                           int(um.get("output_tokens") or 0),
                           got["latency_s"])
        out["text"] = text
        out["finish_reason"] = body.get("stop_reason")
        return out


# --------------------------------------------------------------------------
# OpenAI 兼容：/chat/completions（也覆盖 vLLM / LiteLLM / 各家网关）
# --------------------------------------------------------------------------
class OpenAICompatModel(BaseModel):
    provider = "openai"

    def __init__(self, model: str, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, provider_name: Optional[str] = None,
                 **kw):
        BaseModel.__init__(self, model, **kw)
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL")
                         or "https://api.openai.com/v1")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        if provider_name:
            # 走网关代理其它厂商时，厂商身份要如实标注，
            # 否则跨模型红线（judge 不得与被测同源）会被绕过。
            self.provider = provider_name

    def generate(self, system: str, user: str) -> Dict[str, Any]:
        url = "%s/chat/completions" % self.base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer %s" % self.api_key
        msgs: List[Dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})

        got = self._post(url, headers, {"model": self.model, "messages": msgs,
                                        "temperature": self.temperature,
                                        "max_tokens": self.max_tokens})
        body = got["body"]
        choice = (body.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        um = body.get("usage") or {}
        out = self._record(int(um.get("prompt_tokens") or 0),
                           int(um.get("completion_tokens") or 0),
                           got["latency_s"])
        out["text"] = text
        out["finish_reason"] = choice.get("finish_reason")
        return out


# --------------------------------------------------------------------------
# 离线：脚本化模型，用于测试 runner 本身
# --------------------------------------------------------------------------
class ScriptedModel(BaseModel):
    """按 instance_id 查表返回预置回答。没有网络也能验证整条链路。

    也可以用来跑「人工写的对照答案」，例如把金标当成一个虚拟模型，
    验证满分路径是通的。
    """

    provider = "scripted"

    def __init__(self, table: Dict[str, str], model: str = "scripted",
                 default: Optional[str] = None, **kw):
        BaseModel.__init__(self, model, **kw)
        self.table = table
        self.default = default
        self.current_id: Optional[str] = None

    def generate(self, system: str, user: str) -> Dict[str, Any]:
        key = self.current_id
        if key in self.table:
            text = self.table[key]
        elif self.default is not None:
            text = self.default
        else:
            raise ModelError("脚本化模型没有 %r 的预置回答" % key)
        out = self._record(len(user) // 4, len(text) // 4, 0.0)
        out["text"] = text
        out["finish_reason"] = "stop"
        return out


# --------------------------------------------------------------------------
# Vertex AI
# --------------------------------------------------------------------------
# 与直连 API 的三处差异，每一处都踩过：
#   1. global 端点的 host 没有区域前缀：aiplatform.googleapis.com，
#      而区域端点是 us-central1-aiplatform.googleapis.com
#   2. 用本地 ADC 调用时必须带 x-goog-user-project，否则 403
#   3. Claude 走 :rawPredict（不是 :predict），body 是 Anthropic 原生格式
#      再加一个 anthropic_version 字段，且 model 不出现在 body 里
# --------------------------------------------------------------------------

def _vertex_host(location: str) -> str:
    if location == "global":
        return "https://aiplatform.googleapis.com"
    return "https://%s-aiplatform.googleapis.com" % location


class _VertexBase(BaseModel):
    def __init__(self, model: str, project: Optional[str] = None,
                 location: str = "global", quota_project: Optional[str] = None,
                 **kw):
        BaseModel.__init__(self, model, **kw)
        from gcp_auth import TokenProvider, adc_quota_project
        self._tp = TokenProvider()
        self.project = (project or os.environ.get("VERTEX_PROJECT")
                        or adc_quota_project())
        if not self.project:
            raise ModelError("没有指定 Vertex project（--project 或 VERTEX_PROJECT）")
        self.location = location or os.environ.get("VERTEX_LOCATION") or "global"
        # 配额记在哪个项目下。用本地 ADC 时不带这个头会 403。
        self.quota_project = quota_project or self.project

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": "Bearer %s" % self._tp.token(),
                "Content-Type": "application/json",
                "x-goog-user-project": self.quota_project}

    def _endpoint(self, publisher: str, verb: str) -> str:
        return ("%s/v1/projects/%s/locations/%s/publishers/%s/models/%s:%s"
                % (_vertex_host(self.location), self.project, self.location,
                   publisher, self.model, verb))

    @property
    def tag(self) -> str:
        return "vertex-%s/%s" % (self.provider, self.model)


class VertexGeminiModel(_VertexBase):
    provider = "google"

    def generate(self, system: str, user: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": self.temperature,
                                 "maxOutputTokens": self.max_tokens},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        got = self._post(self._endpoint("google", "generateContent"),
                         self._headers(), payload)
        body = got["body"]
        cands = body.get("candidates") or []
        um = body.get("usageMetadata") or {}
        if not cands:
            reason = (body.get("promptFeedback") or {}).get("blockReason")
            raise ModelError("%s 无候选返回（blockReason=%s）。S 门类上这通常是"
                             "安全过滤，属于一种拒答，应记为 blocked 而非空回答"
                             % (self.tag, reason))
        c = cands[0]
        parts = ((c.get("content") or {}).get("parts") or [])
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        finish = c.get("finishReason")
        if not text and finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
            raise ModelError("%s 被安全策略拦截（finishReason=%s）" % (self.tag, finish))

        out = self._record(int(um.get("promptTokenCount") or 0),
                           int(um.get("candidatesTokenCount") or 0),
                           got["latency_s"])
        out["text"] = text
        out["finish_reason"] = finish
        return out


class VertexAnthropicModel(_VertexBase):
    provider = "anthropic"

    # 新一代 Claude（opus-4-8 起）不再接受 temperature，传了直接 400
    # invalid_request_error: "`temperature` is deprecated for this model."
    # 探到这条错误就摘掉参数重试，并把事实记下来 —— 这意味着它跑在模型
    # 默认采样上，跟 temperature=0 的 Gemini **采样设置不对等**，报表里
    # 必须能看见，不能悄悄吞掉。
    _TEMP_DEPRECATED = "`temperature` is deprecated"

    def __init__(self, model: str, anthropic_version: str = "vertex-2023-10-16",
                 **kw):
        _VertexBase.__init__(self, model, **kw)
        self.anthropic_version = anthropic_version
        self.send_temperature = True

    def _payload(self, system: str, user: str) -> Dict[str, Any]:
        # 注意 model 不进 body —— 它已经在 URL 里了。带上会 400。
        payload: Dict[str, Any] = {
            "anthropic_version": self.anthropic_version,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": user}],
        }
        if self.send_temperature:
            payload["temperature"] = self.temperature
        if system:
            payload["system"] = system
        return payload

    def generate(self, system: str, user: str) -> Dict[str, Any]:
        url = self._endpoint("anthropic", "rawPredict")
        try:
            got = self._post(url, self._headers(), self._payload(system, user))
        except ModelError as exc:
            if not (self.send_temperature and self._TEMP_DEPRECATED in str(exc)):
                raise
            self.send_temperature = False
            self.dropped_params.append("temperature")
            self.usage.errors -= 1   # 这次 400 是探测，不算模型故障
            got = self._post(url, self._headers(), self._payload(system, user))

        body = got["body"]
        text = "".join(b.get("text", "") for b in (body.get("content") or [])
                       if b.get("type") == "text")
        um = body.get("usage") or {}
        out = self._record(int(um.get("input_tokens") or 0),
                           int(um.get("output_tokens") or 0),
                           got["latency_s"])
        out["text"] = text
        out["finish_reason"] = body.get("stop_reason")
        return out


# --------------------------------------------------------------------------
PROVIDERS = {"google": GoogleModel,
             "anthropic": AnthropicModel,
             "openai": OpenAICompatModel,
             "vertex": VertexGeminiModel,
             "vertex_anthropic": VertexAnthropicModel}


def build(spec: str, **kw) -> BaseModel:
    """从 "provider:model" 构造客户端。

        vertex:gemini-3.8-flash            Vertex 上的 Gemini
        vertex_anthropic:claude-opus-4-8   Vertex Model Garden 上的 Claude
        google:gemini-...                  直连 Gemini API
        anthropic:claude-...               直连 Anthropic API
        openai:gpt-...                     OpenAI 兼容端点（含各类网关）
        scripted:<json文件>                离线自检

    不同 provider 接受的参数不一样（vertex 要 project/location，直连要
    base_url/api_key），这里按 provider 过滤，免得把不认识的 kw 传进去炸掉。
    """
    if ":" not in spec:
        raise ValueError("模型规格应形如 provider:model，例如 vertex:gemini-3.8-flash；"
                         "收到 %r" % spec)
    provider, model = spec.split(":", 1)

    if provider == "scripted":
        with open(model, encoding="utf-8") as fh:
            table = json.load(fh)
        return ScriptedModel(table, model=os.path.basename(model))

    if provider not in PROVIDERS:
        raise ValueError("未知 provider %r，可选 %s"
                         % (provider, sorted(PROVIDERS) + ["scripted"]))

    common = ("temperature", "max_tokens", "timeout_s", "retries",
              "usd_per_1k_prompt", "usd_per_1k_completion")
    if provider.startswith("vertex"):
        allowed = common + ("project", "location", "quota_project")
    else:
        allowed = common + ("base_url", "api_key", "provider_name")
    passed = {k: v for k, v in kw.items() if k in allowed and v is not None}
    return PROVIDERS[provider](model, **passed)


def assert_not_same_provider(sut: BaseModel, judge_provider: Optional[str]) -> None:
    """benchmark_plan.md §消偏：Judge 不得与被测模型同源。

    同源会导致 self-preference —— 模型给自己家的文风打高分。
    v0.2 §1 还补了一条：judge 也不得与合成数据的生成模型同源。
    这里只能卡住前者，后者需要在 synthgen 侧记录生成器身份。
    """
    if judge_provider and sut.provider == judge_provider:
        raise ModelError(
            "被测模型与 judge 同为 %s 厂商，违反 benchmark_plan.md 的消偏约束"
            "（self-preference）。请换一个 judge，或对 L3 门类不出结论。"
            % sut.provider)
