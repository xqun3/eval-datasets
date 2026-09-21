#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重抽 IFEval 样本：只要**可机检约束 >= 2 条**的题。

起因：第一批直接取前 3 条，其中 G4-FORMAT_CONSTRAINED_WRITING-0002 只剩一条
可机检约束（no_commas），于是一个 2 个字符的回答 "ok" 也能拿 1.0 ——
这种题在评测里不产生任何区分度，等于白送分。

这里翻若干页原始数据，用 adapter 自己的 translate() 判断每条题能落地几个约束，
挑约束最多的 3 条写回 raw/ifeval.jsonl。用 adapter 的 translate 而不是直接数
instruction_id_list，是因为有些约束（比如「用某某语言回答」）翻译不出来，
数原始 id 会高估。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "benchmark_v0.2", "adapter"))

from adapter.adapters.ifeval import translate      # noqa: E402

API = "https://datasets-server.huggingface.co/rows"
REPO, CONFIG, SPLIT = "google/IFEval", "default", "train"
PAGES, PAGE = 4, 50          # 看前 200 条
WANT, MIN_CONSTRAINTS = 3, 2


def fetch(offset, length, retries=4):
    q = urllib.parse.urlencode({"dataset": REPO, "config": CONFIG,
                                "split": SPLIT, "offset": offset, "length": length})
    for i in range(retries):
        try:
            with urllib.request.urlopen("%s?%s" % (API, q), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))["rows"]
        except Exception as e:                      # 502/429 都会偶发，退避重试
            if i == retries - 1:
                raise
            print("  retry %d (%s)" % (i + 1, e))
            time.sleep(2 ** i * 1.5)
    return []


def n_checkable(rec):
    ids = [str(x) for x in (rec.get("instruction_id_list") or [])]
    kws = list(rec.get("kwargs") or [])
    while len(kws) < len(ids):
        kws.append({})
    return sum(1 for i, k in zip(ids, kws) if translate(i, k))


def main():
    pool = []
    for p in range(PAGES):
        rows = fetch(p * PAGE, PAGE)
        for r in rows:
            rec = r["row"]
            n = n_checkable(rec)
            if n >= MIN_CONSTRAINTS:
                pool.append((n, rec))
        print("page %d: 累计候选 %d" % (p, len(pool)))
        if len(pool) >= 20:
            break
        time.sleep(1.5)

    pool.sort(key=lambda t: -t[0])
    picked = [rec for _n, rec in pool[:WANT]]
    if len(picked) < WANT:
        print("! 只找到 %d 条满足条件的样本" % len(picked))
        return 1

    dst = os.path.join(ROOT, "G4_writing", "raw", "ifeval.jsonl")
    with open(dst, "w", encoding="utf-8") as fh:
        for rec in picked:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    for n, rec in pool[:WANT]:
        print("  %d 条可机检约束: %s" % (n, rec.get("instruction_id_list")))
    print("已写入 %s（%d 条）" % (dst, len(picked)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
