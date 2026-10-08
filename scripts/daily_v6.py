#!/usr/bin/env python3
"""每日 v6 增量记录：164 CN 机型单次查询，记录新版本 + 刷新链接签名 + 拉全字段元数据。
用法: python3 scripts/daily_v6.py [--region CN] [--limit N]
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update


class Opts:
    v6 = True
    only_latest = True
    dry = False
    model = None
    shard = None
    no_downgrade = True
    no_history_write = False
    only_changelog = False


def main():
    import argparse
    ap = argparse.ArgumentParser(description="每日 v6 增量记录")
    ap.add_argument("--region", default="CN")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models = json.load(open(os.path.join(root, "config", "models.json")))["models"]
    targets = [m for m in models if m.get("region") == args.region]
    if args.limit:
        targets = targets[:args.limit]
    print(f"{args.region} 机型 {len(targets)} 个，v6 增量记录开始…", flush=True)

    t0 = time.time()
    new = err = cl_got = 0
    for i, m in enumerate(targets):
        code = m["code"]
        try:
            r = update.update_model(m, Opts())
            new += r["new_links"]
        except Exception as e:
            err += 1
            print(f"  [错误] {code}: {type(e).__name__} {str(e)[:60]}", flush=True)
            continue
        # 日志来源优先级：① descriptionInfo（secondContents）② v6 description.opex.content
        try:
            v6_res = update.v6_query(code, args.region.lower())
            if not v6_res:
                continue
            fp_full = v6_res.get("fp") or ""
            md_text = ""
            cver = v6_res.get("version") or ""
            # ① descriptionInfo
            mm = update.re.match(rf"({code}_11\.[A-Z]\.\d+)_", fp_full)
            if mm:
                rr = update.changelog_query(code, mm.group(1), args.region.lower())
                time.sleep(update.GAP)
                if rr:
                    cver, md_text = rr[0] or cver, rr[1]
            # ② v6 description.opex.content（ColorOS 17+ 新格式）
            if not md_text:
                raw = v6_res.get("raw") or {}
                desc = raw.get("description") or {}
                opex = desc.get("opex") or {}
                if opex.get("content"):
                    md_text = f"## {opex.get('title','更新日志')}\n{opex['content']}"
            if md_text:
                update.write_changelog(code, fp_full, cver or v6_res["version"], md_text)
                cl_got += 1
                history = update.read_history(code)
                history[fp_full] = cver or v6_res["version"]
                update.write_history(code, history)
        except Exception as e:
            print(f"  [日志错误] {code}: {type(e).__name__} {str(e)[:50]}", flush=True)
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(targets)} | 新链接 {new} | 日志 {cl_got} | 错误 {err} | {time.time()-t0:.0f}s", flush=True)
    print(f"完成: {len(targets)} 机型 | 新链接 {new} | 新日志 {cl_got} | 错误 {err} | {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
