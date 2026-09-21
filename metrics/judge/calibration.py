#!/usr/bin/env python3
"""Judge 与人工标注的一致性校准 —— benchmark_plan_v0.2.md §7 要求 κ ≥ 0.7。

为什么这一步不能省
------------------
没有校准的 LLM judge 只是「换了个模型来猜分」。judge 自己也会幻觉、也有
位置偏好、也偏爱长答案。κ 是唯一能回答「这个 judge 打的分能不能代替人」的量。
κ < 0.7 时 judge 分不得用于准入判定，只能当参考。

输入格式（JSONL，每行一条）:
    {"instance_id": "...", "dim": "完整性", "human": 4, "judge": 5}

用法:
    python3 metrics/judge/calibration.py --labels labels.jsonl
    python3 metrics/judge/calibration.py --demo      # 造数跑通，不需要标注文件
"""

import argparse
import json
import math
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

KAPPA_GATE = 0.7


def cohens_kappa(pairs: Sequence[Tuple[Any, Any]],
                 weights: Optional[str] = None) -> Optional[float]:
    """Cohen's κ。weights=None 普通 κ；"linear"/"quadratic" 为加权 κ。

    5 分制评分建议用 quadratic 加权：judge 给 4、人给 5 的「差一档」，
    和 judge 给 1、人给 5 的「差四档」，不该按同样的错误来算。
    普通 κ 会把两者都算成一次完全不一致，对有序评分过于苛刻。
    """
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if n == 0:
        return None
    cats = sorted({c for p in pairs for c in p})
    if len(cats) < 2:
        return None          # 只有一个类别，κ 无定义
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)

    obs = [[0.0] * k for _ in range(k)]
    for a, b in pairs:
        obs[idx[a]][idx[b]] += 1.0
    row = [sum(r) for r in obs]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]

    def w(i: int, j: int) -> float:
        if weights is None:
            return 0.0 if i == j else 1.0
        d = abs(i - j)
        m = float(k - 1)
        return (d / m) if weights == "linear" else (d / m) ** 2

    num = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w(i, j) * row[i] * col[j] / n for i in range(k) for j in range(k))
    if den == 0:
        return 1.0 if num == 0 else None
    return 1.0 - num / den


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def analyse(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    pairs = [(int(r["human"]), int(r["judge"])) for r in rows]
    hs = [float(p[0]) for p in pairs]
    js = [float(p[1]) for p in pairs]

    by_dim: Dict[str, List[Tuple[int, int]]] = {}
    for r in rows:
        by_dim.setdefault(r.get("dim", "_all"), []).append(
            (int(r["human"]), int(r["judge"])))

    out: Dict[str, Any] = {
        "n": len(pairs),
        "kappa": cohens_kappa(pairs),
        "kappa_quadratic": cohens_kappa(pairs, "quadratic"),
        "pearson": pearson(hs, js),
        "exact_agreement": (sum(1 for a, b in pairs if a == b) / float(len(pairs))
                            if pairs else None),
        "within_1": (sum(1 for a, b in pairs if abs(a - b) <= 1) / float(len(pairs))
                     if pairs else None),
        # judge 系统性偏高/偏低。正数=judge 比人松。
        "judge_bias": (sum(js) / len(js) - sum(hs) / len(hs)) if pairs else None,
        "by_dim": {},
    }
    for dim, ps in sorted(by_dim.items()):
        out["by_dim"][dim] = {
            "n": len(ps),
            "kappa": cohens_kappa(ps),
            "kappa_quadratic": cohens_kappa(ps, "quadratic"),
        }
    k = out["kappa_quadratic"]
    out["gate"] = KAPPA_GATE
    out["verdict"] = ("UNDECIDED" if k is None
                      else ("PASS" if k >= KAPPA_GATE else "FAIL"))
    return out


def print_report(a: Dict[str, Any]) -> None:
    print("=" * 66)
    print("Judge 校准报告   n=%s   结论: %s（门槛 κ≥%.1f）"
          % (a["n"], a["verdict"], a["gate"]))
    print("=" * 66)

    def f(v):
        return "—" if v is None else "%.3f" % v

    print("  Cohen's κ (unweighted)  %s" % f(a["kappa"]))
    print("  Cohen's κ (quadratic)   %s   ← 判定用这个" % f(a["kappa_quadratic"]))
    print("  Pearson r               %s" % f(a["pearson"]))
    print("  完全一致率              %s" % f(a["exact_agreement"]))
    print("  差距≤1 档占比           %s" % f(a["within_1"]))
    print("  judge 偏移（正=偏松）   %s" % f(a["judge_bias"]))
    print("\n  分维度：")
    for dim, d in a["by_dim"].items():
        print("    %-16s n=%-4d κ_quad=%s" % (dim, d["n"], f(d["kappa_quadratic"])))

    if a["n"] < 50:
        print("\n  ⚠️ 样本量 %d 偏小。κ 在小样本上极不稳定，"
              "建议至少 50 条（每维度 ≥20）再下结论。" % a["n"])
    if a["verdict"] == "FAIL":
        print("\n  ⚠️ κ 未达标：judge 分只能作为参考，不得用于门类准入判定。")


def demo_rows() -> List[Dict[str, Any]]:
    """造一批带轻微系统性偏松的标注，用来验证脚本本身是对的。"""
    import random
    random.seed(7)
    rows = []
    for i in range(60):
        for dim in ("完整性", "结构"):
            h = random.randint(1, 5)
            # judge 大致跟随人工，但偏松半档、偶尔差两档
            j = min(5, max(1, h + random.choice([0, 0, 0, 1, 1, -1, 2])))
            rows.append({"instance_id": "demo-%03d" % i, "dim": dim,
                         "human": h, "judge": j})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", help="人工标注 JSONL")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.demo:
        rows = demo_rows()
    elif args.labels:
        with open(args.labels, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
    else:
        ap.error("需要 --labels 或 --demo")

    a = analyse(rows)
    if args.json:
        print(json.dumps(a, ensure_ascii=False, indent=2))
    else:
        print_report(a)
    return 0 if a["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
