#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量提取 ARB（防回滚计数器）并存入 models/{code}/arb.json。

复用 ota_extract.py 的 payload 定位 + Range 读取 + xz/bz2 解压，
只 pull xbl_config 分区（几百 KB），ELF64 解析 ARB（移植自 RomCloud ArbParser.kt）。

用法:
  python3 scripts/arb_extract.py --all          # 全量（174 机型最新版本）
  python3 scripts/arb_extract.py --model PLK110 # 单机型
  python3 scripts/arb_extract.py --model PLK110 --url <gate链接>  # 直接指定链接
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import ota_extract as oe
from update import v3_query, REGIONS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────── ELF64 ARB 解析（移植 RomCloud ArbParser.kt / koaaN arbextract.c） ───────────
def parse_arb(data: bytes):
    """从 xbl_config.img 字节里读 ARB。返回 (major, minor, arb) 或 None。"""
    ELF_MAGIC = b"\x7fELF"
    if len(data) < 64 or data[:4] != ELF_MAGIC or data[4] != 2:  # ELFCLASS64
        return None

    def u32(off):
        return struct.unpack_from("<I", data, off)[0]

    def u64(off):
        return struct.unpack_from("<Q", data, off)[0]

    ph_off = u64(0x20)
    ph_entsize = struct.unpack_from("<H", data, 0x36)[0]
    ph_num = struct.unpack_from("<H", data, 0x38)[0]

    # 倒序找第一个非空 PT_NULL（HASH 段在程序头表末尾）
    hash_off = 0
    hash_size = 0
    for i in range(ph_num - 1, -1, -1):
        pos = ph_off + i * ph_entsize
        if pos + 56 > len(data):
            continue
        p_type = u32(pos)
        p_offset = u64(pos + 8)      # p_offset 在 ELF64 Phdr 偏移 8
        p_filesz = u64(pos + 32)     # p_filesz 在偏移 32
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
    """CN 手动域 gauss 直链：带任何 UA 都 403，必须不带 UA。"""
    return ("componentotacostmanual-cn.allawnfs.com" in url
            or "gauss-componentotacostmanual-cn" in url)


def extract_arb_from_url(url: str, code: str):
    """从 OTA 链接提取 ARB。返回 dict 或 None。"""
    is_gate = "downloadCheck" in url or "/download?" in url
    # gate 先解析成直链；CN 手动直链域不带 UA（带 UA 403）
    direct = oe.resolve_direct(url) if is_gate else url
    no_ua = is_cn_manual_direct(direct)
    reader, manifest = oe.open_payload(direct, no_ua=no_ua)
    # 找 xbl_config 分区
    xbl = None
    for p in manifest["partitions"]:
        if p["name"] == "xbl_config":
            xbl = p
            break
    if xbl is None:
        return {"code": code, "error": "无 xbl_config 分区", "arb": None}

    # 提取到临时内存（xbl_config 通常 < 1MB）
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
    """实时查询拿新鲜 gate 链接 → 提取 ARB。"""
    # 确定区域：从 models.json 拿 region，映射到 REGION_TABLE 键
    try:
        models = json.load(open(os.path.join(ROOT, "config", "models.json")))[
            "models"]
        region_tag = ""
        for m in models:
            if m.get("code") == code:
                region_tag = m.get("region", "")
                break
        # region 映射
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

    # 枚举分支拿最新
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
        # 从 site.json 拿机型清单（romcloud-web）
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
