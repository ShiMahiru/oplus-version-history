


import argparse
import bz2
import json
import lzma
import os
import struct
import sys
import time
import zipfile
from typing import Dict, List, Optional, Tuple

import requests

MAGIC = b"CrAU"

DATA_OP_TYPES = frozenset({0, 1, 8, 12, 13})

OP_NAMES = {
    0: "REPLACE",
    1: "REPLACE_BZ",
    2: "MOVE",
    3: "BSDIFF",
    4: "SOURCE_COPY",
    5: "SOURCE_BSDIFF",
    6: "ZERO",
    7: "DISCARD",
    8: "REPLACE_XZ",
    9: "PUFFDIFF",
    10: "BROTLI_BSDIFF",
    11: "ZUCCHINI",
    12: "LZ4DIFF_BSDIFF",
    13: "LZ4DIFF_PUFFDIFF",
}

COMPRESSED_OP_TYPES = frozenset({1, 8, 9, 10, 11, 12, 13})

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
    "userId": "oplus-ota|16002018",
}


def default_out_dir() -> str:
    
    for cand in (
        "/sdcard/Android/data/io.otatracker/files/OTA",
        "/storage/emulated/0/Android/data/io.otatracker/files/OTA",
    ):
        if os.path.isdir(os.path.dirname(os.path.dirname(cand))):
            return cand
    return os.path.join(os.getcwd(), "ota_out")


class ExtractorError(Exception):
    pass


class Cancelled(Exception):
    pass


class RangeReader:
    

    def __init__(self, url: str, session: Optional[requests.Session] = None, timeout: int = 30, no_ua: bool = False):
        self.url = url
        self.session = session or requests.Session()
        self.timeout = timeout
        self.pos = 0
        self._file = None
        self.no_ua = no_ua

        path = url
        if path.lower().startswith("file://"):
            path = path[7:]
        if not path.lower().startswith(("http://", "https://")):
            if not os.path.isfile(path):
                raise ExtractorError(f"找不到这个文件：{path}")
            self._file = open(path, "rb")
            self.size = os.path.getsize(path)
        else:
            self.size = self._probe_size()
            self.url = self._final_url or self.url

    def _probe_size(self) -> int:
        hdrs = self._headers()
        try:
            r = self.session.get(
                self.url,
                headers=dict(hdrs, Range="bytes=0-0"),
                timeout=self.timeout,
                stream=True,
                allow_redirects=True,
            )
        except Exception as e:
            raise ExtractorError(f"连不上这个链接：{e}")
        if r.status_code == 403:
            r.close()
            raise ExtractorError("链接被 CDN 拒绝（403）。链接可能已过期，或需要换网络。")
        if r.status_code == 404:
            r.close()
            raise ExtractorError("链接已失效（404）。")
        if r.status_code not in (200, 206):
            code = r.status_code
            r.close()
            raise ExtractorError(f"服务器返回 {code}。")
        self._final_url = r.url
        if not self._is_zip_url():
            self._final_url = self.url
        cr = r.headers.get("Content-Range", "")
        r.close()
        if "/" not in cr:
            raise ExtractorError("服务器不支持断点分段，无法只下需要的部分。")
        total = cr.split("/", 1)[1].strip()
        if total == "*":
            raise ExtractorError("服务器没有给出文件大小。")
        return int(total)

    def _headers(self) -> dict:
        if self.no_ua:
            h = dict(HEADERS)
            h.pop("User-Agent", None)
            return h
        return HEADERS

    def _is_zip_url(self) -> bool:
        u = (self._final_url or self.url).lower().split("?")[0]
        return u.endswith(".zip")

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.size + offset
        else:
            raise ExtractorError(f"不支持的 whence：{whence}")
        return self.pos

    def tell(self) -> int:
        return self.pos

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return True

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def read(self, n: int = -1) -> bytes:
        if self._file is not None:
            self._file.seek(self.pos)
            blob = self._file.read(n)
            self.pos += len(blob)
            return blob

        if n < 0:
            n = max(0, self.size - self.pos)
        if n == 0:
            return b""
        end = self.pos + n - 1
        r = self.session.get(
            self.url,
            headers=dict(self._headers(), Range=f"bytes={self.pos}-{end}"),
            timeout=self.timeout,
            stream=True,
            allow_redirects=True,
        )
        if r.status_code not in (200, 206):
            r.close()
            raise ExtractorError(f"分段请求失败：HTTP {r.status_code}（offset={self.pos}, len={n}）")
        buf = bytearray()
        for piece in r.iter_content(65536):
            if piece:
                buf.extend(piece)
        r.close()
        self.pos += len(buf)
        return bytes(buf)


