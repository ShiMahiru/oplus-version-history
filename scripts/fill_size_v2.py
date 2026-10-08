#!/usr/bin/env python3
"""sizeBytes 补全 v2：串行温和 + 重试 + 区分真死（4xx）与网络误判（超时/重置不判死）"""
import json, os, ssl, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site", "site.json")
ctx = ssl._create_unverified_context()

def probe(url):
    """返回 (size, is_permanent_dead)"""
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
            r = urllib.request.urlopen(req, timeout=20, context=ctx)
            cr = r.headers.get("Content-Range", ""); r.close()
            if "/" in cr and cr.split("/")[-1].isdigit():
                return int(cr.split("/")[-1]), False
            cl = r.headers.get("Content-Length")
            if cl and cl.isdigit(): return int(cl), False
            return None, False
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return None, True
            return None, False
        except Exception:
            time.sleep(2)
    return None, False

def main():
    d = json.load(open(SITE))
    tasks = []
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url")
                if u and not (v.get("meta") or {}).get("sizeBytes"):
                    tasks.append((u, v))
    print(f"待探测 {len(tasks)} 条（串行 0.4s 间隔 + 重试）")
    ok = dead = 0
    dead_urls = []
    for i, (url, v) in enumerate(tasks):
        size, is_dead = probe(url)
        if size:
            meta = v.get("meta") or {}
            meta["sizeBytes"] = size
            v["meta"] = meta
            ok += 1
        elif is_dead:
            dead += 1; dead_urls.append(url)
        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(tasks)}: ✓{ok} 真死{dead}", flush=True)
            json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
        time.sleep(0.4)
    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(sorted(set(dead_urls)), open(os.path.join(ROOT, "config", "dead_links.json"), "w"), indent=1)
    print(f"完成: ✓{ok} | 真死{dead} | sizeBytes 覆盖 {sum(1 for b in d['brands'] for m in b['models'] for v in m['versions'] if (v.get('meta') or {}).get('sizeBytes'))}")

if __name__ == "__main__":
    main()
