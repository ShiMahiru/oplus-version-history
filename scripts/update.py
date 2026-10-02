#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oplus-version-history 官方更新器
================================
数据全部来自官方服务器（实测验证过的链路）：
  1) v3 OTA 网关   —— 加密查询，枚举在推分支 -> 版本名/指纹/gate链接/大小/MD5/补丁
  2) descriptionInfo—— 明文查询，任意历史版本的官方更新日志 + 版本名反查
  3) downgrade     —— 官方降级包直链（CN 机型，需项目号）

用法:
  python3 scripts/update.py                 # 全量增量
  python3 scripts/update.py --model PLQ110  # 单机型
  python3 scripts/update.py --only-changelog # 只补 changelog（批量）
  python3 scripts/update.py --no-downgrade  # 跳过降级包
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# ─────────────── 区域配置（官方网关，实测值） ───────────────
# carrier 为 nvid 的二进制串；key/neg 必须与 host 匹配，否则网关返回 500「未知异常」。
# 实测来源：op-ota/global.py 的 REGION_MAP + OPlus-Tracker/config.py 的 public_key_version。
# 四个网关各自的公钥/negotiationVersion（用错则 500）：
_SRV = {
    0: {"host": "component-ota-sg.allawnos.com", "key": "sg", "neg": "1615895993238"},
    1: {"host": "component-ota-cn.allawntech.com", "key": "cn", "neg": "1615879139745"},
    2: {"host": "component-ota-in.allawnos.com", "key": "in", "neg": "1615896309308"},
    3: {"host": "component-ota-eu.allawnos.com", "key": "eu", "neg": "1615897067573"},
}
# 区域 -> (server, carrier, uRegion, lang)；uRegion 官方只用 CN/IN/EU/GL 四值。
REGION_TABLE = {
    "cn":    (1, "10010111", "CN", "zh-CN"),
    "in":    (2, "00011011", "IN", "en-IN"),
    "eu":    (3, "01000100", "EU", "en-GB"),
    "gl":    (0, "10100111", "GL", "en-US"),
    "tw":    (0, "00011010", "GL", "zh-TW"),
    "ru":    (3, "00110111", "EU", "ru-RU"),
    "tr":    (3, "01010001", "EU", "tr-TR"),
    "gb":    (3, "10001010", "EU", "en-GB"),
    "sg":    (0, "00101100", "GL", "en-SG"),
    "id":    (0, "00110011", "GL", "id-ID"),
    "my":    (0, "00111000", "GL", "ms-MY"),
    "vn":    (0, "00111100", "GL", "vi-VN"),
    "th":    (0, "00111001", "GL", "th-TH"),
    "ph":    (0, "00111110", "GL", "en-PH"),
    "sa":    (0, "10000011", "GL", "sa-SA"),
    "mea":   (0, "10100110", "GL", "en-MEA"),
    "latam": (0, "10011010", "GL", "en-LA"),
    "br":    (0, "10011110", "GL", "en-BR"),
    "kz":    (0, "01011010", "GL", "ru-KZ"),
    "oca":   (0, "10100101", "GL", "en-US"),
    "apc":   (0, "10100100", "GL", "en-US"),
    "eg":    (0, "01110101", "GL", "ar-EG"),
    "lk":    (0, "01100000", "GL", "en-LK"),
    "mx":    (0, "01111011", "GL", "es-MX"),
    "na":    (0, "10100111", "GL", "en-US"),
}

REGIONS = {}
for _name, (_srv, _carrier, _ureg, _lang) in REGION_TABLE.items():
    REGIONS[_name] = {
        "host": _SRV[_srv]["host"], "key": _SRV[_srv]["key"],
        "neg": _SRV[_srv]["neg"], "carrier": _carrier,
        "uRegion": _ureg, "lang": _lang,
        "nvid": "NV%02X" % int(_carrier, 2),
    }
LETTER_POOL = ["A", "C", "F", "H", "J", "E", "B", "D", "G"]