def _read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ExtractorError("payload 元数据不完整（varint 越界）。")
        b = buf[pos]
        pos += 1
        result |= (b & 127) << shift
        if not (b & 128):
            return result, pos
        shift += 7
        if shift > 63:
            raise ExtractorError("payload 元数据异常（varint 过长）。")


def _fields(buf: bytes):
    
    pos, end = 0, len(buf)
    while pos < end:
        key, pos = _read_varint(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(buf, pos)
        elif wire == 2:
            length, pos = _read_varint(buf, pos)
            if pos + length > end:
                raise ExtractorError("payload 元数据被截断。")
            value = buf[pos:pos + length]
            pos += length
        elif wire == 5:
            value = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
        elif wire == 1:
            value = struct.unpack_from("<Q", buf, pos)[0]
            pos += 8
        else:
            raise ExtractorError("payload 元数据里有未知字段类型 %d。" % wire)
        yield field, wire, value


def parse_payload_header(reader: RangeReader, payload_offset: int) -> Tuple[bytes, int]:
    
    reader.seek(payload_offset)
    head = reader.read(24)
    if len(head) < 24:
        raise ExtractorError("payload 头读不完整。")
    if head[:4] != MAGIC:
        raise ExtractorError(
            "这不是标准 OTA payload（没有 CrAU 魔数）。\n可能是 A-only 旧包，或包内为加密的 payload。"
        )
    version = struct.unpack_from(">Q", head, 4)[0]
    manifest_size = struct.unpack_from(">Q", head, 12)[0]
    if version < 2:
        raise ExtractorError("payload 版本 %d 太旧，不支持。" % version)
    signature_size = struct.unpack_from(">I", head, 20)[0]
    if manifest_size <= 0 or manifest_size > 67108864:
        raise ExtractorError("manifest 大小异常：%d 字节。" % manifest_size)
    manifest_bytes = reader.read(manifest_size)
    data_offset = payload_offset + 24 + manifest_size + signature_size
    return manifest_bytes, data_offset


def parse_manifest(manifest_bytes: bytes) -> Dict:
    partitions: List[Dict] = []
    security_patch = ""
    block_size = 4096
    for field, wire, value in _fields(manifest_bytes):
        if field == 13 and wire == 2:
            partitions.append(_parse_partition(value))
        elif field == 18 and wire == 2:
            security_patch = value.decode("utf-8", "replace")
        elif field == 3 and wire == 0:
            block_size = value or 4096
    return {
        "partitions": partitions,
        "security_patch": security_patch,
        "block_size": block_size,
    }


def _parse_partition_info(buf: bytes) -> int:
    
    for field, wire, value in _fields(buf):
        if field == 1 and wire == 0:
            return value
    return 0


def _parse_partition(buf: bytes) -> Dict:
    name = ""
    ops: List[Dict] = []
    image_size = 0
    for field, wire, value in _fields(buf):
        if field == 1 and wire == 2:
            name = value.decode("utf-8", "replace")
        elif field == 8 and wire == 2:
            ops.append(_parse_operation(value))
        elif field == 7 and wire == 2:
            image_size = _parse_partition_info(value)

    info = {
        "name": name,
        "offset": 0,
        "length": 0,
        "image_size": image_size,
        "ops": ops,
        "op_names": sorted({OP_NAMES.get(o["op_type"], str(o["op_type"])) for o in ops}),
        "compressed": any(o["op_type"] in COMPRESSED_OP_TYPES for o in ops),
    }
    if not ops:
        return info
    data_ops = [o for o in ops if o["op_type"] in DATA_OP_TYPES]
    if not data_ops:
        return info
    start = min(o["data_offset"] for o in data_ops)
    end = max(o["data_offset"] + o["data_length"] for o in data_ops)
    info["offset"] = start
    info["length"] = end - start
    return info


def _parse_operation(buf: bytes) -> Dict:
    op = {"data_offset": 0, "data_length": 0, "op_type": 0}
    for field, wire, value in _fields(buf):
        if field == 1 and wire == 0:
            op["op_type"] = value
        elif field == 2 and wire == 0:
            op["data_offset"] = value
        elif field == 3 and wire == 0:
            op["data_length"] = value
    return op


def _zip_data_offset(reader: RangeReader, info: zipfile.ZipInfo) -> int:
    reader.seek(info.header_offset)
    head = reader.read(30)
    if len(head) < 30:
        raise ExtractorError("zip 条目头读不完整。")
    name_len = struct.unpack_from("<H", head, 26)[0]
    extra_len = struct.unpack_from("<H", head, 28)[0]
    return info.header_offset + 30 + name_len + extra_len


def resolve_direct(url: str, timeout: int = 30) -> str:
    
    if not url.lower().startswith(("http://", "https://")):
        return url
    if not ("downloadCheck" in url or "/download?" in url):
        return url
    r = requests.get(
        url,
        headers=dict(HEADERS, Range="bytes=0-0"),
        timeout=timeout,
        stream=True,
        allow_redirects=False,
    )
    loc = r.headers.get("Location", "")
    r.close()
    if loc:
        return loc
    r2 = requests.get(url, headers=dict(HEADERS, Range="bytes=0-0"),
                      timeout=timeout, stream=True, allow_redirects=True)
    final = r2.url
    r2.close()
    return final or url


def open_payload(url: str, no_ua: bool = False) -> Tuple[RangeReader, Dict]:
    
    url = resolve_direct(url)
    reader = RangeReader(url, no_ua=no_ua)
    payload_offset = 0
    if url.lower().split("?")[0].endswith(".zip"):
        reader.seek(0)
        try:
            zf = zipfile.ZipFile(reader)
            infos = zf.infolist()
        except ExtractorError:
            raise
        except Exception as e:
            raise ExtractorError("读不出 zip 目录：%s" % e)
        found = None
        for info in infos:
            if info.filename in ("payload.bin", "payload/payload.bin"):
                found = info
                break
        if found is None:
            names = ", ".join(i.filename for i in infos[:6])
            raise ExtractorError("zip 里没有 payload.bin。\n包内前几项：" + names)
        payload_offset = _zip_data_offset(reader, found)

    manifest_bytes, data_offset = parse_payload_header(reader, payload_offset)
    manifest = parse_manifest(manifest_bytes)
    manifest["_payload_data_offset"] = data_offset
    manifest["_file_size"] = reader.size
    return reader, manifest


def _decompress(op_type: int, blob: bytes, block_size: int) -> bytes:
    
    if op_type == 0:

        return blob
    if op_type == 1:

        return bz2.decompress(blob)
    if op_type == 8:

        return lzma.decompress(blob)
    if op_type in (6, 7):

        return b"\x00" * len(blob)
    raise ExtractorError(
        "分区用了差分包专属操作 %s，无法从全量包还原。"
        % OP_NAMES.get(op_type, str(op_type))
    )


def extract(
    reader: RangeReader,
    manifest: Dict,
    part: Dict,
    out_dir: str,
    progress_file: Optional[str] = None,
    cancel_file: Optional[str] = None,
) -> str:
    if part["length"] <= 0:
        raise ExtractorError("分区 %s 在包里没有可下载的数据。" % part["name"])

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, part["name"] + ".img")

    free = None
    try:
        st = os.statvfs(out_dir)
        free = st.f_bavail * st.f_frsize
    except Exception:
        free = None

    need = max(part.get("image_size") or 0, part["length"])
    if free is not None and free < need + 33554432:
        raise ExtractorError(
            "空间不够：需要 %.2f GB，可用 %.2f GB。" % (need / 1073741824, free / 1073741824)
        )

    base = manifest["_payload_data_offset"]
    block_size = manifest.get("block_size") or 4096
    ops = part.get("ops") or []
    if not ops:
        ops = [{"op_type": 0, "data_offset": part["offset"], "data_length": part["length"]}]

    total = sum(o["data_length"] for o in ops)
    written = 0
    out_bytes = 0
    started = time.time()
    last_report = 0.0

    def report(done: bool = False, error: str = ""):
        if not progress_file:
            return
        payload = {
            "partition": part["name"],
            "out_path": out_path,
            "done": bool(done),
            "error": error,
            "total": total,
            "written": written,
            "out_size": out_bytes,
            "image_size": part.get("image_size") or 0,
            "elapsed": round(time.time() - started, 2),
        }
        try:
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except Exception:
            pass

    report()
    with open(out_path, "wb") as f:
        for op in ops:
            if cancel_file and os.path.exists(cancel_file):
                f.close()
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                raise Cancelled("已取消")

            dlen = op["data_length"]
            dpos = base + op["data_offset"]
            buf = bytearray()
            while len(buf) < dlen:
                if cancel_file and os.path.exists(cancel_file):
                    f.close()
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass
                    raise Cancelled("已取消")
                want = min(2097152, dlen - len(buf))
                reader.seek(dpos + len(buf))
                blob = reader.read(want)
                if not blob:
                    raise ExtractorError("下载中断，已收到 %.1f MB。" % (written / 1048576))
                buf.extend(blob)
                written += len(blob)
                now = time.time()
                if now - last_report > 0.4:
                    last_report = now
                    report()

            data = _decompress(op["op_type"], bytes(buf), block_size)
            f.write(data)
            out_bytes += len(data)

        img_size = part.get("image_size") or 0
        if img_size > out_bytes:
            remaining = img_size - out_bytes
            zero_chunk = b"\x00" * (1024 * 1024)
            while remaining > 0:
                n = min(len(zero_chunk), remaining)
                f.write(zero_chunk[:n])
                remaining -= n
            out_bytes = img_size

    report(True)
    return out_path


