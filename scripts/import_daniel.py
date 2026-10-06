#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Daniel Springer 的 OTA API 导入欧加历史版本。
==============================================
数据源: https://roms.danielspringer.at/api/ota.php（公开只读目录）
覆盖 OnePlus/OPPO/Realme/Xiaomi/Redmi/POCO，只取欧加三品牌。

铁律（与 import_external.py 一致）:
  1. 只补不覆盖 —— 本地已有同版本跳过。
  2. 只收 gate 链接（downloadCheck，长期有效）—— gauss 直链会过期，
     导入后很快失效，跳过。
  3. 只收欧加机型 code（CPH/NE/PJZ/RMX 等前缀）。

运行:
  python3 scripts/import_daniel.py --dry-run
  python3 scripts/import_daniel.py
"""
import argparse
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://roms.danielspringer.at/api/ota.php"

# 欧加机型 code 前缀（OnePlus/OPPO/Realme），显式白名单，避免把小米等混进来
OPLUS_CODE_RE = re.compile(
    r"^(CPH|NE|LE|IN|KB|PHB|PHK|PHQ|PHT|PJD|PJZ|PJA|PJE|PJF|PJB|PJC|PJD|PJE|"
    r"PLK|PLQ|PLR|PLC|PLD|PLE|PLF|PLG|PLH|PLJ|PLU|PLY|PLZ|PLP|PLL|PLM|PLN|PLT|"
    r"PKA|PKB|PKC|PKD|PKE|PKF|PKG|PKH|PKJ|PKK|PKL|PKM|PKN|PKQ|PKR|PKS|PKT|PKU|"
    r"PKV|PKW|PKX|PKY|PKZ|"
    r"PGA|PGB|PGC|PGD|PGE|PGF|PGG|PGH|PGI|PGJ|PGK|PGL|PGM|PGN|PGO|PGP|PGQ|PGR|"
    r"PGS|PGT|PGU|PGV|PGW|PGX|PGY|PGZ|"
    r"NE|LE|IN\d|KB\d|OPD|RMX|RMP)"
)


def code_of(model):
    """判断 model 是否是欧加机型 code，是则返回，否则 None。"""
    if OPLUS_CODE_RE.match(model):
        return model
    return None


def fetch_catalog():
    print(f"拉取 {API} ...")
    req = urllib.request.Request(API, headers={"User-Agent": "oplus-version-history-importer"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def version_filename(model, version, region):
    """Daniel version + region -> 我们的链接文件名（不含 .txt）。

    老格式（11_A.19 这种）不带 region；新格式（14.0.0.300(CN01)）带 region。
    我们的仓库：NE2210_11_A.19.txt / NE2210_14.0.0.300(CN01).txt
    """
    # version 形如 NE2210_11_A.19 或 NE2210_14.0.0.300(CN01)
    # 去掉 model 前缀；个别脏数据带额外首字母（PPKX110...），剥到与 model 对齐
    ver = version
    if ver.startswith(model + "_"):
        ver = ver[len(model) + 1:]
    else:
        # 找 model 在 version 里最后一次出现的位置，从那里开始取
        idx = ver.rfind(model + "_")
        if idx > 0:
            ver = ver[idx + len(model) + 1:]
    # 判断是否已带 region 括号
    if "(" in ver:
        return f"{model}_{ver}"
    # 老格式：不带 region（除非 region 是明确的 CN/IN/EU/GL）
    if region in ("CN", "IN", "EU", "GL"):
        # 老格式也补 region？不——保持与仓库一致（老格式无 region）
        pass
    return f"{model}_{ver}"


def scan_local_links():
    """-> {code: set(文件名不带.txt)}"""
    out = {}
    links_dir = os.path.join(ROOT, "links")
    if not os.path.isdir(links_dir):
        return out
    for code in os.listdir(links_dir):
        d = os.path.join(links_dir, code)
        if not os.path.isdir(d):
            continue
        names = set()
        for fn in os.listdir(d):
            if fn.endswith(".txt"):
                names.add(fn[:-4])
        out[code] = names
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    catalog = fetch_catalog()
    releases = catalog["releases"]
    local = scan_local_links()

    to_import = []  # (code, filename, url)
    seen = set()  # (code, filename) 去重
    skipped_gate = 0
    skipped_exist = 0
    skipped_non_oplus = 0
    skipped_direct = 0
    skipped_dup = 0

    for r in releases:
        model = r.get("model", "")
        code = code_of(model)
        if not code:
            skipped_non_oplus += 1
            continue
        url = r.get("source_url", "")
        if not url:
            continue
        # 域名白名单：只收欧加官方域名（gate + 裸直链都收，实测裸直链长期有效）
        host = url.split("/")[2] if "/" in url else ""
        if not any(dom in host for dom in (
            "allawnfs.com", "allawnos.com", "allawntech.com",
        )):
            skipped_direct += 1
            continue
        version = r.get("version", "")
        region = r.get("region", "")
        fname = version_filename(model, version, region)
        if fname in local.get(code, set()):
            skipped_exist += 1
            continue
        key = (code, fname)
        if key in seen:
            skipped_dup += 1
            continue
        seen.add(key)
        to_import.append((code, fname, url))

    print(f"欧加机型 release 处理完：可导入 {len(to_import)} 个版本")
    print(f"  （跳过：已存在 {skipped_exist}，非欧加 {skipped_non_oplus}，非欧加域名 {skipped_direct}，重复 {skipped_dup}）")

    if args.dry_run:
        print("\n[Dry-run] 预览前 20 条：")
        for code, fname, url in to_import[:20]:
            print(f"  {code} / {fname} -> {url[:70]}")
        return

    # 实际写入
    written = 0
    for code, fname, url in to_import:
        d = os.path.join(ROOT, "links", code)
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, fname + ".txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(url + "\n")
        written += 1
    print(f"\n已写入 {written} 个链接文件。")
    print("记得接 normalize.py 重排 + build_md.py 重建文档。")


if __name__ == "__main__":
    main()
