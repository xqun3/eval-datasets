"""``python -m synthgen`` command line: generate / verify / validate / stats."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

from .pipeline import Pipeline, PipelineConfig
from .registry import CHECKERS, GENERATORS, load_builtins, registry_snapshot
from .schema import CATEGORIES, DIFFICULTIES, LANGS, SPLITS, SchemaError, TaskInstance
from .utils.jsonl import read_jsonl, write_jsonl


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m synthgen",
        description="合成评测数据生成骨架 (本地可跑, 零第三方依赖)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="生成任务实例 (JSONL)")
    gen.add_argument("--category", required=True, choices=list(CATEGORIES), help="任务门类")
    gen.add_argument("--n", type=int, default=5, help="目标条数")
    gen.add_argument("--seed", type=int, default=0, help="随机种子 (决定可复现性)")
    gen.add_argument("--out", default="out.jsonl", help="输出 JSONL 路径")
    gen.add_argument("--dry-run", action="store_true", help="不调真实 LLM, 使用确定性 stub")
    gen.add_argument("--lang", default="zh", choices=list(LANGS))
    gen.add_argument("--split", default="auto", choices=["auto"] + list(SPLITS))
    gen.add_argument("--difficulty", default="auto", choices=["auto"] + list(DIFFICULTIES))
    gen.add_argument("--max-attempts", type=int, default=3, help="质量闸门打回后的重试轮数")
    gen.add_argument("--review-rate", type=float, default=0.2, help="人工抽检比例")
    gen.add_argument("--dedup-threshold", type=float, default=0.85)
    gen.add_argument("--verify-threshold", type=float, default=0.7)
    gen.add_argument("--exclude-providers", default="", help="逗号分隔, 把同源厂商排除出生成池")
    gen.add_argument("--decontam-corpus", default=None, help="去污染对照语料 (每行一篇)")
    gen.add_argument("--model-config", default=None, help="模型池配置 JSON 文件")
    gen.add_argument("--report", default=None, help="把 run 统计写到这个 JSON 文件")
    gen.add_argument("--review-out", default=None, help="人工抽检样本输出 JSONL")
    gen.add_argument("--run-id", default=None, help="覆盖自动生成的 run_id")

    ver = sub.add_parser("verify", help="用确定性 checker 打分")
    ver.add_argument("--in", dest="in_path", required=True, help="任务实例 JSONL")
    ver.add_argument(
        "--solutions",
        default=None,
        help='候选答案 JSONL, 每行 {"id": ..., "solution": ...}; 缺省用 gold 自检',
    )
    ver.add_argument("--out", default=None, help="打分结果 JSONL")
    ver.add_argument("--dry-run", action="store_true", help="兼容参数: checker 本来就不调 LLM")
    ver.add_argument("--quiet", action="store_true")

    val = sub.add_parser("validate", help="按冻结 schema 校验 JSONL")
    val.add_argument("--in", dest="in_path", required=True)
    val.add_argument("--quiet", action="store_true")

    st = sub.add_parser("stats", help="统计分布")
    st.add_argument("--in", dest="in_path", required=True)
    st.add_argument("--json", action="store_true", help="输出 JSON 而不是表格")

    sub.add_parser("registry", help="列出已注册的 generator / verifier / checker")
    return parser


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def _load_instances(path: str):
    rows = read_jsonl(path)
    instances, errors = [], []
    for i, row in enumerate(rows, 1):
        try:
            instances.append(TaskInstance.from_dict(row))
        except SchemaError as exc:
            errors.append("line {}: {}".format(i, exc))
    return instances, errors


def cmd_generate(args: argparse.Namespace) -> int:
    model_config: Dict[str, Any] = {}
    if args.model_config:
        with open(args.model_config, "r", encoding="utf-8") as fh:
            model_config = json.load(fh)
    if not args.dry_run and not model_config:
        print(
            "[synthgen] 未开启 --dry-run 且没有 --model-config: 真实模式需要你自己实现 LLMClient "
            "并通过配置或 Python API 注入 (见 README「接入真实 LLM」)。",
            file=sys.stderr,
        )
        return 2

    cfg = PipelineConfig(
        category=args.category,
        n=args.n,
        seed=args.seed,
        lang=args.lang,
        split=args.split,
        difficulty=args.difficulty,
        dry_run=args.dry_run,
        max_attempts=args.max_attempts,
        dedup_threshold=args.dedup_threshold,
        verify_threshold=args.verify_threshold,
        review_rate=args.review_rate,
        decontam_corpus=args.decontam_corpus,
        exclude_providers=[p for p in args.exclude_providers.split(",") if p.strip()],
        model_config=model_config,
        run_id=args.run_id,
    )
    result = Pipeline(cfg).run()
    n = write_jsonl(args.out, [i.to_dict() for i in result.items])

    print("[synthgen] run_id={} pipeline={}".format(result.run_id, result.pipeline_name))
    print("[synthgen] 生成 {}/{} 条 -> {}".format(n, cfg.n, args.out))
    print("[synthgen] 模型角色: " + ", ".join(
        "{}={}:{}".format(role, spec["provider"], spec["model"])
        for role, spec in sorted(result.pool["roles"].items())
    ))
    print("[synthgen] 难度分布 {} | split 分布 {}".format(
        json.dumps(result.stats["by_difficulty"], ensure_ascii=False),
        json.dumps(result.stats["by_split"], ensure_ascii=False),
    ))
    print("[synthgen] 打回 {} 条, 原因: {}".format(
        result.stats["rejected"], json.dumps(result.stats["reject_reasons"], ensure_ascii=False)
    ))
    print("[synthgen] 被测候选解出率 {} | 第三方验证均分 {}".format(
        result.stats["candidate_solve_rate"], result.stats["avg_independent_verify_score"]
    ))
    print("[synthgen] 人工抽检 {} 条 | 成本 tokens={} usd={:.6f}".format(
        result.stats["human_review_sampled"], int(result.cost["tokens"]), result.cost["usd"]
    ))
    if result.stats["shortfall"]:
        print("[synthgen] 警告: 未达目标条数, 缺口 {}".format(result.stats["shortfall"]))

    if args.report:
        parent = os.path.dirname(os.path.abspath(args.report))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, ensure_ascii=False, indent=2)
        print("[synthgen] run 报告 -> {}".format(args.report))
    if args.review_out:
        write_jsonl(args.review_out, result.review_sample)
        print("[synthgen] 人工抽检样本 -> {}".format(args.review_out))
    return 0 if n else 1


def cmd_verify(args: argparse.Namespace) -> int:
    load_builtins()
    instances, errors = _load_instances(args.in_path)
    if errors:
        for e in errors:
            print("[synthgen] schema 错误 {}".format(e), file=sys.stderr)
        return 1

    solutions: Dict[str, Any] = {}
    if args.solutions:
        for row in read_jsonl(args.solutions):
            solutions[row["id"]] = row.get("solution", row.get("answer"))

    reports: List[Dict[str, Any]] = []
    passed = 0
    total_score = 0.0
    violation_hits = 0
    for inst in instances:
        checker = CHECKERS.get(inst.checker)
        if inst.id in solutions:
            candidate = solutions[inst.id]
            mode = "solution"
        else:
            candidate = GENERATORS.get(inst.category).reference_candidate(inst)
            mode = "gold_self_check"
        result = checker(inst, candidate)
        passed += 1 if result["passed"] else 0
        total_score += result["score"]
        violation_hits += 1 if result["violations"] else 0
        reports.append({"id": inst.id, "mode": mode, "result": result})
        if not args.quiet:
            print("[{}] {} score={:.3f} passed={} layer={} violations={}".format(
                mode, inst.id, result["score"], result["passed"], result["layer"],
                json.dumps(result["violations"], ensure_ascii=False),
            ))

    n = len(instances)
    print("[synthgen] verify: {}/{} passed, 平均分 {:.4f}, 命中 must_not 的样本 {}".format(
        passed, n, (total_score / n) if n else 0.0, violation_hits
    ))
    if args.out:
        write_jsonl(args.out, reports)
        print("[synthgen] 打分明细 -> {}".format(args.out))
    return 0 if passed == n else 1


def cmd_validate(args: argparse.Namespace) -> int:
    rows = read_jsonl(args.in_path)
    bad = 0
    for i, row in enumerate(rows, 1):
        try:
            inst = TaskInstance.from_dict(row)
        except SchemaError as exc:
            bad += 1
            print("line {}: 结构错误 {}".format(i, exc), file=sys.stderr)
            continue
        errs = inst.validate()
        if errs:
            bad += 1
            for e in errs:
                print("line {} [{}]: {}".format(i, row.get("id"), e), file=sys.stderr)
        elif not args.quiet:
            print("line {} [{}]: OK".format(i, inst.id))
    print("[synthgen] validate: {} 条, 合法 {}, 非法 {}".format(len(rows), len(rows) - bad, bad))
    return 1 if bad else 0


def cmd_stats(args: argparse.Namespace) -> int:
    instances, errors = _load_instances(args.in_path)
    counts: Dict[str, Dict[str, int]] = {
        "category": {}, "subtype": {}, "difficulty": {}, "lang": {},
        "split": {}, "gold_type": {}, "checker": {}, "source": {},
    }
    prompt_len = 0
    for inst in instances:
        for key, value in (
            ("category", inst.category), ("subtype", inst.subtype),
            ("difficulty", inst.difficulty), ("lang", inst.lang),
            ("split", inst.split), ("gold_type", inst.gold.type),
            ("checker", inst.checker), ("source", inst.source),
        ):
            counts[key][value] = counts[key].get(value, 0) + 1
        prompt_len += len(inst.prompt)
    summary = {
        "file": os.path.basename(args.in_path),
        "n": len(instances),
        "schema_errors": len(errors),
        "avg_prompt_chars": round(prompt_len / len(instances), 1) if instances else 0,
        "distributions": counts,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print("文件: {}  条数: {}  schema 错误: {}  平均 prompt 字数: {}".format(
        summary["file"], summary["n"], summary["schema_errors"], summary["avg_prompt_chars"]
    ))
    for key, dist in counts.items():
        if not dist:
            continue
        line = "  ".join("{}={}".format(k, v) for k, v in sorted(dist.items()))
        print("  {:<10} {}".format(key, line))
    return 0


def cmd_registry(args: argparse.Namespace) -> int:
    snap = registry_snapshot()
    for kind, names in snap.items():
        print("{}: {}".format(kind, ", ".join(names)))
    return 0


COMMANDS = {
    "generate": cmd_generate,
    "verify": cmd_verify,
    "validate": cmd_validate,
    "stats": cmd_stats,
    "registry": cmd_registry,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except FileNotFoundError as exc:
        print("[synthgen] 文件不存在: {}".format(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover
        return 130