def _json_out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_dump(url: str, as_json: bool = False) -> int:
    reader, manifest = open_payload(url)
    parts = manifest["partitions"]
    rows = []
    for p in parts:
        rows.append({
            "name": p["name"],
            "image_size": p["image_size"],
            "offset": p["offset"],
            "length": p["length"],
            "ops": p["op_names"],
            "compressed": p["compressed"],
        })
    if as_json:
        _json_out({
            "file_size": manifest.get("_file_size"),
            "payload_data_offset": manifest.get("_payload_data_offset"),
            "block_size": manifest.get("block_size"),
            "security_patch": manifest.get("security_patch"),
            "partitions": rows,
        })
    else:
        print(f"包大小: {manifest.get('_file_size')} 字节")
        print(f"payload 数据区起点: {manifest.get('_payload_data_offset')}")
        print(f"安全补丁: {manifest.get('security_patch')}   块大小: {manifest.get('block_size')}")
        print(f"分区 {len(rows)} 个：")
        print(f"  {'name':22s} {'image_size':>14s} {'length':>14s}  压缩  ops")
        for r in rows:
            print(f"  {r['name']:22s} {r['image_size']:14d} {r['length']:14d}  "
                  f"{'是' if r['compressed'] else '否':2s}  {','.join(r['ops'])}")
    reader.close()
    return 0


