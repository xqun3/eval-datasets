#!/usr/bin/env python3
"""为 G2 构建一个自包含的检索评测池（queries + corpus + qrels）。

设计要点（踩过坑后的版本）：

BEIR-SciFact 语料 5,183 篇，`_id` 是不连续的大整数（如 31715818），
**不能**按 offset 顺序扫描去找指定文档 —— 实测扫了 2,200 篇一个正例都没碰到，
还会触发 429 限流。`/filter` 接口在这个语料上也会超时。

所以这里反着来：**先固定一页语料，再从 qrels 里挑出引用了这页文档的 query**。
qrels 只有几百行，可以整表拉下来。这样一定能凑出正例齐全的 pool。

pool = 这些 query 的全部正例 + 同页其余文档当负例。

用法: python3 fetch_g2_pool.py [--queries 3] [--corpus-page 0] [--pool-size 20]
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request

API = "https://datasets-server.huggingface.co"
PAGE = 100
SLEEP = 1.5                      # 对 datasets-server 客气一点，避免 429
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "G2_retrieval", "raw")


def http_json(path, timeout=60, attempts=5, **params):
    url = "%s/%s?%s" % (API, path, urllib.parse.urlencode(params))
    last = None
    for k in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "model-eval/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except Exception as exc:                                   # noqa: BLE001
            last = exc
            time.sleep(4 + 4 * k)                                  # 429 要退避久一点
    raise RuntimeError("giving up on %s: %s" % (url, last))


def page_rows(dataset, config, split, offset, length=PAGE):
    data = http_json("rows", dataset=dataset, config=config, split=split,
                     offset=offset, length=length)
    time.sleep(SLEEP)
    return [r["row"] for r in data.get("rows", [])], data.get("num_rows_total", 0)


def fetch_all(dataset, config, split, cap=2000):
    rows, off = [], 0
    while off < cap:
        chunk, total = page_rows(dataset, config, split, off)
        if not chunk:
            break
        rows.extend(chunk)
        off += PAGE
        if off >= total:
            break
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=int, default=3, help="选几个 query 进池")
    ap.add_argument("--corpus-page", type=int, default=0, help="用第几页语料（每页 100 篇）")
    ap.add_argument("--pool-size", type=int, default=20, help="pool 里总共放多少篇文档")
    args = ap.parse_args()

    print("[1/4] 整表拉 qrels（几百行，很快）...")
    qrels_rows = fetch_all("BeIR/scifact-qrels", "default", "test")
    print("      qrels %d 行" % len(qrels_rows))

    print("[2/4] 取第 %d 页语料作为候选池 ..." % args.corpus_page)
    corpus_rows, ctotal = page_rows("BeIR/scifact", "corpus", "corpus",
                                    args.corpus_page * PAGE)
    have = {str(r["_id"]): {"title": r.get("title") or "", "text": r.get("text") or ""}
            for r in corpus_rows}
    print("      语料共 %s 篇，本页拿到 %d 篇" % (ctotal, len(have)))

    print("[3/4] 从 qrels 里挑出「正例全部落在本页」的 query ...")
    by_q = {}
    for r in qrels_rows:
        if int(r["score"]) > 0:
            by_q.setdefault(str(r["query-id"]), {})[str(r["corpus-id"])] = int(r["score"])
    eligible = {q: m for q, m in by_q.items() if set(m).issubset(have)}
    print("      qrels 覆盖 %d 个 query，其中 %d 个的正例全在本页" % (len(by_q), len(eligible)))
    if len(eligible) < args.queries:
        raise SystemExit("本页可用 query 不足，换一页试试：--corpus-page %d"
                         % (args.corpus_page + 1))
    chosen = dict(list(eligible.items())[: args.queries])
    positives = {d for m in chosen.values() for d in m}
    print("      选中 query %s，正例 %d 篇" % (list(chosen), len(positives)))

    print("[4/4] 组装 pool 并落盘 ...")
    want_q = set(chosen)
    queries, off = {}, 0
    while want_q and off < 2000:
        rows, _ = page_rows("BeIR/scifact", "queries", "queries", off)
        if not rows:
            break
        for r in rows:
            qid = str(r["_id"])
            if qid in want_q:
                queries[qid] = r["text"]
                want_q.discard(qid)
        off += PAGE

    pool = {d: have[d] for d in positives}
    for did, doc in have.items():                 # 其余当硬负例，补到 pool-size
        if len(pool) >= args.pool_size:
            break
        pool.setdefault(did, doc)

    os.makedirs(OUT_DIR, exist_ok=True)
    qpath = os.path.join(OUT_DIR, "beir_scifact_queries.jsonl")
    with open(qpath, "w", encoding="utf-8") as fh:
        for qid in chosen:
            fh.write(json.dumps({"_id": qid, "text": queries.get(qid, "")},
                                ensure_ascii=False) + "\n")
    apath = os.path.join(OUT_DIR, "beir_scifact_aux.json")
    with open(apath, "w", encoding="utf-8") as fh:
        json.dump({"corpus": pool, "qrels": chosen}, fh, ensure_ascii=False, indent=2)

    print("      queries: %d 条 -> %s" % (len(chosen), os.path.basename(qpath)))
    print("      pool   : %d 篇（%d 正例 + %d 负例）-> %s"
          % (len(pool), len(positives), len(pool) - len(positives), os.path.basename(apath)))
    for qid, m in chosen.items():
        print("        q%s: %.62s  正例=%s" % (qid, queries.get(qid, ""), list(m)))
    print("\n注意：Recall@k 是这个 %d 篇 pool 内的值，绝对值高于全量 5,183 篇语料，"
          "\n      不能与官方 leaderboard 数字直接比较。" % len(pool))


if __name__ == "__main__":
    main()
