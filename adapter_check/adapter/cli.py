"""Command line: ``python3 -m adapter <convert|list|validate|stats|check>``."""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .base import AdapterConfig
from .registry import adapter_items, checker_items, get_adapter, get_checker
from .schema import TaskInstance, validate_instance
from .utils.io import read_json, read_jsonl, write_json, write_jsonl


# --------------------------------------------------------------------------
def cmd_list(args) -> int:
    rows = []
    for name, cls in adapter_items():
        rows.append((name, cls.category, cls.gold_type, cls.checker,
                     "%s@%s" % (cls.dataset, cls.version), cls.commercial_use))
    w = [max(len(r[i]) for r in rows + [("adapter", "cat", "gold.type", "checker",
                                         "dataset@version", "commercial")]) for i in range(6)]
    hdr = ("adapter", "cat", "gold.type", "checker", "dataset@version", "commercial")
    print("ADAPTERS (%d)" % len(rows))
    print("  " + "  ".join(h.ljust(w[i]) for i, h in enumerate(hdr)))
    print("  " + "  ".join("-" * w[i] for i in range(6)))
    for r in rows:
        print("  " + "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))

    crows = [(cid, spec.layer, ",".join(spec.gold_types), spec.description)
             for cid, spec in checker_items()]
    cw = [max(len(str(r[i])) for r in crows + [("checker", "layer", "gold_types", "")])
          for i in range(3)]
    print("\nCHECKERS (%d)" % len(crows))
    print("  " + "  ".join(h.ljust(cw[i]) for i, h in enumerate(("checker", "layer", "gold_types")))
          + "  description")
    print("  " + "  ".join("-" * cw[i] for i in range(3)) + "  " + "-" * 11)
    for cid, layer, gts, desc in crows:
        print("  %s  %s  %s  %s" % (cid.ljust(cw[0]), layer.ljust(cw[1]), gts.ljust(cw[2]), desc))
    return 0


# --------------------------------------------------------------------------
def _load_aux(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise SystemExit("--aux must contain a JSON object")
    return data


def cmd_convert(args) -> int:
    cls = get_adapter(args.adapter)
    cfg = AdapterConfig(
        split=args.split,
        lang=args.lang,
        seq_start=args.seq_start,
        limit=args.limit,
        extra_must_not=list(args.must_not or []),
        difficulty_override=args.difficulty,
        aux=_load_aux(args.aux),
        options=json.loads(args.options) if args.options else {},
        strict=not args.lenient,
    )
    if not cfg.aux and getattr(cls, "default_aux", None):
        cfg.aux = _load_aux(cls.default_aux)
    if not cfg.aux:
        guess = os.path.join(os.path.dirname(__file__), "fixtures",
                             "%s_aux.json" % args.adapter)
        if os.path.exists(guess) and os.path.abspath(args.infile).startswith(
                os.path.join(os.path.dirname(__file__), "fixtures")):
            cfg.aux = _load_aux(guess)

    adapter = cls(cfg)
    rows: List[Dict[str, Any]] = []
    for inst in adapter.run(read_jsonl(args.infile), cfg):
        rows.append(inst.to_dict())

    n = write_jsonl(args.outfile, rows)
    manifest_path = args.manifest or (os.path.splitext(args.outfile)[0] + ".manifest.json")
    write_json(manifest_path, adapter.manifest(cfg))

    s = adapter.stats
    print("adapter   : %s (%s)" % (args.adapter, adapter.source()))
    print("read      : %d" % s.read)
    print("converted : %d" % s.converted)
    print("filtered  : %d" % s.filtered)
    print("errored   : %d" % s.errored)
    for e in s.errors[:5]:
        print("  ! %s" % e)
    print("written   : %d -> %s" % (n, args.outfile))
    print("manifest  : %s" % manifest_path)
    return 0 if s.errored == 0 else 1


# --------------------------------------------------------------------------
def cmd_validate(args) -> int:
    total, bad = 0, 0
    ids: Dict[str, int] = {}
    for i, row in enumerate(read_jsonl(args.infile), 1):
        total += 1
        errs = validate_instance(row)
        iid = row.get("id")
        if isinstance(iid, str):
            if iid in ids:
                errs.append("duplicate id (first seen on line %d)" % ids[iid])
            else:
                ids[iid] = i
        if errs:
            bad += 1
            print("line %d [%s]" % (i, iid))
            for e in errs:
                print("   - %s" % e)
            if bad >= args.max_errors:
                print("... stopping after %d bad rows" % bad)
                break
    print("validated : %d rows, %d invalid" % (total, bad))
    print("RESULT    : %s" % ("OK" if bad == 0 else "FAILED"))
    return 0 if bad == 0 else 1


# --------------------------------------------------------------------------
def cmd_stats(args) -> int:
    counters = {k: collections.Counter() for k in
                ("category", "difficulty", "lang", "split", "gold_type", "checker",
                 "source", "subtype")}
    total = 0
    must_not_total = 0
    for row in read_jsonl(args.infile):
        total += 1
        counters["category"][row.get("category")] += 1
        counters["difficulty"][row.get("difficulty")] += 1
        counters["lang"][row.get("lang")] += 1
        counters["split"][row.get("split")] += 1
        counters["gold_type"][(row.get("gold") or {}).get("type")] += 1
        counters["checker"][row.get("checker")] += 1
        counters["source"][row.get("source")] += 1
        counters["subtype"][row.get("subtype")] += 1
        must_not_total += len(row.get("must_not") or [])

    print("instances : %d" % total)
    for key in ("category", "subtype", "difficulty", "lang", "split", "gold_type",
                "checker", "source"):
        c = counters[key]
        parts = ", ".join("%s=%d" % (k, v) for k, v in sorted(c.items(), key=lambda x: str(x[0])))
        print("%-10s: %s" % (key, parts))
    if total:
        d = counters["difficulty"]
        ratio = ":".join("%.1f" % (10.0 * d.get(k, 0) / total) for k in ("L1", "L2", "L3"))
        print("%-10s: %s  (target 3:5:2)" % ("L1:L2:L3", ratio))
        print("%-10s: %.2f" % ("must_not/inst", must_not_total / float(total)))
    return 0


# --------------------------------------------------------------------------
def cmd_check(args) -> int:
    """Score responses offline: --in instances.jsonl --responses responses.jsonl."""
    from .checkers import run_check

    insts = {r["id"]: TaskInstance.from_dict(r) for r in read_jsonl(args.infile)}
    results = []
    agg = collections.Counter()
    for resp in read_jsonl(args.responses):
        iid = resp.get("id")
        inst = insts.get(iid)
        if inst is None:
            print("! no instance for response id=%r" % iid)
            continue
        res = run_check(inst, resp, env=None)
        agg["n"] += 1
        agg["passed"] += 1 if res["passed"] else 0
        agg["violations"] += len(res["violations"])
        results.append({"id": iid, "checker": inst.checker, "score": res["score"],
                        "passed": res["passed"], "layer": res["layer"],
                        "violations": res["violations"],
                        "sub_metrics": res["sub_metrics"]})
        print("%-28s %-20s score=%.3f passed=%s %s"
              % (iid, inst.checker, res["score"], res["passed"],
                 ("VIOLATIONS: " + "; ".join(res["violations"])) if res["violations"] else ""))
    if args.out:
        write_jsonl(args.out, results)
    print("checked   : %d, passed %d, violations %d"
          % (agg["n"], agg["passed"], agg["violations"]))
    return 0


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m adapter",
                                description="benchmark v0.1 adapter layer")
    p.add_argument("--version", action="version", version="adapter %s" % __version__)
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("list", help="list registered adapters and checkers")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("convert", help="convert a raw dataset file to TaskInstance JSONL")
    sp.add_argument("--adapter", required=True)
    sp.add_argument("--in", dest="infile", required=True)
    sp.add_argument("--out", dest="outfile", required=True)
    sp.add_argument("--aux", help="JSON file with db catalog / corpus / qrels")
    sp.add_argument("--manifest", help="sidecar manifest path (default: <out>.manifest.json)")
    sp.add_argument("--split", default="dev", choices=("dev", "test", "canary"))
    sp.add_argument("--lang", default=None, choices=("zh", "en", "mixed"))
    sp.add_argument("--difficulty", default=None, choices=("L1", "L2", "L3"))
    sp.add_argument("--seq-start", type=int, default=1)
    sp.add_argument("--limit", type=int, default=None)
    sp.add_argument("--must-not", action="append", default=[])
    sp.add_argument("--options", help="JSON dict of adapter-specific options")
    sp.add_argument("--lenient", action="store_true", help="skip bad rows instead of raising")
    sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("validate", help="schema-validate a TaskInstance JSONL")
    sp.add_argument("--in", dest="infile", required=True)
    sp.add_argument("--max-errors", type=int, default=20)
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("stats", help="distribution report over a TaskInstance JSONL")
    sp.add_argument("--in", dest="infile", required=True)
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("check", help="run checkers over (instances, responses)")
    sp.add_argument("--in", dest="infile", required=True)
    sp.add_argument("--responses", required=True)
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_check)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except KeyError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
