#!/usr/bin/env python3
"""从 roms.danielspringer.at 增量同步新版本到本地档案。

用法:
  python3 scripts/sync_daniel.py                 # 同步（写链接 + 补日志）
  python3 scripts/sync_daniel.py --dry-run       # 只报告，不写任何文件
  python3 scripts/sync_daniel.py --arb           # 同时提取高通 ARB
  python3 scripts/sync_daniel.py --deploy        # 同步后构建并部署到 Cloudflare
  python3 scripts/sync_daniel.py --no-verify     # 跳过链接实测（快，但有风险）
  python3 scripts/sync_daniel.py --add-models    # 自动把新机型加入机型表
  python3 scripts/sync_daniel.py --all-regions   # 连海外版一起同步（默认只要 CN）

默认只同步国行（区域 CN / 版本号以 (CN01) 结尾）：
danielspringer 里 55 个海外机型（CPH 代号、EU/GLO 区域）一个 CN 版本都没有，
对只做国行的档案没有价值。

退出码: 0 成功 / 1 有失败项
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import update  # noqa: E402

API = "https://roms.danielspringer.at/api/ota.php"
CATALOG = os.path.join(ROOT, "config", "daniel_catalog.json")
CRAWL = os.path.join(ROOT, "config", "site_crawl.json")
ARB_CACHE = os.path.join(ROOT, "config", "arb_cache.json")
DEAD_URLS = os.path.join(ROOT, "config", "dead_urls.json")
PLAT_CACHE = os.path.join(ROOT, "config", "platform_cache.json")
CTX = ssl._create_unverified_context()

# 机型代号前缀 → 品牌（用于把 daniel 的新机型归到正确品牌）
BRAND_HINT = [
    (r"^RMX", "Realme"),
    (r"^(OPD|CPH|P[A-Z]{2}\d{3})", None),   # 需要看 device 名判断
]


def fetch_api():
    req = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def load_json(path, default=None):
    if os.path.isfile(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    return default


def guess_brand(code, device):
    """按 daniel 的 device 名称 + 代号前缀猜品牌"""
    d = (device or "").lower()
    if "realme" in d:
        return "Realme"
    if "oneplus" in d or d.startswith("op ") or re.match(r"^op\s*\d", d):
        return "OnePlus"
    if "oppo" in d:
        return "OPPO"
    if code.startswith("RMX"):
        return "Realme"
    return "OPPO"


def existing_versions(code):
    """从 links/{code}/ 读出已归档的版本名（不含 .txt）"""
    d = os.path.join(ROOT, "links", code)
    if not os.path.isdir(d):
        return set()
    return {f[:-4] for f in os.listdir(d) if f.endswith(".txt")}


def verify_link(url, md5, size):
    """Range 0-3 实测 + md5/size 对账。返回 (ok, 说明)"""
    for att in range(3):
        try:
            h = {"Range": "bytes=0-3"}
            if "downloadCheck" in url:
                h["userId"] = "oplus-ota|16002018"
            r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30, context=CTX)
            body = r.read(4)
            rmd5 = (r.headers.get("x-amz-meta-filemd5") or "").strip('"')
            r.close()
            if body[:2] != b"PK" and body[:1] != b"{":
                return False, "非 ZIP 响应"
            if rmd5 and md5 and rmd5.lower() != md5.lower():
                return False, "md5 不一致"
            return True, "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "HTTP404"
            if att == 2:
                return False, f"HTTP{e.code}"
            time.sleep(2)
        except Exception as e:
            if att == 2:
                return False, type(e).__name__
            time.sleep(2)
    return False, "未知"


def fix_changelog_header(code, fp, ver):
    """日志文件存在但缺标准头时补齐（缺头会导致 build_site_data 匹配不到）"""
    p = update.changelog_path(code, fp)
    if not os.path.isfile(p) or os.path.getsize(p) < 20:
        return False
    first = open(p, encoding="utf-8").readline()
    if first.startswith("# "):
        return False
    update.write_changelog(code, fp, ver, open(p, encoding="utf-8").read())
    return True


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    do_arb = "--arb" in args
    do_deploy = "--deploy" in args
    no_verify = "--no-verify" in args
    add_models = "--add-models" in args
    all_regions = "--all-regions" in args

    def is_cn(r):
        """默认只要国行：区域 CN 或版本号以 (CN01) 结尾"""
        if all_regions:
            return True
        if (r.get("region") or "").upper() == "CN":
            return True
        return str(r.get("version") or "").endswith("(CN01)")

    print("═" * 60)
    print("danielspringer 增量同步" + ("（演练模式）" if dry else ""))
    print("区域: " + ("全部" if all_regions else "仅国行 CN01"))
    print("═" * 60)

    # ── 1. 拉取线上数据
    print("\n[1/7] 拉取线上 API …", flush=True)
    try:
        data = fetch_api()
    except Exception as e:
        print(f"  ❌ 拉取失败: {type(e).__name__}: {e}")
        return 1
    rels = data.get("releases", [])
    print(f"  线上 {data.get('count')} 条 | catalog_updated_at {data.get('catalog_updated_at')}")

    # ── 2. 对比本地 catalog
    old = load_json(CATALOG, {}) or {}
    old_ids = {r.get("id") for r in old.get("releases", [])}
    added_ids = [r for r in rels if r.get("id") not in old_ids]
    print(f"  本地 catalog {len(old.get('releases', []))} 条 | 新增 {len(added_ids)} 条")

    # ── 3. 找出可同步的版本
    print("\n[2/7] 计算待同步版本 …", flush=True)
    crawl = load_json(CRAWL, {}) or {}
    our_models = {}          # code -> brand
    for brand in ("OnePlus", "OPPO", "Realme"):
        for m in crawl.get(brand, []):
            our_models[m["code"]] = brand

    dead = set(load_json(DEAD_URLS, []) or [])
    if dead:
        print(f"  已知死链 {len(dead)} 条（自动跳过）")

    candidates, unknown_models = [], {}
    for r in rels:
        code = r.get("model") or ""
        ver = r.get("version") or ""
        if not (code and ver and r.get("source_url") and r.get("md5") and r.get("ota_version")):
            continue
        if r["source_url"] in dead:
            continue
        if not is_cn(r):
            continue
        if code not in our_models:
            if is_cn(r):
                unknown_models.setdefault(code, r)
            continue
        if ver in existing_versions(code):
            continue
        candidates.append(r)

    print(f"  可同步版本: {len(candidates)}")
    if unknown_models:
        print(f"  机型表里没有的机型: {len(unknown_models)} 个")
        for c, r in list(unknown_models.items())[:10]:
            print(f"    {c:10s} {r.get('device', '?'):26s} {r.get('version', '')[:26]}")
        if add_models:
            for c, r in unknown_models.items():
                brand = guess_brand(c, r.get("device"))
                crawl.setdefault(brand, []).append({"code": c, "name": r.get("device") or c})
                print(f"    + 加入 {brand}: {c} {r.get('device')}")
            if not dry:
                json.dump(crawl, open(CRAWL, "w"), ensure_ascii=False, indent=1)
            # 重新计算
            for brand in ("OnePlus", "OPPO", "Realme"):
                for m in crawl.get(brand, []):
                    our_models[m["code"]] = brand
            candidates = [r for r in rels
                          if r.get("model") in our_models
                          and r.get("source_url") and r.get("md5") and r.get("ota_version")
                          and r["source_url"] not in dead
                          and is_cn(r)
                          and r.get("version") not in existing_versions(r.get("model"))]
            print(f"  加入后待同步: {len(candidates)}")

    if not candidates:
        print("\n没有需要同步的新版本。")
        if not dry and added_ids:
            json.dump(data, open(CATALOG, "w"), ensure_ascii=False)
            print("（catalog 已更新）")
        return 0

    for r in candidates:
        print(f"    + {r['model']:9s} {r['version']}")

    if dry:
        print("\n演练模式，不写任何文件。")
        return 0

    # ── 4. 链接实测
    print("\n[3/7] 链接实测 …", flush=True)
    good = []
    for i, r in enumerate(candidates):
        if no_verify:
            good.append(r)
            continue
        ok, why = verify_link(r["source_url"], r.get("md5"), r.get("size"))
        print(f"  {'✅' if ok else '❌'} {r['model']:9s} {r['version'][:30]:32s} {why}")
        if ok:
            good.append(r)
        time.sleep(0.3)
    print(f"  通过 {len(good)}/{len(candidates)}")

    # ── 5. 写入链接 + 版本史
    print("\n[4/7] 写入链接与版本史 …", flush=True)
    w = h = 0
    for r in good:
        code, ver = r["model"], r["version"]
        try:
            update.write_link(code, ver, r["source_url"], r.get("size"), r.get("md5"),
                              r.get("security_patch"), r["ota_version"])
            w += 1
            hist = update.read_history(code)
            if r["ota_version"] not in hist:
                hist[r["ota_version"]] = ver
                update.write_history(code, hist)
                h += 1
        except Exception as e:
            print(f"  ❌ {code} {ver}: {type(e).__name__}")
    print(f"  链接 {w} | 版本史 {h}")

    # ── 6. 更新日志
    print("\n[5/7] 获取官方更新日志 …", flush=True)
    cl_ok = cl_skip = cl_fail = 0
    for r in good:
        code, ver, fp = r["model"], r["version"], r["ota_version"]
        if fix_changelog_header(code, fp, ver):
            print(f"  🔧 补标准头 {code} {ver[:26]}")
            cl_ok += 1
            continue
        m = re.match(r"^([A-Z0-9]+_\d+\.[A-Z]\.\d+_\d+)_", fp)
        if not m:
            cl_fail += 1
            continue
        try:
            rr = update.changelog_query(code, m.group(1), "cn")
            if rr and rr[1] and len(rr[1].strip()) > 20:
                update.write_changelog(code, fp, ver, rr[1])
                print(f"  ✅ {code} {ver[:26]} ({len(rr[1])}字)")
                cl_ok += 1
            else:
                print(f"  ⚠️ {code} {ver[:26]} 官方无日志")
                cl_skip += 1
        except Exception as e:
            print(f"  ❌ {code} {ver[:26]} {type(e).__name__}")
            cl_fail += 1
        time.sleep(update.GAP)
    print(f"  取到 {cl_ok} | 无日志 {cl_skip} | 失败 {cl_fail}")

    # ── 7. ARB（可选）
    if do_arb:
        print("\n[6/7] 提取高通 ARB …", flush=True)
        import ota_extract as oe
        import arb_extract as ae
        arb_cache = load_json(ARB_CACHE, {}) or {}
        plat = load_json(PLAT_CACHE, {}) or {}
        got = 0
        for r in good:
            code = r["model"]
            if plat.get(code) == "mediatek":
                continue
            key = f"{code}|{r['version']}"
            if key in arb_cache:
                continue
            try:
                import tempfile
                direct = oe.resolve_direct(r["source_url"]) if "downloadCheck" in r["source_url"] else r["source_url"]
                reader = manifest = None
                for no_ua in (True, False):
                    try:
                        reader, manifest = oe.open_payload(direct, no_ua=no_ua)
                        break
                    except Exception:
                        continue
                if manifest is None:
                    raise RuntimeError("open_payload")
                names = {p["name"] for p in manifest["partitions"]}
                if "xbl_config" in names:
                    p = next(x for x in manifest["partitions"] if x["name"] == "xbl_config")
                    with tempfile.TemporaryDirectory() as tmp:
                        raw = open(oe.extract(reader, manifest, p, tmp), "rb").read()
                    res = ae.parse_arb(raw)
                    if res:
                        major, minor, arb = res
                        arb_cache[key] = {"arb": arb, "major": major, "minor": minor,
                                          "status": "Safe" if arb == 0 else "Protected"}
                        got += 1
                        print(f"  ✅ {code} {r['version'][:26]} ARB={arb}")
                elif "lk" in names or "preloader_raw" in names:
                    plat[code] = "mediatek"
                    print(f"  ○ {code} {r['version'][:26]} MTK")
            except Exception as e:
                print(f"  ❌ {code} {r['version'][:26]} {type(e).__name__}")
            time.sleep(0.3)
        json.dump(arb_cache, open(ARB_CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
        json.dump(plat, open(PLAT_CACHE, "w"), ensure_ascii=False, separators=(",", ":"))
        print(f"  提取 {got} 个")

    # ── 更新 catalog
    json.dump(data, open(CATALOG, "w"), ensure_ascii=False)
    print(f"\n[7/7] catalog 已更新为 {data.get('count')} 条")

    # ── 重建
    print("\n重建站点数据 …", flush=True)
    import subprocess
    for step in ("scripts/site/build_site_data.py", "scripts/site/merge_arb_full.py"):
        r = subprocess.run([sys.executable, os.path.join(ROOT, step)], capture_output=True, text=True)
        tail = (r.stdout.strip().split("\n") or [""])[-1]
        print(f"  {'✅' if r.returncode == 0 else '❌'} {os.path.basename(step)}: {tail}")

    if do_deploy:
        print("\n部署到 Cloudflare …", flush=True)
        web = os.path.join(os.path.dirname(ROOT), "romcloud-web")
        if not os.path.isdir(web):
            print(f"  ❌ 找不到 {web}")
            return 1
        import shutil
        shutil.copyfile(os.path.join(ROOT, "site", "index.json"),
                        os.path.join(web, "frontend", "data", "index.json"))
        vdir = os.path.join(web, "frontend", "data", "versions")
        shutil.rmtree(vdir, ignore_errors=True)
        shutil.copytree(os.path.join(ROOT, "site", "versions"), vdir)
        r = subprocess.run([sys.executable, "scripts/build_static.py"], cwd=web, capture_output=True, text=True)
        print(f"  {'✅' if r.returncode == 0 else '❌'} build_static")
        env = dict(os.environ)
        env.setdefault("CLOUDFLARE_API_TOKEN", "cfut_EDSYBWrC8CULpy9g6nCm2OdEsGn8mawXWj8giUaY81c2d9cc")
        env.setdefault("CLOUDFLARE_ACCOUNT_ID", "bf425e3b280e5facebdad91a7d665576")
        wr = os.path.join(web, "node_modules", ".bin", "wrangler")
        cmd = [wr, "deploy"] if os.path.exists(wr) else ["npx", "wrangler", "deploy"]
        r = subprocess.run(cmd, cwd=web, capture_output=True, text=True, env=env)
        out = [l for l in r.stdout.split("\n") if "Version ID" in l or "workers.dev" in l]
        print("  " + ("\n  ".join(out) if out else f"❌ 部署失败: {r.stderr[-200:]}"))

    print("\n" + "═" * 60)
    print(f"完成: 新增 {w} 个版本 | 日志 {cl_ok} | 失败 {cl_fail}")
    print("═" * 60)
    return 0 if cl_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
