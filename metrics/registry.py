#!/usr/bin/env python3
"""聚合函数注册表 —— 从一堆单条 CheckerResult 汇总到门类级数字。

职责边界（重要）
----------------
本文件只负责「怎么算」，不负责「算哪些」。算哪些由 definitions/*.json 决定，
由 aggregate.py 读取并驱动。这样新增一个指标只需要改 JSON，不用改代码；
只有新增一种**聚合方式**时才动这里。

两类阈值不要混
--------------
  instance_threshold —— 单条级，硬编码在判分器里（如 fact_recall.py:117 的 0.85）
  admission_threshold —— 聚合级，门类准入线（如 G9「100 题过 85 题」）
本文件产出的是聚合值，只应与 admission_threshold 比较。
"""

import math
from typing import Any, Callable, Dict, List, Optional, Sequence

# --------------------------------------------------------------------------
# 取值：从单条 CheckerResult 里按 source 定义抽出一个数
# --------------------------------------------------------------------------

CheckerResult = Dict[str, Any]


def _as_float(v: Any) -> Optional[float]:
    """把判分器写出来的各种形态统一成 float。取不出数就返回 None（= 缺测）。

    缺测与 0 必须分开：模型答错是 0，判分器没跑是 None。前者进均值，后者不进。
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        f = float(v)
        return None if math.isnan(f) else f
    return None


def extract(result: CheckerResult, source: Dict[str, Any]) -> Optional[float]:
    """按指标定义里的 source 从一条 CheckerResult 取值。取不到返回 None。"""
    kind = source.get("kind")
    if kind == "score":
        return _as_float(result.get("score"))
    if kind == "passed":
        return _as_float(result.get("passed"))
    if kind == "sub_metric":
        sub = result.get("sub_metrics") or {}
        key = source.get("key")
        if key not in sub:
            return None
        return _as_float(sub.get(key))
    if kind == "violation":
        rule = source.get("rule")
        vios = result.get("violations") or []
        hit = any((v.get("rule") if isinstance(v, dict) else v) == rule for v in vios)
        return 1.0 if hit else 0.0
    if kind == "cost":
        cost = result.get("cost") or {}
        return _as_float(cost.get(source.get("key")))
    # kind == "derived" 由 aggregate.py 里的 DERIVED 表单独处理
    return None


# --------------------------------------------------------------------------
# 聚合：一列数 → 一个数
# --------------------------------------------------------------------------

AggFn = Callable[[Sequence[float]], Optional[float]]
_AGGREGATORS: Dict[str, AggFn] = {}


def register(name: str) -> Callable[[AggFn], AggFn]:
    def deco(fn: AggFn) -> AggFn:
        if name in _AGGREGATORS:
            raise ValueError("聚合函数 %r 重复注册" % name)
        _AGGREGATORS[name] = fn
        return fn
    return deco


def get(name: str) -> AggFn:
    if name not in _AGGREGATORS:
        raise KeyError("未知聚合方式 %r，已注册: %s" % (name, sorted(_AGGREGATORS)))
    return _AGGREGATORS[name]


def names() -> List[str]:
    return sorted(_AGGREGATORS)


@register("mean")
def agg_mean(xs: Sequence[float]) -> Optional[float]:
    """算术平均。空列表返回 None 而不是 0 —— 没题可算 ≠ 得零分。"""
    xs = list(xs)
    return sum(xs) / float(len(xs)) if xs else None


@register("mean_of_nonnull")
def agg_mean_of_nonnull(xs: Sequence[float]) -> Optional[float]:
    """与 mean 相同；语义上强调调用方已经剔除了缺测项。保留为独立名字是为了
    让 JSON 里能表达「这个指标本来就允许部分实例没有」。"""
    return agg_mean(xs)


@register("pass_rate")
def agg_pass_rate(xs: Sequence[float]) -> Optional[float]:
    """布尔通过率。输入应为 0/1。"""
    xs = list(xs)
    return sum(1.0 for x in xs if x >= 0.5) / float(len(xs)) if xs else None


@register("rate")
def agg_rate(xs: Sequence[float]) -> Optional[float]:
    """比率。与 mean 数值相同，但语义是「命中占比」，方向通常 lower_better。

    注意：definitions 里 kind=derived 的 rate（如 sum(a)/sum(b)）不走这里，
    它们在 aggregate.py 的 DERIVED 表里按分子分母各自求和后相除 ——
    「先除再平均」和「先求和再除」在样本量不均时结果不同，后者才是对的。
    """
    return agg_mean(xs)


@register("sum")
def agg_sum(xs: Sequence[float]) -> Optional[float]:
    xs = list(xs)
    return float(sum(xs)) if xs else None


@register("max")
def agg_max(xs: Sequence[float]) -> Optional[float]:
    xs = list(xs)
    return float(max(xs)) if xs else None


def _percentile(xs: Sequence[float], q: float) -> Optional[float]:
    """线性插值分位数。不引入 numpy —— 本项目全程零第三方依赖。"""
    xs = sorted(xs)
    if not xs:
        return None
    if len(xs) == 1:
        return float(xs[0])
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    return float(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))


@register("p50")
def agg_p50(xs: Sequence[float]) -> Optional[float]:
    return _percentile(xs, 0.5)


@register("p95")
def agg_p95(xs: Sequence[float]) -> Optional[float]:
    """p95 在 n<20 时没有统计意义，调用方应在报表里标注样本量。"""
    return _percentile(xs, 0.95)


# --------------------------------------------------------------------------
# 阈值判定
# --------------------------------------------------------------------------

_OPS = {
    ">=": lambda a, b: a >= b - 1e-9,
    ">": lambda a, b: a > b + 1e-9,
    "<=": lambda a, b: a <= b + 1e-9,
    "<": lambda a, b: a < b - 1e-9,
    "==": lambda a, b: abs(a - b) <= 1e-9,
}


def meets(value: Optional[float], threshold: Optional[Dict[str, Any]]) -> Optional[bool]:
    """value 是否满足 threshold。任一为 None 返回 None（= 判不了，不是没过）。

    返回 None 而不是 False 很关键：准入规则是合取（benchmark_plan.md §4.3），
    把「判不了」误当成「没过」会让一个其实合格的模型被拒；反过来更糟。
    调用方必须显式处理 None。
    """
    if value is None or not threshold:
        return None
    op = _OPS.get(threshold.get("op"))
    if op is None:
        return None
    return bool(op(float(value), float(threshold["value"])))
