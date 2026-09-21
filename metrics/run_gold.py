#!/usr/bin/env python3
"""用金标回放生成一份判分结果，喂给 aggregate.py —— 只为验证接线，不是评测。

为什么需要它
------------
aggregate.py 需要 --run 结果文件才能跑，而真实结果要等接上模型才有。
这个脚本拿 dataset/ 里的金标反构「应当满分」的回答，走一遍真实判分器，
产出格式正确的 run 文件。它回答的是「指标管线通不通」，
**不是**「模型好不好」—— 分数全是满分才对，出现不满分说明判分链路有 bug。

与 dataset/scripts/validate_all.py 的关系：那边做金标闭环体检（逐条断言），
这边只负责把同一批结果落成 run 文件。gold_response() 直接复用那边的实现，
避免两处反构逻辑漂移。

用法:
    python3 metrics/run_gold.py -o /tmp/gold_run.jsonl
    python3 metrics/aggregate.py --run /tmp/gold_run.jsonl
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "benchmark_v0.2", "adapter"))
sys.path.insert(0, os.path.join(ROOT, "dataset", "scripts"))

from adapter.checkers import run_check              # noqa: E402
from adapter.schema import TaskInstance             # noqa: E402
from validate_all import gold_response, NO_REPLAY   # noqa: E402

DATASET = os.path.join(ROOT, "dataset")


def iter_instances():
    for name in sorted(os.listdir(DATASET)):
        path = os.path.join(DATASET, name, "instances.jsonl")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--judge", action="store_true",
                    help="按 JUDGE_BASE_URL / JUDGE_MODEL 装配真实 LLM judge 并注入 env。"
                         "没配环境变量时会回落到离线桩（判分器保留 stub=True 标记）")
    args = ap.parse_args()

    env = None
    if args.judge:
        sys.path.insert(0, HERE)
        from judge.runner import make_env    # noqa: E402
        env = make_env()

    written = skipped = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for raw in iter_instances():
            inst = TaskInstance.from_dict(raw)
            if inst.checker in NO_REPLAY:
                # 金标是约束清单而非参考文本，回放无意义。
                # 但仍要写一条空记录，否则该门类在报表里会显示 0 实例，
                # 让人误以为题目丢了。
                skipped += 1
                continue
            resp = gold_response(inst)
            if resp is None:
                skipped += 1
                continue
            result = run_check(inst, resp, checker_id=inst.checker, env=env)
            out.write(json.dumps({
                "instance_id": inst.id,
                "category": inst.category,
                "checker_id": inst.checker,
                "instance": raw,
                "result": result,
            }, ensure_ascii=False, default=str) + "\n")
            written += 1

    print("写入 %d 条，跳过 %d 条（无法回放）-> %s" % (written, skipped, args.out))
    print("提醒：这份结果是金标自己的分数，全部应为满分。不要当成模型评测结果。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
