#!/usr/bin/env python3
"""sizeBytes 探测 v3：结果独立存 config/size_cache.json（url→size），不写 site.json（避免被 build 覆盖）"""
import json, os, ssl, time, urllib.request, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "size_cache.json")
ctx = ssl._create_unverified_context()

def probe(url):
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
            r = urllib.request.urlopen(req, timeout=20, context=ctx)
            cr = r.headers.get("Content-Range", ""); r.close()
            if "/" in cr and cr.split("/")[-1].isdigit():
                return int(cr.split("/")[-1])
            cl = r.headers.get("Content-Length")
            if cl and cl.isdigit(): return int(cl)
            return None
        except urllib.error.HTTPError:
            return None
        except Exception:
            time.sleep(2)
    return None

def main():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    d = json.load(open(SITE))
    tasks = []
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url")
                if u and u not in cache:
                    tasks.append(u)
    print(f"待探测 {len(tasks)} 条（缓存已有 {len(cache)}）", flush=True)
    ok = 0
    for i, url in enumerate(tasks):
        size = probe(url)
        if size:
            cache[url] = size; ok += 1
        if (i+1) % 100 == 0:
            json.dump(cache, open(CACHE, "w"))
            print(f"  {i+1}/{len(tasks)}: ✓{ok}", flush=True)
        time.sleep(0.4)
    json.dump(cache, open(CACHE, "w"))
    print(f"完成: ✓{ok} | 缓存总 {len(cache)} 条", flush=True)

if __name__ == "__main__":
    main()
