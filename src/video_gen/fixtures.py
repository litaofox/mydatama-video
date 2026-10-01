"""演示数据 fixtures：调用独立复制的生成器，与 mydatama 仓库无任何文件级共享。"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

from . import config

REQUIRED = ["vehicle_gps_20260901.csv", "vehicle_gps_20260902.csv",
            "driver_notes.txt", "unmasked_sample.csv", "vehicle_photos.zip"]


def ensure_fixtures() -> Path:
    """缺失时用固定种子生成全套演示文件（纯标准库，幂等可重复）。"""
    missing = [f for f in REQUIRED if not (config.FIXTURES_DIR / f).exists()]
    if missing:
        print(f"[fixtures] 生成演示数据 {len(missing)} 个文件（固定种子）...")
        subprocess.run(
            [sys.executable, str(config.FIXTURES_GEN)],
            cwd=config.FIXTURES_GEN.parent,
            check=True,
        )
    return config.FIXTURES_DIR


def extract_first_jpg(dest_dir: Path) -> Path:
    """从 vehicle_photos.zip 解出第一张 jpg 作为图片模态演示素材。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / "photo_01.jpg"
    if not out.exists():
        with zipfile.ZipFile(config.FIXTURES_DIR / "vehicle_photos.zip") as zf:
            member = next(n for n in zf.namelist() if n.lower().endswith(".jpg"))
            out.write_bytes(zf.read(member))
    return out
