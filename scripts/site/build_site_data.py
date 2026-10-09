


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
            _raw = open(os.path.join(links_dir, t), encoding="utf-8").read().strip()
            # 支持三行格式：url / size: N / md5: H
            _lines = [l.strip() for l in _raw.split("\n") if l.strip()]
            url = _lines[0] if _lines else ""
            _link_meta = {}
            for _l in _lines[1:]:
                if _l.startswith("size:"):
                    _link_meta["sizeBytes"] = int(_l[5:].strip())

                elif _l.startswith("md5:"):
                    _link_meta["md5"] = _l[4:].strip()
                elif _l.startswith("patch:"):
                    _link_meta["securityPatch"] = _l[6:].strip()
                elif _l.startswith("fp:"):
                    _link_meta["fp"] = _l[3:].strip()
            changelog = cl_fp_to_ver.get(f"{code}_{ver}({region})", "")
            _v = {
                "version": f"ColorOS {ver}({region})",
                "region": region,
                "url": url,
                "changelog": changelog,
            }
            if _link_meta:
                _v["_linkMeta"] = _link_meta
            versions.append(_v)
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
    versions.sort(key=lambda v: ver_key(v["version"]), reverse=True)
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
try:
    _cat = json.load(open(os.path.join(ROOT, "config", "daniel_catalog.json")))
    for _r in _cat.get("releases", []):
        if _r.get("region") == "CN" and (_r.get("md5") or _r.get("size")):
            _dan[(_r["model"], _r["version"])] = (_r.get("md5", ""), _r.get("size"))
except Exception:
    pass

for b in site["brands"]:
    for model in b["models"]:
        for v in model["versions"]:
            meta = v.setdefault("meta", {})
            if meta.get("md5"):
                continue
            ver = v["version"].replace("ColorOS ", "")
            hit = _dan.get((model["code"], f"{model['code']}_{ver}"))
            if hit:
                if not meta.get("md5"):
                    meta["md5"] = hit[0]
                if not meta.get("sizeBytes") and hit[1]:
                    meta["sizeBytes"] = int(hit[1])

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