# 部分区域的官方 nvid 对已上市机型查不到固件（返回 2004 artifactV1Result is empty），
# 但同一机型在其它产线 nvid 下能命中。实测：CPH2735 仅 NV2C 命中、
# CPH2781 在 NV2C/NVA6/NV9E 命中，而两者的区域 nvid(NV44) 全部落空。
# 这里给出按区域追加尝试的 nvid 序列，主 nvid 始终排第一。
NVID_FALLBACK = {
    "eu": ["NV44", "NV2C", "NVA6", "NV9E", "NVA7"],
    "in": ["NV1B", "NV2C", "NV9E"],
}

# config/models.json 的 region 标记来自第三方清单（OTA-Pulse / oppo-probe），实测有误：
# CPH2781 / CPH2735 标为 GL，实际只在 EU 网关有响应。因此主区域全部落空时，
# 按下面的顺序把 host+公钥+nvid 成套切换到别的网关再试一轮。
GATEWAY_FALLBACK = ["gl", "eu", "in", "cn", "sg", "br", "mea", "tw", "id", "th", "ru", "tr"]
GAP = 0.4  # 实测 >300ms 稳定
TIMEOUT = 20

KEYS = json.load(open(os.path.join(ROOT, "config", "keys.json"), encoding="utf-8"))
PNREF = json.load(open(os.path.join(ROOT, "config", "pn_ref.json"), encoding="utf-8"))
MODELS = json.load(open(os.path.join(ROOT, "config", "models.json"), encoding="utf-8"))["models"]

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    sys.exit("需要 cryptography: pip install cryptography")


# models.json 里的 region 标记 -> REGION_TABLE 键。
# 旧实现把非 cn/in/eu 的机型一律压成 gl+NVA7，导致 TW/RU/TR/ID/MY/VN/MEA/KZ 等
# 约 106 个机型长期取不到数据。此处按官方区域逐个映射。
_REGION_ALIAS = {
    "CN": "cn", "CH": "cn", "CT": "cn", "CNCMCC": "cn", "CNMOBILE": "cn",
    "IN": "in", "IND": "in",
    "EU": "eu", "EEA": "eu", "UK": "eu", "EU-OR": "eu", "EUOR": "eu",
    "GL": "gl", "GLO": "gl", "GLOBAL": "gl",
    "TW": "tw", "RU": "ru", "TR": "tr", "GB": "gb",
    "SG": "sg", "ID": "id", "MY": "my", "VN": "vn", "TH": "th",
    "PH": "ph", "SA": "sa", "MEA": "mea",
    "LATAM": "latam", "LA": "latam", "BR": "br",
    "KZ": "kz", "OCA": "oca", "APC": "apc", "EG": "eg",
    "LK": "lk", "MX": "mx", "MX-TELCEL": "mx", "MX-ATT": "mx",
    "NA": "na", "MM": "gl", "BD": "gl", "PK": "gl", "NP": "gl", "KH": "gl",
}


def region_of(model):
    reg = (model.get("region") or "GL").upper()
    return _REGION_ALIAS.get(reg, "gl")


def load_pub(reg_key):
    pem = KEYS["OTA_PUBLIC_KEYS"][reg_key]
    return serialization.load_pem_public_key(pem.encode())


def load_dg_pub():
    pem = KEYS["DOWNGRADE"]["public_key"]
    return serialization.load_pem_public_key(pem.encode())


