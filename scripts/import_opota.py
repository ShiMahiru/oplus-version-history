#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并入 jeck24India/op-ota 的 oneplus_ota_final.json
================================================
该数据集 1627 条，由真实设备/协议查询产出，字段：
  model / version / codename / rom_type / size / md5 / url / region / working_model_string

其中 url 是 gauss CDN 直链（含 remove-<token> 段），version 形如 CPH2477_11_A.57。
本脚本只补写我们尚缺的 links/<code>/<ver>.txt，并把 md5/size 记入 meta，
不改动 ota-version.txt（那是官方 v3 查询产出的指纹行，格式不同）。

用法:
  python3 scripts/import_opota.py --src /tmp/repo-scan/op-ota/oneplus_ota_final.json
  python3 scripts/import_opota.py --src ... --dry-run
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import update as U  # noqa: E402

# 版本名里的 code 前缀可能与目录 code 不同（CPH2477_11_A.57 的 code 是 CPH2477）
VER_RE = re.compile(r"^([A-Z]{2,4}\d{3,5}[A-Z]{0,4})_(\d+\.\d+_[A-Z]\.\d+)$")


def ver_filename(ver, code):
    """把 CPH2477_11_A.57 规范成 links 文件名用的形式。"""
    v = ver.strip()
    if v.startswith(code):
        return v
    m = VER_RE.match(v)
    return v if not m else v


def brand_of(name):
    n = (name or "").lower()
    if "oneplus" in n:
        return "oneplus"
    if "realme" in n:
        return "realme"
    if "oppo" in n:
        return "oppo"
    return "unknown"


def merge_models(new_entries, dry_run):
    """把 op-ota 里我们清单外的机型补进 config/models.json。"""
    mp = os.path.join(ROOT, "config", "models.json")
    doc = json.load(open(mp, encoding="utf-8"))
    have = {m["code"] for m in doc["models"]}
    added = []
    for code, (name, region) in sorted(new_entries.items()):
        if code in have:
            continue
        added.append({
            "code": code, "name": name or code,
            "brand": brand_of(name), "region": region.upper(),
            "_source": "jeck24India/op-ota",
        })
    if not dry_run and added:
        doc["models"].extend(added)
        doc["models"].sort(key=lambda m: m["code"])
        doc["count"] = len(doc["models"])
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="oneplus_ota_final.json 路径")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-new-models", action="store_true",
                    help="只并入链接，不扩充机型清单")
    opts = ap.parse_args()

    data = json.load(open(opts.src, encoding="utf-8"))
    print(f"读入 {len(data)} 条记录")

    known = {m["code"] for m in U.MODELS}
    print(f"本地已知机型 {len(known)} 个")

    # 先收集清单外机型（code -> (name, region)），region 取该机型出现次数最多的
    outside = {}
    reg_votes = {}
    for e in data:
        code = (e.get("codename") or "").upper().strip()
        if not code or code in known:
            continue
        outside.setdefault(code, e.get("model") or code)
        reg_votes.setdefault(code, Counter())[(e.get("region") or "gl").lower()] += 1

    if outside and not opts.no_new_models:
        new_models = {c: (outside[c], reg_votes[c].most_common(1)[0][0]) for c in outside}
        added = merge_models(new_models, opts.dry_run)
        print(f"清单外机型 {len(outside)} 个 -> 补入 {len(added)} 个"
              + ("（试运行）" if opts.dry_run else ""))
        known |= set(new_models)

    stats = Counter()
    meta_out = {}
    added_models = set()

    for e in data:
        code = (e.get("codename") or "").upper().strip()
        ver = (e.get("version") or "").strip()
        url = (e.get("url") or "").strip()
        if not code or not ver or not url:
            stats["跳过_字段缺失"] += 1
            continue

        if code not in known:
            stats["跳过_机型不在清单"] += 1
            continue

        lp = U.links_path(code, ver)
        if os.path.isfile(lp):
            stats["跳过_已有链接"] += 1
        else:
            if not opts.dry_run:
                U.write_link(code, ver, url)
            stats["新增链接"] += 1
            added_models.add(code)

        meta_out.setdefault(code, {})[ver] = {
            "md5": e.get("md5") or "",
            "size": e.get("size") or "",
            "region": (e.get("region") or "").lower(),
            "working_model_string": e.get("working_model_string") or "",
            "source": "jeck24India/op-ota",
        }
        stats["记录元数据"] += 1

    if not opts.dry_run and meta_out:
        mp = os.path.join(ROOT, "config", "opota_meta.json")
        old = {}
        if os.path.isfile(mp):
            old = json.load(open(mp, encoding="utf-8"))
        for code, vs in meta_out.items():
            old.setdefault(code, {}).update(vs)
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(old, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"元数据写入 {mp}（{len(old)} 个机型）")

    print()
    for k, v in stats.most_common():
        print(f"  {k}: {v}")
    print(f"\n涉及机型 {len(added_models)} 个")


if __name__ == "__main__":
    main()
