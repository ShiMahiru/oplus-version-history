

import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

crawl = json.load(open(os.path.join(ROOT, "config", "site_crawl.json")))
OUT = os.path.join(ROOT, "site", "site.json")

def load_fp_to_version(code):
    fp2ver = {}
    p = os.path.join(ROOT, "models", code, "ota-version.txt")
    if not os.path.exists(p): return fp2ver
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        m = re.match(r'^(\S+)\s+#\s*ColorOS:\s*(\S+)', line)
        if m:
            fp2ver[m.group(1)] = m.group(2)
    return fp2ver

def load_changelog(code):
    fp2cl = {}
    cdir = os.path.join(ROOT, "models", code, "changelog")
    if not os.path.isdir(cdir): return fp2cl
    for f in os.listdir(cdir):
        if not f.endswith(".md"): continue
        fp = f[:-3]
        fp2cl[fp] = open(os.path.join(cdir, f), encoding="utf-8").read()
    return fp2cl

def build_versions(code):
    fp2cl = load_changelog(code)
    fp2ver = load_fp_to_version(code)
    cl_fp_to_ver = {}
    for cl_fp, content in fp2cl.items():
        head_m = re.search(r"^#\s*(\S+)", content, re.M)
        if head_m and code not in head_m.group(1):
            continue
        for full_fp, ver in fp2ver.items():
            if full_fp.startswith(cl_fp):
                cl_fp_to_ver[ver] = content
                break

    versions = []
    seen_versions = set()
    links_dir = os.path.join(ROOT, "links", code)
    if not os.path.isdir(links_dir): links_dir = None
    if links_dir:
        for t in sorted(os.listdir(links_dir)):
            if not t.endswith(".txt"): continue
            name = t[:-4]
            m = re.match(rf"^{re.escape(code)}_(.+?)\(([A-Z0-9]+)\)$", name)
            ver = m.group(1) if m else name[len(code):].lstrip("_")
            region = m.group(2) if m else ""
            _raw = open(os.path.join(links_dir, t), encoding="utf-8").read()
            _lines = [l.strip() for l in _raw.split("\n") if l.strip()]
            url = _lines[0].replace(" ", "") if _lines else ""
            changelog = cl_fp_to_ver.get(f"{code}_{ver}({region})", "")
            versions.append({
                "version": f"ColorOS {ver}({region})",
                "region": region,
                "url": url,
                "changelog": changelog,
            })
            seen_versions.add(f"{code}_{ver}({region})")
    for ver_name in cl_fp_to_ver:
        if ver_name in seen_versions:
            continue
        mm = re.match(rf"^{re.escape(code)}_(.+?)\(([A-Z0-9]+)\)$", ver_name)
        if not mm:
            continue
        if re.search(r"[A-Z]{2,5}\d{3,4}", mm.group(1)):
            continue
        versions.append({
            "version": f"ColorOS {mm.group(1)}({mm.group(2)})",
            "region": mm.group(2),
            "url": "",
            "changelog": cl_fp_to_ver[ver_name],
        })
        seen_versions.add(ver_name)
    versions.sort(key=lambda v: (str((v.get("meta") or {}).get("buildDate") or ""), ver_key(v["version"])), reverse=True)
    return versions

def ver_key(vstr):
    m = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', vstr)
    if m: return tuple(int(x) for x in m.groups())
    m2 = re.search(r'(\d+)_(\d+)\.(\d+)\.(\d+)', vstr)
    if m2: return tuple(int(x) for x in m2.groups())
    return (0, 0, 0, 0)

KEEP = ("OnePlus", "OPPO", "Realme")
site = {"brands": []}
for key in KEEP:
    brand_obj = {"key": key, "models": []}
    for m in crawl.get(key, []):
        code = m["code"]
        versions = build_versions(code)
        if not versions:
            continue
        brand_obj["models"].append({"code": code, "name": m["name"], "versions": versions})
    site["brands"].append(brand_obj)