# ─────────────── v3 加密查询 ───────────────
def v3_query(model, region, letter):
    """查询一个分支。返回 dict 或 None。model=型号 code，region=区域 key，letter=分支字母。"""
    cfg = REGIONS[region]
    fw = f"{model}{cfg['nvid']}_11.{letter}.01_0001_100001010000"
    aes_key = os.urandom(32)
    iv = os.urandom(16)
    pub = load_pub(cfg["key"])
    protected = base64.b64encode(
        pub.encrypt(base64.b64encode(aes_key),
                    padding.OAEP(mgf=padding.MGF1(hashes.SHA1()),
                                 algorithm=hashes.SHA1(), label=None))
    ).decode()

    now_ms = int(time.time() * 1000)
    body = {
        "language": cfg["lang"], "romVersion": f"{model}_11", "otaVersion": fw,
        "androidVersion": "Android16.0", "colorOSVersion": "ColorOS16",
        "model": model, "productName": model, "operator": "ALLNET",
        "uRegion": cfg["uRegion"], "trackRegion": cfg["uRegion"],
        "imei": "000000000000000", "imei1": "000000000000000", "mode": "0",
        "registrationId": "unknown", "deviceId": "0" * 64, "version": "3",
        "type": "1", "otaPrefix": f"{model}_11", "isRealme": "0",
        "time": str(now_ms), "canCheckSelf": "0", "gray": "0", "reqMode": "manual",
    }
    headers = {
        "language": cfg["lang"], "newLanguage": cfg["lang"],
        "romVersion": f"{model}_11", "otaVersion": fw,
        "androidVersion": "Android16.0", "colorOSVersion": "ColorOS16",
        "model": model, "infVersion": "1", "pipelineKey": "ALLNET",
        "operator": "ALLNET", "companyId": "", "nvCarrier": cfg["carrier"],
        "uRegion": cfg["uRegion"], "trackRegion": cfg["uRegion"],
        "imei": "000000000000000", "imei1": "000000000000000",
        "deviceId": "0" * 64, "mode": "manual", "channel": "pc", "version": "2",
        "Accept": "application/json", "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "NULL",
        "protectedKey": json.dumps({"SCENE_1": {"protectedKey": protected,
                                                "version": str(now_ms + 86400000),
                                                "negotiationVersion": cfg["neg"]}}),
    }
    c = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
    enc = c.encryptor()
    ct = enc.update(json.dumps(body).encode()) + enc.finalize()
    wire = json.dumps({"params": json.dumps({"cipher": base64.b64encode(ct).decode(),
                                             "iv": base64.b64encode(iv).decode()})})
    try:
        r = requests.post(f"https://{cfg['host']}/update/v3", headers=headers,
                          data=wire, timeout=TIMEOUT)
        j = r.json()
    except Exception:
        return None
    if j.get("responseCode") != 200:
        return None
    try:
        inner = json.loads(j["body"])
        d = Cipher(algorithms.AES(aes_key), modes.CTR(base64.b64decode(inner["iv"])))
        dec = d.decryptor()
        content = json.loads(dec.update(base64.b64decode(inner["cipher"])) + dec.finalize())
    except Exception:
        return None
    comps = content.get("components") or []
    if not comps:
        return None
    comp = comps[0]
    pkts = comp.get("componentPackets") or {}
    url = pkts.get("manualUrl") or pkts.get("url") or ""
    return {
        "letter": letter,
        "fw": fw,
        "version": content.get("versionName") or "",
        "fp": content.get("otaVersion") or "",      # 完整指纹（fake otaVersion）
        "real": content.get("realOtaVersion") or "",
        "url": url,
        "size": pkts.get("size") or "",
        "md5": pkts.get("md5") or "",
        "patch": content.get("securityPatch") or "",
        "published": content.get("publishedTime") or 0,
        "android": content.get("androidVersion") or "",
    }


# ─────────────── descriptionInfo（官方 changelog） ───────────────
def changelog_query(model, fp_prefix, region="cn"):
    """fp_prefix 形如 PLQ110_11.A.57_0570（不含时间戳）。返回 (version_name, md_text)。"""
    cfg = REGIONS[region]
    full = f"{fp_prefix}_197001010000"
    headers = {
        "language": cfg["lang"], "nvCarrier": cfg["carrier"], "mode": "manual",
        "osVersion": "unknown", "maskOtaVersion": full, "otaVersion": full,
        "model": model, "androidVersion": "unknown",
        "Content-Type": "application/json", "User-Agent": "okhttp/3.12.12",
    }
    payload = {"params": json.dumps({"mode": 0, "maskOtaVersion": full,
                                     "bigVersion": 0, "h5LinkVersion": 6})}
    try:
        r = requests.post(f"https://{cfg['host']}/descriptionInfo",
                          headers=headers, json=payload, timeout=TIMEOUT)
        j = r.json()
    except Exception:
        return None
    if j.get("responseCode") != 200:
        return None
    try:
        data = json.loads(j["body"])
    except Exception:
        return None
    version = data.get("versionName") or ""
    md = render_changelog(data, region)
    return version, md


