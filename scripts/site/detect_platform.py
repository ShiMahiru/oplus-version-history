
import json, os, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "platform_cache.json")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ota_extract as oe

def detect(url):
    """通过分区结构判断平台：有 xbl_config = 高通，有 lk/preloader = MTK"""
    direct = oe.resolve_direct(url) if "downloadCheck" in url else url
    
    for no_ua in (True, False):
        try:
            reader, manifest = oe.open_payload(direct, no_ua=no_ua)
            break
        except Exception:
            if no_ua is False:
                return None
            continue
    else:
        return None
    names = set(p["name"] for p in manifest["partitions"])
    try:
        if "xbl_config" in names:
            return "qualcomm"
        if "lk" in names or "preloader_raw" in names:
            return "mediatek"
        if "preloader" in names:
            return "mediatek"
        return "unknown"
    except Exception:
        return None

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    d = json.load(open(SITE))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    
    todo = []
    for b in d["brands"]:
        for m in b["models"]:
            if m["code"] in cache:
                continue
            for v in m["versions"]:
                if (v.get("meta") or {}).get("arb") is None and v.get("url"):
                    todo.append((m["code"], v["url"]))
                    break
    if limit:
        todo = todo[:limit]
    print(f"待检测平台: {len(todo)}", flush=True)

    ok = 0
    t0 = time.time()
    for i, (code, url) in enumerate(todo):
        plat = detect(url)
        if plat:
            cache[code] = plat
            ok += 1
        if (i + 1) % 10 == 0:
            json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
            print(f"  {i+1}/{len(todo)} | {ok} 已识别 | {time.time()-t0:.0f}s", flush=True)
        time.sleep(0.3)

    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成: {ok}/{len(todo)}")
    from collections import Counter
    print(Counter(cache.values()))

if __name__ == "__main__":
    main()
