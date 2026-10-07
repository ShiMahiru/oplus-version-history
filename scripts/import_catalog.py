#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导入目录源（catalog-source）欧加版本目录 → 目录条目（链接待补）。

目录源数据库：gate 链接存档（2403 版本），API 只吐版本名
不吐链接（链接字段全空，下载走它自己后端的 OTA 实时查询）。

导入策略：
  - 版本存在于目录源、但本地 links/ 没有链接 → 生成目录条目
    （links/{code}/{code}_{ver}() 目录文件，内容空串 + 注释标记）
  - 已有链接的版本不动（links 里的 gate/直链 100% 实测存活，价值更高）
运行: python3 scripts/import_lian_catalog.py [--dry-run]
"""
import argparse, json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 上一级 = 仓库根
CATALOG = os.path.join(ROOT, "config", "lian_versions.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    theirs = json.load(open(CATALOG))
    print(f"目录源: {len(theirs)} 机型 / {sum(len(v) for v in theirs.values())} 版本")

    added = 0
    skipped_have = 0
    skipped_marked = 0
    for code, versions in sorted(theirs.items()):
        links_dir = os.path.join(ROOT, "links", code)
        os.makedirs(links_dir, exist_ok=True)
        have = set()
        for fn in os.listdir(links_dir):
            if fn.endswith(".txt"):
                have.add(fn[:-4])
        for ver in sorted(versions):
            # 版本名规范化：空格 → 下划线（'12.1 A.07' → '12.1_A.07'），与站点 URL 编码兼容
            ver_norm = ver.replace(" ", "_")
            fname = f"{code}_{ver_norm}.txt"
            if fname[:-4] in have:
                skipped_have += 1
                continue
            if args.dry_run:
                added += 1
                continue
            # 写空链接文件（目录条目标记：内容为空 = 待补链接；normalize/网站管线识别空串）
            out = os.path.join(links_dir, fname)
            if not os.path.exists(out):
                with open(out, "w", encoding="utf-8") as f:
                    f.write("")  # 空内容 = 目录条目（待补链接）
                added += 1
            else:
                skipped_marked += 1
    print(f"新增目录条目: {added}")
    print(f"（已有链接跳过 {skipped_have}，已标记跳过 {skipped_marked}）")


if __name__ == "__main__":
    main()