def render_changelog(data, region):
    items = data.get("upgInstDetail") or []
    if not items:
        return "官方无更新日志。\n"

    def text_of(ci):
        if isinstance(ci, dict):
            return ci.get("data", "")
        return str(ci)

    lines = []
    first_block = True
    for item in items:
        children = item.get("children")
        if children:
            for child in children:
                title = child.get("title", "")
                content = child.get("content", [])
                if title:
                    if not first_block:
                        lines.append("")
                    lines.append(f"## {title}")
                for ci in content:
                    t = text_of(ci)
                    if t:
                        lines.append(f"- {t}")
                first_block = False
        else:
            title = item.get("title", "")
            content = item.get("content", [])
            if title:
                if not first_block:
                    lines.append("")
                lines.append(f"## {title}")
            for ci in content:
                t = text_of(ci)
                if t:
                    lines.append(f"- {t}")
            first_block = False
    if not lines:
        return "官方无更新日志。\n"
    return "\n".join(lines) + "\n"


def fp_prefix(fp):
    """PLQ110_11.A.57_0570_202608071758 -> PLQ110_11.A.57_0570"""
    return fp.rsplit("_", 1)[0] if fp.count("_") >= 2 else fp


# ─────────────── downgrade（官方降级包） ───────────────
def downgrade_query(model, letter, prj, duid="498A44DF1BEC4EB19FBCB3A870FCACB4EC7D424979CC9C517FE7B805A1937746"):
    cfg = KEYS["DOWNGRADE"]
    neg = cfg["negotiation_version"]
    pub = load_dg_pub()

    def enc_gcm(aes_key, iv, plaintext):
        c = Cipher(algorithms.AES(aes_key), modes.GCM(iv))
        e = c.encryptor()
        ct = e.update(plaintext) + e.finalize()
        return ct + e.tag

    key_pt = "SCENE_1@" + duid
    proto = base64.b64encode(
        pub.encrypt(key_pt.encode(),
                    padding.OAEP(mgf=padding.MGF1(hashes.SHA1()),
                                 algorithm=hashes.SHA1(), label=None))
    ).decode()
    aes_key = os.urandom(32)
    iv = os.urandom(12)
    enc_dev = enc_gcm(aes_key, iv, duid.encode())
    protected_all = base64.b64encode(
        pub.encrypt(base64.b64encode(aes_key),
                    padding.OAEP(mgf=padding.MGF1(hashes.SHA1()),
                                 algorithm=hashes.SHA1(), label=None))
    ).decode()
    headers = {
        "Host": "downgrade.coloros.com",
        "Content-Type": "application/json; charset=utf-8",
        "cipherInfo": json.dumps({"downgrade-server": {
            "negotiationVersion": neg, "protectedKey": protected_all,
            "version": str(int(time.time()))}}),
        "connection": "close",
        "deviceId": duid,
        "User-Agent": "okhttp/3.12.12",
    }
    payload = {
        "model": model, "nvCarrier": "10010111", "prjNum": str(prj),
        "serialNo": "a1b2c3d4", "otaVersion": f"{model}_11.{letter}",
        "deviceId": {"cipher": base64.b64encode(enc_dev).decode(),
                     "iv": base64.b64encode(iv).decode()},
    }
    requests.packages.urllib3.disable_warnings()
    try:
        r = requests.post(cfg["url"], headers=headers, json=payload,
                          timeout=TIMEOUT, verify=False)
        if r.status_code != 200:
            return None
        j = r.json()
        if isinstance(j, dict) and j.get("code") == 1004:
            return None  # DUID query GUID is empty
        # 服务端两态：明文 {code:200,data:{downgradeVoList}} 或 密文 {cipher,iv}
        if "cipher" in j:
            resp_cipher = base64.b64decode(j["cipher"])
            iv2 = base64.b64decode(j["iv"])
            d = Cipher(algorithms.AES(aes_key), modes.GCM(iv2, resp_cipher[-16:]))
            dec = d.decryptor()
            inner = json.loads(dec.update(resp_cipher[:-16]) + dec.finalize())
        else:
            inner = j
    except Exception:
        return None
    if inner.get("code") != 200:
        return None
    vo = (inner.get("data") or {}).get("downgradeVoList") or []
    return vo