dead_path = os.path.join(ROOT, "config", "dead_links.json")
if os.path.exists(dead_path):
    dead_raw = json.load(open(dead_path)); dead_urls = {x["url"] if isinstance(x, dict) else x for x in (dead_raw["dead"] if isinstance(dead_raw, dict) else dead_raw)}
    for b in site["brands"]:
        for m in b["models"]:
            m["versions"] = [v for v in m["versions"] if v.get("url") not in dead_urls]
        b["models"] = [m for m in b["models"] if m.get("versions")]

DEV = json.load(open(os.path.join(ROOT, "config", "devices.json")))
PN = json.load(open(os.path.join(ROOT, "config", "pn_ref.json")))["models"]
NV_MAP = {"CN": "NV97", "GLO": "NVA7", "IN": "NV1B", "EU": "NV44"}
def nv_of(region):
    r = (region or "").upper()
    for k in NV_MAP:
        if r.startswith(k[:2]):
            return NV_MAP[k]
    return ""

dev_meta = {}
for _m in DEV["models"]:
    for _v in _m.get("variants", []):
        if _v.get("code"):
            dev_meta.setdefault(_v["code"], {})[_v.get("region", "")] = _v

def build_date(fp):
    if not fp or "197001010000" in fp:
        return ""

    m = re.search(r"_(\d{8})(?:\d{4})?$", fp)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return ""

for b in site["brands"]:
    for model in b["models"]:
        code = model["code"]
        variants = dev_meta.get(code, {})
        prj = (PN.get(code) or {}).get("prj", "")
        for v in model["versions"]:
            ver = v["version"]
            rm = re.search(r"\(([A-Z0-9]+)\)", ver)
            region = rm.group(1) if rm else ""
            vm = re.search(r"(\d+\.\d+\.\d+\.\d+)", ver)
            pure = vm.group(1) if vm else ""
            meta_match = None
            for _rg, _vv in variants.items():
                if (_vv.get("latest") or "").startswith(f"{code}_{pure}"):
                    meta_match = _vv
                    break
            target = ""
            if v.get("changelog"):
                fm = re.search(r"OTA 指纹: `([^`]+)`", v["changelog"])
                if fm:
                    target = fm.group(1).strip()
            v.setdefault("meta", {})
            v["meta"].update({
                "android": ((meta_match.get("android") if meta_match else "") or v["meta"].get("android", "")),
                "securityPatch": ((meta_match.get("securityPatch") if meta_match else "") or v["meta"].get("securityPatch", "")),
                "sizeBytes": (meta_match.get("sizeBytes", 0) if meta_match else 0) or v["meta"].get("sizeBytes", 0),
                "md5": ((meta_match.get("md5") if meta_match else "") or v["meta"].get("md5", "")),
                "nv": v["meta"].get("nv", ""),
                "projectId": prj or v["meta"].get("projectId", ""),
                "buildDate": build_date(target) or v["meta"].get("buildDate", ""),
                "targetVersion": target or v["meta"].get("targetVersion", ""),
            })

import re as _re
DG_RE = _re.compile(
    r"###\s+(\S+)\n- Android: (\S+)\n- 大小: (\d+)\n- MD5: (\S+)\n- 链接: (\S+)")
for b in site["brands"]:
    for m in b["models"]:
        dg_path = os.path.join(ROOT, "downgrade", m["code"] + ".txt")
        if not os.path.isfile(dg_path):
            continue
        text = open(dg_path, encoding="utf-8").read()
        for coloros_ver, android, size, md5, url in DG_RE.findall(text):
            ver_name = f"降级包 {coloros_ver}(CN)"
            if any(v["url"] == url for v in m["versions"]):
                continue
            m["versions"].append({
                "version": ver_name,
                "region": "CN",
                "url": url,
                "changelog": "",
                "meta": {"android": android.replace("Android", "Android ").strip(), "sizeBytes": int(size), "md5": md5,
                         "targetVersion": "", "dgTarget": coloros_ver},
            })

