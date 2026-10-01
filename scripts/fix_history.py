#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本史清洗 + 查询基线指纹修正
==============================
问题（实测取证）：
  1) 936 行里有 79 行是「同一指纹+同一版本」的重复，只因写入时空格数不同
     （seed.py 直接搬运源文本，未归一化）。
  2) 187 行是**查询基线指纹**而非官方 OTA 指纹：
     形如 `CPH2411NV1B_11.H.01_0001_100001010000`
     —— 这是枚举时构造的服务固件模板 `{code}{nvid}_11.{letter}.01_0001_100001010000`，
     不是官方返回的 otaVersion。仓库声明「指纹来自官方 v3 响应」，必须修正。

处理规则：
  a) 归一化 + 按 (指纹, 版本) 去重
  b) 基线指纹行：若该版本在本机型已有真实指纹行 → 删除基线行（保留真实指纹）
  c) 基线指纹行且无真实指纹 → 用官方 v3 重查该机型该分支：
       命中且版本一致 → 写入真实 otaVersion 指纹
       未命中/版本已变   → 保留该行但显式标注「查询基线 · 非官方 OTA 指纹」（不伪造）

运行: python3 scripts/fix_history.py [--dry]
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402  复用 v3_query / MODELS / region_of

ROOT = U.ROOT
NV_RE = re.compile(r"^[A-Z0-9]+NV[0-9A-F]{2}_11\.[A-Z]\.01_0001_100001010000$")
NVID_RE = re.compile(r"^([A-Z0-9]+?)(NV[0-9A-F]{2})_11\.([A-Z])\.01_0001_100001010000$")

# nvid → 官方网关区域（RomCloud 实测区域表：NV97=CN, NV1B=IN, NV44=EU, NVA7=GL；
# 其余区域码走 EU 网关，实测这些机型在 eu 网关有响应）
NVID_REGION = {
    "NV97": "cn", "NV1B": "in", "NV44": "eu", "NVA7": "gl",
    "NV33": "eu", "NV2C": "eu", "NV1A": "eu", "NV38": "eu", "NV39": "eu",
    "NV37": "eu", "NV51": "gl", "NV83": "eu", "NVA6": "eu", "NV3D": "eu",
    "NV5A": "eu", "NV9A": "eu", "NV9E": "gl",
}


def parse_line(ln):
    """-> (fp, ver) 或 None"""
    ln = ln.strip()
    if not ln:
        return None
    if "#" in ln:
        left, right = ln.split("#", 1)
        fp = left.strip()
        ver = right.strip()
        ver = re.sub(r"^ColorOS\s*:?\s*", "", ver).strip()
        ver = re.sub(r"\s*（.*?）\s*$", "", ver).strip()   # 去旧标注
        ver = re.sub(r"\s*\[.*?\]\s*$", "", ver).strip()
    else:
        fp, ver = ln, ""
    return fp, ver


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="只报告不改文件")
    args = ap.parse_args()

    models_dir = os.path.join(ROOT, "models")
    region_of_code = {m["code"]: U.region_of(m) for m in U.MODELS}
    st = {"files": 0, "dup": 0, "nv_dropped": 0, "nv_fixed": 0, "nv_kept": 0, "kept_versions": []}

    for code in sorted(os.listdir(models_dir)):
        d = os.path.join(models_dir, code)
        p = os.path.join(d, "ota-version.txt")
        if not os.path.isfile(p):
            continue
        st["files"] += 1

        rows = []
        for ln in open(p, encoding="utf-8"):
            r = parse_line(ln)
            if r:
                rows.append(r)

        # a) 去重（同指纹同版本）
        seen, uniq = set(), []
        for fp, ver in rows:
            if (fp, ver) in seen:
                st["dup"] += 1
                continue
            seen.add((fp, ver))
            uniq.append((fp, ver))

        # 同版本已存在的真实指纹
        real_by_ver = {}
        for fp, ver in uniq:
            if ver and not NV_RE.match(fp):
                real_by_ver.setdefault(ver, fp)

        out, requery = [], []
        for fp, ver in uniq:
            if NV_RE.match(fp):
                if ver and ver in real_by_ver:
                    st["nv_dropped"] += 1          # b) 已有真实指纹 → 丢基线行
                    continue
                requery.append((fp, ver))          # c) 待重查
            else:
                out.append((fp, ver, ""))

        # c) 官方 v3 重查补真实指纹
        for fp, ver in requery:
            m = NVID_RE.match(fp)
            letter = m.group(3) if m else None
            nvid = m.group(2) if m else None
            region = NVID_REGION.get(nvid or "", region_of_code.get(code, "gl"))
            saved = U.REGIONS[region]["nvid"]
            if nvid:
                U.REGIONS[region]["nvid"] = nvid     # 用原始 nvid 重查同一分支
            res = None
            try:
                res = U.v3_query(code, region, letter) if letter else None
            finally:
                U.REGIONS[region]["nvid"] = saved
            time.sleep(U.GAP)

            if res and res.get("fp") and (not ver or not res.get("version") or res["version"] == ver):
                out.append((res["fp"], res.get("version") or ver, ""))
                st["nv_fixed"] += 1
            else:
                out.append((fp, ver, "（查询基线 · 非官方 OTA 指纹）"))
                st["nv_kept"] += 1
                st["kept_versions"].append(f"{code} {ver}")

        # 排序：指纹尾时间戳倒序
        def keyof(it):
            tail = it[0].rsplit("_", 1)[-1]
            return tail if tail.isdigit() else it[0]

        out.sort(key=keyof, reverse=True)

        lines = []
        for fp, ver, note in out:
            if ver:
                lines.append(f"{fp}  # ColorOS: {ver}" + (f" {note}" if note else ""))
            else:
                lines.append(fp + (f"  # {note}" if note else ""))
        text = "\n".join(lines) + "\n"
        if not args.dry:
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
        print(f"  {code:12s} {len(rows):3d} → {len(lines):3d} 行"
              f"  去重 {len(rows)-len(uniq)}  基线删除/修正/保留 "
              f"{sum(1 for x in uniq if NV_RE.match(x[0])) and ''}"
              f"{st['nv_dropped']}+{st['nv_fixed']}+{st['nv_kept']}")

    print(f"\n文件 {st['files']}  去重 {st['dup']}  "
          f"基线行删除 {st['nv_dropped']}  修正为真实指纹 {st['nv_fixed']}  标注保留 {st['nv_kept']}")
    if st["kept_versions"]:
        print("未取得真实指纹（已如实标注）:")
        for v in st["kept_versions"]:
            print("   ", v)


if __name__ == "__main__":
    main()
