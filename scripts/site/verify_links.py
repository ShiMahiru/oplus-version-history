#!/usr/bin/env python3
"""实测欧加链接存活（正确头：gate 带 userId+UA，gauss 直链不带 UA）"""
import json, urllib.request, ssl, concurrent.futures

ctx = ssl._create_unverified_context()

def probe(url):
    headers = {"Range": "bytes=0-3"}
    if "downloadCheck" in url:
        headers["userId"] = "oplus-ota|16002018"
        headers["User-Agent"] = "okhttp/3.12.12"
    # gauss 直链：不带 UA（带任何 UA 都 403）
    try:
        req = urllib.request.Request(url, headers=headers)
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        data = r.read(4)
        alive = data[:2] == b"PK" or r.status in (200, 206)
        return (url, "alive" if alive else f"bad:{data[:4]!r}")
    except urllib.error.HTTPError as e:
        return (url, f"HTTP_{e.code}")
    except Exception as e:
        return (url, f"ERR_{type(e).__name__}")

d = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "site", "site.json")))
links = []
for b in d["brands"]:
    if b["key"] not in ("OnePlus", "OPPO", "Realme"): continue
    for m in b["models"]:
        for v in m.get("versions", []):
            if v.get("url"): links.append(v["url"])

print(f"共 {len(links)} 个链接")
results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    for i, (url, status) in enumerate(ex.map(probe, links)):
        results.append((url, status))
        if (i+1) % 100 == 0: print(f"  {i+1}/{len(links)}")

alive = [r for r in results if r[1] == "alive"]
dead = [r for r in results if r[1] != "alive"]
print(f"\n存活: {len(alive)} / {len(links)}")
print(f"失效: {len(dead)}")
for url, st in dead[:40]:
    print(f"  {st}: {url[:70]}")
json.dump({"alive": len(alive), "total": len(links), "dead": [{"status": s, "url": u} for u, s in dead]},
          open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "dead_links.json"), "w"), ensure_ascii=False, indent=2)
