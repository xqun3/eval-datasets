#!/usr/bin/env python3
"""用已保存的模型回答重新判分，不重新调模型。

    python3 runner/rescore.py --run runs/a_gemini_3_8_flash.jsonl --only G4

判分器改了、金标改了、阈值改了 —— 这些都不该逼着人再烧一遍 API。run 文件里
存了每条的 ``raw_text``，把它塞回 ScriptedModel 走一遍原来的 ``run_one``，
判分结果就重算了，而且走的是**完全相同**的 parse → check 路径，不会出现
「重判用的是另一套逻辑」这种偏差。

保留什么
--------
模型侧的事实一律沿用原记录，不允许被这次重判改写：
  model / cost.tokens / cost.usd / cost.latency_s / finish_reason /
  judge_caveat / sampling_dropped
重判只改 ``result``（以及随之变化的 ``status``）。

判分侧的 ``cost.wall_s`` 会变成本次重判的耗时，这是对的 —— 它本来就是
判分耗时。

judge 的坑
----------
rubric_judge 这类要调 judge 的门类，重判等于重新调一次 judge，分数不可能
跟原来逐位相同（judge 本身有随机性）。所以默认**跳过**它们，除非显式
``--judge``。不加 --judge 又硬要重判 L3，只会把真 judge 的分换成桩分，
这比不重判更糟。

只重判一部分
------------
``--only G4`` 只重判 G4，其余记录原样透传。输出默认原地覆盖，
``--out`` 可以另存。
"""

import argparse
import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmark_v0.2", "adapter"))
sys.path.insert(0, HERE)

import clients                                   # noqa: E402
import prompting                                 # noqa: E402
from run_benchmark import DATASET, iter_instances, run_one   # noqa: E402

# 这些 checker 要调 judge，没有 --judge 就不能重判（会退化成桩分）
JUDGE_CHECKERS = {"rubric_judge"}

# 重判不得改写的字段：它们记录的是「模型当时做了什么」，与判分无关
PRESERVE_TOP = ("model", "finish_reason", "judge_caveat", "sampling_dropped")
PRESERVE_COST = ("tokens", "prompt_tokens", "completion_tokens", "usd", "latency_s")


def _instance_index(only: Optional[List[str]]):
    """instance_id -> (磁盘上的最新实例, 所在门类目录)。

    必须重新从磁盘读，不能用 run 文件里存的 ``instance`` 快照 —— 重判的
    全部意义就在于金标可能已经改了。目录也得跟着走，context.files 的相对
    路径要靠它解析。
    """
    out: Dict[str, Any] = {}
    for raw, src_dir in iter_instances(only):
        out[raw["id"]] = (raw, src_dir)
    return out


def rescore_record(rec: Dict[str, Any], fresh: Dict[str, Any], src_dir: str,
                   env: Optional[Dict[str, Any]],
                   budget: int) -> Dict[str, Any]:
    """拿 rec 里存的 raw_text 重新判一次分，模型侧事实原样搬回。

    ``fresh`` 是磁盘上的实例（可能含改过的金标），不是 rec["instance"]。
    """
    model = clients.ScriptedModel({rec["instance_id"]: rec["raw_text"]},
                                  model=rec.get("model") or "scripted")
    new = run_one(model, fresh, env, budget, root=src_dir)

    for k in PRESERVE_TOP:
        if k in rec:
            new[k] = rec[k]
        else:
            new.pop(k, None)
    old_cost = (rec.get("result") or {}).get("cost") or {}
    for k in PRESERVE_COST:
        if k in old_cost:
            new["result"]["cost"][k] = old_cost[k]
    return new


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="要重判的 run 文件")
    ap.add_argument("--out", help="输出路径，默认原地覆盖（会先备份 .bak）")
    ap.add_argument("--only", nargs="*", help="只重判指定门类，例如 --only G4")
    ap.add_argument("--budget", type=int,
                    default=prompting.DEFAULT_CONTEXT_BUDGET)
    ap.add_argument("--judge", action="store_true",
                    help="接真实 judge，允许重判 rubric_judge 门类")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    with open(args.run, encoding="utf-8") as fh:
        records = [json.loads(l) for l in fh if l.strip()]

    env = None
    if args.judge:
        from judge.runner import make_env      # noqa: E402
        env = make_env()

    index = _instance_index(None)
    only = set(args.only) if args.only else None

    out_records: List[Dict[str, Any]] = []
    changed: List[str] = []
    skipped_judge = 0
    t0 = time.time()

    for rec in records:
        cat = rec.get("category")
        if only and cat not in only:
            out_records.append(rec)
            continue
        if rec.get("status") == "model_error" or rec.get("raw_text") is None:
            # 模型当时就没产出，没东西可重判
            out_records.append(rec)
            continue
        if rec.get("checker_id") in JUDGE_CHECKERS and not args.judge:
            skipped_judge += 1
            out_records.append(rec)
            continue
        entry = index.get(rec["instance_id"])
        if entry is None:
            print("跳过 %s：数据集里已找不到这条实例" % rec["instance_id"])
            out_records.append(rec)
            continue
        fresh, src_dir = entry

        old = rec.get("result") or {}
        new = rescore_record(rec, fresh, src_dir, env, args.budget)
        if (old.get("score") != new["result"].get("score")
                or old.get("passed") != new["result"].get("passed")):
            changed.append("%-44s %s → %s" % (
                rec["instance_id"], _fmt(old.get("score")),
                _fmt(new["result"].get("score"))))
        out_records.append(new)

    dest = args.out or args.run
    if dest == args.run and not args.no_backup:
        shutil.copy2(args.run, args.run + ".bak")
    with open(dest, "w", encoding="utf-8") as fh:
        for rec in out_records:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    print("重判完成：%d 条记录，用时 %.1fs → %s"
          % (len(out_records), time.time() - t0, dest))
    if skipped_judge:
        print("跳过 %d 条需要 judge 的记录（加 --judge 才会重判）" % skipped_judge)
    if changed:
        print("分数变化 %d 条：" % len(changed))
        for line in changed:
            print("  " + line)
    else:
        print("没有任何分数变化")
    return 0


def _fmt(v: Any) -> str:
    return "—" if v is None else ("%.3f" % v)


if __name__ == "__main__":
    raise SystemExit(main())
