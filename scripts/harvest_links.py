#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从目标站 harvest 历史版本直链：
  init(假captcha) → token → link → 直链 → 立即验证 PK → 存 links/{code}/{code}_{ver}.txt

覆盖：missing_from_lian.json 里我们有目录条目但无链接的版本。
限速：每版本 ~1.2s（init+link+验证），1774 个 ≈ 40 分钟。
"""
import json, os, re, sys, time, urllib.request, urllib.parse, http.cookiejar, ssl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
BRAND_MAP = None  # code -> brand，从 site_crawl 取

ctx = ssl._create_unverified_context()
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))


def session_warm():
    """过 Peekabo 握手"""
    for _ in range(3):
        raw = op.open(urllib.request.Request("https://catalog-source.local/", headers={"User-Agent": UA}), timeout=20).read()
        text = raw.decode(errors="ignore")
        if "UAM_CHECKING" not in text[:3000]:
            return
        m = re.search(r"var nonce = (\d+)", text)
        fl = [c.value for c in cj if c.name == "fl_ua_p"]
        if m and fl:
            nonce = int(m.group(1)); d = 12345
            for i in range(len(fl[0])):
                if re.match(r"[a-zA-Z0-9]", fl[0][i]): d += ord(fl[0][i]) * (nonce + i)
            op.open(urllib.request.Request("https://catalog-source.local/", data=urllib.parse.urlencode(
                {"sum": d, "nonce": nonce}).encode(),
                headers={"User-Agent": UA, "Content-type": "application/x-www-form-urlencoded",
                         "X-FL-UA-Step": "prev"}), timeout=20)
            time.sleep(4)


def get_token(brand, model, version):
    req = urllib.request.Request("https://catalog-source.local/proxy/init",
        data=json.dumps({"captchaVerifyParam": "auto", "brand": brand, "model": model, "version": version}).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/json"})
    r = op.open(req, timeout=25)
    return json.loads(r.read().decode()).get("token")


def get_link(brand, model, version, token):
    q = f"brand={urllib.parse.quote(brand)}&model={urllib.parse.quote(model)}&version={urllib.parse.quote(version)}"
    req = urllib.request.Request(f"https://catalog-source.local/proxy/roms/link?{q}",
        headers={"User-Agent": UA, "Authorization": f"Bearer {token}", "Accept": "application/json"})
    r = op.open(req, timeout=30)
    return json.loads(r.read().decode())


def verify_pk(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-3"}), timeout=25, context=ctx)
        return r.read(2) == b"PK"
    except Exception:
        return False


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--brand-filter")
    args = ap.parse_args()

    missing = json.load(open(os.path.join(ROOT, "config", "missing_from_lian.json")))
    site_crawl = json.load(open(os.path.join(ROOT, "config", "site_crawl.json")))
    brand_of = {}
    for b, ms in site_crawl.items():
        for m in ms:
            brand_of[m["code"]] = b

    # 任务清单：从目标站目录 API 现查原始 version 字符串（init 需要完整形态）
    tasks = []
    for code, vers in sorted(missing.items()):
        brand = brand_of.get(code, "OnePlus")
        try:
            req = urllib.request.Request(
                f"https://catalog-source.local/proxy/roms/versions?model={urllib.parse.quote(code)}&brand={urllib.parse.quote(brand)}",
                headers={"User-Agent": UA})
            d = json.loads(op.open(req, timeout=20).read().decode())
            if d.get("status") != "success":
                continue
            # 目标站原始 version → 我们的本地形态（去 ColorOS+model 前缀），只要本地缺的
            for item in d["data"]:
                full_ver = item["version"]
                local_ver = full_ver.replace("ColorOS ", "").replace(f"{code}_", "", 1)
                if local_ver in set(vers):
                    tasks.append((code, brand, full_ver))
        except Exception as e:
            print(f"  {code}: 目录拉取失败 {type(e).__name__}")
        time.sleep(0.4)
    if args.brand_filter:
        tasks = [t for t in tasks if t[1] == args.brand_filter]
    if args.limit:
        tasks = tasks[:args.limit]
    print(f"待 harvest 版本: {len(tasks)}")

    session_warm()
    ok = 0; fail = 0; no_link = 0
    done_set = set()
    for i, (code, brand, ver) in enumerate(tasks):
        # 目标站 version 带 model 前缀 + ColorOS
        ver_api = ver  # 完整形态（ColorOS {code}_{ver}）
        local_ver = ver.replace("ColorOS ", "").replace(f"{code}_", "", 1)
        fname = f"{code}_{local_ver.replace(' ', '_')}.txt"
        out = os.path.join(ROOT, "links", code, fname)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            continue
        print(f"[{i+1}/{len(tasks)}] {ver} ...", end=" ", flush=True)
        try:
            token = get_token(brand, code, ver_api)
            if not token:
                print("no token"); fail += 1; continue
            r = get_link(brand, code, ver_api, token)
            links = (r.get("data") or {}).get("links") or []
            if not links:
                print("无链接"); no_link += 1; time.sleep(0.3); continue
            link = links[0]
            # 验证可下载
            if verify_pk(link):
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(link + "\n")
                print(f"✓ 已存 ({len(link)}B)")
                ok += 1
            else:
                print("✗ 链接验证失败"); fail += 1
        except Exception as e:
            print(f"ERR {type(e).__name__}: {str(e)[:50]}"); fail += 1
            # 连接被重置时重新握手
            if "reset" in str(e).lower() or "10054" in str(e):
                time.sleep(5)
                try: session_warm()
                except Exception: pass
        time.sleep(0.4)
    print(f"\n完成: 成功 {ok} | 无链接 {no_link} | 失败 {fail}")


if __name__ == "__main__":
    main()
