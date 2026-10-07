


import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


site = json.load(open(os.path.join(ROOT, "site", "site.json")))
arbdb_path = os.path.join(ROOT, "config", "arb_database.json")
arbdb = json.load(open(arbdb_path)) if os.path.exists(arbdb_path) else {}


def norm_ver(v):
    
    m = re.search(r'(\d+\.\d+\.\d+\.\d+\([A-Z0-9]+\))', v)
    return m.group(1) if m else v

merged = 0
matched_hist = 0
for b in site["brands"]:
    for m in b["models"]:
        code = m["code"]
        if code in arbdb:
            arb_versions = arbdb[code].get("versions", {})
            for v in m["versions"]:
                vkey = norm_ver(v["version"])
                match = None
                for k, info in arb_versions.items():
                    if vkey in k or k in vkey:
                        match = info
                        break
                if match:
                    v.setdefault("meta", {})
                    v["meta"]["arb"] = match.get("arb")
                    v["meta"]["arbStatus"] = "Safe" if match.get("arb") == 0 else "Protected"
                    v["meta"]["arbMajor"] = match.get("major")
                    v["meta"]["arbMinor"] = match.get("minor")
                    matched_hist += 1
            merged += 1

        arb_path = os.path.join(ROOT, "models", code, "arb.json")
        if os.path.exists(arb_path):
            arb = json.load(open(arb_path))
            if arb.get("arb") is not None:
                v0 = m["versions"][0]
                if "arb" not in v0.get("meta", {}):
                    v0.setdefault("meta", {})
                    v0["meta"]["arb"] = arb.get("arb")
                    v0["meta"]["arbStatus"] = arb.get("status")
                    v0["meta"]["arbMajor"] = arb.get("major")
                    v0["meta"]["arbMinor"] = arb.get("minor")

json.dump(site, open(os.path.join(ROOT, "site", "site.json"), "w"), ensure_ascii=False, separators=(",", ":"))

total_arb_ver = 0
for b in site["brands"]:
    for m in b["models"]:
        for v in m["versions"]:
            if "arb" in v.get("meta", {}):
                total_arb_ver += 1
print(f"合并完成：{merged} 机型来自 antirollchecker（{matched_hist} 历史版本），总 {total_arb_ver} 版本有 ARB")