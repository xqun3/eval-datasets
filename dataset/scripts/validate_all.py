#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量校验 dataset/ 下的实例：schema + 金标闭环 + 分布统计。

三件事，任何一件出问题都以非 0 退出码结束：

1. **schema 校验** —— 复用 adapter.schema.validate_instance，与 build 阶段同一套规则。
2. **金标闭环**（最重要）—— 把每条实例的 gold 反构成「模型回答」，喂回它自己的
   checker，分数必须是 1.0 且不触发任何 must_not。
   这一步抓的是**题目本身的 bug**，不是模型的 bug：如果参考答案都拿不到满分，
   这道题的满分区间就是空集，任何模型做它都是在被无差别扣分。
   （项目里真出过这种死题：G9 的金标终态含一个合法手机号，而 must_not 的 PII
   扫描当时把 final_state 也算成「模型说的话」，回显判泄露、抹掉判状态不符。）
3. **分布统计** —— 门类 / 难度 / 语言 / checker / 来源 / split 的实际配比，
   用来对照 SCHEMA 里 L1:L2:L3 = 3:5:2 的目标，以及「L1 确定性判分占比 ≥40%」。

用法:
    python3 validate_all.py              # 全量
    python3 validate_all.py --only G9    # 只看某门类
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # dataset/
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "benchmark_v0.2", "adapter"))

from adapter.checkers import run_check              # noqa: E402
from adapter.schema import TaskInstance, validate_instance  # noqa: E402

# 这些 checker 的金标里没有可回放的「参考文本」，闭环对它们无意义：
#   format_compliance -- IFEval 的 gold 是约束清单（「至少 300 词」「不要逗号」），
#                        要真生成一段满足约束的文本才能验，不是回放能解决的。
NO_REPLAY = {"format_compliance"}

# ---------------------------------------------------------------------------
# format_compliance 的约束自洽性
# ---------------------------------------------------------------------------
# 回放验不了这类金标，于是它整个逃过了闭环 —— G4 的 3 条实例在下面的统计里
# 一直显示「跳过」。代价是两条错约束一路活到了跑批：
#   0002  prompt 写「less than 5 sentences」，金标写成 at_least:5。方向反了，
#         结果只写 2 句（遵循指令）的模型被判失败，写满 5 句（违反指令）的
#         反倒满分 —— 这不是漏判，是把胜负判反。
#   0003  prompt 写「30-line poem，每行一句」，金标同时挂 at_least:30 和
#         at_least:31。后者永远不可能满足。
# 下面这些检查不需要看回答，光看约束清单本身就能抓出来。

_BOUNDS = {"word_count": ("word_count_at_least", "word_count_at_most"),
           "sentence_count": ("sentence_count_at_least", "sentence_count_at_most")}


def _parse_ifeval(entries):
    """把 "ifeval:key:arg" 拆成 (key, arg)，非 ifeval 条目跳过。"""
    out = []
    for e in entries or []:
        if not isinstance(e, str) or not e.startswith("ifeval:"):
            continue
        body = e[len("ifeval:"):]
        key, _, arg = body.partition(":")
        out.append((key, arg))
    return out


def constraint_issues(inst: TaskInstance):
    """静态检查一条实例的 ifeval 约束清单，返回问题描述列表。"""
    from adapter.checkers.format_compliance import CONSTRAINTS

    gv = inst.gold.get("value") if isinstance(inst.gold, dict) else None
    parsed = _parse_ifeval((gv or {}).get("must_cover"))
    if not parsed:
        return []

    issues = []
    by_key = collections.defaultdict(list)
    for key, arg in parsed:
        if key not in CONSTRAINTS:
            issues.append("未实现的约束 %r —— 判分时会被静默算作 unsupported，"
                          "等于这条要求根本没生效" % key)
            continue
        by_key[key].append(arg)

    # 同一个约束键出现多次：要么冗余，要么其中一条必然失败
    for key, argv in by_key.items():
        if len(argv) > 1:
            issues.append("约束 %r 出现 %d 次（参数 %s）—— 同向阈值只需保留"
                          "最严的那条，多出来的要么冗余要么写错了"
                          % (key, len(argv), ", ".join(map(repr, argv))))

    # 上下界互相矛盾：下界 > 上界，怎么写都过不了
    for name, (lo_key, hi_key) in _BOUNDS.items():
        los = [int(a) for a in by_key.get(lo_key, []) if str(a).lstrip("-").isdigit()]
        his = [int(a) for a in by_key.get(hi_key, []) if str(a).lstrip("-").isdigit()]
        if los and his and max(los) > min(his):
            issues.append("%s 的下界 %d 大于上界 %d —— 这条实例无论回答什么"
                          "都不可能满分" % (name, max(los), min(his)))
    return issues



