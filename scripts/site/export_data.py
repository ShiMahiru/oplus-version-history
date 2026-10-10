

import os, re, json, collections

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEVICES = os.path.join(ROOT, "config", "devices.json")
PN_REF = os.path.join(ROOT, "config", "pn_ref.json")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
os.makedirs(OUT, exist_ok=True)

dev = json.load(open(DEVICES))
pn = json.load(open(PN_REF))["models"]

def clean_name(n):
    n = n.replace("<br>", " / ").replace("<br/>", " / ").replace("<br />", " / ")
    return n.strip()

name_map = {}
for code, info in pn.items():
    name_map[code] = clean_name(info.get("name", code))

brand_map = {}
for m in dev["models"]:
    for v in m.get("variants", []):
        c = v.get("code", "")
        if c:
            brand_map[c] = m["brandLabel"]

def brand_of(code):
    if code in brand_map: return brand_map[code]
    for suf in ["EEA", "IN", "RU", "TR", "EU", "TW", "MEA", "SA", "SG", "TH",
                "LATAM", "BR", "MY", "ID", "KZ", "OCA", "VN", "GLO"]:
        if code.endswith(suf):
            b = code[:-len(suf)]
            if b in brand_map: return brand_map[b]
    if code.startswith("RMX"): return "Realme"
    if code.startswith("CPH"): return "OnePlus"

    if code.startswith(("PH", "OPD", "PJ", "PK", "PL", "PF", "PE", "PD", "PG", "NE", "IN", "KB", "LE", "MT", "GM", "HD", "DN")):
        return "OnePlus"
    return "OPPO"

def model_name(code):
    if code in name_map: return name_map[code]
    for suf in ["EEA", "IN", "RU", "TR", "EU", "TW", "MEA", "SA", "SG", "TH",
                "LATAM", "BR", "MY", "ID", "KZ", "OCA", "VN", "GLO"]:
        if code.endswith(suf):
            b = code[:-len(suf)]
            if b in name_map: return name_map[b]
    return code

brands = collections.OrderedDict()
for k in ["OnePlus", "OPPO", "Realme"]:
    brands[k] = {"key": k, "label": k, "models": []}
for k in ["Xiaomi", "Redmi", "vivo", "iQOO", "Meizu", "Lenovo", "OnePlus Global"]:
    brands[k] = {"key": k, "label": k, "models": [], "empty": True}

models = {}
links_dir = os.path.join(ROOT, "links")
models_dir = os.path.join(ROOT, "models")

for code in sorted(os.listdir(links_dir)):
    if code == "_dead": continue
    cdir = os.path.join(links_dir, code)
    if not os.path.isdir(cdir): continue
    txts = sorted(f for f in os.listdir(cdir) if f.endswith(".txt"))
    if not txts: continue

    brand = brand_of(code)
    if brand not in brands: brand = "OPPO"

    versions = []
    for t in txts:
        name = t[:-4]
        m = re.match(rf"^{re.escape(code)}_(.+?)\(([A-Z0-9]+)\)$", name)
        if m:
            ver = m.group(1); region = m.group(2)
        else:
            ver = name[len(code):].lstrip("_"); region = ""
        url = open(os.path.join(cdir, t)).read().strip()
        versions.append({"version": ver, "region": region, "url": url})

    latest = ""; android = ""; security = ""
    mdir = os.path.join(models_dir, code)
    if os.path.isdir(mdir):
        lu = os.path.join(mdir, "latest-update.txt")
        if os.path.exists(lu):
            for line in open(lu):
                line = line.strip()
                if line.startswith("版本名称:"): latest = line.split(":", 1)[1].strip()
                elif line.startswith("Android 版本:"): android = line.split(":", 1)[1].strip()
                elif line.startswith("安全补丁:"): security = line.split(":", 1)[1].strip()

    rui = 6
    region_default = ""
    if code in brand_map:
        for m in dev["models"]:
            for v in m.get("variants", []):
                if v.get("code") == code:
                    rui = v.get("rui", 6); region_default = v.get("region", "")
                    break

    models[code] = {
        "code": code,
        "brand": brand,
        "name": model_name(code),
        "region": region_default,
        "rui": rui,
        "latest": latest,
        "android": android,
        "securityPatch": security,
        "versions": versions,
    }
    brands[brand]["models"].append(code)

json.dump({"brands": list(brands.keys())}, open(os.path.join(OUT, "brands.json"), "w"), ensure_ascii=False)
json.dump(models, open(os.path.join(OUT, "models.json"), "w"), ensure_ascii=False, separators=(",", ":"))

total = sum(len(m["versions"]) for m in models.values())
named = sum(1 for m in models.values() if m["name"] != m["code"])
print(f"品牌: {len(brands)} | 机型: {len(models)} | 版本链接: {total} | 有名机型: {named}")
for b, d in brands.items():
    print(f"  {b}: {len(d['models'])} 机型 {'(空壳)' if d.get('empty') else ''}")