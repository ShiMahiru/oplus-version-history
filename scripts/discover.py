#!/usr/bin/env python3
"""新机型发现：枚举候选机型代号，用官方 v6 接口探活，命中即写入 models.json。

用法:
  python3 scripts/discover.py --pattern cph --from 2400 --to 2450 --region sg --limit 50
  python3 scripts/discover.py --pattern rmx --from 4000 --to 4200 --region in
  python3 scripts/discover.py --pattern cn --prefix PM --region cn
"""
import sys, os, json, time, argparse, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update

ROOT = update.ROOT
MP = os.path.join(ROOT, "config", "models.json")

CN_SUFFIX = ["110","120","130","140","150","160","170","180","190","200",
             "210","220","230","240","250","260","270","280","290","300"]

def candidates(a):
    if a.pattern in ("cph", "rmx", "opd"):
        pre = a.pattern.upper()
        for n in range(a.frm, a.to + 1):
            yield f"{pre}{n}"
    elif a.pattern == "cn":
        pre = a.prefix.upper()
        letters = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        for x in letters:
            for y in letters:
                for suf in CN_SUFFIX:
                    yield f"{pre}{x}{y}{suf}"
    elif a.pattern == "list":
        for c in a.codes:
            yield c

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", default="cph", choices=["cph", "rmx", "opd", "cn", "list"])
    ap.add_argument("--prefix", default="PM")
    ap.add_argument("--from", dest="frm", type=int, default=2400)
    ap.add_argument("--to", type=int, default=2500)
    ap.add_argument("--region", default="cn")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--gap", type=float, default=0.5)
    ap.add_argument("--codes", nargs="*", default=[])
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--offset", type=int, default=0, help="轮转起点，配合 --limit 分批扫完整个空间")
    ap.add_argument("--include-known", action="store_true", help="调试用：不跳过已知机型")
    a = ap.parse_args()

    data = json.load(open(MP))
    known = {m["code"] for m in data["models"]}
    todo = [c for c in candidates(a) if a.include_known or c not in known]
    if a.offset:
        todo = todo[a.offset:] + todo[:a.offset]
    if a.limit:
        todo = todo[:a.limit]
    print(f"候选 {len(todo)} 个，区域 {a.region}，已知机型 {len(known)}", flush=True)
    if a.dry:
        print("样例:", todo[:10]); return

    hits = []
    for i, code in enumerate(todo):
        try:
            r = update.v6_query(code, a.region)
        except Exception:
            r = None
        if r and r.get("version"):
            brand = "realme" if code.startswith("RMX") else ("oneplus" if code.startswith("P") else "oppo")
            hits.append({"code": code, "name": r.get("version", "").split("_")[0],
                         "brand": brand, "region": a.region.upper(), "_source": "discover"})
            print(f"  ✅ 命中 {code} -> {r.get('version')} | md5 {'有' if r.get('md5') else '无'}", flush=True)
        if (i + 1) % 50 == 0:
            print(f"  ... {i+1}/{len(todo)} 命中 {len(hits)}", flush=True)
        time.sleep(a.gap)

    print(f"探测 {len(todo)} 个，命中 {len(hits)} 个")
    if hits:
        data["models"].extend(hits)
        json.dump(data, open(MP, "w"), ensure_ascii=False, indent=1)
        print(f"已写入 models.json，共 {len(data['models'])} 条")

if __name__ == "__main__":
    main()
