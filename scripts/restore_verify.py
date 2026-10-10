#!/usr/bin/env python3
"""用正确方法（downloadCheck 带 userId 头）逐条实测，恢复被误删的 size/md5"""
import json, os, ssl, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "meta_cache.json")
ctx = ssl._create_unverified_context()
LOCK = threading.Lock()
STAT = {"ok": 0, "restored": 0, "nometa": 0, "fail": 0}

def probe(url):
    """正确探测：downloadCheck 需 userId 头"""
    hdrs = {"Range": "bytes=0-0", "Accept": "*/*"}
    if "downloadCheck" in url:
        hdrs["userId"] = "oplus-ota|16002018"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=25, context=ctx)
        cr = r.headers.get("Content-Range", "")
        md5 = (r.headers.get("x-amz-meta-filemd5") or "").strip('"')
        r.close()
        size = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else None
        return size, (md5 if len(md5) == 32 else None)
    except Exception:
        return None, None

def main():
    d = json.load(open(SITE))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    tasks = []
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url")
                if not u:
                    continue
                meta = v.get("meta") or {}
                
                if not meta.get("sizeBytes") or not meta.get("md5"):
                    tasks.append((m["code"], v, u))
    print(f"待实测 {len(tasks)} 条（用正确请求方式）", flush=True)

    def work(t):
        code, v, u = t
        size, md5 = probe(u)
        with LOCK:
            meta = v.setdefault("meta", {})
            if size:
                meta["sizeBytes"] = size
            if md5:
                meta["md5"] = md5
            if size or md5:
                cache[u] = {"size": size, "md5": md5}
                if size: STAT["restored"] += 1
            else:
                STAT["fail"] += 1
            done = STAT["restored"] + STAT["fail"] + STAT["nometa"]
            if done % 200 == 0:
                json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
                json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
                print(f"  {done}/{len(tasks)}: 恢复 {STAT['restored']} 失败 {STAT['fail']}", flush=True)
        time.sleep(0.15)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(work, tasks))
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成: 恢复 {STAT['restored']} | 失败 {STAT['fail']}")

if __name__ == "__main__":
    main()
