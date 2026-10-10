

import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

def read_lines(p):
    try:
        with open(p, encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]
    except Exception:
        return []

def parse_history(code):

    p = os.path.join(ROOT, "models", code, "ota-version.txt")
    out = []
    for ln in read_lines(p):
        if "#" in ln:
            left, right = ln.split("#", 1)
            fp = left.strip()
            ver = re.sub(r"^ColorOS\s*:?\s*", "", right.strip()).strip()
            note = ""
            m = re.search(r"[（(]([^（()）]*基线[^（()）]*)[）)]", ver)
            if m:
                note = m.group(1)
                ver = re.sub(r"\s*[（(][^（()）]*基线[^（()）]*[）)]\s*", "", ver).strip()
        else:
            fp, ver, note = ln.strip(), "", ""
        if fp:
            out.append({"fp": fp, "ver": ver, "note": note})
    return out

def parse_latest(code):
    p = os.path.join(ROOT, "models", code, "latest-update.txt")
    d = {}
    for ln in read_lines(p):
        if ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d

def parse_downgrade(code):
    p = os.path.join(ROOT, "downgrade", f"{code}.txt")
    if not os.path.isfile(p):
        return []
    items, cur = [], None
    for ln in read_lines(p):
        if ln.startswith("###"):
            cur = {"title": ln[3:].strip()}
            items.append(cur)
        elif ln.startswith("- ") and cur is not None:
            if ":" in ln:
                k, v = ln[2:].split(":", 1)
                cur[k.strip()] = v.strip()
    return items

def main():
    models_cfg = json.load(open(os.path.join(ROOT, "config", "models.json"), encoding="utf-8"))["models"]
    by_code = {m["code"]: m for m in models_cfg}

    links_dir = os.path.join(ROOT, "links")
    models_dir = os.path.join(ROOT, "models")
    codes = set()
    for base in (links_dir, models_dir):
        if os.path.isdir(base):
            for d in os.listdir(base):
                if d != "_dead" and os.path.isdir(os.path.join(base, d)):
                    codes.add(d)

    out_models = []
    tot_links = tot_clog = tot_dg = tot_vers = 0

    for code in sorted(codes):
        ldir = os.path.join(links_dir, code)
        links = {}
        if os.path.isdir(ldir):
            for fn in sorted(os.listdir(ldir)):
                if not fn.endswith(".txt"):
                    continue
                ver = fn[:-4]
                url = ""
                for ln in read_lines(os.path.join(ldir, fn)):
                    if ln.startswith("http"):
                        url = ln.strip()
                        break
                if url:
                    links[ver] = url

        cdir = os.path.join(models_dir, code, "changelog")
        clogs = {}
        if os.path.isdir(cdir):
            for fn in sorted(os.listdir(cdir)):
                if fn.endswith(".md"):
                    clogs[fn[:-3]] = f"models/{code}/changelog/{fn}"

        hist = parse_history(code)
        latest = parse_latest(code)
        dg = parse_downgrade(code)

        vers = []
        seen_ver = set()
        for h in hist:
            ver = h["ver"]
            fp = h["fp"]
            url = links.get(ver, "")
            cl = ""
            for k, v in clogs.items():
                if fp.startswith(k):
                    cl = v
                    break
            vers.append({"fp": fp, "ver": ver, "note": h["note"], "url": url, "cl": cl,
                         "date": (fp.rsplit("_", 1)[-1] if fp.count("_") >= 2 else "")})
            if ver:
                seen_ver.add(ver)
        for ver, url in sorted(links.items()):
            if ver not in seen_ver:
                vers.append({"fp": "", "ver": ver, "note": "", "url": url, "cl": "", "date": ""})
                seen_ver.add(ver)

        cfg = by_code.get(code, {})
        out_models.append({
            "code": code,
            "name": cfg.get("name", ""),
            "brand": cfg.get("brand", ""),
            "region": cfg.get("region", ""),
            "rui": cfg.get("rui", 0),
            "latest": latest.get("版本名称", ""),
            "ota": latest.get("最新 OTA 版本", ""),
            "android": latest.get("Android 版本", ""),
            "patch": latest.get("安全补丁", ""),
            "versions": vers,
            "downgrade": dg,
        })

        tot_links += len(links)
        tot_clog += len(clogs)
        tot_dg += len(dg)
        tot_vers += len(vers)

    data = {"models": out_models}

    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    stat = {"models": len(out_models), "links": tot_links, "changelog": tot_clog,
            "downgrade": tot_dg, "versions": tot_vers}
    page = PAGE.replace("/*__STAT__*/", json.dumps(stat, ensure_ascii=False)) \
               .replace("/*__DATA__*/", payload)
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)

    print(f"✓ docs/index.html  ({len(page) / 1024:.0f} KB)")
    print(f"  机型 {stat['models']}  链接 {stat['links']}  版本 {stat['versions']}  "
          f"changelog {stat['changelog']}  降级包 {stat['downgrade']}")
    return stat

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>oplus-version-history · 欧加官方 ROM 历史版本档案</title>
<style>
:root{
  --bg:
  --fg:
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
header{padding:28px 20px 18px;border-bottom:1px solid var(--line)}
h1{margin:0 0 6px;font-size:20px;letter-spacing:.2px}
.sub{color:var(--mut);font-size:13px}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:8px 14px;min-width:96px}
.stat b{display:block;font-size:18px;color:var(--fg)}
.stat span{color:var(--mut);font-size:12px}
.wrap{padding:16px 20px 60px;max-width:1180px;margin:0 auto}
.ctrl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
input[type=search]{flex:1;min-width:220px;background:var(--card);border:1px solid var(--line);
  color:var(--fg);border-radius:10px;padding:10px 14px;font-size:14px;outline:none}