def patch_from_changelog(cl):
    if not cl:
        return ""
    m = re.search(r"安全补丁[至到]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", cl)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"安全补丁[至到]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月", cl)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(?:Android)?\s*安全补丁", cl)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"安全补丁[^\d]{0,12}[（(]\s*(20\d{2})\s*[#＃]\s*(\d{1,2})\s*[）)]", cl)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.search(r"安全补丁[^\d]{0,12}(20\d{2})\s*[-/]\s*(\d{1,2})", cl)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m2 = re.search(r"(?:security patch|patch level)[^\d]{0,20}(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", cl, re.I)
    if m2:
        return f"{m2.group(1)}-{int(m2.group(2)):02d}-{int(m2.group(3)):02d}"
    return ""

for b in site["brands"]:
    for model in b["models"]:
        for v in model["versions"]:
            if not (v.get("meta") or {}).get("securityPatch"):
                p = patch_from_changelog(v.get("changelog", ""))
                if p:
                    v.setdefault("meta", {})["securityPatch"] = p

_dan = {}
_dan_ota = {}
_dan_src = {}
try:
    _cat = json.load(open(os.path.join(ROOT, "config", "daniel_catalog.json")))
    for _r in _cat.get("releases", []):
        if _r.get("md5") or _r.get("security_patch") or _r.get("size"):
            _dan[(_r["model"], _r["version"])] = (_r.get("md5"), _r.get("size"), _r.get("security_patch"))
        if _r.get("ota_version"):
            _dan_ota[_r["ota_version"]] = _r
        if _r.get("source_url"):
            _dan_src[_r["source_url"]] = _r
except Exception:
    pass

for b in site["brands"]:
    for model in b["models"]:
        for v in model["versions"]:
            meta = v.setdefault("meta", {})
            if meta.get("md5"):
                continue
            ver = v["version"].replace("ColorOS ", "")
            _fp = meta.get("targetVersion", "")
            _u = v.get("url", "")
            _rec = _dan_ota.get(_fp) or _dan_src.get(_u)
            if _rec:
                if not meta.get("securityPatch") and _rec.get("security_patch"):
                    meta["securityPatch"] = _rec["security_patch"]
                if not meta.get("md5") and _rec.get("md5"):
                    meta["md5"] = _rec["md5"]
                if not meta.get("sizeBytes") and _rec.get("size"):
                    try: meta["sizeBytes"] = int(_rec["size"])
                    except Exception: pass
                if not meta.get("buildDate") and _rec.get("build_timestamp"):
                    meta["buildDate"] = str(_rec["build_timestamp"])[:10]
                if not meta.get("published") and _rec.get("published"):
                    try: meta["published"] = int(_rec["published"])
                    except Exception: pass
                if not meta.get("versionCode") and _rec.get("version_code"):
                    meta["versionCode"] = _rec["version_code"]
                continue
            hit = _dan.get((model["code"], f"{model['code']}_{ver}"))
            if hit:
                if not meta.get("md5") and hit[0]:
                    meta["md5"] = hit[0]
                if not meta.get("sizeBytes") and hit[1]:
                    meta["sizeBytes"] = int(hit[1])
                if not meta.get("securityPatch") and len(hit) > 2 and hit[2]:
                    meta["securityPatch"] = hit[2]

_lian_path = os.path.join(ROOT, "config", "catalog_versions.json")
if os.path.exists(_lian_path):
    _lian = json.load(open(_lian_path))
    for b in site["brands"]:
        for model in b["models"]:
            code = model["code"]
            for ver in _lian.get(code, []):
                ver_clean = ver.replace(f"{code}_", "", 1) if ver.startswith(f"{code}_") else ver
                rm = re.search(r"\(([A-Z0-9]+)\)", ver_clean)
                region = rm.group(1) if rm else "CN"
                disp = f"ColorOS {ver_clean}" if not rm else f"ColorOS {ver_clean}"
                if any(v["version"] == disp for v in model["versions"]):
                    continue
                model["versions"].append({
                    "version": disp,
                    "region": region,
                    "url": "",
                    "changelog": "",
                                    })

def nv_of(region):
    r = (region or "").upper()
    for k in NV_MAP:
        if r.startswith(k[:2]):
            return NV_MAP[k]
    return ""

for b in site["brands"]:
    for model in b["models"]:
        val = ""
        for v in model["versions"]:
            if (v.get("meta") or {}).get("android"):
                val = v["meta"]["android"]
                break
        for v in model["versions"]:
            v.setdefault("meta", {})
            if not v["meta"].get("nv"):
                rm = re.search(r"\(([A-Z0-9]+)\)", v["version"])
                v["meta"]["nv"] = nv_of(rm.group(1) if rm else "CN")
            if not v["meta"].get("projectId"):
                v["meta"]["projectId"] = (PN.get(model["code"]) or {}).get("prj", "")
            if val:
                v["meta"]["android"] = v["meta"].get("android") or val

for b in site["brands"]:
    for m in b["models"]:
        for idx, v in enumerate(m["versions"]):
            if v.get("url"):
                v["tags"] = ["降级包" if "downgradefs.coloros.com" in v["url"] else "全量包"]
            else:
                v["tags"] = ["待补链接"]

for b in site["brands"]:
    b["models"].sort(
        key=lambda m: ver_key(m["versions"][0]["version"]) if m["versions"] else (0, 0, 0, 0),
        reverse=True,
    )

CODE_RE2 = re.compile(r"[A-Z]{2,5}\d{3,4}")
for b in site["brands"]:
    keep_models = []
    for m in b["models"]:
        code = m["code"]
        clean_versions = []
        for v in m["versions"]:
            ver = v["version"]
            seg = ver.replace("ColorOS ", "").replace("OxygenOS ", "")
            seg = seg[len(code) + 1:] if seg.startswith(code + "_") else seg
            others = [c for c in CODE_RE2.findall(seg) if c != code]
            same_family = all(c[:2] == code[:2] or c[:3] == code[:3] for c in others)
            bad = bool(others) and not same_family
            if not bad:
                clean_versions.append(v)
        m["versions"] = clean_versions
        if m["versions"]:
            keep_models.append(m)
    b["models"] = keep_models

_size_cache_path = os.path.join(ROOT, "config", "size_cache.json")
if os.path.exists(_size_cache_path):
    _size_cache = json.load(open(_size_cache_path))
    for b in site["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                _u = v.get("url")
                if _u and _u in _size_cache and not (v.get("meta") or {}).get("sizeBytes"):
                    v.setdefault("meta", {})["sizeBytes"] = _size_cache[_u]

MIN_ROM_SIZE = 500 * 1024 * 1024
for b in site["brands"]:
    for m in b["models"]:
        for v in m["versions"]:
            meta = v.get("meta") or {}
            sb = meta.get("sizeBytes")
            if sb and isinstance(sb, int) and sb < MIN_ROM_SIZE:
                del meta["sizeBytes"]

for b in site["brands"]:
    for m in b["models"]:
        for v in m["versions"]:
            _u = v.get("url", "")
            if not _u:
                continue
            
            _link_file = None
            for _ext in [".txt"]:
                _lf = os.path.join(ROOT, "links", m["code"], f"{m['code']}_" + v["version"].replace("ColorOS ", "").replace(m["code"] + "_", "", 1).replace(" ", "_") + _ext)
                if os.path.exists(_lf):
                    _link_file = _lf
                    break
            if not _link_file:
                continue
            _lines = [l.strip() for l in open(_link_file, encoding="utf-8").read().split("\n") if l.strip()]
            meta = v.setdefault("meta", {})
            for _l in _lines[1:]:
                if _l.startswith("size:") and not meta.get("sizeBytes"):
                    _sv = _l[5:].strip()
                    if _sv.isdigit(): meta["sizeBytes"] = int(_sv)
                elif _l.startswith("md5:") and not meta.get("md5"):
                    meta["md5"] = _l[4:].strip()
                elif _l.startswith("patch:") and not meta.get("securityPatch"):
                    meta["securityPatch"] = _l[6:].strip()
                elif _l.startswith("fp:"):
                    meta["targetVersion"] = _l[3:].strip()
                    _dm = re.search(r"_(\d{12})$", _l[3:].strip())
                    if _dm and not meta.get("buildDate"):
                        _ts = _dm.group(1)
                        meta["buildDate"] = f"{_ts[:4]}-{_ts[4:6]}-{_ts[6:8]}"

_meta_cache_path = os.path.join(ROOT, "config", "meta_cache.json")
if os.path.exists(_meta_cache_path):
    _meta_cache = json.load(open(_meta_cache_path))
    for b in site["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                _u = v.get("url", "")
                if _u and _u in _meta_cache:
                    _hit = _meta_cache[_u]
                    meta = v.setdefault("meta", {})
                    if _hit.get("size") and not meta.get("sizeBytes"):
                        meta["sizeBytes"] = _hit["size"]
                    if _hit.get("md5") and not meta.get("md5"):
                        meta["md5"] = _hit["md5"]

for b in site["brands"]:
    for m in b["models"]:
        m["versions"] = [
            v for v in m["versions"]
            if (v.get("meta") or {}).get("md5") and v.get("url") and (v.get("changelog") or "").strip()
        ]
    b["models"] = [m for m in b["models"] if m["versions"]]

_dead_path = os.path.join(ROOT, "config", "dead_urls.json")
if os.path.exists(_dead_path):
    try:
        _dead = set(json.load(open(_dead_path)))
    except Exception:
        _dead = set()
    if _dead:
        for b in site["brands"]:
            for m in b["models"]:
                m["versions"] = [v for v in m["versions"] if v.get("url") not in _dead]

_arb_cache_path = os.path.join(ROOT, "config", "arb_cache.json")
if os.path.exists(_arb_cache_path):
    try:
        _arb_cache = json.load(open(_arb_cache_path))
    except Exception:
        _arb_cache = {}
    if _arb_cache:
        for b in site["brands"]:
            for m in b["models"]:
                for v in m["versions"]:
                    _k = f"{m['code']}|{v['version']}"
                    _hit = _arb_cache.get(_k)
                    if _hit and _hit.get("arb") is not None:
                        meta = v.setdefault("meta", {})
                        meta["arb"] = _hit["arb"]
                        meta["arbMajor"] = _hit.get("major")
                        meta["arbMinor"] = _hit.get("minor")
                        meta["arbStatus"] = _hit.get("status") or ("Safe" if _hit["arb"] == 0 else "Protected")

_plat_path = os.path.join(ROOT, "config", "platform_cache.json")
if os.path.exists(_plat_path):
    try:
        _plat = json.load(open(_plat_path))
    except Exception:
        _plat = {}
    if _plat:
        for b in site["brands"]:
            for m in b["models"]:
                _p = _plat.get(m["code"])
                if not _p:
                    continue
                for v in m["versions"]:
                    meta = v.setdefault("meta", {})
                    if meta.get("arb") is None:
                        meta["platform"] = _p
                        if _p == "mediatek":
                            meta["arbNote"] = "联发科平台，ARB 存于硬件熔丝，ROM 包内不含"

def _real_cl(cl):
    t = re.sub(r"^#[^\n]*\n?", "", cl or "")
    t = re.sub(r"^>[^\n]*\n?", "", t, flags=re.M)
    t = re.sub(r"[\s。．.]", "", t)
    if not t:
        return False
    if t.startswith("官方无更新日志"):
        return False
    return len(t) > 10

for b in site["brands"]:
    for m in b["models"]:
        m["versions"] = [v for v in m["versions"] if _real_cl(v.get("changelog"))]
    b["models"] = [m for m in b["models"] if m["versions"]]

# 发布日期优先使用官方 published 毫秒时间戳；缺失时回退编译日期，再回退版本号。
def _release_key(v):
    meta = v.get("meta") or {}
    published = meta.get("published")
    if published:
        try:
            return (3, int(published), ver_key(v.get("version", "")))
        except (TypeError, ValueError):
            pass
    build_date = meta.get("buildDate") or ""
    if build_date:
        return (2, build_date, ver_key(v.get("version", "")))
    return (1, "", ver_key(v.get("version", "")))

for b in site["brands"]:
    for m in b["models"]:
        full = [v for v in m["versions"] if "降级包" not in v["version"]]
        dg = [v for v in m["versions"] if "降级包" in v["version"]]
        full.sort(key=_release_key, reverse=True)
        dg.sort(key=_release_key, reverse=True)
        m["versions"] = full + dg
    b["models"].sort(
        key=lambda m: _release_key(m["versions"][0]) if m["versions"] else (0, "", (0, 0, 0, 0)),
        reverse=True,
    )

json.dump(site, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))

# ── 分片输出：index.json（首页/品牌页）+ versions/{code}.json（机型页）
# 安全补丁 / ARB / 编译日期：不再输出（用户不需要）——放在写分片之前
_DROP_META = ("securityPatch", "buildDate", "arb", "arbStatus", "arbMajor", "arbMinor", "arbNote")
for _b in site["brands"]:
    for _m in _b["models"]:
        for _v in _m["versions"]:
            _meta = _v.get("meta")
            if isinstance(_meta, dict):
                for _k in _DROP_META:
                    _meta.pop(_k, None)
                if not _meta:
                    _v.pop("meta", None)

IDX_DIR = os.path.join(ROOT, "site")
VER_DIR = os.path.join(ROOT, "site", "versions")
os.makedirs(VER_DIR, exist_ok=True)
for _old in os.listdir(VER_DIR):
    if _old.endswith(".json"):
        os.remove(os.path.join(VER_DIR, _old))

index = {"brands": [], "generated": site.get("generated", "")}
for b in site["brands"]:
    bm = []
    for m in b["models"]:
        vs = m["versions"]
        latest = vs[0] if vs else {}
        lm = latest.get("meta") or {}
        bm.append({
            "code": m["code"],
            "name": m["name"],
            "n": len(vs),
            "latest": latest.get("version", ""),
        })
        # 单机型文件
        payload = {"code": m["code"], "name": m["name"], "brand": b["key"], "versions": vs}
        with open(os.path.join(VER_DIR, m["code"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    index["brands"].append({"key": b["key"], "models": bm})

with open(os.path.join(IDX_DIR, "index.json"), "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

_idx_sz = os.path.getsize(os.path.join(IDX_DIR, "index.json"))
_ver_sz = sum(os.path.getsize(os.path.join(VER_DIR, x)) for x in os.listdir(VER_DIR))
print(f"分片: index.json {_idx_sz/1024:.1f} KB | versions/ {len(os.listdir(VER_DIR))} 文件 {_ver_sz/1024/1024:.2f} MB")


total_models = sum(len(b["models"]) for b in site["brands"])
total_ver = sum(len(m["versions"]) for b in site["brands"] for m in b["models"])
total_cl = sum(1 for b in site["brands"] for m in b["models"] for v in m["versions"] if v["changelog"])
print(f"品牌 {len(site['brands'])} | 机型 {total_models} | 版本 {total_ver} | 有更新日志 {total_cl}")

CODE_RE2 = re.compile(r"[A-Z]{2,5}\d{3,4}")
for b in site["brands"]:
    keep_models = []
    for m in b["models"]:
        code = m["code"]
        clean_versions = []
        for v in m["versions"]:
            ver = v["version"]
            seg = ver.replace("ColorOS ", "").replace("OxygenOS ", "")
            seg = seg[len(code) + 1:] if seg.startswith(code + "_") else seg
            others = [c for c in CODE_RE2.findall(seg) if c != code]
            same_family = all(c[:2] == code[:2] or c[:3] == code[:3] for c in others)
            bad = bool(others) and not same_family
            if not bad:
                clean_versions.append(v)
        m["versions"] = clean_versions
        if m["versions"]:
            keep_models.append(m)
    b["models"] = keep_models

json.dump(site, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))