
import json, os, re, ssl, sys, time, urllib.request, urllib.parse, http.cookiejar

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITE = os.path.join(ROOT, "site", "site.json")
CACHE = os.path.join(ROOT, "config", "meta_cache.json")
ctx = ssl._create_unverified_context()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
BASE = "https://roms.lian86.top"

BRAND_OF = {"P": "OnePlus", "O": "OPPO", "R": "Realme"}


def new_session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))
    for _ in range(5):
        try:
            raw = op.open(urllib.request.Request(BASE + "/", headers={"User-Agent": UA}), timeout=20).read()
            text = raw.decode(errors="ignore")
            if "UAM_CHECKING" not in text[:3000]:
                return op
            m = re.search(r"var nonce = (\d+)", text)
            fl = [c.value for c in cj if c.name == "fl_ua_p"]
            if m and fl:
                nonce = int(m.group(1)); d = 12345
                for i in range(len(fl[0])):
                    if re.match(r"[a-zA-Z0-9]", fl[0][i]):
                        d += ord(fl[0][i]) * (nonce + i)
                op.open(urllib.request.Request(BASE + "/", data=urllib.parse.urlencode({"sum": d, "nonce": nonce}).encode(),
                    headers={"User-Agent": UA, "Content-type": "application/x-www-form-urlencoded", "X-FL-UA-Step": "prev"}), timeout=20)
                time.sleep(4)
        except Exception:
            time.sleep(1)
    return None


def resign(op, brand, model, version):
    try:
        req = urllib.request.Request(BASE + "/proxy/init",
            data=json.dumps({"captchaVerifyParam": "auto", "brand": brand, "model": model, "version": version}).encode(),
            headers={"User-Agent": UA, "Content-Type": "application/json"})
        token = json.loads(op.open(req, timeout=25).read().decode()).get("token")
        if not token:
            return None
        q = f"brand={brand}&model={model}&version=" + urllib.parse.quote(version)
        req = urllib.request.Request(f"{BASE}/proxy/roms/link?{q}",
            headers={"User-Agent": UA, "Authorization": f"Bearer {token}"})
        r = json.loads(op.open(req, timeout=30).read().decode())
        links = r.get("data", {}).get("links", [])
        for ln in links:
            if "Expires=" in ln:
                return ln
        return None
    except Exception:
        return None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    d = json.load(open(SITE))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

    todo = []
    for b in d["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                u = v.get("url", "")
                if "compota-c" in u:
                    todo.append((b["key"], m["code"], v))
    if limit:
        todo = todo[:limit]
    print(f"待重签: {len(todo)}", flush=True)

    op = new_session()
    if not op:
        print("会话建立失败")
        return
    print("会话就绪", flush=True)

    ok = fail = 0
    t0 = time.time()
    for i, (brand, code, v) in enumerate(todo):
        if i and i % 40 == 0:
            op = new_session() or op
        # 目标站需要 "ColorOS {CODE}_{版本}(区域)" 格式
        ver_str = v["version"]
        if not ver_str.startswith("ColorOS " + code):
            ver_str = "ColorOS " + code + "_" + ver_str.replace("ColorOS ", "", 1)
        new_url = resign(op, brand, code, ver_str)
        if new_url:
            v["url"] = new_url
            # 探测 md5/size
            try:
                r = urllib.request.urlopen(urllib.request.Request(new_url, headers={"Range": "bytes=0-0"}), timeout=20, context=ctx)
                md5h = (r.headers.get("x-amz-meta-filemd5") or "").strip('"')
                cr = r.headers.get("Content-Range", "")
                r.close()
                meta = v.setdefault("meta", {})
                if len(md5h) == 32:
                    meta["md5"] = md5h
                if "/" in cr and cr.split("/")[-1].isdigit():
                    sz = int(cr.split("/")[-1])
                    if sz > 500 * 1024 * 1024:
                        meta["sizeBytes"] = sz
                cache[new_url] = {"size": meta.get("sizeBytes"), "md5": meta.get("md5", "")}
            except Exception:
                pass
            ok += 1
        else:
            fail += 1
        if (i + 1) % 25 == 0:
            json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
            json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
            print(f"  {i+1}/{len(todo)} | 重签 {ok} 失败 {fail} | {time.time()-t0:.0f}s", flush=True)
        time.sleep(0.8)

    json.dump(d, open(SITE, "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"完成: 重签 {ok} | 失败 {fail} | {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