input[type=search]:focus{border-color:var(--acc)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:var(--card);border:1px solid var(--line);color:var(--mut);
  border-radius:20px;padding:5px 13px;cursor:pointer;font-size:12px;user-select:none}
.chip.on{background:var(--acc);border-color:var(--acc);color:
.m{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:8px;overflow:hidden}
.mh{display:flex;align-items:center;gap:12px;padding:13px 16px;cursor:pointer}
.mh:hover{background:var(--card2)}
.mname{font-weight:600}
.mcode{color:var(--mut);font-family:ui-monospace,Menlo,monospace;font-size:12px}
.tag{font-size:11px;border-radius:6px;padding:2px 7px;border:1px solid var(--line);color:var(--mut)}
.tag.b{color:
.tag.r{color:
.tag.g{color:
.right{margin-left:auto;color:var(--mut);font-size:12px;white-space:nowrap}
.body{display:none;border-top:1px solid var(--line);padding:6px 0 10px}
.m.open .body{display:block}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 16px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:500;font-size:12px}
td.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--mut)}
.act{white-space:nowrap}
button{background:var(--card2);border:1px solid var(--line);color:var(--fg);
  border-radius:7px;padding:4px 10px;font-size:12px;cursor:pointer}
button:hover{border-color:var(--acc);color:var(--acc)}
.none{color:var(--mut);font-size:12px;padding:10px 16px}
.toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(20px);
  background:
  padding:9px 18px;font-size:13px;opacity:0;transition:.2s;pointer-events:none}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
.dg{padding:2px 16px 12px}
.dgitem{background:var(--card2);border:1px solid var(--line);border-radius:9px;
  padding:9px 13px;margin-top:7px;font-size:12px}
.dgitem b{color:var(--warn)}
footer{color:var(--mut);font-size:12px;padding:24px 20px;border-top:1px solid var(--line);text-align:center}
</style>
</head>
<body>
<header>
  <h1>oplus-version-history</h1>
  <div class="sub">欧加（OPPO / OnePlus / Realme）官方 ROM 历史版本档案 · 数据全部来自官方服务器 · 每周自动更新与校验</div>
  <div class="stats" id="stats"></div>
</header>
<div class="wrap">
  <div class="ctrl">
    <input type="search" id="q" placeholder="搜索机型名或型号（如 一加 Ace6 / PLQ110）…" autocomplete="off">
    <div class="chips" id="brands"></div>
    <div class="chips" id="regions"></div>
  </div>
  <div id="list"></div>
</div>
<footer>
  数据来源：官方 OTA 网关（v3 加密接口）· 官方降级接口 · 官方更新日志接口<br>
  链接入库前逐个实测（302 → 官方 CDN）· 本页由 <code>scripts/build_index.py</code> 自动生成
</footer>
<div class="toast" id="toast"></div>
<script>
const STAT = /*__STAT__*/;
const DATA = /*__DATA__*/;
const M = DATA.models;
const $ = s => document.querySelector(s);
const esc = s => (s||"").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

