#!/usr/bin/env python3
"""
整合生成前端数据：
- 只保留欧加三品牌（OnePlus/OPPO/Realme），有版本数据的机型
- 版本数据 + 更新日志（changelog）都挂到版本上
- 版本按语义版本号新到旧；机型按最新版本号（发布新到旧）
- 过滤失效链接（dead_links.json）
输出 frontend/data/site.json
"""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 仓库根
crawl = json.load(open(os.path.join(ROOT, "config", "site_crawl.json")))
OUT = os.path.join(ROOT, "site", "site.json")

# ── 1. 读 ota-version.txt：指纹(带时间戳) → 版本名 ──
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

# ── 2. 读 changelog：指纹(无时间戳) → markdown 内容 ──
def load_changelog(code):
    fp2cl = {}
    cdir = os.path.join(ROOT, "models", code, "changelog")
    if not os.path.isdir(cdir): return fp2cl
    for f in os.listdir(cdir):
        if not f.endswith(".md"): continue
        fp = f[:-3]
        fp2cl[fp] = open(os.path.join(cdir, f), encoding="utf-8").read()
    return fp2cl

# ── 3. 构建版本数据 ──
def build_versions(code):
    fp2cl = load_changelog(code)
    fp2ver = load_fp_to_version(code)
    # changelog 无时间戳指纹 → 版本名（通过 fp2ver 前缀匹配）
    cl_fp_to_ver = {}
    for cl_fp, content in fp2cl.items():
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
            url = open(os.path.join(links_dir, t), encoding="utf-8").read().strip()
            changelog = cl_fp_to_ver.get(f"{code}_{ver}({region})", "")
            versions.append({
                "version": f"ColorOS {ver}({region})",
                "region": region,
                "url": url,
                "changelog": changelog,
            })
            seen_versions.add(f"{code}_{ver}({region})")
    # 目录条目：ota-version 里有指纹（官方确认发布过）但 links 缺失的版本
    for ver_name in cl_fp_to_ver:
        if ver_name in seen_versions:
            continue
        mm = re.match(rf"^{re.escape(code)}_(.+?)\(([A-Z0-9]+)\)$", ver_name)
        if not mm:
            continue
        versions.append({
            "version": f"ColorOS {mm.group(1)}({mm.group(2)})",
            "region": mm.group(2),
            "url": "",
            "changelog": cl_fp_to_ver[ver_name],
        })
        seen_versions.add(ver_name)
    # 版本按语义版本号新到旧
    versions.sort(key=lambda v: ver_key(v["version"]), reverse=True)
    return versions

# ── 版本号解析（语义排序） ──
def ver_key(vstr):
    m = re.search(r'(\d+)\.(\d+)\.(\d+)\.(\d+)', vstr)
    if m: return tuple(int(x) for x in m.groups())
    m2 = re.search(r'(\d+)_(\d+)\.(\d+)\.(\d+)', vstr)
    if m2: return tuple(int(x) for x in m2.groups())
    return (0, 0, 0, 0)

# ── 4. 只保留欧加三品牌 ──
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

# ── 5. 过滤失效链接 ──
dead_path = os.path.join(ROOT, "config", "dead_links.json")
if os.path.exists(dead_path):
    dead_urls = {x["url"] for x in json.load(open(dead_path))["dead"]}
    for b in site["brands"]:
        for m in b["models"]:
            m["versions"] = [v for v in m["versions"] if v.get("url") not in dead_urls]
        b["models"] = [m for m in b["models"] if m.get("versions")]

# ── 5.3 版本元数据（devices.json + pn_ref + changelog 指纹） ──
DEV = json.load(open(os.path.join(ROOT, "config", "devices.json")))
PN = json.load(open(os.path.join(ROOT, "config", "pn_ref.json")))["models"]
NV_MAP = {"CN": "NV97", "GLO": "NVA7", "IN": "NV1B", "EU": "NV44"}
def nv_of(region):
    # CN01/CH/CT -> CN；EX01/EEA -> EU；GLxx -> GLO
    r = (region or "").upper()
    for k in NV_MAP:
        if r.startswith(k[:2]):
            return NV_MAP[k]
    return ""

# code -> {region -> variant 元数据}
dev_meta = {}
for _m in DEV["models"]:
    for _v in _m.get("variants", []):
        if _v.get("code"):
            dev_meta.setdefault(_v["code"], {})[_v.get("region", "")] = _v

