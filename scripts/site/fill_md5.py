
import json, os, ssl, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "meta_cache.json")
ctx = ssl._create_unverified_context()


def probe(url, tries=2):
    """探测 CDN 响应头：返回 (md5, size)。仅 CDN 有明确 md5 头时返回 md5。"""
    for _ in range(tries):
        hdrs = {"Range": "bytes=0-0"}
        if "downloadCheck" in url:
            hdrs["userId"] = "oplus-ota|16002018"
            hdrs["User-Agent"] = "okhttp/3.12.12"
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=hdrs), timeout=20, context=ctx)
            md5h = (r.headers.get("x-amz-meta-filemd5") or "").strip('"')
            cr = r.headers.get("Content-Range", "")
            r.close()
            size = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else None
            return (md5h if len(md5h) == 32 else None), size
        except Exception:
            time.sleep(0.5)
    return None, None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    d = json.load(open(SITE))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    todo = []
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url", "")
                if u and not (v.get("meta") or {}).get("md5"):
                    todo.append(v)
    if limit:
        todo = todo[:limit]
    print(f"待补 md5: {len(todo)} | 并发 {workers}", flush=True)

    ok = miss = 0
    t0 = time.time()

    def work(v):
        md5h, size = probe(v["url"])
        return v, md5h, size

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (v, md5h, size) in enumerate(ex.map(work, todo)):
            meta = v.setdefault("meta", {})
            if size and size > 500 * 1024 * 1024 and not meta.get("sizeBytes"):
                meta["sizeBytes"] = size
            if md5h:
                meta["md5"] = md5h
                cache[v["url"]] = {"size": meta.get("sizeBytes"), "md5": md5h}
                ok += 1
            else:
                miss += 1
            if (i + 1) % 200 == 0:
                json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
                json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
                print(f"  {i+1}/{len(todo)} | 补到 {ok} 无 {miss} | {time.time()-t0:.0f}s", flush=True)

    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成: 补到 {ok} | CDN 无 md5 {miss} | {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
