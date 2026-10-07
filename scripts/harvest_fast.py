#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并发 harvest：多线程会话池，从目录源拉直链并验证入库"""
import json, os, re, sys, time, urllib.request, urllib.parse, http.cookiejar, ssl, threading
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
ctx = ssl._create_unverified_context()
LOCK = threading.Lock()
STATS = {"ok": 0, "fail": 0, "nolink": 0, "skip": 0}
GIVEUP = set()  # 本轮已确认后端无记录的（跳过重试）


class Session:
    """独立 cookie 会话（每个线程一个，避免 cookie 竞争）"""
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj),
            urllib.request.HTTPSHandler(context=ctx))
        self.warm()

    def warm(self):
        for _ in range(3):
            try:
                raw = self.op.open(urllib.request.Request(
                    "https://roms.lian86.top/", headers={"User-Agent": UA}), timeout=20).read()
                text = raw.decode(errors="ignore")
                if "UAM_CHECKING" not in text[:3000]:
                    return True
                m = re.search(r"var nonce = (\d+)", text)
                fl = [c.value for c in self.cj if c.name == "fl_ua_p"]
                if m and fl:
                    nonce = int(m.group(1)); d = 12345
                    for i in range(len(fl[0])):
                        if re.match(r"[a-zA-Z0-9]", fl[0][i]): d += ord(fl[0][i]) * (nonce + i)
                    self.op.open(urllib.request.Request("https://roms.lian86.top/",
                        data=urllib.parse.urlencode({"sum": d, "nonce": nonce}).encode(),
                        headers={"User-Agent": UA, "Content-type": "application/x-www-form-urlencoded",
                                 "X-FL-UA-Step": "prev"}), timeout=20)
                    time.sleep(2)
            except Exception:
                time.sleep(3)
        return False

    def get_token(self, brand, model, version):
        req = urllib.request.Request("https://roms.lian86.top/proxy/init",
            data=json.dumps({"captchaVerifyParam": "auto", "brand": brand, "model": model,
                             "version": version}).encode(),
            headers={"User-Agent": UA, "Content-Type": "application/json"})
        r = self.op.open(req, timeout=25)
        return json.loads(r.read().decode()).get("token")

    def get_link(self, brand, model, version, token):
        q = f"brand={urllib.parse.quote(brand)}&model={urllib.parse.quote(model)}&version={urllib.parse.quote(version)}"
        req = urllib.request.Request(f"https://roms.lian86.top/proxy/roms/link?{q}",
            headers={"User-Agent": UA, "Authorization": f"Bearer {token}", "Accept": "application/json"})
        return json.loads(self.op.open(req, timeout=30).read().decode())

    def verify_pk(self, url):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-3"}),
                                       timeout=20, context=ctx)
            return r.read(2) == b"PK"
        except Exception:
            return False


def build_tasks():
    """任务清单：目标站目录原始 version ∩ 本地缺链接。
    动态构建：以当前 site.json 的无链接版本为准（含挖掘新增的目录条目）"""
    # 从数据仓库 site.json 拿当前无链接版本
    site_path = os.path.join(ROOT, "site", "site.json")
    d = json.load(open(site_path))
    missing = {}
    for b in d["brands"]:
        for m in b["models"]:
            no_url = [v["version"].replace("ColorOS ", "").replace(f"{m['code']}_", "", 1)
                      for v in m["versions"] if not v.get("url")]
            if no_url:
                missing[m["code"]] = no_url
    site_crawl = json.load(open(os.path.join(ROOT, "config", "site_crawl.json")))
    brand_of = {}
    for b, ms in site_crawl.items():
        for m in ms:
            brand_of[m["code"]] = b
    # 目标站目录（原始 version 形态）需要现拉——用缓存文件
    cache = os.path.join(ROOT, "config", "lian_versions_raw.json")
    if os.path.exists(cache):
        raw_cat = json.load(open(cache))
    else:
        raw_cat = {}
    tasks = []
    s = Session()
    for code, vers in sorted(missing.items()):
        brand = brand_of.get(code, "OnePlus")
        want = set(vers)
        if code in raw_cat:
            items = raw_cat[code]
        else:
            try:
                q = f"model={urllib.parse.quote(code)}&brand={urllib.parse.quote(brand)}"
                d = json.loads(s.op.open(urllib.request.Request(
                    f"https://roms.lian86.top/proxy/roms/versions?{q}",
                    headers={"User-Agent": UA}), timeout=20).read().decode())
                items = d.get("data") or []
                raw_cat[code] = items
                json.dump(raw_cat, open(cache, "w"), ensure_ascii=False)
                time.sleep(0.3)
            except Exception:
                continue
        for item in items:
            full_ver = item.get("version", "")
            local_ver = full_ver.replace("ColorOS ", "").replace(f"{code}_", "", 1)
            if local_ver in want:
                tasks.append((code, brand, full_ver,
                              f"{code}_{local_ver.replace(' ', '_')}.txt"))
    json.dump(raw_cat, open(cache, "w"), ensure_ascii=False)
    return tasks


def worker(sess, task_queue, root_links):
    while True:
        with LOCK:
            if not task_queue:
                return
            code, brand, full_ver, fname = task_queue.pop(0)
        out = os.path.join(root_links, code, fname)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            with LOCK: STATS["skip"] += 1
            continue
        if out in GIVEUP:
            with LOCK: STATS["nolink"] += 1
            continue
        try:
            token = sess.get_token(brand, code, full_ver)
            if not token:
                with LOCK: STATS["fail"] += 1
                continue
            r = sess.get_link(brand, code, full_ver, token)
            links = (r.get("data") or {}).get("links") or []
            if links and sess.verify_pk(links[0]):
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    f.write(links[0] + "\n")
                with LOCK:
                    STATS["ok"] += 1
                    done = STATS["ok"] + STATS["fail"] + STATS["nolink"] + STATS["skip"]
                    if done % 20 == 0:
                        print(f"  进度 {done}: ✓{STATS['ok']} ✗{STATS['fail']} 无{STATS['nolink']} 跳{STATS['skip']}", flush=True)
            else:
                with LOCK:
                    STATS["nolink"] += 1
                    GIVEUP.add(out)  # 目标站后端无记录，本轮跳过
        except Exception as e:
            with LOCK: STATS["fail"] += 1
            if "reset" in str(e).lower():
                sess.warm()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print("构建任务清单（拉目标站目录）...")
    tasks = build_tasks()
    if args.limit:
        tasks = tasks[:args.limit]
    print(f"待 harvest: {len(tasks)} | {args.workers} 线程并发")

    root_links = os.path.join(ROOT, "links")
    task_queue = list(tasks)
    sessions = [Session() for _ in range(args.workers)]
    threads = [threading.Thread(target=worker, args=(s, task_queue, root_links), daemon=True)
               for s in sessions]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    el = time.time() - t0
    print(f"\n完成：{el/60:.1f} 分钟 | ✓{STATS['ok']} ✗{STATS['fail']} 无链接{STATS['nolink']} 跳过{STATS['skip']}")


if __name__ == "__main__":
    main()