def build_date(fp):
    if not fp or "197001010000" in fp:
        return ""  # 挖掘占位指纹，真实编译日期不可知
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
            # 匹配 variant：版本号对上
            meta_match = None
            for _rg, _vv in variants.items():
                if (_vv.get("latest") or "").startswith(f"{code}_{pure}"):
                    meta_match = _vv
                    break
            # 目标版本 = changelog 里的 OTA 指纹
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

# ── 5.4 降级包导入（downgrade/{code}.txt，官方降级直链） ──
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
            # coloros_ver 形如 ColorOS13.1.0 —— 目标版本段
            ver_name = f"降级包 {coloros_ver}(CN)"
            # 去重：同 url 已存在跳过
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

# ── 5.44 securityPatch 从 changelog 文字提取（"更新 Android 安全补丁至 2026 年 8 月"） ──
def patch_from_changelog(cl):
    if not cl:
        return ""
    m = re.search(r"安全补丁[至到]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", cl)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"安全补丁[至到]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月", cl)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    # 英文形态
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

# ── 5.44b Daniel API 的 md5/size 补全（CN，全格式键） ──
_dan = {}
try:
    _cat = json.load(open(os.path.join(ROOT, "config", "daniel_catalog.json")))
    for _r in _cat.get("releases", []):
        if _r.get("md5") and _r.get("region") == "CN":
            _dan[(_r["model"], _r["version"])] = (_r["md5"], _r.get("size"))
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

# ── 5.44c 目标站（lian86）版本目录入库：官方确认发布过但链接待补 ──
_lian_path = os.path.join(ROOT, "config", "lian_versions.json")
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
                # 去重：links 或已有目录条目
                if any(v["version"] == disp for v in model["versions"]):
                    continue
                model["versions"].append({
                    "version": disp,
                    "region": region,
                    "url": "",
                    "changelog": "",
                    "source": "lian86-catalog",
                })

# ── 5.45 机型级回填：Android / NV / projectId（跨全部版本含降级包） ──
def nv_of(region):
    r = (region or "").upper()
    for k in NV_MAP:
        if r.startswith(k[:2]):
            return NV_MAP[k]
    return ""

for b in site["brands"]:
    for model in b["models"]:
        # Android：任一版本有值则全机型回填
        val = ""
        for v in model["versions"]:
            if (v.get("meta") or {}).get("android"):
                val = v["meta"]["android"]
                break
        for v in model["versions"]:
            v.setdefault("meta", {})
            # NV 按 region 推（CN01/老格式 CN 域都是 NV97）
            if not v["meta"].get("nv"):
                rm = re.search(r"\(([A-Z0-9]+)\)", v["version"])
                v["meta"]["nv"] = nv_of(rm.group(1) if rm else "CN")
            # projectId 机型级
            if not v["meta"].get("projectId"):
                v["meta"]["projectId"] = (PN.get(model["code"]) or {}).get("prj", "")
            # Android 机型级回填（放最后，覆盖降级包导入的）
            if val:
                v["meta"]["android"] = v["meta"].get("android") or val

# ── 5.5 包类型与最新标签 ──
for b in site["brands"]:
    for m in b["models"]:
        for idx, v in enumerate(m["versions"]):
            # 顶部即最新，不加"最新"标签；无链接的目录条目不给包类型标签
            if v.get("url"):
                v["tags"] = ["降级包" if "downgradefs.coloros.com" in v["url"] else "全量包"]
            else:
                v["tags"] = ["待补链接"]

# ── 6. 机型按发布新到旧（最新版本号降序） ──
for b in site["brands"]:
    b["models"].sort(
        key=lambda m: ver_key(m["versions"][0]["version"]) if m["versions"] else (0, 0, 0, 0),
        reverse=True,
    )

json.dump(site, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))

total_models = sum(len(b["models"]) for b in site["brands"])
total_ver = sum(len(m["versions"]) for b in site["brands"] for m in b["models"])
total_cl = sum(1 for b in site["brands"] for m in b["models"] for v in m["versions"] if v["changelog"])
print(f"品牌 {len(site['brands'])} | 机型 {total_models} | 版本 {total_ver} | 有更新日志 {total_cl}")
