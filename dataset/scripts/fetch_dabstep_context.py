#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 DABStep 的分析语料到 G6_data_analysis/context/。

## 为什么需要这一步

DABStep 在 HF datasets-server 上只暴露 `tasks` 这个 config，字段是
`question / answer / guidelines / level` —— **只有题干和答案，没有数据**。
真正要分析的 payments.csv、定义业务口径的 manual.md 等文件放在仓库的
`data/context/` 目录下，不是 dataset config，必须单独拉。

不拉的后果不是「少点上下文」，而是**这道题根本没法做**：模型只能闭卷猜一个国家码。
更隐蔽的是口径问题 —— 实测 G6-DATA_ANALYSIS-0002「top country for fraud」：

    按欺诈笔数：NL 2955 > BE 2493      -> 答 NL
    按欺诈率：  BE 10.85% > NL 9.93%   -> 答 BE   <- 金标是 "B. BE"

题干只说 "top country for fraud"，两种读法都说得通，**口径定义在 manual.md 里**。
不把 manual.md 给模型，这题就是在考猜谜。

## 为什么不把文件直接入库

payments.csv 有 22.5 MB（138236 行）。数据本身是可重新下载的，
入库的只有 `context_manifest.json`（路径 + sha256 + 字节数），
需要时跑这个脚本还原。校验和入库，保证「我们评测时用的就是这份数据」。

用法: python3 fetch_dabstep_context.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DST = os.path.join(ROOT, "G6_data_analysis", "context")
BASE = "https://huggingface.co/datasets/adyen/DABstep/resolve/main/data/context/"

FILES = [
    ("payments.csv",                "text/csv",         "交易明细，138236 行"),
    ("payments-readme.md",          "text/markdown",    "字段说明"),
    ("manual.md",                   "text/markdown",    "业务口径定义（欺诈率等指标怎么算）"),
    ("merchant_data.json",          "application/json", "商户档案"),
    ("merchant_category_codes.csv", "text/csv",         "MCC 码表"),
    ("acquirer_countries.csv",      "text/csv",         "收单行国家"),
    ("fees.json",                   "application/json", "费率规则"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已存在也重新下载")
    args = ap.parse_args()

    os.makedirs(DST, exist_ok=True)
    manifest = []
    for name, mime, desc in FILES:
        path = os.path.join(DST, name)
        if args.force or not os.path.exists(path):
            print("下载 %s ..." % name)
            urllib.request.urlretrieve(BASE + name, path)
        digest = sha256(path)
        size = os.path.getsize(path)
        manifest.append({"path": "context/%s" % name, "mime": mime,
                         "content_ref": "blob://sha256:%s" % digest,
                         "bytes": size, "desc": desc})
        print("  %-28s %9d bytes  sha256:%s..." % (name, size, digest[:16]))

    mpath = os.path.join(ROOT, "G6_data_analysis", "context_manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump({"source": "adyen/DABstep@data/context",
                   "note": "内容本身不入库，只入库校验和；build_instances.py 会把这份清单"
                           "挂到每条 G6 实例的 context.files 上",
                   "files": manifest}, fh, ensure_ascii=False, indent=2)
    print("\n清单 -> %s" % mpath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
