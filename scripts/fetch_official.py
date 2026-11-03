#!/usr/bin/env python3
"""用 OPPO 官方 v6 + descriptionInfo 接口补齐：链接(gate)、MD5、体积、更新日志。"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update

ROOT = update.ROOT

def fetch(model, region="cn", verbose=True):
    info = update.v6_query(model, region)
    if not info or not info.get("version"):
        return None
    ver, fp = info["version"], info.get("fp") or ""
    # 链接文件
    update.write_link(model, ver, info.get("url", ""), info.get("size"), info.get("md5"),
                      info.get("patch"), fp)
    # 更新日志
    md = None
    if fp:
        pre = update.fp_prefix(fp)
        r = update.changelog_query(model, pre, region)
        if r and r[1]:
            update.write_changelog(model, fp, r[0] or ver, r[1])
            md = r[1]
    # ota-version.txt
    hist = update.read_history(model)
    if fp and fp not in hist:
        hist[fp] = ver
        update.write_history(model, hist)
    if verbose:
        print(f"{model} {ver} | md5 {'有' if info.get('md5') else '无'} | 日志 {'有' if md else '无'} | fp {fp}")
    return {"model": model, "version": ver, "fp": fp, "md5": info.get("md5"),
            "size": info.get("size"), "changelog": bool(md), "url": info.get("url")}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--region", default="cn")
    a = ap.parse_args()
    targets = a.models
    if a.all:
        targets = sorted(d for d in os.listdir(os.path.join(ROOT, "models"))
                         if os.path.isdir(os.path.join(ROOT, "models", d)))
    ok = 0
    for m in targets:
        try:
            if fetch(m, a.region): ok += 1
        except Exception as e:
            print(m, "ERR", type(e).__name__, str(e)[:60])
    print(f"完成 {ok}/{len(targets)}")