# ─────────────── 文件维护 ───────────────
def history_path(model):
    return os.path.join(ROOT, "models", model, "ota-version.txt")


def links_path(model, ver):
    safe = re.sub(r'[\\/:*?"<>|]', "_", ver)
    return os.path.join(ROOT, "links", model, f"{safe}.txt")


def changelog_path(model, fp):
    return os.path.join(ROOT, "models", model, "changelog", f"{fp_prefix(fp)}.md")


def latest_path(model):
    return os.path.join(ROOT, "models", model, "latest-update.txt")


def downgrade_path(model):
    return os.path.join(ROOT, "downgrade", f"{model}.txt")


def read_history(model):
    p = history_path(model)
    if not os.path.isfile(p):
        return {}
    out = {}
    for ln in open(p, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        if " # " in ln:
            fp, ver = ln.split(" # ", 1)
            ver = ver.replace("ColorOS: ", "")
        else:
            fp, ver = ln, ""
        out[fp] = ver
    return out


def write_history(model, history):
    rows = sorted(history.items(),
                  key=lambda kv: (kv[0].rsplit("_", 1)[-1] if kv[0].count("_") >= 2 else kv[0]),
                  reverse=True)
    os.makedirs(os.path.dirname(history_path(model)), exist_ok=True)
    with open(history_path(model), "w", encoding="utf-8") as f:
        for fp, ver in rows:
            if ver:
                f.write(f"{fp}  # ColorOS: {ver}\n")
            else:
                f.write(f"{fp}\n")
    return len(rows)


def write_link(model, ver, url):
    os.makedirs(os.path.dirname(links_path(model, ver)), exist_ok=True)
    with open(links_path(model, ver), "w", encoding="utf-8") as f:
        f.write(url.strip() + "\n")


def write_latest(model, info):
    os.makedirs(os.path.dirname(latest_path(model)), exist_ok=True)
    lines = [
        f"本地更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"查询地区: {info.get('region','CN')}",
        f"最新 OTA 版本: {info.get('fp','')}",
        f"版本名称: {info.get('version','')}",
        f"Android 版本: {info.get('android','') or 'Android' + info.get('android','')}",
        f"ColorOS 版本: {info.get('version','')}",
        f"安全补丁: {info.get('patch','')}",
        f"发布时间: {info.get('published','')}",
        f"ROM 下载链接: {info.get('url','')}",
        "",
    ]
    with open(latest_path(model), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_changelog(model, fp, version, md):
    p = changelog_path(model, fp)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    head = f"# {version or fp}\n\n> 官方更新日志 · 来源: OTA descriptionInfo\n> OTA 指纹: `{fp}`\n\n"
    with open(p, "w", encoding="utf-8") as f:
        f.write(head + md)


def write_downgrade(model, items):
    p = downgrade_path(model)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    seen = set()
    uniq = []
    for it in items:
        url = it.get("downloadUrl", "")
        if not url or url in seen:
            continue
        seen.add(url)
        uniq.append(it)
    lines = [f"# 官方降级包（downgrade.coloros.com 直链） · 更新时间 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for it in uniq:
        url = it.get("downloadUrl", "")
        if not url:
            continue
        ver = it.get("otaVersion", "")
        cver = it.get("colorosVersion", "")
        size = it.get("fileSize", "")
        md5 = it.get("fileMd5", "")
        android = it.get("androidVersion", "")
        lines.append(f"### {cver or ver}")
        if android:
            lines.append(f"- Android: {android}")
        if size:
            lines.append(f"- 大小: {size}")
        if md5:
            lines.append(f"- MD5: {md5}")
        lines.append(f"- 链接: {url}")
        intro = it.get("versionIntroduction", "")
        if intro:
            lines.append(f"- 更新说明: {intro[:200]}")
        lines.append("")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# 各区域机型 code 常见的后缀写法（RMX2202RU / CPH2551IN / CPH2477EEA）。
# 带后缀的串在 v3 的 model header 里查不到，必须去掉后缀用裸 code 重试。
REGION_SUFFIX = {
    "cn": ("CN",), "in": ("IN",), "eu": ("EEA", "EU"), "gl": (),
    "tw": ("TW",), "ru": ("RU",), "tr": ("TR",), "gb": ("GB",),
    "sg": ("SG",), "id": ("ID",), "my": ("MY",), "vn": ("VN",),
    "th": ("TH",), "ph": ("PH",), "sa": ("SA",), "mea": ("MEA",),
    "latam": ("LATAM", "LA"), "br": ("BR",), "kz": ("KZ",),
    "oca": ("OCA",), "apc": ("APC",), "eg": ("EG",), "lk": ("LK",),
    "mx": ("MX",), "na": ("NA",),
}
_CODE_SUFFIX_RE = re.compile(r"^([A-Z]{2,4}\d{3,5})([A-Z]{2,4})$")


def code_variants(code, region):
    """返回待试的 model 串，原串优先，其次是去区域后缀的裸 code。"""
    m = _CODE_SUFFIX_RE.match(code)
    if not m:
        return [code]
    base, suffix = m.group(1), m.group(2)
    out = [code]
    if suffix in REGION_SUFFIX.get(region, ()) or suffix in (
            "RU", "IN", "EEA", "EU", "TW", "ID", "MY", "VN", "TH",
            "PH", "SA", "MEA", "KZ", "BR", "LA", "LATAM", "OCA", "APC",
            "EG", "LK", "MX", "NA", "SG", "TR", "GB", "CN"):
        out.append(base)
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


# ─────────────── 主流程 ───────────────
def scan_region(code, region, variants, history):
    """在一个网关上扫 variant × nvid × letter。
    返回 (hits, new_fp, new_links, latest)。会临时改写 REGIONS[region]['nvid']。"""
    hits, new_fp, new_links, latest = [], 0, 0, None
    nvid_seq = NVID_FALLBACK.get(region, [REGIONS[region]["nvid"]])
    saved = REGIONS[region]["nvid"]
    try:
        for variant in variants:
            for nvid in nvid_seq:
                REGIONS[region]["nvid"] = nvid
                before = len(hits)
                for letter in LETTER_POOL:
                    res = v3_query(variant, region, letter)
                    if not res or not res["url"]:
                        time.sleep(GAP)
                        continue
                    hits.append(letter)
                    fp = res["fp"] or res["fw"]
                    ver = res["version"]
                    if not history.get(fp):
                        history[fp] = ver
                        new_fp += 1
                        if ver:
                            write_link(code, ver, res["url"])
                            new_links += 1
                    if latest is None:
                        latest = res
                    time.sleep(GAP)
                if len(hits) > before:
                    break          # 该 nvid 有产出，不再试回退值
            if hits:
                break              # 该 variant 已命中，无需再去后缀重试
    finally:
        REGIONS[region]["nvid"] = saved
    return hits, new_fp, new_links, latest


def update_model(model, opts):
    code = model["code"]
    region = region_of(model)
    history = read_history(code)
    variants = code_variants(code, region)

    hits, new_fp, new_links, latest = scan_region(code, region, variants, history)

    # 主区域全落空 -> 按 GATEWAY_FALLBACK 成套切换 host+公钥+nvid 再试
    if not hits and not opts.no_gateway_fallback:
        for alt in GATEWAY_FALLBACK:
            if alt == region:
                continue
            h, f, l, lt = scan_region(code, alt, code_variants(code, alt), history)
            if h:
                print(f"  {code} 主区域 {region} 无产出，改走 {alt} 命中 {'/'.join(h)}")
                hits = h
                new_fp += f
                new_links += l
                latest = latest or lt
                region = alt
                break
    elif not hits and len(variants) > 1:
        print(f"  {code} 原串与去后缀串均未命中")

    if new_fp:
        write_history(code, history)
    if latest and (new_fp or not os.path.isfile(latest_path(code))):
        latest["region"] = region.upper()
        write_latest(code, latest)

    # changelog：对每条有版本名的指纹补官方日志（--only-changelog 时全补）
    clogs = 0
    for fp, ver in (() if opts.only_latest else history.items()):
        if not ver or not fp:
            continue
        cp = changelog_path(code, fp)
        if os.path.isfile(cp) and not opts.only_changelog:
            continue
        rr = changelog_query(code, fp_prefix(fp), region)
        time.sleep(GAP)
        if not rr:
            continue
        cver, md = rr
        cver = cver or ver
        if cver and not history[fp]:
            history[fp] = cver
        write_changelog(code, fp, cver, md)
        clogs += 1
    if clogs and not opts.no_history_write:
        write_history(code, history)

    # downgrade（仅 CN 机型且配置了项目号）
    done_dg = False
    if not opts.no_downgrade and not opts.only_latest and region == "cn":
        entry = PNREF.get("models", {}).get(code)
        prj = entry.get("prj") if entry else None
        if prj:
            all_items = []
            for letter in ("A", "C", "F", "H", "J"):
                vo = downgrade_query(code, letter, prj)
                time.sleep(GAP)
                if vo:
                    all_items.extend(vo)
            if all_items:
                write_downgrade(code, all_items)
                done_dg = True

    print(f"  {code:10s} {region:2s} 分支命中 {len(hits)}{''.join(hits)} "
          f"新增指纹 {new_fp} 新链接 {new_links} changelog {clogs}"
          + (f" 降级包 ✓" if done_dg else ""))
    return {"code": code, "region": region, "new_fp": new_fp,
            "new_links": new_links, "changelog": clogs, "downgrade": done_dg}


def main():
    ap = argparse.ArgumentParser(description="oplus-version-history 官方更新器")
    ap.add_argument("--model", help="单机型 code")
    ap.add_argument("--region", choices=sorted(REGIONS.keys()),
                    help="只处理映射到该官方网关的机型（CI 按网关分片，避免单次全量超时）")
    ap.add_argument("--only-changelog", action="store_true", help="只补 changelog")
    ap.add_argument("--only-latest", action="store_true",
                    help="只补 latest-update.txt（跳过 changelog 与降级包），用于补齐机型元数据")
    ap.add_argument("--no-downgrade", action="store_true", help="跳过降级包")
    ap.add_argument("--no-history-write", action="store_true", help="不写版本史文件")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 个机型（测试用）")
    ap.add_argument("--no-gateway-fallback", action="store_true",
                    help="主区域无产出时不跨网关重试（更快，但会漏掉区域标记错误的机型）")
    ap.add_argument("--shard", help="分片，形如 0/4（配合多进程并行回填）")
    opts = ap.parse_args()

    if opts.model:
        models = [m for m in MODELS if m["code"] == opts.model.upper()]
        if not models:
            sys.exit(f"机型 {opts.model} 不在清单里")
    else:
        models = MODELS
    if opts.region:
        models = [m for m in models if region_of(m) == opts.region]
        if not models:
            sys.exit(f"网关 {opts.region} 下没有机型")
    if opts.shard:
        try:
            idx, total = (int(x) for x in opts.shard.split("/"))
        except ValueError:
            sys.exit("--shard 需要形如 0/4 的写法")
        if not 0 <= idx < total:
            sys.exit(f"--shard 索引 {idx} 超出 0..{total - 1}")
        models = [m for i, m in enumerate(models) if i % total == idx]
    if opts.limit:
        models = models[: opts.limit]

    print(f"共 {len(models)} 个机型，区域分布: { {r: sum(1 for m in models if region_of(m) == r) for r in REGIONS} }")
    t0 = time.time()
    stats = {"new_fp": 0, "new_links": 0, "changelog": 0, "downgrade": 0}
    for i, m in enumerate(models, 1):
        r = update_model(m, opts)
        stats["new_fp"] += r["new_fp"]
        stats["new_links"] += r["new_links"]
        stats["changelog"] += r["changelog"]
        stats["downgrade"] += r["downgrade"]
        if i % 20 == 0:
            print(f"  ... {i}/{len(models)} 用时 {time.time()-t0:.0f}s")
    print(f"完成：新增指纹 {stats['new_fp']} 新链接 {stats['new_links']} "
          f"changelog {stats['changelog']} 降级包 {stats['downgrade']} 用时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()