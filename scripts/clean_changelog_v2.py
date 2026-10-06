#!/usr/bin/env python3
"""深度清洗 changelog 竖排碎行：连续短列表项（≤2字符）拼回句子/编号列表。"""
import glob, re

def clean(text):
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    SHORT = re.compile(r"^- (.{0,2})$")   # "- x" / "- " / "- .."
    NUM = re.compile(r"^(\d+)\.\s*$")     # "1."
    while i < n:
        line = lines[i]
        m_short = SHORT.match(line.strip())
        m_num = NUM.match(line.strip())
        if m_num:
            # 编号列表：N. 后跟连续短项拼成 "N. 内容"
            num = m_num.group(1)
            i += 1
            chars = []
            while i < n:
                raw = lines[i]
                s = raw.strip()
                if s == "-":
                    chars.append(" ")
                    i += 1
                elif SHORT.match(s):
                    chars.append(raw[raw.index("-") + 2:])
                    i += 1
                elif s == "":
                    i += 1
                    # 空行后若还是短项继续，否则停
                    if i < n and (lines[i].strip() == "-" or SHORT.match(lines[i].strip())):
                        continue
                    break
                else:
                    break
            content = "".join(chars).strip()
            out.append(f"{num}. {content}" if content else f"{num}.")
            continue
        if m_short:
            # 普通短项流：连续短项拼回一段（用原始行取 body，保留空格）
            chars = []
            while i < n:
                raw = lines[i]
                s = raw.strip()
                if s == "-":
                    chars.append(" ")
                    i += 1
                elif SHORT.match(s):
                    chars.append(raw[raw.index("-") + 2:])
                    i += 1
                else:
                    break
            out.append("".join(chars).strip())
            continue
        out.append(line)
        i += 1
    return "\n".join(out)

fixed = 0
for f in glob.glob("models/*/changelog/*.md"):
    t = open(f, encoding="utf-8").read()
    c = clean(t)
    if c != t:
        open(f, "w", encoding="utf-8").write(c)
        fixed += 1
print(f"清洗 {fixed} 个文件")

# 复查残留
import os
bad = 0
for f in glob.glob("models/*/changelog/*.md"):
    lines = open(f, encoding="utf-8").read().split("\n")
    short = sum(1 for l in lines if re.match(r"^- .{0,2}$", l.strip()))
    if short >= 3:
        bad += 1
        if bad <= 3: print("残留:", f, short)
print(f"残留竖排文件: {bad}")
