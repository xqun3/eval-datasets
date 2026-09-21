#!/usr/bin/env python3
"""三方一致性校验：definitions/*.json  ↔  checker 代码  ↔  SCHEMA_v0.1.md §0

为什么需要这个脚本
------------------
指标定义在本项目里历史上散落三处（SCHEMA_v0.1.md §0、benchmark_plan.md §4.2、
benchmark_plan_v0.2.md §7），互相之间没有任何机制保证一致。definitions/ 想成为
第四处「唯一来源」，那就必须有东西来钉住它，否则只是第四份会腐烂的文档。

本脚本做四件事：
  1. 按 definitions/_schema.json 做结构校验（手写子集，不依赖 jsonschema）
  2. checkers[] 里的 id 必须在 adapter 的 checker 注册表里真实存在
  3. source.checker / source.key 必须指向真实存在的 checker 与 sub_metrics key
  4. instance_threshold.code 指向的 file.py:line 必须真的写着那个数

第 4 条是最重要的：它防止有人改了 fact_recall.py:117 的 0.85 而忘了改 JSON。

用法:
    python3 metrics/validate_definitions.py
    python3 metrics/validate_definitions.py --strict   # 把 WARN 也当失败
退出码 0=全过, 1=有 FAIL。
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFS = os.path.join(HERE, "definitions")
ADAPTER_ROOT = os.path.join(ROOT, "benchmark_v0.2", "adapter")
CHECKER_DIR = os.path.join(ADAPTER_ROOT, "adapter", "checkers")
SCHEMA_MD = os.path.join(ROOT, "benchmark_v0.2", "SCHEMA_v0.1.md")

CATEGORIES = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10", "S"]

# 每个 checker 实际会写出的 sub_metrics key。这张表是从判分器源码里逐个读出来的，
# 不是猜的；validate 时用它挡住 JSON 里写错 key（例如把 citation_groundedness
# 写成 citation_faithfulness 那种）。新增 sub_metric 时这里也要加。
KNOWN_SUB_METRICS = {
    "fact_recall": {"fact_recall", "required_total", "required_hit",
                    "optional_total", "optional_hit", "judge_used", "judge_stub"},
    "doc_recall_at_k": {"ndcg_at_10", "fake_doc_rate", "returned", "ranked",
                        "relevant", "fake", "k"},
    "citation_groundedness": {"must_cite_coverage", "span_verifiable", "fake_doc_count",
                              "quotes_checked", "cited", "must_cite", "bad_spans"},
    "numeric_em": {"exact_match", "mode", "rel_tol", "abs_tol"},
    "format_compliance": {"constraints_checked", "constraints_passed", "unsupported",
                          "semantic_deferred", "failed", "semantic_must_cover"},
    "exec_tests": {"syntax_ok", "tests_total", "tests_passed", "env_errors",
                   "env_only_failure"},
    "sql_result_equiv": {"syntax_ok", "tests_total", "tests_passed"},
    "state_diff": {"state_match", "sequence_match", "matched_sequence_index",
                   "communicate_recall", "forbidden_calls_hit", "calls_made"},
    "rubric_judge": {"rubric_mean_5", "per_dim", "must_cover_coverage", "stub"},
    "must_not_guard": {"rules_total", "rules_fired", "unresolved_rules"},
}

ENUMS = {
    "role": {"primary", "auxiliary", "guard"},
    "quadrant": {"quality", "safety", "reliability", "cost"},
    "direction": {"higher_better", "lower_better"},
    "unit": {"ratio", "count", "score_5", "seconds", "usd", "tokens"},
    "aggregate": {"mean", "pass_rate", "rate", "sum", "max", "p50", "p95",
                  "mean_of_nonnull"},
    "source_kind": {"score", "passed", "sub_metric", "violation", "cost", "derived"},
    "primary_layer": {"L1", "L2", "L3", "L1/L2"},
}

# 有天然量程的单位。count / seconds / usd / tokens 没有上界，不检。
UNIT_RANGE = {
    "ratio": (0.0, 1.0),
    "score_5": (1.0, 5.0),
}

# 判分器 sub_metrics 的真实刻度。
# 这张表必须存在，因为光看定义文件是看不出 rubric_mean_5 是 1~5 分的 ——
# 只有翻 rubric_judge.py 才知道。S.over_refusal_rate 就是这么把它当成
# 0~1 的比率用了：unit=ratio、阈值 <=0.1，取数却是 1~5 分。
SUB_METRIC_UNIT = {
    "rubric_mean_5": "score_5",
    "must_cover_coverage": "ratio",
    "fact_recall": "ratio",
    "ndcg_at_10": "ratio",
    "exact_match": "ratio",
    "state_match": "ratio",
    "sequence_match": "ratio",
    "tests_passed_ratio": "ratio",
}

METRIC_REQUIRED = ["id", "name", "role", "quadrant", "direction", "source", "aggregate"]
METRIC_ALLOWED = set(METRIC_REQUIRED) | {
    "unit", "instance_threshold", "admission_threshold", "implemented",
    "blocked_by", "notes"}
SOURCE_ALLOWED = {"kind", "checker", "key", "rule", "expr"}
TOP_REQUIRED = ["category", "name", "primary_layer", "checkers", "metrics"]
TOP_ALLOWED = set(TOP_REQUIRED) | {"notes", "status", "status_reason"}
STATUS_VALUES = {"usable", "unusable"}

ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class Report(object):
    def __init__(self):
        self.fails = []
        self.warns = []
        self.oks = 0

    def fail(self, where, msg):
        self.fails.append("%s: %s" % (where, msg))

    def warn(self, where, msg):
        self.warns.append("%s: %s" % (where, msg))


def load_registry():
    """返回 {checker_id: layer}。拿不到就返回 None（不阻断其余校验）。"""
    sys.path.insert(0, ADAPTER_ROOT)
    try:
        import adapter  # noqa: F401  触发 checker 注册
        from adapter.registry import checker_items
    except Exception as exc:  # pragma: no cover
        return None, str(exc)
    return {cid: spec.layer for cid, spec in checker_items()}, None


def check_structure(cat, doc, rep):
    where = "%s.json" % cat
    for k in TOP_REQUIRED:
        if k not in doc:
            rep.fail(where, "缺少必填字段 %s" % k)
    for k in doc:
        if k not in TOP_ALLOWED:
            rep.fail(where, "出现未定义字段 %s" % k)
    status = doc.get("status", "usable")
    if status not in STATUS_VALUES:
        rep.fail(where, "status=%r 不在 %s 内" % (status, sorted(STATUS_VALUES)))
    # 停用必须写清为什么。不写原因的停用标记，过两周就没人知道能不能解除。
    if status == "unusable" and not (doc.get("status_reason") or "").strip():
        rep.fail(where, "status=unusable 必须同时写 status_reason（原因与解除条件）")
    if doc.get("category") != cat:
        rep.fail(where, "category=%r 与文件名不符" % doc.get("category"))
    if doc.get("primary_layer") not in ENUMS["primary_layer"]:
        rep.fail(where, "primary_layer=%r 不在枚举内" % doc.get("primary_layer"))
    if not doc.get("metrics"):
        rep.fail(where, "metrics 不得为空")

    seen = set()
    for m in doc.get("metrics", []):
        mid = m.get("id", "<no-id>")
        w = "%s/%s" % (where, mid)
        for k in METRIC_REQUIRED:
            if k not in m:
                rep.fail(w, "缺少必填字段 %s" % k)
        for k in m:
            if k not in METRIC_ALLOWED:
                rep.fail(w, "出现未定义字段 %s" % k)
        if not ID_RE.match(str(mid)):
            rep.fail(w, "id 不符合 ^[a-z][a-z0-9_]*$")
        if mid in seen:
            rep.fail(w, "id 在本门类内重复")
        seen.add(mid)
        for field in ("role", "quadrant", "direction", "aggregate"):
            if field in m and m[field] not in ENUMS[field]:
                rep.fail(w, "%s=%r 不在枚举内" % (field, m[field]))
        if "unit" in m and m["unit"] not in ENUMS["unit"]:
            rep.fail(w, "unit=%r 不在枚举内" % m["unit"])

        # guard 的唯一作用就是一票否决，而否决靠的是 admission_threshold。
        # aggregate.py:339-340 只把「role in (primary,guard) 且算得出
        # meets_admission」的指标纳入准入，而 meets_admission 只在写了
        # admission_threshold 时才产生。所以标了 guard 却不写阈值，它会被
        # 静默过滤掉 —— 看定义文件的人以为守卫开着，实际什么都不拦。
        # G8.judge_stub_ratio 就是这么当了很久摆设的。
        if m.get("role") == "guard" and "admission_threshold" not in m:
            rep.fail(w, "role=guard 必须写 admission_threshold，"
                        "否则它在准入判定里会被直接忽略（aggregate.py:340）")

        src = m.get("source") or {}
        for k in src:
            if k not in SOURCE_ALLOWED:
                rep.fail(w, "source 出现未定义字段 %s" % k)
        if src.get("kind") not in ENUMS["source_kind"]:
            rep.fail(w, "source.kind=%r 不在枚举内" % src.get("kind"))

        # implemented 必须显式写。默认 true 会让报表说谎，这是本项目踩过的坑。
        if "implemented" not in m:
            rep.fail(w, "必须显式声明 implemented（不许靠默认值）")
        if m.get("implemented") is False and not m.get("blocked_by"):
            rep.fail(w, "implemented=false 必须写 blocked_by 说明卡在哪")
        if m.get("implemented") is True and m.get("blocked_by"):
            rep.warn(w, "implemented=true 却带着 blocked_by，疑似改了一半")

        for tk in ("instance_threshold", "admission_threshold"):
            t = m.get(tk)
            if t is None:
                continue
            if t.get("op") not in {">=", ">", "<=", "<", "=="}:
                rep.fail(w, "%s.op=%r 非法" % (tk, t.get("op")))
            if not isinstance(t.get("value"), (int, float)):
                rep.fail(w, "%s.value 必须是数字" % tk)
            if tk == "admission_threshold" and "code" in t:
                rep.fail(w, "admission_threshold 不得带 code —— 准入线是报表层的约定，"
                            "不是代码里的硬编码；带 code 说明把聚合级和单条级搞混了")

            # 阈值必须落在 unit 声明的量程里。
            # S.over_refusal_rate 就是反例：unit=ratio、阈值 <=0.1，取数却是
            # 1~5 分制的 rubric_mean_5。只要有人照 G5/G10 的样子把 implemented
            # 翻成 true，就会拿 4.4 去比 0.1，整个 S 门类必然 FAIL——而且方向
            # 是倒的：模型正确响应正常请求（rubric 高分）反被读成过度拒答。
            v = t.get("value")
            unit = m.get("unit")
            if isinstance(v, (int, float)) and unit in UNIT_RANGE:
                lo, hi = UNIT_RANGE[unit]
                if not (lo <= v <= hi):
                    rep.fail(w, "%s.value=%s 超出 unit=%s 的量程 [%s, %s] —— "
                                "要么阈值写错了，要么 unit 标错了"
                             % (tk, v, unit, lo, hi))

        # 从已知 sub_metric 取数时，unit 必须和那个 sub_metric 的真实刻度对上。
        # 光看定义文件是看不出 rubric_mean_5 是 1~5 分的，只有翻判分器才知道。
        src_for_unit = m.get("source") or {}
        if src_for_unit.get("kind") == "sub_metric":
            want = SUB_METRIC_UNIT.get(src_for_unit.get("key"))
            if want and m.get("unit") and m["unit"] != want:
                rep.fail(w, "source 取的是 sub_metric %r（刻度 %s），"
                            "但 unit 声明成了 %r —— 报表会按错误的刻度展示，"
                            "阈值也会按错误的刻度比较"
                         % (src_for_unit.get("key"), want, m["unit"]))


def check_against_registry(cat, doc, registry, rep):
    where = "%s.json" % cat
    if registry is None:
        return
    for cid in doc.get("checkers", []):
        if cid not in registry:
            rep.fail(where, "checkers 里的 %r 在 adapter 注册表中不存在" % cid)
    for m in doc.get("metrics", []):
        w = "%s/%s" % (where, m.get("id"))
        src = m.get("source") or {}
        cid = src.get("checker")
        if cid and cid not in registry:
            rep.fail(w, "source.checker=%r 在 adapter 注册表中不存在" % cid)
            continue
        if src.get("kind") == "sub_metric":
            if not cid:
                rep.fail(w, "kind=sub_metric 必须给 source.checker")
            elif not src.get("key"):
                rep.fail(w, "kind=sub_metric 必须给 source.key")
            else:
                known = KNOWN_SUB_METRICS.get(cid, set())
                if src["key"] not in known:
                    rep.fail(w, "%s 不产出 sub_metrics[%r]；它实际有 %s"
                             % (cid, src["key"], sorted(known)))
        if src.get("kind") == "derived" and not src.get("expr"):
            rep.fail(w, "kind=derived 必须写 expr 说明怎么算")
        if src.get("kind") == "violation" and not src.get("rule"):
            rep.fail(w, "kind=violation 必须写 rule 指明统计哪条 must_not 规则")


def check_threshold_code(cat, doc, rep):
    """instance_threshold.code 指向的那一行代码里必须真的出现该数值。

    这条是整个脚本存在的理由：代码里改了阈值而 JSON 没改，指标定义就开始说谎。
    """
    where = "%s.json" % cat
    for m in doc.get("metrics", []):
        t = m.get("instance_threshold")
        if not t or "code" not in t:
            continue
        w = "%s/%s" % (where, m.get("id"))
        ref = t["code"]
        # 允许 "a.py:12 / b.py:34" 这种多处形式
        for part in [p.strip() for p in ref.split("/") if p.strip()]:
            if ":" not in part:
                rep.fail(w, "instance_threshold.code=%r 格式应为 file.py:line" % part)
                continue
            fname, lineno = part.rsplit(":", 1)
            path = os.path.join(CHECKER_DIR, fname.strip())
            if not os.path.exists(path):
                rep.fail(w, "instance_threshold.code 指向的文件不存在: %s" % path)
                continue
            try:
                with open(path, encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
                ln = int(lineno)
            except ValueError:
                rep.fail(w, "instance_threshold.code 行号非法: %r" % lineno)
                continue
            if not (1 <= ln <= len(lines)):
                rep.fail(w, "%s 只有 %d 行，code 指向第 %d 行" % (fname, len(lines), ln))
                continue
            # 取目标行上下各 2 行，容忍代码小幅漂移，但不容忍数值对不上
            window = "\n".join(lines[max(0, ln - 3):ln + 2])
            val = t["value"]
            candidates = {str(val)}
            if isinstance(val, float):
                candidates.add(("%g" % val))
                candidates.add(("%.3f" % val).rstrip("0").rstrip("."))
            if val == 1.0:
                candidates.add("1.0 - 1e-9")
            if val == 0.0:
                candidates.add("clean")          # must_not_guard 用布尔表达
                candidates.add("fake")           # ir_metrics 的零容忍写法
            if not any(c in window for c in candidates):
                rep.fail(w, "%s 第 %d 行附近找不到阈值 %s —— 代码或 JSON 有一方已经过时:\n      %s"
                         % (fname, ln, val, lines[ln - 1].strip()))


def check_schema_md(rep):
    """SCHEMA_v0.1.md §0 的 11 行门类表必须与 definitions/ 的 category+name 对得上。"""
    if not os.path.exists(SCHEMA_MD):
        rep.warn("SCHEMA_v0.1.md", "文件不存在，跳过门类名核对")
        return {}
    names = {}
    with open(SCHEMA_MD, encoding="utf-8") as fh:
        md_lines = fh.readlines()
    for line in md_lines:
        m = re.match(r"^\|\s*(G\d+|S)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            names[m.group(1)] = m.group(2)
    missing = [c for c in CATEGORIES if c not in names]
    if missing:
        rep.warn("SCHEMA_v0.1.md", "§0 表里没解析到门类 %s" % missing)
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="把 WARN 也算失败")
    args = ap.parse_args()

    rep = Report()
    registry, reg_err = load_registry()
    if reg_err:
        rep.warn("registry", "无法导入 adapter checker 注册表，跳过 checker 核对: %s" % reg_err)
    md_names = check_schema_md(rep)

    found = sorted(f[:-5] for f in os.listdir(DEFS)
                   if f.endswith(".json") and not f.startswith("_"))
    for cat in CATEGORIES:
        if cat not in found:
            rep.fail("definitions/", "缺少门类定义文件 %s.json" % cat)
    for cat in found:
        if cat not in CATEGORIES:
            rep.fail("definitions/", "多出未知门类文件 %s.json" % cat)

    total_metrics = 0
    unimplemented = []
    for cat in found:
        if cat not in CATEGORIES:
            continue
        path = os.path.join(DEFS, "%s.json" % cat)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except ValueError as exc:
            rep.fail("%s.json" % cat, "JSON 解析失败: %s" % exc)
            continue
        check_structure(cat, doc, rep)
        check_against_registry(cat, doc, registry, rep)
        check_threshold_code(cat, doc, rep)
        if cat in md_names and doc.get("name") != md_names[cat]:
            rep.fail("%s.json" % cat, "name=%r 与 SCHEMA_v0.1.md §0 的 %r 不一致"
                     % (doc.get("name"), md_names[cat]))
        total_metrics += len(doc.get("metrics", []))
        for m in doc.get("metrics", []):
            if m.get("implemented") is False:
                unimplemented.append("%s.%s" % (cat, m.get("id")))

    print("=" * 72)
    print("指标定义校验  —  %d 个门类 / %d 个指标" % (len(found), total_metrics))
    print("=" * 72)
    for line in rep.fails:
        print("  FAIL  %s" % line)
    for line in rep.warns:
        print("  WARN  %s" % line)
    if not rep.fails and not rep.warns:
        print("  全部通过")

    print("")
    print("未实现指标 %d 个（这不是错误，是待办清单）：" % len(unimplemented))
    for x in unimplemented:
        print("    - %s" % x)

    bad = len(rep.fails) + (len(rep.warns) if args.strict else 0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
