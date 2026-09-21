#!/usr/bin/env python3
"""从 HuggingFace datasets-server 抽取每个公开集的前 N 条真实样本。

只用标准库（目标机器没有 datasets / huggingface_hub）。
产物写到 dataset/<门类目录>/raw/<alias>.jsonl，外加一份 _fetch_meta.json 记录溯源。

用法:
    python3 fetch_public_samples.py [--n 3] [--out <dataset根目录>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://datasets-server.huggingface.co"

# 门类 → 目录名
CATEGORY_DIR = {
    "G1": "G1_knowledge_qa",
    "G2": "G2_retrieval",
    "G3": "G3_comprehension",
    "G4": "G4_writing",
    "G5": "G5_solution_design",
    "G6": "G6_data_analysis",
    "G7": "G7_code_sql",
    "G8": "G8_diagnosis",
    "G9": "G9_tool_ops",
    "G10": "G10_communication",
    "S": "S_safety",
}

# alias, 门类, repo, config, split, 许可证, 说明
SOURCES = [
    ("simpleqa",         "G1", "basicv8vc/SimpleQA",              "default", "test",
     "MIT", "短事实问答；显式区分 correct/incorrect/not attempted"),
    ("chinese_simpleqa", "G1", "OpenStellarTeam/Chinese-SimpleQA", "default", "train",
     "MIT", "中文短事实问答，6 大类 99 子类"),
    ("frames",           "G1", "google/frames-benchmark",         "default", "test",
     "Apache-2.0", "多跳事实推理，每题需综合 2-15 篇 Wikipedia"),

    ("beir_scifact_queries", "G2", "BeIR/scifact",                "queries", "queries",
     "CC-BY-SA-4.0(见说明)", "科学论断检索的 query 侧"),
    ("beir_scifact_corpus",  "G2", "BeIR/scifact",                "corpus",  "corpus",
     "CC-BY-SA-4.0(见说明)", "语料侧；全量 5183 篇，此处仅抽样示意"),
    ("beir_scifact_qrels",   "G2", "BeIR/scifact-qrels",          "default", "test",
     "CC-BY-SA-4.0(见说明)", "query↔doc 相关性标注"),

    ("longbench_v2",     "G3", "zai-org/LongBench-v2",            "default", "train",
     "Apache-2.0", "长上下文理解，含中英文，带 difficulty 标注"),
    ("ruler_niah",       "G3", "simonjegou/ruler",                "16384",   "test",
     "Apache-2.0(未逐一核实)", "合成长上下文 needle-in-haystack；完全合成，结构上不可能被污染"),

    ("ifeval",           "G4", "google/IFEval",                   "default", "train",
     "Apache-2.0", "可程序校验的指令约束（25 类 instruction_id）"),

    ("dabstep",          "G6", "adyen/DABstep",                   "tasks",   "dev",
     "CC-BY-4.0", "多步数据分析，hard 档顶尖系统仅 14-16%"),

    ("bird_minidev",     "G7", "birdsql/bird_mini_dev",           "default", "mini_dev_sqlite",
     "CC-BY-SA-4.0", "文本转 SQL，Mini-Dev 780 条。**必须取 sqlite 方言**——判分器跑 sqlite3"),
    ("bigcodebench",     "G7", "bigcode/bigcodebench",            "default", "v0.1.0_hf",
     "Apache-2.0", "函数级代码生成 + 官方单测"),

    ("rcaeval",          "G8", "phamquiluan/RCAEval",             "cases",   "train",
     "MIT(未逐一核实)", "微服务故障注入案例；v0.2 文档推荐的 G8 自建起点"),

    ("toolace",          "G9", "Team-ACE/ToolACE",                "default", "train",
     "Apache-2.0(未逐一核实)", "工具调用对话，含 system 里的工具定义"),
    ("apigen_mt",        "G9", "Salesforce/APIGen-MT-5k",         "dataset", "train",
     "CC-BY-4.0(未逐一核实)", "多轮工具调用轨迹 + 工具 schema"),

    ("helpsteer3",       "G10", "nvidia/HelpSteer3",              "preference", "validation",
     "CC-BY-4.0", "人类偏好对，用于 pairwise 与 Judge 校准"),
    ("mt_bench",         "G10", "HuggingFaceH4/mt_bench_prompts", "default", "train",
     "Apache-2.0(未逐一核实)", "多轮开放式对话，带部分参考答案"),

    ("jailbreakbench",   "S", "JailbreakBench/JBB-Behaviors",     "behaviors", "harmful",
     "MIT", "越狱行为集，100 条 harmful + 100 条 benign 对照"),
    ("orbench_hard",     "S", "bench-llm/or-bench",               "or-bench-hard-1k", "train",
     "CC-BY-4.0", "过度拒答（over-refusal）反向指标"),
    ("airbench_2024",    "S", "stanford-crfm/air-bench-2024",     "default", "test",
     "CC-BY-4.0", "taxonomy 出自 8 部政府法规 + 16 家公司政策"),
]


def http_json(path, timeout=40, **params):
    url = "%s/%s?%s" % (API, path, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": "model-eval-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.loads(fh.read().decode("utf-8"))


def fetch_rows(repo, config, split, n, attempts=4):
    """HF 的 datasets-server 偶发 502，必须重试，否则会漏抓。"""
    last = None
    for k in range(attempts):
        try:
            data = http_json("rows", dataset=repo, config=config, split=split,
                             offset=0, length=n)
            return [r["row"] for r in data.get("rows", [])], None
        except urllib.error.HTTPError as exc:
            last = "HTTP %s" % exc.code
            if exc.code in (401, 404):
                return None, last
        except Exception as exc:                                   # noqa: BLE001
            last = "%s: %s" % (type(exc).__name__, exc)
        time.sleep(3 + 3 * k)
    return None, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3, help="每个数据集抽多少条")
    ap.add_argument("--out", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="dataset 根目录")
    args = ap.parse_args()

    meta, ok_n, fail_n = [], 0, 0
    for alias, cat, repo, config, split, lic, note in SOURCES:
        rows, err = fetch_rows(repo, config, split, args.n)
        if rows is None or not rows:
            print("  --  %-22s %-38s %s" % (alias, repo, err or "empty"))
            fail_n += 1
            meta.append({"alias": alias, "category": cat, "repo": repo,
                         "config": config, "split": split, "license": lic,
                         "note": note, "fetched": 0, "error": err or "empty"})
            continue

        d = os.path.join(args.out, CATEGORY_DIR[cat], "raw")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "%s.jsonl" % alias)
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("  OK  %-22s %-38s %d 条 -> %s" % (alias, repo, len(rows),
                                                 os.path.relpath(path, args.out)))
        ok_n += 1
        meta.append({"alias": alias, "category": cat, "repo": repo,
                     "config": config, "split": split, "license": lic,
                     "note": note, "fetched": len(rows),
                     "columns": sorted(rows[0].keys()),
                     "path": os.path.relpath(path, args.out)})
        sys.stdout.flush()

    mpath = os.path.join(args.out, "_fetch_meta.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump({"api": API, "rows_per_dataset": args.n,
                   "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "sources": meta}, fh, ensure_ascii=False, indent=2)
    print("\n成功 %d / 失败 %d -> %s" % (ok_n, fail_n, os.path.relpath(mpath, args.out)))


if __name__ == "__main__":
    main()
