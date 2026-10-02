#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 op-ota 数据集补 latest-update.txt
===================================
有些机型在官方 v3 协议下查不到（返回 2004 artifactV1Result is empty），
但 op-ota 通过另一套端点拿到了它们的固件直链，这些链接已并入 links/。
本脚本据此补出 latest-update.txt，并在文件里明确标注数据来源，
避免与 v3 官方查询产出的文件混淆。

用法:
  python3 scripts/fill_latest_from_opota.py --dry-run
  python3 scripts/fill_latest_from_opota.py
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import update as U  # noqa: E402


def ver_sort_key(ver):
    """CPH2573_16.0.10.501(EX01) -> (16,0,10,501)；_11_A.57 -> (11, A, 57)"""
    nums = [int(x) for x in re.findall(r"\d+", ver.split("(")[0])]
    return nums or [0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-missing", action="store_true", default=True,
                    help="只补还没有 latest-update.txt 的机型（默认）")
    opts = ap.parse_args()

    meta_path = os.path.join(ROOT, "config", "opota_meta.json")
    if not os.path.isfile(meta_path):
        sys.exit("缺少 config/opota_meta.json，先跑 scripts/import_opota.py")
    meta = json.load(open(meta_path, encoding="utf-8"))

    filled = skipped_nofile = skipped_has = 0
    for code, versions in sorted(meta.items()):
        lp = U.latest_path(code)
        if opts.only_missing and os.path.isfile(lp):
            skipped_has += 1
            continue

        # 挑版本号最大的那条，且 links 文件确实存在
        best = None
        for ver, info in versions.items():
            lf = U.links_path(code, ver)
            if not os.path.isfile(lf):
                continue
            if best is None or ver_sort_key(ver) > ver_sort_key(best[0]):
                best = (ver, info, lf)
        if best is None:
            skipped_nofile += 1
            continue

        ver, info, lf = best
        url = open(lf, encoding="utf-8").read().strip()
        lines = [
            f"本地更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"查询地区: {(info.get('region') or '').upper()}",
            f"最新 OTA 版本: {ver}",
            f"版本名称: {ver}",
            f"Android 版本: ",
            f"ColorOS 版本: {ver}",
            f"安全补丁: ",
            f"发布时间: ",
            f"ROM 下载链接: {url}",
            "",
            f"数据来源: {info.get('source','op-ota')}（官方 v3 协议对该机型返回 2004，",
            f"          本文件由 op-ota 数据集补出，非 v3 查询产物）",
            f"包大小: {info.get('size','')}",
            f"MD5: {info.get('md5','')}",
            "",
        ]
        if not opts.dry_run:
            os.makedirs(os.path.dirname(lp), exist_ok=True)
            with open(lp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        filled += 1

    print(f"补出 latest-update.txt: {filled}"
          + ("（试运行）" if opts.dry_run else ""))
    print(f"已有 latest 跳过: {skipped_has}")
    print(f"无对应 links 文件跳过: {skipped_nofile}")


if __name__ == "__main__":
    main()
