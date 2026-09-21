#!/usr/bin/env python3
"""把 raw/ 下的公开集原始记录转换成统一 Task Instance，按门类写 instances.jsonl。

两个来源合并：
  1. **公开集转换** —— 直接复用 benchmark_v0.2/adapter 里已有的 9 个 adapter，
     不重复实现字段映射。
  2. **人工撰写** —— 门类目录下的 authored.jsonl（已是统一 schema），
     用于公开集覆盖不到的场景（G5 方案设计、G8 根因标签、G9 企业工具等）。

用法: python3 build_instances.py [--only G7] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # dataset/
ADAPTER_PKG = os.path.join(os.path.dirname(ROOT), "benchmark_v0.2", "adapter")
sys.path.insert(0, ADAPTER_PKG)

from adapter.base import AdapterConfig            # noqa: E402
from adapter.registry import get_adapter          # noqa: E402
from adapter.schema import validate_instance      # noqa: E402
from adapter.utils.io import read_json, read_jsonl  # noqa: E402

# 门类目录 -> [(adapter 名, raw 文件, aux 文件 or None)]
PLAN = {
    "G1_knowledge_qa": [
        ("simpleqa",         "simpleqa.jsonl",         None),
        ("chinese_simpleqa", "chinese_simpleqa.jsonl", None),
        ("frames",           "frames.jsonl",           None),
    ],
    "G2_retrieval": [
        ("beir",             "beir_scifact_queries.jsonl", "beir_scifact_aux.json"),
    ],
    "G4_writing": [
        ("ifeval",           "ifeval.jsonl",           None),
    ],
    "G6_data_analysis": [
        ("dabstep",          "dabstep.jsonl",          None),
    ],
    "G7_code_sql": [
        ("bird_sql",         "bird_minidev.jsonl",     "bird_minidev_aux.json"),
        ("bigcodebench",     "bigcodebench.jsonl",     None),
    ],
    # 以下门类没有可直接转换的公开集，全部走 authored.jsonl：
    #   G3 长上下文原文体积过大，需外部化存储后另行处理
    #   G5 公开集零覆盖（v0.2 §3.2 结论）
    #   G8 RCAEval 只有故障元数据，没有根因标签与修复命令白名单
    #   G9 ToolACE/APIGen-MT 的工具 schema 与企业内部工具不匹配
    #   G10 HelpSteer3/MT-Bench 需人工补 rubric 维度
    #   S   公开集只给攻击 prompt，判定标准需自定义
    "G3_comprehension": [],
    "G5_solution_design": [],
    "G8_diagnosis": [],
    "G9_tool_ops": [],
    "G10_communication": [],
    "S_safety": [],
}


def convert_one(adapter_name, raw_path, aux_path, quiet=False):
    cls = get_adapter(adapter_name)
    aux = read_json(aux_path) if aux_path and os.path.exists(aux_path) else {}
    cfg = AdapterConfig(aux=aux)
    a = cls(cfg)
    rows = list(a.run(read_jsonl(raw_path), cfg))
    if not quiet:
        st = a.stats                      # ConversionStats 对象，不是 dict
        print("    %-18s read %-3s -> %-3s 条  (过滤 %s / 出错 %s)"
              % (adapter_name, getattr(st, "read", "?"), len(rows),
                 getattr(st, "filtered", "?"), getattr(st, "errored", "?")))
    return [r.to_dict() for r in rows]


def attach_context(cat_dir, instances):
    """把门类级的语料清单挂到每条实例的 context.files 上。

    目前只有 G6 用得上：DABStep 在 HF 上只暴露 question/answer/guidelines，
    要分析的 payments.csv 和定义业务口径的 manual.md 在仓库的 data/context/ 下，
    得单独拉（scripts/fetch_dabstep_context.py）。

    不挂的后果不是「少点背景」，是**题目没法做**：模型只能闭卷猜一个国家码。
    而且 G6-DATA_ANALYSIS-0002 实测下来，「top country for fraud」按笔数是 NL、
    按 manual.md 定义的「欺诈金额/总金额」是 BE（12.27% vs 12.18%），金标取 BE
    —— 口径只写在 manual.md 里，不给这个文件就是在考猜谜。

    语料本身不入库（payments.csv 22.5 MB），入库的是 context_manifest.json 里的
    sha256，保证「评测时用的确实是这一份」。
    """
    mpath = os.path.join(ROOT, cat_dir, "context_manifest.json")
    if not os.path.exists(mpath):
        return 0
    files = [{"path": f["path"], "mime": f["mime"], "content_ref": f["content_ref"]}
             for f in read_json(mpath).get("files", [])]
    if not files:
        return 0
    for inst in instances:
        inst["context"]["files"] = files
    return len(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只构建某个门类目录，如 G7_code_sql")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    manifest, total, bad = [], 0, 0
    for cat_dir in sorted(PLAN, key=lambda d: (len(d.split("_")[0]), d)):
        if args.only and cat_dir != args.only:
            continue
        d = os.path.join(ROOT, cat_dir)
        if not os.path.isdir(d):
            continue
        print("[%s]" % cat_dir)

        instances, sources = [], []
        for adapter_name, raw_name, aux_name in PLAN[cat_dir]:
            raw_path = os.path.join(d, "raw", raw_name)
            if not os.path.exists(raw_path):
                print("    %-18s ! 缺 raw 文件 %s，跳过" % (adapter_name, raw_name))
                continue
            aux_path = os.path.join(d, "raw", aux_name) if aux_name else None
            got = convert_one(adapter_name, raw_path, aux_path, args.quiet)
            instances.extend(got)
            sources.append({"kind": "public", "adapter": adapter_name,
                            "raw": raw_name, "count": len(got)})

        authored = os.path.join(d, "authored.jsonl")
        if os.path.exists(authored):
            got = [json.loads(l) for l in open(authored, encoding="utf-8") if l.strip()]
            instances.extend(got)
            sources.append({"kind": "authored", "raw": "authored.jsonl",
                            "count": len(got)})
            if not args.quiet:
                print("    %-18s %d 条（人工撰写）" % ("authored", len(got)))

        if not instances:
            print("    (空)")
            continue

        n_ctx = attach_context(cat_dir, instances)
        if n_ctx and not args.quiet:
            print("    %-18s 挂载 %d 个语料文件到 context.files" % ("context", n_ctx))

        errs = 0
        for inst in instances:
            e = validate_instance(inst)
            if e:
                errs += 1
                print("    ! %s: %s" % (inst.get("id"), e))
        bad += errs

        out = os.path.join(d, "instances.jsonl")
        with open(out, "w", encoding="utf-8") as fh:
            for inst in instances:
                fh.write(json.dumps(inst, ensure_ascii=False) + "\n")
        total += len(instances)
        print("    => %d 条 -> %s/instances.jsonl  (schema 错误 %d)"
              % (len(instances), cat_dir, errs))

        manifest.append({"category_dir": cat_dir,
                         "category": cat_dir.split("_")[0],
                         "instances": len(instances),
                         "schema_errors": errs,
                         "sources": sources})

    mpath = os.path.join(ROOT, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump({"total_instances": total, "schema_errors": bad,
                   "usage": "internal routing evaluation only; not for redistribution",
                   "categories": manifest}, fh, ensure_ascii=False, indent=2)
    print("\n合计 %d 条，schema 错误 %d -> manifest.json" % (total, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
