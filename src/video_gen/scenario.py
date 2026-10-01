"""15 步演示动线自动化：用公开 API 造好演示状态，返回每镜应截图的页面路由。

状态造数走 HTTP API（稳定），页面仅用于截图（DOM 变更影响面只在 browser.py）。
"""
from __future__ import annotations

import time
from pathlib import Path

from . import config, fixtures
from .platform_api import PlatformClient, PlatformError


def run(client: PlatformClient, scratch: Path) -> dict[int, str]:
    """执行完整动线。返回 {分镜号: 浏览器路由}。"""
    fdir = fixtures.ensure_fixtures()
    routes: dict[int, str] = {}

    # 镜 24：大屏（先取空态之外的任意状态亦可，这里按动线最终统计丰富）
    routes[24] = "/screen"

    # ---- 步骤 2~4：0901 上传/五阶段/修复重跑 ----
    print("[scenario] ① 上传 vehicle_gps_20260901.csv（5 万行，约 1 分钟）...")
    f1 = client.upload_file(fdir / "vehicle_gps_20260901.csv", "TRANSPORT", 2)
    client.wait_ready(f1, config.LIVE_TIMEOUT)
    print(f"[scenario]   fileId={f1} READY，执行修复重跑...")
    client.repair(f1)
    routes[25] = f"/processing/files/{f1}"

    # ---- 步骤 5：多模态（文本 + 图片；视频占位文件不保证可处理，容错跳过）----
    print("[scenario] ② 多模态：driver_notes.txt + 一张实拍 JPG...")
    txt_id = client.upload_file(fdir / "driver_notes.txt", "TRANSPORT", 2)
    client.wait_ready(txt_id, config.LIVE_TIMEOUT)
    try:
        jpg = fixtures.extract_first_jpg(scratch)
        img_id = client.upload_file(jpg, "TRANSPORT", 2)
        client.wait_ready(img_id, config.LIVE_TIMEOUT)
    except PlatformError as exc:
        print(f"[scenario]   图片处理跳过: {exc}")
    routes[26] = "/processing/files"

    # ---- 步骤 6~7：资产与血缘（找到第一个结构化资产）----
    assets = client.list_assets("vehicle")
    asset_id = assets[0]["id"] if assets else None
    if asset_id:
        routes[27] = f"/governance/lineage/{asset_id}"
        print(f"[scenario] ③ 血缘截图资产 id={asset_id}")
    else:
        routes[27] = "/governance/assets"

    # ---- 步骤 8：数据集 v1 ----
    print("[scenario] ④ 创建驾驶行为样本集 v1...")
    ds1 = client.create_dataset(
        "驾驶行为样本集", "驾驶行为分析",
        {"modality": "STRUCTURED", "bizDomain": "TRANSPORT", "secretLevelMax": 4},
        "五阶段治理后的北斗货运驾驶行为数据")
    v1 = client.create_version(ds1, "v1 首批 GPS 数据")
    print(f"[scenario]   dataset={ds1} version={v1.get('versionNo')} itemCount={v1.get('itemCount')}")

    # ---- 步骤 9：0902（GBK+中文列名）→ v2 ----
    print("[scenario] ⑤ 上传 vehicle_gps_20260902.csv（GBK/中文列名）...")
    f2 = client.upload_file(fdir / "vehicle_gps_20260902.csv", "TRANSPORT", 2)
    client.wait_ready(f2, config.LIVE_TIMEOUT)
    v2 = client.create_version(ds1, "v2 追加 0902")
    print(f"[scenario]   v2 itemCount={v2.get('itemCount')}")
    routes[28] = f"/dataset/{ds1}"

    # ---- 步骤 10~12：正面产品（四绿→登记→挂牌）----
    print("[scenario] ⑥ 正面数据包产品：配置→生成→合规...")
    code = f"PRD-{time.strftime('%Y%m%d')}-{int(time.time()) % 1000000:06d}"
    pos = _create_package_product(client, v2["id"], code, secret_level=2)
    client.product_action(pos, "configure")
    client.product_action(pos, "generate")
    comp = client.product_action(pos, "compliance/run")
    print(f"[scenario]   正面产品合规: {comp.get('status')}")
    if comp.get("status") == "PASSED":
        reg = client.product_action(pos, "register")
        print(f"[scenario]   登记凭证号 {reg.get('regNo')} → 挂牌")
        client.product_action(pos, "listing")

    # ---- 步骤 13：反面产品（密级倒挂 → R1 必红 → BLOCKED）----
    print("[scenario] ⑦ 反面产品：上传明文样例（密级 3）+ 产品密级倒挂...")
    neg_asset = client.upload_file(fdir / "unmasked_sample.csv", "RISK", 3)
    client.wait_ready(neg_asset, config.LIVE_TIMEOUT)
    ds2 = client.create_dataset(
        "风险明文样例集", "合规反面演示",
        {"bizDomain": "RISK", "secretLevelMax": 4},
        "用于演示密级倒挂被合规引擎拦阻")
    nv = client.create_version(ds2, "明文样例版本")
    neg = _create_package_product(client, nv["id"], code + "-X", secret_level=1)
    client.product_action(neg, "configure")
    client.product_action(neg, "generate")
    neg_comp = client.product_action(neg, "compliance/run")
    print(f"[scenario]   反面产品合规: {neg_comp.get('status')}（预期 BLOCKED）")
    routes[29] = f"/product/{neg}"

    # ---- 步骤 14~15：挂牌后大屏 + 审计 ----
    routes[30] = "/iam/audit"
    return routes


def _create_package_product(client: PlatformClient, version_id: int, code: str,
                            secret_level: int) -> int:
    template_id = client.template_id_by_code("tpl-data-package-v1")
    return client.create_product({
        "templateId": template_id,
        "name": "货运驾驶行为精算样本集" if secret_level >= 2 else "明文风险样例产品",
        "code": code,
        "datasetVersionId": version_id,
        "secretLevel": secret_level,
        "category": "交通物流",
        "pricingModel": "PER_MONTH",
        "price": 1999.00,
        "description": "mydatama-video 自动化演示生成",
        "manualMeta": {
            "sourceDesc": "货运车辆北斗 GPS 轨迹，经五阶段治理流水线处理",
            "fieldDesc": "车牌/定位时间/经纬度/速度/方向/司机联系方式（已脱敏）",
            "updateFreq": "每月",
            "deliveryMode": "zip 数据包下载",
        },
    })
