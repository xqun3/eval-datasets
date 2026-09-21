#!/usr/bin/env python3
"""跑一个被测模型，产出 metrics/aggregate.py 能直接消费的 run 文件。

    python3 runner/run_benchmark.py \
        --model google:gemini-3.8-flash \
        --out runs/gemini.jsonl

    python3 metrics/aggregate.py --run runs/gemini.jsonl

对比两个模型：分别跑两次，再用 runner/compare.py。

关于成本
--------
判分器的 ``cost.tokens`` / ``cost.usd`` 一直是 0，因为判分器看不到模型侧的
用量。这里会把真实用量合并进 CheckerResult.cost，四象限的成本象限才有数。
定价用 --price-in / --price-out 传（美元 / 1k tokens），不传就只统计 token。

关于失败
--------
三种失败必须分开记，不能都算成 0 分：
  model_error  —— 请求失败/被安全过滤，模型根本没产出 → 不计入质量均值
  parse_failed —— 产出了但不符合输出契约 → 计入，但单独统计指令遵循率
  低分         —— 正常作答但答错 → 计入
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmark_v0.2", "adapter"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "metrics"))

from adapter.checkers import run_check           # noqa: E402
from adapter.schema import TaskInstance          # noqa: E402

import clients                                   # noqa: E402
import parsing                                   # noqa: E402
import prompting                                 # noqa: E402

DATASET = os.path.join(ROOT, "dataset")


def iter_instances(only: Optional[List[str]] = None):
    for name in sorted(os.listdir(DATASET)):
        path = os.path.join(DATASET, name, "instances.jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                if only and raw.get("category") not in only:
                    continue
                yield raw


def run_one(model: clients.BaseModel, raw: Dict[str, Any],
            env: Optional[Dict[str, Any]], budget: int) -> Dict[str, Any]:
    inst = TaskInstance.from_dict(raw)
    built = prompting.build_prompt(inst, root=DATASET, budget=budget)

    if isinstance(model, clients.ScriptedModel):
        model.current_id = inst.id

    rec: Dict[str, Any] = {
        "instance_id": inst.id,
        "category": inst.category,
        "checker_id": inst.checker,
        "model": model.tag,
        "instance": raw,
        "prompt_meta": built["meta"],
    }

    try:
        gen = model.generate(built["system"], built["user"])
    except clients.ModelError as exc:
        # 模型没产出。这不是 0 分，是缺测 —— aggregate 里 value=None 不进均值。
        rec["status"] = "model_error"
        rec["error"] = str(exc)
        rec["result"] = {
            "score": None, "passed": None, "layer": None,
            "sub_metrics": {}, "violations": [],
            "detail": {"model_error": str(exc)},
            "cost": {"tokens": 0, "usd": 0.0, "wall_s": 0.0},
        }
        return rec

    parsed = parsing.parse(inst.checker, gen["text"])
    result = run_check(inst, parsed["response"], checker_id=inst.checker, env=env)

    # 把模型侧的真实成本并进来。wall_s 保持为判分耗时，模型延迟单列。
    result["cost"]["tokens"] = gen["prompt_tokens"] + gen["completion_tokens"]
    result["cost"]["prompt_tokens"] = gen["prompt_tokens"]
    result["cost"]["completion_tokens"] = gen["completion_tokens"]
    result["cost"]["usd"] = round(gen["usd"], 6)
    result["cost"]["latency_s"] = gen["latency_s"]

    result["detail"]["parse"] = parsed["parse"]
    result["sub_metrics"]["contract_followed"] = (
        1.0 if parsed["parse"]["how"] in ("raw", "json", "fenced", "answer_line")
        else 0.0)

    # judge 坏掉 != 模型答得差。判分器报缺测时单独记一个状态，
    # 否则它在报表里长得跟「模型拿了 0 分」一模一样。
    if result.get("sub_metrics", {}).get("judge_failed"):
        rec["status"] = "judge_failed"
        rec["error"] = result.get("detail", {}).get("judge_error")
    elif parsed["parse"]["ok"]:
        rec["status"] = "ok"
    else:
        rec["status"] = "parse_failed"
    rec["raw_text"] = gen["text"]
    rec["finish_reason"] = gen.get("finish_reason")
    rec["result"] = result
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True,
                    help="provider:model，例如 vertex:gemini-3.8-flash 或 "
                         "vertex_anthropic:claude-opus-4-8")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", help="只跑指定门类，例如 --only G1 G7")
    ap.add_argument("--limit", type=int, help="只跑前 N 条（冒烟用）")
    ap.add_argument("--base-url")
    ap.add_argument("--api-key-env", help="从哪个环境变量读 key")
    ap.add_argument("--project", help="Vertex project（默认取 ADC 的 quota project）")
    ap.add_argument("--location", default="global",
                    help="Vertex location，默认 global")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--budget", type=int, default=prompting.DEFAULT_CONTEXT_BUDGET)
    ap.add_argument("--price-in", type=float, default=0.0,
                    help="美元 / 1k prompt tokens")
    ap.add_argument("--price-out", type=float, default=0.0,
                    help="美元 / 1k completion tokens")
    ap.add_argument("--judge", action="store_true",
                    help="给 L3 门类接真实 judge（需 JUDGE_VERTEX_MODEL 或 "
                         "JUDGE_BASE_URL/JUDGE_MODEL）")
    ap.add_argument("--allow-same-vendor-judge", action="store_true",
                    help="允许 judge 与被测模型同厂商。默认拒绝——"
                         "同源评审会 self-preference（benchmark_plan.md §消偏）。"
                         "放行时每条记录都会打上 judge_caveat 标记")
    ap.add_argument("--sleep", type=float, default=0.0, help="每条之间的间隔秒数")
    args = ap.parse_args()

    kw: Dict[str, Any] = {"temperature": args.temperature,
                          "max_tokens": args.max_tokens,
                          "usd_per_1k_prompt": args.price_in,
                          "usd_per_1k_completion": args.price_out,
                          "project": args.project,
                          "location": args.location}
    if args.base_url:
        kw["base_url"] = args.base_url
    if args.api_key_env:
        kw["api_key"] = os.environ.get(args.api_key_env, "")
    model = clients.build(args.model, **kw)

    env = None
    judge_caveat = None
    if args.judge:
        from judge.runner import make_env      # noqa: E402
        from judge import client as jc         # noqa: E402
        env = make_env()
        jrun = env.get("_judge_runner")
        if jrun and not isinstance(jrun.client, jc.StubClient):
            jp = (os.environ.get("JUDGE_PROVIDER")
                  or getattr(jrun.client, "provider", None))
            same = bool(jp) and jp == model.provider
            if same and not args.allow_same_vendor_judge:
                clients.assert_not_same_provider(model, jp)
            if same:
                # 放行了，但不能让这件事消失在日志里。写进每条记录，
                # 报表和后续读数据的人都能看到 L3 分数是被污染的。
                judge_caveat = (
                    "judge 与被测模型同为 %s 厂商（self-preference 风险）。"
                    "L3 门类（G4/G5/G10/S）的 rubric 分数存在系统性偏袒，"
                    "不得用于跨厂商的准入或映射决策。" % jp)
                print("!" * 78)
                print("警告: %s" % judge_caveat)
                print("!" * 78)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    counts = {"ok": 0, "parse_failed": 0, "model_error": 0, "judge_failed": 0}
    t0 = time.time()

    with open(args.out, "w", encoding="utf-8") as out:
        for n, raw in enumerate(iter_instances(args.only), 1):
            if args.limit and n > args.limit:
                break
            rec = run_one(model, raw, env, args.budget)
            if judge_caveat:
                rec["judge_caveat"] = judge_caveat
            if model.dropped_params:
                rec["sampling_dropped"] = list(model.dropped_params)
            counts[rec["status"]] = counts.get(rec["status"], 0) + 1
            out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            out.flush()          # 中途挂掉也保住已跑的部分
            score = (rec["result"] or {}).get("score")
            print("  [%3d] %-38s %-20s %s %s"
                  % (n, rec["instance_id"], rec["checker_id"],
                     ("%.3f" % score) if isinstance(score, float) else "  —  ",
                     "" if rec["status"] == "ok" else "<%s>" % rec["status"]))
            if args.sleep:
                time.sleep(args.sleep)

    u = model.usage.to_dict()
    print("\n%s  用时 %.1fs" % (model.tag, time.time() - t0))
    print("  正常 %d / 契约未遵循 %d / 模型无产出 %d / 判分器故障 %d"
          % (counts["ok"], counts["parse_failed"], counts["model_error"],
             counts["judge_failed"]))
    print("  tokens %d（in %d / out %d）  usd %.4f  模型总延迟 %.1fs"
          % (u["tokens"], u["prompt_tokens"], u["completion_tokens"],
             u["usd"], u["wall_s"]))
    if u["usd"] == 0.0 and u["tokens"] > 0:
        print("  注意：未传 --price-in/--price-out，成本只有 token 数没有金额")
    if model.dropped_params:
        print("  警告：%s 拒收参数 %s，本次跑在模型默认采样上；"
              "与对照组的采样设置不对等，属已知偏差"
              % (model.tag, ", ".join(sorted(set(model.dropped_params)))))

    # judge 自身的健康度。这些数一旦非零，本轮 L3 分数就不是完整测量。
    jrun = (env or {}).get("_judge_runner")
    if jrun is not None:
        js = jrun.stats()
        print("  judge: 调用 %s / 解析失败 %s / 弃权 %s"
              % (js.get("calls"), js.get("parse_failures"), js.get("abstained")))
        if counts["judge_failed"] or js.get("parse_failures"):
            print("  警告：有 %d 条 L3 未测到（judge 故障），这些条目 score=None "
                  "不进均值，别把它们当成模型得了 0 分" % counts["judge_failed"])
    print("\n下一步: python3 metrics/aggregate.py --run %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
