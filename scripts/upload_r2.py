#!/usr/bin/env python3
"""拆分 site.json → 每机型一个文件 → 上传 R2（经 wrangler r2 object put）"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ 上一级
ENV = dict(os.environ,
           CLOUDFLARE_API_TOKEN="cfut_EDSYBWrC8CULpy9g6nCm2OdEsGn8mawXWj8giUaY81c2d9cc",
           CLOUDFLARE_ACCOUNT_ID="bf425e3b280e5facebdad91a7d665576")

def main():
    d = json.load(open(os.path.join(ROOT, "site", "site.json")))
    tmp = "/tmp/r2_upload"
    os.makedirs(tmp, exist_ok=True)
    files = []
    for b in d["brands"]:
        for m in b["models"]:
            key = f"{b['key']}__{m['code']}.json"
            path = os.path.join(tmp, key.replace("__", "/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"name": m["name"], "versions": m["versions"]}, f, ensure_ascii=False, separators=(",", ":"))
            files.append((key, path))
    print(f"拆分 {len(files)} 个机型文件，上传 R2...")
    ok = 0
    for key, path in files:
        r = subprocess.run(["npx", "wrangler", "r2", "object", "put", f"rombase-data/{key}",
                            f"--file={path}", "--remote"], capture_output=True, text=True, env=ENV, cwd=ROOT)
        if r.returncode == 0: ok += 1
        else: print(f"  失败 {key}: {r.stderr[:60]}")
    # 品牌目录（机型列表）
    brands = [{"key": b["key"], "models": [{"code": m["code"], "name": m["name"], "verCount": len(m["versions"])} for m in b["models"]]} for b in d["brands"]]
    bp = os.path.join(tmp, "_brands.json")
    json.dump(brands, open(bp, "w"), ensure_ascii=False, separators=(",", ":"))
    subprocess.run(["npx", "wrangler", "r2", "object", "put", "rombase-data/_brands.json",
                    f"--file={bp}", "--remote"], capture_output=True, text=True, env=ENV, cwd=ROOT)
    print(f"上传完成: {ok}/{len(files)} 机型 + 品牌索引")

if __name__ == "__main__":
    main()
