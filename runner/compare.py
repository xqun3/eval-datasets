#!/usr/bin/env python3
"""两个模型的 head-to-head 对比报表。

    python3 runner/compare.py --a runs/gemini.jsonl --b runs/claude.jsonl

为什么不直接看两张 aggregate 报表
---------------------------------
分别看两份门类均分，很容易得出「A 的 G7 是 0.83、B 是 0.67，A 更强」这种结论。
在 n=6 的门类上这句话没有意义 —— 差一道题就能翻盘。

所以这里做两件 aggregate 不做的事：
  1. **配对比较**：只在两个模型都跑了的同一批实例上比，按题算 赢/平/输
  2. **显著性**：对赢/输做精确二项检验（符号检验），并直接给出
     「当前样本量下，多大的差距才可能显著」

样本量不够时，报表会明写 INSUFFICIENT 而不是给一个好看的排名。
"""

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "metrics"))

import aggregate                       # noqa: E402
import registry                        # noqa: E402

ALPHA = 0.05
# 低于这个配对样本量，符号检验在 alpha=0.05 下**无论全胜与否**都不可能显著：
# 全胜 n 场的双侧 p = 2 * 0.5^n，要 <= 0.05 需要 n >= 6。
MIN_N_FOR_SIGNIFICANCE = 6


def binom_two_sided(wins: int, losses: int) -> Optional[float]:
    """符号检验的精确双侧 p 值。平局按惯例剔除，不计入 n。"""
    n = wins + losses
    if n == 0:
        return None
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def load(path: str) -> Tuple[List[Dict[str, Any]], str]:
    recs = []
    tag = "?"
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            tag = r.get("model", tag)
            recs.append(r)
    return recs, tag


def usable_score(r: Dict[str, Any]) -> Optional[float]:
    """模型无产出（model_error）记为缺测，不是 0 分。

    把请求失败当成 0 分，等于用对方的网络故障给自己加分。
    """
    if r.get("status") == "model_error":
        return None
    return registry._as_float((r.get("result") or {}).get("score"))


def paired(a_recs, b_recs) -> Dict[str, Dict[str, Any]]:
    """按门类做配对比较。"""
    ai = {r["instance_id"]: r for r in a_recs}
    bi = {r["instance_id"]: r for r in b_recs}
    common = sorted(set(ai) & set(bi))

    out: Dict[str, Dict[str, Any]] = {}
    for iid in common:
        ra, rb = ai[iid], bi[iid]
        cat = ra.get("category")
        d = out.setdefault(cat, {"n": 0, "wins": 0, "losses": 0, "ties": 0,
                                 "a_sum": 0.0, "b_sum": 0.0, "scored": 0,
                                 "a_missing": 0, "b_missing": 0,
                                 "detail": []})
        d["n"] += 1
        sa, sb = usable_score(ra), usable_score(rb)
        if sa is None:
            d["a_missing"] += 1
        if sb is None:
            d["b_missing"] += 1
        if sa is None or sb is None:
            continue
        d["scored"] += 1
        d["a_sum"] += sa
        d["b_sum"] += sb
        if abs(sa - sb) < 1e-9:
            d["ties"] += 1
            verdict = "tie"
        elif sa > sb:
            d["wins"] += 1
            verdict = "A"
        else:
            d["losses"] += 1
            verdict = "B"
        d["detail"].append({"instance_id": iid, "a": sa, "b": sb,
                            "winner": verdict})

    for cat, d in out.items():
        d["a_mean"] = d["a_sum"] / d["scored"] if d["scored"] else None
        d["b_mean"] = d["b_sum"] / d["scored"] if d["scored"] else None
        d["p_value"] = binom_two_sided(d["wins"], d["losses"])
        decisive = d["wins"] + d["losses"]
        if decisive < MIN_N_FOR_SIGNIFICANCE:
            d["verdict"] = "INSUFFICIENT"
            d["reason"] = ("有胜负的配对只有 %d 场，符号检验在 α=%.2f 下"
                           "即使全胜也不可能显著（需要 ≥%d 场）"
                           % (decisive, ALPHA, MIN_N_FOR_SIGNIFICANCE))
        elif d["p_value"] is not None and d["p_value"] <= ALPHA:
            d["verdict"] = "A 更强" if d["wins"] > d["losses"] else "B 更强"
            d["reason"] = "p=%.4f" % d["p_value"]
        else:
            d["verdict"] = "无显著差异"
            d["reason"] = "p=%.4f" % (d["p_value"] if d["p_value"] is not None
                                      else 1.0)
    return out


def cost_summary(recs) -> Dict[str, Any]:
    tok = usd = lat = 0.0
    n = 0
    for r in recs:
        c = (r.get("result") or {}).get("cost") or {}
        tok += float(c.get("tokens") or 0)
        usd += float(c.get("usd") or 0)
        lat += float(c.get("latency_s") or 0)
        n += 1
    return {"tokens": int(tok), "usd": round(usd, 4),
            "latency_total_s": round(lat, 1),
            "latency_mean_s": round(lat / n, 2) if n else None}


