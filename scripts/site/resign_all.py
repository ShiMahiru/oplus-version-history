
import json, os, ssl, sys, time, urllib.request, urllib.parse, http.cookiejar, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "meta_cache.json")
ctx = ssl._create_unverified_context()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
BASE = "https://roms.lian86.top"

def brand_of(code):
    if code.startswith("RMX"): return "Realme"
    if code.startswith("OPD") or code.startswith("CPH"): return "OPPO"
    return "OnePlus"

def init_token(brand, model, version):
    req = urllib.request.Request(f"{BASE}/proxy/init",
        data=json.dumps({"captchaVerifyParam": "auto", "brand": brand, "model": model, "version": version}).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=20, context=ctx)
        return json.loads(r.read().decode()).get("token")
    except Exception:
        return None

def resign(brand, code, version):
    for _ in range(2):
        tk = init_token(brand, code, version)
        if not tk:
            continue
        q = f"brand={urllib.parse.quote(brand)}&model={urllib.parse.quote(code)}&version={urllib.parse.quote(version)}"
        req = urllib.request.Request(f"{BASE}/proxy/roms/link?{q}",
            headers={"User-Agent": UA, "Authorization": f"Bearer {tk}"})
        try:
            r = urllib.request.urlopen(req, timeout=25, context=ctx)
            links = json.loads(r.read().decode()).get("data", {}).get("links", [])
            for ln in links:
                if "Expires=" in ln:
                    return ln
            if links:
                return links[0]
        except Exception:
            pass
    return None

def probe(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-0"}), timeout=20, context=ctx)
        md5 = (r.headers.get("x-amz-meta-filemd5") or "").strip('"')
        cr = r.headers.get("Content-Range", "")
        r.close()
        size = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else None
        return (md5 if len(md5) == 32 else None), size
    except Exception:
        return None, None

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    only_expired = "--all" not in sys.argv
    d = json.load(open(SITE))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    todo = []
    now = time.time()
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url", "")
                meta = v.get("meta") or {}
                if not u:
                    continue
                expired = False
                if "Expires=" in u:
                    try:
                        exp = int(urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("Expires", [0])[0])
                        expired = exp < now + 1800
                    except Exception:
                        expired = True
                if not only_expired or expired or not meta.get("md5"):
                    todo.append((b["key"], m["code"], v, expired))
    if limit:
        todo = todo[:limit]
    print(f"待处理: {len(todo)}（含过期链接与缺 md5）", flush=True)

    ok = md5got = fail = 0
    t0 = time.time()
    for i, (brand, code, v, expired) in enumerate(todo):
        ver = v["version"]
        verstr = ver if ver.startswith("ColorOS " + code) else "ColorOS " + code + "_" + ver.replace("ColorOS ", "", 1)
        url = None
        if expired or "compota-c" in (v.get("url") or ""):
            url = resign(brand, code, verstr)
            if url:
                v["url"] = url
                ok += 1
        target = url or v.get("url")
        if target:
            md5, size = probe(target)
            meta = v.setdefault("meta", {})
            if md5:
                meta["md5"] = md5
                cache[target] = {"size": meta.get("sizeBytes"), "md5": md5}
                md5got += 1
            if size and size > 500 * 1024 * 1024:
                meta["sizeBytes"] = size
        else:
            fail += 1
        if (i + 1) % 50 == 0:
            json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
            json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
            print(f"  {i+1}/{len(todo)} | 重签 {ok} 补md5 {md5got} 失败 {fail} | {time.time()-t0:.0f}s", flush=True)
        time.sleep(0.4)

    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成: 重签 {ok} | 补 md5 {md5got} | 失败 {fail} | {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
