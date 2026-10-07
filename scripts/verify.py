


import argparse
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "okhttp/3.12.12"
UID = "oplus-ota|16002018"
DEAD_DIR = os.path.join(ROOT, "links", "_dead")


def check(url):
    is_gate = "downloadCheck" in url or "download?" in url
    try:
        if is_gate:
            r = requests.get(url, allow_redirects=False, timeout=15,
                             headers={"User-Agent": UA, "userId": UID})
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location", "")
                if "allawn" in loc or "coloros" in loc:
                    return True, f"302 → {loc.split('/')[2]}"
                return False, f"302 → 非官方域 {loc[:60]}"
            return False, f"gate HTTP {r.status_code}（需 302）"
        h = {"Range": "bytes=0-0"}
        r = requests.get(url, allow_redirects=False, timeout=15, headers=h)
        if r.status_code in (200, 206):
            return True, f"{r.status_code}"
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
    ap.add_argument("--dry-run", action="store_true",
                    help="只报告，不移动文件、不写 DEAD.md")
    ap.add_argument("--max", type=int, default=0, metavar="N",
                    help="随机抽 N 条校验（冒烟用；0=全量）")
    args = ap.parse_args()

    files = []
    for root, _, fs in os.walk(os.path.join(ROOT, "links")):
        if "_dead" in root:
            continue
        for f in fs:
            if f.endswith(".txt"):
                files.append(os.path.join(root, f))
    if args.max and args.max < len(files):
        files = random.sample(files, args.max)
    print(f"共 {len(files)} 条链接开始校验（并发 8）")

    dead, ok, fail1 = [], 0, []

    def one(p):
        url = open(p, encoding="utf-8").read().strip()
        good, msg = check(url)
        return p, url, good, msg

    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (p, url, good, msg) in enumerate(ex.map(one, files), 1):
            if good:
                ok += 1
            else:
                fail1.append((p, url, msg))
            if i % 100 == 0:
                print(f"  ... {i}/{len(files)} 有效 {ok} 待定 {len(fail1)}", flush=True)

    def reconfirm(item):
        p, url, msg = item
        good, _ = check(url)
        if not good and not args.fast:
            time.sleep(1.0)
            good, _ = check(url)
        return p, url, msg, good

    if fail1:
        print(f"  二轮确认 {len(fail1)} 条待定链接 …", flush=True)
        with ThreadPoolExecutor(max_workers=4) as ex:
            for p, url, msg, good in ex.map(reconfirm, fail1):
                if good:
                    ok += 1
                else:
                    rel = os.path.relpath(p, os.path.join(ROOT, "links"))
                    dead.append((rel, url, msg))

    if dead:
        if args.dry_run:
            print(f"（dry-run）死链 {len(dead)} 条，未归档：")
            for rel, url, msg in dead:
                print(f"  ✗ {rel}  {msg}")
            return
        import shutil
        moved = []
        for rel, url, msg in dead:
            dst = os.path.join(DEAD_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                shutil.move(os.path.join(ROOT, "links", rel), dst)
                moved.append((rel, url, msg))
            except Exception:
                pass

        with open(os.path.join(ROOT, "DEAD.md"), "w", encoding="utf-8") as f:
            f.write("# 死链报告\n\n以下链接连续校验失败，已移入 `links/_dead/`（版本史保留）。\n\n")
            f.write("| 文件 | 链接 | 原因 |\n|---|---|---|\n")
            for rel, url, msg in moved:
                f.write(f"| `{rel}` | `{url}` | {msg} |\n")
        print(f"✗ 死链 {len(moved)} 条已归档 links/_dead/ → 详见 DEAD.md")
        print(f"  累计有效 {ok}/{len(files)}")
    else:
        with open(os.path.join(ROOT, "DEAD.md"), "w", encoding="utf-8") as f:
            f.write("# 死链报告\n\n以下链接连续校验失败，已移入 `links/_dead/`（版本史保留）。\n\n")
            f.write("最近一次全量校验未发现死链。历史死链见 `links/_dead/`。\n")
        print(f"✓ 全部 {ok}/{len(files)} 条链接有效，无死链")


if __name__ == "__main__":
    main()