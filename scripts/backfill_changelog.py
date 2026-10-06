#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补全 CN 版本的更新日志。
来源：
  1) 本地 ota-version.txt 已有指纹的（直接查）
  2) Daniel API 的 ota_version 字段补指纹后查
写入 models/{code}/changelog/{指纹前缀}.md + ota-version.txt 补行。
"""
import json, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from update import changelog_query

CN_REGIONS = {"CN", "CN01", "CH", "CT"}


def full_fp(ota_version):
    """Daniel ota_version -> 完整指纹（校验 12 位时间戳结尾）。"""
    ov = ota_version.strip()
    m = re.match(r"^[A-Z0-9]+_\d+\.[A-Z]\.\d+_\d+_\d{12}$", ov)
    return ov if m else None


def main():
    catalog = json.load(open("/tmp/catalog.json"))
    # Daniel: {(model, version) -> ota_version}
    dan = {}
    for r in catalog["releases"]:
        m, v, ov = r.get("model",""), r.get("version",""), r.get("ota_version","")
        if m and v and ov:
            dan[(m, v)] = ov

    # 遍历 CN links，找缺 changelog 的
    stats = {"have": 0, "direct": 0, "via_daniel": 0, "no_fp": 0, "query_fail": 0}
    for code in sorted(os.listdir(os.path.join(ROOT, "links"))):
        d = os.path.join(ROOT, "links", code)
        if not os.path.isdir(d): continue
        ver_file = os.path.join(ROOT, "models", code, "ota-version.txt")
        ver_map = {}
        if os.path.isfile(ver_file):
            for line in open(ver_file, encoding="utf-8"):
                mm = re.match(r"^(\S+)\s+#\s*(?:ColorOS:\s*)?(\S+)", line.strip())
                if mm: ver_map[mm.group(2)] = mm.group(1)
        cl_dir = os.path.join(ROOT, "models", code, "changelog")
        existing = set(os.listdir(cl_dir)) if os.path.isdir(cl_dir) else set()

        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".txt"): continue
            ver = fn[:-4]
            m2 = re.search(r"\(([A-Z0-9]+)\)$", ver)
            if m2 and m2.group(1) not in CN_REGIONS: continue
            fp_full = ver_map.get(ver)
            if fp_full:
                fp_prefix = fp_full.rsplit("_", 1)[0] if fp_full.rsplit("_", 1)[-1].isdigit() else fp_full
                if fp_prefix + ".md" in existing:
                    stats["have"] += 1
                    continue
                source = "local"
            else:
                # 从 Daniel 拿指纹
                ov = dan.get((code, ver))
                if not ov:
                    stats["no_fp"] += 1
                    continue
                fp_full = full_fp(ov)
                if not fp_full:
                    stats["no_fp"] += 1
                    continue
                fp_prefix = fp_full.rsplit("_", 1)[0]
                source = "daniel"

            # 查 changelog
            r = changelog_query(code, fp_prefix, "cn")
            if not r or not r[1] or "官方无更新日志" in r[1]:
                stats["query_fail"] += 1
                time.sleep(0.3)
                continue
            version_name, md = r
            # 写 changelog
            os.makedirs(cl_dir, exist_ok=True)
            with open(os.path.join(cl_dir, fp_prefix + ".md"), "w", encoding="utf-8") as f:
                f.write(md)
            # 指纹补进 ota-version.txt
            if source == "daniel":
                with open(ver_file, "a", encoding="utf-8") as f:
                    f.write(f"{fp_full}  # ColorOS: {ver}\n")
                ver_map[ver] = fp_full
            stats["direct" if source == "local" else "via_daniel"] += 1
            print(f"  {code} {ver} [{source}] -> {fp_prefix}.md ({len(md)}B)")
            time.sleep(0.3)

    print(f"\n完成: {stats}")


if __name__ == "__main__":
    main()
