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
    ap.add_argument("--shard", default="0/1", help="分片，形如 0/6")
    ap.add_argument("--taste", action="store_true", help="额外采集 taste 灰度版")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models = json.load(open(os.path.join(root, "config", "models.json")))["models"]
    targets = [m for m in models if m.get("region") == args.region]
    
    try:
        si, st = (int(x) for x in args.shard.split("/"))
        if st > 1:
            targets = targets[si::st]
    except Exception:
        pass
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
        
        try:
            v6_res = update.v6_query(code, args.region.lower())
            if not v6_res:
                continue
            fp_full = v6_res.get("fp") or ""
            md_text = ""
            cver = v6_res.get("version") or ""
            
            mm = update.re.match(rf"({code}_11\.[A-Z]\.\d+)_", fp_full)
            if mm:
                rr = update.changelog_query(code, mm.group(1), args.region.lower())
                time.sleep(update.GAP)
                if rr:
                    cver, md_text = rr[0] or cver, rr[1]
            
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

    
    if getattr(args, "taste", False):
        print("\n开始采集 taste 灰度版…", flush=True)
        t1 = time.time()
        t_new = t_err = 0
        for i, m in enumerate(targets):
            code = m["code"]
            try:
                tr = update.v6_query(code, args.region.lower(), mode="taste")
                if tr and tr.get("url") and tr.get("version"):
                    fp = tr.get("fp") or ""
                    ver = tr["version"]
                    if not update.re.match(r"^[A-Z0-9]+_\d+\.\d+\.\d+", ver):
                        continue
                    
                    hist = update.read_history(code)
                    def _vkey(s):
                        mm = update.re.search(r"_(\d+(?:\.\d+)+)", s)
                        return [int(x) for x in mm.group(1).split(".")] if mm else [0]
                    newest = [0]
                    for _h in hist.values():
                        _k = _vkey(_h)
                        if _k > newest:
                            newest = _k
                    if _vkey(ver) <= newest:
                        continue
                    if fp and fp not in hist:
                        update.write_link(code, ver, tr["url"], tr.get("size"), tr.get("md5"),
                                          tr.get("patch"), fp)
                        hist[fp] = ver
                        update.write_history(code, hist)
                        t_new += 1
                        print(f"  🎯 {code} {ver} (灰度)", flush=True)
            except Exception as e:
                t_err += 1
            time.sleep(update.GAP)
        print(f"taste 完成: 新灰度版 {t_new} | 错误 {t_err} | {time.time()-t1:.0f}s", flush=True)

if __name__ == "__main__":
    main()
