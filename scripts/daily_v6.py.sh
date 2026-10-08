#!/bin/bash
cd /root/oplus-rom-dev/repos/oplus-version-history
python3 - <<'PY'
import sys, json, time
sys.path.insert(0, 'scripts')
import update

class Opts:
    v6 = True
    only_latest = True
    dry = False
    model = None
    shard = None
    no_downgrade = True
    no_history_write = False
    only_changelog = False

models = json.load(open('config/models.json'))['models']
cn = [m for m in models if m.get('region') == 'CN']
print(f"CN 机型 {len(cn)} 个，开始 v6 全量记录…", flush=True)
t0 = time.time()
ok = err = refreshed = new = 0
for i, m in enumerate(cn):
    try:
        r = update.update_model(m, Opts())
        new += r['new_links']
    except Exception as e:
        err += 1
    if (i+1) % 20 == 0:
        print(f"  {i+1}/{len(cn)} | 新链接 {new} | 错误 {err} | {time.time()-t0:.0f}s", flush=True)
print(f"完成: {len(cn)} 机型 | 新链接 {new} | 错误 {err} | {time.time()-t0:.0f}s")
PY
