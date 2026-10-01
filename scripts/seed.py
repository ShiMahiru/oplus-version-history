#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oplus-version-history 种子导入
==============================
把已验证的种子资产导入仓库，作为首次提交基线：
  1) oplusrom_links.json  —— 43 机型 / 393 条官方 gate 链接（实测存活）+ 版本史
  2) devices.json         —— 356 机型最新官方 gate 链接 + 内置版本史

种子文件通过环境变量指定（默认在仓库 seeds/ 目录下查找）：

    SEED_OPLUSROM=/path/to/oplusrom_links.json \
    SEED_DEVICES=/path/to/devices.json \
    python3 scripts/seed.py

缺省路径: seeds/oplusrom_links.json / seeds/devices.json
两个种子都可缺失——缺失的源直接跳过，已入库的数据不受影响。

只做合并，不覆盖脚本已产出的文件（比 update.py 生成的内容优先级低）。
运行: python3 scripts/seed.py
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OJSON = os.environ.get("SEED_OPLUSROM", os.path.join(ROOT, "seeds", "oplusrom_links.json"))
DJSON = os.environ.get("SEED_DEVICES", os.path.join(ROOT, "seeds", "devices.json"))


def link_of(model, ver, url):
    safe = re.sub(r'[\\/:*?"<>|]', "_", ver)
    p = os.path.join(ROOT, "links", model, f"{safe}.txt")
    if os.path.isfile(p):
        return False
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(url.strip() + "\n")
    return True


def hist_add(model, fp, ver):
    p = os.path.join(ROOT, "models", model, "ota-version.txt")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.isfile(p):
        existing = open(p, encoding="utf-8").read()
        if fp in existing:
            return False
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{fp}  # ColorOS: {ver}\n" if ver else f"{fp}\n")
    return True


def main():
    n_link = n_hist = n_ver = 0

    # 1) oplusrom 链接库（种子缺失则跳过）
    if not os.path.isfile(OJSON):
        print(f"跳过 oplusrom 种子（未找到 {OJSON}）")
        idx = {"models": {}}
    else:
        idx = json.load(open(OJSON, encoding="utf-8"))
    for pn, m in idx["models"].items():
        for v in m["versions"]:
            ver = v.get("v")
            fp = v.get("fp", "")
            u = v.get("u")
            if u and ver:
                if link_of(pn, ver, u):
                    n_link += 1
            d = v.get("d")
            if fp:
                # 版本史：指纹 + 版本名（+日期不进版本史文件，日期在 versions 归档由 update 维护）
                if hist_add(pn, fp, ver):
                    n_hist += 1
            if ver:
                n_ver += 1
    print(f"oplusrom 源: 新链接 {n_link}  版本史行 {n_hist}  版本条目 {n_ver}")

    # 2) RomCloud devices.json（356 机型；种子缺失则跳过）
    if not os.path.isfile(DJSON):
        print(f"跳过 devices 种子（未找到 {DJSON}）")
        devs = []
    else:
        devs = json.load(open(DJSON, encoding="utf-8"))["devices"]
    n2l = n2h = 0
    for d in devs:
        code = d["code"]
        ota = d.get("otaUrl") or ""
        latest = d.get("latest") or ""
        hist = d.get("historyJson") or ""
        if ota and latest:
            if link_of(code, latest, ota):
                n2l += 1
        try:
            entries = json.loads(hist)
        except Exception:
            entries = []
        for e in entries:
            fp = e.get("fp", "")
            ver = e.get("v", "")
            if fp and hist_add(code, fp, ver):
                n2h += 1
    print(f"devices 源: 新链接 {n2l}  版本史行 {n2h}")

    # 3) 汇总
    links_total = 0
    for root, _, files in os.walk(os.path.join(ROOT, "links")):
        links_total += sum(1 for f in files if f.endswith(".txt"))
    hist_total = 0
    for root, _, files in os.walk(os.path.join(ROOT, "models")):
        for f in files:
            if f == "ota-version.txt":
                hist_total += sum(1 for ln in open(os.path.join(root, f), encoding="utf-8") if ln.strip())
    print(f"汇总: links 共 {links_total} 条, 版本史共 {hist_total} 行")


if __name__ == "__main__":
    main()