#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业数据中台 MVP —— 演示数据生成器
固定随机种子 20260930，可重复生成（多次运行输出字节级一致）。
数据语义对齐 JT/T 808-2019 车联网定位报文（车牌/经纬度/速度/方向/报警标志/ADAS/DSM 事件码）。

用法:  python samples/generator/generate_all.py     （输出全部落到 samples/ 目录）
说明:  本机若无 openpyxl，则 fleet_info 回退为 3 个 CSV（fleet_info_sheet1/2/3.csv）；
       有 openpyxl 时产出真实 fleet_info.xlsx，二者行内容与空行位置一致。
"""
import csv
import json
import os
import random
import struct
import zipfile
from datetime import datetime, timedelta, date

SEED = 20260930
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, ".."))  # samples/

T0 = datetime(2026, 9, 1, 0, 0, 0)

# ---------------- JT/T 808-2019 语义数据池 ----------------
PROVINCES = "京津沪渝冀晋蒙辽吉黑苏浙皖闽赣鲁豫鄂湘粤桂琼川贵云藏陕甘青宁新"
PLATE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"          # 808 车牌字母不含 I/O
PLATE_SUFFIX = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
ID_AREA_CODES = ["110101", "110105", "110108", "310101", "440103",
                 "510104", "330102", "420102", "500103", "610102"]
# 808-2019 报警标志位（演示子集）：1 超速报警 2 疲劳驾驶 4 急加速 8 急减速
ALARM_BITS = [1, 2, 4, 8]
# 国标驾驶事件码（1 急加速 2 急减速 3 急转弯 4 疲劳驾驶 5 超速 6 前向碰撞预警FCW 7 车道偏离LDW）
NATIONAL_EVENT_CODES = ["1", "2", "3", "4", "5", "6", "7"]
# 厂商私有事件码
VENDOR_EVENT_CODES = ["V_FCW", "V_LDW", "V_HMW", "V_PCW"]
# 少量非北京城市 (名称, 经度基准, 纬度基准)
OTHER_CITIES = [
    ("上海", 121.40, 31.20), ("广州", 113.30, 23.10), ("深圳", 114.05, 22.55),
    ("成都", 104.06, 30.66), ("杭州", 120.15, 30.28),
]
VEHICLE_MODELS = ["解放J6P", "东风天龙KL", "福田欧曼EST", "重汽豪沃TH7",
                  "陕汽德龙X6000", "江淮格尔发A5", "比亚迪T5", "上汽跃进H500"]
COMPANIES = ["北京迅达物流有限公司", "京诚运输集团", "华北快运股份公司",
             "沪上冷链物流有限公司", "穗通货运代理有限公司", "蓉城配运有限公司",
             "杭州云驰物流有限公司", "津门港联运输有限公司"]
COMPANY_SUFFIX = ["第一分公司", "第二分公司", "车队一部", "车队二部", "特种运输部"]

# ---------------- vehicle_gps 行号注入计划（数据行 1-based，不含表头） ----------------
N_GPS_ROWS = 50000          # 100 车 × 500 行（每车 1Hz 连续 500 秒）
ROWS_PER_VEHICLE = 500
MISSING_RANGE = (2001, 3000)                    # (a) 约 2% 行 手机号/证件号为空
DUP_RANGE = (5001, 5500)                        # (b) 约 1% 完全重复行 ← 复制 4501-5000
DUP_SRC_BASE = 4501
DRIFT_ROWS = list(range(10000, 19801, 200))     # (c) 50 个漂移点: 10000,10200,...,19800
DISORDER_ROWS = list(range(20000, 39001, 1000))  # (d) 20 处时间乱序: 20000,21000,...,39000

SUMMARY = []  # (文件名, 行数说明, 异常注入描述)

try:
    import openpyxl  # noqa: F401
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%dB" % n) if unit == "B" else ("%.1f%s" % (n, unit))
        n = float(n) / 1024.0


# ---------------- 基础数据构造 ----------------
def make_plate(rng):
    """真实格式: 省份简称汉字 + 发牌机关字母 + 5 位(数字或末位字母), 如 京A12345"""
    return (rng.choice(PROVINCES) + rng.choice(PLATE_LETTERS)
            + "%04d" % rng.randint(0, 9999) + rng.choice(PLATE_SUFFIX))


def make_phone(rng):
    return "1" + rng.choice("3456789") + "%09d" % rng.randint(0, 999999999)


def make_idcard(rng):
    area = rng.choice(ID_AREA_CODES)
    y = rng.randint(1962, 2002)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    seq = "%03d" % rng.randint(1, 999)
    body = "%s%04d%02d%02d%s" % (area, y, m, d, seq)
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_map = "10X98765432"
    s = sum(int(c) * w for c, w in zip(body, weights))
    return body + check_map[s % 11]


def make_bank_card(rng):
    n = rng.randint(16, 19)
    body = "".join(str(rng.randint(0, 9)) for _ in range(n - 1))
    s = 0
    for i, ch in enumerate(reversed(body)):
        dig = int(ch)
        if i % 2 == 0:
            dig *= 2
            if dig > 9:
                dig -= 9
        s += dig
    return body + str((10 - s % 10) % 10)


def build_vehicle_pool(rng, count):
    """每车: 车牌/基础坐标(北京为主)/司机(手机号+证件号配对) —— 每车固定一名司机"""
    pool = []
    for i in range(count):
        if rng.random() < 0.88 or not OTHER_CITIES:
            city, lon0, lat0 = "北京", rng.uniform(116.0, 117.0), rng.uniform(39.6, 40.2)
        else:
            city, lon0, lat0 = OTHER_CITIES[rng.randrange(len(OTHER_CITIES))]
            lon0 += rng.uniform(-0.3, 0.3)
            lat0 += rng.uniform(-0.2, 0.2)
        pool.append({
            "vehicle_id": "VEH%05d" % (i + 1),
            "plate_no": (PROVINCES[i % len(PROVINCES)] + PLATE_LETTERS[(i // len(PROVINCES)) % len(PLATE_LETTERS)]
                         + "%04d" % i + PLATE_SUFFIX[i % len(PLATE_SUFFIX)]),  # 序号入牌保证唯一
            "city": city,
            "lon0": round(lon0, 6),
            "lat0": round(lat0, 6),
            "driver_phone": make_phone(rng),
            "driver_idcard": make_idcard(rng),
        })
    return pool


def gen_gps_rows(seed):
    """生成 50000 行 GPS 轨迹（时间 1Hz 递增），随后按固定行号注入异常。"""
    rng = random.Random(seed)
    vehicles = build_vehicle_pool(rng, N_GPS_ROWS // ROWS_PER_VEHICLE)
    rows = []
    for vi, v in enumerate(vehicles):
        mileage = float(rng.randint(12000, 380000))  # 出发里程 km
        for s in range(ROWS_PER_VEHICLE):
            speed = rng.randint(0, 120)  # km/h
            mileage = round(mileage + speed / 3.6 / 1000.0, 1)
            t = T0 + timedelta(seconds=s)
            rows.append({
                "vehicle_id": v["vehicle_id"],
                "plate_no": v["plate_no"],
                "gps_time": t.strftime("%Y-%m-%d %H:%M:%S"),
                "longitude": round(v["lon0"] + rng.uniform(-0.02, 0.02), 6),
                "latitude": round(v["lat0"] + rng.uniform(-0.015, 0.015), 6),
                "speed": speed,
                "direction": rng.randint(0, 359),
                "altitude": rng.randint(28, 65),
                "alarm_flag": 0 if rng.random() > 0.03 else rng.choice(ALARM_BITS),
                "driver_phone": v["driver_phone"],
                "driver_idcard": v["driver_idcard"],
                "mileage": "%.1f" % mileage,
            })

    # (a) 缺失: 手机号/证件号置空
    for r in range(MISSING_RANGE[0], MISSING_RANGE[1] + 1):
        rows[r - 1]["driver_phone"] = ""
        rows[r - 1]["driver_idcard"] = ""
    # (b) 完全重复: 5001-5500 ← 4501-5000
    for i, r in enumerate(range(DUP_RANGE[0], DUP_RANGE[1] + 1)):
        rows[r - 1] = dict(rows[DUP_SRC_BASE - 1 + i])
    # (c) 漂移点: 跳到 [120,121)/[30,31)，与北京相邻行相距 >1 度
    for r in DRIFT_ROWS:
        rows[r - 1]["longitude"] = round(rng.uniform(120.0, 121.0), 6)
        rows[r - 1]["latitude"] = round(rng.uniform(30.0, 31.0), 6)
        rows[r - 1]["alarm_flag"] = rng.choice(ALARM_BITS)
    # (d) 时间乱序: 比前一行早 65 秒
    for r in DISORDER_ROWS:
        t = datetime.strptime(rows[r - 2]["gps_time"], "%Y-%m-%d %H:%M:%S") - timedelta(seconds=65)
        rows[r - 1]["gps_time"] = t.strftime("%Y-%m-%d %H:%M:%S")
    return rows


GPS_HEADER = ["vehicle_id", "plate_no", "gps_time", "longitude", "latitude",
              "speed", "direction", "altitude", "alarm_flag",
              "driver_phone", "driver_idcard", "mileage"]
# 0902 文件: 同义词列名 + 固定乱序
GPS_HEADER_CN = ["定位时间", "vehicle_id", "速度", "车牌号", "mileage", "经度",
                 "司机手机号", "方向", "证件号", "纬度", "alarm_flag"]
GPS_KEY_ORDER_CN = ["gps_time", "vehicle_id", "speed", "plate_no", "mileage",
                    "longitude", "driver_phone", "direction", "driver_idcard",
                    "latitude", "alarm_flag"]


def gps_anomaly_desc():
    return ("缺失:%d-%d(1000); 重复:%d-%d(500←%d起); 漂移:%d..%d步长200(50); "
            "乱序:%d..%d步长1000(20)" % (
                MISSING_RANGE[0], MISSING_RANGE[1], DUP_RANGE[0], DUP_RANGE[1],
                DUP_SRC_BASE, DRIFT_ROWS[0], DRIFT_ROWS[-1],
                DISORDER_ROWS[0], DISORDER_ROWS[-1]))


def gen_vehicle_gps_0901():
    path = os.path.join(OUT_DIR, "vehicle_gps_20260901.csv")
    rows = gen_gps_rows(SEED + 1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(GPS_HEADER)
        for r in rows:
            w.writerow([str(r[k]) for k in GPS_HEADER])
    SUMMARY.append(("vehicle_gps_20260901.csv", "50000 数据行", gps_anomaly_desc()))


def gen_vehicle_gps_0902():
    path = os.path.join(OUT_DIR, "vehicle_gps_20260902.csv")
    rows = gen_gps_rows(SEED + 2)
    with open(path, "w", encoding="gbk", newline="") as f:  # GBK 编码演示
        w = csv.writer(f, lineterminator="\n")
        w.writerow(GPS_HEADER_CN)
        for r in rows:
            w.writerow([str(r[k]) for k in GPS_KEY_ORDER_CN])
    SUMMARY.append(("vehicle_gps_20260902.csv", "50000 数据行(GBK/中文列名)",
                    "与0901相同行号规则; 列名同义词且乱序"))


# ---------------- fleet_info ----------------
FLEET_PER_SHEET = [667, 667, 666]
FLEET_BLANK_AFTER = [133, 266, 399, 532, 665]  # 每个 sheet: 原始数据行计数处之后插全空行
FLEET_HEADER = ["fleet_id", "plate_no", "company", "vehicle_model",
                "purchase_date", "bank_card", "contact_phone"]


def gen_fleet_rows(seed, n):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        fmt = i % 3
        base_plate = rng.choice(PROVINCES) + rng.choice(PLATE_LETTERS) + "%05d" % rng.randint(0, 99999)
        if fmt == 0:                      # 带 ·
            plate = base_plate[:2] + "·" + base_plate[2:]
        elif fmt == 1:                    # 字母小写
            plate = base_plate[:1] + base_plate[1].lower() + base_plate[2:]
        else:                             # 带空格
            plate = base_plate[:2] + " " + base_plate[2:]
        pd_ = date(rng.randint(2018, 2025), rng.randint(1, 12), rng.randint(1, 28))
        rows.append([
            "FLT%04d" % (i + 1),
            plate,
            rng.choice(COMPANIES) + rng.choice(COMPANY_SUFFIX),
            rng.choice(VEHICLE_MODELS),
            pd_.isoformat(),
            make_bank_card(rng),
            make_phone(rng),
        ])
    return rows


def gen_fleet_info():
    if HAS_OPENPYXL:
        import openpyxl
        path = os.path.join(OUT_DIR, "fleet_info.xlsx")
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        for si, n in enumerate(FLEET_PER_SHEET):
            ws = wb.create_sheet("sheet%d" % (si + 1))
            ws.append(FLEET_HEADER)
            rows = gen_fleet_rows(SEED + 3 + si, n)
            for ri, row in enumerate(rows, start=1):
                ws.append(row)
                if ri in FLEET_BLANK_AFTER:
                    ws.append([])  # 全空行
            ws.append([])
        wb.save(path)
        SUMMARY.append(("fleet_info.xlsx", "%d 数据行/3sheet + 每sheet 5 空行" % sum(FLEET_PER_SHEET),
                        "空行@数据行 134/268/402/536/670; 车牌混杂 ·/小写/空格; 银行卡16-19位"))
    else:
        blank_note = []
        for si, n in enumerate(FLEET_PER_SHEET):
            path = os.path.join(OUT_DIR, "fleet_info_sheet%d.csv" % (si + 1))
            rows = gen_fleet_rows(SEED + 3 + si, n)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(FLEET_HEADER)
                for ri, row in enumerate(rows, start=1):
                    w.writerow(row)
                    if ri in FLEET_BLANK_AFTER:
                        w.writerow([])  # 全空行
            blank_note.append("sheet%d" % (si + 1))
        SUMMARY.append(("fleet_info_sheet1/2/3.csv", "%d 数据行/3文件 + 每文件 5 空行" % sum(FLEET_PER_SHEET),
                        "空行@数据行 134/268/402/536/670; 车牌混杂 ·/小写/空格; 银行卡16-19位"
                        + "(本机无openpyxl,真实容器环境同逻辑产出 fleet_info.xlsx)"))


# ---------------- driver_events.json ----------------
def gen_driver_events():
    path = os.path.join(OUT_DIR, "driver_events.json")
    rng = random.Random(SEED + 8)
    vehicles = build_vehicle_pool(rng, 60)
    events = []
    for i in range(1, 10001):
        v = vehicles[rng.randrange(len(vehicles))]
        if i % 2 == 0:  # 一半厂商私有码
            code, source = rng.choice(VENDOR_EVENT_CODES), "vendor"
        else:           # 一半国标码
            code, source = rng.choice(NATIONAL_EVENT_CODES), "national"
        t = T0 + timedelta(seconds=rng.randint(0, 86399))
        events.append({
            "event_id": "EVT%06d" % i,
            "plate_no": v["plate_no"],
            "event_time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "event_code": code,
            "event_source": source,
            "speed": rng.randint(0, 130),
            "lat": round(v["lat0"] + rng.uniform(-0.05, 0.05), 6),
            "lon": round(v["lon0"] + rng.uniform(-0.05, 0.05), 6),
            "extra": {"dsm_level": rng.randint(1, 3)},
        })
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"events": events}, f, ensure_ascii=False, indent=1)
    SUMMARY.append(("driver_events.json", "10000 事件",
                    "国标码(1-7)5000/厂商码(V_FCW,V_LDW,V_HMW,V_PCW)5000"))


# ---------------- driver_notes.txt ----------------
NOTE_TEMPLATES = [
    "今日{route}方向车流较大，平均时速{sp}公里，{sensitive}请调度关注。",
    "凌晨{h}点从{loc}出发，装载{goods}共{t}吨，{sensitive}随车备货清单已上传。",
    "途经服务区休息{m}分钟，轻微疲劳，{sensitive}已服用提神饮品，继续行驶。",
    "客户收货延迟{m}分钟，{sensitive}建议下单一并备注装卸货窗口期。",
    "雨雾天气能见度低，降速至{sp}公里行驶，{sensitive}已开启防碰撞预警。",
    "车辆胎压异常报警，已驶入{loc}检修，{sensitive}请安排备用车辆接驳。",
    "今日往返{route}两趟，通行费{fee}元，{sensitive}过路发票已拍照留档。",
    "到达园区等待叫号{h}小时，{sensitive}园区门禁需要提前报备车牌。",
]
ROUTES = ["京藏高速", "京沪高速", "京港澳高速", "六环", "机场高速", "沪昆高速"]
LOCS = ["马驹桥服务区", "窦店服务区", "青云店", "杭州南枢纽", "东莞常平", "郫都园区"]
GOODS = ["冷链生鲜", "建材钢管", "日用百货", "快递包裹", "化工原料", "电子元器件"]
SENSITIVE_FALLBACK = ["路况正常，", "货物完好，", "一切顺利，", "打卡完成，"]


def gen_driver_notes():
    path = os.path.join(OUT_DIR, "driver_notes.txt")
    rng = random.Random(SEED + 9)
    surnames = "王李张刘陈杨赵黄周吴徐孙马朱胡郭何高林"
    givens = ["伟", "芳", "强", "敏", "磊", "军", "洋", "勇", "艳", "杰", "涛", "明"]
    lines = []
    for seg in range(500):
        n_lines = rng.randint(3, 6)
        hit_idx = set(rng.sample(range(n_lines), rng.randint(1, 2)))
        lines.append("---- 司机日志 第%03d段 ----" % (seg + 1))
        for li in range(n_lines):
            tpl = rng.choice(NOTE_TEMPLATES)
            if li in hit_idx:
                kind = rng.randint(0, 2)
                if kind == 0:
                    sens = make_phone(rng)
                elif kind == 1:
                    name = rng.choice(surnames) + "".join(rng.sample(givens, 2)).lower()
                    sens = name + "@%s.com" % rng.choice(["163", "126", "qq", "sina"])
                else:
                    sens = make_idcard(rng)
            else:
                sens = rng.choice(SENSITIVE_FALLBACK)
            line = tpl.format(route=rng.choice(ROUTES), sp=rng.randint(30, 100),
                              h=rng.randint(1, 5), loc=rng.choice(LOCS),
                              goods=rng.choice(GOODS), t=rng.randint(3, 30),
                              m=rng.randint(5, 40), fee=rng.randint(80, 600),
                              sensitive=sens)
            lines.append(line)
        lines.append("")  # 段间空行
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    SUMMARY.append(("driver_notes.txt", "500 段(每段3-6行)",
                    "每段嵌入 1~2 个明文手机号/邮箱/身份证"))


# ---------------- vehicle_photos.zip ----------------
def build_gray_jpeg(size=64):
    """标准库手写最小合法基线 JPEG（64x64 纯灰度，全零 DCT 块，自定义最简 Huffman 表）。"""
    out = bytearray(b"\xff\xd8")                                    # SOI
    qt = b"\x00" + bytes([1] * 64)                                  # DQT: 表0, 全1量化
    out += b"\xff\xdb" + struct.pack(">H", len(qt) + 2) + qt
    sof = bytes([8]) + struct.pack(">HH", size, size) + b"\x01" + bytes([1, 0x11, 0])
    out += b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof      # SOF0 基线灰度
    dht_dc = b"\x00" + bytes([0, 1] + [0] * 14) + b"\x00"           # DC: 1个码长2 → "00"
    out += b"\xff\xc4" + struct.pack(">H", len(dht_dc) + 2) + dht_dc
    dht_ac = b"\x10" + bytes([0, 0, 0, 0, 1] + [0] * 11) + b"\x00"  # AC: EOB 码长4 → "0000"
    out += b"\xff\xc4" + struct.pack(">H", len(dht_ac) + 2) + dht_ac
    sos = b"\x01" + bytes([1, 0x00]) + bytes([0, 63, 0])            # SOS
    out += b"\xff\xda" + struct.pack(">H", len(sos) + 2) + sos
    n_blocks = (size // 8) * (size // 8)                            # 每块: DC(0)="00"+EOB="0000"
    bits = "000000" * n_blocks + "1" * ((-(n_blocks * 6)) % 8)      # 末字节补 1
    entropy = bytearray()
    for i in range(0, len(bits), 8):
        b = int(bits[i:i + 8], 2)
        entropy.append(b)
        if b == 0xFF:
            entropy.append(0x00)                                    # 字节填充
    out += entropy + b"\xff\xd9"                                    # EOI
    return bytes(out)


def build_exif_app1(make):
    """构造含 IFD0/Make(0x010F) 的最小 EXIF APP1 段（小端 TIFF）。"""
    data = make.encode("ascii") + b"\x00"
    ifd = struct.pack("<H", 1)                                   # IFD0 条目数=1
    ifd += struct.pack("<HHI", 0x010F, 2, len(data))             # Make, ASCII
    ifd += struct.pack("<I", 26)                                 # value offset: 8+2+12+4
    ifd += struct.pack("<I", 0)                                  # next IFD = 0
    ifd += data
    assert len(ifd) == 18 + len(data)
    tiff = b"II" + struct.pack("<H", 42) + struct.pack("<I", 8) + ifd
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def inject_exif(jpeg, app1):
    assert jpeg[:2] == b"\xff\xd8" and jpeg[-2:] == b"\xff\xd9"
    pos = 2
    if jpeg[2:4] == b"\xff\xe0":                                 # 跳过 JFIF APP0 再插入
        pos = 2 + 2 + struct.unpack(">H", jpeg[4:6])[0]
    return jpeg[:pos] + app1 + jpeg[pos:]


def gen_vehicle_photos():
    path = os.path.join(OUT_DIR, "vehicle_photos.zip")
    base = build_gray_jpeg(64)
    assert base[:2] == b"\xff\xd8" and base[-2:] == b"\xff\xd9"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(1, 21):
            img = inject_exif(base, build_exif_app1("DEMO-CAM-%02d" % i))
            zi = zipfile.ZipInfo("photo_%02d.jpg" % i, date_time=(2026, 9, 30, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, img)
    SUMMARY.append(("vehicle_photos.zip", "20 张 JPEG(占位图+EXIF Make段)",
                    "真实环境用 Pillow 生成带 EXIF/GPS 图像; 演示包为轻量占位图, EXIF 剥离由处理服务执行"))


# ---------------- dashcam_clips.zip ----------------
MP4_HDR = (b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
           b"\x00\x00\x00\x08free")
MOV_HDR = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  "
AVI_HDR = b"RIFF\x00\x00\x00\x00AVI LIST\x00\x00\x00\x00hdrl"
MKV_HDR = b"\x1a\x45\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x00\x1fB\x86\x81\x01B\xf7\x81\x01B\xf2\x81\x04B\xf3\x81\x08"


def gen_dashcam_clips():
    path = os.path.join(OUT_DIR, "dashcam_clips.zip")
    clips = [("dashcam_01.mp4", MP4_HDR), ("dashcam_02.mov", MOV_HDR),
             ("dashcam_03.mp4", MP4_HDR), ("dashcam_04.avi", AVI_HDR),
             ("dashcam_05.mkv", MKV_HDR)]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, hdr in clips:
            blob = hdr + b"\x00" * (48 * 1024 - len(hdr))        # ~48KB 占位
            zi = zipfile.ZipInfo(name, date_time=(2026, 9, 30, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, blob)
    SUMMARY.append(("dashcam_clips.zip", "5 段视频占位(mp4/mov/avi/mkv)",
                    "真实环境由 ffmpeg 生成 3-5s 320x240 低码率视频; 演示包为二进制头部占位"))


# ---------------- unmasked_sample.csv ----------------
def gen_unmasked_sample():
    path = os.path.join(OUT_DIR, "unmasked_sample.csv")
    rng = random.Random(SEED + 10)
    surnames = "王李张刘陈杨赵黄周吴"
    givens = ["伟", "芳", "娜", "敏", "磊", "军", "洋", "勇", "艳", "杰", "静", "超"]
    notes = ["内部薪酬Adjust系数勿外传", "vip客户白名单渠道", "竞对报价底线备忘",
             "高管直连专线号段", "内部风控豁免名单", "并购标的信息备注"]
    header = ["plate_no", "driver_name", "phone", "id_card", "bank_card", "secret_note"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for _ in range(200):
            name = rng.choice(surnames) + rng.choice(givens) + rng.choice(givens)
            w.writerow([
                rng.choice(PROVINCES) + rng.choice(PLATE_LETTERS) + "%05d" % rng.randint(0, 99999),
                name,
                make_phone(rng),
                make_idcard(rng),
                make_bank_card(rng),
                rng.choice(notes),
            ])
    SUMMARY.append(("unmasked_sample.csv", "200 数据行", "全字段明文; 上传密级3而产品密级设1制造密级倒挂 → 合规引擎 R1 亮红拦阻"))


def main():
    gen_vehicle_gps_0901()
    gen_vehicle_gps_0902()
    gen_fleet_info()
    gen_driver_events()
    gen_driver_notes()
    gen_vehicle_photos()
    gen_dashcam_clips()
    gen_unmasked_sample()

    print("=" * 100)
    print("演示数据生成摘要 (seed=%d, 输出目录=%s)" % (SEED, OUT_DIR))
    print("=" * 100)
    print("%-34s %-34s %s" % ("文件名", "行数/规模", "异常注入位置"))
    print("-" * 100)
    for name, rows_desc, anomaly in SUMMARY:
        p = os.path.join(OUT_DIR, name)
        size = os.path.getsize(p) if os.path.exists(p) else 0
        print("%-34s %-34s %s" % (name, rows_desc + " | " + human_size(size), anomaly))
    print("-" * 100)
    print("全部文件生成完毕，共 %d 项。" % len(SUMMARY))


if __name__ == "__main__":
    main()
