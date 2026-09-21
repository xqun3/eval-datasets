#!/usr/bin/env python3
"""把金标翻译成「符合输出契约的回答文本」，生成一张 scripted 模型的答案表。

这是 runner 的自检手段：一个完美模型按契约作答，整条链路
（prompting → 模型 → parsing → checker → metrics）必须全部判满分。
任何一处契约与解析对不上，这里就会掉分。

与 metrics/run_gold.py 的区别：
    run_gold.py     直接构造**结构化** response，跳过 prompting/parsing
    这个脚本         构造**文本** response，把 prompting/parsing 也纳入验证

用法:
    python3 runner/make_gold_script.py -o /tmp/gold_answers.json
    python3 runner/run_benchmark.py --model scripted:/tmp/gold_answers.json \
            --out /tmp/gold_run.jsonl
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATASET = os.path.join(ROOT, "dataset")


def gold_text(raw):
    """按判分器反构一段**符合输出契约**的文本回答。

    必须按 checker 分发，不能按 gold.value 里有哪些 key 去猜 ——
    DABStep 的 gold 同时带 doc_ids 和 value，按 key 猜会把引用型回答
    喂进 numeric_em（这个坑在 dataset/scripts/validate_all.py 里踩过）。
    """
    ck = raw["checker"]
    v = raw["gold"]["value"]

    if ck == "fact_recall":
        return v.get("ref_answer")
    if ck == "rubric_judge":
        # rubric 的 gold 本没有参考答案，ref_answer 是本数据集的扩展字段，
        # 只为让这一步能闭环。
        return v.get("ref_answer")
    if ck == "doc_recall_at_k":
        return json.dumps({"citations": v["doc_ids"]}, ensure_ascii=False)
    if ck == "numeric_em":
        return "推理略。\nAnswer: %s" % v["value"]
    if ck == "sql_result_equiv":
        return "```sql\n%s\n```" % v["ref_solution"]
    if ck == "exec_tests":
        return "```python\n%s\n```" % v["ref_solution"]
    if ck == "state_diff":
        seqs = v.get("valid_sequences") or [[]]
        info = v.get("communicate_info") or []
        return json.dumps({
            "tool_calls": [{"name": n, "arguments": {}} for n in seqs[0]],
            "final_state": v["final_state"],
            "text": "已完成。" + " ".join(str(x) for x in info),
        }, ensure_ascii=False)
    if ck == "format_compliance":
        # 金标是约束清单（「至少 300 词」「不要逗号」），不是参考文本。
        # 要真生成一段满足约束的文本才能验，回放解决不了 —— 跳过。
        return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    table = {}
    skipped = []
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
                text = gold_text(raw)
                if text is None:
                    skipped.append("%s (%s)" % (raw["id"], raw["checker"]))
                else:
                    table[raw["id"]] = text

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(table, fh, ensure_ascii=False, indent=1)

    print("写入 %d 条契约格式的金标回答 -> %s" % (len(table), args.out))
    if skipped:
        print("跳过 %d 条（金标无法回放）:" % len(skipped))
        for s in skipped:
            print("    %s" % s)
    print("\n这些回答应当全部判满分。有不满分的，说明 prompting 的输出契约"
          "与 parsing 的解析规则对不上，不是模型的问题。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
