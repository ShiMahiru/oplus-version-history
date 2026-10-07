#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
指纹挖掘：枚举 {code}_11.{letter}.{nn}_{nn*10} 指纹前缀，经 descriptionInfo
验证存在性，补全历史版本的 changelog + ota-version。断点续传。
"""
import json, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 的上一级 = 仓库根
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from update import changelog_query, REGIONS

LETTERS = ["A", "C", "F", "H", "J"]
import os as _os
_shard = _os.environ.get("MINE_SHARD", "")
PROGRESS = os.path.join(ROOT, "config", f"mine_progress{_shard}.json") if _shard else os.path.join(ROOT, "config", "mine_progress.json")


def load_progress():
    if os.path.exists(PROGRESS):
        return json.load(open(PROGRESS))
    return {"done": []}


def save_progress(p):
    json.dump(p, open(PROGRESS, "w"), ensure_ascii=False)


def mine_model(code, site_versions, dry=False):
    """枚举一个机型的指纹空间，返回新增 (指纹前缀, 版本名) 列表"""
    ver_file = os.path.join(ROOT, "models", code, "ota-version.txt")
    known_versions = set()
    if os.path.isfile(ver_file):
        for line in open(ver_file, encoding="utf-8"):
            mm = re.match(r"^(\S+)\s+#\s*(?:ColorOS:\s*)?(.+)", line.strip())
            if mm:
                known_versions.add(mm.group(2))
    known_fps = set()
    if os.path.isfile(ver_file):
        for line in open(ver_file, encoding="utf-8"):
            fp = line.strip().split()[0] if line.strip() else ""
            if fp:
                prefix = fp.rsplit("_", 1)[0] if fp.rsplit("_", 1)[-1].isdigit() else fp
                known_fps.add(prefix)

    new_hits = []
    # 智能枚举：从目录缺口版本的 ColorOS 大版本 → 对应分支字母（实测映射），
    # 只枚举相关分支，序号 1-99 全扫但限速更快（0.05s，官方 descriptionInfo 限流松）
    VER_BRANCH = {"13": ["A", "C", "F"], "14": ["A", "C", "F", "H"],
                  "15": ["A", "C", "F", "H"], "16": ["A", "C", "F", "H", "J"],
                  "17": ["A", "C"], "11": ["A", "C"], "12": ["A", "C", "F"]}
    # 该机型的缺口版本 ColorOS 大版本集合
    need_bigs = set()
    for v in site_versions if isinstance(site_versions, dict) else []:
        mm2 = re.match(r"ColorOS\s*(\d+)", str(v))
        if mm2: need_bigs.add(mm2.group(1))
    branches = sorted(set(b for big in need_bigs for b in VER_BRANCH.get(big, LETTERS))) or LETTERS
    for letter in branches:
        for nn in range(1, 100):
            fp = f"{code}_11.{letter}.{nn:02d}_{nn*10:04d}"
            if fp in known_fps:
                continue
            if dry:
                continue
            r = changelog_query(code, fp, "cn")
            if r and r[0]:
                vn = r[0]
                # 跨机型撞车校验：versionName 必须含本机型 code
                if code not in vn:
                    continue
                # 只入库目录源有而本地没有的版本
                if vn not in known_versions:
                    new_hits.append((fp, vn, r[1]))
                    known_versions.add(vn)
                    known_fps.add(fp)
                    print(f"    命中 {fp} → {vn}", flush=True)
            else:
                # 也记录"已挖过无结果"避免重复
                known_fps.add(fp)
            time.sleep(0.05)
    return new_hits


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="最多挖几个机型（调试）")
    ap.add_argument("--shard", type=int, default=0, help="分片序号")
    ap.add_argument("--total", type=int, default=1, help="总分片数")
    args = ap.parse_args()

    missing_path = os.path.join(ROOT, "config", "missing_from_lian.json")
    missing = json.load(open(missing_path))
    targets = sorted(missing.keys())
    # 分片：按序取每隔 total 的机型，均衡分布
    if args.total > 1:
        targets = targets[args.shard::args.total]
    if args.model:
        targets = [args.model]
    if args.limit:
        targets = targets[:args.limit]

    prog = load_progress()
    print(f"待挖机型: {len(targets)}（已完成 {len(prog['done'])}）")

    for i, code in enumerate(targets):
        if code in prog["done"]:
            continue
        print(f"[{i+1}/{len(targets)}] {code} 枚举中...", flush=True)
        # 目录缺口版本的 ColorOS 大版本集合（用于智能分支选择）
        site_versions = missing.get(code, [])
        hits = mine_model(code, site_versions, dry=args.dry)
        # 入库
        ver_file = os.path.join(ROOT, "models", code, "ota-version.txt")
        cl_dir = os.path.join(ROOT, "models", code, "changelog")
        os.makedirs(cl_dir, exist_ok=True)
        existing_lines = set()
        if os.path.isfile(ver_file):
            existing_lines = {l.strip() for l in open(ver_file, encoding="utf-8") if l.strip()}
        added = 0
        with open(ver_file, "a", encoding="utf-8") as f:
            for fp, vn, md in hits:
                line = f"{fp}_197001010000  # ColorOS: {vn}"
                # 时间戳用挖掘占位（真实时间戳不可知）——normalize 会保留
                if fp not in {l.split()[0].rsplit('_',1)[0] for l in existing_lines}:
                    f.write(line + "\n")
                    existing_lines.add(line)
                cl_path = os.path.join(cl_dir, fp + ".md")
                if not os.path.exists(cl_path) and md:
                    with open(cl_path, "w", encoding="utf-8") as cf:
                        cf.write(md)
                    added += 1
        prog["done"].append(code)
        save_progress(prog)
        print(f"  完成：命中 {len(hits)}，入库 {added}")
        time.sleep(1)


if __name__ == "__main__":
    main()
