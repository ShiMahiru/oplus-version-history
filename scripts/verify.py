#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oplus-version-history 链接存活校验
==================================
遍历 links/ 下全部条目，核实下载链接真实可用：
  - 官方 gate（downloadCheck?）→ 302 跳转，Location 指向官方 Gauss CDN = 有效
  - 直接直链（gauss-*.allawnfs.com）→ 206/200 Range 探测 = 有效
连续 2 轮失败的移入 links/_dead/，并生成 DEAD.md 报告。

运行: python3 scripts/verify.py [--fast]
"""
import argparse
import os
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "okhttp/3.12.12"
UID = "oplus-ota|16002018"
DEAD_DIR = os.path.join(ROOT, "links", "_dead")


def check(url):
    is_gate = "downloadCheck" in url or "download?" in url
    try:
        if is_gate:
            # gate 只认 302 → 官方 CDN；返回 200（错误页）视为无效
            r = requests.get(url, allow_redirects=False, timeout=15,
                             headers={"User-Agent": UA, "userId": UID})
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location", "")
                if "allawn" in loc or "coloros" in loc:
                    return True, f"302 → {loc.split('/')[2]}"
                return False, f"302 → 非官方域 {loc[:60]}"
            return False, f"gate HTTP {r.status_code}（需 302）"
        # 直链：Range 探测（防盗链对无 Range 请求可能 403）
        # 注意 downgradefs.coloros.com 对 okhttp/浏览器 UA 均返回 403，
        # 只接受空 UA / python-requests 默认 UA——探测时不手动设 UA。
        h = {"Range": "bytes=0-0"}
        r = requests.get(url, allow_redirects=False, timeout=15, headers=h)
        if r.status_code in (200, 206):
            return True, f"{r.status_code}"
        # 二次尝试：带 Referer（部分 CDN 校验来源）
        h2 = dict(h, Referer="https://www.coloros.com/")
        r2 = requests.get(url, allow_redirects=False, timeout=15, headers=h2)
        if r2.status_code in (200, 206):
            return True, f"{r2.status_code}(+Referer)"
        return False, f"HTTP {r2.status_code} 直链不可用"
    except Exception as e:
        return False, str(e)[:60]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="单轮校验（不二轮确认）")
    args = ap.parse_args()

    files = []
    for root, _, fs in os.walk(os.path.join(ROOT, "links")):
        if "_dead" in root:
            continue
        for f in fs:
            if f.endswith(".txt"):
                files.append(os.path.join(root, f))
    print(f"共 {len(files)} 条链接开始校验")

    dead, ok, fail1 = [], 0, []
    for i, p in enumerate(files, 1):
        url = open(p, encoding="utf-8").read().strip()
        good, msg = check(url)
        if good:
            ok += 1
        else:
            fail1.append((p, url, msg))
        time.sleep(0.32)
        if i % 100 == 0:
            print(f"  ... {i}/{len(files)} 有效 {ok} 待定 {len(fail1)}")

    # 二轮确认（决定性证据：死链在两个轮次都失败才算）
    for p, url, msg in fail1:
        if args.fast:
            good, _ = check(url)
        else:
            good, _ = check(url)
            if not good:
                time.sleep(1.0)
                good, _ = check(url)
        time.sleep(0.32)
        if good:
            ok += 1
        else:
            rel = os.path.relpath(p, os.path.join(ROOT, "links"))
            dead.append((rel, url, msg))

    # 归档死链
    if dead:
        import shutil
        for rel, url, msg in dead:
            dst = os.path.join(DEAD_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.move(os.path.join(ROOT, "links", rel), dst)
            except Exception:
                pass
        with open(os.path.join(ROOT, "DEAD.md"), "w", encoding="utf-8") as f:
            f.write("# 死链报告\n\n以下链接连续校验失败，已移入 `links/_dead/`（版本史保留）。\n\n")
            f.write("| 文件 | 链接 | 原因 |\n|---|---|---|\n")
            for rel, url, msg in dead:
                f.write(f"| `{rel}` | `{url}` | {msg} |\n")
        print(f"✗ 死链 {len(dead)} 条已归档 links/_dead/ → 详见 DEAD.md")
    else:
        print(f"✓ 全部 {ok}/{len(files)} 条链接有效，无死链")


if __name__ == "__main__":
    main()