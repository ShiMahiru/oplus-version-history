#!/usr/bin/env python3
"""对 remove 永久直链发 Range 请求，从响应头拿 sizeBytes（Content-Range）+ md5（x-amz-meta-filemd5）"""
import json, os, ssl, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "size_cache.json")
ctx = ssl._create_unverified_context()
LOCK = threading.Lock()

def probe(url):
    try:
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        r = urllib.request.urlopen(req, timeout=20, context=ctx)
        cr = r.headers.get("Content-Range", "")
        md5 = (r.headers.get("x-amz-meta-filemd5") or "").strip('"')
        r.close()
        size = None
        if "/" in cr and cr.split("/")[-1].isdigit():
            size = int(cr.split("/")[-1])
        return size, (md5 if len(md5) == 32 else None)
    except Exception:
        return None, None

def main():
    d = json.load(open(SITE))
    cache = json.load(open(os.path.join(ROOT, "config", "size_cache.json"))) if os.path.exists(os.path.join(ROOT, "config", "size_cache.json")) else {}
    tasks = []
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url", "")
                if not u or "/remove-" not in u:
                    continue
                meta = v.get("meta") or {}
                if not meta.get("sizeBytes") or not meta.get("md5"):
                    tasks.append((u, v))
    print(f"待探测 {len(tasks)} 条 remove 直链", flush=True)
    ok = fail = 0
    t0 = time.time()

    def work(t):
        nonlocal ok, fail
        url, v = t
        size, md5 = probe(url)
        with LOCK:
            if size or md5:
                meta = v.setdefault("meta", {})
                if size: meta["sizeBytes"] = size
                if md5: meta["md5"] = md5
                if size: cache[url] = size
                ok += 1
            else:
                fail += 1
            done = ok + fail
            if done % 100 == 0:
                json.dump(cache, open(os.path.join(ROOT, "config", "size_cache.json"), "w"))
                print(f"  {done}/{len(tasks)}: ✓{ok} ✗{fail}", flush=True)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(work, tasks))

    json.dump(cache, open(os.path.join(ROOT, "config", "size_cache.json"), "w"))
    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成 {time.time()-t0:.0f}s: ✓{ok} ✗{fail}")

if __name__ == "__main__":
    main()
