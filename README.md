# oplus-version-history

欧加（OPPO / OnePlus / Realme）官方 ROM 历史版本档案 · 自动维护

> 数据**全部来自官方服务器**：OTA 网关（v3 加密接口）、官方降级接口、官方更新日志接口。
> 链接入库前逐个实测（302 → 官方 CDN 才算有效），每周自动增量更新并全量校验。
> **无任何第三方托管、无伪造条目、无编造字段**——拿不到的字段就不写，下架的链接如实归档。

---

## 快速使用

拿到官方下载链接（两栖方式）：

```
# 1) 直接进机型目录复制
links/PLQ110/PLQ110_16.0.10.500(CN01).txt      ← 内容即官方 downloadCheck 链接（长期有效）
                                                ← 浏览器/下载器访问即 302 → 官方 Gauss 直链

# 2) 或看最新版档案
models/PLQ110/latest-update.txt                ← 最新版本 8 元组（含链接/大小/MD5/补丁）

# 3) 看某版本的官方更新日志
models/PLQ110/changelog/PLQ110_11.A.57_0570.md ← 官方 descriptionInfo 原文全文
```

教程：打开 `links/你的机型/` → 复制版本文件内容 → 粘贴到浏览器地址栏 → 开始下载（多线程下载器也支持，gate 链接对 `Range` 友好）。

## 仓库结构

```
├── links/{型号}/{版本}.txt        # 官方下载链接（核心资产；文件名=版本号）
├── models/{型号}/
│   ├── ota-version.txt            # 版本史时间线：OTA 指纹 ↔ 用户可见版本（只追加）
│   ├── latest-update.txt          # 最新版元数据（Android/安全补丁/发布时间/链接）
│   └── changelog/{指纹前缀}.md    # 官方更新日志全文
├── downgrade/{型号}.txt           # 官方降级包直链（downgrade.coloros.com）
├── links/_dead/ + DEAD.md         # 校验失败的死链归档与报告
├── config/                        # 机型清单 / 官方公钥 / 项目号表
├── docs/index.html                # 静态检索页（机型/版本/链接，可 GitHub Pages 直出）
└── scripts/                       # update.py（官方增量）/ verify.py / seed.py
                                   # normalize.py（归一化去重）/ fix_history.py（基线修正）
                                   # build_index.py（生成检索页）
```

### 数据格式

`links/PLQ110/PLQ110_16.0.10.500(CN01).txt`：

```
https://component-ota-cn.allawntech.com/downloadCheck?c=...&p=...&g=...&id=...
```

`models/PLQ110/ota-version.txt`（新版本追加在底部前，排序按指纹时间戳）：

```
PLQ110_11.A.24_0240_202510150218  # ColorOS: PLQ110_16.0.2.402(CN01)
PLQ110_11.A.57_0570_202608071758  # ColorOS: PLQ110_16.0.10.500(CN01)
```

`downgrade/PLQ110.txt`：

```
### ColorOS16.1.0
- Android: Android16
- 大小: 10570375254
- MD5: c9b3ab6db40b402bf468107a5ec98d4a
- 链接: https://downgradefs.coloros.com/downgrade/26/08/17/....zip
- 更新说明: KTM降级包测试
```

## 数据来源声明（纯官方）

| 接口 | 用途 | 备注 |
|---|---|---|
| `component-ota-{cn,eu,in,sg}.allawnos/allawntech.com/update/v3` | 在推分支版本/指纹/gate 链接/大小/MD5/补丁 | AES-256-CTR + RSA-OAEP-SHA1，公开加密协议 |
| `component-ota-*.…/descriptionInfo` | 任意历史版本的官方更新日志 + 版本名反查 | 明文 POST |
| `downgrade.coloros.com/downgrade/query-v3` | 官方降级包直链 | AES-256-GCM 设备标识 |

指纹与版本名的对应关系（`ota-version.txt`）来自官方 v3 响应（`otaVersion` ↔ `versionName`），不是猜测。

## 维护（自动 + 手动）

- **自动**：GitHub Actions 每周一 04:00 UTC 全量执行（见 `.github/workflows/update.yml`）
- **手动**：
  ```bash
  python3 scripts/update.py --model PLQ110    # 单机型增量（含 changelog/降级包）
  python3 scripts/update.py                   # 全量增量（所有机型）
  python3 scripts/verify.py                   # 全量链接存活校验（死链移 links/_dead/）
  python3 scripts/seed.py                     # 重新导入种子基线（幂等）
  ```

## 设计原则

1. **只增不改**：版本史只用追加；链接失效进 `_dead/` 归档，不删版本记录（"存在过"是事实）
2. **真实可验**：每个链接入库前 302 实测；`verify.py` 每轮全量复查
3. **宁缺毋滥**：官方接口没有的字段就不写，绝不编造
4. **限流友好**：固定 ≥300ms 请求间隔，官方 2004 限流自动退避

## 版本记录（2026-09 起）

- v0.1 首版：231 机型 / 649 条官方链接 / 614 行版本史基线 + 全链路自动更新
- v0.2 全量首次扫描完成：356 机型 / 809 条官方链接（全量校验 809/809 有效，零死链）
  / 507 份官方 changelog / 33 台降级包
- v0.3 版本史清洗：剔除 79 行重复 + 151 行查询基线指纹，34 条基线重查修正为官方 OTA 指纹，
  2 条无法取证如实标注「查询基线 · 非官方 OTA 指纹」；新增 `build_index.py` 静态检索页
- v0.4 版本名反查补全：30 条只有指纹的早期记录经官方 `descriptionInfo` 反查，21 条补上官方版本名
  / 7 条附带官方更新日志；官方返回的 3 条内部占位符（`v_0`/`v_2`）已剔除，不冒充版本名