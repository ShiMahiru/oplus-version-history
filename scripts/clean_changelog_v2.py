

import glob, re

def clean(text):
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    SHORT = re.compile(r"^- (.{0,2})$")

    NUM = re.compile(r"^(\d+)\.\s*$")

    while i < n:
        line = lines[i]
        m_short = SHORT.match(line.strip())
        m_num = NUM.match(line.strip())
        if m_num:
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
                    if i < n and (lines[i].strip() == "-" or SHORT.match(lines[i].strip())):
                        continue
                    break
                else:
                    break
            content = "".join(chars).strip()
            out.append(f"{num}. {content}" if content else f"{num}.")
            continue
        if m_short:
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

import os
bad = 0
for f in glob.glob("models/*/changelog/*.md"):
    lines = open(f, encoding="utf-8").read().split("\n")
    short = sum(1 for l in lines if re.match(r"^- .{0,2}$", l.strip()))
    if short >= 3:
        bad += 1
        if bad <= 3: print("残留:", f, short)
print(f"残留竖排文件: {bad}")