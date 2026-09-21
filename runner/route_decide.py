#!/usr/bin/env python3
"""按门类给出「该路由到哪个模型」的加权决策。

    python3 runner/route_decide.py \
        --a runs/a_gemini_3_8_flash.jsonl \
        --b runs/b_claude_opus_4_8.jsonl \
        --price-a 0.075,0.30 --price-b 15.0,75.0 \
        --w quality=0.5,latency=0.2,cost=0.3

四个维度，四个刻度
------------------
质量  score 均值        0~1     越高越好
延迟  latency_s         秒      越低越好
输入  prompt_tokens     个      越低越好
输出  completion_tokens 个      越低越好
成本  usd = 输入×单价 + 输出×单价   越低越好

这四样没法直接相加。归一化用**相对比值**而不是 min-max：两个模型做 min-max
只会得到 1 和 0，幅度信息全丢 —— 「贵 3%」和「贵 300%」会长得一模一样。
相对比值下赢家恒为 1.0，输家拿到的数就是它相对赢家的倍率：

    越高越好:  norm = x / max(a, b)
    越低越好:  norm = min(a, b) / x

所以 0.34 的含义是「这一维只有对方的三分之一好」，可读且保留量级。

关于价格
--------
**价格不是测出来的，是你输入的。** run 文件里只有 token 数，usd 一直是
n/a（跑的时候没传 --price-in/--price-out）。本脚本的默认价目表是按
「flash 档 vs opus 档」的量级估的，**不是这两个模型的真实报价**，
必须用 --price-a / --price-b 覆盖成你实际付的价钱，否则成本维的结论没有意义。
量级差异极大（opus 档通常是 flash 档的 100~200 倍），所以只要成本权重
不为 0，它几乎一定主导结果 —— 这正是需要看翻转点的原因。

关于准入
--------
默认只报告、不拦截。加 --gate 后，准入 FAIL 的模型在该门类直接判出局：
「便宜且快，但答不对」不该被路由选中。G9 这类 status=unusable 的门类
一律跳过，不参与决策。
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "metrics"))
sys.path.insert(0, os.path.join(ROOT, "benchmark_v0.2", "adapter"))

import compare                                   # noqa: E402
import aggregate                                 # noqa: E402

# 美元 / 1M tokens。**占位量级，不是真实报价**，务必用 --price-a/--price-b 覆盖。
DEFAULT_PRICE = {"a": (0.075, 0.30), "b": (15.0, 75.0)}

DEFAULT_WEIGHTS = {"quality": 0.5, "latency": 0.2, "cost": 0.3,
                   "tokens_in": 0.0, "tokens_out": 0.0}

# 越低越好的维度
LOWER_BETTER = {"latency", "cost", "tokens_in", "tokens_out"}


def parse_kv_weights(text: str) -> Dict[str, float]:
    out = dict(DEFAULT_WEIGHTS)
    if not text:
        return out
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in DEFAULT_WEIGHTS:
            raise SystemExit("未知权重维度 %r，可用：%s"
                             % (k, ", ".join(sorted(DEFAULT_WEIGHTS))))
        out[k] = float(v)
    return out


def parse_price(text: str, fallback: Tuple[float, float]) -> Tuple[float, float]:
    if not text:
        return fallback
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 2:
        raise SystemExit("--price-* 格式为 `输入单价,输出单价`（美元/1M tokens）")
    return float(parts[0]), float(parts[1])


def per_category(recs: List[Dict[str, Any]], price: Tuple[float, float]
                 ) -> Dict[str, Dict[str, Any]]:
    """按门类汇总质量 / 延迟 / token / 成本。"""
    pin, pout = price
    acc: Dict[str, Dict[str, Any]] = {}
    for r in recs:
        cat = r.get("category")
        d = acc.setdefault(cat, {"scores": [], "lat": [], "tin": 0, "tout": 0,
                                 "n": 0, "missing": 0})
        d["n"] += 1
        s = compare.usable_score(r)
        if s is None:
            d["missing"] += 1        # 缺测不进均值，别拿对方的故障给自己加分
        else:
            d["scores"].append(s)
        c = (r.get("result") or {}).get("cost") or {}
        if c.get("latency_s"):
            d["lat"].append(float(c["latency_s"]))
        d["tin"] += int(c.get("prompt_tokens") or 0)
        d["tout"] += int(c.get("completion_tokens") or 0)

    out = {}
    for cat, d in acc.items():
        n_ok = len(d["scores"]) or 1
        lat = sorted(d["lat"]) or [0.0]
        out[cat] = {
            "n": d["n"],
            "missing": d["missing"],
            "quality": sum(d["scores"]) / n_ok if d["scores"] else None,
            # 用中位数：单条长尾不该决定一个门类的路由
            "latency": lat[len(lat) // 2],
            "latency_mean": sum(lat) / len(lat),
            "tokens_in": d["tin"],
            "tokens_out": d["tout"],
            "cost": d["tin"] / 1e6 * pin + d["tout"] / 1e6 * pout,
        }
    return out


def norm(a: Optional[float], b: Optional[float], dim: str
         ) -> Tuple[Optional[float], Optional[float]]:
    """相对比值归一化。赢家 1.0，输家按倍率折算。"""
    if a is None or b is None:
        return None, None
    if dim in LOWER_BETTER:
        lo = min(a, b)
        if lo <= 0:
            return (1.0, 1.0) if a == b else ((1.0, 0.0) if a < b else (0.0, 1.0))
        return lo / a, lo / b
    hi = max(a, b)
    if hi <= 0:
        return 1.0, 1.0
    return a / hi, b / hi


def verdicts(run_path: str) -> Dict[str, str]:
    """跑一遍门类报表，拿每个门类的准入结论。"""
    rep = aggregate.aggregate(aggregate.load_run(run_path))
    return {cat: v.get("verdict", "?")
            for cat, v in (rep.get("admission") or {}).items()}


def decide(cat_a, cat_b, weights, gate, va, vb, unusable):
    rows = []
    for cat in sorted(set(cat_a) | set(cat_b),
                      key=lambda c: (len(c), c)):
        if cat in unusable:
            rows.append({"cat": cat, "skip": "UNUSABLE（%s）" % unusable[cat]})
            continue
        A, B = cat_a.get(cat), cat_b.get(cat)
        if not A or not B:
            rows.append({"cat": cat, "skip": "只有一侧有数据"})
            continue

        dims, sa, sb, wsum = {}, 0.0, 0.0, 0.0
        for dim in ("quality", "latency", "cost", "tokens_in", "tokens_out"):
            w = weights.get(dim, 0.0)
            na, nb = norm(A.get(dim), B.get(dim), dim)
            dims[dim] = {"a": A.get(dim), "b": B.get(dim), "na": na, "nb": nb, "w": w}
            if w and na is not None:
                sa += w * na
                sb += w * nb
                wsum += w
        if wsum:
            sa, sb = sa / wsum, sb / wsum

        ga = va.get(cat, "?")
        gb = vb.get(cat, "?")
        blocked_a = gate and ga == "FAIL"
        blocked_b = gate and gb == "FAIL"

        if blocked_a and blocked_b:
            winner, why = "—", "两侧均未通过准入"
        elif blocked_a:
            winner, why = "B", "A 未通过准入，被门禁排除"
        elif blocked_b:
            winner, why = "A", "B 未通过准入，被门禁排除"
        elif abs(sa - sb) < 1e-9:
            winner, why = "平", "综合分完全相同"
        else:
            winner = "A" if sa > sb else "B"
            why = ""

        rows.append({"cat": cat, "dims": dims, "sa": sa, "sb": sb,
                     "winner": winner, "why": why,
                     "verdict_a": ga, "verdict_b": gb,
                     "n": A["n"], "missing": A["missing"] + B["missing"]})
    return rows


def flip_point(dims, weights, dim="cost"):
    """把某一维的权重推到多大，胜负才会翻转。

    综合分对单维权重是单调的，所以直接解一元一次方程即可。
    返回 None 表示在 [0,1] 内怎么调都翻不了。
    """
    base_w = {k: v for k, v in weights.items() if k != dim}
    rest = sum(base_w.values())
    ra = sum(base_w[k] * dims[k]["na"] for k in base_w if dims[k]["na"] is not None)
    rb = sum(base_w[k] * dims[k]["nb"] for k in base_w if dims[k]["nb"] is not None)
    na, nb = dims[dim]["na"], dims[dim]["nb"]
    if na is None:
        return None
    # (ra + w*na)/(rest+w) == (rb + w*nb)/(rest+w)  →  ra + w*na == rb + w*nb
    denom = (nb - na)
    if abs(denom) < 1e-12:
        return None
    w = (ra - rb) / denom
    return w if w >= 0 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--price-a", help="A 的 `输入,输出` 单价（美元/1M tokens）")
    ap.add_argument("--price-b", help="B 的 `输入,输出` 单价（美元/1M tokens）")
    ap.add_argument("--w", help="权重，如 quality=0.5,latency=0.2,cost=0.3")
    ap.add_argument("--gate", action="store_true",
                    help="准入 FAIL 的模型在该门类直接出局")
    ap.add_argument("--json", help="同时写一份机器可读的结果")
    args = ap.parse_args()

    weights = parse_kv_weights(args.w)
    pa = parse_price(args.price_a, DEFAULT_PRICE["a"])
    pb = parse_price(args.price_b, DEFAULT_PRICE["b"])

    a_recs, a_tag = compare.load(args.a)
    b_recs, b_tag = compare.load(args.b)
    cat_a = per_category(a_recs, pa)
    cat_b = per_category(b_recs, pb)
    va, vb = verdicts(args.a), verdicts(args.b)
    unusable = {c: v["reason"][:40] for c, v in compare.category_status().items()}

    rows = decide(cat_a, cat_b, weights, args.gate, va, vb, unusable)

    W = 96
    print("=" * W)
    print("路由决策  A = %s    B = %s" % (a_tag, b_tag))
    print("=" * W)
    print("权重: " + "  ".join("%s=%.2f" % (k, v)
                               for k, v in weights.items() if v))
    print("价格(美元/1M tokens): A 输入 %.4f 输出 %.4f  |  B 输入 %.4f 输出 %.4f"
          % (pa[0], pa[1], pb[0], pb[1]))
    if not args.price_a or not args.price_b:
        print("⚠ 有一侧用的是内置占位价，不是真实报价。成本维结论仅供演示，"
              "请用 --price-a/--price-b 传真实单价。")
    print("门禁: %s" % ("开（准入 FAIL 直接出局）" if args.gate else "关（只报告）"))
    print()

    hdr = ("门类  n   质量A  质量B   延迟A  延迟B    成本A      成本B     "
           "综合A  综合B  推荐")
    print(hdr)
    print("-" * W)
    for r in rows:
        if "skip" in r:
            print("%-5s %s" % (r["cat"], r["skip"]))
            continue
        d = r["dims"]
        print("%-5s %-3d %.3f  %.3f   %5.2fs %5.2fs  $%-8.5f $%-8.5f  "
              "%.3f  %.3f  %s%s"
              % (r["cat"], r["n"],
                 d["quality"]["a"] or 0, d["quality"]["b"] or 0,
                 d["latency"]["a"], d["latency"]["b"],
                 d["cost"]["a"], d["cost"]["b"],
                 r["sa"], r["sb"], r["winner"],
                 ("  ← " + r["why"]) if r["why"] else ""))

    # 汇总
    tally = {}
    for r in rows:
        if "skip" in r:
            continue
        tally[r["winner"]] = tally.get(r["winner"], 0) + 1
    print("-" * W)
    print("推荐分布: " + "  ".join("%s=%d" % (k, v) for k, v in sorted(tally.items())))

    # 翻转点：成本权重推到多少会改判
    print()
    print("成本权重翻转点（其余权重固定，把 cost 的权重调到该值即改判）")
    print("-" * W)
    for r in rows:
        if "skip" in r or r["winner"] in ("—", "平"):
            continue
        fp = flip_point(r["dims"], weights, "cost")
        if fp is None:
            # w 解出负数 = 就算把成本权重压到 0，赢家在其余维度上照样赢。
            # 这和「该维没差异」是两回事，不能混着说。
            print("  %-5s 当前推荐 %s —— 成本权重归零也不改判，"
                  "%s 在质量/延迟上本身就占优"
                  % (r["cat"], r["winner"], r["winner"]))
        else:
            other = "B" if r["winner"] == "A" else "A"
            print("  %-5s 当前推荐 %s —— cost 权重降到 %.3f 以下改判为 %s（当前 %.2f）"
                  % (r["cat"], r["winner"], fp, other, weights.get("cost", 0.0)))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"a": a_tag, "b": b_tag, "weights": weights,
                       "price_a": pa, "price_b": pb, "rows": rows},
                      fh, ensure_ascii=False, indent=2, default=str)
        print("\n已写出 %s" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