def status_summary(recs) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in recs:
        out[r.get("status", "?")] = out.get(r.get("status", "?"), 0) + 1
    return out


def contract_rate(recs) -> Optional[float]:
    """指令遵循率：按输出契约作答的比例。

    与质量分分开看。一个很聪明但不听格式的模型，在结构化门类上会拿低分，
    但那是指令遵循问题，不是能力问题 —— 路由决策要区别对待。
    """
    vals = [float((r.get("result") or {}).get("sub_metrics", {})
                  .get("contract_followed", float("nan")))
            for r in recs if r.get("status") != "model_error"]
    vals = [v for v in vals if v == v]
    return sum(vals) / len(vals) if vals else None


def category_status() -> Dict[str, Dict[str, str]]:
    """读 metrics/definitions/<CAT>.json 的 status。

    被标成 unusable 的门类，分差不是模型差距而是题目/环境缺陷造成的。
    报表必须自己把它们摘出去 —— 定义文件里标了而报表不读，等于没标。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    ddir = os.path.join(os.path.dirname(here), "metrics", "definitions")
    out: Dict[str, Dict[str, str]] = {}
    if not os.path.isdir(ddir):
        return out
    for fn in sorted(os.listdir(ddir)):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        try:
            with open(os.path.join(ddir, fn), encoding="utf-8") as fh:
                d = json.load(fh)
        except (ValueError, OSError):
            continue
        if d.get("status", "usable") != "usable":
            out[d.get("category", fn[:-5])] = {
                "status": d["status"],
                "reason": d.get("status_reason", ""),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="模型 A 的 run 文件")
    ap.add_argument("--b", required=True, help="模型 B 的 run 文件")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    a_recs, a_tag = load(args.a)
    b_recs, b_tag = load(args.b)
    per_cat = paired(a_recs, b_recs)

    unusable = category_status()
    for cat, info in unusable.items():
        if cat in per_cat:
            per_cat[cat]["verdict"] = "UNUSABLE"
            per_cat[cat]["reason"] = info["reason"]

    report = {
        "a": {"tag": a_tag, "records": len(a_recs),
              "status": status_summary(a_recs), "cost": cost_summary(a_recs),
              "contract_followed": contract_rate(a_recs)},
        "b": {"tag": b_tag, "records": len(b_recs),
              "status": status_summary(b_recs), "cost": cost_summary(b_recs),
              "contract_followed": contract_rate(b_recs)},
        "by_category": per_cat,
        "unusable_categories": unusable,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("=" * 84)
    print("Head-to-head:  A = %s    B = %s" % (a_tag, b_tag))
    print("=" * 84)
    print("%-6s %-5s %-8s %-8s %-6s %-6s %-6s %-9s %s"
          % ("门类", "n", "A均分", "B均分", "A赢", "平", "B赢", "p", "结论"))
    for cat in sorted(per_cat, key=lambda c: (len(c), c)):
        d = per_cat[cat]
        fa = "%.3f" % d["a_mean"] if d["a_mean"] is not None else "  —  "
        fb = "%.3f" % d["b_mean"] if d["b_mean"] is not None else "  —  "
        fp = "%.4f" % d["p_value"] if d["p_value"] is not None else "  —  "
        mark = "⛔" if cat in unusable else "  "
        print("%s%-6s %-5d %-8s %-8s %-6d %-6d %-6d %-9s %s"
              % (mark, cat, d["n"], fa, fb, d["wins"], d["ties"], d["losses"],
                 fp, d["verdict"]))

    print("\n" + "-" * 84)
    print("成本与稳定性")
    print("-" * 84)
    for key, side in (("A", report["a"]), ("B", report["b"])):
        c = side["cost"]
        cr = side["contract_followed"]
        print("  %s %-34s tokens=%-9d usd=%-8s 平均延迟=%-7s 契约遵循=%s"
              % (key, side["tag"], c["tokens"],
                 ("%.4f" % c["usd"]) if c["usd"] else "n/a",
                 ("%.2fs" % c["latency_mean_s"]) if c["latency_mean_s"] else "n/a",
                 ("%.3f" % cr) if cr is not None else "n/a"))
        print("      状态: %s" % side["status"])

    if unusable:
        print("\n" + "!" * 84)
        for cat, info in sorted(unusable.items()):
            print("⛔ %s 当前不可用，分数不反映模型能力，不得进入准入/映射决策。" % cat)
            print("   原因: %s" % info["reason"])
        print("!" * 84)

    insuf = [c for c, d in per_cat.items()
             if d["verdict"] == "INSUFFICIENT" and c not in unusable]
    if insuf:
        print("\n" + "!" * 84)
        print("以下门类样本量不足，不得据此下结论: %s" % ", ".join(sorted(insuf)))
        print("符号检验在 α=%.2f 下需要至少 %d 场有胜负的配对；"
              "当前数据集每门类只有 2~9 条。" % (ALPHA, MIN_N_FOR_SIGNIFICANCE))
        print("!" * 84)

    print("\n注：model_error 记为缺测，不计入均值 —— 把对方的请求失败算成 0 分"
          "等于给自己加分。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
