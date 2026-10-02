#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并三份机型清单 → config/inventory.json
=======================================
config/ 下原本散着三份清单，各自只覆盖一部分事实：

  models.json   自建机型清单（356 条）：code / name / brand / region / rui
  devices.json  设备目录（706 条设备）：最新版本 / 直链 / 大小 / MD5 / 补丁
  pn_ref.json   项目号表（356 条）：官方降级接口要的 prjNum

三者的 code 集合并不相同（models 与 devices 完全一致，pn_ref 是另一批、
以 OnePlus 早期机型为主，只有 67 个重合）。这个脚本以 code 为键取并集，
每个机型记下三件事：

  1. sources —— 它在哪几份清单里出现过（溯源，谁贡献了什么）
  2. devices —— 设备目录里的条目（同 code 多区域/多版本时全部保留）
  3. local   —— 本地实际抓到了多少（链接数 / 版本史行数 / 有没有 latest /
                changelog 份数 / 有没有降级包）

有了这张表就能一眼看出：哪些机型有清单没数据、哪些有数据没项目号、
哪些三样齐全。

用法:
    python3 scripts/build_inventory.py
"""
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config")
OUT = os.path.join(CFG, "inventory.json")

DEVICE_FIELDS = (
    "name", "region", "rui", "android", "latest", "osVersion",
    "sizeBytes", "md5", "directUrl", "securityPatch", "source",
)


def load(name):
    p = os.path.join(CFG, name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    models = load("models.json") or {}
    devices = load("devices.json") or {}
    pnref = load("pn_ref.json") or {}

    mlist = models.get("models") if isinstance(models, dict) else models
    mlist = mlist or []
    dlist = devices.get("devices") or []
    plist = pnref.get("models") or {}

    inv = {}

    def slot(code):
        return inv.setdefault(code, {
            "name": "", "brand": "", "region": "", "rui": None,
            "prj": None, "sources": [], "devices": [],
            "local": {"links": 0, "versions": 0, "latest": False,
                      "changelog": 0, "downgrade": False},
        })

    for m in mlist:
        e = slot(m["code"])
        e["name"] = m.get("name") or e["name"]
        e["brand"] = m.get("brand") or e["brand"]
        e["region"] = m.get("region") or e["region"]
        if m.get("rui") is not None:
            e["rui"] = m["rui"]
        e["sources"].append("models")

    for d in dlist:
        e = slot(d["code"])
        if d.get("name") and not e["name"]:
            e["name"] = d["name"]
        entry = {k: d[k] for k in DEVICE_FIELDS if d.get(k) not in (None, "", 0)}
        if entry:
            e["devices"].append(entry)
        if "devices" not in e["sources"]:
            e["sources"].append("devices")

    for code, v in plist.items():
        e = slot(code)
        e["prj"] = v.get("prj")
        if v.get("name") and not e["name"]:
            e["name"] = v["name"]
        e["sources"].append("pn_ref")

    # 本地实际抓到了多少
    for code, e in inv.items():
        lp = os.path.join(ROOT, "links", code)
        if os.path.isdir(lp):
            e["local"]["links"] = len([f for f in os.listdir(lp) if f.endswith(".txt")])
        hp = os.path.join(ROOT, "models", code, "ota-version.txt")
        if os.path.isfile(hp):
            with open(hp, encoding="utf-8") as f:
                e["local"]["versions"] = sum(1 for ln in f if ln.strip())
        e["local"]["latest"] = os.path.isfile(
            os.path.join(ROOT, "models", code, "latest-update.txt"))
        cp = os.path.join(ROOT, "models", code, "changelog")
        if os.path.isdir(cp):
            e["local"]["changelog"] = len(os.listdir(cp))
        e["local"]["downgrade"] = os.path.isfile(
            os.path.join(ROOT, "downgrade", f"{code}.txt"))

    payload = {
        "_meta": {
            "generated": datetime.now().strftime("%Y-%m-%d"),
            "note": ("三份清单的合并总表。sources 记录每个 code 来自哪几份，"
                     "local 记录本地实际抓到了多少数据"),
            "sources": {
                "models": "config/models.json —— 自建机型清单",
                "devices": "config/devices.json —— 设备目录（原始来源 OTA-Pulse）",
                "pn_ref": "config/pn_ref.json —— 项目号表（原始来源 Kheronix/oplus-pn-ref）",
            },
        },
        "count": len(inv),
        "models": dict(sorted(inv.items())),
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    tot = len(inv)
    with_data = sum(1 for e in inv.values()
                    if e["local"]["links"] or e["local"]["versions"])
    print(f"✓ {OUT}")
    print(f"  机型总数      {tot}")
    print(f"  本地有数据    {with_data}（{with_data * 100 // max(tot, 1)}%）")
    for s in ("models", "devices", "pn_ref"):
        n = sum(1 for e in inv.values() if s in e["sources"])
        print(f"  来自 {s:8}  {n}")
    print(f"  有项目号      {sum(1 for e in inv.values() if e['prj'])}")
    print(f"  三样齐全      {sum(1 for e in inv.values() if len(e['sources']) == 3)}")


if __name__ == "__main__":
    sys.exit(main())
