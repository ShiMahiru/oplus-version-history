#!/usr/bin/env python3
"""合并 antirollchecker 的 database.json 历史版本 ARB + 本地 arb.json 最新版 ARB 进 site.json。

优先级：antirollchecker（社区维护，含历史版本）> 本地 arb.json（自己提取的最新版）
按版本号精确匹配（versionName 匹配 + md5 兜底）。
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根

site = json.load(open(os.path.join(ROOT, "site", "site.json")))
arbdb_path = os.path.join(ROOT, "config", "arb_database.json")
arbdb = json.load(open(arbdb_path)) if os.path.exists(arbdb_path) else {}

# 本地 arb.json（最新版）

def norm_ver(v):
    """从 'ColorOS 16.0.10.500(CN01)' 提取 '16.0.10.500(CN01)'"""
    m = re.search(r'(\d+\.\d+\.\d+\.\d+\([A-Z0-9]+\))', v)
    return m.group(1) if m else v

merged = 0
matched_hist = 0
for b in site["brands"]:
    for m in b["models"]:
        code = m["code"]
        # 1. antirollchecker 历史版本（按版本号匹配每个版本）
        if code in arbdb:
            arb_versions = arbdb[code].get("versions", {})
            for v in m["versions"]:
                # 从 version 提取版本号，匹配 arb_versions 的 key
                vkey = norm_ver(v["version"])
                # 尝试直接匹配 key
                match = None
                for k, info in arb_versions.items():
                    if vkey in k or k in vkey:
                        match = info
                        break
                if match:
                    v.setdefault("meta", {})
                    v["meta"]["arb"] = match.get("arb")
                    v["meta"]["arbStatus"] = "Safe" if match.get("arb") == 0 else "Protected"
                    v["meta"]["arbMajor"] = match.get("major")
                    v["meta"]["arbMinor"] = match.get("minor")
                    matched_hist += 1
            merged += 1

        # 2. 本地 arb.json 兜底（antirollchecker 没覆盖的）
        arb_path = os.path.join(ROOT, "models", code, "arb.json")
        if os.path.exists(arb_path):
            arb = json.load(open(arb_path))
            if arb.get("arb") is not None:
                # 只补最新版（第一个版本），且 antirollchecker 没填的
                v0 = m["versions"][0]
                if "arb" not in v0.get("meta", {}):
                    v0.setdefault("meta", {})
                    v0["meta"]["arb"] = arb.get("arb")
                    v0["meta"]["arbStatus"] = arb.get("status")
                    v0["meta"]["arbMajor"] = arb.get("major")
                    v0["meta"]["arbMinor"] = arb.get("minor")

json.dump(site, open(os.path.join(ROOT, "site", "site.json"), "w"), ensure_ascii=False, separators=(",", ":"))

# 统计
total_arb_ver = 0
for b in site["brands"]:
    for m in b["models"]:
        for v in m["versions"]:
            if "arb" in v.get("meta", {}):
                total_arb_ver += 1
print(f"合并完成：{merged} 机型来自 antirollchecker（{matched_hist} 历史版本），总 {total_arb_ver} 版本有 ARB")
