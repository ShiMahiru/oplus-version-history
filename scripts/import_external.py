#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从外部归档导入增量（links / 版本史）
====================================
给一份与本地同构的外部归档（例如 chlink2025/oplusrom），把本地缺的链接与
版本史补进来。

三条铁律：

  1. **只补不覆盖**。本地数据由 update.py 每周从官方接口刷新，比外部归档新；
     覆盖等于倒退。同版本链接已存在就跳过（哪怕 URL 不同 —— gate 链接的
     c/s 参数每次查询都会变，两边都有效）。
  2. **只收完整指纹**。外部归档里混着「查询基线」这类半截指纹（形如
     `PHY110_11.A`，没有尾部的 12 位时间戳），normalize.py 早就把它们清洗掉了，
     导入时不能再放回来。判定：指纹必须以 12 位时间戳结尾。
  3. **目录名不参与映射**。外部归档用机型名做目录（`OnePlus 15 (GLO)`），
     本地用 code（`CPH2747`）。code 从文件名 `CPH2747_16.0.10.500(EX01).txt`
     和指纹 `CPH2747_11.A.48_0480_202609111034` 里取，两边一致。

跑完记得接 normalize.py（重排指纹顺序）。

运行:
    python3 scripts/import_external.py --src /tmp/oplusrom-src --dry-run
    python3 scripts/import_external.py --src /tmp/oplusrom-src
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 机型 code：OPPO/一加/realme 的型号前缀，如 CPH2747 / PHY110 / PGEM10 / OPD2481
CODE_RE = re.compile(r"[A-Z]{2,5}\d{2,5}")
# 完整 OTA 指纹必须以 12 位时间戳结尾（PLQ110_11.A.57_0570_202608071758）
FULL_FP_RE = re.compile(r"^[A-Z0-9]+_\d+\.[A-Z]\.\d+_\d+_\d{12}$")


def code_of(text):
    """CPH2747_16.0.10.500(EX01) / CPH2747_11.A.48_0480_202609111034 -> CPH2747"""
    head = text.split("_", 1)[0]
    return head if CODE_RE.fullmatch(head) else None


def read_url(path):
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("http"):
                    return ln.strip()
    except OSError:
        pass
    return ""


def scan_links(src):
    """-> {code: {version: url}}"""
    out = {}
    base = os.path.join(src, "links")
    if not os.path.isdir(base):
        return out
    for model_dir in sorted(os.listdir(base)):
        d = os.path.join(base, model_dir)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".txt"):
                continue
            ver = fn[:-4]
            code = code_of(ver)
            if not code:
                continue
            url = read_url(os.path.join(d, fn))
            if url:
                out.setdefault(code, {})[ver] = url
    return out


def scan_history(src):
    """-> {code: {fingerprint: version_name}}"""
    out = {}
    base = os.path.join(src, "models")
    if not os.path.isdir(base):
        return out
    for model_dir in sorted(os.listdir(base)):
        p = os.path.join(base, model_dir, "ota-version.txt")
        if not os.path.isfile(p):
            continue
        with open(p, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                if "#" in ln:
                    left, right = ln.split("#", 1)
                    fp = left.strip()
                    ver = re.sub(r"^ColorOS\s*:?\s*", "", right.strip()).strip()
                else:
                    fp, ver = ln, ""
                if not FULL_FP_RE.match(fp):
                    continue          # 查询基线之类的半截指纹，不收
                code = code_of(fp)
                if code:
                    out.setdefault(code, {})[fp] = ver
    return out


def local_links(code):
    d = os.path.join(ROOT, "links", code)
    if not os.path.isdir(d):
        return set()
    return {fn[:-4] for fn in os.listdir(d) if fn.endswith(".txt")}


def local_history(code):
    p = os.path.join(ROOT, "models", code, "ota-version.txt")
    if not os.path.isfile(p):
        return set()
    out = set()
    with open(p, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                out.add(ln.split("#")[0].strip())
    return out


def main():
    ap = argparse.ArgumentParser(description="从外部归档导入增量")
    ap.add_argument("--src", required=True, help="外部归档根目录（含 links/ 与 models/）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    opts = ap.parse_args()

    src = os.path.abspath(opts.src)
    if not os.path.isdir(os.path.join(src, "links")):
        sys.exit(f"{src} 下没有 links/，不像同构归档")

    src_links = scan_links(src)
    src_hist = scan_history(src)
    print(f"外部归档：links {len(src_links)} code / {sum(map(len, src_links.values()))} 条"
          f" | 版本史 {len(src_hist)} code / {sum(map(len, src_hist.values()))} 条")

    new_links, new_fps, new_codes = [], [], set()

    for code, vers in sorted(src_links.items()):
        have = local_links(code)
        if not have and not os.path.isdir(os.path.join(ROOT, "models", code)):
            new_codes.add(code)
        for ver, url in sorted(vers.items()):
            if ver in have:
                continue
            new_links.append((code, ver, url))
            if not opts.dry_run:
                d = os.path.join(ROOT, "links", code)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, f"{ver}.txt"), "w", encoding="utf-8") as f:
                    f.write(url + "\n")

    for code, fps in sorted(src_hist.items()):
        have = local_history(code)
        add = [(fp, ver) for fp, ver in sorted(fps.items()) if fp not in have]
        if not add:
            continue
        for fp, ver in add:
            new_fps.append((code, fp, ver))
        if not opts.dry_run:
            p = os.path.join(ROOT, "models", code, "ota-version.txt")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                for fp, ver in add:
                    f.write(f"{fp}  # ColorOS: {ver}\n" if ver else f"{fp}\n")

    print(f"\n新增 code {len(new_codes)} 个：{sorted(new_codes) if new_codes else '无'}")
    print(f"新增链接 {len(new_links)} 条")
    for code, ver, _ in new_links:
        print(f"  + {code}  {ver}")
    print(f"新增版本史 {len(new_fps)} 条")
    for code, fp, ver in new_fps:
        print(f"  + {code}  {fp}  {ver}")
    print()
    print("（dry-run，未写文件）" if opts.dry_run else "已写入，接着跑 normalize.py 重排顺序")


if __name__ == "__main__":
    main()