$("#stats").innerHTML = [
  ["机型", STAT.models], ["版本条目", STAT.versions], ["官方链接", STAT.links],
  ["官方日志", STAT.changelog], ["降级包", STAT.downgrade]
].map(([k,v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join("");

const BRAND = {"oneplus":"OnePlus","oppo":"OPPO","realme":"realme"};
let fBrand = "", fRegion = "";

function chips(el, vals, setter){
  el.innerHTML = ["<div class='chip on' data-v=''>全部</div>"]
    .concat(vals.map(v => `<div class="chip" data-v="${v}">${v}</div>`)).join("");
  el.querySelectorAll(".chip").forEach(c => c.onclick = () => {
    el.querySelectorAll(".chip").forEach(x => x.classList.remove("on"));
    c.classList.add("on"); setter(c.dataset.v);
  });
}
chips($("#brands"), [...new Set(M.map(m => m.brand).filter(Boolean))].map(b => BRAND[b]||b), v => {
  fBrand = Object.keys(BRAND).find(k => BRAND[k] === v) || ""; render();
});
chips($("#regions"), [...new Set(M.map(m => m.region).filter(Boolean))].sort(), v => { fRegion = v; render(); });
$("#q").oninput = render;

function toast(t){ const el=$("#toast"); el.textContent=t; el.classList.add("on");
  clearTimeout(el._t); el._t=setTimeout(()=>el.classList.remove("on"),1600); }

function copy(text, label){
  navigator.clipboard.writeText(text).then(()=>toast(label+" 已复制"), ()=>toast("复制失败，请手动选择"));
}

function rowLinks(m){
  return `<table><thead><tr>
    <th style="width:30%">版本</th><th style="width:26%">OTA 指纹</th>
    <th style="width:18%">链接</th><th>官方更新日志</th></tr></thead><tbody>`
    + m.versions.map(v => `<tr>
        <td>${esc(v.ver) || '<span class="mono">（无版本名）</span>'}
          ${v.note ? `<span class="tag r">${esc(v.note)}</span>` : ""}</td>
        <td class="mono">${esc(v.fp) || "—"}</td>
        <td class="act">${v.url
            ? `<button onclick="copy('${esc(v.url)}','链接')">复制链接</button>`
            : `<span class="tag">未收录</span>`}</td>
        <td>${v.cl
            ? `<a href="${esc(v.cl)}" target="_blank" rel="noopener">查看日志</a>`
            : `<span class="tag">—</span>`}</td>
      </tr>`).join("")
    + `</tbody></table>`;
}

function dgBlock(m){
  if(!m.downgrade.length) return "";
  return `<div class="dg">` + m.downgrade.map(d => `<div class="dgitem">
      <b>${esc(d.title)}</b>
      ${d.Android ? ` · ${esc(d.Android)}` : ""}
      ${d["大小"] ? ` · ${(d["大小"]/1073741824).toFixed(2)} GB` : ""}
      ${d["MD5"] ? ` · MD5 ${esc(d["MD5"])}` : ""}
      ${d["更新说明"] ? `<div style="color:var(--mut);margin-top:3px">${esc(d["更新说明"])}</div>` : ""}
      ${d["链接"] ? `<div style="margin-top:5px"><button onclick="copy('${esc(d["链接"])}','降级包链接')">复制降级包链接</button></div>` : ""}
    </div>`).join("") + `</div>`;
}

function render(){
  const q = $("#q").value.trim().toLowerCase();
  const list = M.filter(m => {
    if (fBrand && m.brand !== fBrand) return false;
    if (fRegion && m.region !== fRegion) return false;
    if (!q) return true;
    return (m.code + " " + m.name + " " + (m.latest||"")).toLowerCase().includes(q);
  });
  $("#list").innerHTML = list.length ? list.map(m => {
    const nLink = m.versions.filter(v => v.url).length;
    return `<div class="m" data-code="${esc(m.code)}">
      <div class="mh" onclick="this.parentNode.classList.toggle('open')">
        <div>
          <div class="mname">${esc(m.name) || esc(m.code)}</div>
          <div class="mcode">${esc(m.code)}${m.latest ? " · " + esc(m.latest) : ""}</div>
        </div>
        <span class="tag b">${BRAND[m.brand]||esc(m.brand)}</span>
        ${m.region ? `<span class="tag">${esc(m.region)}</span>` : ""}
        <span class="right">${m.versions.length} 版本 · ${nLink} 链接${m.downgrade.length ? " · 降级包 " + m.downgrade.length : ""}</span>
      </div>
      <div class="body">
        ${m.versions.length ? rowLinks(m) : '<div class="none">暂无版本数据</div>'}
        ${dgBlock(m)}
      </div>
    </div>`;
  }).join("") : '<div class="none">没有匹配的机型</div>';
}
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()