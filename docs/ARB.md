# ARB（防回滚）数据说明

ARB（Anti-Rollback，防回滚计数器）数据有两个互补来源：

## 1. `config/arb_database.json`（OnePlus 品牌，历史版本）

- **来源**：https://github.com/Bartixxx32/OnePlus-antirollchecker
- **内容**：96 机型 / 554 版本的 ARB 历史（arb / major / minor / md5）
- **特点**：覆盖 OnePlus 品牌（含国行 CPH/PJZ/PLK/PLQ 等），记录**每个历史版本**的 ARB，能看到防回滚计数被抬高的时间点
- **维护**：社区长期维护（GitHub Action 每日更新），需定期同步

## 2. `models/{code}/arb.json`（OPPO/Realme + OnePlus 补充，最新版）

- **来源**：本地 `scripts/arb_extract.py` 实时提取（复用 ota_extract.py 的 payload 定位 + Range 下载 + xz/bz2 解压 + ELF64 ARB 解析）
- **内容**：每机型**最新版**的 ARB（arb / major / minor / status / md5 / fp）
- **特点**：覆盖 OPPO/Realme（antirollchecker 不覆盖的品牌），且含 MTK 机型判断（无 xbl_config 分区 = 非高通）

## ARB 提取原理（高通芯片）

```
OTA zip → payload.bin（CrAU 头 + protobuf manifest）
→ 定位 xbl_config 分区（Range 请求只取这一块，几百 KB）
→ 解压（REPLACE_XZ / REPLACE_BZ）
→ xbl_config.img 是 ELF64，ARB 藏在 HASH 段（PT_NULL）的 OEM metadata
→ 读 major / minor / arb 三个 uint32
→ arb==0 表示 Safe（未抬高防回滚），否则 Protected
```

## 非高通机型（MTK）

MediaTek 芯片机型没有 xbl_config 分区（那是高通专有），ARB 机制在 preloader/lk 里。
这类机型的 arb 字段为 null，属正常情况，不是数据缺失。

## 合并进网站

```bash
cd /root/oplus-rom-dev/romcloud-web
python3 scripts/merge_arb_full.py   # 合并两个来源进 site.json
```