# ── sizeBytes 缓存应用（探测结果 url→size）
_size_cache_path = os.path.join(ROOT, "config", "size_cache.json")
if os.path.exists(_size_cache_path):
    _size_cache = json.load(open(_size_cache_path))
    for b in site["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                _u = v.get("url")
                if _u and _u in _size_cache and not (v.get("meta") or {}).get("sizeBytes"):
                    v.setdefault("meta", {})["sizeBytes"] = _size_cache[_u]

# ── v6 新鲜元数据（链接文件自带的 size/md5/patch/fp，来自官方 v6 响应）
for b in site["brands"]:
    for m in b["models"]:
        for v in m["versions"]:
            lm = v.pop("_linkMeta", None)
            if lm:
                meta = v.setdefault("meta", {})
                if lm.get("sizeBytes"):
                    meta["sizeBytes"] = lm["sizeBytes"]
                if lm.get("md5"):
                    meta["md5"] = lm["md5"]
                if lm.get("securityPatch"):
                    meta["securityPatch"] = lm["securityPatch"]
                if lm.get("fp"):
                    # 指纹 → 编译日期 + 目标版本
                    _fp = lm["fp"]
                    meta["targetVersion"] = _fp
                    if not meta.get("buildDate"):
                        _dm = re.search(r"_(\d{12})$", _fp)
                        if _dm:
                            _ts = _dm.group(1)
                            meta["buildDate"] = f"{_ts[:4]}-{_ts[4:6]}-{_ts[6:8]}"

# ── 实测元数据应用（verify_meta 的 CDN 实测结果，最高优先级）
_meta_cache_path = os.path.join(ROOT, "config", "meta_cache.json")
if os.path.exists(_meta_cache_path):
    _meta_cache = json.load(open(_meta_cache_path))
    for b in site["brands"]:
        for m in b["models"]:
            for v in m["versions"]:
                _u = v.get("url")
                if _u and _u in _meta_cache:
                    _hit = _meta_cache[_u]
                    meta = v.setdefault("meta", {})
                    if _hit.get("size"): meta["sizeBytes"] = _hit["size"]
                    if _hit.get("md5"): meta["md5"] = _hit["md5"]

# ── md5 来源门禁：只保留可信来源
# 可信来源：① meta_cache（CDN 实测）② v6 官方响应（_linkMeta）③ 降级包（官方独立域）
# 剔除：历史批量快照（daniel_catalog/devices，按机型贴值不可信）
_trusted_md5 = set()
for _p in (os.path.join(ROOT, "config", "meta_cache.json"),):
    if os.path.exists(_p):
        try:
            for _u, _h in json.load(open(_p)).items():
                if _h.get("md5"): _trusted_md5.add((_u, _h["md5"]))
        except Exception:
            pass
# v6 新鲜值：从链接文件的三行格式读取（在下方 _linkMeta 应用时已并入）
# 这里用链接文件里的 md5 建白名单
for _b in site["brands"]:
    for _m in _b["models"]:
        for _v in _m["versions"]:
            _u = _v.get("url", "")
            if _u and _u.startswith("https://component-ota"):
                _trusted_md5.add((_u, (_v.get("meta") or {}).get("md5", "")))

for b in site["brands"]:
    for m in b["models"]:
        for v in m["versions"]:
            meta = v.get("meta") or {}
            _md5 = meta.get("md5")
            if not _md5:
                continue
            _u = v.get("url", "")
            _hit = _meta_cache.get(_u) if _u else None
            _verified = (_hit and _hit.get("md5") == _md5)
            _gate = "component-ota-cn.allawntech.com/downloadCheck" in _u  # v6 官方响应
            _costmanual = "costmanual" in _u  # costmanual 域的 md5 来自官方（v3响应/devices.json）
            if not (_verified or _gate or "downgradefs" in _u or _costmanual):
                del meta["md5"]

# ── sizeBytes 清洗：<500MB 一律视为无效
# 依据实测分布：异常值最大 1.4MB（错误归档/门卫响应），正常 ROM 最小 869MB，断层清晰
MIN_ROM_SIZE = 500 * 1024 * 1024
for b in site["brands"]:
    for m in b["models"]:
        for v in m["versions"]:
            meta = v.get("meta") or {}
            sb = meta.get("sizeBytes")
            if sb and isinstance(sb, int) and sb < MIN_ROM_SIZE:
                del meta["sizeBytes"]

json.dump(site, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))

total_models = sum(len(b["models"]) for b in site["brands"])
total_ver = sum(len(m["versions"]) for b in site["brands"] for m in b["models"])
total_cl = sum(1 for b in site["brands"] for m in b["models"] for v in m["versions"] if v["changelog"])
print(f"品牌 {len(site['brands'])} | 机型 {total_models} | 版本 {total_ver} | 有更新日志 {total_cl}")

def sort_key(vstr):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", vstr)
    if m:
        mm2 = re.match(r"(?:ColorOS |OxygenOS )?(\d+)", vstr)
        big = int(mm2.group(1)) if mm2 else 0
        return (2, big) + tuple(int(x) for x in m.groups())
    m2 = re.search(r"(\d+)(?:\.(\d+))?[_ ]([A-Z])\.(\d+)", vstr)
    if m2:
        major = int(m2.group(1)); minor = int(m2.group(2) or 0)
        return (1, major * 100 + minor, ord(m2.group(3)), int(m2.group(4)))
    return (0, 0, 0, 0)

for b in site["brands"]:
    for m in b["models"]:
        full = [v for v in m["versions"] if "降级包" not in v["version"]]
        dg = [v for v in m["versions"] if "降级包" in v["version"]]
        full.sort(key=lambda v: sort_key(v["version"]), reverse=True)
        m["versions"] = full + dg
    b["models"].sort(
        key=lambda m: sort_key(m["versions"][0]["version"]) if m["versions"] else (0, 0, 0, 0),
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

json.dump(site, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))