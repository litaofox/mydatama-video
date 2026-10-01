# samples/ —— 演示数据包说明（考题与答案）

本目录数据由 `samples/generator/generate_all.py` 生成，**固定随机种子 20260930**，可重复生成（多次运行输出字节级一致，已验证 MD5 一致）。数据语义对齐 **JT/T 808-2019** 车联网定位报文（车牌/经纬度/速度/方向/报警标志位/ADAS·DSM 事件码）。

## 一、文件清单

| 文件 | 规模 | 说明 |
|---|---|---|
| vehicle_gps_20260901.csv | 50000 数据行 / 约 5.3MB / UTF-8 | 100 车 × 500 行，1Hz 连续轨迹，北京为主+少量沪穗深蓉杭 |
| vehicle_gps_20260902.csv | 50000 数据行 / 约 5.1MB / **GBK** | 同上特征；**列名同义词+乱序**（车牌号/定位时间/经度/纬度/速度/方向/司机手机号/证件号；vehicle_id、alarm_flag、mileage 保持） |
| fleet_info_sheet1/2/3.csv | 共 2000 数据行 + 每文件 5 空行 | 本机无 openpyxl 时的回退产物；**真实容器环境由脚本同逻辑产出 fleet_info.xlsx**（3 sheet，行内容与空行位置一致）。CSV 为 UTF-8 带 BOM |
| driver_events.json | 10000 事件 | 一半国标码（1 急加速 2 急减速 3 急转弯 4 疲劳驾驶 5 超速 6 前向碰撞预警 FCW 7 车道偏离 LDW），一半厂商私有码（V_FCW/V_LDW/V_HMW/V_PCW），`event_source` 为 `national`/`vendor` |
| driver_notes.txt | 500 段（每段 3~6 行） | 中文司机日志；每段随机嵌入 1~2 个明文手机号/邮箱/身份证 |
| vehicle_photos.zip | 20 张 JPEG / 3.8KB | photo_01.jpg~photo_20.jpg，每张含 EXIF APP1（Make=DEMO-CAM-xx）。**真实环境用 Pillow 生成带 EXIF/GPS 的图像，演示包为轻量占位图，EXIF 剥离逻辑由处理服务实际执行** |
| dashcam_clips.zip | 5 段视频占位 / 约 1KB | dashcam_01.mp4 / 02.mov / 03.mp4 / 04.avi / 05.mkv（二进制头部占位）。**真实环境由 ffmpeg 生成 3~5s 320x240 低码率视频** |
| unmasked_sample.csv | 200 数据行 | **反面演示专用**：plate_no/driver_name/phone/id_card/bank_card/secret_note 全部明文（合法格式假数据） |

## 二、考题与答案（注入点 → 预期治理结果）

行号均为**数据行号（1-based，不含表头）**。

| 文件 | 注入点（精确行号/计数） | 预期治理结果 |
|---|---|---|
| vehicle_gps_20260901.csv | **缺失**：行 2001–3000，共 1000 行（≈2%），driver_phone/driver_idcard 为空 | 缺失率≈2% → 清洗后 0 |
| vehicle_gps_20260901.csv | **完全重复**：行 5001–5500，共 500 行（≈1%），逐行复制行 4501–5000 | 重复率 1% → 去重后 0 |
| vehicle_gps_20260901.csv | **漂移点**：行 10000, 10200, 10400, …, 19800（步长 200），共 50 条，经纬度跳到 [120,121)/[30,31)，与相邻行相距>1 度 | 漂移 50 条 → 入隔离 |
| vehicle_gps_20260901.csv | **时间乱序**：行 20000, 21000, 22000, …, 39000（步长 1000），共 20 条，gps_time 比前一行早 65 秒 | 乱序 20 条 → 归一 |
| vehicle_gps_20260902.csv | 与 0901 **相同行号规则**的缺失/重复/漂移/乱序（1000/500/50/20） | **GBK 编码 + 中文乱序列名 → 标准化映射**（车牌号→plate_no、定位时间→gps_time、经度→longitude、纬度→latitude、速度→speed、方向→direction、司机手机号→driver_phone、证件号→driver_idcard），编码转 UTF-8 后同规则治理 |
| fleet_info_sheet1/2/3.csv | 每 sheet **全空行**位于数据行 **134 / 268 / 402 / 536 / 670**（各 5 处）；车牌格式混杂（带·/小写/带空格）；bank_card 16~19 位、contact_phone 11 位 | 空行剔除；车牌标准化（去·/去空格/统一大写）；银行卡 16~19 位数字 → 脱敏策略（保留前 4 后 4） |
| driver_events.json | 事件序号偶数位（共 5000 条）为厂商私有码 V_FCW/V_LDW/V_HMW/V_PCW；奇数位（共 5000 条）为国标码 1–7 | **JSON 厂商码 → 国标映射**：V_FCW→6(FCW)、V_LDW→7(LDW)、V_HMW/PCW 归入隔离/扩展映射，映射后国标计数 10000 |
| vehicle_photos.zip | 每张 JPEG 含 EXIF APP1 段 | **EXIF → 剥离**（处理服务入库前移除 APP1/APP2 元数据段） |
| dashcam_clips.zip | 视频占位（无元数据） | 走媒体类资产登记/转码流程 |
| driver_notes.txt | 每段（第 1~500 段，段间空行分隔）嵌入 1~2 个明文手机号/邮箱/18 位身份证 | **文本明文 → 掩码**（正则识别：手机号 138\*\*\*\*1234、邮箱 a\*\*@163.com、身份证前 3 后 4） |
| unmasked_sample.csv | 200 行全字段明文（姓名/手机/证件/银行卡/敏感备注） | **上传此文件时选择密级 3 且不做脱敏修复直接建产品 → 合规引擎 R1+R2 拦阻**（R1 敏感字段未脱敏、R2 密级与敏感数据冲突），产品状态 BLOCKED |

## 三、生成 / 再生成

```bash
# 依赖：仅 Python 3 标准库（无第三方依赖；有 openpyxl 时 fleet_info 产出真 xlsx，否则 3 个 CSV）
python samples/generator/generate_all.py
```

运行后打印摘要表（文件名 / 行数 / 大小 / 异常注入位置行号范围）。

## 四、演示前重置说明

1. **数据重置**：删除 samples/ 下全部生成文件（保留 generator/ 子目录），再执行
   `python samples/generator/generate_all.py`；固定种子保证与上次完全一致（含异常注入行号）。
2. **平台侧重置**（如需从零演示）：`docker compose down -v && docker compose up -d`，
   等待服务就绪后（约 1~2 分钟）再执行冒烟测试。
3. **冒烟测试**：`bash scripts/smoke-test.sh`（Windows 用 Git Bash 执行；可用环境变量 `BASE` 指定网关地址，默认 http://localhost:8090）。
