#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私有可浏览的版本史（Markdown）
==============================
读 docs/data.json（build_index.py 的产物），生成：

  - HISTORY.md           根目录全机型索引表，按品牌分组，可点进详情
  - docs/md/{型号}.md     单机型完整版本史（版本 / 指纹 / 日期 / 官方链接 / 更新日志 / 降级包）

为什么不用 GitHub Pages：私有仓库的 Pages 需要付费计划（免费账号只能公开仓库开 Pages）。
Markdown 由 GitHub 网页直接渲染 —— 私有、免费、手机能看、官方链接可点，
不用额外托管、不用 Cloudflare/Vercel、不用把仓库转公开。

运行: python3 scripts/build_md.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
MD_DIR = os.path.join(DOCS, "md")


def cell(s):
    """表格单元格转义：竖线和换行会破坏 Markdown 表格"""
    return str(s or "").replace("|", "\\|").replace("\n", " ").strip()


def short_date(ts):
    """指纹尾部时间戳 202608071758 -> 2026-08-07"""
    if len(ts) >= 8 and ts[:8].isdigit():
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
    return ""


def size_text(n):
    try:
        n = int(str(n).strip())
    except Exception:
        return ""
    if n <= 0:
        return ""
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.1f} MB"


def md_link(label, url):
    """URL 用尖括号包住，避免参数里的特殊字符破坏链接语法"""
    return f"[{label}](<{url}>)" if url else ""


def rel_from_md(path):
    """docs/md/x.md 回到仓库根"""
    return "../../" + path.lstrip("./")


def build_model_page(m):
    code = m["code"]
    name = m.get("name") or code
    brand = m.get("brand") or ""
    region = m.get("region") or ""
    vers = m.get("versions") or []
    dg = m.get("downgrade") or []
    with_url = [v for v in vers if v.get("url")]
    with_cl = [v for v in vers if v.get("cl")]

    head = [f"# {code} · {name}", ""]
    head.append("[← 返回机型索引](../../HISTORY.md)"
                + (f" · [最新版元数据](<{rel_from_md(f'models/{code}/latest-update.txt')}>)")
                + (f" · [降级包原始档](<{rel_from_md(f'downgrade/{code}.txt')}>)"
                   if dg else ""))
    head.append("")
    meta = []
    if brand or region:
        meta.append(f"**{' / '.join(x for x in (brand, region) if x)}**")
    if m.get("latest"):
        meta.append(f"最新版本 `{m['latest']}`")
    if m.get("ota"):
        meta.append(f"OTA `{m['ota']}`")
    if m.get("android"):
        a = str(m["android"]).strip()
        meta.append(a if a.lower().startswith("android") else f"Android {a}")
    if m.get("patch"):
        meta.append(f"安全补丁 {m['patch']}")
    head.append(" · ".join(meta) if meta else "")
    head.append("")
    head.append(f"版本记录 **{len(vers)}** 条 · 有官方链接 **{len(with_url)}** 条 · "
                f"有更新日志 **{len(with_cl)}** 份")
    head.append("")
    head.append("## 版本史")
    head.append("")
    head.append("| 版本 | 指纹 | 日期 | 官方链接 | 更新日志 | 备注 |")
    head.append("|---|---|---|---|---|---|")
    for v in vers:
        ver = cell(v.get("ver")) or "_(仅指纹)_"
        fp = f"`{cell(v.get('fp'))}`" if v.get("fp") else ""
        date = short_date(v.get("date") or "")
        url = md_link("下载", v.get("url"))
        cl = md_link("原文", rel_from_md(v["cl"])) if v.get("cl") else ""
        note = cell(v.get("note"))
        head.append(f"| {ver} | {fp} | {date} | {url} | {cl} | {note} |")
    head.append("")

    if dg:
        head.append("## 官方降级包")
        head.append("")
        head.append("| 名称 | Android | 大小 | 链接 | 说明 |")
        head.append("|---|---|---|---|---|")
        for d in dg:
            head.append("| {} | {} | {} | {} | {} |".format(
                cell(d.get("title")), cell(d.get("Android")), size_text(d.get("大小")),
                md_link("下载", d.get("链接")), cell(d.get("更新说明"))))
        head.append("")

    head.append("---")
    head.append("")
    head.append("链接是官方 `downloadCheck` 网关地址（长期有效）：浏览器或多线程下载器访问会 "
                "302 跳到官方 CDN 直链。")
    head.append("")
    return "\n".join(head)


def main():
    data_path = os.path.join(DOCS, "data.json")
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    models = data.get("models") or []

    os.makedirs(MD_DIR, exist_ok=True)

    tot_vers = sum(len(m.get("versions") or []) for m in models)
    tot_links = sum(1 for m in models for v in (m.get("versions") or []) if v.get("url"))
    tot_clog = sum(1 for m in models for v in (m.get("versions") or []) if v.get("cl"))
    tot_dg = sum(len(m.get("downgrade") or []) for m in models)

    # 单机型页
    for m in models:
        with open(os.path.join(MD_DIR, f"{m['code']}.md"), "w", encoding="utf-8") as f:
            f.write(build_model_page(m))

    # 索引页
    out = ["# 欧加官方 ROM 历史版本档案 · 索引", ""]
    out.append(f"> **{len(models)}** 机型 · **{tot_links}** 条官方链接 · "
               f"**{tot_clog}** 份官方更新日志 · **{tot_dg}** 个官方降级包")
    out.append(">")
    out.append("> 私有档案，仅自己可见。数据全部来自官方服务器，链接入库前逐个 302 实测。")
    out.append("")
    out.append("点型号进详情页；表格里的「下载」就是官方 gate 链接，"
               "浏览器/下载器访问会 302 到官方 CDN。")
    out.append("")

    groups = {}
    for m in models:
        groups.setdefault(m.get("brand") or "", []).append(m)

    # config/models.json 里的 brand 是小写（oneplus/oppo/realme），展示时再转回正式写法
    label = {"oppo": "OPPO", "oneplus": "OnePlus", "realme": "realme"}
    order = ["oppo", "oneplus", "realme"]
    brands = [b for b in order if b in groups] + sorted(b for b in groups if b not in order)

    for brand in brands:
        rows = sorted(groups[brand], key=lambda x: x["code"])
        out.append(f"## {label.get(brand, brand or '其他')}（{len(rows)}）")
        out.append("")
        out.append("| 型号 | 名称 | 区域 | 版本数 | 链接数 | 最新版本 | 详情 |")
        out.append("|---|---|---|---:|---:|---|---|")
        for m in rows:
            vers = m.get("versions") or []
            n_url = sum(1 for v in vers if v.get("url"))
            out.append("| {} | {} | {} | {} | {} | {} | {} |".format(
                f"`{m['code']}`", cell(m.get("name")), cell(m.get("region")),
                len(vers), n_url, cell(m.get("latest")) or "—",
                md_link("查看", f"docs/md/{m['code']}.md")))
        out.append("")

    out.append("---")
    out.append("")
    out.append("原始数据：`links/`（官方链接）· `models/`（版本史与更新日志）· "
               "`downgrade/`（降级包）。用法见 [README](README.md)。")
    out.append("")

    with open(os.path.join(ROOT, "HISTORY.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print(f"✓ HISTORY.md  ({len(models)} 机型)")
    print(f"✓ docs/md/    ({len(models)} 个机型页)")
    print(f"  链接 {tot_links}  版本 {tot_vers}  更新日志 {tot_clog}  降级包 {tot_dg}")
    return {"models": len(models), "links": tot_links, "versions": tot_vers}


if __name__ == "__main__":
    main()
