#!/usr/bin/env python3
"""对 site.json 里已有直链但缺 sizeBytes 的版本，用 Range 请求拿 Content-Range 补全。
顺带标记死链（连续失败的 URL 写入 config/dead_links.json）。"""
import json, os, ssl, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "site.json")
ctx = ssl._create_unverified_context()
LOCK = threading.Lock()
STATS = {"ok": 0, "dead": 0, "skip": 0}
DEAD = set()

def probe_size(url):
    """Range 请求拿 Content-Range 的总大小"""
    try:
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": "okhttp/3.12.12"})
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        cr = r.headers.get("Content-Range", "")
        r.close()
        if "/" in cr:
            total = cr.split("/")[-1]
            if total.isdigit():
                return int(total)
        cl = r.headers.get("Content-Length")
        if cl and cl.isdigit():
            return int(cl)
    except Exception:
        return None
    return None

def main():
    d = json.load(open(SITE))
    tasks = []
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url")
                if not u:
                    continue
                meta = v.get("meta") or {}
                if meta.get("sizeBytes"):
                    continue
                tasks.append((m["code"], v["version"], u, v))
    print(f"待探测: {len(tasks)} 条直链")
    t0 = time.time()

    def work(t):
        code, ver, url, v = t
        size = probe_size(url)
        with LOCK:
            if size:
                meta = v.get("meta") or {}
                meta["sizeBytes"] = size
                v["meta"] = meta
                STATS["ok"] += 1
            else:
                DEAD.add(url)
                STATS["dead"] += 1
            done = STATS["ok"] + STATS["dead"]
            if done % 100 == 0:
                print(f"  进度 {done}: ✓{STATS['ok']} 死{STATS['dead']}", flush=True)

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, tasks))

    json.dump(sorted(DEAD), open(os.path.join(ROOT, "config", "dead_links.json"), "w"), indent=1)
    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    el = time.time() - t0
    print(f"完成 {el/60:.1f} 分钟: ✓size {STATS['ok']} | 死链 {STATS['dead']}")

if __name__ == "__main__":
    main()