def gold_response(inst: TaskInstance):
    """按 checker 反构一个「应当满分」的回答。

    必须按 ``inst.checker`` 分发，**不能**按 gold.value 里有哪些 key 去猜：
    DABStep 的 gold 同时带 doc_ids 和 value，按 key 猜会把引用型回答喂进
    numeric_em，三条 G6 全判 0（这个坑踩过一次）。
    """
    v = inst.gold["value"]
    ck = inst.checker

    if ck in ("sql_result_equiv", "exec_tests"):
        return {"text": v["ref_solution"]}
    if ck == "fact_recall":
        return {"text": v["ref_answer"]}
    if ck == "doc_recall_at_k":
        return {"citations": v["doc_ids"]}
    if ck == "numeric_em":
        return {"text": "Answer: %s" % v["value"]}
    if ck == "state_diff":
        seqs = v.get("valid_sequences") or [[]]
        info = v.get("communicate_info") or []
        return {"text": "已完成。" + " ".join(str(x) for x in info),
                "final_state": v["final_state"],
                "tool_calls": [{"name": n} for n in seqs[0]]}
    if ck == "rubric_judge":
        # rubric 的 gold 本来没有参考答案，ref_answer 是本数据集加的扩展字段，
        # 专门为了让这一步能闭环（见 author_instances.py 文件头第 6 条）。
        ref = v.get("ref_answer")
        return {"text": ref} if ref else None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只校验某个门类，如 G9")
    args = ap.parse_args()

    dirs = sorted((d for d in os.listdir(ROOT)
                   if os.path.isdir(os.path.join(ROOT, d)) and "_" in d),
                  key=lambda d: (len(d.split("_")[0]), d))

    stats = collections.defaultdict(collections.Counter)
    schema_errs, gold_fails, skipped, checked, total = [], [], [], 0, 0
    constraint_errs = []

    for cat_dir in dirs:
        path = os.path.join(ROOT, cat_dir, "instances.jsonl")
        if not os.path.exists(path):
            continue
        cat = cat_dir.split("_")[0]
        if args.only and cat != args.only:
            continue
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
        total += len(rows)

        for d in rows:
            errs = validate_instance(d)
            if errs:
                schema_errs.append((d.get("id"), errs))
                continue
            inst = TaskInstance.from_dict(d)
            stats["category"][inst.category] += 1
            stats["difficulty"][inst.difficulty] += 1
            stats["lang"][inst.lang] += 1
            stats["checker"][inst.checker] += 1
            stats["split"][inst.split] += 1
            stats["source"][inst.source.split(":")[0].split("@")[0]] += 1

            for issue in constraint_issues(inst):
                constraint_errs.append((inst.id, issue))

            resp = gold_response(inst)
            if resp is None:
                skipped.append((inst.id, inst.checker, "无可回放金标"))
                continue
            res = run_check(inst, resp)
            if res["sub_metrics"].get("env_only_failure"):
                # 本机缺 pandas/numpy 之类，是环境问题不是题目问题
                skipped.append((inst.id, inst.checker,
                                "缺依赖 %s" % res["detail"].get("missing_modules")))
                continue
            if res["violations"] or abs(res["score"] - 1.0) > 1e-6:
                gold_fails.append((inst.id, inst.checker, res["score"],
                                   res["violations"], res["sub_metrics"]))
            else:
                checked += 1

    # ---------------- 报告 ----------------
    print("=" * 66)
    print("实例总数: %d   schema 错误: %d   金标闭环通过: %d   跳过: %d   失败: %d"
          % (total, len(schema_errs), checked, len(skipped), len(gold_fails)))
    print("=" * 66)

    for key in ("category", "difficulty", "lang", "checker", "split", "source"):
        c = stats[key]
        items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
        print("\n[%s]" % key)
        for k, n in items:
            print("    %-22s %3d  %5.1f%%" % (k, n, 100.0 * n / max(total, 1)))

    if skipped:
        print("\n[跳过的闭环]（不计失败）")
        for iid, ck, why in skipped:
            print("    %-34s %-18s %s" % (iid, ck, why))

    if schema_errs:
        print("\n[schema 错误]")
        for iid, errs in schema_errs:
            print("    %-34s %s" % (iid, errs))

    if gold_fails:
        print("\n[金标闭环失败 —— 这些是死题，必须修]")
        for iid, ck, score, viol, sub in gold_fails:
            print("    %-34s %-16s score=%.3f violations=%s" % (iid, ck, score, viol))
            print("        sub_metrics=%s" % (sub,))

    if constraint_errs:
        print("\n[约束定义问题 —— 判分会算错，必须修]")
        for iid, issue in constraint_errs:
            print("    %-34s %s" % (iid, issue))

    return 1 if (schema_errs or gold_fails or constraint_errs) else 0


if __name__ == "__main__":
    sys.exit(main())