def cmd_pull(url: str, part_names, out_dir: str, all_parts: bool = False,
             progress_file: Optional[str] = None, cancel_file: Optional[str] = None) -> int:
    reader, manifest = open_payload(url)
    parts = manifest["partitions"]
    if all_parts:
        todo = [p for p in parts if p["length"] > 0]
    else:
        want = list(part_names or [])
        have = {p["name"] for p in parts}
        missing = [n for n in want if n not in have]
        if missing:
            avail = ", ".join(p["name"] for p in parts if p["length"] > 0)
            raise ExtractorError(f"包里没有分区 {', '.join(missing)}。可用：{avail}")
        todo = [p for p in parts if p["name"] in want]
        if not todo:
            raise ExtractorError("没有可提取的分区。")
    total_bytes = sum(p["length"] for p in todo)
    print(f"准备提取 {len(todo)} 个分区，共 {total_bytes / 1048576:.1f} MB（包总大小 "
          f"{(manifest.get('_file_size') or 0) / 1048576 / 1024:.2f} GB）")
    for p in todo:
        t0 = time.time()
        path = extract(reader, manifest, p, out_dir,
                       progress_file=progress_file, cancel_file=cancel_file)
        got = os.path.getsize(path)
        print(f"  ✓ {p['name']:20s} {got / 1048576:8.2f} MB  "
              f"{time.time() - t0:5.1f}s  → {path}"
              + ("  （压缩数据，需解压）" if p["compressed"] else ""))
    reader.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="从 OTA zip 里按分区远程提取镜像，不用下整包。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="列出包内分区与字节区间")
    d.add_argument("url", help="OTA zip 链接（或本地路径 / file://）")
    d.add_argument("--json", action="store_true", help="以 JSON 输出")

    p = sub.add_parser("pull", help="提取指定分区")
    p.add_argument("url", help="OTA zip 链接（或本地路径 / file://）")
    p.add_argument("parts", nargs="*", help="分区名（可多个，如 boot init_boot dtbo）")
    p.add_argument("--all", action="store_true", help="提取全部分区")
    p.add_argument("-o", "--out", default=None, help="输出目录")
    p.add_argument("--progress-file", default=None, help="进度 JSON 文件路径")
    p.add_argument("--cancel-file", default=None, help="该文件出现即取消")

    args = ap.parse_args()
    try:
        if args.cmd == "dump":
            return cmd_dump(args.url, as_json=args.json)
        out_dir = args.out or default_out_dir()
        parts = list(args.parts or [])
        if not parts and not args.all:
            raise ExtractorError("pull 需要分区名，或用 --all 提取全部。")
        return cmd_pull(args.url, parts, out_dir, all_parts=args.all,
                        progress_file=args.progress_file, cancel_file=args.cancel_file)
    except Cancelled as e:
        print(f"已取消：{e}")
        return 130
    except ExtractorError as e:
        print(f"错误：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())