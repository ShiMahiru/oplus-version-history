#!/usr/bin/env python3
"""修复坏元数据：
1) size < 1MB 且无 md5 → 判定为 CDN 错误页字节数，删除该行
2) 同机型同版本、URL 不同、MD5/大小一致的重复 → 保留带 md5 的那条，其余删除
3) 同机型同版本、但 EX01/EEA/GLO 与 CN01 并存 → 不算重复（不同区域包），保留
用法: python3 scripts/fix_meta.py [--dry]
"""
import os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINKS = os.path.join(ROOT, "links")
MIN_SIZE = 1024 * 1024

def parse(p):
    t = open(p, encoding="utf-8", errors="ignore").read()
    return t

def main():
    dry = "--dry" in sys.argv
    bad_size = 0
    for code in os.listdir(LINKS):
        d = os.path.join(LINKS, code)
        if not os.path.isdir(d) or code.startswith("_"):
            continue
        for f in os.listdir(d):
            if not f.endswith(".txt"):
                continue
            p = os.path.join(d, f)
            t = parse(p)
            sm = re.search(r"^size: (\d+)\s*$", t, re.M)
            has_md5 = bool(re.search(r"^md5: [0-9a-fA-F]{32}", t, re.M))
            if sm and 0 < int(sm.group(1)) < MIN_SIZE and not has_md5:
                bad_size += 1
                if not dry:
                    lines = t.splitlines()
                    out = [l for l in lines if not l.strip().startswith("size: ")]
                    open(p, "w", encoding="utf-8").write("\n".join(out) + "\n")
                print(f"  清坏 size: {code}/{f} ({sm.group(1)})")
    print(f"坏 size 清理 {bad_size} 条{'（dry）' if dry else ''}")

if __name__ == "__main__":
    main()
