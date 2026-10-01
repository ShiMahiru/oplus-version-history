#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
版本史归一化去重（幂等维护脚本）
================================
把 models/{型号}/ota-version.txt 统一成规范形态：

    <指纹>  # ColorOS: <版本名>
    <指纹>  # ColorOS: <版本名> （查询基线 · 非官方 OTA 指纹）

处理内容：
  1) 去掉行尾空白、把分隔符统一为两个空格
  2) 版本名统一剥离重复的 "ColorOS:" 前缀
  3) 按 (指纹, 版本名) 精确去重（同指纹同版本只留一行）
  4) 按指纹尾时间戳倒序排列（新版本在前）
  5) 保留「查询基线」标注，不伪造指纹

运行: python3 scripts/normalize.py [--dry]
"""
import argparse
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE_RE = re.compile(r"\s*[（(]\s*查询基线.*?[）)]\s*$")


def parse_line(ln):
    """-> (fp, ver, note) 或 None"""
    ln = ln.strip()
    if not ln:
        return None
    note = ""
    m = NOTE_RE.search(ln)
    if m:
        note = "（查询基线 · 非官方 OTA 指纹）"
        ln = ln[: m.start()].rstrip()
    if "#" in ln:
        left, right = ln.split("#", 1)
        fp = left.strip()
        ver = right.strip()
        ver = re.sub(r"^(?:ColorOS\s*:?\s*)+", "", ver).strip()
    else:
        fp, ver = ln, ""
    return fp, ver, note


def key_of(fp):
    tail = fp.rsplit("_", 1)[-1]
    return tail if tail.isdigit() else fp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    models_dir = os.path.join(ROOT, "models")
    n_files = n_before = n_dup = n_after = 0
    dup_files = []

    for code in sorted(os.listdir(models_dir)):
        p = os.path.join(models_dir, code, "ota-version.txt")
        if not os.path.isfile(p):
            continue
        n_files += 1
        rows = []
        for ln in open(p, encoding="utf-8"):
            r = parse_line(ln)
            if r:
                rows.append(r)
        n_before += len(rows)

        seen, uniq = set(), []
        for fp, ver, note in rows:
            k = (fp, ver)
            if k in seen:
                n_dup += 1
                continue
            seen.add(k)
            uniq.append((fp, ver, note))

        uniq.sort(key=lambda it: key_of(it[0]), reverse=True)

        lines = []
        for fp, ver, note in uniq:
            if ver:
                lines.append(f"{fp}  # ColorOS: {ver}" + (f" {note}" if note else ""))
            else:
                lines.append(fp + (f"  # {note}" if note else ""))
        n_after += len(lines)

        if len(lines) != len(rows):
            dup_files.append(f"{code}: {len(rows)} → {len(lines)}")
        if not args.dry:
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

    print(f"文件 {n_files}  行数 {n_before} → {n_after}  去掉重复 {n_dup}")
    if dup_files:
        print("有变化的文件:")
        for d in dup_files:
            print("   ", d)


if __name__ == "__main__":
    main()
