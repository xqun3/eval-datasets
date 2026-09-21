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

    return 1 if (schema_errs or gold_fails) else 0


if __name__ == "__main__":
    sys.exit(main())
