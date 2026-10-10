

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ota_extract as oe
from update import v3_query, REGIONS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parse_arb(data: bytes):

    ELF_MAGIC = b"\x7fELF"
    if len(data) < 64 or data[:4] != ELF_MAGIC or data[4] != 2:

        return None

    def u32(off):
        return struct.unpack_from("<I", data, off)[0]

    def u64(off):
        return struct.unpack_from("<Q", data, off)[0]

    ph_off = u64(0x20)
    ph_entsize = struct.unpack_from("<H", data, 0x36)[0]
    ph_num = struct.unpack_from("<H", data, 0x38)[0]

    hash_off = 0
    hash_size = 0
    for i in range(ph_num - 1, -1, -1):
        pos = ph_off + i * ph_entsize
        if pos + 56 > len(data):
            continue
        p_type = u32(pos)
        p_offset = u64(pos + 8)

        p_filesz = u64(pos + 32)

        if p_type == 0 and p_filesz > 0:
            hash_off = p_offset
            hash_size = p_filesz
            break
    if hash_size == 0 or hash_off + hash_size > len(data):
        return None

    hash_start = hash_off
    hash_len = hash_size
    scan_limit = min(0x1000, hash_len)
    header_off = -1
    common_sz = 0
    qti_sz = 0
    off = 0
    while off + 36 <= scan_limit:
        version = u32(hash_start + off)
        common = u32(hash_start + off + 4)
        qti = u32(hash_start + off + 8)
        oem = u32(hash_start + off + 12)
        hash_tbl_sz = u32(hash_start + off + 16)
        if (1 <= version <= 10 and common <= 0x1000 and oem <= 0x4000
                and hash_tbl_sz <= 0x4000
                and off + 36 + common + qti + oem <= hash_len):
            header_off = off
            common_sz = common
            qti_sz = qti
            break
        off += 4
    if header_off < 0:
        return None

    oem_off = hash_start + header_off + 36 + common_sz + qti_sz
    if oem_off + 12 > len(data):
        return None
    major = u32(oem_off)
    minor = u32(oem_off + 4)
    arb = u32(oem_off + 8)
    return (major, minor, arb)

def is_cn_manual_direct(url: str) -> bool:

    return ("componentotacostmanual-cn.allawnfs.com" in url
            or "gauss-componentotacostmanual-cn" in url)

def extract_arb_from_url(url: str, code: str):

    is_gate = "downloadCheck" in url or "/download?" in url
    direct = oe.resolve_direct(url) if is_gate else url
    no_ua = is_cn_manual_direct(direct)
    reader, manifest = oe.open_payload(direct, no_ua=no_ua)
    xbl = None
    for p in manifest["partitions"]:
        if p["name"] == "xbl_config":
            xbl = p
            break
    if xbl is None:
        return {"code": code, "error": "无 xbl_config 分区", "arb": None}

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = oe.extract(reader, manifest, xbl, tmp)
        data = open(out, "rb").read()
        r = parse_arb(data)
        if r is None:
            return {"code": code, "error": "ELF64 解析失败", "arb": None,
                    "size": xbl.get("image_size")}
        major, minor, arb = r
        return {"code": code, "major": major, "minor": minor, "arb": arb,
                "status": "Safe" if arb == 0 else "Protected",
                "size": xbl.get("image_size")}

def query_and_extract(code: str):

    try:
        models = json.load(open(os.path.join(ROOT, "config", "models.json")))[
            "models"]
        region_tag = ""
        for m in models:
            if m.get("code") == code:
                region_tag = m.get("region", "")
                break
        alias = {
            "CN": "cn", "CH": "cn", "CT": "cn", "CNCMCC": "cn",
            "IN": "in", "IND": "in", "EU": "eu", "EEA": "eu", "UK": "eu",
            "GL": "gl", "GLO": "gl", "GLOBAL": "gl",
            "TW": "tw", "RU": "ru", "TR": "tr", "GB": "gb", "SG": "sg",
            "ID": "id", "MY": "my", "VN": "vn", "TH": "th", "PH": "ph",
            "SA": "sa", "MEA": "mea", "LATAM": "latam", "LA": "latam",
            "BR": "br", "KZ": "kz", "OCA": "oca", "APC": "apc", "EG": "eg",
            "LK": "lk", "MX": "mx", "NA": "na",
        }
        region = alias.get(region_tag, "cn")
    except Exception:
        region = "cn"

    for letter in ["A", "C", "F", "H", "J", "E", "B", "D", "G"]:
        r = v3_query(code, region, letter)
        if r and r.get("url"):
            arb = extract_arb_from_url(r["url"], code)
            if arb:
                arb["version"] = r.get("version")
                arb["fp"] = r.get("fp")
                arb["md5"] = r.get("md5")
                return arb
    return {"code": code, "error": "查不到固件", "arb": None}

def save(code, result):
    out_dir = os.path.join(ROOT, "models", code)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "arb.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="全量提取所有机型")
    ap.add_argument("--model", help="单机型 code")
    ap.add_argument("--url", help="直接指定 OTA 链接（配合 --model）")
    args = ap.parse_args()

    if args.url and args.model:
        r = extract_arb_from_url(args.url, args.model)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        if r.get("arb") is not None:
            save(args.model, r)
        return

    if args.model:
        r = query_and_extract(args.model)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        if r.get("arb") is not None:
            save(args.model, r)
        return

    if args.all:
        site_path = "/root/oplus-rom-dev/romcloud-web/frontend/data/site.json"
        site = json.load(open(site_path))
        codes = []
        for b in site["brands"]:
            for m in b["models"]:
                codes.append(m["code"])
        print(f"共 {len(codes)} 机型，开始批量提取 ARB...")
        ok = 0
        fail = 0
        for i, code in enumerate(codes):
            print(f"[{i+1}/{len(codes)}] {code} ...", end=" ", flush=True)
            try:
                r = query_and_extract(code)
                if r.get("arb") is not None:
                    save(code, r)
                    print(f"ARB={r['arb']} ({r['status']})")
                    ok += 1
                else:
                    print(f"失败: {r.get('error')}")
                    fail += 1
            except Exception as e:
                print(f"异常: {type(e).__name__}: {e}")
                fail += 1
        print(f"\n完成：成功 {ok}，失败 {fail}")
        return

    ap.print_help()

if __name__ == "__main__":
    main()