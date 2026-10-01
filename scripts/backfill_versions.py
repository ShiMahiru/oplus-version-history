#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史版本名反查补全（官方 descriptionInfo）
==========================================
仓库里部分早期记录只有 OTA 指纹、没有用户可见版本名，形如：

    MT2110_11.A.07_0070_202111020020

官方 changelog 接口（descriptionInfo）对**任意指纹前缀**都能返回 versionName，
用它做官方反查补全版本名，并把官方日志一并落盘。不猜测、不编造：
接口没返回就保持原样（只有指纹的行是真实记录，不是缺陷）。

运行: python3 scripts/backfill_versions.py [--dry]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

ROOT = U.ROOT
MODELS_DIR = os.path.join(ROOT, "models")
REGION_OF = {m["code"]: U.region_of(m) for m in U.MODELS}


def parse_line(ln):
    ln = ln.strip()
    if not ln:
        return None
    if "#" in ln:
        left, right = ln.split("#", 1)
        fp = left.strip()
        ver = right.strip()
        if ver.startswith("ColorOS:"):
            ver = ver[len("ColorOS:"):].strip()
        return fp, ver
    return ln, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只查询报告，不写文件")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    targets = []          # (code, path, index, fp)
    for code in sorted(os.listdir(MODELS_DIR)):
        p = os.path.join(MODELS_DIR, code, "ota-version.txt")
        if not os.path.isfile(p):
            continue
        for i, ln in enumerate(open(p, encoding="utf-8")):
            r = parse_line(ln)
            if r and r[0] and not r[1]:
                targets.append((code, p, i, r[0]))
    if args.limit:
        targets = targets[: args.limit]

    print(f"待反查 {len(targets)} 条（只有指纹、无版本名）")
    fixed = 0
    logs = 0
    for n, (code, path, idx, fp) in enumerate(targets, 1):
        region = REGION_OF.get(code, "gl")
        prefix = U.fp_prefix(fp)
        rr = U.changelog_query(code, prefix, region)
        time.sleep(U.GAP)
        if not rr:
            print(f"  {n:3d}/{len(targets)} {code:12s} {prefix:34s} ✗ 官方无返回")
            continue
        ver, md = rr
        if not ver:
            print(f"  {n:3d}/{len(targets)} {code:12s} {prefix:34s} ✗ 无版本名")
            continue
        fixed += 1
        print(f"  {n:3d}/{len(targets)} {code:12s} {prefix:34s} → {ver}")
        if args.dry:
            continue
        # 回写版本名
        lines = open(path, encoding="utf-8").read().splitlines()
        lines[idx] = f"{fp}  # ColorOS: {ver}"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        # 官方日志落盘
        if md and "官方无更新日志" not in md:
            U.write_changelog(code, fp, ver, md)
            logs += 1

    print(f"\n完成：补全版本名 {fixed}/{len(targets)}  官方日志 {logs} 条")


if __name__ == "__main__":
    main()
