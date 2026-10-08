#!/usr/bin/env python3
"""逐版本实测 size+md5：Range 请求拿 Content-Range + x-amz-meta-filemd5，
与记录值比对，不一致则以实测值覆盖；实测取不到的删除该字段（绝不猜）。"""
import json, os, ssl, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "meta_cache.json")
ctx = ssl._create_unverified_context()
LOCK = threading.Lock()
STAT = {"ok": 0, "fixed": 0, "nometa": 0, "fail": 0}

def probe(url):
    try:
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        r = urllib.request.urlopen(req, timeout=20, context=ctx)
        cr = r.headers.get("Content-Range", "")
        md5 = (r.headers.get("x-amz-meta-filemd5") or "").strip('"')
        r.close()
        size = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else None
        if size and size < 500 * 1024 * 1024:
            size = None
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
                if not u or "/remove-" not in u:
                    continue
                tasks.append((m["code"], v, u))
    print(f"逐版本实测 {len(tasks)} 条", flush=True)

    def work(t):
        code, v, u = t
        size, md5 = probe(u)
        with LOCK:
            meta = v.setdefault("meta", {})
            old_size, old_md5 = meta.get("sizeBytes"), meta.get("md5")
            if size is None and md5 is None:
                if old_size or old_md5:
                    meta.pop("sizeBytes", None); meta.pop("md5", None)
                    STAT["nometa"] += 1
                else:
                    STAT["fail"] += 1
            else:
                changed = False
                if size and size != old_size:
                    meta["sizeBytes"] = size; changed = True
                elif size is None and old_size:
                    meta.pop("sizeBytes", None); changed = True
                if md5 and md5 != old_md5:
                    meta["md5"] = md5; changed = True
                elif md5 is None and old_md5:
                    meta.pop("md5", None); changed = True
                STAT["fixed" if changed else "ok"] += 1
            if size or md5:
                cache[u] = {"size": size, "md5": md5}
            done = sum(STAT.values())
            if done % 200 == 0:
                json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
                json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
                print(f"  {done}/{len(tasks)}: 核对一致 {STAT['ok']} 修正 {STAT['fixed']} 无元数据 {STAT['nometa']}", flush=True)
        time.sleep(0.2)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(work, tasks))
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成: 一致 {STAT['ok']} | 修正 {STAT['fixed']} | 无元数据删除 {STAT['nometa']} | 失败 {STAT['fail']}")

if __name__ == "__main__":
    main()
